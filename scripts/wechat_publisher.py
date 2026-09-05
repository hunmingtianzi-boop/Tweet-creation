#!/usr/bin/env python3
"""Transactional WeChat Official Account API publisher.

This module deliberately separates five truths:

* account/token preflight passed;
* source-SHA assets were uploaded and committed to an account map;
* one exact compiled payload was saved as a draft;
* a publish job was submitted after fresh explicit confirmation;
* the job reached status=0 and returned article URLs.

The default command path stops after the draft.  Ambiguous non-idempotent API
calls are never retried automatically; their durable operation row must be
reconciled before another mutation can be attempted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import random
import re
import sqlite3
import ssl
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional, Protocol

if __name__ == "__main__":
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/wechat_publisher.py")

from asset_quality import file_sha256
from transport_fidelity import (
    PUBLICATION_CONFIRMATION_RECEIPT_SOURCE,
    UPLOAD_MAP_SOURCE,
    WECHAT_AUTHOR_MAX_CHARS,
    WECHAT_BODY_IMAGE_MAX_BYTES,
    WECHAT_CONTENT_MAX_BYTES,
    WECHAT_CONTENT_MAX_CHARS,
    WECHAT_COVER_IMAGE_MAX_BYTES,
    WECHAT_DIGEST_MAX_CHARS,
    WECHAT_MEDIA_ID_MAX_CHARS,
    WECHAT_TITLE_MAX_CHARS,
    _export_delivery_assets,
    _handoff_cover_asset,
    _is_wechat_cdn_url,
    _TransportHTML,
    _validate_transport_fidelity_contract,
    _visual_similarity,
    canonical_transport_revision_hash,
    resolve_local_asset,
    validate_wechat_upload_map,
    validate_transport_fidelity_diagnostic,
    verify_host_publication_confirmation_receipt,
    text_sha256,
)
from wechat_interaction_policy import _validate_mobile_profile, CurrentSessionMobileAuthority
from validate_workflow_attribution import validate_workflow_attribution_handoff
from safe_paths import (
    SafePathError,
    new_directory_path,
    new_file_path,
    write_bytes_create_once,
    write_text_create_once,
)


API_BASE = "https://api.weixin.qq.com"
TRANSIENT_ERRCODES = {-1, 45009}
SUCCESS_ERRCODES = {0, None}
PUBLISH_STATUS = {
    0: "published",
    1: "publishing",
    2: "originality-check-failed",
    3: "failed",
    4: "audit-rejected",
    5: "all-articles-deleted",
    6: "all-articles-blocked",
}
TERMINAL_FAILURE_STATUSES = {2, 3, 4, 5, 6}
CONFIRMATION_SOURCE = "wechat-explicit-publication-confirmation-v1"
CONFIRMATION_MAX_AGE_SECONDS = 600
DEFAULT_TIMEOUT_SECONDS = 30
MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}
SAFE_PLATFORM_PATH_ALIASES = {
    # macOS exposes these immutable compatibility aliases at the filesystem
    # root.  TemporaryDirectory commonly returns /var/folders even though its
    # canonical storage is /private/var/folders; user-created symlinks remain
    # forbidden below these exact aliases.
    Path("/var"): Path("/private/var"),
    Path("/tmp"): Path("/private/tmp"),
    Path("/etc"): Path("/private/etc"),
}
CURRENT_SESSION_READBACK_CAPTURE_SOURCE = (
    "wechat-current-session-readback-capture-bundle-v1"
)


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_digest(path: Path) -> str:
    return "sha256:" + file_sha256(path)


def _parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be an RFC3339 timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{label} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _secure_runtime_roots() -> tuple[Path, ...]:
    """Return roots beneath which credentialed capture outputs are forbidden."""

    roots = {Path(__file__).resolve().parent.parent}
    marker = getattr(sys, "_org_wechat_secure_runtime_v1", None)
    if isinstance(marker, dict):
        value = marker.get("workspace_root")
        if isinstance(value, str) and value:
            try:
                roots.add(Path(value).resolve(strict=True))
            except OSError as exc:
                raise ValueError("secure runtime workspace root is unavailable") from exc
    return tuple(sorted(roots, key=lambda item: str(item)))


def _require_external_output(path: Path, *, label: str) -> Path:
    """Keep one already-normalized output path outside every runtime root."""

    for root in _secure_runtime_roots():
        try:
            path.relative_to(root)
        except ValueError:
            continue
        raise ValueError(f"{label} must remain outside the installed runtime")
    return path


def _prepare_capture_output_file(path: Path, *, label: str) -> Path:
    try:
        output = new_file_path(path, label=label)
    except SafePathError as exc:
        raise ValueError(str(exc)) from exc
    return _require_external_output(output, label=label)


def _prepare_capture_output_directory(path: Path, *, label: str) -> Path:
    try:
        output = new_directory_path(path, label=label)
    except SafePathError as exc:
        raise ValueError(str(exc)) from exc
    return _require_external_output(output, label=label)


def _create_capture_directory(path: Path, *, label: str) -> Path:
    """Reserve a validated directory exactly once without creating parents."""

    try:
        os.mkdir(path, mode=0o700)
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError(f"{label} cannot be created once: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"{label} must be a real directory")
    return path


def _absolute_path_without_symlinks(path: Path, *, label: str) -> Path:
    """Return an absolute path after rejecting every existing symlink component."""

    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    absolute = Path(os.path.abspath(os.fspath(expanded)))
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor /= part
        if os.path.lexists(cursor) and cursor.is_symlink():
            allowed_target = SAFE_PLATFORM_PATH_ALIASES.get(cursor)
            if allowed_target is not None:
                try:
                    if cursor.resolve(strict=True) == allowed_target:
                        continue
                except OSError:
                    pass
            raise ValueError(f"{label} must not traverse a symlink: {cursor}")
    return absolute.resolve(strict=False)


def _upload_journal_path(output_path: Path) -> Path:
    return output_path.with_name(f".{output_path.name}.upload-journal.jsonl")


def _prepare_publisher_store_path(path: Path) -> Path:
    """Create or reopen one lexical non-symlink SQLite file in an existing parent."""

    store = _absolute_path_without_symlinks(path, label="publisher store")
    parent = store.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError(
            "publisher store parent must already exist as a real directory"
        )
    if store.exists():
        metadata = store.lstat()
        if not stat.S_ISREG(metadata.st_mode) or store.is_symlink():
            raise ValueError("publisher store must be a regular non-symlink file")
        return store
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(store, flags, 0o600)
    except OSError as exc:
        raise ValueError(f"cannot create publisher store safely: {exc}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("publisher store must be a regular file")
    finally:
        os.close(descriptor)
    return store


def _prepare_create_once_output(output_path: Path) -> tuple[Path, Path]:
    """Validate the upload-map destination before the first remote mutation.

    The parent must already exist.  This deliberately avoids creating a broad
    user-supplied directory tree from a credentialed publisher process.
    """

    output = _absolute_path_without_symlinks(output_path, label="upload map output")
    if os.path.lexists(output):
        raise ValueError(f"upload map output already exists; refusing overwrite: {output}")
    parent = output.parent
    try:
        parent_stat = parent.stat()
    except OSError as exc:
        raise ValueError("upload map output parent must already exist") from exc
    if not stat.S_ISDIR(parent_stat.st_mode) or parent.is_symlink():
        raise ValueError("upload map output parent must be a non-symlink directory")
    journal = _absolute_path_without_symlinks(
        _upload_journal_path(output), label="upload transaction journal"
    )
    if os.path.lexists(journal) and (journal.is_symlink() or not journal.is_file()):
        raise ValueError("upload transaction journal must be a regular non-symlink file")
    return output, journal


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _create_once_bytes(path: Path, payload: bytes) -> None:
    """Atomically install new bytes without ever replacing the target."""

    path = _absolute_path_without_symlinks(path, label="create-once artifact")
    if os.path.lexists(path):
        raise ValueError(f"refusing to overwrite create-once artifact: {path}")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError as exc:
            raise ValueError(f"refusing to overwrite create-once artifact: {path}") from exc
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _create_once_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _create_once_bytes(path, encoded)


class UploadTransactionJournal:
    """Append-only, hash-chained recovery record for one upload-map path."""

    SOURCE = "wechat-upload-transaction-journal-v1"

    def __init__(self, path: Path, binding: Mapping[str, Any]) -> None:
        self.path = path
        self.binding = dict(binding)
        self.event_index = -1
        self.last_event_sha256: str | None = None
        self.events: list[dict[str, Any]] = []
        if os.path.lexists(path):
            self._load()
            self.append("resumed", {})
        else:
            self._create()

    @staticmethod
    def _event_digest(event: Mapping[str, Any]) -> str:
        return _canonical_sha256(
            {key: value for key, value in event.items() if key != "event_sha256"}
        )

    def _event(self, name: str, data: Mapping[str, Any]) -> dict[str, Any]:
        unsigned: dict[str, Any] = {
            "schema_version": 1,
            "source": self.SOURCE,
            "event_index": self.event_index + 1,
            "previous_event_sha256": self.last_event_sha256,
            "event": name,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "binding": self.binding,
            "data": dict(data),
        }
        return {**unsigned, "event_sha256": self._event_digest(unsigned)}

    def _create(self) -> None:
        event = self._event("reserved", {})
        encoded = (json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        _create_once_bytes(self.path, encoded)
        self.event_index = 0
        self.last_event_sha256 = str(event["event_sha256"])
        self.events = [event]

    def _load(self) -> None:
        expected_fields = {
            "schema_version",
            "source",
            "event_index",
            "previous_event_sha256",
            "event",
            "recorded_at",
            "binding",
            "data",
            "event_sha256",
        }
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise ValueError("upload transaction journal is unreadable") from exc
        if not lines:
            raise ValueError("upload transaction journal is empty; reconcile manually")
        previous: str | None = None
        parsed_events: list[dict[str, Any]] = []
        for index, line in enumerate(lines):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("upload transaction journal is truncated or invalid") from exc
            if (
                not isinstance(event, dict)
                or set(event) != expected_fields
                or event.get("schema_version") != 1
                or event.get("source") != self.SOURCE
                or event.get("event_index") != index
                or event.get("previous_event_sha256") != previous
                or event.get("binding") != self.binding
                or not isinstance(event.get("data"), dict)
                or event.get("event_sha256") != self._event_digest(event)
                or (index == 0 and event.get("event") != "reserved")
            ):
                raise ValueError(
                    "upload transaction journal binding/hash chain is invalid; reconcile manually"
                )
            previous = str(event["event_sha256"])
            parsed_events.append(event)
        self.event_index = len(lines) - 1
        self.last_event_sha256 = previous
        self.events = parsed_events

    def append(self, name: str, data: Mapping[str, Any]) -> None:
        event = self._event(name, data)
        encoded = (json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        descriptor = os.open(
            self.path,
            os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0),
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            os.close(descriptor)
            raise ValueError("upload transaction journal is not a regular file")
        with os.fdopen(descriptor, "ab") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        self.event_index += 1
        self.last_event_sha256 = str(event["event_sha256"])
        self.events.append(event)

    def verify_committed_uploads(self, store: "PublisherStore") -> None:
        """Require every journal commitment to exist in this exact ledger."""

        for event in self.events:
            if event.get("event") != "upload-committed":
                continue
            data = event.get("data")
            if not isinstance(data, dict):
                raise ValueError(
                    "upload journal commitment is invalid; reconcile manually"
                )
            row = store.connection.execute(
                "SELECT state,result_json FROM uploads WHERE target_account_ref=? "
                "AND source_sha256=? AND kind=?",
                (
                    self.binding.get("target_account_ref"),
                    data.get("source_sha256"),
                    data.get("kind"),
                ),
            ).fetchone()
            result = None
            if (
                row is not None
                and row["state"] == "complete"
                and isinstance(row["result_json"], str)
            ):
                try:
                    result = json.loads(row["result_json"])
                except json.JSONDecodeError:
                    result = None
            expected = {
                "response_sha256": data.get("response_sha256"),
                "uploaded_at": data.get("uploaded_at"),
                "url": data.get("hosted_url"),
                "media_id": data.get("media_id"),
            }
            if not isinstance(result, dict) or any(
                result.get(key) != value for key, value in expected.items()
            ):
                raise ValueError(
                    "upload journal commitment has no matching complete transaction "
                    "in the bound publisher store; reconcile manually"
                )


def _create_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


class WeChatAPIError(RuntimeError):
    def __init__(self, message: str, *, errcode: int | None = None) -> None:
        super().__init__(message)
        self.errcode = errcode


class AmbiguousMutation(RuntimeError):
    """The request may have reached WeChat; automatic replay is forbidden."""


@dataclass(frozen=True)
class HostScreenshotCapture:
    """Opaque result returned by the active host's UI capture adapter."""

    png_bytes: bytes
    captured_at: str
    capture_event_id: str


@dataclass(frozen=True)
class CurrentSessionPublicationChallenge:
    """Exact live facts a host must re-observe before current-session submit."""

    target_account_ref: str
    article_revision: str
    draft_media_id: str
    draft_payload_sha256: str
    compile_report_sha256: str
    live_root_path: Path
    live_root_sha256: str
    readback_sha256: str
    confirmation_nonce: str


@dataclass(frozen=True)
class CurrentSessionPublicationAuthorization:
    """Non-portable host callback result; never accepted from JSON."""

    target_account_ref: str
    article_revision: str
    draft_media_id: str
    draft_payload_sha256: str
    compile_report_sha256: str
    readback_sha256: str
    ardot_live_root_sha256: str
    confirmation_nonce: str
    host_session_id: str
    confirmation_event_id: str
    confirmed_at: str


class CurrentSessionHostAuthority(Protocol):
    """Non-cryptographic policy hook supplied by a trusted embedding harness.

    This ``Protocol`` is dependency injection, not independent evidence and not
    an authentication boundary against Python running in this process. It is
    valid only when the embedding harness owns the process and does not execute
    model-controlled Python inside that trust boundary. The checked-in Codex
    adapter leaves the hook unavailable and the standalone CLI injects
    ``None``. A portable claim still requires verified host receipts.
    """

    def capture_wechat_chapters(
        self,
        *,
        target_account_ref: str,
        draft_media_id: str,
        article_revision: str,
        chapter_ids: tuple[str, ...],
    ) -> Mapping[str, HostScreenshotCapture]: ...

    def verify_mobile_evidence(
        self,
        *,
        target_account_ref: str,
        draft_media_id: str,
        profile_sha256: str,
        host_trace_sha256: str,
    ) -> bool: ...

    def authorize_publication(
        self, challenge: CurrentSessionPublicationChallenge
    ) -> CurrentSessionPublicationAuthorization: ...


@dataclass(frozen=True)
class HTTPResponse:
    status: int
    headers: dict[str, str]
    body: bytes


Transport = Callable[
    [str, str, Mapping[str, str], Optional[bytes], float], HTTPResponse
]


def _default_transport(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: bytes | None,
    timeout: float,
) -> HTTPResponse:
    request = urllib.request.Request(
        url, data=body, headers=dict(headers), method=method
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
            context=ssl.create_default_context(),
        ) as response:
            return HTTPResponse(
                int(response.status),
                {str(key).lower(): str(value) for key, value in response.headers.items()},
                response.read(),
            )
    except urllib.error.HTTPError as exc:
        return HTTPResponse(
            int(exc.code),
            {str(key).lower(): str(value) for key, value in exc.headers.items()},
            exc.read(),
        )


class WeChatAPIProvider:
    """Small official-API client with injectable HTTP for deterministic tests."""

    def __init__(
        self,
        *,
        access_token: str,
        app_id: str,
        transport: Transport | None = None,
        base_url: str = API_BASE,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_safe_retries: int = 3,
        sleeper: Callable[[float], None] = time.sleep,
        random_source: random.Random | None = None,
    ) -> None:
        if not access_token or any(ord(char) < 33 for char in access_token):
            raise ValueError("access_token must be a non-empty opaque secret")
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,128}", app_id):
            raise ValueError("app_id is invalid")
        self._access_token = access_token
        self.app_id = app_id
        self.transport = transport or _default_transport
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_safe_retries = max_safe_retries
        self.sleeper = sleeper
        self.random = random_source or random.Random()

    @property
    def account_ref(self) -> str:
        return f"appid:{self.app_id}"

    def _url(self, endpoint: str, **query: str) -> str:
        values = {"access_token": self._access_token, **query}
        return f"{self.base_url}{endpoint}?{urllib.parse.urlencode(values)}"

    @staticmethod
    def _decode(response: HTTPResponse, label: str) -> dict[str, Any]:
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise WeChatAPIError(
                f"{label} returned non-JSON HTTP {response.status}"
            ) from exc
        if not isinstance(payload, dict):
            raise WeChatAPIError(f"{label} returned a non-object JSON response")
        errcode = payload.get("errcode")
        if response.status < 200 or response.status >= 300 or errcode not in SUCCESS_ERRCODES:
            raise WeChatAPIError(
                f"{label} failed: HTTP {response.status}, errcode={errcode}, "
                f"errmsg={payload.get('errmsg')}",
                errcode=errcode if isinstance(errcode, int) else None,
            )
        return payload

    def _request_json(
        self,
        method: str,
        endpoint: str,
        *,
        payload: Mapping[str, Any] | None = None,
        safe_retry: bool,
        label: str,
        query: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        body = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            if payload is not None
            else None
        )
        headers = {"Content-Type": "application/json; charset=utf-8"}
        attempts = self.max_safe_retries + 1 if safe_retry else 1
        for attempt in range(attempts):
            try:
                response = self.transport(
                    method,
                    self._url(endpoint, **dict(query or {})),
                    headers,
                    body,
                    self.timeout,
                )
                try:
                    return self._decode(response, label)
                except WeChatAPIError as exc:
                    # An unsafe request may have committed even when a proxy
                    # returns 5xx, truncated/non-JSON bytes, or WeChat reports
                    # a transient server/rate-limit code.  Treat those states
                    # as unknown and require reconciliation; never replay.
                    if not safe_retry and (
                        response.status < 200
                        or response.status >= 300
                        or exc.errcode in TRANSIENT_ERRCODES
                        or "non-JSON" in str(exc)
                    ):
                        raise AmbiguousMutation(
                            f"{label} response was ambiguous; reconcile before retry"
                        ) from exc
                    raise
            except WeChatAPIError as exc:
                retryable = exc.errcode in TRANSIENT_ERRCODES
                if not safe_retry or not retryable or attempt + 1 >= attempts:
                    raise
            except (OSError, TimeoutError) as exc:
                if not safe_retry:
                    raise AmbiguousMutation(
                        f"{label} transport ended ambiguously; reconcile before retry"
                    ) from exc
                if attempt + 1 >= attempts:
                    raise WeChatAPIError(f"{label} transport failed after retries") from exc
            delay = min(8.0, 0.5 * (2**attempt)) + self.random.random() * 0.25
            self.sleeper(delay)
        raise AssertionError("retry loop exhausted")

    @staticmethod
    def _multipart(path: Path, field: str = "media") -> tuple[bytes, str]:
        boundary = "----org-wechat-" + uuid.uuid4().hex
        content_type = MIME_BY_SUFFIX.get(path.suffix.lower()) or mimetypes.guess_type(
            path.name
        )[0]
        if content_type is None:
            raise ValueError(f"cannot determine MIME type for {path.name}")
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field}"; filename="{path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
        body = header + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        return body, f"multipart/form-data; boundary={boundary}"

    def _upload(
        self,
        endpoint: str,
        path: Path,
        *,
        label: str,
        query: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        body, content_type = self._multipart(path)
        try:
            response = self.transport(
                "POST",
                self._url(endpoint, **dict(query or {})),
                {"Content-Type": content_type},
                body,
                self.timeout,
            )
        except (OSError, TimeoutError) as exc:
            raise AmbiguousMutation(
                f"{label} transport ended ambiguously; reconcile before retry"
            ) from exc
        try:
            return self._decode(response, label)
        except WeChatAPIError as exc:
            if (
                response.status < 200
                or response.status >= 300
                or exc.errcode in TRANSIENT_ERRCODES
                or "non-JSON" in str(exc)
            ):
                raise AmbiguousMutation(
                    f"{label} response was ambiguous; reconcile before retry"
                ) from exc
            raise

    def account_preflight(self, target_account_ref: str) -> dict[str, Any]:
        if target_account_ref != self.account_ref:
            raise ValueError(
                f"target account must exactly equal the configured appid reference {self.account_ref}"
            )
        draft_count = self._request_json(
            "GET",
            "/cgi-bin/draft/count",
            safe_retry=True,
            label="draft/count preflight",
        )
        material_count = self._request_json(
            "GET",
            "/cgi-bin/material/get_materialcount",
            safe_retry=True,
            label="get_materialcount preflight",
        )
        draft_read = isinstance(draft_count.get("total_count"), int)
        material_read = all(
            isinstance(material_count.get(field), int)
            for field in (
                "voice_count",
                "video_count",
                "image_count",
                "news_count",
            )
        )
        if not draft_read or not material_read:
            raise WeChatAPIError(
                "account preflight responses did not prove draft/count and "
                "material/get_materialcount access"
            )
        return {
            "status": "passed",
            "target_account_ref": target_account_ref,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "credential_binding": _canonical_sha256(
                {"app_id": self.app_id, "target_account_ref": target_account_ref}
            ),
            "capabilities": {
                "draft_read": draft_read,
                "material_read": material_read,
                "uploadimg": "proven-only-by-upload-transaction",
                "material_write": "proven-only-by-upload-transaction",
                "draft_write": "proven-only-by-draft-transaction",
                "freepublish": "proven-only-by-submit-and-status-readback",
            },
        }

    def uploadimg(self, path: Path) -> dict[str, Any]:
        result = self._upload("/cgi-bin/media/uploadimg", path, label="uploadimg")
        if not _is_wechat_cdn_url(result.get("url")):
            raise WeChatAPIError("uploadimg did not return an HTTPS mmbiz.qpic.cn URL")
        return result

    def add_material(self, path: Path, *, material_type: str = "image") -> dict[str, Any]:
        result = self._upload(
            "/cgi-bin/material/add_material",
            path,
            label="add_material",
            query={"type": material_type},
        )
        media_id = result.get("media_id")
        if not isinstance(media_id, str) or not 1 <= len(media_id) <= WECHAT_MEDIA_ID_MAX_CHARS:
            raise WeChatAPIError("add_material did not return a bounded permanent media_id")
        return result

    def draft_add(self, news: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/cgi-bin/draft/add",
            payload={"articles": news},
            safe_retry=False,
            label="draft/add",
        )

    def draft_update(self, media_id: str, article: dict[str, Any], index: int = 0) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/cgi-bin/draft/update",
            payload={"media_id": media_id, "index": index, "articles": article},
            safe_retry=True,
            label="draft/update",
        )

    def draft_get(self, media_id: str) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/cgi-bin/draft/get",
            payload={"media_id": media_id},
            safe_retry=True,
            label="draft/get",
        )

    def draft_get_with_receipt(
        self, media_id: str
    ) -> tuple[dict[str, Any], HTTPResponse, str]:
        endpoint = "/cgi-bin/draft/get"
        body = json.dumps(
            {"media_id": media_id}, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        request_id = uuid.uuid4().hex
        last_error: Exception | None = None
        for attempt in range(self.max_safe_retries + 1):
            try:
                response = self.transport(
                    "POST",
                    self._url(endpoint),
                    {
                        "Content-Type": "application/json; charset=utf-8",
                        "X-Org-WeChat-Request-Id": request_id,
                    },
                    body,
                    self.timeout,
                )
                return self._decode(response, "draft/get"), response, request_id
            except WeChatAPIError as exc:
                last_error = exc
                if exc.errcode not in TRANSIENT_ERRCODES or attempt >= self.max_safe_retries:
                    raise
            except (OSError, TimeoutError) as exc:
                last_error = exc
                if attempt >= self.max_safe_retries:
                    raise WeChatAPIError("draft/get transport failed after retries") from exc
            self.sleeper(min(8.0, 0.5 * (2**attempt)) + self.random.random() * 0.25)
        raise WeChatAPIError("draft/get failed") from last_error

    def freepublish_submit(self, media_id: str) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/cgi-bin/freepublish/submit",
            payload={"media_id": media_id},
            safe_retry=False,
            label="freepublish/submit",
        )

    def freepublish_get(self, publish_id: str) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/cgi-bin/freepublish/get",
            payload={"publish_id": publish_id},
            safe_retry=True,
            label="freepublish/get",
        )


class PublisherStore:
    """SQLite ledger for idempotency, crash recovery, and nonce replay defense."""

    def __init__(self, path: Path) -> None:
        self.path = _prepare_publisher_store_path(path)
        self.connection = sqlite3.connect(str(self.path), isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS operations (
              operation_key TEXT PRIMARY KEY,
              kind TEXT NOT NULL,
              state TEXT NOT NULL CHECK(state IN ('pending','complete','ambiguous','failed')),
              request_sha256 TEXT NOT NULL,
              response_json TEXT,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS uploads (
              target_account_ref TEXT NOT NULL,
              source_sha256 TEXT NOT NULL,
              kind TEXT NOT NULL CHECK(kind IN ('body','cover')),
              state TEXT NOT NULL CHECK(state IN ('pending','complete','ambiguous','failed')),
              result_json TEXT,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(target_account_ref, source_sha256, kind)
            );
            CREATE TABLE IF NOT EXISTS drafts (
              target_account_ref TEXT NOT NULL,
              article_revision TEXT NOT NULL,
              media_id TEXT NOT NULL,
              payload_sha256 TEXT NOT NULL,
              state TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(target_account_ref, article_revision)
            );
            CREATE TABLE IF NOT EXISTS publication_jobs (
              target_account_ref TEXT NOT NULL,
              article_revision TEXT NOT NULL,
              draft_media_id TEXT NOT NULL,
              draft_payload_sha256 TEXT NOT NULL,
              compile_report_sha256 TEXT NOT NULL,
              publish_id TEXT,
              state TEXT NOT NULL,
              status_code INTEGER,
              result_json TEXT,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(target_account_ref, article_revision)
            );
            CREATE TABLE IF NOT EXISTS nonce_ledger (
              source TEXT NOT NULL,
              nonce TEXT NOT NULL,
              consumed_at TEXT NOT NULL,
              expires_at TEXT NOT NULL,
              PRIMARY KEY(source, nonce)
            );
            CREATE TABLE IF NOT EXISTS account_preflights (
              target_account_ref TEXT PRIMARY KEY,
              report_sha256 TEXT NOT NULL,
              report_json TEXT NOT NULL,
              checked_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS account_preflight_events (
              target_account_ref TEXT NOT NULL,
              report_sha256 TEXT NOT NULL,
              report_json TEXT NOT NULL,
              checked_at TEXT NOT NULL,
              PRIMARY KEY(target_account_ref, report_sha256)
            );
            CREATE TABLE IF NOT EXISTS readback_captures (
              target_account_ref TEXT NOT NULL,
              article_revision TEXT NOT NULL,
              draft_media_id TEXT NOT NULL,
              draft_payload_sha256 TEXT NOT NULL,
              readback_sha256 TEXT NOT NULL,
              raw_response_sha256 TEXT NOT NULL,
              raw_content_sha256 TEXT NOT NULL,
              captured_at TEXT NOT NULL,
              PRIMARY KEY(target_account_ref, article_revision, draft_media_id,
                          draft_payload_sha256)
            );
            CREATE TABLE IF NOT EXISTS publisher_store_metadata (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            """
        )
        self.connection.execute(
            "INSERT OR IGNORE INTO publisher_store_metadata(key,value) VALUES('store_identity',?)",
            (uuid.uuid4().hex,),
        )
        store_identity_row = self.connection.execute(
            "SELECT value FROM publisher_store_metadata WHERE key='store_identity'"
        ).fetchone()
        if (
            store_identity_row is None
            or not isinstance(store_identity_row["value"], str)
            or not re.fullmatch(r"[0-9a-f]{32}", store_identity_row["value"])
        ):
            raise ValueError("publisher store identity is unavailable or invalid")
        self.identity = str(store_identity_row["value"])
        # Existing stores predate immutable publication bindings.  Upgrade in
        # place, but old rows remain unusable until the new values are filled
        # by a fresh submit.
        publication_columns = {
            row[1]
            for row in self.connection.execute("PRAGMA table_info(publication_jobs)")
        }
        if "draft_payload_sha256" not in publication_columns:
            self.connection.execute(
                "ALTER TABLE publication_jobs ADD COLUMN draft_payload_sha256 TEXT"
            )
        if "compile_report_sha256" not in publication_columns:
            self.connection.execute(
                "ALTER TABLE publication_jobs ADD COLUMN compile_report_sha256 TEXT"
            )

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield self.connection
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def begin_operation(self, key: str, kind: str, request: Any) -> dict[str, Any] | None:
        request_sha = _canonical_sha256(request)
        with self.transaction() as database:
            row = database.execute(
                "SELECT * FROM operations WHERE operation_key=?", (key,)
            ).fetchone()
            if row is not None:
                if row["request_sha256"] != request_sha or row["kind"] != kind:
                    raise ValueError("idempotency key was reused for different bytes")
                if row["state"] == "complete":
                    return json.loads(row["response_json"])
                if row["state"] in {"pending", "ambiguous"}:
                    raise AmbiguousMutation(
                        f"operation {key} is {row['state']}; reconcile before retry"
                    )
            database.execute(
                "INSERT OR REPLACE INTO operations(operation_key,kind,state,request_sha256,response_json,updated_at) "
                "VALUES(?,?,?,?,NULL,?)",
                (key, kind, "pending", request_sha, self._now()),
            )
        return None

    def finish_operation(self, key: str, response: Mapping[str, Any]) -> None:
        with self.transaction() as database:
            database.execute(
                "UPDATE operations SET state='complete',response_json=?,updated_at=? WHERE operation_key=? AND state='pending'",
                (json.dumps(response, ensure_ascii=False), self._now(), key),
            )
            if database.execute("SELECT changes()").fetchone()[0] != 1:
                raise RuntimeError("operation completion lost its pending claim")

    def mark_operation(self, key: str, state: str) -> None:
        if state not in {"ambiguous", "failed"}:
            raise ValueError("invalid terminal operation state")
        self.connection.execute(
            "UPDATE operations SET state=?,updated_at=? WHERE operation_key=?",
            (state, self._now(), key),
        )

    def claim_upload(
        self, account: str, source_sha: str, kind: str
    ) -> dict[str, Any] | None:
        """Atomically return committed cache or claim the one upload slot."""

        with self.transaction() as database:
            row = database.execute(
                "SELECT state,result_json FROM uploads WHERE target_account_ref=? "
                "AND source_sha256=? AND kind=?",
                (account, source_sha, kind),
            ).fetchone()
            if row is not None:
                if row["state"] == "complete":
                    return json.loads(row["result_json"])
                if row["state"] in {"pending", "ambiguous"}:
                    raise AmbiguousMutation(
                        f"{kind} upload for {source_sha} is {row['state']}; "
                        "reconcile before retry"
                    )
                database.execute(
                    "UPDATE uploads SET state='pending',result_json=NULL,updated_at=? "
                    "WHERE target_account_ref=? AND source_sha256=? AND kind=? "
                    "AND state='failed'",
                    (self._now(), account, source_sha, kind),
                )
            else:
                database.execute(
                    "INSERT INTO uploads(target_account_ref,source_sha256,kind,state,result_json,updated_at) "
                    "VALUES(?,?,?,'pending',NULL,?)",
                    (account, source_sha, kind, self._now()),
                )
        return None

    def record_account_preflight(
        self, target_account_ref: str, report: Mapping[str, Any]
    ) -> None:
        with self.transaction() as database:
            database.execute(
                "INSERT OR IGNORE INTO account_preflight_events"
                "(target_account_ref,report_sha256,report_json,checked_at) "
                "VALUES(?,?,?,?)",
                (
                    target_account_ref,
                    _canonical_sha256(report),
                    json.dumps(report, ensure_ascii=False),
                    str(report.get("checked_at")),
                ),
            )

    def verify_account_preflight(
        self, target_account_ref: str, report: Mapping[str, Any]
    ) -> None:
        row = self.connection.execute(
            "SELECT report_sha256 FROM account_preflight_events "
            "WHERE target_account_ref=? AND report_sha256=?",
            (target_account_ref, _canonical_sha256(report)),
        ).fetchone()
        if row is None or row["report_sha256"] != _canonical_sha256(report):
            raise ValueError("upload map lacks its committed account preflight transaction")

    def finish_upload(
        self, account: str, source_sha: str, kind: str, result: Mapping[str, Any]
    ) -> None:
        with self.transaction() as database:
            database.execute(
                "UPDATE uploads SET state='complete',result_json=?,updated_at=? "
                "WHERE target_account_ref=? AND source_sha256=? AND kind=? AND state='pending'",
                (
                    json.dumps(result, ensure_ascii=False),
                    self._now(),
                    account,
                    source_sha,
                    kind,
                ),
            )
            if database.execute("SELECT changes()").fetchone()[0] != 1:
                raise RuntimeError("upload completion lost its pending claim")

    def mark_upload_ambiguous(self, account: str, source_sha: str, kind: str) -> None:
        self.connection.execute(
            "UPDATE uploads SET state='ambiguous',updated_at=? "
            "WHERE target_account_ref=? AND source_sha256=? AND kind=?",
            (self._now(), account, source_sha, kind),
        )

    def consume_nonce(self, source: str, nonce: str, expires_at: datetime) -> None:
        with self.transaction() as database:
            try:
                database.execute(
                    "INSERT INTO nonce_ledger(source,nonce,consumed_at,expires_at) VALUES(?,?,?,?)",
                    (source, nonce, self._now(), expires_at.isoformat()),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("confirmation/receipt nonce has already been consumed") from exc


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not readable JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _detected_mime(path: Path) -> str | None:
    header = path.read_bytes()[:12]
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header.startswith(b"BM"):
        return "image/bmp"
    return None


class WeChatPublisher:
    def __init__(
        self,
        provider: WeChatAPIProvider,
        store: PublisherStore,
        *,
        current_session_authority: CurrentSessionHostAuthority | None = None,
        current_session_mobile_authority: CurrentSessionMobileAuthority | None = None,
        allow_editor_review: bool = False,
    ) -> None:
        # The object API carries credentials and can mutate drafts/publication
        # state, so importing this module must not bypass the isolated runner.
        # A trusted embedding harness may inject its non-cryptographic policy
        # hook only after the same locked-runtime guard has succeeded. This is
        # not portable evidence and is unavailable in the standalone CLI.
        from secure_runtime import require_secure_runtime

        require_secure_runtime("scripts/wechat_publisher.py")
        self.provider = provider
        self.store = store
        self.current_session_authority = current_session_authority
        self.current_session_mobile_authority = current_session_mobile_authority
        self.allow_editor_review = allow_editor_review

    def _require_provider_account(self, target_account_ref: str) -> None:
        provider_account_ref = getattr(self.provider, "account_ref", None)
        if (
            not isinstance(provider_account_ref, str)
            or provider_account_ref != target_account_ref
        ):
            raise ValueError(
                "target account does not match the active WeChat credential"
            )

    def preflight_account(
        self,
        *,
        target_account_ref: str,
        output_path: Path,
    ) -> dict[str, Any]:
        """Run a read-only account probe and persist a zero-mutation report."""

        self._require_provider_account(target_account_ref)
        output = _prepare_capture_output_file(
            output_path, label="WeChat account preflight report"
        )
        preflight = self.provider.account_preflight(target_account_ref)
        self.store.record_account_preflight(target_account_ref, preflight)
        payload = {
            "schema_version": 1,
            "kind": "wechat-account-readonly-preflight-v1",
            "status": "passed",
            "target_account_ref": target_account_ref,
            "checked_at": preflight.get("checked_at"),
            "account_preflight": preflight,
            "provider_calls": ["draft/count", "material/get_materialcount"],
            "mutations_attempted": 0,
            "capability_boundary": {
                "draft_read": "proved-by-draft-count",
                "material_read": "proved-by-material-count",
                "upload": "not-proved",
                "draft_write": "not-proved",
                "ui_readback": "separate-current-session-browser-probe-required",
                "publication": "not-proved",
            },
        }
        _create_once_json(output, payload)
        return {
            **payload,
            "report_path": str(output),
            "report_sha256": _file_digest(output),
        }

    def _upload_once(
        self,
        *,
        account: str,
        source_sha: str,
        kind: str,
        path: Path,
    ) -> dict[str, Any]:
        cached = self.store.claim_upload(account, source_sha, kind)
        if cached is not None:
            return cached
        try:
            raw = (
                self.provider.uploadimg(path)
                if kind == "body"
                else self.provider.add_material(path, material_type="image")
            )
        except AmbiguousMutation:
            self.store.mark_upload_ambiguous(account, source_sha, kind)
            raise
        except Exception:
            self.store.connection.execute(
                "UPDATE uploads SET state='failed',updated_at=? WHERE target_account_ref=? AND source_sha256=? AND kind=?",
                (self.store._now(), account, source_sha, kind),
            )
            raise
        result = {
            "url": raw.get("url"),
            "media_id": raw.get("media_id"),
            "response_sha256": _canonical_sha256(raw),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        self.store.finish_upload(account, source_sha, kind, result)
        return result

    def _verify_upload_map_store(
        self,
        upload_map: Mapping[str, Any],
        *,
        target_account_ref: str,
    ) -> None:
        """Bind model-readable upload JSON back to durable API transactions."""

        preflight = upload_map.get("account_preflight")
        if not isinstance(preflight, dict):
            raise ValueError("upload map account preflight is invalid")
        self.store.verify_account_preflight(target_account_ref, preflight)

        for item in upload_map.get("body_assets", []):
            if not isinstance(item, dict):
                raise ValueError("upload map body record is invalid")
            row = self.store.connection.execute(
                "SELECT state,result_json FROM uploads WHERE target_account_ref=? "
                "AND source_sha256=? AND kind='body'",
                (target_account_ref, item.get("source_sha256")),
            ).fetchone()
            result = (
                json.loads(row["result_json"])
                if row is not None
                and row["state"] == "complete"
                and isinstance(row["result_json"], str)
                else None
            )
            if (
                not isinstance(result, dict)
                or result.get("url") != item.get("hosted_url")
                or result.get("response_sha256") != item.get("response_sha256")
                or result.get("uploaded_at") != item.get("uploaded_at")
            ):
                raise ValueError(
                    f"body upload {item.get('asset_id')} has no matching committed API transaction"
                )
        cover = upload_map.get("cover")
        if not isinstance(cover, dict):
            raise ValueError("upload map cover record is invalid")
        row = self.store.connection.execute(
            "SELECT state,result_json FROM uploads WHERE target_account_ref=? "
            "AND source_sha256=? AND kind='cover'",
            (target_account_ref, cover.get("source_sha256")),
        ).fetchone()
        result = (
            json.loads(row["result_json"])
            if row is not None
            and row["state"] == "complete"
            and isinstance(row["result_json"], str)
            else None
        )
        if (
            not isinstance(result, dict)
            or result.get("media_id") != cover.get("media_id")
            or result.get("response_sha256") != cover.get("response_sha256")
            or result.get("uploaded_at") != cover.get("uploaded_at")
        ):
            raise ValueError("cover has no matching committed permanent-material transaction")

    def prepare_uploads(
        self,
        handoff_path: Path,
        *,
        target_account_ref: str,
        output_path: Path,
    ) -> dict[str, Any]:
        self._require_provider_account(target_account_ref)
        # Resolve the final destination and reject collisions/symlink traversal
        # before making even the first credentialed provider call.  The
        # append-only sidecar is opened only after all local handoff checks pass.
        output_path, journal_path = _prepare_create_once_output(output_path)
        handoff_path = handoff_path.resolve()
        handoff = _read_json(handoff_path, "handoff")
        export = handoff.get("transport_fidelity", {}).get("export")
        if not isinstance(export, dict):
            raise ValueError("handoff lacks transport_fidelity.export")
        if export.get("revision_hash") != canonical_transport_revision_hash(export):
            raise ValueError("handoff transport revision hash is stale")
        structural = validate_transport_fidelity_diagnostic(handoff_path)
        if structural.get("ok") is not True:
            raise ValueError(
                "handoff failed upload dry-run: "
                + "; ".join(
                    str(item.get("message"))
                    for item in structural.get("errors", [])
                    if isinstance(item, dict)
                )
            )
        attribution = validate_workflow_attribution_handoff(handoff_path)
        if attribution.get("ok") is not True:
            raise ValueError(
                "handoff failed attribution dry-run: "
                + "; ".join(str(error) for error in attribution.get("errors", []))
            )

        # Resolve and validate the complete census before the first mutation.
        # A bad late asset or cover must never leave a partial upload batch.
        body_census: list[tuple[str, Path, int, str, str]] = []
        for asset_id, asset in sorted(_export_delivery_assets(export).items()):
            source = resolve_local_asset(handoff_path, asset.get("path"))
            if source is None:
                raise ValueError(f"body asset {asset_id} is unavailable")
            size = source.stat().st_size
            mime = _detected_mime(source)
            suffix_mime = MIME_BY_SUFFIX.get(source.suffix.lower())
            if (
                size >= WECHAT_BODY_IMAGE_MAX_BYTES
                or mime not in {"image/png", "image/jpeg"}
                or suffix_mime != mime
            ):
                raise ValueError(
                    f"body asset {asset_id} must be matching PNG/JPEG bytes and strictly smaller than 1 MB"
                )
            source_sha = str(asset.get("sha256"))
            if source_sha != _file_digest(source):
                raise ValueError(f"body asset {asset_id} differs from its frozen SHA")
            body_census.append((asset_id, source, size, mime, source_sha))
        cover_asset = _handoff_cover_asset(handoff)
        if cover_asset is None:
            raise ValueError("handoff article has no role=cover asset")
        cover_path = resolve_local_asset(handoff_path, cover_asset.get("path"))
        if cover_path is None:
            raise ValueError("cover asset is unavailable")
        cover_size = cover_path.stat().st_size
        cover_mime = _detected_mime(cover_path)
        cover_suffix_mime = MIME_BY_SUFFIX.get(cover_path.suffix.lower())
        if (
            cover_size > WECHAT_COVER_IMAGE_MAX_BYTES
            or cover_mime not in {"image/bmp", "image/png", "image/jpeg", "image/gif"}
            or cover_suffix_mime != cover_mime
        ):
            raise ValueError(
                "permanent cover must be matching BMP/PNG/JPEG/GIF bytes and at most 10 MB"
            )
        cover_sha = str(cover_asset.get("sha256"))
        if cover_sha != _file_digest(cover_path):
            raise ValueError("cover asset differs from its frozen SHA")

        journal = UploadTransactionJournal(
            journal_path,
            {
                "target_account_ref": target_account_ref,
                "handoff_path": str(handoff_path),
                "handoff_sha256": _file_digest(handoff_path),
                "transport_revision_hash": export.get("revision_hash"),
                "output_path": str(output_path),
                "publisher_store_path": str(self.store.path),
                "publisher_store_identity": self.store.identity,
            },
        )
        journal.verify_committed_uploads(self.store)
        # A concurrent workflow that populated the final map while local
        # validation ran must still stop before any provider mutation.
        if os.path.lexists(output_path):
            raise ValueError(
                f"upload map output already exists; refusing overwrite: {output_path}"
            )
        try:
            preflight = self.provider.account_preflight(target_account_ref)
        except Exception as exc:
            journal.append("account-preflight-failed", {"error_type": type(exc).__name__})
            raise
        self.store.record_account_preflight(target_account_ref, preflight)
        journal.append(
            "account-preflight-committed",
            {
                "report_sha256": _canonical_sha256(preflight),
                "checked_at": preflight.get("checked_at"),
            },
        )

        def committed_upload(
            *, asset_id: str, kind: str, source: Path, source_sha: str
        ) -> dict[str, Any]:
            identity = {
                "asset_id": asset_id,
                "kind": kind,
                "source_sha256": source_sha,
            }
            journal.append("upload-attempt", identity)
            try:
                result = self._upload_once(
                    account=target_account_ref,
                    source_sha=source_sha,
                    kind=kind,
                    path=source,
                )
            except AmbiguousMutation:
                journal.append("upload-ambiguous", identity)
                raise
            except Exception as exc:
                journal.append(
                    "upload-failed",
                    {**identity, "error_type": type(exc).__name__},
                )
                raise
            journal.append(
                "upload-committed",
                {
                    **identity,
                    "response_sha256": result.get("response_sha256"),
                    "uploaded_at": result.get("uploaded_at"),
                    "hosted_url": result.get("url"),
                    "media_id": result.get("media_id"),
                },
            )
            return result

        body_records: list[dict[str, Any]] = []
        for asset_id, source, size, mime, source_sha in body_census:
            uploaded = committed_upload(
                asset_id=asset_id,
                kind="body",
                source=source,
                source_sha=source_sha,
            )
            body_records.append(
                {
                    "asset_id": asset_id,
                    "source_sha256": source_sha,
                    "source_byte_length": size,
                    "source_content_type": mime,
                    "hosted_url": uploaded["url"],
                    "uploaded_at": uploaded["uploaded_at"],
                    "response_sha256": uploaded["response_sha256"],
                    "status": "uploaded",
                }
            )
        cover_uploaded = committed_upload(
            asset_id=str(cover_asset.get("id")),
            kind="cover",
            source=cover_path,
            source_sha=cover_sha,
        )
        payload = {
            "schema_version": 1,
            "source": UPLOAD_MAP_SOURCE,
            "target_account_ref": target_account_ref,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "handoff_sha256": _file_digest(handoff_path),
            "transport_revision_hash": export.get("revision_hash"),
            "account_preflight": preflight,
            "body_assets": body_records,
            "cover": {
                "asset_id": cover_asset.get("id"),
                "source_sha256": cover_sha,
                "source_byte_length": cover_size,
                "source_content_type": cover_mime,
                "media_id": cover_uploaded["media_id"],
                "hosted_url": cover_uploaded.get("url"),
                "uploaded_at": cover_uploaded["uploaded_at"],
                "response_sha256": cover_uploaded["response_sha256"],
                "status": "uploaded",
            },
        }
        try:
            _create_once_json(output_path, payload)
            validate_wechat_upload_map(
                output_path,
                manifest_path=handoff_path,
                handoff=handoff,
                export=export,
                expected_target_account_ref=target_account_ref,
            )
        except Exception as exc:
            try:
                journal.append(
                    "final-map-failed",
                    {"error_type": type(exc).__name__},
                )
            except Exception:
                # The durable SQLite upload ledger still remains authoritative
                # if the filesystem itself can no longer append the sidecar.
                pass
            raise
        journal.append(
            "final-map-committed",
            {
                "output_sha256": _file_digest(output_path),
                "body_asset_ids": [item[0] for item in body_census],
                "cover_asset_id": cover_asset.get("id"),
            },
        )
        return payload

    def _article_payload(
        self,
        handoff: dict[str, Any],
        handoff_path: Path,
        compile_report: dict[str, Any],
        report_path: Path,
    ) -> tuple[dict[str, Any], str, Path]:
        if compile_report.get("schema_version") != 2:
            raise ValueError("compile report schema_version is unsupported")
        if compile_report.get("ok") is not True:
            raise ValueError("compile report is not successful")
        if compile_report.get("handoff_sha256") != _file_digest(handoff_path.resolve()):
            raise ValueError("compile report is not bound to these exact handoff bytes")
        if compile_report.get("source") != "ardot-current-root-layer-export-v1":
            raise ValueError("compile report is not an Ardot delivery transport report")
        scope = compile_report.get("assurance_scope")
        if scope not in {
            "current-session-draft",
            "current-session-interaction-probe",
            "portable-signed-draft-candidate",
        }:
            raise ValueError("authoring preview and diagnostic candidates cannot be saved as drafts")
        selected_payload = compile_report.get("selected_payload")
        if selected_payload not in {"dynamic", "static"}:
            raise ValueError("compile report did not select one transport payload")
        postflight = compile_report.get("postflight")
        if (
            not isinstance(postflight, dict)
            or postflight.get("ok") is not True
            or postflight.get("contract_ok") is not True
            or postflight.get("selected_payload") != selected_payload
            or not isinstance(postflight.get("selected"), dict)
            or postflight["selected"].get("ok") is not True
        ):
            raise ValueError("compile report lacks successful dual-payload postflight")
        if scope == "portable-signed-draft-candidate":
            if compile_report.get("draft_write_eligible") is not True:
                raise ValueError("portable compile is not draft-write eligible")
        else:
            compiled_at = _parse_time(compile_report.get("compiled_at"), "compiled_at")
            if (
                (datetime.now(timezone.utc) - compiled_at).total_seconds() > 3600
                or compile_report.get("portable_audit_verified") is not False
                or compile_report.get("preflight", {}).get(
                    "session_live_root_structural_match"
                )
                is not True
                or not isinstance(
                    compile_report.get("artifact_binding", {}).get(
                        "live_root_export"
                    ),
                    dict,
                )
            ):
                raise ValueError("current-session compile lacks a fresh exact live-root binding")
        article = handoff.get("article")
        upload_binding = compile_report.get("upload_map_binding")
        bindings = compile_report.get("artifact_binding", {})
        binding = bindings.get("wechat_html") or bindings.get("candidate_html")
        if not isinstance(article, dict) or not isinstance(upload_binding, dict) or not isinstance(binding, dict):
            raise ValueError("compile report lacks article/upload/artifact bindings")
        upload_map_path = Path(str(upload_binding.get("path", "")))
        if (
            not upload_map_path.is_absolute()
            or upload_map_path.is_symlink()
            or not upload_map_path.is_file()
            or _file_digest(upload_map_path) != upload_binding.get("sha256")
        ):
            raise ValueError("compile report upload map binding is unavailable or changed")
        export = handoff.get("transport_fidelity", {}).get("export")
        if not isinstance(export, dict):
            raise ValueError("handoff lacks transport_fidelity.export")
        validated_upload_map = validate_wechat_upload_map(
            upload_map_path,
            manifest_path=handoff_path.resolve(),
            handoff=handoff,
            export=export,
            expected_target_account_ref=str(upload_binding.get("target_account_ref")),
        )
        if validated_upload_map.get("cover", {}).get("media_id") != upload_binding.get(
            "cover_media_id"
        ):
            raise ValueError("compile report cover media_id differs from the upload transaction")
        html_path = (report_path.resolve().parent / str(binding.get("path", ""))).resolve()
        html_path.relative_to(report_path.resolve().parent)
        if not html_path.is_file() or html_path.is_symlink():
            raise ValueError("bound final HTML is unavailable")
        if _file_digest(html_path) != binding.get("sha256"):
            raise ValueError("bound final HTML bytes changed after compile")
        live_root_binding = bindings.get("live_root_export")
        if not isinstance(live_root_binding, dict):
            raise ValueError("compile report lacks its exact live-root binding")
        live_root_path = Path(str(live_root_binding.get("path", "")))
        receipt_binding = bindings.get("live_root_receipt")
        live_receipt_path = (
            Path(str(receipt_binding.get("path", "")))
            if isinstance(receipt_binding, dict)
            else None
        )
        structural = _validate_transport_fidelity_contract(
            handoff_path,
            html_path=html_path,
            live_root_path=live_root_path,
            live_receipt_path=live_receipt_path,
            require_live_root=True,
            compile_report_path=report_path,
            require_compile_report=True,
            upload_map_path=upload_map_path,
            require_upload_map=True,
            diagnostic=scope
            in {"current-session-draft", "current-session-interaction-probe"},
        )
        if structural.get("ok") is not True:
            raise ValueError(
                "bound compile/live-root/payload chain no longer validates: "
                + "; ".join(
                    str(item.get("message"))
                    for item in structural.get("errors", [])
                    if isinstance(item, dict)
                )
            )

        if selected_payload == "dynamic" and scope != "current-session-interaction-probe":
            evidence = compile_report.get("interaction_evidence_binding")
            required_evidence_fields = {
                "mobile_profile",
                "interaction_readback",
                "current_session_live_authority_used",
                "editor_review_accepted",
            }
            if not isinstance(evidence, dict) or set(evidence) != required_evidence_fields:
                raise ValueError("dynamic compile lacks exact interaction evidence bindings")

            def evidence_path(value: Any, label: str) -> Path:
                if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
                    raise ValueError(f"dynamic {label} binding is incomplete")
                candidate = Path(str(value.get("path", "")))
                if (
                    not candidate.is_absolute()
                    or candidate.is_symlink()
                    or not candidate.is_file()
                    or _file_digest(candidate) != value.get("sha256")
                ):
                    raise ValueError(f"dynamic {label} evidence changed or is unavailable")
                return candidate.resolve()

            profile_path = evidence_path(evidence.get("mobile_profile"), "mobile profile")
            interaction_readback_path = evidence_path(
                evidence.get("interaction_readback"), "interaction readback"
            )
            profile = _read_json(profile_path, "mobile profile")
            dynamic_output = compile_report.get("outputs", {}).get("dynamic")
            dynamic_path = (report_path.resolve().parent / str(dynamic_output or "")).resolve()
            if dynamic_path != html_path:
                if not dynamic_path.is_file() or _file_digest(dynamic_path) != binding.get("sha256"):
                    raise ValueError("selected dynamic payload differs from the bound artifact")
            mobile_ok, mobile_errors, mobile_scope = _validate_mobile_profile(
                profile,
                str(upload_binding.get("target_account_ref")),
                profile_path=profile_path,
                candidate_html=html_path.read_text(encoding="utf-8"),
                readback_html=interaction_readback_path.read_text(encoding="utf-8"),
                current_session_authority=self.current_session_mobile_authority,
                allow_editor_review=(scope == "current-session-draft" and self.allow_editor_review and evidence.get("editor_review_accepted") is True),
            )
            expected_mobile_scope = (
                ("current-session-editor-reviewed" if evidence.get("editor_review_accepted") is True else "current-session-live")
                if scope == "current-session-draft"
                else "portable-signed"
            )
            if not mobile_ok or mobile_scope != expected_mobile_scope:
                raise ValueError(
                    "dynamic mobile/readback evidence is invalid: "
                    + "; ".join(mobile_errors)
                )
        content = html_path.read_text(encoding="utf-8")
        title = article.get("title")
        author = article.get("author", "")
        digest = article.get("digest", "")
        if not isinstance(title, str) or not 1 <= len(title) <= WECHAT_TITLE_MAX_CHARS:
            raise ValueError("title exceeds official draft/add limit")
        if not isinstance(author, str) or len(author) > WECHAT_AUTHOR_MAX_CHARS:
            raise ValueError("author exceeds official draft/add limit")
        if not isinstance(digest, str) or len(digest) > WECHAT_DIGEST_MAX_CHARS:
            raise ValueError("digest exceeds official draft/add limit")
        if len(content) >= WECHAT_CONTENT_MAX_CHARS or len(content.encode("utf-8")) >= WECHAT_CONTENT_MAX_BYTES:
            raise ValueError("content exceeds official draft/add limit")
        if re.search(r"<script\b|\bon[a-z]+\s*=|javascript\s*:", content, re.I):
            raise ValueError("content contains JavaScript that WeChat will remove")
        thumb_media_id = upload_binding.get("cover_media_id")
        if not isinstance(thumb_media_id, str) or not 1 <= len(thumb_media_id) <= WECHAT_MEDIA_ID_MAX_CHARS:
            raise ValueError("final compile lacks a permanent thumb_media_id")
        payload = {
            "title": title,
            "author": author,
            "digest": digest,
            "content": content,
            "thumb_media_id": thumb_media_id,
            "need_open_comment": int(bool(article.get("need_open_comment", False))),
            "only_fans_can_comment": int(bool(article.get("only_fans_can_comment", False))),
        }
        return payload, _canonical_sha256(payload), html_path

    def save_draft(
        self,
        handoff_path: Path,
        compile_report_path: Path,
        *,
        target_account_ref: str,
    ) -> dict[str, Any]:
        self._require_provider_account(target_account_ref)
        handoff = _read_json(handoff_path, "handoff")
        report = _read_json(compile_report_path, "compile report")
        if report.get("upload_map_binding", {}).get("target_account_ref") != target_account_ref:
            raise ValueError("compile report target account differs from active preflight")
        upload_map_path = Path(str(report["upload_map_binding"].get("path", "")))
        upload_map = _read_json(upload_map_path, "upload map")
        self._verify_upload_map_store(
            upload_map, target_account_ref=target_account_ref
        )
        article, payload_sha, _ = self._article_payload(
            handoff, handoff_path, report, compile_report_path
        )
        revision = str(report.get("revision_hash"))
        publication = self.store.connection.execute(
            "SELECT publish_id,state FROM publication_jobs "
            "WHERE target_account_ref=? AND article_revision=?",
            (target_account_ref, revision),
        ).fetchone()
        if publication is not None and publication["publish_id"]:
            raise ValueError(
                "a publication job already owns this revision; the draft is immutable"
            )
        row = self.store.connection.execute(
            "SELECT media_id,payload_sha256 FROM drafts WHERE target_account_ref=? AND article_revision=?",
            (target_account_ref, revision),
        ).fetchone()
        if row is not None:
            media_id = str(row["media_id"])
            repair_binding = str(row["payload_sha256"])
            if (
                report.get("selected_payload") == "dynamic"
                and report.get("assurance_scope")
                != "current-session-interaction-probe"
            ):
                profile_binding = report.get("interaction_evidence_binding", {}).get(
                    "mobile_profile"
                )
                profile_path = Path(str(profile_binding.get("path", "")))
                profile = _read_json(profile_path, "mobile profile")
                if profile.get("draft_id") != media_id:
                    raise ValueError("dynamic mobile profile belongs to a different draft")
            if row["payload_sha256"] == payload_sha:
                # A local mapping is not proof that the remote draft still
                # exists or still contains these bytes.  Reopen it before
                # reporting success; mismatches are repaired with one exact
                # idempotent update to the same media ID.
                remote, _, _ = self.provider.draft_get_with_receipt(media_id)
                items = remote.get("news_item")
                remote_article = (
                    items[0]
                    if isinstance(items, list)
                    and len(items) == 1
                    and isinstance(items[0], dict)
                    else None
                )
                if isinstance(remote_article, dict) and all(
                    remote_article.get(field, "") == article.get(field, "")
                    for field in (
                        "title",
                        "author",
                        "digest",
                        "content",
                        "thumb_media_id",
                    )
                ):
                    return {
                        "state": "draft-saved",
                        "created": False,
                        "media_id": media_id,
                        "payload_sha256": payload_sha,
                        "published": False,
                    }
                repair_binding = _canonical_sha256(remote_article)
            key = (
                f"draft-update:{target_account_ref}:{revision}:{payload_sha}:"
                f"{repair_binding}"
            )
            cached = self.store.begin_operation(key, "draft-update", article)
            if cached is None:
                try:
                    result = self.provider.draft_update(media_id, article)
                except AmbiguousMutation:
                    self.store.mark_operation(key, "ambiguous")
                    raise
                except Exception:
                    self.store.mark_operation(key, "failed")
                    raise
                self.store.finish_operation(key, result)
            self.store.connection.execute(
                "UPDATE drafts SET payload_sha256=?,state='saved',updated_at=? "
                "WHERE target_account_ref=? AND article_revision=?",
                (payload_sha, self.store._now(), target_account_ref, revision),
            )
            return {
                "state": "draft-saved",
                "created": False,
                "media_id": media_id,
                "payload_sha256": payload_sha,
                "published": False,
            }
        if report.get("assurance_scope") == "current-session-interaction-probe":
            raise ValueError(
                "interaction probe may only update an existing saved draft; it can never create one"
            )
        if report.get("selected_payload") == "dynamic":
            raise ValueError(
                "dynamic payload requires an existing saved draft bound to its mobile readback"
            )
        key = f"draft-add:{target_account_ref}:{revision}:{payload_sha}"
        cached = self.store.begin_operation(key, "draft-add", [article])
        try:
            result = cached or self.provider.draft_add([article])
        except AmbiguousMutation:
            self.store.mark_operation(key, "ambiguous")
            raise
        except Exception:
            self.store.mark_operation(key, "failed")
            raise
        if cached is None:
            self.store.finish_operation(key, result)
        media_id = result.get("media_id")
        if not isinstance(media_id, str) or not 1 <= len(media_id) <= WECHAT_MEDIA_ID_MAX_CHARS:
            raise WeChatAPIError("draft/add did not return a bounded media_id")
        self.store.connection.execute(
            "INSERT INTO drafts(target_account_ref,article_revision,media_id,payload_sha256,state,updated_at) "
            "VALUES(?,?,?,?,?,?)",
            (
                target_account_ref,
                revision,
                media_id,
                payload_sha,
                "saved",
                self.store._now(),
            ),
        )
        return {
            "state": "draft-saved",
            "created": True,
            "media_id": media_id,
            "payload_sha256": payload_sha,
            "published": False,
        }

    def capture_raw_draft(
        self,
        media_id: str,
        *,
        target_account_ref: str,
        output_path: Path,
    ) -> dict[str, Any]:
        # Validate the entire lexical destination and its existing parent
        # before touching the credentialed provider or account binding.
        output_path = _prepare_capture_output_file(
            output_path, label="raw draft capture output"
        )
        self._require_provider_account(target_account_ref)
        mapped = self.store.connection.execute(
            "SELECT 1 FROM drafts WHERE target_account_ref=? AND media_id=? AND state='saved'",
            (target_account_ref, media_id),
        ).fetchone()
        if mapped is None:
            raise ValueError("raw draft capture requires this store's exact saved draft")
        observed_at = datetime.now(timezone.utc).isoformat()
        raw, response, request_id = self.provider.draft_get_with_receipt(media_id)
        payload = {
            "schema_version": 1,
            "source": "wechat-api-draft-get-raw-v1",
            "target_account_ref": target_account_ref,
            "draft_id": media_id,
            "request": {
                "endpoint": "/cgi-bin/draft/get",
                "method": "POST",
                "request_id": request_id,
            },
            "observed_at": observed_at,
            "http_status": response.status,
            "response_headers": response.headers,
            "response": raw,
            "response_sha256": _canonical_sha256(raw),
        }
        write_text_create_once(
            output_path,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            label="raw draft capture output",
        )
        return payload

    def _download_image(
        self,
        url: str,
        *,
        output_path: Path,
        observed_at: str,
    ) -> dict[str, Any]:
        if not _is_wechat_cdn_url(url):
            raise ValueError(f"readback image is not a WeChat CDN URL: {url}")
        response = self.provider.transport(
            "GET", url, {"Accept": "image/*"}, None, self.provider.timeout
        )
        if response.status != 200:
            raise WeChatAPIError(f"image readback failed with HTTP {response.status}")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if not content_type.startswith("image/"):
            raise WeChatAPIError("image readback response is not an image")
        write_bytes_create_once(
            output_path,
            response.body,
            label="WeChat CDN readback",
        )
        return {
            "request_url": url,
            "http_status": response.status,
            "response_headers": response.headers,
            "response_headers_sha256": _canonical_sha256(response.headers),
            "observed_at": observed_at,
            "path": output_path.name,
            "sha256": _file_digest(output_path),
            "byte_length": output_path.stat().st_size,
            "content_type": content_type,
        }

    def capture_readback(
        self,
        handoff_path: Path,
        compile_report_path: Path,
        *,
        media_id: str,
        target_account_ref: str,
        output_dir: Path,
        screenshot_manifest_path: Path | None,
        capture_bundle_path: Path | None = None,
        viewport_review_path: Path | None = None,
    ) -> dict[str, Any]:
        """Capture API bytes, CDN downloads, chapter screenshots, and census."""

        # This is intentionally the first operation. A direct symlink, any
        # symlinked ancestor, a missing parent, an existing destination, or a
        # destination inside the installed runtime must fail before any
        # provider/account/draft_get interaction.
        output_dir = _prepare_capture_output_directory(
            output_dir, label="readback output directory"
        )
        self._require_provider_account(target_account_ref)
        handoff = _read_json(handoff_path, "handoff")
        report = _read_json(compile_report_path, "compile report")
        article_payload, draft_payload_sha, compiled_html_path = self._article_payload(
            handoff, handoff_path, report, compile_report_path
        )
        if report.get("upload_map_binding", {}).get("target_account_ref") != target_account_ref:
            raise ValueError("readback target account differs from final compile")
        mapped = self.store.connection.execute(
            "SELECT 1 FROM drafts WHERE target_account_ref=? AND article_revision=? "
            "AND media_id=? AND state='saved'",
            (target_account_ref, str(report.get("revision_hash")), media_id),
        ).fetchone()
        if mapped is None:
            raise ValueError("readback requires this store's exact saved draft")

        export = handoff["transport_fidelity"]["export"]
        current_session_capture = report.get("assurance_scope") in {
            "current-session-draft",
            "current-session-interaction-probe",
        }
        capture_bundle: dict[str, Any] | None = None
        capture_bundle_resolved: Path | None = None
        capture_nonce: str | None = None
        if current_session_capture:
            if screenshot_manifest_path is not None:
                raise ValueError(
                    "current-session capture cannot accept the portable screenshot manifest"
                )
            if capture_bundle_path is not None and self.current_session_authority is not None:
                raise ValueError(
                    "select exactly one current-session capture source: ingestion bundle or in-process callback"
                )
            if capture_bundle_path is not None:
                from ingest_wechat_readback_capture import (
                    CAPTURE_NONCE_SOURCE,
                    validate_current_session_bundle,
                )

                capture_bundle_resolved = capture_bundle_path.resolve(strict=False)
                capture_bundle = validate_current_session_bundle(
                    capture_bundle_path,
                    handoff_path=handoff_path,
                    compile_report_path=compile_report_path,
                    target_account_ref=target_account_ref,
                    draft_id=media_id,
                    article_revision=str(report.get("revision_hash")),
                )
                capture_nonce = str(capture_bundle.get("nonce"))
                nonce_expiry = _parse_time(
                    capture_bundle.get("created_at"),
                    "current-session capture bundle created_at",
                ) + timedelta(minutes=10)
                try:
                    # Consume before any draft/CDN provider activity.  The
                    # ledger is store-wide, so copying one bundle to another
                    # output directory cannot replay its observation nonce.
                    self.store.consume_nonce(
                        CAPTURE_NONCE_SOURCE,
                        capture_nonce,
                        nonce_expiry,
                    )
                except ValueError as exc:
                    raise ValueError(
                        "current-session readback capture nonce has already been consumed"
                    ) from exc
            elif self.current_session_authority is None:
                raise ValueError(
                    "current-session readback requires a verified Browser/Computer Use "
                    "ingestion bundle or an active in-process host capture callback"
                )
        else:
            if capture_bundle_path is not None:
                raise ValueError(
                    "current-session capture bundle cannot masquerade as portable evidence"
                )
            if screenshot_manifest_path is None:
                raise ValueError("portable capture requires its host screenshot manifest")

        # Reserve the final directory with mkdir(2), never mkdir parents. Every
        # child is then installed O_EXCL/create-once.
        _create_capture_directory(output_dir, label="readback output directory")

        if capture_bundle is not None:
            raw_binding = capture_bundle["raw_draft"]
            raw_source_path = Path(str(raw_binding["path"]))
            raw_wrapper = _read_json(raw_source_path, "raw draft capture")
            raw_response = raw_wrapper["response"]
            http_response = HTTPResponse(
                int(raw_wrapper["http_status"]),
                dict(raw_wrapper["response_headers"]),
                b"",
            )
            request_id = str(raw_wrapper["request"]["request_id"])
            observed_at = str(raw_wrapper["observed_at"])
        else:
            observed_at = datetime.now(timezone.utc).isoformat()
            raw_response, http_response, request_id = self.provider.draft_get_with_receipt(
                media_id
            )
            raw_wrapper = {
                "schema_version": 1,
                "source": "wechat-api-draft-get-raw-v1",
                "target_account_ref": target_account_ref,
                "draft_id": media_id,
                "request": {
                    "endpoint": "/cgi-bin/draft/get",
                    "method": "POST",
                    "request_id": request_id,
                },
                "observed_at": observed_at,
                "http_status": http_response.status,
                "response_headers": http_response.headers,
                "response": raw_response,
                "response_sha256": _canonical_sha256(raw_response),
            }
        news_items = raw_response.get("news_item")
        if not isinstance(news_items, list) or len(news_items) != 1 or not isinstance(news_items[0], dict):
            raise ValueError("draft/get must return exactly one article")
        saved_article = news_items[0]
        content = saved_article.get("content")
        if not isinstance(content, str):
            raise ValueError("draft/get article has no content HTML")
        raw_path = output_dir / "raw-draft-response.json"
        content_path = output_dir / "raw-draft-content.html"
        raw_encoded = (
            raw_source_path.read_bytes()
            if capture_bundle is not None
            else (
                json.dumps(
                    raw_wrapper,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8")
        )
        write_bytes_create_once(
            raw_path,
            raw_encoded,
            label="raw readback response",
        )
        write_bytes_create_once(
            content_path,
            content.encode("utf-8"),
            label="raw readback content",
        )

        upload_map_path = Path(str(report.get("upload_map_binding", {}).get("path")))
        upload_map = validate_wechat_upload_map(
            upload_map_path,
            manifest_path=handoff_path,
            handoff=handoff,
            export=handoff["transport_fidelity"]["export"],
            expected_target_account_ref=target_account_ref,
        )
        body_by_id = upload_map["_body_by_id"]
        parser = _TransportHTML()
        parser.feed(content)
        parser.close()
        if parser.payload_variant not in {"dynamic", "static"}:
            raise ValueError("saved draft content lacks a transport payload variant")

        host_screenshot_records: Mapping[str, HostScreenshotCapture] | None = None
        screenshot_records: dict[str, dict[str, Any]] = {}
        if current_session_capture:
            if capture_bundle is not None:
                assert capture_bundle_resolved is not None
                screenshot_records = {
                    str(item.get("chapter_id")): item
                    for item in capture_bundle.get("chapters", [])
                    if isinstance(item, dict)
                    and isinstance(item.get("chapter_id"), str)
                }
            else:
                assert self.current_session_authority is not None
                host_screenshot_records = self.current_session_authority.capture_wechat_chapters(
                    target_account_ref=target_account_ref,
                    draft_media_id=media_id,
                    article_revision=str(report.get("revision_hash")),
                    chapter_ids=tuple(
                        str(chapter.get("chapter_id")) for chapter in export["chapters"]
                    ),
                )
        else:
            assert screenshot_manifest_path is not None
            screenshot_manifest = _read_json(
                screenshot_manifest_path, "chapter screenshot manifest"
            )
            if (
                screenshot_manifest.get("schema_version") != 1
                or screenshot_manifest.get("source")
                != "wechat-host-chapter-screenshots-v1"
                or screenshot_manifest.get("target_account_ref") != target_account_ref
                or screenshot_manifest.get("draft_id") != media_id
            ):
                raise ValueError("chapter screenshots are not bound to this account/draft")
            screenshot_records = {
                str(item.get("chapter_id")): item
                for item in screenshot_manifest.get("chapters", [])
                if isinstance(item, dict) and isinstance(item.get("chapter_id"), str)
            }

        downloaded_cache: dict[str, tuple[dict[str, Any], Path]] = {}

        def download_asset(asset_id: str) -> tuple[dict[str, Any], Path]:
            cached = downloaded_cache.get(asset_id)
            if cached is not None:
                return cached
            mapped = body_by_id.get(asset_id)
            if not isinstance(mapped, dict):
                raise ValueError(f"saved body asset {asset_id} is not in upload map")
            source = resolve_local_asset(
                handoff_path,
                next(
                    (
                        value["path"]
                        for value in _export_delivery_assets(
                            handoff["transport_fidelity"]["export"]
                        ).values()
                        if value.get("asset_id") == asset_id
                    ),
                    None,
                ),
            )
            if source is None:
                raise ValueError(f"frozen source for {asset_id} is unavailable")
            destination = output_dir / f"download-{re.sub(r'[^A-Za-z0-9._-]+', '-', asset_id)}{source.suffix.lower()}"
            receipt = self._download_image(
                str(mapped["hosted_url"]),
                output_path=destination,
                observed_at=observed_at,
            )
            similarity = _visual_similarity(source, destination)
            record = {
                "asset_id": asset_id,
                "source_sha256": _file_digest(source),
                "url": mapped["hosted_url"],
                "download": receipt,
                "visual_similarity": round(similarity, 6),
            }
            downloaded_cache[asset_id] = (record, destination)
            return record, destination

        chapter_records: list[dict[str, Any]] = []
        chapter_screenshot_digests: set[str] = set()
        for chapter in export["chapters"]:
            asset_ids = [chapter["background_layer"]["asset_id"]]
            asset_ids.extend(item["asset_id"] for item in chapter["decorations"])
            asset_ids.extend(item["asset_id"] for item in chapter["photos"])
            interactions = chapter.get("interaction")
            interaction_items = interactions if isinstance(interactions, list) else [interactions]
            if parser.payload_variant == "static":
                asset_ids.extend(
                    item["fallback_asset"]["asset_id"]
                    for item in interaction_items
                    if isinstance(item, dict)
                    and item.get("mode") in {"svg", "horizontal-swipe"}
                )
            for item in interaction_items:
                if not isinstance(item, dict) or parser.payload_variant != "dynamic":
                    continue
                source = item.get("svg") if item.get("mode") == "svg" else item.get("swipe")
                if isinstance(source, dict):
                    asset_ids.extend(
                        nested["asset_id"]
                        for nested in source.get("assets", [])
                        if isinstance(nested, dict) and nested.get("asset_id")
                    )
            hosted_records = [download_asset(asset_id)[0] for asset_id in dict.fromkeys(asset_ids)]
            screenshot = screenshot_records.get(chapter["chapter_id"])
            host_capture = (
                host_screenshot_records.get(chapter["chapter_id"])
                if host_screenshot_records is not None
                else None
            )
            screenshot_capture_source = "portable-host-manifest"
            if current_session_capture and capture_bundle is not None:
                if not isinstance(screenshot, dict):
                    raise ValueError(
                        f"missing ingested screenshot for chapter {chapter['chapter_id']}"
                    )
                screenshot_captured_at = screenshot.get("captured_at")
                screenshot_event_id = screenshot.get("capture_event_id")
                if (
                    not isinstance(screenshot_event_id, str)
                    or not re.fullmatch(r"[A-Za-z0-9._:/-]{2,256}", screenshot_event_id)
                ):
                    raise ValueError("ingested screenshot capture event ID is invalid")
                assert capture_bundle_resolved is not None
                source_screenshot = (
                    capture_bundle_resolved.parent
                    / str(screenshot.get("path", ""))
                )
                if (
                    source_screenshot.is_symlink()
                    or not source_screenshot.resolve().is_file()
                    or _file_digest(source_screenshot.resolve())
                    != screenshot.get("sha256")
                    or source_screenshot.resolve().stat().st_size
                    != screenshot.get("byte_length")
                ):
                    raise ValueError(
                        "ingested chapter screenshot bytes changed after bundle validation"
                    )
                screenshot_capture_source = "active-host-callback"
            elif current_session_capture:
                if not isinstance(host_capture, HostScreenshotCapture):
                    raise ValueError(
                        f"active host did not capture chapter {chapter['chapter_id']}"
                    )
                screenshot_captured_at = host_capture.captured_at
                screenshot_event_id = host_capture.capture_event_id
                if not re.fullmatch(r"[A-Za-z0-9._:-]{8,256}", screenshot_event_id):
                    raise ValueError("host screenshot capture event ID is invalid")
                screenshot_capture_source = "active-host-callback"
            else:
                if not isinstance(screenshot, dict):
                    raise ValueError(f"missing screenshot for chapter {chapter['chapter_id']}")
                screenshot_captured_at = screenshot.get("captured_at")
                screenshot_event_id = screenshot.get("capture_event_id")
                if not isinstance(screenshot_event_id, str) or not screenshot_event_id:
                    raise ValueError("portable screenshot manifest lacks a host capture event ID")
                assert screenshot_manifest_path is not None
                source_screenshot = Path(str(screenshot.get("path", "")))
                if not source_screenshot.is_absolute():
                    source_screenshot = screenshot_manifest_path.resolve().parent / source_screenshot
                if source_screenshot.is_symlink() or not source_screenshot.resolve().is_file():
                    raise ValueError("chapter screenshot is unavailable or a symlink")
            reference = resolve_local_asset(
                handoff_path, chapter["reference_screenshot"]["path"]
            )
            if reference is None:
                raise ValueError("Ardot reference screenshot is unavailable")
            screenshot_destination = output_dir / f"screenshot-{chapter['chapter_id']}.png"
            if current_session_capture and capture_bundle is not None:
                write_bytes_create_once(
                    screenshot_destination,
                    source_screenshot.resolve().read_bytes(),
                    label=f"chapter {chapter['chapter_id']} readback screenshot",
                )
            elif current_session_capture:
                assert isinstance(host_capture, HostScreenshotCapture)
                write_bytes_create_once(
                    screenshot_destination,
                    host_capture.png_bytes,
                    label=f"chapter {chapter['chapter_id']} readback screenshot",
                )
            else:
                if source_screenshot.resolve().samefile(reference):
                    raise ValueError("Ardot reference cannot masquerade as WeChat screenshot")
                write_bytes_create_once(
                    screenshot_destination,
                    source_screenshot.resolve().read_bytes(),
                    label=f"chapter {chapter['chapter_id']} readback screenshot",
                )
            screenshot_digest = _file_digest(screenshot_destination)
            chapter_screenshot_digests.add(screenshot_digest)
            from render_quality import compare_screenshots
            if not compare_screenshots(reference, screenshot_destination)["ok"]:
                raise ValueError("WeChat screenshot has a local visual regression")
            screenshot_similarity = _visual_similarity(reference, screenshot_destination)
            interaction_records = []
            for item in interaction_items:
                if not isinstance(item, dict):
                    continue
                mode = str(item.get("mode"))
                signature = str(item.get("structure_sha256"))
                if parser.payload_variant == "static" and mode in {"svg", "horizontal-swipe"}:
                    mode = "static-fallback"
                    signature = str(item.get("fallback_semantic_sha256"))
                interaction_records.append(
                    {
                        "interaction_id": item.get("interaction_id"),
                        "mode": mode,
                        "signature_sha256": signature,
                    }
                )
            chapter_records.append(
                {
                    "chapter_id": chapter["chapter_id"],
                    "section_node_id": chapter["section_node_id"],
                    "visible_text_node_ids": [
                        node["node_id"] for node in chapter["visible_text_nodes"]
                    ],
                    "visible_text_sha256": text_sha256(
                        " ".join(node["text"] for node in chapter["visible_text_nodes"])
                    ),
                    "asset_ids": sorted(set(asset_ids)),
                    "hosted_assets": hosted_records,
                    "screenshot": {
                        "path": screenshot_destination.name,
                        "sha256": screenshot_digest,
                        "byte_length": screenshot_destination.stat().st_size,
                        "width_px": 390,
                        "height_px": round(float(chapter["geometry"]["height"])),
                        "captured_at": screenshot_captured_at,
                        "capture_source": screenshot_capture_source,
                        "capture_event_id": screenshot_event_id,
                        "reference_asset_id": chapter["reference_screenshot"]["asset_id"],
                        "visual_similarity": round(screenshot_similarity, 6),
                    },
                    "interactions": interaction_records,
                }
            )

        cover_url = saved_article.get("thumb_url")
        if not _is_wechat_cdn_url(cover_url):
            raise ValueError("draft/get did not return a WeChat cover derivative URL")
        cover_source = _handoff_cover_asset(handoff)
        cover_source_path = resolve_local_asset(handoff_path, cover_source.get("path")) if isinstance(cover_source, dict) else None
        if cover_source_path is None:
            raise ValueError("cover source is unavailable")
        cover_destination = output_dir / f"download-cover{cover_source_path.suffix.lower()}"
        cover_download = self._download_image(
            str(cover_url), output_path=cover_destination, observed_at=observed_at
        )

        eligible_ids = [
            asset.get("id")
            for asset in handoff.get("assets", [])
            if isinstance(asset, dict)
            and (
                asset.get("watermark_required") is True
                or (
                    isinstance(asset.get("watermark"), dict)
                    and asset["watermark"].get("required") is True
                )
            )
        ]
        verified_ids: list[str] = []
        for asset_id in eligible_ids:
            _, downloaded = download_asset(str(asset_id))
            try:
                from provenance_watermark import detect_watermark

                detection = detect_watermark(downloaded)
            except (ImportError, OSError, ValueError) as exc:
                raise ValueError(
                    f"eligible watermark carrier {asset_id} cannot be authenticated: {exc}"
                ) from exc
            if not isinstance(detection, dict) or detection.get("authenticated") is not True or detection.get("input_sha256") != file_sha256(downloaded):
                raise ValueError(f"eligible watermark carrier {asset_id} did not authenticate after CDN download")
            verified_ids.append(str(asset_id))
        census = {
            "schema_version": 1,
            "source": "watermark-transport-carrier-census-v1",
            "eligible_carrier_ids": sorted(str(value) for value in eligible_ids),
            "transport_verified_carrier_ids": sorted(verified_ids),
        }
        census_path = output_dir / "watermark-carrier-census.json"
        write_text_create_once(
            census_path,
            json.dumps(census, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            label="watermark carrier census",
        )
        readback = {
            "schema_version": 2,
            "source": "wechat-saved-draft-readback-v2",
            "target_account_ref": target_account_ref,
            "draft_id": media_id,
            "title": saved_article.get("title"),
            "digest": saved_article.get("digest", ""),
            "cover_asset_id": handoff.get("article", {}).get("cover_asset_id"),
            "thumb_media_id": saved_article.get("thumb_media_id"),
            "cover_hosted_derivative": cover_download,
            "transport_revision_hash": export.get("revision_hash"),
            "observed_at": observed_at,
            "raw_draft": {
                "source": "wechat-api-draft-get-raw-v1",
                "path": raw_path.name,
                "sha256": _file_digest(raw_path),
                "byte_length": raw_path.stat().st_size,
                "provider": "wechat-official-api",
                "request_id": request_id,
                "request_url": "/cgi-bin/draft/get",
                "request_method": "POST",
                "http_status": http_response.status,
                "response_headers": http_response.headers,
                "response_headers_sha256": _canonical_sha256(http_response.headers),
                "observed_at": observed_at,
                "content_path": content_path.name,
                "content_sha256": _file_digest(content_path),
                "content_byte_length": content_path.stat().st_size,
            },
            "watermark_transport": {
                "status": "not-applicable" if not eligible_ids else "verified",
                "census_path": census_path.name,
                "census_sha256": _file_digest(census_path),
                "census_byte_length": census_path.stat().st_size,
            },
            "chapters": chapter_records,
        }
        if viewport_review_path is not None:
            from render_quality import validate_viewport_review
            viewport_review = _read_json(viewport_review_path, "viewport review")
            viewport_errors = validate_viewport_review(viewport_review, base=viewport_review_path.resolve().parent,
                export=export, content_sha256=_file_digest(content_path), account=target_account_ref, draft=media_id)
            if viewport_errors:
                raise ValueError("; ".join(viewport_errors))
            for sample in viewport_review["samples"]:
                source = viewport_review_path.resolve().parent / sample["screenshot"]["path"]
                destination = output_dir / f"viewport-{sample['width_px']}.png"
                write_bytes_create_once(destination, source.read_bytes(), label="viewport screenshot")
                if _file_digest(destination) != sample["screenshot"]["sha256"]:
                    raise ValueError("viewport screenshot changed during freezing")
                sample["screenshot"]["path"] = destination.name
            readback["viewport_review"] = viewport_review
        readback_path = output_dir / "readback.json"
        write_text_create_once(
            readback_path,
            json.dumps(readback, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            label="saved draft readback",
        )
        scope_path: Path | None = None
        if current_session_capture:
            scope_path = output_dir / "readback-scope.json"
            scope = {
                "schema_version": 1,
                "source": "wechat-current-session-readback-scope-v1",
                "assurance_scope": "current-session-readback-nonportable",
                "target_account_ref": target_account_ref,
                "draft_id": media_id,
                "article_revision": str(report.get("revision_hash")),
                "readback_sha256": _file_digest(readback_path),
                "capture_route": (
                    "browser-computer-use-create-once-ingestion"
                    if capture_bundle is not None
                    else "trusted-in-process-capture-callback"
                ),
                "capture_bundle_sha256": (
                    _file_digest(capture_bundle_resolved)
                    if capture_bundle_resolved is not None
                    else None
                ),
                "host_attested": False,
                "portable": False,
                "publication_authority": False,
            }
            write_text_create_once(
                scope_path,
                json.dumps(scope, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                label="current-session readback scope",
            )
        draft_row = self.store.connection.execute(
            "SELECT media_id,payload_sha256 FROM drafts WHERE target_account_ref=? "
            "AND article_revision=?",
            (target_account_ref, str(report.get("revision_hash"))),
        ).fetchone()
        if (
            draft_row is None
            or draft_row["media_id"] != media_id
            or draft_row["payload_sha256"] != draft_payload_sha
        ):
            raise ValueError("captured readback is not bound to this store's saved draft")
        with self.store.transaction() as database:
            database.execute(
                "INSERT OR REPLACE INTO readback_captures"
                "(target_account_ref,article_revision,draft_media_id,draft_payload_sha256,"
                "readback_sha256,raw_response_sha256,raw_content_sha256,captured_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (
                    target_account_ref,
                    str(report.get("revision_hash")),
                    media_id,
                    draft_payload_sha,
                    _file_digest(readback_path),
                    _file_digest(raw_path),
                    _file_digest(content_path),
                    observed_at,
                ),
            )
        return {
            "state": "readback-captured",
            "readback": str(readback_path),
            "readback_sha256": _file_digest(readback_path),
            "compiled_payload_sha256": _file_digest(compiled_html_path),
            "watermark_transport_status": readback["watermark_transport"]["status"],
            "assurance_scope": (
                "current-session-readback-nonportable"
                if current_session_capture
                else "portable-signed-readback-candidate"
            ),
            "scope": str(scope_path) if scope_path is not None else None,
            "host_attested": False if current_session_capture else None,
            "portable": False if current_session_capture else None,
            "publication_authority": False,
        }

    @staticmethod
    def validate_confirmation(
        confirmation: dict[str, Any],
        *,
        target_account_ref: str,
        article_revision: str,
        draft_media_id: str,
        compile_report_sha256: str,
        now: datetime | None = None,
    ) -> tuple[str, datetime]:
        required = {
            "schema_version",
            "source",
            "action",
            "target_account_ref",
            "article_revision",
            "draft_media_id",
            "compile_report_sha256",
            "nonce",
            "confirmed_at",
            "expires_at",
        }
        if set(confirmation) != required:
            raise ValueError("publication confirmation has missing or extra fields")
        if (
            confirmation.get("schema_version") != 1
            or confirmation.get("source") != CONFIRMATION_SOURCE
            or confirmation.get("action") != "freepublish"
            or confirmation.get("target_account_ref") != target_account_ref
            or confirmation.get("article_revision") != article_revision
            or confirmation.get("draft_media_id") != draft_media_id
            or confirmation.get("compile_report_sha256") != compile_report_sha256
        ):
            raise ValueError("publication confirmation is not bound to this exact draft/account/revision")
        nonce = confirmation.get("nonce")
        if not isinstance(nonce, str) or re.fullmatch(r"[0-9a-f]{32,64}", nonce) is None:
            raise ValueError("publication confirmation nonce is invalid")
        confirmed_at = _parse_time(confirmation.get("confirmed_at"), "confirmed_at")
        expires_at = _parse_time(confirmation.get("expires_at"), "expires_at")
        current = now or datetime.now(timezone.utc)
        if (
            confirmed_at > current + timedelta(seconds=30)
            or expires_at <= current
            or expires_at <= confirmed_at
            or (expires_at - confirmed_at).total_seconds()
            > CONFIRMATION_MAX_AGE_SECONDS
        ):
            raise ValueError("publication confirmation is stale, future-dated, or overlong")
        return nonce, expires_at

    def _poll_publication_status(
        self,
        *,
        target_account_ref: str,
        article_revision: str,
        publish_id: str,
        portable: bool,
        poll_attempts: int,
        sleeper: Callable[[float], None],
    ) -> dict[str, Any]:
        authority_assurance = (
            "portable-host-signed"
            if portable
            else "trusted-harness-policy-hook-not-independently-attested"
        )
        last: dict[str, Any] | None = None
        for attempt in range(max(1, poll_attempts)):
            last = self.provider.freepublish_get(publish_id)
            status = last.get("publish_status")
            stored_result = json.dumps(
                {
                    "api_response": last,
                    "portable_audit_verified": portable,
                    "publication_authority_assurance": authority_assurance,
                },
                ensure_ascii=False,
            )
            if status == 0:
                details = last.get("article_detail", {}).get("item")
                urls = [
                    item.get("article_url")
                    for item in details
                    if isinstance(item, dict)
                    and isinstance(item.get("article_url"), str)
                ] if isinstance(details, list) else []
                if not urls:
                    raise WeChatAPIError(
                        "publish_status=0 but no article_detail.item[].article_url was returned"
                    )
                self.store.connection.execute(
                    "UPDATE publication_jobs SET state='published',status_code=0,result_json=?,updated_at=? "
                    "WHERE target_account_ref=? AND article_revision=?",
                    (
                        stored_result,
                        self.store._now(),
                        target_account_ref,
                        article_revision,
                    ),
                )
                return {
                    "state": "published",
                    "publish_id": publish_id,
                    "article_urls": urls,
                    "portable_audit_verified": portable,
                    "publication_authority_assurance": authority_assurance,
                }
            if status in TERMINAL_FAILURE_STATUSES:
                state = PUBLISH_STATUS[int(status)]
                self.store.connection.execute(
                    "UPDATE publication_jobs SET state=?,status_code=?,result_json=?,updated_at=? "
                    "WHERE target_account_ref=? AND article_revision=?",
                    (
                        state,
                        status,
                        stored_result,
                        self.store._now(),
                        target_account_ref,
                        article_revision,
                    ),
                )
                return {
                    "state": state,
                    "publish_id": publish_id,
                    "article_urls": [],
                    "portable_audit_verified": portable,
                    "publication_authority_assurance": authority_assurance,
                }
            if status != 1:
                raise WeChatAPIError(f"unknown publish_status: {status}")
            if attempt + 1 < poll_attempts:
                sleeper(min(15.0, 1.0 * (2**attempt)))
        self.store.connection.execute(
            "UPDATE publication_jobs SET state='unknown',status_code=1,result_json=?,updated_at=? "
            "WHERE target_account_ref=? AND article_revision=?",
            (
                json.dumps(
                    {
                        "api_response": last or {},
                        "portable_audit_verified": portable,
                        "publication_authority_assurance": authority_assurance,
                    },
                    ensure_ascii=False,
                ),
                self.store._now(),
                target_account_ref,
                article_revision,
            ),
        )
        return {
            "state": "unknown",
            "publish_id": publish_id,
            "article_urls": [],
            "portable_audit_verified": portable,
            "publication_authority_assurance": authority_assurance,
        }

    def _resume_existing_publication(
        self,
        row: sqlite3.Row,
        *,
        target_account_ref: str,
        article_revision: str,
        poll_attempts: int,
        sleeper: Callable[[float], None],
    ) -> dict[str, Any]:
        publish_id = str(row["publish_id"])
        try:
            stored = json.loads(row["result_json"] or "{}")
        except json.JSONDecodeError:
            stored = {}
        portable = bool(stored.get("portable_audit_verified"))
        authority_assurance = (
            "portable-host-signed"
            if portable
            else "trusted-harness-policy-hook-not-independently-attested"
        )
        response = stored.get("api_response")
        if row["state"] == "published" and isinstance(response, dict):
            details = response.get("article_detail", {}).get("item")
            urls = [
                item.get("article_url")
                for item in details
                if isinstance(item, dict)
                and isinstance(item.get("article_url"), str)
            ] if isinstance(details, list) else []
            if urls:
                return {
                    "state": "published",
                    "publish_id": publish_id,
                    "article_urls": urls,
                    "portable_audit_verified": portable,
                    "publication_authority_assurance": authority_assurance,
                }
        if row["status_code"] in TERMINAL_FAILURE_STATUSES:
            return {
                "state": str(row["state"]),
                "publish_id": publish_id,
                "article_urls": [],
                "portable_audit_verified": portable,
                "publication_authority_assurance": authority_assurance,
            }
        return self._poll_publication_status(
            target_account_ref=target_account_ref,
            article_revision=article_revision,
            publish_id=publish_id,
            portable=portable,
            poll_attempts=poll_attempts,
            sleeper=sleeper,
        )

    def publish(
        self,
        *,
        target_account_ref: str,
        article_revision: str,
        compile_report_path: Path,
        confirmation_path: Path,
        publication_gate_path: Path,
        poll_attempts: int = 6,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> dict[str, Any]:
        self._require_provider_account(target_account_ref)
        report = _read_json(compile_report_path, "compile report")
        compile_report_sha = _file_digest(compile_report_path)
        gate = _read_json(publication_gate_path, "publication gate")
        draft = self.store.connection.execute(
            "SELECT * FROM drafts WHERE target_account_ref=? AND article_revision=?",
            (target_account_ref, article_revision),
        ).fetchone()
        if draft is None or draft["state"] != "saved":
            raise ValueError("no saved draft is bound to this account/revision")
        if report.get("revision_hash") != article_revision:
            raise ValueError("compile report revision differs from publish request")
        selected_payload = report.get("selected_payload")
        gate_fields = {
            "schema_version",
            "source",
            "assurance_scope",
            "target_account_ref",
            "article_revision",
            "draft_media_id",
            "handoff",
            "compile_report",
            "upload_map",
            "readback",
            "watermark_report",
            "live_root",
            "live_receipt",
            "readback_receipt",
            "mobile_profile",
        }
        if set(gate) != gate_fields:
            raise ValueError("publication gate has missing or self-asserted extra fields")
        assurance_scope = gate.get("assurance_scope")
        if (
            gate.get("schema_version") != 2
            or gate.get("source") != "wechat-publication-input-bindings-v2"
            or assurance_scope not in {"current-session-live", "portable-signed"}
            or gate.get("target_account_ref") != target_account_ref
            or gate.get("article_revision") != article_revision
            or gate.get("draft_media_id") != draft["media_id"]
        ):
            raise ValueError("publication bindings differ from this exact account/draft/revision")

        def bound_path(value: Any, label: str, *, optional: bool = False) -> Path | None:
            if value is None and optional:
                return None
            if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
                raise ValueError(f"{label} binding must contain only path and sha256")
            candidate = Path(str(value.get("path", "")))
            if (
                not candidate.is_absolute()
                or candidate.is_symlink()
                or not candidate.is_file()
                or _file_digest(candidate) != value.get("sha256")
            ):
                raise ValueError(f"{label} binding is unavailable, a symlink, or changed")
            return candidate.resolve()

        handoff_path = bound_path(gate.get("handoff"), "handoff")
        gate_compile_report = bound_path(gate.get("compile_report"), "compile report")
        upload_map_path = bound_path(gate.get("upload_map"), "upload map")
        readback_path = bound_path(gate.get("readback"), "readback")
        watermark_report_path = bound_path(
            gate.get("watermark_report"), "watermark report"
        )
        live_root_path = bound_path(gate.get("live_root"), "live root")
        live_receipt_path = bound_path(
            gate.get("live_receipt"), "live receipt", optional=True
        )
        readback_receipt_path = bound_path(
            gate.get("readback_receipt"), "readback receipt", optional=True
        )
        if gate_compile_report != compile_report_path.resolve():
            raise ValueError("publish command compile report differs from publication bindings")
        if assurance_scope == "current-session-live" and (
            live_receipt_path is not None or readback_receipt_path is not None
        ):
            raise ValueError("current-session gate must not claim portable receipt assurance")
        if assurance_scope == "portable-signed" and (
            live_receipt_path is None or readback_receipt_path is None
        ):
            raise ValueError("portable publication requires both authenticated receipts")
        assert (
            handoff_path
            and upload_map_path
            and readback_path
            and watermark_report_path
            and live_root_path
        )
        bound_upload_map = _read_json(upload_map_path, "upload map")
        self._verify_upload_map_store(
            bound_upload_map, target_account_ref=target_account_ref
        )

        artifact_binding = report.get("artifact_binding", {})
        html_binding = artifact_binding.get("wechat_html") or artifact_binding.get(
            "candidate_html"
        )
        if not isinstance(html_binding, dict):
            raise ValueError("compile report lacks its selected payload binding")
        html_path = (compile_report_path.resolve().parent / str(html_binding.get("path", ""))).resolve()
        if not html_path.is_file() or _file_digest(html_path) != html_binding.get("sha256"):
            raise ValueError("selected compiled payload changed after compilation")
        validation = _validate_transport_fidelity_contract(
            handoff_path,
            html_path=html_path,
            live_root_path=live_root_path,
            live_receipt_path=live_receipt_path,
            require_live_root=True,
            compile_report_path=compile_report_path,
            require_compile_report=True,
            readback_path=readback_path,
            readback_receipt_path=readback_receipt_path,
            require_readback=True,
            expected_target_account_ref=target_account_ref,
            upload_map_path=upload_map_path,
            require_upload_map=True,
            diagnostic=assurance_scope == "current-session-live",
        )
        portable = validation.get("portable_audit_verified") is True
        if assurance_scope == "portable-signed":
            if not portable:
                raise ValueError("portable signed publication audit did not validate")
        elif validation.get("current_session_publication_preflight_eligible") is not True:
            raise ValueError("current-session live readback/publication preflight did not validate")
        if validation.get("watermark_transport_status") not in {
            "verified",
            "not-applicable",
        }:
            raise ValueError("watermark census is incomplete for eligible carriers")

        readback = _read_json(readback_path, "readback")
        watermark_binding = readback.get("watermark_transport")
        if (
            not isinstance(watermark_binding, dict)
            or (readback_path.parent / str(watermark_binding.get("census_path", ""))).resolve()
            != watermark_report_path
            or watermark_binding.get("census_sha256")
            != _file_digest(watermark_report_path)
        ):
            raise ValueError("publication watermark report is not the exact readback census")
        raw_content_path = (
            readback_path.parent
            / str(readback.get("raw_draft", {}).get("content_path", ""))
        ).resolve()
        if selected_payload == "dynamic":
            mobile_binding = gate.get("mobile_profile")
            if not isinstance(mobile_binding, dict) or set(mobile_binding) != {"path", "sha256"}:
                raise ValueError("dynamic publication requires exact mobile evidence bindings")
            profile_path = Path(str(mobile_binding["path"]))
            compiled_mobile = report.get("interaction_evidence_binding")
            compiled_profile = compiled_mobile.get("mobile_profile") if isinstance(compiled_mobile, dict) else None
            if (
                not profile_path.is_absolute()
                or profile_path.is_symlink()
                or not profile_path.is_file()
                or _file_digest(profile_path) != mobile_binding.get("sha256")
                or not isinstance(compiled_profile, dict)
                or Path(str(compiled_profile.get("path", ""))).resolve()
                != profile_path.resolve()
                or compiled_profile.get("sha256") != mobile_binding.get("sha256")
            ):
                raise ValueError("mobile profile changed after compilation")
            profile = _read_json(profile_path, "mobile profile")
            if profile.get("draft_id") != str(draft["media_id"]):
                raise ValueError("mobile profile belongs to a different saved draft")
            dynamic_path = compile_report_path.resolve().parent / str(
                report.get("outputs", {}).get("dynamic", "")
            )
            mobile_ok, mobile_errors, mobile_scope = _validate_mobile_profile(
                profile,
                target_account_ref,
                profile_path=profile_path,
                candidate_html=dynamic_path.read_text(encoding="utf-8"),
                readback_html=raw_content_path.read_text(encoding="utf-8"),
                current_session_authority=self.current_session_mobile_authority,
            )
            if not mobile_ok or mobile_scope != assurance_scope:
                raise ValueError(
                    "mobile profile is not trusted for selected dynamic payload: "
                    + "; ".join(mobile_errors)
                )
        elif gate.get("mobile_profile") is not None:
            raise ValueError("static publication must not smuggle an unused mobile profile")

        # Re-read the same draft immediately before submit.  A handcrafted gate
        # or stale readback cannot authorize different current server bytes.
        live_draft, _, _ = self.provider.draft_get_with_receipt(str(draft["media_id"]))
        live_items = live_draft.get("news_item")
        if not isinstance(live_items, list) or len(live_items) != 1 or not isinstance(live_items[0], dict):
            raise ValueError("fresh draft/get did not return one article")
        handoff = _read_json(handoff_path, "handoff")
        expected_article, expected_payload_sha, _ = self._article_payload(
            handoff, handoff_path, report, compile_report_path
        )
        if draft["payload_sha256"] != expected_payload_sha:
            raise ValueError("publisher store draft payload differs from the compile report")
        live_article = live_items[0]
        for field in ("title", "author", "digest", "content", "thumb_media_id"):
            if live_article.get(field, "") != expected_article.get(field, ""):
                raise ValueError(f"fresh draft/get changed {field}; publish aborted")
        capture_row = self.store.connection.execute(
            "SELECT * FROM readback_captures WHERE target_account_ref=? "
            "AND article_revision=? AND draft_media_id=? AND draft_payload_sha256=?",
            (
                target_account_ref,
                article_revision,
                str(draft["media_id"]),
                expected_payload_sha,
            ),
        ).fetchone()
        raw_response_path = (
            readback_path.parent
            / str(readback.get("raw_draft", {}).get("path", ""))
        ).resolve()
        if (
            capture_row is None
            or capture_row["readback_sha256"] != _file_digest(readback_path)
            or capture_row["raw_content_sha256"] != _file_digest(raw_content_path)
            or not raw_response_path.is_file()
            or capture_row["raw_response_sha256"]
            != _file_digest(raw_response_path)
        ):
            raise ValueError(
                "readback was not captured by this publisher/provider transaction"
            )
        existing = self.store.connection.execute(
            "SELECT * FROM publication_jobs WHERE target_account_ref=? AND article_revision=?",
            (target_account_ref, article_revision),
        ).fetchone()
        if existing is not None and existing["publish_id"]:
            if (
                existing["draft_media_id"] != draft["media_id"]
                or existing["draft_payload_sha256"] != expected_payload_sha
                or existing["compile_report_sha256"] != compile_report_sha
            ):
                raise ValueError(
                    "existing publication job belongs to a different immutable payload/report"
                )
            # Status recovery is read-only, but only after the caller's exact
            # report/gate/draft chain has been recomputed above.
            return self._resume_existing_publication(
                existing,
                target_account_ref=target_account_ref,
                article_revision=article_revision,
                poll_attempts=poll_attempts,
                sleeper=sleeper,
            )
        confirmation = _read_json(confirmation_path, "publication confirmation")
        if assurance_scope == "current-session-live":
            nonce, expires_at = self.validate_confirmation(
                confirmation,
                target_account_ref=target_account_ref,
                article_revision=article_revision,
                draft_media_id=str(draft["media_id"]),
                compile_report_sha256=compile_report_sha,
            )
            confirmation_source = CONFIRMATION_SOURCE
            if self.current_session_authority is None:
                raise ValueError(
                    "standalone file-only current-session publication is forbidden; "
                    "an isolated trusted embedding harness must inject its "
                    "non-cryptographic policy hook, or use portable signed/UI publication"
                )
            authorization = self.current_session_authority.authorize_publication(
                CurrentSessionPublicationChallenge(
                    target_account_ref=target_account_ref,
                    article_revision=article_revision,
                    draft_media_id=str(draft["media_id"]),
                    draft_payload_sha256=expected_payload_sha,
                    compile_report_sha256=compile_report_sha,
                    live_root_path=live_root_path,
                    live_root_sha256=_file_digest(live_root_path),
                    readback_sha256=_file_digest(readback_path),
                    confirmation_nonce=nonce,
                )
            )
            try:
                authority_time = _parse_time(
                    authorization.confirmed_at, "host confirmation event"
                )
            except AttributeError as exc:
                raise ValueError("host authority returned an invalid authorization object") from exc
            if (
                not isinstance(authorization, CurrentSessionPublicationAuthorization)
                or authorization.target_account_ref != target_account_ref
                or authorization.article_revision != article_revision
                or authorization.draft_media_id != str(draft["media_id"])
                or authorization.draft_payload_sha256 != expected_payload_sha
                or authorization.compile_report_sha256 != compile_report_sha
                or authorization.readback_sha256 != _file_digest(readback_path)
                or authorization.ardot_live_root_sha256 != _file_digest(live_root_path)
                or authorization.confirmation_nonce != nonce
                or not authorization.host_session_id
                or not authorization.confirmation_event_id
                or abs((datetime.now(timezone.utc) - authority_time).total_seconds()) > 60
            ):
                raise ValueError(
                    "active host did not freshly re-observe Ardot/draft and consume this confirmation"
                )
        else:
            nonce, expires_at = verify_host_publication_confirmation_receipt(
                confirmation,
                target_account_ref=target_account_ref,
                article_revision=article_revision,
                draft_media_id=str(draft["media_id"]),
                draft_payload_sha256=expected_payload_sha,
                compile_report_sha256=compile_report_sha,
                readback_sha256=_file_digest(readback_path),
            )
            confirmation_source = PUBLICATION_CONFIRMATION_RECEIPT_SOURCE
        key = (
            f"freepublish-submit:{target_account_ref}:{article_revision}:"
            f"{expected_payload_sha}:{compile_report_sha}"
        )
        request = {"media_id": draft["media_id"]}
        operation = self.store.connection.execute(
            "SELECT * FROM operations WHERE operation_key=?", (key,)
        ).fetchone()
        cached: dict[str, Any] | None = None
        if operation is not None and operation["state"] == "complete":
            if (
                operation["kind"] != "freepublish-submit"
                or operation["request_sha256"] != _canonical_sha256(request)
            ):
                raise ValueError("stored publication operation differs from this draft")
            consumed = self.store.connection.execute(
                "SELECT 1 FROM nonce_ledger WHERE source=? AND nonce=?",
                (confirmation_source, nonce),
            ).fetchone()
            if consumed is None:
                raise ValueError(
                    "completed publication operation lacks its consumed confirmation nonce"
                )
            cached = json.loads(operation["response_json"])
        else:
            self.store.consume_nonce(confirmation_source, nonce, expires_at)
            cached = self.store.begin_operation(
                key, "freepublish-submit", request
            )
        try:
            submitted = cached or self.provider.freepublish_submit(
                str(draft["media_id"])
            )
        except AmbiguousMutation:
            self.store.mark_operation(key, "ambiguous")
            raise
        except Exception:
            self.store.mark_operation(key, "failed")
            raise
        if cached is None:
            self.store.finish_operation(key, submitted)
        publish_id = submitted.get("publish_id")
        if not isinstance(publish_id, str) or not publish_id:
            raise WeChatAPIError("freepublish/submit did not return publish_id")
        self.store.connection.execute(
            "INSERT OR REPLACE INTO publication_jobs(target_account_ref,article_revision,draft_media_id,draft_payload_sha256,compile_report_sha256,publish_id,state,status_code,result_json,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                target_account_ref,
                article_revision,
                draft["media_id"],
                expected_payload_sha,
                compile_report_sha,
                publish_id,
                "submitted",
                None,
                json.dumps(
                    {
                        "api_response": submitted,
                        "portable_audit_verified": portable,
                        "publication_authority_assurance": (
                            "portable-host-signed"
                            if portable
                            else "trusted-harness-policy-hook-not-independently-attested"
                        ),
                    },
                    ensure_ascii=False,
                ),
                self.store._now(),
            ),
        )
        return self._poll_publication_status(
            target_account_ref=target_account_ref,
            article_revision=article_revision,
            publish_id=publish_id,
            portable=portable,
            poll_attempts=poll_attempts,
            sleeper=sleeper,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--access-token-env", default="WECHAT_ACCESS_TOKEN")
    parser.add_argument("--app-id-env", default="WECHAT_APP_ID")
    subparsers = parser.add_subparsers(dest="command", required=True)

    account = subparsers.add_parser("preflight-account")
    account.add_argument("--target-account", required=True)
    account.add_argument("--output", type=Path, required=True)

    uploads = subparsers.add_parser("prepare-uploads")
    uploads.add_argument("handoff", type=Path)
    uploads.add_argument("--target-account", required=True)
    uploads.add_argument("--output", type=Path, required=True)

    draft = subparsers.add_parser("save-draft")
    draft.add_argument("handoff", type=Path)
    draft.add_argument("compile_report", type=Path)
    draft.add_argument("--target-account", required=True)
    draft.add_argument("--accept-editor-mobile-review", action="store_true")

    raw_readback = subparsers.add_parser("capture-raw")
    raw_readback.add_argument("media_id")
    raw_readback.add_argument("--target-account", required=True)
    raw_readback.add_argument("--output", type=Path, required=True)

    readback = subparsers.add_parser("capture-readback")
    readback.add_argument("--accept-editor-mobile-review", action="store_true")
    readback.add_argument("--viewport-review", type=Path)
    readback.add_argument("handoff", type=Path)
    readback.add_argument("compile_report", type=Path)
    readback.add_argument("media_id")
    readback.add_argument("--target-account", required=True)
    readback.add_argument("--output-dir", type=Path, required=True)
    readback.add_argument(
        "--screenshots",
        type=Path,
        help=(
            "portable signed host screenshot manifest; never accepted for the "
            "current-session ingestion route"
        ),
    )
    readback.add_argument(
        "--capture-bundle",
        type=Path,
        help=(
            "create-once current-session Browser/Computer Use capture bundle; "
            "nonportable and never publication authority"
        ),
    )

    publish = subparsers.add_parser("publish")
    publish.add_argument("compile_report", type=Path)
    publish.add_argument(
        "confirmation",
        type=Path,
        help=(
            "current-session confirmation challenge, or portable host-signed "
            "wechat-host-publication-confirmation-receipt-v1"
        ),
    )
    publish.add_argument("publication_gate", type=Path)
    publish.add_argument("--target-account", required=True)
    publish.add_argument("--article-revision", required=True)
    publish.add_argument("--poll-attempts", type=int, default=6)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    token = os.environ.get(args.access_token_env)
    app_id = os.environ.get(args.app_id_env)
    if not token or not app_id:
        raise SystemExit(
            f"{args.access_token_env} and {args.app_id_env} must be configured"
        )
    store = PublisherStore(args.store)
    try:
        publisher = WeChatPublisher(
            WeChatAPIProvider(access_token=token, app_id=app_id), store,
            allow_editor_review=getattr(args, "accept_editor_mobile_review", False),
        )
        if args.command == "preflight-account":
            result = publisher.preflight_account(
                target_account_ref=args.target_account,
                output_path=args.output,
            )
        elif args.command == "prepare-uploads":
            result = publisher.prepare_uploads(
                args.handoff,
                target_account_ref=args.target_account,
                output_path=args.output,
            )
        elif args.command == "save-draft":
            result = publisher.save_draft(
                args.handoff,
                args.compile_report,
                target_account_ref=args.target_account,
            )
        elif args.command == "capture-raw":
            result = publisher.capture_raw_draft(
                args.media_id,
                target_account_ref=args.target_account,
                output_path=args.output,
            )
        elif args.command == "capture-readback":
            result = publisher.capture_readback(
                args.handoff,
                args.compile_report,
                media_id=args.media_id,
                target_account_ref=args.target_account,
                output_dir=args.output_dir,
                screenshot_manifest_path=args.screenshots,
                capture_bundle_path=args.capture_bundle,
                viewport_review_path=args.viewport_review,
            )
        else:
            result = publisher.publish(
                target_account_ref=args.target_account,
                article_revision=args.article_revision,
                compile_report_path=args.compile_report,
                confirmation_path=args.confirmation,
                publication_gate_path=args.publication_gate,
                poll_attempts=args.poll_attempts,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())

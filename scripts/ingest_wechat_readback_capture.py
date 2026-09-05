#!/usr/bin/env python3
"""Ingest current-session WeChat chapter captures into a bound bundle.

This entrypoint is an integrity bridge for a real Browser/Computer Use capture
performed in the current Codex session.  It is deliberately non-portable and
does not attest the host, authorize publication, or accept the portable
screenshot-manifest schema used by the signed delivery route.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

if __name__ == "__main__":
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/ingest_wechat_readback_capture.py")

from PIL import Image

from safe_paths import (
    SafePathError,
    existing_directory,
    existing_regular_file,
    new_directory_path,
    write_bytes_create_once,
    write_text_create_once,
)
from transport_fidelity import _visual_similarity


BUNDLE_SOURCE = "wechat-current-session-readback-capture-bundle-v1"
RAW_DRAFT_SOURCE = "wechat-api-draft-get-raw-v1"
PROFILE_KIND = "org-wechat-runtime-profile"
REPORT_KIND = "org-wechat-runtime-preflight-report"
CENSUS_KIND = "org-wechat-host-registry-census-v1"
CAPTURE_CAPABILITY = "wechat_current_session_readback"
CAPTURE_SEMANTIC_KIND = "wechat.current-session-readback"
CAPTURE_NONCE_SOURCE = BUNDLE_SOURCE
BUNDLE_TRUTH_BOUNDARY = (
    "Binds current-session Browser/Computer Use capture bytes to the exact "
    "runtime, API draft reread and article revision. It is not a host signature "
    "and cannot authorize freepublish."
)
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{1,255}$")
NONCE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
CAPTURE_MAX_AGE = timedelta(minutes=10)
RUNTIME_ROOT = Path(__file__).resolve().parent.parent


class ReadbackCaptureIngestionError(ValueError):
    """Raised when a current-session capture cannot be bound safely."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ReadbackCaptureIngestionError(f"{label} must be an RFC3339 timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ReadbackCaptureIngestionError(
            f"{label} must be an RFC3339 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReadbackCaptureIngestionError(
            f"{label} must include a timezone offset"
        )
    return parsed.astimezone(timezone.utc)


def _read_json_file(path: Path, label: str) -> tuple[Path, dict[str, Any]]:
    try:
        source = existing_regular_file(path, label=label)
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, SafePathError) as exc:
        raise ReadbackCaptureIngestionError(f"{label} is unavailable: {exc}") from exc
    if not isinstance(value, dict):
        raise ReadbackCaptureIngestionError(f"{label} must be a JSON object")
    return source, value


def _outside(path: Path, root: Path, label: str) -> None:
    try:
        path.relative_to(root)
    except ValueError:
        return
    raise ReadbackCaptureIngestionError(
        f"{label} must remain outside the installed runtime: {root}"
    )


def _sanitize_observed_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ReadbackCaptureIngestionError("observed URL is invalid") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != "mp.weixin.qq.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/")
    ):
        raise ReadbackCaptureIngestionError(
            "observed URL must be credential-free https://mp.weixin.qq.com/ with no query or fragment"
        )
    return f"https://mp.weixin.qq.com{parsed.path}"


def _validate_raw_capture(
    path: Path,
    payload: Mapping[str, Any],
    *,
    target_account_ref: str,
    draft_id: str,
) -> dict[str, Any]:
    required = {
        "schema_version",
        "source",
        "target_account_ref",
        "draft_id",
        "request",
        "observed_at",
        "http_status",
        "response_headers",
        "response",
        "response_sha256",
    }
    request = payload.get("request")
    response = payload.get("response")
    if (
        set(payload) != required
        or payload.get("schema_version") != 1
        or payload.get("source") != RAW_DRAFT_SOURCE
        or payload.get("target_account_ref") != target_account_ref
        or payload.get("draft_id") != draft_id
        or payload.get("http_status") != 200
        or not isinstance(payload.get("response_headers"), dict)
        or not isinstance(request, dict)
        or set(request) != {"endpoint", "method", "request_id"}
        or request.get("endpoint") != "/cgi-bin/draft/get"
        or request.get("method") != "POST"
        or not isinstance(request.get("request_id"), str)
        or not IDENTIFIER.fullmatch(str(request.get("request_id")))
        or not isinstance(response, dict)
        or payload.get("response_sha256") != _canonical_sha256(response)
    ):
        raise ReadbackCaptureIngestionError(
            "raw draft capture is not one complete bound API draft/get response"
        )
    items = response.get("news_item")
    if (
        not isinstance(items, list)
        or len(items) != 1
        or not isinstance(items[0], dict)
        or not isinstance(items[0].get("content"), str)
    ):
        raise ReadbackCaptureIngestionError(
            "raw draft capture must contain exactly one article with content"
        )
    return {
        "path": str(path),
        "sha256": _file_sha256(path),
        "byte_length": path.stat().st_size,
        "request_id": request["request_id"],
        "response_sha256": payload["response_sha256"],
        "observed_at": payload["observed_at"],
    }


def _runtime_binding(
    *,
    profile_path: Path,
    report_path: Path,
    census_path: Path,
    target_account_ref: str,
    host_session_id: str,
    capture_tool_id: str,
) -> tuple[dict[str, Any], Path]:
    profile_path, profile = _read_json_file(profile_path, "runtime profile")
    report_path, report = _read_json_file(report_path, "runtime binding report")
    census_path, census = _read_json_file(census_path, "registry census")
    if (
        profile.get("schema_version") != 2
        or profile.get("kind") != PROFILE_KIND
        or report.get("schema_version") != 2
        or report.get("kind") != REPORT_KIND
        or report.get("phase") not in {"delivery", "full"}
        or report.get("check_level") != "binding"
        or report.get("ok") is not True
        or report.get("binding_ready") is not True
        or report.get("phase_ready") is not False
        or census.get("schema_version") != 1
        or census.get("kind") != CENSUS_KIND
    ):
        raise ReadbackCaptureIngestionError(
            "current-session readback requires a passing delivery/full binding profile, report and census"
        )
    if census.get("registry_digest") != _canonical_sha256(
        {key: value for key, value in census.items() if key != "registry_digest"}
    ):
        raise ReadbackCaptureIngestionError("registry census digest is invalid")
    census_sha = _file_sha256(census_path)
    census_reference = profile.get("registry_census")
    if (
        not isinstance(census_reference, dict)
        or Path(str(census_reference.get("path", ""))) != census_path
        or census_reference.get("sha256") != census_sha
    ):
        raise ReadbackCaptureIngestionError(
            "runtime profile does not bind the exact registry census bytes"
        )

    local = report.get("local")
    if not isinstance(local, dict):
        raise ReadbackCaptureIngestionError("runtime binding report lacks local evidence")
    try:
        from runtime_preflight import _binding_digest, _validate_registry_census

        registry_errors: list[dict[str, str]] = []
        installed = _validate_registry_census(
            profile, RUNTIME_ROOT, registry_errors
        )
    except Exception as exc:
        raise ReadbackCaptureIngestionError(
            f"verified installed release/census cannot be rechecked: {exc}"
        ) from exc
    if registry_errors or installed.get("verified") is not True:
        detail = "; ".join(
            str(item.get("message", item)) for item in registry_errors
        )
        raise ReadbackCaptureIngestionError(
            "verified installed release/census recheck failed"
            + (f": {detail}" if detail else "")
        )
    if (
        local.get("installed_registry_verified") is not True
        or local.get("installed_release_sha256") != installed.get("release_sha256")
        or local.get("registry_digest") != installed.get("registry_digest")
        or local.get("registry_census_sha256") != census_sha
    ):
        raise ReadbackCaptureIngestionError(
            "runtime binding report no longer matches the verified installed release/census"
        )
    trusted_bundle = local.get("trusted_bundle_sha256")
    resolved_links = report.get("resolved_links")
    if not SHA256.fullmatch(str(trusted_bundle or "")) or not isinstance(
        resolved_links, dict
    ):
        raise ReadbackCaptureIngestionError(
            "runtime binding report lacks its trusted bundle/link binding"
        )
    expected_binding = _binding_digest(
        profile, str(report["phase"]), resolved_links, str(trusted_bundle)
    )
    if report.get("binding_digest") != expected_binding:
        raise ReadbackCaptureIngestionError("runtime binding digest is stale or forged")

    resolved = report.get("resolved_capabilities")
    readback_capability = (
        resolved.get(CAPTURE_CAPABILITY) if isinstance(resolved, dict) else None
    )
    delivery = resolved.get("wechat_delivery") if isinstance(resolved, dict) else None
    selected_profile_capability = (
        profile.get("capabilities", {}).get(CAPTURE_CAPABILITY)
        if isinstance(profile.get("capabilities"), dict)
        else None
    )
    tool_ids = (
        readback_capability.get("tool_ids")
        if isinstance(readback_capability, dict)
        else None
    )
    if (
        not isinstance(delivery, dict)
        or delivery.get("mode") != "api"
        or delivery.get("terminal_state", "draft") != "draft"
        or delivery.get("target_account_ref") != target_account_ref
        or not isinstance(readback_capability, dict)
        or readback_capability.get("mode") != "host-ui"
        or not isinstance(selected_profile_capability, dict)
        or selected_profile_capability.get("status") not in {"declared", "passed"}
        or not isinstance(tool_ids, list)
        or capture_tool_id not in tool_ids
    ):
        raise ReadbackCaptureIngestionError(
            "runtime binding does not select the exact API-draft current-session readback UI route"
        )

    census_tools = {
        item.get("id"): item
        for item in census.get("tools", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    tool = census_tools.get(capture_tool_id)
    if (
        not isinstance(tool, dict)
        or tool.get("kind") != CAPTURE_SEMANTIC_KIND
        or tool.get("status") != "available"
        or tool.get("session_id") != host_session_id
        or not isinstance(tool.get("provider"), str)
    ):
        raise ReadbackCaptureIngestionError(
            "capture tool/provider/session does not match the registry census"
        )
    harness = census.get("harness")
    if (
        not isinstance(harness, dict)
        or harness.get("session_id") != host_session_id
        or report.get("resolved_harness", {}).get("name") != harness.get("name")
    ):
        raise ReadbackCaptureIngestionError(
            "capture host session does not match the runtime/census harness"
        )

    release = census.get("installed_release")
    if not isinstance(release, dict):
        raise ReadbackCaptureIngestionError("registry census lacks installed release binding")
    skills_root = existing_directory(
        Path(str(release.get("skills_root", ""))), label="installed skills root"
    )
    manifest_value = Path(str(release.get("manifest_path", "")))
    if not manifest_value.is_absolute():
        manifest_value = RUNTIME_ROOT / manifest_value
    manifest_path = existing_regular_file(
        manifest_value, label="installed release manifest"
    )
    if (
        _file_sha256(manifest_path) != release.get("manifest_sha256")
        or release.get("release_sha256") != installed.get("release_sha256")
    ):
        raise ReadbackCaptureIngestionError(
            "installed release manifest or release digest changed after census"
        )

    runtime = {
        "profile": {
            "path": str(profile_path),
            "sha256": _file_sha256(profile_path),
        },
        "binding_report": {
            "path": str(report_path),
            "sha256": _file_sha256(report_path),
            "binding_digest": expected_binding,
            "trusted_bundle_sha256": trusted_bundle,
        },
        "registry_census": {
            "path": str(census_path),
            "sha256": census_sha,
            "registry_digest": census.get("registry_digest"),
        },
        "installed_release": {
            "skills_root": str(skills_root),
            "release_sha256": installed.get("release_sha256"),
            "manifest_path": str(manifest_path),
            "manifest_sha256": _file_sha256(manifest_path),
        },
        "host": {
            "harness": harness.get("name"),
            "session_id": host_session_id,
            "capture_tool_id": capture_tool_id,
            "capture_tool_kind": CAPTURE_SEMANTIC_KIND,
            "capture_provider": tool.get("provider"),
        },
    }
    return runtime, skills_root


def _chapter_specification(
    handoff: Mapping[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    export = (
        handoff.get("transport_fidelity", {}).get("export")
        if isinstance(handoff.get("transport_fidelity"), dict)
        else None
    )
    chapters = export.get("chapters") if isinstance(export, dict) else None
    revision = export.get("revision_hash") if isinstance(export, dict) else None
    if (
        not SHA256.fullmatch(str(revision or ""))
        or not isinstance(chapters, list)
        or not chapters
        or any(not isinstance(item, dict) for item in chapters)
    ):
        raise ReadbackCaptureIngestionError(
            "handoff lacks a complete transport revision/chapter export"
        )
    return str(revision), chapters


def _validate_png(path: Path, expected_size: tuple[int, int]) -> tuple[str, int]:
    payload = path.read_bytes()
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            if image.format != "PNG" or image.size != expected_size:
                raise ReadbackCaptureIngestionError(
                    f"chapter capture must be a real {expected_size[0]}x{expected_size[1]} PNG"
                )
            image.load()
    except (OSError, ValueError) as exc:
        raise ReadbackCaptureIngestionError(
            "chapter capture is not a valid PNG"
        ) from exc
    return digest, len(payload)


def validate_current_session_bundle(
    bundle_path: Path,
    *,
    handoff_path: Path,
    compile_report_path: Path,
    target_account_ref: str,
    draft_id: str,
    article_revision: str,
) -> dict[str, Any]:
    """Revalidate an ingested bundle against its live files and exact target."""

    bundle_path, bundle = _read_json_file(bundle_path, "readback capture bundle")
    expected_fields = {
        "schema_version",
        "source",
        "created_at",
        "assurance_scope",
        "host_attested",
        "portable",
        "publication_authority",
        "truth_boundary",
        "nonce",
        "runtime",
        "target",
        "raw_draft",
        "browser_observation",
        "chapters",
    }
    if (
        set(bundle) != expected_fields
        or bundle.get("schema_version") != 1
        or bundle.get("source") != BUNDLE_SOURCE
        or bundle.get("assurance_scope") != "current-session-only"
        or bundle.get("host_attested") is not False
        or bundle.get("portable") is not False
        or bundle.get("publication_authority") is not False
        or bundle.get("truth_boundary") != BUNDLE_TRUTH_BOUNDARY
        or not NONCE.fullmatch(str(bundle.get("nonce", "")))
    ):
        raise ReadbackCaptureIngestionError(
            "capture bundle must remain current-session-only, nonportable and non-authorizing"
        )
    current = datetime.now(timezone.utc)
    created_at = _parse_time(bundle.get("created_at"), "capture bundle created_at")
    if (
        created_at > current + timedelta(seconds=30)
        or current - created_at > CAPTURE_MAX_AGE
    ):
        raise ReadbackCaptureIngestionError(
            "capture bundle creation time is stale or future-dated"
        )
    target = bundle.get("target")
    if (
        not isinstance(target, dict)
        or set(target)
        != {
            "target_account_ref",
            "draft_id",
            "article_revision",
            "handoff_sha256",
            "compile_report_sha256",
        }
        or target.get("target_account_ref") != target_account_ref
        or target.get("draft_id") != draft_id
        or target.get("article_revision") != article_revision
    ):
        raise ReadbackCaptureIngestionError(
            "capture bundle is bound to a different account/draft/revision"
        )
    handoff_path = existing_regular_file(handoff_path, label="handoff")
    compile_report_path, compile_report = _read_json_file(
        compile_report_path, "compile report"
    )
    if (
        target.get("handoff_sha256") != _file_sha256(handoff_path)
        or target.get("compile_report_sha256")
        != _file_sha256(compile_report_path)
        or compile_report.get("revision_hash") != article_revision
        or compile_report.get("assurance_scope")
        not in {"current-session-draft", "current-session-interaction-probe"}
        or compile_report.get("portable_audit_verified") is not False
    ):
        raise ReadbackCaptureIngestionError(
            "capture bundle handoff/compile bytes or current-session scope changed"
        )

    runtime = bundle.get("runtime")
    host = runtime.get("host") if isinstance(runtime, dict) else None
    if not isinstance(runtime, dict) or not isinstance(host, dict):
        raise ReadbackCaptureIngestionError("capture bundle runtime binding is missing")
    rebound, _skills_root = _runtime_binding(
        profile_path=Path(str(runtime.get("profile", {}).get("path", ""))),
        report_path=Path(
            str(runtime.get("binding_report", {}).get("path", ""))
        ),
        census_path=Path(
            str(runtime.get("registry_census", {}).get("path", ""))
        ),
        target_account_ref=target_account_ref,
        host_session_id=str(host.get("session_id", "")),
        capture_tool_id=str(host.get("capture_tool_id", "")),
    )
    if runtime != rebound:
        raise ReadbackCaptureIngestionError(
            "capture bundle runtime/release/census/session binding changed"
        )

    observation = bundle.get("browser_observation")
    if (
        not isinstance(observation, dict)
        or set(observation)
        != {"credential_free_url", "host_session_id", "capture_tool_id"}
        or observation.get("host_session_id") != host.get("session_id")
        or observation.get("capture_tool_id") != host.get("capture_tool_id")
        or observation.get("credential_free_url")
        != _sanitize_observed_url(str(observation.get("credential_free_url", "")))
    ):
        raise ReadbackCaptureIngestionError(
            "Browser observation URL/tool/session binding is invalid or credential-bearing"
        )

    raw = bundle.get("raw_draft")
    if not isinstance(raw, dict) or set(raw) != {
        "path",
        "sha256",
        "byte_length",
        "request_id",
        "response_sha256",
        "observed_at",
    }:
        raise ReadbackCaptureIngestionError("capture bundle raw draft binding is invalid")
    raw_path, raw_payload = _read_json_file(
        Path(str(raw.get("path", ""))), "raw draft capture"
    )
    raw_expected = _validate_raw_capture(
        raw_path,
        raw_payload,
        target_account_ref=target_account_ref,
        draft_id=draft_id,
    )
    if raw != raw_expected:
        raise ReadbackCaptureIngestionError(
            "capture bundle raw draft bytes/request changed after ingestion"
        )
    raw_observed = _parse_time(raw.get("observed_at"), "raw draft observed_at")
    compiled_at = _parse_time(
        compile_report.get("compiled_at"), "compile report compiled_at"
    )
    if (
        raw_observed <= compiled_at
        or raw_observed > created_at
        or created_at - raw_observed > CAPTURE_MAX_AGE
    ):
        raise ReadbackCaptureIngestionError(
            "capture bundle was not created promptly after the bound API reread"
        )

    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    bound_revision, expected_chapters = _chapter_specification(handoff)
    if bound_revision != article_revision:
        raise ReadbackCaptureIngestionError(
            "capture bundle handoff revision differs from the exact target"
        )
    bundle_chapters = bundle.get("chapters")
    if not isinstance(bundle_chapters, list):
        raise ReadbackCaptureIngestionError("capture bundle chapters must be a list")
    chapter_map = {
        str(item.get("chapter_id")): item
        for item in bundle_chapters
        if isinstance(item, dict)
    }
    if (
        len(bundle_chapters) != len(expected_chapters)
        or len(chapter_map) != len(expected_chapters)
    ):
        raise ReadbackCaptureIngestionError(
            "capture bundle does not contain every chapter exactly once"
        )
    byte_hashes: set[str] = set()
    event_ids: set[str] = set()
    for chapter in expected_chapters:
        chapter_id = str(chapter.get("chapter_id"))
        item = chapter_map.get(chapter_id)
        if not isinstance(item, dict) or set(item) != {
            "chapter_id",
            "path",
            "sha256",
            "byte_length",
            "width_px",
            "height_px",
            "captured_at",
            "capture_event_id",
        }:
            raise ReadbackCaptureIngestionError(
                f"capture bundle chapter {chapter_id} is invalid"
            )
        capture_path = existing_regular_file(
            bundle_path.parent / str(item.get("path", "")),
            label=f"chapter {chapter_id} capture",
        )
        relative_capture = Path(str(item.get("path", "")))
        if (
            relative_capture.is_absolute()
            or relative_capture.name != str(item.get("path", ""))
            or capture_path.parent != bundle_path.parent
        ):
            raise ReadbackCaptureIngestionError(
                "capture bundle chapter paths must be local create-once basenames"
            )
        expected_size = (
            390,
            round(float(chapter.get("geometry", {}).get("height", 0))),
        )
        digest, byte_length = _validate_png(capture_path, expected_size)
        event_id = str(item.get("capture_event_id", ""))
        captured_at = _parse_time(
            item.get("captured_at"), f"chapter {chapter_id} captured_at"
        )
        if (
            item.get("chapter_id") != chapter_id
            or item.get("sha256") != digest
            or item.get("byte_length") != byte_length
            or item.get("width_px") != expected_size[0]
            or item.get("height_px") != expected_size[1]
            or not IDENTIFIER.fullmatch(event_id)
            or digest in byte_hashes
            or event_id in event_ids
            or captured_at <= raw_observed
            or captured_at > created_at
            or created_at - captured_at > CAPTURE_MAX_AGE
        ):
            raise ReadbackCaptureIngestionError(
                "capture bundle contains mismatched or duplicate chapter bytes/events"
            )
        byte_hashes.add(digest)
        event_ids.add(event_id)
    return bundle


def ingest_wechat_readback_capture(
    *,
    handoff_path: Path,
    compile_report_path: Path,
    raw_draft_path: Path,
    runtime_profile_path: Path,
    runtime_report_path: Path,
    registry_census_path: Path,
    target_account_ref: str,
    draft_id: str,
    article_revision: str,
    host_session_id: str,
    capture_tool_id: str,
    observed_url: str,
    nonce: str,
    chapter_captures: Sequence[Mapping[str, Any]],
    output_dir: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not NONCE.fullmatch(nonce):
        raise ReadbackCaptureIngestionError("capture nonce is invalid")
    for value, label in (
        (target_account_ref, "target account"),
        (draft_id, "draft id"),
        (host_session_id, "host session id"),
        (capture_tool_id, "capture tool id"),
    ):
        if not IDENTIFIER.fullmatch(value):
            raise ReadbackCaptureIngestionError(f"{label} is invalid")
    if not SHA256.fullmatch(article_revision):
        raise ReadbackCaptureIngestionError("article revision is invalid")
    observed_url = _sanitize_observed_url(observed_url)

    try:
        output_dir = new_directory_path(
            output_dir,
            label="readback capture bundle output",
            forbidden_root=RUNTIME_ROOT,
        )
    except SafePathError as exc:
        raise ReadbackCaptureIngestionError(str(exc)) from exc
    handoff_path, handoff = _read_json_file(handoff_path, "handoff")
    compile_report_path, compile_report = _read_json_file(
        compile_report_path, "compile report"
    )
    raw_draft_path, raw_draft = _read_json_file(
        raw_draft_path, "raw draft capture"
    )
    runtime, skills_root = _runtime_binding(
        profile_path=runtime_profile_path,
        report_path=runtime_report_path,
        census_path=registry_census_path,
        target_account_ref=target_account_ref,
        host_session_id=host_session_id,
        capture_tool_id=capture_tool_id,
    )
    _outside(output_dir, skills_root, "readback capture bundle output")
    revision, chapters = _chapter_specification(handoff)
    if (
        revision != article_revision
        or compile_report.get("revision_hash") != article_revision
        or compile_report.get("assurance_scope")
        not in {"current-session-draft", "current-session-interaction-probe"}
        or compile_report.get("portable_audit_verified") is not False
    ):
        raise ReadbackCaptureIngestionError(
            "compile/handoff revision is not a current-session nonportable candidate"
        )
    raw_binding = _validate_raw_capture(
        raw_draft_path,
        raw_draft,
        target_account_ref=target_account_ref,
        draft_id=draft_id,
    )
    raw_observed = _parse_time(raw_binding["observed_at"], "raw draft observed_at")
    compiled_at = _parse_time(
        compile_report.get("compiled_at"), "compile report compiled_at"
    )
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if (
        raw_observed <= compiled_at
        or raw_observed > current
        or current - raw_observed > CAPTURE_MAX_AGE
    ):
        raise ReadbackCaptureIngestionError("raw draft capture is stale or future-dated")

    expected_by_id = {str(item.get("chapter_id")): item for item in chapters}
    supplied_by_id: dict[str, Mapping[str, Any]] = {}
    for item in chapter_captures:
        chapter_id = item.get("chapter_id") if isinstance(item, Mapping) else None
        if not isinstance(chapter_id, str) or chapter_id in supplied_by_id:
            raise ReadbackCaptureIngestionError(
                "chapter capture IDs must be present and unique"
            )
        supplied_by_id[chapter_id] = item
    if set(supplied_by_id) != set(expected_by_id):
        raise ReadbackCaptureIngestionError(
            "chapter capture set must exactly match the frozen handoff chapters"
        )

    prepared: list[tuple[dict[str, Any], Path, bytes]] = []
    seen_hashes: set[str] = set()
    seen_events: set[str] = set()
    for chapter_id, chapter in expected_by_id.items():
        item = supplied_by_id[chapter_id]
        try:
            source = existing_regular_file(
                Path(str(item.get("path", ""))),
                label=f"chapter {chapter_id} source capture",
            )
        except SafePathError as exc:
            raise ReadbackCaptureIngestionError(str(exc)) from exc
        captured_at = _parse_time(
            item.get("captured_at"), f"chapter {chapter_id} captured_at"
        )
        event_id = str(item.get("capture_event_id", ""))
        if (
            captured_at <= raw_observed
            or captured_at > current
            or current - captured_at > CAPTURE_MAX_AGE
            or not IDENTIFIER.fullmatch(event_id)
            or event_id in seen_events
        ):
            raise ReadbackCaptureIngestionError(
                f"chapter {chapter_id} capture time/event is invalid or duplicated"
            )
        expected_size = (
            390,
            round(float(chapter.get("geometry", {}).get("height", 0))),
        )
        digest, byte_length = _validate_png(source, expected_size)
        if digest in seen_hashes:
            raise ReadbackCaptureIngestionError(
                "chapter captures must contain distinct actual PNG bytes"
            )
        reference = chapter.get("reference_screenshot")
        reference_path = (
            existing_regular_file(
                handoff_path.parent / str(reference.get("path", "")),
                label=f"chapter {chapter_id} Ardot reference",
            )
            if isinstance(reference, dict)
            else None
        )
        if reference_path is None:
            raise ReadbackCaptureIngestionError("Ardot reference screenshot is missing")
        try:
            same_file = source.samefile(reference_path)
        except OSError:
            same_file = False
        if same_file:
            raise ReadbackCaptureIngestionError(
                "Ardot reference cannot masquerade as a WeChat chapter capture"
            )
        destination_name = (
            "chapter-"
            + re.sub(r"[^A-Za-z0-9._-]+", "-", chapter_id).strip("-.")
            + ".png"
        )
        if destination_name == "chapter-.png":
            raise ReadbackCaptureIngestionError("chapter ID cannot form a safe filename")
        record = {
            "chapter_id": chapter_id,
            "path": destination_name,
            "sha256": digest,
            "byte_length": byte_length,
            "width_px": expected_size[0],
            "height_px": expected_size[1],
            "captured_at": captured_at.isoformat(),
            "capture_event_id": event_id,
        }
        prepared.append((record, source, source.read_bytes()))
        seen_hashes.add(digest)
        seen_events.add(event_id)

    try:
        os.mkdir(output_dir, mode=0o700)
        metadata = output_dir.lstat()
    except OSError as exc:
        raise ReadbackCaptureIngestionError(
            f"readback capture bundle output cannot be created once: {exc}"
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ReadbackCaptureIngestionError(
            "readback capture bundle output must be a real directory"
        )
    for record, _source, payload in prepared:
        write_bytes_create_once(
            output_dir / str(record["path"]),
            payload,
            label=f"chapter {record['chapter_id']} bundle capture",
        )

    bundle = {
        "schema_version": 1,
        "source": BUNDLE_SOURCE,
        "created_at": current.isoformat(),
        "assurance_scope": "current-session-only",
        "host_attested": False,
        "portable": False,
        "publication_authority": False,
        "truth_boundary": BUNDLE_TRUTH_BOUNDARY,
        "nonce": nonce,
        "runtime": runtime,
        "target": {
            "target_account_ref": target_account_ref,
            "draft_id": draft_id,
            "article_revision": article_revision,
            "handoff_sha256": _file_sha256(handoff_path),
            "compile_report_sha256": _file_sha256(compile_report_path),
        },
        "raw_draft": raw_binding,
        "browser_observation": {
            "credential_free_url": observed_url,
            "host_session_id": host_session_id,
            "capture_tool_id": capture_tool_id,
        },
        "chapters": [item[0] for item in prepared],
    }
    bundle_path = output_dir / "capture-bundle.json"
    write_text_create_once(
        bundle_path,
        json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        label="readback capture bundle",
    )
    validate_current_session_bundle(
        bundle_path,
        handoff_path=handoff_path,
        compile_report_path=compile_report_path,
        target_account_ref=target_account_ref,
        draft_id=draft_id,
        article_revision=article_revision,
    )
    return {
        "state": "current-session-readback-capture-ingested",
        "bundle": str(bundle_path),
        "bundle_sha256": _file_sha256(bundle_path),
        "host_attested": False,
        "portable": False,
        "publication_authority": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff", type=Path)
    parser.add_argument("compile_report", type=Path)
    parser.add_argument("raw_draft", type=Path)
    parser.add_argument("--runtime-profile", type=Path, required=True)
    parser.add_argument("--runtime-report", type=Path, required=True)
    parser.add_argument("--registry-census", type=Path, required=True)
    parser.add_argument("--target-account", required=True)
    parser.add_argument("--draft-id", required=True)
    parser.add_argument("--article-revision", required=True)
    parser.add_argument("--host-session-id", required=True)
    parser.add_argument("--capture-tool-id", required=True)
    parser.add_argument("--observed-url", required=True)
    parser.add_argument("--nonce", required=True)
    parser.add_argument(
        "--chapter-capture",
        action="append",
        nargs=4,
        metavar=("CHAPTER_ID", "PNG_PATH", "CAPTURED_AT", "EVENT_ID"),
        required=True,
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    chapter_captures = [
        {
            "chapter_id": values[0],
            "path": values[1],
            "captured_at": values[2],
            "capture_event_id": values[3],
        }
        for values in args.chapter_capture
    ]
    try:
        result = ingest_wechat_readback_capture(
            handoff_path=args.handoff,
            compile_report_path=args.compile_report,
            raw_draft_path=args.raw_draft,
            runtime_profile_path=args.runtime_profile,
            runtime_report_path=args.runtime_report,
            registry_census_path=args.registry_census,
            target_account_ref=args.target_account,
            draft_id=args.draft_id,
            article_revision=args.article_revision,
            host_session_id=args.host_session_id,
            capture_tool_id=args.capture_tool_id,
            observed_url=args.observed_url,
            nonce=args.nonce,
            chapter_captures=chapter_captures,
            output_dir=args.output_dir,
        )
    except (OSError, ReadbackCaptureIngestionError, SafePathError) as exc:
        raise SystemExit(f"wechat-readback-ingestion: {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

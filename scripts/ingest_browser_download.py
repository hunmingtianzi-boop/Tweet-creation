#!/usr/bin/env python3
"""Create-once ingestion for a Browser-observed download path.

This is a current-session integrity bridge, not a browser-event signature.  It
copies a regular non-symlink source into an explicitly bounded staging root,
then records both sides' bytes and SHA-256 in a create-once JSON report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

if __name__ == "__main__":
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/ingest_browser_download.py")


SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{1,159}$")
NONCE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


class IngestionError(RuntimeError):
    pass


def _sha256_stream(handle: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
        total += len(chunk)
    return "sha256:" + digest.hexdigest(), total


def _assert_no_symlink_components(path: Path) -> None:
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise IngestionError(f"path contains a symbolic link: {cursor}")


def _bounded_new_path(raw: Path, allowed_root: Path, label: str) -> Path:
    candidate = raw.expanduser().absolute()
    root = allowed_root.expanduser().resolve(strict=True)
    if not root.is_dir() or root in {Path(root.anchor), Path.home().resolve()}:
        raise IngestionError("allowed target root must be a narrow existing directory")
    _assert_no_symlink_components(root)
    _assert_no_symlink_components(candidate.parent)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise IngestionError(f"{label} must stay under the allowed target root") from exc
    if candidate.exists() or candidate.is_symlink():
        raise IngestionError(f"{label} already exists; overwrite is forbidden")
    if not candidate.parent.is_dir():
        raise IngestionError(f"{label} parent directory must already exist")
    return candidate


def _open_source(path: Path) -> tuple[int, os.stat_result]:
    if not path.is_absolute():
        raise IngestionError("source download path must be absolute")
    _assert_no_symlink_components(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise IngestionError(f"cannot open source download: {exc}") from exc
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        os.close(descriptor)
        raise IngestionError("source download must be a regular file")
    return descriptor, metadata


def ingest_download(
    source: Path,
    target: Path,
    report: Path,
    allowed_target_root: Path,
    *,
    binding_nonce: str,
    binding_digest: str,
    provider_session_id: str,
    provider_request_id: str,
    observed_download_id: str,
    request_metadata_sha256: str,
) -> dict[str, object]:
    if not NONCE.fullmatch(binding_nonce):
        raise IngestionError("binding nonce is invalid")
    for value, label in (
        (binding_digest, "binding digest"),
        (request_metadata_sha256, "request metadata digest"),
    ):
        if not SHA256.fullmatch(value):
            raise IngestionError(f"{label} is invalid")
    for value, label in (
        (provider_session_id, "provider session id"),
        (provider_request_id, "provider request id"),
        (observed_download_id, "observed download id"),
    ):
        if not IDENTIFIER.fullmatch(value):
            raise IngestionError(f"{label} is invalid")

    source = source.expanduser().absolute()
    target = _bounded_new_path(target, allowed_target_root, "target")
    report = _bounded_new_path(report, allowed_target_root, "report")
    if source in {target, report} or target == report:
        raise IngestionError("source, target and report must be distinct")

    descriptor, before = _open_source(source)
    copied_sha = ""
    copied_bytes = 0
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as reader, target.open("xb") as writer:
            digest = hashlib.sha256()
            for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                writer.write(chunk)
                digest.update(chunk)
                copied_bytes += len(chunk)
            writer.flush()
            os.fsync(writer.fileno())
            after = os.fstat(reader.fileno())
            copied_sha = "sha256:" + digest.hexdigest()
    except Exception:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
        target.unlink(missing_ok=True)
        raise IngestionError("source download changed while it was copied")
    if copied_bytes != before.st_size:
        target.unlink(missing_ok=True)
        raise IngestionError("source byte length changed while it was copied")

    target_flags = os.O_RDONLY | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
    target_fd = os.open(target, target_flags)
    try:
        with os.fdopen(target_fd, "rb", closefd=True) as target_reader:
            target_sha, target_bytes = _sha256_stream(target_reader)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    if target_sha != copied_sha or target_bytes != copied_bytes:
        target.unlink(missing_ok=True)
        raise IngestionError("target readback does not match the source stream")

    payload: dict[str, object] = {
        "schema_version": 1,
        "kind": "org-wechat-browser-download-ingestion-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "assurance": "current-session-observed-path",
        "browser_event_attested": False,
        "truth_boundary": (
            "The host trace supplied the observed source path and identifiers; this local "
            "report proves create-once byte ingestion only and is not a signed browser event."
        ),
        "binding": {
            "binding_nonce": binding_nonce,
            "binding_digest": binding_digest,
            "request_metadata_sha256": request_metadata_sha256,
        },
        "host_trace": {
            "provider_session_id": provider_session_id,
            "provider_request_id": provider_request_id,
            "observed_download_id": observed_download_id,
        },
        "source": {
            "observed_absolute_path": str(source),
            "sha256": copied_sha,
            "byte_length": copied_bytes,
            "device": before.st_dev,
            "inode": before.st_ino,
            "mtime_ns": before.st_mtime_ns,
        },
        "target": {
            "path": str(target),
            "sha256": target_sha,
            "byte_length": target_bytes,
            "create_once": True,
        },
    }
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        with report.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--allowed-target-root", type=Path, required=True)
    parser.add_argument("--binding-nonce", required=True)
    parser.add_argument("--binding-digest", required=True)
    parser.add_argument("--provider-session-id", required=True)
    parser.add_argument("--provider-request-id", required=True)
    parser.add_argument("--observed-download-id", required=True)
    parser.add_argument("--request-metadata-sha256", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = ingest_download(
            args.source,
            args.target,
            args.report,
            args.allowed_target_root,
            binding_nonce=args.binding_nonce,
            binding_digest=args.binding_digest,
            provider_session_id=args.provider_session_id,
            provider_request_id=args.provider_request_id,
            observed_download_id=args.observed_download_id,
            request_metadata_sha256=args.request_metadata_sha256,
        )
    except (OSError, IngestionError) as exc:
        raise SystemExit(f"download-ingestion: {exc}") from exc
    print(
        json.dumps(
            {
                "created": str(args.target.expanduser().absolute()),
                "report": str(args.report.expanduser().absolute()),
                "sha256": result["target"]["sha256"],  # type: ignore[index]
                "byte_length": result["target"]["byte_length"],  # type: ignore[index]
                "browser_event_attested": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Stdlib-only verification shared by isolated workflow entrypoints."""

from __future__ import annotations

import hashlib
import importlib.machinery
import json
import os
import platform
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Collection


MARKER_NAME = "_org_wechat_secure_runtime_v1"
SNAPSHOT_MANIFEST_NAME = ".org-wechat-dependency-snapshot-v1.json"


def _die(message: str) -> "NoReturn":  # type: ignore[name-defined]
    raise SystemExit(message)


def _platform_key() -> str:
    return "-".join(
        (
            platform.system().lower(),
            platform.machine().lower(),
            sys.implementation.cache_tag or "unknown-python",
        )
    )


def _script_importable_entries(root: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    suffixes = sorted(
        {
            *importlib.machinery.SOURCE_SUFFIXES,
            *importlib.machinery.BYTECODE_SUFFIXES,
            *importlib.machinery.EXTENSION_SUFFIXES,
        },
        key=len,
        reverse=True,
    )
    try:
        children = sorted(root.iterdir(), key=lambda item: item.name)
    except OSError as exc:
        _die(f"secure scripts import root is unavailable: {exc}")
    for child in children:
        name = child.name
        if name == "__pycache__" and child.is_dir() and not child.is_symlink():
            continue
        if child.is_symlink():
            importable = name.isidentifier() or any(
                name.endswith(suffix) and name[: -len(suffix)].isidentifier()
                for suffix in suffixes
            )
            if importable:
                _die(f"secure scripts importable entry is a symlink: {name}")
            continue
        if child.is_dir():
            if name.isidentifier():
                entries.append({"kind": "directory", "path": name})
            continue
        for suffix in suffixes:
            if name.endswith(suffix) and name[: -len(suffix)].isidentifier():
                kind = "source"
                if suffix in importlib.machinery.BYTECODE_SUFFIXES:
                    kind = "bytecode"
                elif suffix in importlib.machinery.EXTENSION_SUFFIXES:
                    kind = "extension"
                entries.append({"kind": kind, "path": name})
                break
    entries.sort(key=lambda item: (item["path"], item["kind"]))
    return entries


def _validate_scripts_census(lock: dict[str, Any], scripts_root: Path) -> None:
    census = lock.get("scripts_importable_census")
    if (
        not isinstance(census, dict)
        or set(census) != {"algorithm", "entries"}
        or census.get("algorithm") != "top-level-python-importables-v1"
        or not isinstance(census.get("entries"), list)
    ):
        _die("secure scripts importable census schema is invalid")
    expected = census["entries"]
    for item in expected:
        if (
            not isinstance(item, dict)
            or set(item) != {"kind", "path"}
            or item.get("kind") not in {"source", "bytecode", "extension", "directory"}
            or not isinstance(item.get("path"), str)
            or Path(item["path"]).name != item["path"]
        ):
            _die("secure scripts importable census entry is invalid")
    if _script_importable_entries(scripts_root) != expected:
        _die("secure scripts importable census changed after runner validation")


def _parse_sha256(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        _die(f"{label} is not a canonical sha256 digest")
    return value[7:]


def _rows_digest(rows: list[tuple[str, str, int]]) -> str:
    canonical = [[name, digest, size] for name, digest, size in sorted(rows)]
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _validate_snapshot_tree(
    snapshot: Path,
    expected_files: set[str],
    expected_directories: set[str],
    file_evidence: dict[str, tuple[str, int]],
) -> None:
    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    for current, directory_names, file_names in os.walk(snapshot, followlinks=False):
        current_path = Path(current)
        for name in directory_names:
            candidate = current_path / name
            if candidate.is_symlink():
                _die(f"secure dependency snapshot contains a symlink directory: {name}")
            actual_directories.add(candidate.relative_to(snapshot).as_posix())
        for name in file_names:
            candidate = current_path / name
            if candidate.is_symlink() or not candidate.is_file():
                _die(f"secure dependency snapshot contains a non-regular file: {name}")
            actual_files.add(candidate.relative_to(snapshot).as_posix())
    if actual_files != expected_files:
        _die("secure dependency snapshot file census does not match its manifest")
    if actual_directories != expected_directories:
        _die("secure dependency snapshot directory census does not match its manifest")
    for relative, (expected_digest, expected_size) in sorted(file_evidence.items()):
        path = snapshot / PurePosixPath(relative)
        try:
            data = path.read_bytes()
        except OSError as exc:
            _die(f"secure dependency snapshot file cannot be read: {relative}: {exc}")
        if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_digest:
            _die(f"secure dependency snapshot file digest mismatch: {relative}")


def _validate_snapshot(
    snapshot: Path,
    manifest_sha256: Any,
    lock: dict[str, Any],
    lock_sha256: str,
    key: str,
) -> None:
    manifest_path = snapshot / SNAPSHOT_MANIFEST_NAME
    if manifest_path.is_symlink() or not manifest_path.is_file():
        _die("secure dependency snapshot manifest is missing or non-regular")
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        _die(f"secure dependency snapshot manifest is unavailable: {exc}")
    expected_manifest_digest = _parse_sha256(
        manifest_sha256, "secure dependency snapshot manifest digest"
    )
    if hashlib.sha256(manifest_bytes).hexdigest() != expected_manifest_digest:
        _die("secure dependency snapshot manifest digest mismatch")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        _die(f"secure dependency snapshot manifest is invalid: {exc}")
    required_manifest_keys = {
        "schema_version",
        "kind",
        "hash_algorithm",
        "platform_key",
        "dependency_lock_sha256",
        "distributions",
    }
    if (
        not isinstance(manifest, dict)
        or set(manifest) != required_manifest_keys
        or manifest.get("schema_version") != 1
        or manifest.get("kind") != "org-wechat-dependency-snapshot"
        or manifest.get("hash_algorithm") != "sha256"
        or manifest.get("platform_key") != key
        or manifest.get("dependency_lock_sha256") != lock_sha256
        or not isinstance(manifest.get("distributions"), dict)
    ):
        _die("secure dependency snapshot manifest schema is invalid")
    platforms = lock.get("platforms")
    selected = platforms.get(key) if isinstance(platforms, dict) else None
    expected_distributions = (
        selected.get("distributions") if isinstance(selected, dict) else None
    )
    if not isinstance(expected_distributions, dict):
        _die(f"secure dependency lock has no platform entry for {key}")
    manifest_distributions = manifest["distributions"]
    if set(manifest_distributions) != set(expected_distributions):
        _die("secure dependency snapshot distribution census is invalid")

    file_evidence: dict[str, tuple[str, int]] = {}
    expected_directories: set[str] = set()
    for name, expected in sorted(expected_distributions.items()):
        actual = manifest_distributions.get(name)
        if (
            not isinstance(expected, dict)
            or not isinstance(actual, dict)
            or set(actual) != {"version", "files"}
            or actual.get("version") != expected.get("version")
            or not isinstance(actual.get("files"), list)
        ):
            _die(f"secure dependency snapshot metadata is invalid for {name}")
        rows: list[tuple[str, str, int]] = []
        for item in actual["files"]:
            if (
                not isinstance(item, dict)
                or set(item) != {"path", "sha256", "size"}
                or not isinstance(item.get("path"), str)
                or not isinstance(item.get("size"), int)
                or isinstance(item.get("size"), bool)
                or item["size"] < 0
            ):
                _die(f"secure dependency snapshot file evidence is invalid for {name}")
            relative = PurePosixPath(item["path"])
            if (
                not item["path"]
                or relative.is_absolute()
                or ".." in relative.parts
                or relative.as_posix() != item["path"]
                or item["path"] == SNAPSHOT_MANIFEST_NAME
            ):
                _die(f"secure dependency snapshot path is unsafe for {name}")
            digest = _parse_sha256(item["sha256"], f"snapshot digest for {item['path']}")
            if item["path"] in file_evidence:
                _die(f"secure dependency snapshot distributions overlap at {item['path']}")
            file_evidence[item["path"]] = (digest, item["size"])
            rows.append((item["path"], digest, item["size"]))
            parent = relative.parent
            while parent != PurePosixPath("."):
                expected_directories.add(parent.as_posix())
                parent = parent.parent
        if len(rows) != expected.get("file_count"):
            _die(f"secure dependency snapshot file count is invalid for {name}")
        if _rows_digest(rows) != expected.get("aggregate_sha256"):
            _die(f"secure dependency snapshot aggregate digest is invalid for {name}")

    expected_files = set(file_evidence)
    expected_files.add(SNAPSHOT_MANIFEST_NAME)
    _validate_snapshot_tree(
        snapshot,
        expected_files,
        expected_directories,
        file_evidence,
    )


def require_secure_runtime(expected_entrypoint: str) -> None:
    """Require one exact secure-runner entrypoint binding."""

    require_secure_runtime_any((expected_entrypoint,))


def require_secure_runtime_any(expected_entrypoints: Collection[str]) -> str:
    """Refuse execution outside one of the named secure-runner bindings.

    Besides checking isolation and path ordering, this independently verifies
    the runner-created snapshot manifest, its exact file/directory census, and
    every dependency byte against the tracked platform lock before a sensitive
    entrypoint may import third-party code.
    """

    allowed_bindings = frozenset(expected_entrypoints)
    if not allowed_bindings or any(
        not isinstance(item, str) or not item for item in allowed_bindings
    ):
        _die("secure runtime expected entrypoint set is invalid")
    if not sys.flags.isolated or not sys.flags.no_site:
        _die(
            "security-sensitive CLI requires: python3 -I -S scripts/secure_runner.py TARGET ..."
        )
    marker = getattr(sys, MARKER_NAME, None)
    if not isinstance(marker, dict):
        _die("secure runtime marker is missing; invoke scripts/secure_runner.py")
    required = {
        "schema_version",
        "entrypoint",
        "workspace_root",
        "scripts_root",
        "dependency_snapshot",
        "dependency_lock_sha256",
        "snapshot_manifest_sha256",
        "platform_key",
        "base_sys_path",
    }
    if set(marker) != required or marker.get("schema_version") != 1:
        _die("secure runtime marker schema is invalid")
    bound_entrypoint = marker.get("entrypoint")
    if bound_entrypoint not in allowed_bindings:
        _die("secure runtime marker is bound to another entrypoint")
    if marker.get("platform_key") != _platform_key():
        _die("secure runtime marker is bound to another platform/Python")

    raw_workspace_root = Path(str(marker["workspace_root"]))
    raw_scripts_root = Path(str(marker["scripts_root"]))
    raw_snapshot = Path(str(marker["dependency_snapshot"]))
    if raw_workspace_root.is_symlink() or raw_scripts_root.is_symlink() or raw_snapshot.is_symlink():
        _die("secure runtime roots must not be symlinks")
    workspace_root = raw_workspace_root.resolve()
    scripts_root = raw_scripts_root.resolve()
    dependency_snapshot = raw_snapshot.resolve()
    if (
        scripts_root != workspace_root / "scripts"
        or not scripts_root.is_dir()
        or not dependency_snapshot.is_dir()
    ):
        _die("secure runtime roots are invalid")

    lock_path = workspace_root / "runtime" / "python-dependency-lock.json"
    try:
        lock_bytes = lock_path.read_bytes()
        lock_sha = "sha256:" + hashlib.sha256(lock_bytes).hexdigest()
    except OSError as exc:
        _die(f"secure dependency lock is unavailable: {exc}")
    if lock_sha != marker.get("dependency_lock_sha256"):
        _die("secure dependency lock changed after runner validation")
    try:
        lock = json.loads(lock_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        _die(f"secure dependency lock cannot be read: {exc}")
    if (
        not isinstance(lock, dict)
        or lock.get("schema_version") != 1
        or lock.get("kind") != "org-wechat-python-dependency-lock"
        or lock.get("hash_algorithm") != "distribution-files-sha256-v1"
    ):
        _die("secure dependency lock schema is invalid")
    if bound_entrypoint not in lock.get("allowed_entrypoints", []):
        _die("entrypoint is absent from the secure dependency lock")
    _validate_scripts_census(lock, scripts_root)

    base_sys_path = marker.get("base_sys_path")
    if (
        not isinstance(base_sys_path, list)
        or any(not isinstance(item, str) or not item for item in base_sys_path)
    ):
        _die("secure runtime base sys.path evidence is invalid")
    expected_path = [str(dependency_snapshot), *base_sys_path, str(scripts_root)]
    if sys.path != expected_path:
        _die("secure runtime sys.path contains an unverified import root")
    if not sys.dont_write_bytecode:
        _die("secure runtime must disable dependency snapshot bytecode writes")
    _validate_snapshot(
        dependency_snapshot,
        marker.get("snapshot_manifest_sha256"),
        lock,
        lock_sha,
        str(marker["platform_key"]),
    )
    return str(bound_entrypoint)

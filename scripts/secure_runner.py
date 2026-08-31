#!/usr/bin/env python3
"""Run a locked workflow CLI with isolated Python and copied dependencies.

Invoke only as::

    python3 -I -S scripts/secure_runner.py scripts/ENTRYPOINT.py [args...]

The runner itself uses only the standard library.  It discovers candidate
Pillow/cryptography distributions without importing them, validates their
complete executable file set against the tracked platform lock, copies the
validated bytes into a fresh private snapshot, and exposes only that snapshot
plus this repository's scripts to the target process.
"""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.metadata
import json
import os
import platform
import runpy
import shutil
import site
import sys
import sysconfig
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_ROOT = WORKSPACE_ROOT / "scripts"
LOCK_PATH = WORKSPACE_ROOT / "runtime" / "python-dependency-lock.json"
MARKER_NAME = "_org_wechat_secure_runtime_v1"
SNAPSHOT_MANIFEST_NAME = ".org-wechat-dependency-snapshot-v1.json"


def fail(message: str) -> "NoReturn":  # type: ignore[name-defined]
    raise SystemExit(f"secure-runner: {message}")


def platform_key() -> str:
    return "-".join(
        (
            platform.system().lower(),
            platform.machine().lower(),
            sys.implementation.cache_tag or "unknown-python",
        )
    )


def load_lock() -> tuple[dict[str, Any], str]:
    try:
        raw = LOCK_PATH.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"dependency lock is unavailable or invalid: {exc}")
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or payload.get("kind") != "org-wechat-python-dependency-lock"
        or payload.get("hash_algorithm") != "distribution-files-sha256-v1"
    ):
        fail("dependency lock schema is invalid")
    return payload, "sha256:" + hashlib.sha256(raw).hexdigest()


def script_importable_entries(root: Path) -> list[dict[str, str]]:
    """Return every top-level entry Python could resolve from ``root``.

    The scripts directory has to remain on ``sys.path`` for the workflow's
    local modules.  Keeping a complete lock census prevents a newly dropped
    ``PIL.py``/``cryptography`` package (or a sourceless/extension module) from
    silently joining that import root.
    """

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
        fail(f"scripts import root is unavailable: {exc}")
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
                fail(f"scripts importable entry is a symlink: {name}")
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


def validate_scripts_census(lock: dict[str, Any]) -> None:
    census = lock.get("scripts_importable_census")
    if (
        not isinstance(census, dict)
        or set(census) != {"algorithm", "entries"}
        or census.get("algorithm") != "top-level-python-importables-v1"
        or not isinstance(census.get("entries"), list)
    ):
        fail("scripts importable census schema is invalid")
    expected = census["entries"]
    for item in expected:
        if (
            not isinstance(item, dict)
            or set(item) != {"kind", "path"}
            or item.get("kind") not in {"source", "bytecode", "extension", "directory"}
            or not isinstance(item.get("path"), str)
            or Path(item["path"]).name != item["path"]
        ):
            fail("scripts importable census entry is invalid")
    actual = script_importable_entries(SCRIPTS_ROOT)
    if actual != expected:
        expected_tokens = {f"{item['kind']}:{item['path']}" for item in expected}
        actual_tokens = {f"{item['kind']}:{item['path']}" for item in actual}
        added = sorted(actual_tokens - expected_tokens)
        missing = sorted(expected_tokens - actual_tokens)
        details: list[str] = []
        if added:
            details.append("unexpected=" + ",".join(added))
        if missing:
            details.append("missing=" + ",".join(missing))
        fail("scripts importable census mismatch" + (": " + "; ".join(details) if details else ""))


def candidate_roots() -> list[Path]:
    values: list[str] = []
    configured = os.environ.get("ORG_WECHAT_DEPENDENCY_ROOT")
    if configured:
        values.append(configured)
    try:
        user_site = site.getusersitepackages()
        if isinstance(user_site, str):
            values.append(user_site)
    except (AttributeError, OSError):
        pass
    try:
        values.extend(site.getsitepackages())
    except (AttributeError, OSError):
        pass
    values.extend(
        value
        for value in sysconfig.get_paths().values()
        if isinstance(value, str) and value.endswith("site-packages")
    )
    roots: list[Path] = []
    seen: set[Path] = set()
    for value in values:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            continue
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_dir() and resolved not in seen:
            seen.add(resolved)
            roots.append(resolved)
    return roots


def distribution_rows(
    distribution: importlib.metadata.Distribution,
    root: Path,
) -> list[tuple[str, str, int, Path]]:
    rows: list[tuple[str, str, int, Path]] = []
    for item in distribution.files or ():
        relative = PurePosixPath(str(item))
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "__pycache__" in relative.parts
            or str(relative).endswith(".pyc")
        ):
            continue
        source = Path(distribution.locate_file(item))
        if source.is_symlink():
            fail(f"locked distribution file is a symlink: {relative}")
        try:
            resolved = source.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError):
            fail(f"locked distribution file escapes its site root: {relative}")
        if not resolved.is_file():
            fail(f"locked distribution file is not regular: {relative}")
        data = resolved.read_bytes()
        rows.append((str(relative), hashlib.sha256(data).hexdigest(), len(data), resolved))
    rows.sort(key=lambda row: row[0])
    return rows


def rows_digest(rows: list[tuple[str, str, int, Path]]) -> str:
    canonical = [[name, digest, size] for name, digest, size, _ in rows]
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def find_locked_distribution(
    name: str,
    expected: dict[str, Any],
    roots: list[Path],
) -> tuple[Path, list[tuple[str, str, int, Path]]]:
    matches: list[tuple[Path, list[tuple[str, str, int, Path]]]] = []
    normalized = name.lower().replace("-", "_")
    for root in roots:
        for distribution in importlib.metadata.distributions(path=[str(root)]):
            actual_name = str(distribution.metadata.get("Name", "")).lower().replace("-", "_")
            if actual_name != normalized or distribution.version != expected.get("version"):
                continue
            rows = distribution_rows(distribution, root)
            if (
                len(rows) == expected.get("file_count")
                and rows_digest(rows) == expected.get("aggregate_sha256")
            ):
                matches.append((root, rows))
    if len(matches) != 1:
        fail(
            f"{name} must resolve to exactly one locked distribution for {platform_key()}; "
            f"found {len(matches)}"
        )
    return matches[0]


def copy_snapshot(
    snapshot: Path,
    distributions: dict[str, dict[str, Any]],
    key: str,
    lock_sha: str,
) -> str:
    roots = candidate_roots()
    if not roots:
        fail("no candidate dependency roots are available")
    all_rows: list[tuple[str, str, int, Path]] = []
    manifest_distributions: dict[str, dict[str, Any]] = {}
    for name, expected in sorted(distributions.items()):
        if not isinstance(expected, dict):
            fail(f"lock entry for {name} is invalid")
        _, rows = find_locked_distribution(name, expected, roots)
        all_rows.extend(rows)
        manifest_distributions[name] = {
            "version": expected.get("version"),
            "files": [
                {
                    "path": relative,
                    "sha256": "sha256:" + digest,
                    "size": size,
                }
                for relative, digest, size, _ in rows
            ],
        }
    seen: set[str] = set()
    for relative, digest, size, source in all_rows:
        if relative in seen:
            fail(f"locked distributions overlap at {relative}")
        seen.add(relative)
        destination = snapshot / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as reader, destination.open("xb") as writer:
            shutil.copyfileobj(reader, writer, length=1024 * 1024)
        copied = destination.read_bytes()
        if len(copied) != size or hashlib.sha256(copied).hexdigest() != digest:
            fail(f"dependency changed while copying: {relative}")
    manifest = {
        "schema_version": 1,
        "kind": "org-wechat-dependency-snapshot",
        "hash_algorithm": "sha256",
        "platform_key": key,
        "dependency_lock_sha256": lock_sha,
        "distributions": manifest_distributions,
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    manifest_path = snapshot / SNAPSHOT_MANIFEST_NAME
    with manifest_path.open("xb") as writer:
        writer.write(manifest_bytes)
    return "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()


def main() -> int:
    if not sys.flags.isolated or not sys.flags.no_site:
        fail("invoke with both -I and -S")
    if len(sys.argv) < 2:
        fail("target entrypoint is required")
    lock, lock_sha = load_lock()
    validate_scripts_census(lock)
    key = platform_key()
    platforms = lock.get("platforms")
    selected = platforms.get(key) if isinstance(platforms, dict) else None
    if not isinstance(selected, dict) or not isinstance(selected.get("distributions"), dict):
        fail(f"platform/Python combination is not locked: {key}")
    target = Path(sys.argv[1])
    if not target.is_absolute():
        target = WORKSPACE_ROOT / target
    try:
        resolved_target = target.resolve(strict=True)
        relative_target = resolved_target.relative_to(WORKSPACE_ROOT).as_posix()
    except (OSError, ValueError):
        fail("target must be a real file inside this workspace")
    if resolved_target.is_symlink() or not resolved_target.is_file():
        fail("target must be a regular non-symlink file")
    allowed = lock.get("allowed_entrypoints")
    if not isinstance(allowed, list) or relative_target not in allowed:
        fail("target is not an allowed secure entrypoint")

    base_sys_path = [item for item in sys.path if item and Path(item).resolve() != SCRIPTS_ROOT]
    with tempfile.TemporaryDirectory(prefix="org-wechat-dependencies-") as directory:
        snapshot = Path(directory).resolve()
        manifest_sha = copy_snapshot(
            snapshot,
            selected["distributions"],
            key,
            lock_sha,
        )
        # The locked dependency snapshot must win over the workspace scripts
        # root.  Otherwise an untracked scripts/PIL.py or scripts/cryptography/
        # could shadow the bytes that were just verified and copied.
        sys.path[:] = [str(snapshot), *base_sys_path, str(SCRIPTS_ROOT)]
        sys.dont_write_bytecode = True
        setattr(
            sys,
            MARKER_NAME,
            {
                "schema_version": 1,
                "entrypoint": relative_target,
                "workspace_root": str(WORKSPACE_ROOT),
                "scripts_root": str(SCRIPTS_ROOT),
                "dependency_snapshot": str(snapshot),
                "dependency_lock_sha256": lock_sha,
                "snapshot_manifest_sha256": manifest_sha,
                "platform_key": key,
                "base_sys_path": base_sys_path,
            },
        )
        sys.argv = [str(resolved_target), *sys.argv[2:]]
        runpy.run_path(str(resolved_target), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

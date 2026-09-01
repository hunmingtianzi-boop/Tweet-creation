#!/usr/bin/env python3
"""Build, verify, and atomically install the workflow Skill packages.

The repository contains authoring fixtures and organization data that must not
leak into a source-zero Skill installation.  This module therefore packages an
explicit allowlist, records every installed byte, and verifies the checked-in
release manifest before installation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_SCHEMA = "org-wechat-skill-release-v1"
INSTALLED_MANIFEST_DIRECTORY = ".org-wechat-release-manifests"
CLONE_READINESS_SCHEMA = "org-wechat-clone-readiness-v1"
SUPPORTED_EXECUTION_HOST = "codex-desktop"
SUPPORTED_PHASES = ("migration", "bootstrap", "authoring", "delivery", "full")
CODEX_WITH_CHATGPT_REPOSITORY = "https://github.com/XiaoDuoYa/codex-with-chatgpt"
PACKAGE_SOURCES = {
    "org-wechat-studio": Path("."),
    "chatgpt-web-image-route": Path("skills/chatgpt-web-image-route"),
    "ardot-wechat-publisher": Path("skills/ardot-wechat-publisher"),
}
ORG_ROOT_FILES = {
    ".gitignore",
    "README.md",
    "SKILL.md",
    "requirements.txt",
}
ORG_ROOT_DIRS = {
    "agents",
    "references",
    "runtime",
    "scripts",
    "style-presets",
    "tests",
}
WRAPPER_ROOT_FILES = {"SKILL.md"}
WRAPPER_ROOT_DIRS = {"agents", "references"}
FORBIDDEN_PARTS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "examples",
    "experiments",
    "organizations",
    "output",
}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo", ".swp", ".tmp"}


class ReleaseError(RuntimeError):
    """Raised when a package cannot be proven safe and reproducible."""


_PLATFORM_PATH_ALIASES = {
    Path("/var"): Path("/private/var"),
    Path("/tmp"): Path("/private/tmp"),
    Path("/etc"): Path("/private/etc"),
}


def _release_absolute_path(path: Path, *, label: str) -> Path:
    """Resolve one release path only after inspecting its lexical ancestry."""

    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    lexical = Path(os.path.abspath(os.fspath(expanded)))
    cursor = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        cursor /= part
        if not os.path.lexists(cursor):
            continue
        metadata = cursor.lstat()
        if not stat.S_ISLNK(metadata.st_mode):
            continue
        allowed = _PLATFORM_PATH_ALIASES.get(cursor)
        if allowed is not None and cursor.resolve(strict=True) == allowed:
            continue
        raise ReleaseError(f"{label} must not traverse a symlink: {cursor}")
    return lexical.resolve(strict=False)


def _release_existing_file(path: Path, *, label: str) -> Path:
    candidate = _release_absolute_path(path, label=label)
    try:
        metadata = candidate.lstat()
    except OSError as exc:
        raise ReleaseError(f"{label} is unavailable: {candidate}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise ReleaseError(f"{label} must be a regular non-symlink file")
    return candidate


def _release_existing_directory(path: Path, *, label: str) -> Path:
    candidate = _release_absolute_path(path, label=label)
    try:
        metadata = candidate.lstat()
    except OSError as exc:
        raise ReleaseError(f"{label} is unavailable: {candidate}") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise ReleaseError(f"{label} must be an existing non-symlink directory")
    return candidate


def _release_new_file(path: Path, *, label: str) -> Path:
    candidate = _release_absolute_path(path, label=label)
    if os.path.lexists(candidate):
        raise ReleaseError(f"{label} already exists; replacement is forbidden")
    parent = _release_existing_directory(candidate.parent, label=f"{label} parent")
    return parent / candidate.name


def _release_new_directory(path: Path, *, label: str) -> Path:
    candidate = _release_absolute_path(path, label=label)
    if os.path.lexists(candidate):
        raise ReleaseError(f"{label} must be new and absent: {candidate}")
    parent = _release_existing_directory(candidate.parent, label=f"{label} parent")
    return parent / candidate.name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_regular_file(path: Path) -> None:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ReleaseError(f"package input must be a regular non-symlink file: {path}")


def _assert_canonical_existing_path_without_symlinks(
    path: Path,
    *,
    label: str,
    directory: bool,
) -> Path:
    """Require an absolute canonical path whose full ancestry has no symlink.

    Installed-release verification is intentionally stricter than ordinary
    source verification.  Resolving a caller-supplied path before checking it
    would hide a symlinked parent, so compare the supplied absolute spelling
    with the strict canonical result and also inspect every existing component.
    """

    expanded = path.expanduser()
    if not expanded.is_absolute():
        raise ReleaseError(f"{label} must be an absolute canonical path: {expanded}")
    try:
        canonical = expanded.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ReleaseError(f"{label} does not exist or cannot be resolved: {expanded}") from exc
    if expanded != canonical:
        raise ReleaseError(
            f"{label} must not use symlinks or a non-canonical path: {expanded}"
        )

    current = Path(expanded.anchor)
    for part in expanded.parts[1:]:
        current = current / part
        try:
            metadata = current.lstat()
        except OSError as exc:  # pragma: no cover - strict resolve handled this
            raise ReleaseError(f"{label} path component is unavailable: {current}") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ReleaseError(f"{label} path component must not be a symlink: {current}")

    metadata = expanded.lstat()
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(metadata.st_mode):
        expected = "directory" if directory else "regular file"
        raise ReleaseError(f"{label} must be a {expected}: {expanded}")
    return expanded


def _read_installed_manifest(
    skills_root: Path,
    manifest_path: Path,
) -> tuple[Path, Path, dict[str, object]]:
    """Read only the create-once manifest stored beside installed Skills.

    This establishes a local location and byte-census binding.  It deliberately
    does not claim that the manifest is signed or host-attested.
    """

    canonical_skills_root = _assert_canonical_existing_path_without_symlinks(
        skills_root,
        label="skills root",
        directory=True,
    )
    manifest_store = _assert_canonical_existing_path_without_symlinks(
        canonical_skills_root / INSTALLED_MANIFEST_DIRECTORY,
        label="installed manifest store",
        directory=True,
    )
    canonical_manifest = _assert_canonical_existing_path_without_symlinks(
        manifest_path,
        label="installed release manifest",
        directory=False,
    )
    if canonical_manifest.parent != manifest_store:
        raise ReleaseError(
            "installed release manifest must be located directly in "
            f"{manifest_store}: {canonical_manifest}"
        )
    payload = _validate_manifest_payload(_read_manifest(canonical_manifest))
    expected_name = f"{payload['release_sha256']}.json"
    if canonical_manifest.name != expected_name:
        raise ReleaseError(
            "installed release manifest filename must equal its internal "
            f"release_sha256: expected={expected_name} actual={canonical_manifest.name}"
        )
    return canonical_skills_root, canonical_manifest, payload


def _allowed_top_level(package: str) -> tuple[set[str], set[str]]:
    if package == "org-wechat-studio":
        return ORG_ROOT_FILES, ORG_ROOT_DIRS
    return WRAPPER_ROOT_FILES, WRAPPER_ROOT_DIRS


def collect_package_files(
    package: str, workspace_root: Path = WORKSPACE_ROOT
) -> list[tuple[Path, Path]]:
    """Return ``(source, package-relative)`` files in deterministic order."""

    if package not in PACKAGE_SOURCES:
        raise ReleaseError(f"unknown package: {package}")
    source_root = (workspace_root / PACKAGE_SOURCES[package]).resolve()
    if not source_root.is_dir():
        raise ReleaseError(f"package source is missing: {source_root}")
    allowed_files, allowed_dirs = _allowed_top_level(package)
    collected: list[tuple[Path, Path]] = []
    for candidate in sorted(source_root.rglob("*"), key=lambda item: item.as_posix()):
        relative = candidate.relative_to(source_root)
        if not relative.parts:
            continue
        if any(part in FORBIDDEN_PARTS for part in relative.parts):
            continue
        if candidate.is_dir():
            continue
        if relative.parts[0] not in allowed_files | allowed_dirs:
            continue
        if len(relative.parts) == 1 and relative.name not in allowed_files:
            continue
        if candidate.suffix.lower() in FORBIDDEN_SUFFIXES:
            continue
        _assert_regular_file(candidate)
        collected.append((candidate, relative))
    if not any(relative == Path("SKILL.md") for _, relative in collected):
        raise ReleaseError(f"{package} package has no SKILL.md")
    return collected


def _package_manifest(package: str, workspace_root: Path) -> dict[str, object]:
    records: list[dict[str, object]] = []
    aggregate = hashlib.sha256()
    for source, relative in collect_package_files(package, workspace_root):
        file_digest = _sha256(source)
        byte_length = source.stat().st_size
        record = {
            "path": relative.as_posix(),
            "sha256": file_digest,
            "byte_length": byte_length,
        }
        records.append(record)
        aggregate.update(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        aggregate.update(b"\n")
    return {
        "package": package,
        "source": PACKAGE_SOURCES[package].as_posix(),
        "bundle_sha256": aggregate.hexdigest(),
        "file_count": len(records),
        "files": records,
    }


def build_manifest(workspace_root: Path = WORKSPACE_ROOT) -> dict[str, object]:
    packages = [
        _package_manifest(package, workspace_root)
        for package in sorted(PACKAGE_SOURCES)
    ]
    release_digest = hashlib.sha256(
        json.dumps(packages, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return {
        "schema": MANIFEST_SCHEMA,
        "release_sha256": release_digest,
        "packages": packages,
    }


def _read_manifest(path: Path) -> dict[str, object]:
    path = _release_existing_file(path, label="release manifest")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"cannot read release manifest {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != MANIFEST_SCHEMA:
        raise ReleaseError(f"unsupported release manifest: {path}")
    return payload


def _validate_manifest_payload(payload: dict[str, object]) -> dict[str, object]:
    """Validate a release manifest without consulting a source checkout.

    Installed runtimes intentionally do not contain the wrapper source trees.
    Their trust anchor is therefore the create-once release manifest plus an
    exact byte census of all three sibling packages, not a reconstruction from
    files that cannot exist inside ``org-wechat-studio``.
    """

    packages = payload.get("packages")
    if not isinstance(packages, list):
        raise ReleaseError("release manifest packages must be a list")
    expected_names = set(PACKAGE_SOURCES)
    seen_names: set[str] = set()
    normalized: list[dict[str, object]] = []
    sha256_pattern = re.compile(r"^[0-9a-f]{64}$")
    for package in packages:
        if not isinstance(package, dict):
            raise ReleaseError("release manifest package entry must be an object")
        name = package.get("package")
        source = package.get("source")
        files = package.get("files")
        if (
            not isinstance(name, str)
            or name not in expected_names
            or name in seen_names
            or source != PACKAGE_SOURCES[name].as_posix()
            or not isinstance(files, list)
        ):
            raise ReleaseError("release manifest package identity is invalid")
        seen_names.add(name)
        seen_paths: set[str] = set()
        aggregate = hashlib.sha256()
        for record in files:
            if not isinstance(record, dict):
                raise ReleaseError(f"release manifest file entry is invalid: {name}")
            relative = record.get("path")
            digest = record.get("sha256")
            byte_length = record.get("byte_length")
            relative_path = Path(relative) if isinstance(relative, str) else Path(".")
            if (
                not isinstance(relative, str)
                or not relative
                or relative in seen_paths
                or relative_path.is_absolute()
                or ".." in relative_path.parts
                or any(part in FORBIDDEN_PARTS for part in relative_path.parts)
                or not isinstance(digest, str)
                or not sha256_pattern.fullmatch(digest)
                or not isinstance(byte_length, int)
                or isinstance(byte_length, bool)
                or byte_length < 0
                or set(record) != {"path", "sha256", "byte_length"}
            ):
                raise ReleaseError(f"release manifest file record is invalid: {name}")
            seen_paths.add(relative)
            aggregate.update(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            aggregate.update(b"\n")
        if "SKILL.md" not in seen_paths:
            raise ReleaseError(f"release manifest package has no SKILL.md: {name}")
        if (
            package.get("file_count") != len(files)
            or package.get("bundle_sha256") != aggregate.hexdigest()
            or set(package)
            != {"package", "source", "bundle_sha256", "file_count", "files"}
        ):
            raise ReleaseError(f"release manifest package digest is invalid: {name}")
        normalized.append(package)
    if seen_names != expected_names:
        raise ReleaseError("release manifest does not contain the exact Skill set")
    normalized.sort(key=lambda item: str(item["package"]))
    release_digest = hashlib.sha256(
        json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if (
        set(payload) != {"schema", "release_sha256", "packages"}
        or payload.get("release_sha256") != release_digest
    ):
        raise ReleaseError("release manifest aggregate digest is invalid")
    return payload


def verify_manifest(path: Path, workspace_root: Path = WORKSPACE_ROOT) -> dict[str, object]:
    expected = _validate_manifest_payload(_read_manifest(path))
    actual = build_manifest(workspace_root)
    if expected != actual:
        expected_digest = expected.get("release_sha256", "missing")
        actual_digest = actual.get("release_sha256", "missing")
        raise ReleaseError(
            "release manifest does not match repository bytes: "
            f"expected={expected_digest} actual={actual_digest}"
        )
    return actual


def write_manifest(path: Path, workspace_root: Path = WORKSPACE_ROOT) -> dict[str, object]:
    payload = build_manifest(workspace_root)
    try:
        if not os.path.lexists(path.parent):
            parent = _release_new_directory(
                path.parent, label="release manifest directory"
            )
            parent.mkdir(mode=0o755, parents=False, exist_ok=False)
        path = _release_new_file(path, label="release manifest")
    except OSError as exc:
        raise ReleaseError(str(exc)) from exc
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    with path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return payload


def _copy_package(package: str, destination: Path, workspace_root: Path) -> None:
    package_root = destination / package
    package_root.mkdir(parents=True, exist_ok=False)
    for source, relative in collect_package_files(package, workspace_root):
        output = package_root / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as reader, output.open("xb") as writer:
            shutil.copyfileobj(reader, writer)
        shutil.copymode(source, output, follow_symlinks=False)


def stage_packages(destination: Path, workspace_root: Path = WORKSPACE_ROOT) -> dict[str, object]:
    try:
        destination = _release_new_directory(
            destination, label="release staging destination"
        )
        destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    except OSError as exc:
        raise ReleaseError(str(exc)) from exc
    for package in sorted(PACKAGE_SOURCES):
        _copy_package(package, destination, workspace_root)
    manifest = build_manifest(workspace_root)
    (destination / "release-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _manifest_for_directory(package: str, root: Path) -> dict[str, object]:
    temporary_sources = dict(PACKAGE_SOURCES)
    try:
        PACKAGE_SOURCES[package] = Path(package)
        result = _package_manifest(package, root)
        result["source"] = temporary_sources[package].as_posix()
        return result
    finally:
        PACKAGE_SOURCES.clear()
        PACKAGE_SOURCES.update(temporary_sources)


def install_packages(
    skills_root: Path,
    manifest_path: Path,
    workspace_root: Path = WORKSPACE_ROOT,
) -> dict[str, object]:
    """Atomically install verified packages and preserve timestamped backups."""

    try:
        manifest_path = _release_existing_file(
            manifest_path, label="release manifest"
        )
    except ReleaseError as exc:
        raise ReleaseError(str(exc)) from exc
    manifest = verify_manifest(manifest_path, workspace_root)
    try:
        if os.path.lexists(skills_root):
            skills_root = _release_existing_directory(skills_root, label="skills root")
        else:
            skills_root = _release_new_directory(skills_root, label="skills root")
            skills_root.mkdir(mode=0o755, parents=False, exist_ok=False)
    except OSError as exc:
        raise ReleaseError(str(exc)) from exc
    with tempfile.TemporaryDirectory(prefix="org-wechat-skill-stage-") as temporary:
        stage_root = Path(temporary) / "packages"
        stage_packages(stage_root, workspace_root)
        expected_by_name = {
            str(item["package"]): item for item in manifest["packages"]  # type: ignore[index]
        }
        for package in sorted(PACKAGE_SOURCES):
            staged_manifest = _manifest_for_directory(package, stage_root)
            if staged_manifest != expected_by_name[package]:
                raise ReleaseError(f"staged package differs before install: {package}")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        transaction_id = uuid.uuid4().hex[:12]
        installed: list[dict[str, str]] = []
        targets: dict[str, Path] = {}
        incomings: dict[str, Path] = {}
        backups: dict[str, Path | None] = {}
        moved_backups: list[str] = []
        moved_incomings: list[str] = []

        # Resolve every active target and backup name before copying or moving
        # a single Skill.
        for package in sorted(PACKAGE_SOURCES):
            target = skills_root / package
            incoming = skills_root / (
                f".{package}.incoming-{stamp}-{os.getpid()}-{transaction_id}"
            )
            if incoming.exists() or incoming.is_symlink():
                raise ReleaseError(f"incoming install path already exists: {incoming}")
            targets[package] = target
            incomings[package] = incoming
            backup: Path | None = None
            if target.exists() or target.is_symlink():
                if target.is_symlink() or not target.is_dir():
                    raise ReleaseError(f"installed target is not a regular directory: {target}")
                backup = skills_root / (
                    f".{package}.backup-{stamp}-{transaction_id}"
                )
                if backup.exists() or backup.is_symlink():
                    raise ReleaseError(f"backup path already exists: {backup}")
            backups[package] = backup

        manifest_store = skills_root / INSTALLED_MANIFEST_DIRECTORY
        if manifest_store.is_symlink():
            raise ReleaseError(
                f"installed manifest store must not be a symlink: {manifest_store}"
            )
        manifest_store.mkdir(mode=0o755, parents=True, exist_ok=True)
        release_digest = str(manifest["release_sha256"])
        installed_manifest = manifest_store / f"{release_digest}.json"
        source_manifest_bytes = manifest_path.read_bytes()
        manifest_already_present = False
        if installed_manifest.exists() or installed_manifest.is_symlink():
            _assert_regular_file(installed_manifest)
            if installed_manifest.read_bytes() != source_manifest_bytes:
                raise ReleaseError(
                    f"installed release manifest collision: {installed_manifest}"
                )
            manifest_already_present = True

        # Prepare every replacement inside the destination filesystem before
        # moving a single active Skill.  This makes each directory swap atomic
        # and lets the whole release roll back if any later swap fails.
        try:
            for package in sorted(PACKAGE_SOURCES):
                shutil.copytree(
                    stage_root / package,
                    incomings[package],
                    symlinks=False,
                )
        except Exception:
            for incoming in incomings.values():
                if incoming.is_dir() and not incoming.is_symlink():
                    shutil.rmtree(incoming)
            raise

        try:
            for package in sorted(PACKAGE_SOURCES):
                target = targets[package]
                backup = backups[package]
                if backup is not None:
                    os.replace(target, backup)
                    moved_backups.append(package)

            for package in sorted(PACKAGE_SOURCES):
                target = targets[package]
                incoming = incomings[package]
                os.replace(incoming, target)
                moved_incomings.append(package)

            # Verify the active bytes before publishing the installed release
            # manifest that build-census will trust.
            for package in sorted(PACKAGE_SOURCES):
                active_manifest = _manifest_for_directory(package, skills_root)
                if active_manifest != expected_by_name[package]:
                    raise ReleaseError(
                        f"installed package differs after atomic swap: {package}"
                    )

            if not manifest_already_present:
                with installed_manifest.open("xb") as handle:
                    handle.write(source_manifest_bytes)
                    handle.flush()
                    os.fsync(handle.fileno())
        except Exception:
            # Move this transaction's new trees out of the active names first,
            # then restore every prior Skill.  All paths are exact validated
            # package targets under skills_root.
            for package in reversed(moved_incomings):
                target = targets[package]
                incoming = incomings[package]
                if target.is_dir() and not target.is_symlink() and not incoming.exists():
                    os.replace(target, incoming)
            for package in reversed(moved_backups):
                target = targets[package]
                backup = backups[package]
                if backup is not None and backup.is_dir() and not target.exists():
                    os.replace(backup, target)
            if not manifest_already_present and installed_manifest.is_file():
                installed_manifest.unlink()
            for incoming in incomings.values():
                if incoming.is_dir() and not incoming.is_symlink():
                    shutil.rmtree(incoming)
            raise

        for package in sorted(PACKAGE_SOURCES):
            target = targets[package]
            backup = backups[package]
            try:
                target.relative_to(skills_root)
            except ValueError as exc:  # pragma: no cover - defensive invariant
                raise ReleaseError("installed target escaped skills root") from exc
            installed.append(
                {
                    "package": package,
                    "path": str(target),
                    "backup": str(backup) if backup is not None else "",
                }
            )
    return {
        "ok": True,
        "release_sha256": release_digest,
        "installed_manifest": str(installed_manifest),
        "installed": installed,
    }


def verify_installed_packages(
    skills_root: Path,
    manifest_path: Path,
    workspace_root: Path = WORKSPACE_ROOT,
    *,
    verify_workspace_source: bool = True,
) -> dict[str, object]:
    """Verify that installed package bytes exactly match the release manifest.

    ``verify_workspace_source`` is used during release creation and install.
    Installed runtimes set it to false because their main package deliberately
    excludes the two wrapper source trees; the manifest is still validated
    internally and every installed byte in all three sibling packages is
    checked below.
    """

    if verify_workspace_source:
        # Release creation and install remain anchored to the source checkout:
        # the caller-supplied manifest must equal the repository bytes.
        manifest = verify_manifest(manifest_path, workspace_root)
        skills_root = skills_root.expanduser().resolve()
    else:
        # An installed runtime has no source checkout to compare against.  Only
        # accept the create-once manifest at the exact installed-store path;
        # accepting an externally supplied, internally self-consistent manifest
        # would let an attacker redefine both the expected package bytes and
        # their hashes.
        skills_root, manifest_path, manifest = _read_installed_manifest(
            skills_root,
            manifest_path,
        )
    expected_packages = {
        str(item["package"]): item for item in manifest["packages"]  # type: ignore[index]
    }
    verified: list[dict[str, object]] = []
    for package, expected in sorted(expected_packages.items()):
        package_root = skills_root / package
        _assert_canonical_existing_path_without_symlinks(
            package_root,
            label=f"installed package directory ({package})",
            directory=True,
        )
        actual_files: set[str] = set()
        for candidate in package_root.rglob("*"):
            relative = candidate.relative_to(package_root)
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise ReleaseError(
                    f"installed package path must not be a symlink: {candidate}"
                )
            if stat.S_ISDIR(metadata.st_mode):
                continue
            if "__pycache__" in relative.parts or candidate.suffix.lower() in {".pyc", ".pyo"}:
                continue
            _assert_regular_file(candidate)
            actual_files.add(relative.as_posix())
        expected_files = {str(item["path"]): item for item in expected["files"]}  # type: ignore[index]
        if actual_files != set(expected_files):
            missing = sorted(set(expected_files) - actual_files)
            unexpected = sorted(actual_files - set(expected_files))
            raise ReleaseError(
                f"installed package file census differs for {package}: "
                f"missing={missing} unexpected={unexpected}"
            )
        for relative, record in expected_files.items():
            path = package_root / relative
            if path.stat().st_size != record["byte_length"] or _sha256(path) != record["sha256"]:
                raise ReleaseError(f"installed package byte mismatch: {package}/{relative}")
        verified.append(
            {
                "package": package,
                "path": str(package_root),
                "bundle_sha256": expected["bundle_sha256"],
            }
        )
    return {
        "ok": True,
        "release_sha256": manifest["release_sha256"],
        "verified": verified,
    }


def _current_platform_key() -> str:
    return "-".join(
        (
            platform.system().lower(),
            platform.machine().lower(),
            sys.implementation.cache_tag or "unknown-python",
        )
    )


def _command_version(command: str) -> tuple[str | None, str | None]:
    executable = shutil.which(command)
    if executable is None:
        return None, None
    try:
        completed = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return executable, None
    version = (completed.stdout or completed.stderr).strip()
    return executable, version or None


def _major_version(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.search(r"(?:^|\s)v?(\d+)(?:\.|$)", value)
    return int(match.group(1)) if match else None


def _codex_with_chatgpt_checkout(skill_path: Path) -> Path | None:
    if not skill_path.is_file() or skill_path.is_symlink():
        return None
    try:
        text = skill_path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(
        r"The codex-with-chatgpt checkout lives at:\s*`?([^`\n]+?)`?\s*$",
        text,
        re.MULTILINE,
    )
    if not match:
        return None
    candidate = Path(match.group(1).strip()).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not resolved.is_dir():
        return None
    return resolved


def clone_readiness(
    skills_root: Path,
    *,
    phase: str = "full",
    workspace_root: Path = WORKSPACE_ROOT,
) -> dict[str, object]:
    """Declare clone-time requirements without pretending to prove live login.

    This check deliberately stops at local installation evidence.  ChatGPT,
    Ardot and WeChat readiness can only be closed by the current Codex Desktop
    registry and live page/provider probes after the repository is opened.
    """

    if phase not in SUPPORTED_PHASES:
        raise ReleaseError(f"unsupported readiness phase: {phase}")
    workspace_root = _release_existing_directory(
        workspace_root, label="source workspace root"
    )
    skills_root = _release_absolute_path(skills_root, label="skills root")
    setup_path = workspace_root / "runtime" / "setup-links.json"
    platform_path = workspace_root / "runtime" / "platform-support.json"
    manifest_path = workspace_root / "release" / "org-wechat-skills-v1.json"
    try:
        setup = json.loads(setup_path.read_text(encoding="utf-8"))
        support = json.loads(platform_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"cannot read clone prerequisite contracts: {exc}") from exc
    if not isinstance(setup, dict) or not isinstance(support, dict):
        raise ReleaseError("clone prerequisite contracts must be JSON objects")
    expected_support = {
        "execution_host": SUPPORTED_EXECUTION_HOST,
        "status": "supported-only-on-codex-desktop",
        "other_harnesses": "unsupported-until-a-reviewed-adapter-and-full-forward-test-are-released",
        "semantic_contract_portability_is_execution_support": False,
    }
    if setup.get("support") != expected_support:
        raise ReleaseError("setup support contract must declare Codex Desktop only")
    if support.get("supported_execution_hosts") != [SUPPORTED_EXECUTION_HOST]:
        raise ReleaseError("platform support matrix must declare Codex Desktop only")

    external = setup.get("external")
    if not isinstance(external, dict):
        raise ReleaseError("setup link registry has no external link map")
    links = {
        key: value.get("url")
        for key, value in external.items()
        if isinstance(value, dict) and isinstance(value.get("url"), str)
    }

    checks: list[dict[str, object]] = []

    def add_check(
        check_id: str,
        status: str,
        *,
        required: bool,
        scope: str,
        detail: str,
        action: str,
        url: str | None = None,
    ) -> None:
        item: dict[str, object] = {
            "id": check_id,
            "status": status,
            "required": required,
            "scope": scope,
            "detail": detail,
            "action": action,
        }
        if url:
            item["url"] = url
        checks.append(item)

    platform_key = _current_platform_key()
    supported_keys = {
        row.get("platform_key")
        for row in support.get("supported", [])
        if isinstance(row, dict) and row.get("status") == "locked"
    }
    platform_ok = platform_key in supported_keys
    add_check(
        "locked-platform",
        "passed" if platform_ok else "missing",
        required=True,
        scope="local",
        detail=(
            f"current={platform_key}; this release executes only reviewed locked rows"
        ),
        action=(
            "Continue with the installed workflow."
            if platform_ok
            else "Use Apple Silicon macOS with the reviewed bundled CPython 3.9 runtime; other platforms are contract-test-only."
        ),
    )

    manifest_ok = False
    release_sha = None
    try:
        manifest = verify_manifest(manifest_path, workspace_root)
        manifest_ok = True
        release_sha = str(manifest["release_sha256"])
    except ReleaseError as exc:
        manifest = None
        manifest_error = str(exc)
    add_check(
        "source-release-manifest",
        "passed" if manifest_ok else "missing",
        required=True,
        scope="local",
        detail=(
            f"verified release={release_sha}"
            if manifest_ok
            else f"release manifest is absent, stale or invalid: {manifest_error}"
        ),
        action=(
            "The checked-in release manifest matches the clone."
            if manifest_ok
            else "Verify or regenerate the checked-in release manifest before installation."
        ),
    )

    installed_ok = False
    installed_manifest = (
        skills_root / INSTALLED_MANIFEST_DIRECTORY / f"{release_sha}.json"
        if release_sha
        else None
    )
    if manifest_ok and installed_manifest is not None and installed_manifest.is_file():
        try:
            verify_installed_packages(
                skills_root,
                installed_manifest,
                workspace_root,
                verify_workspace_source=False,
            )
            installed_ok = True
        except ReleaseError:
            installed_ok = False
    install_command = " ".join(
        (
            "python3 -I -S",
            shlex.quote(str(workspace_root / "scripts" / "release_skills.py")),
            "install",
            shlex.quote(str(manifest_path)),
            "--skills-root",
            shlex.quote(str(skills_root)),
        )
    )
    add_check(
        "same-release-workflow-skills",
        "passed" if installed_ok else "missing",
        required=True,
        scope="local",
        detail="org-wechat-studio, chatgpt-web-image-route and ardot-wechat-publisher must be installed from one verified release",
        action=("Installed bytes match the source release." if installed_ok else install_command),
    )

    git_path, git_version = _command_version("git")
    add_check(
        "git",
        "passed" if git_path else "missing",
        required=True,
        scope="local",
        detail=git_version or "git was not found",
        action=(
            "Git is available."
            if git_path
            else "Install Git and reopen the cloned workspace in Codex Desktop."
        ),
    )

    c2c_required = phase in {"migration", "authoring", "full"}
    node_path, node_version = _command_version("node")
    node_ok = bool(node_path and (_major_version(node_version) or 0) >= 20)
    add_check(
        "node-20",
        "passed" if node_ok else ("missing" if c2c_required else "not-required"),
        required=c2c_required,
        scope="local",
        detail=node_version or "Node.js was not found",
        action=(
            "Node.js satisfies the C2C requirement."
            if node_ok
            else "Install Node.js 20 or newer for Codex with ChatGPT."
        ),
    )

    cloudflared_path, cloudflared_version = _command_version("cloudflared")
    add_check(
        "cloudflared",
        "passed"
        if cloudflared_path
        else ("missing" if c2c_required else "not-required"),
        required=c2c_required,
        scope="local",
        detail=cloudflared_version or "cloudflared was not found",
        action=(
            "cloudflared is available."
            if cloudflared_path
            else "Let the Codex with ChatGPT setup install cloudflared, or install it before pairing."
        ),
    )

    c2c_skill = skills_root / "codex-with-chatgpt" / "SKILL.md"
    c2c_checkout = _codex_with_chatgpt_checkout(c2c_skill)
    c2c_ok = bool(
        c2c_checkout
        and (c2c_checkout / "bin" / "c2c.js").is_file()
        and (c2c_checkout / "dist").is_dir()
    )
    add_check(
        "codex-with-chatgpt",
        "passed" if c2c_ok else ("missing" if c2c_required else "not-required"),
        required=c2c_required,
        scope="local",
        detail=(
            f"installed Skill and built checkout={c2c_checkout}"
            if c2c_ok
            else "this repository does not vendor Codex with ChatGPT; its Skill and built checkout are external prerequisites"
        ),
        action=(
            "The external Skill and built checkout are present; live workspace pairing still requires the current Codex session."
            if c2c_ok
            else "Install and configure Codex with ChatGPT for this exact cloned workspace."
        ),
        url=CODEX_WITH_CHATGPT_REPOSITORY,
    )

    add_check(
        "codex-desktop-session",
        "requires-live-probe",
        required=True,
        scope="host-session",
        detail="the repository cannot prove which harness loaded it from shell or files",
        action="Open this exact clone as a local task in Codex Desktop, reload the installed Skills, and run the runtime census.",
    )
    if c2c_required:
        add_check(
            "chatgpt-connection-and-login",
            "requires-live-probe",
            required=True,
            scope="host-session",
            detail="C2C doctor, connector/workspace identity, the single built-in Browser tab, and ChatGPT login must pass in this Codex session",
            action="Run the Codex with ChatGPT first-time/setup or doctor flow; complete login, CAPTCHA or 2FA only when the built-in Browser asks.",
            url=links.get("chatgpt_web"),
        )
        add_check(
            "codex-image-and-browser-tools",
            "requires-live-probe",
            required=True,
            scope="host-session",
            detail="image_gen__imagegen, view_image, browser:control-in-app-browser and its JavaScript runtime must be model-visible",
            action="Let runtime_preflight build the current-session census; a shell executable or generic JavaScript tool is not a substitute.",
        )

    ardot_required = phase in {"bootstrap", "authoring", "delivery", "full"}
    add_check(
        "ardot-login-and-target-access",
        "requires-live-probe" if ardot_required else "not-required",
        required=ardot_required,
        scope="host-session",
        detail="Ardot MCP OAuth/web login and permission for the exact file/root are session-specific and never travel with the clone",
        action="Connect ardot-remote in Codex, log in to Ardot, then prove create/read/write/export access to the exact target file and root.",
        url=links.get("ardot_web"),
    )

    wechat_required = phase in {"delivery", "full"}
    add_check(
        "wechat-account-session",
        "requires-live-probe" if wechat_required else "not-required",
        required=wechat_required,
        scope="host-session",
        detail="the exact Official Account login or API credentials and draft readback route are required only for delivery/full",
        action="Log in at the credential-free WeChat entry or provide execution-time API credentials; then bind and re-read the exact account before any draft write.",
        url=links.get("wechat_web"),
    )

    local_blockers = [
        str(item["id"])
        for item in checks
        if item["scope"] == "local"
        and item["required"] is True
        and item["status"] != "passed"
    ]
    live_pending = [
        str(item["id"])
        for item in checks
        if item["required"] is True and item["status"] == "requires-live-probe"
    ]
    return {
        "schema": CLONE_READINESS_SCHEMA,
        "support": expected_support,
        "phase": phase,
        "workspace_root": str(workspace_root),
        "skills_root": str(skills_root),
        "release_sha256": release_sha,
        "local_prerequisites_ready": not local_blockers,
        "live_session_ready": False,
        "ready_to_read_source_material": False,
        "local_blockers": local_blockers,
        "live_probes_required": live_pending,
        "checks": checks,
        "truth_boundary": "clone-check proves local files and binaries only; login, registry visibility, account identity, Ardot file/root access and WeChat state require current Codex Desktop live probes",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    write = subparsers.add_parser("write-manifest")
    write.add_argument("path", type=Path)
    verify = subparsers.add_parser("verify")
    verify.add_argument("path", type=Path)
    stage = subparsers.add_parser("stage")
    stage.add_argument("destination", type=Path)
    install = subparsers.add_parser("install")
    install.add_argument("manifest", type=Path)
    install.add_argument("--skills-root", type=Path, required=True)
    verify_installed = subparsers.add_parser("verify-installed")
    verify_installed.add_argument("manifest", type=Path)
    verify_installed.add_argument("--skills-root", type=Path, required=True)
    clone_check = subparsers.add_parser("clone-check")
    clone_check.add_argument("--skills-root", type=Path, required=True)
    clone_check.add_argument("--phase", choices=SUPPORTED_PHASES, default="full")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "write-manifest":
            result = write_manifest(args.path)
        elif args.command == "verify":
            result = verify_manifest(args.path)
        elif args.command == "stage":
            result = stage_packages(args.destination)
        elif args.command == "install":
            result = install_packages(args.skills_root, args.manifest)
        elif args.command == "clone-check":
            result = clone_readiness(args.skills_root, phase=args.phase)
        else:
            result = verify_installed_packages(
                args.skills_root,
                args.manifest,
                verify_workspace_source=False,
            )
    except ReleaseError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True))
        return 1
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    if not sys.flags.isolated or not sys.flags.no_site:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "release_skills CLI requires python3 -I -S",
                },
                ensure_ascii=True,
            )
        )
        raise SystemExit(2)
    raise SystemExit(main())

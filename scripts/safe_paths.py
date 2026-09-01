#!/usr/bin/env python3
"""Shared lexical path guards for create-once workflow artifacts.

``Path.resolve`` is not a security check: it silently follows user-controlled
symlinks.  Workflow entrypoints use these helpers before resolving a path so a
file selected below ``alias/`` cannot be written below the alias target.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path


SAFE_PLATFORM_PATH_ALIASES = {
    # macOS exposes these fixed compatibility aliases.  They are the only
    # symlinks accepted in an otherwise lexical, no-symlink ancestry walk.
    Path("/var"): Path("/private/var"),
    Path("/tmp"): Path("/private/tmp"),
    Path("/etc"): Path("/private/etc"),
}


class SafePathError(ValueError):
    """Raised when a path crosses a symlink or violates create-once policy."""


def absolute_path_without_symlinks(path: str | Path, *, label: str) -> Path:
    """Return a canonical absolute path after a lexical ancestry inspection."""

    expanded = Path(path).expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    lexical = Path(os.path.abspath(os.fspath(expanded)))
    cursor = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        cursor /= part
        if not os.path.lexists(cursor):
            continue
        try:
            metadata = cursor.lstat()
        except OSError as exc:
            raise SafePathError(f"{label} ancestry cannot be inspected: {cursor}") from exc
        if not stat.S_ISLNK(metadata.st_mode):
            continue
        allowed_target = SAFE_PLATFORM_PATH_ALIASES.get(cursor)
        if allowed_target is not None:
            try:
                if cursor.resolve(strict=True) == allowed_target:
                    continue
            except OSError:
                pass
        raise SafePathError(f"{label} must not traverse a symlink: {cursor}")
    try:
        return lexical.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise SafePathError(f"{label} cannot be resolved safely") from exc


def existing_regular_file(path: str | Path, *, label: str) -> Path:
    """Return one canonical existing regular file with a symlink-free ancestry."""

    candidate = absolute_path_without_symlinks(path, label=label)
    try:
        metadata = candidate.lstat()
    except OSError as exc:
        raise SafePathError(f"{label} is unavailable: {candidate}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise SafePathError(f"{label} must be a regular non-symlink file")
    return candidate


def existing_directory(path: str | Path, *, label: str) -> Path:
    """Return one canonical existing directory with a symlink-free ancestry."""

    candidate = absolute_path_without_symlinks(path, label=label)
    try:
        metadata = candidate.lstat()
    except OSError as exc:
        raise SafePathError(f"{label} is unavailable: {candidate}") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise SafePathError(f"{label} must be an existing non-symlink directory")
    return candidate


def new_file_path(
    path: str | Path,
    *,
    label: str,
    forbidden_root: str | Path | None = None,
) -> Path:
    """Bind a create-once file to an existing, symlink-free parent directory."""

    candidate = absolute_path_without_symlinks(path, label=label)
    if os.path.lexists(candidate):
        raise SafePathError(f"{label} already exists; replacement is forbidden")
    parent = existing_directory(candidate.parent, label=f"{label} parent")
    canonical = parent / candidate.name
    if forbidden_root is not None:
        root = existing_directory(forbidden_root, label="installed runtime root")
        try:
            canonical.relative_to(root)
        except ValueError:
            pass
        else:
            raise SafePathError(f"{label} must remain outside the installed runtime")
    if os.path.lexists(canonical):
        raise SafePathError(f"{label} already exists; replacement is forbidden")
    return canonical


def new_directory_path(
    path: str | Path,
    *,
    label: str,
    forbidden_root: str | Path | None = None,
) -> Path:
    """Bind a new output directory and optionally keep it outside a runtime."""

    candidate = absolute_path_without_symlinks(path, label=label)
    if os.path.lexists(candidate):
        raise SafePathError(f"{label} must be new and absent: {candidate}")
    parent = existing_directory(candidate.parent, label=f"{label} parent")
    canonical = parent / candidate.name
    if forbidden_root is not None:
        root = existing_directory(forbidden_root, label="installed runtime root")
        try:
            canonical.relative_to(root)
        except ValueError:
            pass
        else:
            raise SafePathError(f"{label} must remain outside the installed runtime")
    if os.path.lexists(canonical):
        raise SafePathError(f"{label} must be new and absent: {canonical}")
    return canonical


def require_within(path: str | Path, root: str | Path, *, label: str) -> Path:
    """Return a symlink-free path only when it remains below an allowed root."""

    candidate = absolute_path_without_symlinks(path, label=label)
    allowed = existing_directory(root, label=f"{label} allowed root")
    try:
        candidate.relative_to(allowed)
    except ValueError as exc:
        raise SafePathError(f"{label} must remain inside its configured root") from exc
    return candidate


def write_bytes_create_once(
    path: str | Path,
    payload: bytes,
    *,
    label: str,
    mode: int = 0o600,
    forbidden_root: str | Path | None = None,
) -> Path:
    """Write and fsync one new regular file without replacement or symlinks."""

    destination = new_file_path(
        path,
        label=label,
        forbidden_root=forbidden_root,
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(destination, flags, mode)
    except OSError as exc:
        raise SafePathError(f"{label} cannot be created safely: {exc}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise SafePathError(f"{label} destination must be a regular file")
        with os.fdopen(descriptor, "wb", closefd=True) as output:
            descriptor = -1
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
            descriptor = -1
        # The path was absent before this function and was opened O_EXCL, so
        # this cleanup can only remove our incomplete file.
        try:
            destination.unlink()
        except OSError:
            pass
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return destination


def write_text_create_once(
    path: str | Path,
    payload: str,
    *,
    label: str,
    mode: int = 0o600,
    forbidden_root: str | Path | None = None,
) -> Path:
    """UTF-8 convenience wrapper for :func:`write_bytes_create_once`."""

    return write_bytes_create_once(
        path,
        payload.encode("utf-8"),
        label=label,
        mode=mode,
        forbidden_root=forbidden_root,
    )

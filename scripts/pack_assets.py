#!/usr/bin/env python3
"""Resolve organization-pack assets without permitting path escape or symlinks."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Any


WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[/\\\\]")


class PackAssetResolutionError(ValueError):
    """Raised when an asset registry location is unsafe or unreadable."""


def canonical_pack_root(pack_dir: Path) -> Path:
    """Return the canonical pack root after rejecting lexical symlink traversal."""

    lexical_pack_root = Path(os.path.abspath(os.fspath(pack_dir)))
    cursor = Path(lexical_pack_root.anchor)
    for part in lexical_pack_root.parts[1:]:
        cursor = cursor / part
        try:
            metadata = os.lstat(cursor)
        except OSError as exc:
            raise PackAssetResolutionError(
                f"organization pack root is missing or unreadable: {pack_dir}"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise PackAssetResolutionError(
                f"organization pack root cannot traverse a symlink: {pack_dir}"
            )
    try:
        pack_root = lexical_pack_root.resolve(strict=True)
    except OSError as exc:
        raise PackAssetResolutionError(
            f"organization pack root is missing or unreadable: {pack_dir}"
        ) from exc
    if not pack_root.is_dir():
        raise PackAssetResolutionError(f"organization pack root is not a directory: {pack_dir}")
    return pack_root


def canonical_asset_location(location: Any, *, label: str = "asset location") -> str:
    """Return a canonical pack-relative POSIX path or fail closed.

    Registry locations are portable data, so they use the POSIX spelling on every
    host.  Requiring the serialized value to equal its normalized spelling keeps
    ``.``, duplicate separators, trailing separators, backslashes and traversal
    segments out of the trust boundary before the filesystem is consulted.
    """

    if not isinstance(location, str) or not location:
        raise PackAssetResolutionError(f"{label} must be a non-empty canonical relative path")
    if location != location.strip() or any(ord(character) < 32 for character in location):
        raise PackAssetResolutionError(f"{label} must be a canonical relative path")
    if "\\" in location or WINDOWS_ABSOLUTE.match(location):
        raise PackAssetResolutionError(f"{label} must use a canonical relative POSIX path")

    relative = PurePosixPath(location)
    if relative.is_absolute():
        raise PackAssetResolutionError(f"{label} must be relative to the organization pack")
    if not relative.parts or relative in {PurePosixPath("."), PurePosixPath("..")}:
        raise PackAssetResolutionError(f"{label} must name a file inside the organization pack")
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise PackAssetResolutionError(f"{label} cannot contain '.' or '..' path segments")
    if relative.as_posix() != location:
        raise PackAssetResolutionError(f"{label} must be a canonical relative POSIX path")
    return location


def resolve_pack_asset(
    pack_dir: Path,
    location: Any,
    *,
    label: str = "asset location",
) -> Path:
    """Resolve one registry asset to a regular, non-symlink file in ``pack_dir``.

    Every lexical component below the canonical pack root is inspected with
    ``lstat`` before ``resolve(strict=True)``.  This rejects both a symlink target
    and a symlinked parent directory even when the eventual target happens to be
    inside the pack.
    """

    serialized = canonical_asset_location(location, label=label)
    pack_root = canonical_pack_root(pack_dir)

    relative = PurePosixPath(serialized)
    candidate = pack_root
    for index, part in enumerate(relative.parts):
        candidate = candidate / part
        try:
            metadata = os.lstat(candidate)
        except OSError as exc:
            raise PackAssetResolutionError(f"{label} is missing or unreadable: {serialized}") from exc
        if stat.S_ISLNK(metadata.st_mode):
            subject = "target" if index == len(relative.parts) - 1 else "parent"
            raise PackAssetResolutionError(
                f"{label} cannot traverse a {subject} symlink: {serialized}"
            )
        if index < len(relative.parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
            raise PackAssetResolutionError(
                f"{label} has a non-directory parent component: {serialized}"
            )

    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(pack_root)
    except (OSError, ValueError) as exc:
        raise PackAssetResolutionError(
            f"{label} must resolve inside the canonical organization pack root: {serialized}"
        ) from exc
    try:
        final_metadata = os.lstat(candidate)
    except OSError as exc:
        raise PackAssetResolutionError(f"{label} is missing or unreadable: {serialized}") from exc
    if stat.S_ISLNK(final_metadata.st_mode) or not stat.S_ISREG(final_metadata.st_mode):
        raise PackAssetResolutionError(
            f"{label} must resolve to a regular non-symlink file: {serialized}"
        )
    return resolved

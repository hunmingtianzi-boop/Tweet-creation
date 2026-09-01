#!/usr/bin/env python3
"""Validate screenshot-backed Ardot visual review evidence."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

if __name__ == "__main__":
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/build_visual_review.py")

from pack_assets import canonical_asset_location, canonical_pack_root, resolve_pack_asset
try:
    from safe_paths import SafePathError, new_file_path, write_text_create_once
except ImportError:  # package import in repository tests
    from .safe_paths import (  # type: ignore
        SafePathError,
        new_file_path,
        write_text_create_once,
    )
from workflow_quality import read_json, validate_visual_review


RUNTIME_ROOT = Path(__file__).resolve().parent.parent


def canonical_input_file(path: Path, *, label: str) -> Path:
    """Resolve a strict input file while preserving lexical symlink evidence."""

    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    lexical = Path(os.path.abspath(os.fspath(expanded)))
    parent = canonical_pack_root(lexical.parent)
    return resolve_pack_asset(
        parent,
        canonical_asset_location(lexical.name, label=label),
        label=label,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path)
    parser.add_argument("--article", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        review_path = canonical_input_file(args.review, label="visual review document")
        article_path = canonical_input_file(args.article, label="article document")
        output = new_file_path(
            args.output or review_path.with_name(f"{review_path.stem}-report.json"),
            label="visual review report",
            forbidden_root=RUNTIME_ROOT,
        )
        review = read_json(review_path)
        article = read_json(article_path)
        report = validate_visual_review(review, article, article_path)
    except (SafePathError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    try:
        created = write_text_create_once(
            output,
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            label="visual review report",
            forbidden_root=RUNTIME_ROOT,
        )
    except SafePathError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({"created": str(created), **report}, ensure_ascii=False, indent=2))
    if not report["ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Validate the article's narrative storyboard before visual-kit generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

if __name__ == "__main__":
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/build_storyboard.py")

from workflow_quality import read_json

try:
    from safe_paths import (
        SafePathError,
        existing_regular_file,
        new_file_path,
        write_text_create_once,
    )
except ImportError:  # pragma: no cover - package import fallback
    from .safe_paths import (  # type: ignore
        SafePathError,
        existing_regular_file,
        new_file_path,
        write_text_create_once,
    )


RUNTIME_ROOT = Path(__file__).resolve().parent.parent


DENSITY_OCCUPANCY_BANDS = {
    "compact-editorial": (0.68, 0.90),
    "standard": (0.55, 0.86),
    "spacious-feature": (0.45, 0.76),
}


def build_storyboard_plan(article_path: Path) -> dict[str, Any]:
    article = read_json(article_path)
    blocks = article.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("article.blocks must be a non-empty array")
    storyboard = article.get("storyboard")
    if not isinstance(storyboard, dict):
        storyboard = {}
    chapters_raw = storyboard.get("chapters")
    chapters = [item for item in chapters_raw if isinstance(item, dict)] if isinstance(chapters_raw, list) else []
    errors: list[str] = []
    warnings: list[str] = []
    if storyboard.get("status") != "approved":
        errors.append("article.storyboard.status must be approved")
    if not chapters:
        errors.append("article storyboard requires at least one narrative chapter")
    elif not 4 <= len(chapters) <= 10:
        warnings.append("4 to 10 chapters is a long-form suggestion, not a delivery gate")
    covered: list[int] = []
    compositions: set[str] = set()
    chapter_ids: set[str] = set()
    previous_last_block = -1
    for index, chapter in enumerate(chapters):
        chapter_id = chapter.get("id")
        if not isinstance(chapter_id, str) or not chapter_id:
            errors.append(f"storyboard chapter {index} requires id")
        elif chapter_id in chapter_ids:
            errors.append(f"duplicate storyboard chapter id: {chapter_id}")
        else:
            chapter_ids.add(chapter_id)
        for field in ("label", "thesis", "composition", "visual_intent"):
            if not isinstance(chapter.get(field), str) or not chapter.get(field, "").strip():
                errors.append(f"storyboard chapter {chapter_id or index} requires {field}")
        density_intent = chapter.get("density_intent")
        if not isinstance(density_intent, dict):
            errors.append(
                f"storyboard chapter {chapter_id or index} density_intent must be a structured object"
            )
        else:
            density_mode = density_intent.get("mode")
            band = DENSITY_OCCUPANCY_BANDS.get(density_mode)
            if band is None:
                errors.append(
                    f"storyboard chapter {chapter_id or index} density_intent.mode is invalid"
                )
            target = density_intent.get("target_content_occupancy_ratio")
            if (
                band is None
                or not isinstance(target, (int, float))
                or isinstance(target, bool)
                or not band[0] <= float(target) <= band[1]
            ):
                errors.append(
                    f"storyboard chapter {chapter_id or index} density target is outside its mode band"
                )
            intentional = density_intent.get("intentional_whitespace")
            if not isinstance(intentional, bool):
                errors.append(
                    f"storyboard chapter {chapter_id or index} intentional_whitespace must be boolean"
                )
            if intentional is True and not isinstance(
                density_intent.get("whitespace_reason"), str
            ):
                errors.append(
                    f"storyboard chapter {chapter_id or index} intentional whitespace requires a reason"
                )
        composition = chapter.get("composition")
        if isinstance(composition, str):
            compositions.add(composition)
        indices = chapter.get("block_indices")
        if not isinstance(indices, list) or not indices:
            errors.append(f"storyboard chapter {chapter_id or index} requires block_indices")
            continue
        integer_indices = [
            value
            for value in indices
            if isinstance(value, int) and not isinstance(value, bool)
        ]
        if integer_indices != sorted(integer_indices):
            errors.append(
                f"storyboard chapter {chapter_id or index} block_indices must be monotonically increasing"
            )
        if integer_indices and integer_indices[0] <= previous_last_block:
            errors.append(
                "storyboard chapters must preserve the article block order; explicit visual reordering is forbidden"
            )
        if integer_indices:
            previous_last_block = max(previous_last_block, integer_indices[-1])
        for block_index in indices:
            if not isinstance(block_index, int) or isinstance(block_index, bool) or not 0 <= block_index < len(blocks):
                errors.append(f"storyboard chapter {chapter_id or index} has invalid block index: {block_index}")
            else:
                covered.append(block_index)
    duplicates = sorted({value for value in covered if covered.count(value) > 1})
    if duplicates:
        errors.append(f"storyboard block indices may appear only once: {duplicates}")
    expected = {
        index for index, block in enumerate(blocks)
        if isinstance(block, dict) and block.get("type") not in {"references", "footer"}
    }
    missing = sorted(expected - set(covered))
    if missing:
        errors.append(f"storyboard does not cover narrative block indices: {missing}")
    if len(compositions) < 3:
        warnings.append("consider varied composition only where it helps the reader")
    return {
        "schema_version": 1,
        "kind": "org-wechat-storyboard-plan",
        "article_id": article.get("article_id"),
        "ready_for_visual_kit": not errors,
        "errors": errors,
        "warnings": warnings,
        "chapter_count": len(chapters),
        "composition_count": len(compositions),
        "chapters": chapters,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("article", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        article = existing_regular_file(args.article, label="article")
        output = new_file_path(
            args.output,
            label="storyboard output",
            forbidden_root=RUNTIME_ROOT,
        )
        plan = build_storyboard_plan(article)
        write_text_create_once(
            output,
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
            label="storyboard output",
            forbidden_root=RUNTIME_ROOT,
        )
    except (SafePathError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({"created": str(output), "ready_for_visual_kit": plan["ready_for_visual_kit"], "errors": plan["errors"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

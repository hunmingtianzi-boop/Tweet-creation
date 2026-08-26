#!/usr/bin/env python3
"""Validate the article's narrative storyboard before visual-kit generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from workflow_quality import read_json


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
    if storyboard.get("status") != "approved":
        errors.append("article.storyboard.status must be approved")
    if not 4 <= len(chapters) <= 10:
        errors.append("article storyboard requires 4 to 10 narrative chapters")
    covered: list[int] = []
    compositions: set[str] = set()
    chapter_ids: set[str] = set()
    for index, chapter in enumerate(chapters):
        chapter_id = chapter.get("id")
        if not isinstance(chapter_id, str) or not chapter_id:
            errors.append(f"storyboard chapter {index} requires id")
        elif chapter_id in chapter_ids:
            errors.append(f"duplicate storyboard chapter id: {chapter_id}")
        else:
            chapter_ids.add(chapter_id)
        for field in ("label", "thesis", "composition", "visual_intent", "density_intent"):
            if not isinstance(chapter.get(field), str) or not chapter.get(field, "").strip():
                errors.append(f"storyboard chapter {chapter_id or index} requires {field}")
        composition = chapter.get("composition")
        if isinstance(composition, str):
            compositions.add(composition)
        indices = chapter.get("block_indices")
        if not isinstance(indices, list) or not indices:
            errors.append(f"storyboard chapter {chapter_id or index} requires block_indices")
            continue
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
        errors.append("storyboard requires at least 3 different composition modes")
    return {
        "schema_version": 1,
        "kind": "org-wechat-storyboard-plan",
        "article_id": article.get("article_id"),
        "ready_for_visual_kit": not errors,
        "errors": errors,
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
        plan = build_storyboard_plan(args.article.resolve())
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"created": str(args.output.resolve()), "ready_for_visual_kit": plan["ready_for_visual_kit"], "errors": plan["errors"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

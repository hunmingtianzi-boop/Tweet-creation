#!/usr/bin/env python3
"""Validate screenshot-backed Ardot visual review evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from workflow_quality import read_json, validate_visual_review


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path)
    parser.add_argument("--article", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    review_path = args.review.resolve()
    article_path = args.article.resolve()
    try:
        review = read_json(review_path)
        article = read_json(article_path)
        report = validate_visual_review(review, article, article_path)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    output = args.output or review_path.with_name(f"{review_path.stem}-report.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"created": str(output.resolve()), **report}, ensure_ascii=False, indent=2))
    if not report["ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

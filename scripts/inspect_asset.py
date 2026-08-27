#!/usr/bin/env python3
"""Inspect and validate a generated article micro-visual."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from asset_quality import ROLE_ASPECT_RATIOS, validate_micro_asset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset", type=Path)
    parser.add_argument("--role", required=True, choices=sorted(ROLE_ASPECT_RATIOS))
    args = parser.parse_args()
    report = validate_micro_asset(args.asset.resolve(), args.role)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

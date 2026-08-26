#!/usr/bin/env python3
"""Build organization-level calibration strips before full article production."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orgs import load_pack, validate_pack
from workflow_quality import calibration_state


def build_directions(org_dir: Path, article_type: str) -> dict[str, Any]:
    report = validate_pack(org_dir)
    if not report["ok"]:
        raise ValueError("invalid organization pack: " + "; ".join(report["errors"]))
    pack = load_pack(org_dir)
    organization = pack["organization"]
    if article_type not in organization.get("article_types", {}):
        raise ValueError(f"unknown article_type for organization: {article_type}")
    routes = [
        route
        for route in organization.get("visual", {}).get("routes", [])
        if isinstance(route, dict) and (
            article_type in route.get("uses", []) or not route.get("uses")
        )
    ]
    if len(routes) < 2:
        routes = [
            route for route in organization.get("visual", {}).get("routes", [])
            if isinstance(route, dict)
        ]
    route_candidates = routes[:3]
    tokens = organization["visual"]["tokens"]
    palette = ", ".join(
        f"{key} {tokens[key]}" for key in ("ink", "accent", "accent_alt", "surface_alt")
    )
    motifs = "、".join(organization["visual"].get("motifs", []))
    directions: list[dict[str, Any]] = []
    for route in route_candidates:
        base = (
            f"{organization['identity']['name']} / {article_type} / {route['label']}; "
            f"direction {route['dominant_style']}; palette {palette}; motifs {motifs}; "
            "text remains editable in Ardot; no generated letters, logo, QR, dashboard, or generic AI glow."
        )
        directions.append(
            {
                "route_id": route["id"],
                "label": route["label"],
                "rationale": route["rationale"],
                "calibration_strip": [
                    {"role": "hero", "prompt": base + " Create one mobile hero with a real title-safe zone."},
                    {"role": "chapter", "prompt": base + " Create one open editorial chapter with one concrete subject."},
                    {"role": "photo-composition", "instruction": "Compose supplied real photos with route-specific crop, overlap, caption, and whitespace behavior."},
                    {"role": "micro-visual", "prompt": base + " Create one unframed micro illustration grounded in a concrete organization object or action."},
                ],
            }
        )
    state = calibration_state(organization)
    return {
        "schema_version": 1,
        "kind": "org-wechat-visual-directions",
        "organization_id": organization["id"],
        "article_type": article_type,
        "calibration_ready": len(directions) >= 2,
        "full_article_allowed": state["ready"],
        "blocking_reasons": (
            [] if len(directions) >= 2 else ["create at least two materially different visual routes"]
        ) + state["blocking_reasons"],
        "directions": directions,
        "required_review": {
            "compare": ["hero", "chapter", "photo-composition", "micro-visual"],
            "approve_one_route_in": "organization.visual.calibration.approved_routes",
            "record_benchmark": ["file_url", "page_name", "article_node_id"],
            "stop_before_full_article": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("org", type=Path)
    parser.add_argument("article_type")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        plan = build_directions(args.org.resolve(), args.article_type)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"created": str(args.output.resolve()), "directions": len(plan["directions"]), "full_article_allowed": plan["full_article_allowed"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

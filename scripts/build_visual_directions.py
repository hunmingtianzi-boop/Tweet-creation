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
    provenance = organization.get("provenance", {})
    visual_input_source_ids = provenance.get("visual_input_source_ids", [])
    personality = organization.get("personality", {})
    typography_strategy = (
        "expressive-native"
        if personality.get("experimental", 0) >= 60 or personality.get("action", 0) >= 65
        else "restrained-native"
    )
    directions: list[dict[str, Any]] = []
    for route in route_candidates:
        base = (
            f"{organization['identity']['name']} / {article_type} / {route['label']}; "
            f"direction {route['dominant_style']}; palette {palette}; motifs {motifs}; "
            f"derive visual decisions only from source IDs {visual_input_source_ids}; "
            "do not inspect or imitate prior article layouts, Ardot files, screenshots, examples, or another organization's pack; "
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
                    {"role": "density-strip", "instruction": "Compose editable body text, one list/process, and one photo-to-text transition at compact-editorial density."},
                ],
                "background_family_trial": {
                    "required": True,
                    "master": "Generate one text-free atmosphere master with a near-solid copy-safe zone.",
                    "companions": "Generate 1 to 3 variants with the same spatial logic, material, light direction, palette, and declared surface mode.",
                    "approval_contract": {
                        "surface_mode": "choose exactly one of light or dark for the whole family",
                        "copy_safe_zone": "record normalized x/y/width/height",
                        "body_text_color": "record one hex color used for the contrast preflight",
                        "minimum_contrast_ratio": 4.5,
                        "maximum_copy_safe_stddev": 0.10,
                    },
                    "preflight": "Export final opaque PNGs, register the master and companions, then run orgs.py validate. Do not begin an article root until pixel inspection passes.",
                    "forbidden": "Do not mix light and dark chapter surfaces, accept a high-variance copy zone, generate unrelated chapter backgrounds, or use generated scenes as documentary evidence.",
                },
                "typography_trial": {
                    "recommended_strategy": typography_strategy,
                    "compare": ["hero-title", "chapter-title"],
                    "candidate_treatments": ["stacked-title", "mixed-weight", "stroke-offset"],
                    "approve_as_recipes": True,
                    "requirements": [
                        "native editable Ardot text nodes",
                        "licensed or system fonts only",
                        "standard readable body copy",
                        "fallback text style for every expressive moment",
                        "at least two non-font construction techniques per approved recipe",
                        "at least two editable text/accent layers per expressive moment",
                        "record recipe ID, construction techniques, and Ardot node IDs",
                    ],
                    "forbidden": "A font swap alone is not art type. No AI-generated Chinese lettering bitmap, flattened title image, or outlined-only critical copy.",
                },
            }
        )
    state = calibration_state(organization, assets_doc=pack["assets"])
    return {
        "schema_version": 1,
        "kind": "org-wechat-visual-directions",
        "organization_id": organization["id"],
        "article_type": article_type,
        "source_isolation": state["source_isolation"],
        "input_basis": {
            "visual_input_source_ids": visual_input_source_ids,
            "forbidden_visual_inputs": provenance.get("excluded_visual_reference_kinds", []),
        },
        "calibration_ready": len(directions) >= 2,
        "full_article_allowed": state["ready"],
        "blocking_reasons": (
            [] if len(directions) >= 2 else ["create at least two materially different visual routes"]
        ) + state["blocking_reasons"],
        "directions": directions,
        "required_review": {
            "compare": ["hero", "chapter", "photo-composition", "micro-visual", "density-strip"],
            "background_family": ["master", "1-3 companions", "one surface mode", "normalized copy-safe zone", "4.5:1 text contrast", "copy-zone variance <= 0.10", "pixel-checked continuity"],
            "typography": ["strategy", "at least two approved construction recipes", "at least two non-font techniques", "editable text/accent layers", "body-copy fallback"],
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

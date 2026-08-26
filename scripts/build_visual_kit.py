#!/usr/bin/env python3
"""Plan the mandatory article-specific micro-illustration kit before layout."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from orgs import load_pack, validate_pack


KIT_ROLES = (
    {
        "role": "floating-spot",
        "purpose": "a small floating illustration that enters or exits an open text section",
        "aspect_ratio": "1:1",
        "placement": "lead, open paragraph edge, or between two text passages",
    },
    {
        "role": "section-transition",
        "purpose": "a wide flowing illustration that carries the eye into the next section",
        "aspect_ratio": "4:1",
        "placement": "between major sections; never inside a bordered panel",
    },
    {
        "role": "inline-explainer",
        "purpose": "a compact visual explanation of one concrete object, action, or process",
        "aspect_ratio": "4:3",
        "placement": "beside or between explanatory paragraphs",
    },
    {
        "role": "closing-motif",
        "purpose": "a small finishing illustration that gives the CTA a visual landing",
        "aspect_ratio": "1:1",
        "placement": "near the closing action without becoming a button or card",
    },
)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def choose_route(article: dict[str, Any], organization: dict[str, Any]) -> dict[str, Any]:
    article_type = article.get("article_type")
    config = organization.get("article_types", {}).get(article_type)
    if not isinstance(config, dict):
        raise ValueError(f"unknown article_type for organization: {article_type}")
    route_id = article.get("route") or config.get("route")
    for route in organization.get("visual", {}).get("routes", []):
        if isinstance(route, dict) and route.get("id") == route_id:
            return route
    raise ValueError(f"unknown visual route: {route_id}")


def collect_material(value: Any) -> list[str]:
    collected: list[str] = []
    if isinstance(value, str):
        if value.strip() and not re.match(r"^(?:core\.|visual\.|brand\.|legacy-)", value):
            collected.append(value.strip())
    elif isinstance(value, list):
        for item in value:
            collected.extend(collect_material(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in {"source_id", "component", "src", "background", "alt", "background_alt"}:
                collected.extend(collect_material(item))
    return collected


def visual_kit_assets(article: dict[str, Any]) -> list[dict[str, Any]]:
    visual_kit = article.get("visual_kit")
    if not isinstance(visual_kit, dict):
        return []
    assets = visual_kit.get("assets")
    return [item for item in assets if isinstance(item, dict)] if isinstance(assets, list) else []


def build_visual_kit_plan(article_path: Path, org_dir: Path) -> dict[str, Any]:
    report = validate_pack(org_dir)
    if not report["ok"]:
        raise ValueError("invalid organization pack: " + "; ".join(report["errors"]))
    article = read_json(article_path)
    pack = load_pack(org_dir)
    organization = pack["organization"]
    if article.get("organization_id") != organization.get("id"):
        raise ValueError("article organization_id does not match the organization pack")
    article_id = article.get("article_id")
    if not isinstance(article_id, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", article_id):
        raise ValueError("article.article_id must be a lowercase hyphenated slug")
    route = choose_route(article, organization)
    registered = {
        item.get("id"): item
        for item in pack["assets"].get("assets", [])
        if isinstance(item, dict) and item.get("id")
    }
    approved_assets = visual_kit_assets(article)
    visual_kit_status = (
        article.get("visual_kit", {}).get("status")
        if isinstance(article.get("visual_kit"), dict)
        else None
    )
    by_role = {
        item.get("role"): item
        for item in approved_assets
        if isinstance(item.get("role"), str) and isinstance(item.get("id"), str)
    }
    material = "；".join(dict.fromkeys(collect_material(article.get("blocks", []))))
    material = material[:700]
    motifs = "、".join(organization.get("visual", {}).get("motifs", []))
    avoid = "、".join(organization.get("visual", {}).get("avoid", []))
    tokens = organization["visual"]["tokens"]
    palette = ", ".join(
        f"{name} {tokens[name]}"
        for name in ("ink", "accent", "accent_alt", "surface_alt")
    )
    slots: list[dict[str, Any]] = []
    missing_roles: list[str] = []
    registered_generated_ids: set[str] = set()
    for definition in KIT_ROLES:
        role = definition["role"]
        approved = by_role.get(role)
        asset_id = approved.get("id") if approved else None
        registered_asset = registered.get(asset_id) if asset_id else None
        ready = bool(
            registered_asset
            and registered_asset.get("origin") == "generated-illustrative"
            and article_id in registered_asset.get("generated_for_articles", [])
        )
        if ready and asset_id:
            registered_generated_ids.add(asset_id)
        if not ready:
            missing_roles.append(role)
        prompt = (
            f"Create one text-free {definition['purpose']} for the article “{article.get('title', '')}” "
            f"by {organization['identity']['name']}. Derive the visual from these concrete article "
            f"materials: {material}. Follow the {route['dominant_style']} direction with motifs "
            f"{motifs} and palette {palette}. Aspect ratio {definition['aspect_ratio']}. Use a "
            f"transparent background or an irregular/open edge; keep generous negative space. "
            f"Do not create a rectangle, card, UI panel, border, poster, generic blob, letters, "
            f"numbers, watermark, logo, or QR code. Avoid: {avoid}."
        )
        slots.append(
            {
                **definition,
                "status": "approved-and-registered" if ready else "generate-required",
                "asset_id": asset_id,
                "prompt": prompt,
                "registration": {
                    "origin": "generated-illustrative",
                    "role": role,
                    "generated_for": article_id,
                },
                "ardot_component_name": f"WeChat/Ornament/{''.join(part.title() for part in role.split('-'))}/{pack['ardot']['variable_mode']}",
            }
        )
    minimum_unique_assets = 3
    ready_for_layout = (
        visual_kit_status == "approved"
        and not missing_roles
        and len(registered_generated_ids) >= minimum_unique_assets
    )
    blocking_reasons = [f"missing visual role: {role}" for role in missing_roles]
    if visual_kit_status != "approved":
        blocking_reasons.append("article.visual_kit.status must be approved after image inspection")
    if len(registered_generated_ids) < minimum_unique_assets:
        blocking_reasons.append(
            f"needs at least {minimum_unique_assets} unique generated micro assets; found {len(registered_generated_ids)}"
        )
    return {
        "schema_version": 1,
        "kind": "org-wechat-visual-kit-plan",
        "organization_id": organization["id"],
        "article_id": article_id,
        "article_title": article.get("title"),
        "article_type": article.get("article_type"),
        "route_id": route["id"],
        "minimum_micro_component_roles": len(KIT_ROLES),
        "minimum_unique_generated_micro_assets": minimum_unique_assets,
        "visual_kit_status": visual_kit_status,
        "ready_for_layout": ready_for_layout,
        "missing_roles": missing_roles,
        "blocking_reasons": blocking_reasons,
        "slots": slots,
        "required_sequence": [
            "generate every missing slot before any article layout",
            "inspect each image and reject rectangular, framed, generic, or text-bearing results",
            f"save and register approved images as generated-illustrative assets with generated_for_articles={article_id}",
            "record the registered IDs under article.visual_kit.assets",
            "create native Ardot ornament components from the approved images",
            "only then assemble the long article",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("article", type=Path)
    parser.add_argument("--org", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        plan = build_visual_kit_plan(args.article.resolve(), args.org.resolve())
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "created": str(args.output.resolve()),
                "ready_for_layout": plan["ready_for_layout"],
                "missing_roles": plan["missing_roles"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

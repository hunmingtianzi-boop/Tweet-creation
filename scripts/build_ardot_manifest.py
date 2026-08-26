#!/usr/bin/env python3
"""Build a deterministic Ardot assembly manifest from an article and organization pack."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from build_visual_kit import build_visual_kit_plan
from orgs import load_pack, validate_pack


TOKEN_NAMES = {
    "ink": "Ink",
    "body": "Body",
    "accent": "Accent",
    "accent_alt": "Accent Alt",
    "surface": "Surface",
    "surface_alt": "Surface Alt",
    "border": "Border",
    "on_accent": "On Accent",
}

OPEN_COMPOSITIONS = {
    "hero": ("image-led-opening", []),
    "lead": ("open-editorial", ["floating-spot"]),
    "section": ("floating-marker", ["section-transition"]),
    "text": ("open-editorial", ["floating-spot"]),
    "statement": ("typographic-pause", ["floating-spot"]),
    "metrics": ("open-number-field", ["inline-explainer"]),
    "timeline": ("flowing-line", ["inline-explainer"]),
    "gallery": ("edge-to-edge-sequence", ["section-transition"]),
    "case": ("layered-process-without-outer-card", ["inline-explainer"]),
    "roles": ("staggered-open-labels", ["floating-spot", "inline-explainer"]),
    "quote": ("full-width-type-pause", ["floating-spot"]),
    "steps": ("continuous-journey-path", ["inline-explainer"]),
    "image": ("open-image-break", ["section-transition"]),
    "cta": ("illustrated-ending", ["closing-motif"]),
    "references": ("quiet-open-notes", []),
    "footer": ("quiet-open-ending", ["closing-motif"]),
}


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


def pascal(value: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in re.split(r"[-_\s]+", value) if part)


def choose_route(article: dict[str, Any], organization: dict[str, Any]) -> dict[str, Any]:
    article_type = article.get("article_type")
    article_config = organization.get("article_types", {}).get(article_type)
    if not isinstance(article_config, dict):
        raise ValueError(f"unknown article_type for organization: {article_type}")
    route_id = article.get("route") or article_config.get("route")
    for route in organization.get("visual", {}).get("routes", []):
        if isinstance(route, dict) and route.get("id") == route_id:
            return route
    raise ValueError(f"unknown visual route: {route_id}")


def variant_for(block: dict[str, Any], route: dict[str, Any]) -> str:
    explicit = block.get("variant")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    configured = route.get("component_variants", {}).get(block.get("type"))
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    return "standard"


def asset_references(block: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("background", "src"):
        value = block.get(key)
        if isinstance(value, str) and value:
            refs.append(value)
    for key in ("images", "items"):
        items = block.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("src"), str):
                refs.append(item["src"])
    qr = block.get("qr")
    if isinstance(qr, dict) and isinstance(qr.get("src"), str):
        refs.append(qr["src"])
    return list(dict.fromkeys(refs))


def resolve_asset(ref: str, pack: dict[str, Any], article_path: Path) -> dict[str, Any]:
    registry = {
        item.get("id"): item
        for item in pack["assets"].get("assets", [])
        if isinstance(item, dict) and item.get("id")
    }
    item = registry.get(ref)
    if item:
        location = item.get("location")
        local_path = None
        if isinstance(location, str) and not re.match(r"^(?:https?://|data:)", location):
            local_path = str((pack["path"] / location).resolve())
        return {
            "ref": ref,
            "registered": True,
            "kind": item.get("kind"),
            "origin": item.get("origin"),
            "location": location,
            "local_path": local_path,
        }
    local_path = (article_path.parent / ref).resolve()
    return {
        "ref": ref,
        "registered": False,
        "location": ref,
        "local_path": str(local_path) if local_path.exists() else None,
    }


def build_manifest(article_path: Path, org_dir: Path) -> dict[str, Any]:
    report = validate_pack(org_dir)
    if not report["ok"]:
        raise ValueError("invalid organization pack: " + "; ".join(report["errors"]))
    article = read_json(article_path)
    pack = load_pack(org_dir)
    organization = pack["organization"]
    if article.get("organization_id") != organization.get("id"):
        raise ValueError("article organization_id does not match the organization pack")
    route = choose_route(article, organization)
    visual_kit_plan = build_visual_kit_plan(article_path, org_dir)
    kit_asset_by_role = {
        item["role"]: item.get("asset_id")
        for item in visual_kit_plan["slots"]
        if item.get("asset_id")
    }
    ardot = pack["ardot"]
    mode = ardot["variable_mode"]
    aliases = ardot.get("component_aliases", {})
    blocks: list[dict[str, Any]] = []
    used_assets: list[str] = []
    for index, raw in enumerate(article.get("blocks", [])):
        if not isinstance(raw, dict) or not isinstance(raw.get("type"), str):
            raise ValueError(f"block {index} must be an object with type")
        kind = raw["type"]
        variant = variant_for(raw, route)
        alias_key = f"{kind}.{variant}"
        component_name = aliases.get(
            alias_key,
            f"WeChat/{pascal(kind)}/{pascal(variant)}/{mode}",
        )
        refs = asset_references(raw)
        used_assets.extend(refs)
        composition_mode, kit_roles = OPEN_COMPOSITIONS.get(
            kind, ("open-editorial", ["floating-spot"])
        )
        kit_assets = [kit_asset_by_role[role] for role in kit_roles if role in kit_asset_by_role]
        used_assets.extend(kit_assets)
        content = {
            key: value
            for key, value in raw.items()
            if key not in {"type", "component", "variant", "background"}
        }
        blocks.append(
            {
                "index": index,
                "semantic_id": f"block-{index:02d}-{kind}",
                "type": kind,
                "content_component": raw.get("component", f"core.{kind}"),
                "variant": variant,
                "ardot_component": component_name,
                "composition_mode": composition_mode,
                "container_policy": "open-by-default",
                "micro_visual_roles": kit_roles,
                "micro_visual_assets": kit_assets,
                "content": content,
                "asset_refs": refs,
            }
        )
    tokens = organization["visual"]["tokens"]
    variables = {
        TOKEN_NAMES[key]: value
        for key, value in tokens.items()
        if key in TOKEN_NAMES
    }
    assets = [
        resolve_asset(ref, pack, article_path)
        for ref in dict.fromkeys(used_assets)
    ]
    unresolved = [item["ref"] for item in assets if not item.get("local_path") and not re.match(r"^https?://", str(item.get("location", "")))]
    return {
        "schema_version": 1,
        "kind": "org-wechat-ardot-assembly",
        "organization": {
            "id": organization["id"],
            "name": organization["identity"]["name"],
            "status": organization["status"],
        },
        "article": {
            "article_id": article.get("article_id"),
            "title": article.get("title"),
            "article_type": article.get("article_type"),
            "mobile_width": 390,
            "root_name": f"Article / {organization['identity']['short_name']} / {article.get('title', 'Untitled')}",
        },
        "design_target": {
            "status": ardot["status"],
            "file_url": ardot["design_file"].get("url"),
            "variable_set": ardot["variable_set"],
            "variable_mode": mode,
            "pages": ardot["page_names"],
        },
        "route": {
            "id": route["id"],
            "label": route["label"],
            "layout": route["layout"],
            "dominant_style": route["dominant_style"],
            "component_variants": route.get("component_variants", {}),
        },
        "variables": variables,
        "visual_kit": visual_kit_plan,
        "blocks": blocks,
        "assets": assets,
        "assembly": [
            "STOP if visual_kit.ready_for_layout is false",
            "generate, inspect, register, and componentize the four micro illustrations before article layout",
            "apply or update the organization variable mode",
            "fetch reusable components by exact ardot_component name",
            "create missing semantic component variants before article assembly",
            "create one 390px article root and insert blocks in manifest order",
            "place micro illustrations between and beside open text flows; never use them as card backgrounds",
            "upload registered image assets to their named image slots",
            "capture section screenshots and iterate before any WeChat handoff",
        ],
        "qa": {
            "ready_for_layout": visual_kit_plan["ready_for_layout"],
            "blocking": [
                "article-specific visual kit lacks any required role or has fewer than three unique generated micro assets",
                "layout started before micro illustrations became native Ardot components",
                "missing component variant",
                "unresolved asset",
                "clipped or overflowed text",
                "more than 20 percent of content sections use a closed box",
                "two boxed sections appear consecutively",
                "every semantic block has its own background, border, or rounded container",
                "micro illustration is rectangular, framed, generic, or used as a panel background",
                "organization mode or organization_id mismatch",
            ],
            "layout_policy": {
                "maximum_boxed_section_ratio": 0.2,
                "maximum_consecutive_boxed_sections": 1,
                "minimum_micro_illustration_roles": 4,
                "minimum_unique_generated_micro_assets": 3,
                "minimum_asymmetric_or_edge_breaking_moments": 3,
                "default_container": "none",
            },
            "unresolved_assets": unresolved,
            "requires_visual_review": True,
        },
        "handoff": {
            "source_of_truth": "ardot-native",
            "wechat_adapter": "hidden-final-transport",
            "publish_action": "draft-only",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("article", type=Path)
    parser.add_argument("--org", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = build_manifest(args.article.resolve(), args.org.resolve())
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"created": str(args.output.resolve()), "blocks": len(manifest["blocks"]), "ok": not manifest["qa"]["unresolved_assets"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

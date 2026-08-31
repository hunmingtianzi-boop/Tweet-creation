#!/usr/bin/env python3
"""Initialize, inspect, search, recommend, and validate organization packs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from asset_quality import (
    MICRO_CUTOUT_EVIDENCE_FIELDS,
    validate_background_family_assets,
    validate_micro_asset,
)
from workflow_quality import (
    ALLOWED_VISUAL_REFERENCE_POLICIES,
    ALLOWED_ART_TYPE_TREATMENTS,
    ALLOWED_ART_TYPE_TECHNIQUES,
    ALLOWED_TYPOGRAPHY_STRATEGIES,
    EXPLICIT_STYLE_REFERENCE_SCOPE,
    REQUIRED_STYLE_NON_COPY_CONSTRAINTS,
    WATERMARK_POLICY_MODES,
    WATERMARK_SCHEME,
    asset_watermark_requirement,
    style_grammar_errors,
    validate_asset_watermark,
    valid_watermark_key_id,
    watermark_evidence_from_report,
    watermark_inventory,
    watermark_policy,
)


HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PACK_FILES = (
    "organization.json",
    "sources.json",
    "components.json",
    "assets.json",
    "ardot.json",
)
AXES = ("authority", "technical", "warmth", "experimental", "action")
TOKENS = (
    "ink",
    "body",
    "accent",
    "accent_alt",
    "surface",
    "surface_alt",
    "border",
    "white",
)
LAYOUTS = {"editorial", "poster", "technical", "institutional", "warm-community"}
SAFE_IDENTITY_ORIGINS = {"user-supplied", "official"}
ASSET_ORIGINS = SAFE_IDENTITY_ORIGINS | {
    "photographed",
    "generated-illustrative",
    "derived",
}
ASSET_KINDS = {"logo", "qr", "photo", "illustration", "background", "decoration"}
VISUAL_KIT_ROLES = {
    "floating-spot",
    "section-transition",
    "inline-explainer",
    "closing-motif",
}
DENSITY_MODES = {"compact-editorial", "standard", "spacious-feature"}
VISUAL_ASSET_ROLES = {
    "documentary-evidence",
    "illustrative-atmosphere",
    "editorial-explainer",
    "article-micro",
    "identity",
    "functional",
}
SOURCE_ZERO_EXCLUSIONS = {
    "prior-article-layout",
    "prior-ardot-file",
    "prior-article-screenshot",
    "other-organization-visual-pack",
}


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_pack(pack_dir: Path) -> dict[str, Any]:
    pack_dir = pack_dir.resolve()
    return {
        "path": pack_dir,
        "organization": read_json(pack_dir / "organization.json"),
        "sources": read_json(pack_dir / "sources.json"),
        "components": read_json(pack_dir / "components.json"),
        "assets": read_json(pack_dir / "assets.json"),
        "ardot": read_json(pack_dir / "ardot.json"),
    }


def require_dict(value: Any, label: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return {}
    return value


def require_list(value: Any, label: str, errors: list[str]) -> list[Any]:
    if not isinstance(value, list):
        errors.append(f"{label} must be an array")
        return []
    return value


def duplicate_ids(items: list[Any]) -> list[str]:
    ids = [item.get("id") for item in items if isinstance(item, dict) and item.get("id")]
    return sorted({item_id for item_id in ids if ids.count(item_id) > 1})


def validate_pack(pack_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    background_quality: dict[str, Any] | None = None
    for filename in PACK_FILES:
        if not (pack_dir / filename).exists():
            errors.append(f"missing file: {filename}")
    if errors:
        return {"ok": False, "path": str(pack_dir), "errors": errors, "warnings": warnings}

    try:
        pack = load_pack(pack_dir)
    except ValueError as exc:
        return {"ok": False, "path": str(pack_dir), "errors": [str(exc)], "warnings": []}

    org = require_dict(pack["organization"], "organization.json", errors)
    sources_doc = require_dict(pack["sources"], "sources.json", errors)
    components_doc = require_dict(pack["components"], "components.json", errors)
    assets_doc = require_dict(pack["assets"], "assets.json", errors)
    ardot_doc = require_dict(pack["ardot"], "ardot.json", errors)

    org_id = org.get("id")
    if not isinstance(org_id, str) or not SLUG.fullmatch(org_id):
        errors.append("organization.id must be a lowercase hyphenated slug")
    for label, doc in (
        ("sources", sources_doc),
        ("components", components_doc),
        ("assets", assets_doc),
        ("ardot", ardot_doc),
    ):
        if doc.get("organization_id") != org_id:
            errors.append(f"{label}.organization_id must match organization.id")
    for label, doc in (
        ("organization", org),
        ("sources", sources_doc),
        ("components", components_doc),
        ("assets", assets_doc),
        ("ardot", ardot_doc),
    ):
        if doc.get("schema_version") != 1:
            errors.append(f"{label}.schema_version must be 1")

    if org.get("status") not in {"provisional", "confirmed", "migrated-draft"}:
        errors.append("organization.status must be provisional, confirmed, or migrated-draft")
    elif org.get("status") != "confirmed":
        warnings.append(f"organization pack status is {org.get('status')}; confirm before external delivery")

    identity = require_dict(org.get("identity"), "organization.identity", errors)
    for field in ("name", "short_name", "summary", "category"):
        if not isinstance(identity.get(field), str) or not identity.get(field, "").strip():
            errors.append(f"organization.identity.{field} must be a non-empty string")
    for field in ("audiences", "content_pillars"):
        if not require_list(identity.get(field), f"organization.identity.{field}", errors):
            errors.append(f"organization.identity.{field} must not be empty")

    personality = require_dict(org.get("personality"), "organization.personality", errors)
    for axis in AXES:
        value = personality.get(axis)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 100:
            errors.append(f"organization.personality.{axis} must be a number from 0 to 100")

    voice = require_dict(org.get("voice"), "organization.voice", errors)
    for field in ("traits", "headline_patterns", "preferred_terms", "avoid_terms"):
        require_list(voice.get(field), f"organization.voice.{field}", errors)

    visual = require_dict(org.get("visual"), "organization.visual", errors)
    tokens = require_dict(visual.get("tokens"), "organization.visual.tokens", errors)
    for token in TOKENS:
        value = tokens.get(token)
        if not isinstance(value, str) or not HEX_COLOR.fullmatch(value):
            errors.append(f"organization.visual.tokens.{token} must be a #RRGGBB color")
    require_list(visual.get("motifs"), "organization.visual.motifs", errors)
    require_list(visual.get("avoid"), "organization.visual.avoid", errors)
    routes = require_list(visual.get("routes"), "organization.visual.routes", errors)
    for duplicate in duplicate_ids(routes):
        errors.append(f"duplicate visual route id: {duplicate}")
    route_ids: set[str] = set()
    for index, route_raw in enumerate(routes):
        route = require_dict(route_raw, f"organization.visual.routes[{index}]", errors)
        route_id = route.get("id")
        if not isinstance(route_id, str) or not SLUG.fullmatch(route_id):
            errors.append(f"visual route {index} has invalid id")
            continue
        route_ids.add(route_id)
        if route.get("layout") not in LAYOUTS:
            errors.append(f"visual route {route_id} has unsupported layout: {route.get('layout')}")
        for field in ("label", "dominant_style", "rationale"):
            if not isinstance(route.get(field), str) or not route.get(field, "").strip():
                errors.append(f"visual route {route_id} missing {field}")
        require_list(route.get("uses"), f"visual route {route_id}.uses", errors)
    default_route = visual.get("default_route")
    if default_route not in route_ids:
        errors.append("organization.visual.default_route must reference a registered route")

    calibration = visual.get("calibration")
    if not isinstance(calibration, dict):
        calibration = {}
        warnings.append("organization.visual.calibration is missing; full article production is blocked")
    calibration_status = calibration.get("status", "missing")
    if calibration_status not in {"not-started", "directions-ready", "approved", "missing"}:
        errors.append("organization.visual.calibration.status is invalid")
    approved_routes = require_list(
        calibration.get("approved_routes", []),
        "organization.visual.calibration.approved_routes",
        errors,
    )
    for route_id in approved_routes:
        if route_id not in route_ids:
            errors.append(f"visual calibration references unknown route: {route_id}")
    if calibration_status == "approved":
        benchmark = require_dict(
            calibration.get("benchmark"),
            "organization.visual.calibration.benchmark",
            errors,
        )
        for field in ("file_url", "page_name", "article_node_id"):
            if not isinstance(benchmark.get(field), str) or not benchmark.get(field, "").strip():
                errors.append(f"approved visual calibration benchmark requires {field}")
        if not approved_routes:
            errors.append("approved visual calibration requires at least one approved route")
        if calibration.get("density_mode") not in DENSITY_MODES:
            errors.append("approved visual calibration requires a valid density_mode")
        background_family = calibration.get("background_family")
        if background_family is None:
            errors.append("approved visual calibration requires a generated background_family")
        else:
            background_family = require_dict(
                background_family,
                "organization.visual.calibration.background_family",
                errors,
            )
            for field in ("id", "strategy", "master_asset_id"):
                if not isinstance(background_family.get(field), str) or not background_family.get(field, "").strip():
                    errors.append(f"approved visual calibration background_family requires {field}")
            if background_family.get("strategy") != "generated-family":
                errors.append("approved visual calibration background_family.strategy must be generated-family")
            if background_family.get("surface_mode") not in {"light", "dark"}:
                errors.append("approved background family surface_mode must be light or dark")
            copy_safe_zone = require_dict(
                background_family.get("copy_safe_zone"),
                "organization.visual.calibration.background_family.copy_safe_zone",
                errors,
            )
            for field in ("x", "y", "width", "height"):
                value = copy_safe_zone.get(field)
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    errors.append(f"approved background family copy_safe_zone.{field} must be numeric")
            body_text_color = background_family.get("body_text_color")
            if not isinstance(body_text_color, str) or not HEX_COLOR.fullmatch(body_text_color):
                errors.append("approved background family body_text_color must be a #RRGGBB color")
            minimum_contrast = background_family.get("minimum_contrast_ratio")
            if not isinstance(minimum_contrast, (int, float)) or isinstance(minimum_contrast, bool) or minimum_contrast < 4.5:
                errors.append("approved background family minimum_contrast_ratio must be at least 4.5")
            maximum_stddev = background_family.get("maximum_copy_safe_stddev")
            if not isinstance(maximum_stddev, (int, float)) or isinstance(maximum_stddev, bool) or not 0 < maximum_stddev <= 0.12:
                errors.append("approved background family maximum_copy_safe_stddev must be between 0 and 0.12")
            companions = require_list(
                background_family.get("companion_asset_ids"),
                "organization.visual.calibration.background_family.companion_asset_ids",
                errors,
            )
            if not 1 <= len(companions) <= 3:
                errors.append("approved background family requires 1 to 3 companion assets")
        typography = require_dict(
            calibration.get("typography"),
            "organization.visual.calibration.typography",
            errors,
        )
        if typography.get("strategy") not in ALLOWED_TYPOGRAPHY_STRATEGIES:
            errors.append("approved typography strategy must be expressive-native or restrained-native")
        if typography.get("editable_text_required") is not True:
            errors.append("approved typography must require editable native text")
        if typography.get("font_policy") != "licensed-or-system-only":
            errors.append("approved typography font_policy must be licensed-or-system-only")
        if typography.get("body_copy_remains_standard") is not True:
            errors.append("approved typography must keep body copy standard")
        treatments = require_list(
            typography.get("approved_treatments"),
            "organization.visual.calibration.typography.approved_treatments",
            errors,
        )
        if not treatments:
            errors.append("approved typography requires at least one treatment")
        for treatment in treatments:
            if treatment not in ALLOWED_ART_TYPE_TREATMENTS:
                errors.append(f"approved typography has invalid treatment: {treatment}")
        maximum_moments = typography.get("maximum_moments_per_article")
        if (
            not isinstance(maximum_moments, int)
            or isinstance(maximum_moments, bool)
            or not 2 <= maximum_moments <= 4
        ):
            errors.append("approved typography maximum_moments_per_article must be 2 to 4")
        recipes = require_list(
            typography.get("approved_recipes"),
            "organization.visual.calibration.typography.approved_recipes",
            errors,
        )
        if typography.get("strategy") == "expressive-native" and len(recipes) < 2:
            errors.append("expressive typography requires at least 2 approved construction recipes")
        recipe_ids: set[str] = set()
        for index, recipe_raw in enumerate(recipes):
            recipe = require_dict(recipe_raw, f"approved typography recipe {index}", errors)
            recipe_id = recipe.get("id")
            if not isinstance(recipe_id, str) or not SLUG.fullmatch(recipe_id):
                errors.append(f"approved typography recipe {index} requires a slug id")
            elif recipe_id in recipe_ids:
                errors.append(f"duplicate typography recipe id: {recipe_id}")
            else:
                recipe_ids.add(recipe_id)
            if recipe.get("treatment") not in treatments:
                errors.append(f"approved typography recipe {index} must use an approved treatment")
            techniques = require_list(recipe.get("techniques"), f"approved typography recipe {index}.techniques", errors)
            technique_set = {item for item in techniques if isinstance(item, str)}
            if len(technique_set) < 2:
                errors.append(f"approved typography recipe {index} needs at least 2 non-font construction techniques")
            for technique in sorted(technique_set - ALLOWED_ART_TYPE_TECHNIQUES):
                errors.append(f"approved typography recipe {index} has invalid technique: {technique}")
            minimum_layers = recipe.get("minimum_editable_layers")
            if not isinstance(minimum_layers, int) or isinstance(minimum_layers, bool) or minimum_layers < 2:
                errors.append(f"approved typography recipe {index} minimum_editable_layers must be at least 2")
            if not isinstance(recipe.get("fallback_text_style"), str) or not recipe.get("fallback_text_style"):
                errors.append(f"approved typography recipe {index} requires fallback_text_style")
    elif org.get("status") == "confirmed":
        warnings.append("confirmed organization lacks approved visual calibration; full article production is blocked")

    article_types = require_dict(org.get("article_types"), "organization.article_types", errors)
    for article_type, config_raw in article_types.items():
        config = require_dict(config_raw, f"article type {article_type}", errors)
        if config.get("route") not in route_ids:
            errors.append(f"article type {article_type} references unknown route: {config.get('route')}")
        blocks = require_list(config.get("recommended_blocks"), f"article type {article_type}.recommended_blocks", errors)
        if not blocks:
            errors.append(f"article type {article_type} needs recommended_blocks")

    sources = require_list(sources_doc.get("sources"), "sources.sources", errors)
    facts = require_list(sources_doc.get("facts"), "sources.facts", errors)
    for duplicate in duplicate_ids(sources):
        errors.append(f"duplicate source id: {duplicate}")
    for duplicate in duplicate_ids(facts):
        errors.append(f"duplicate fact id: {duplicate}")
    source_ids = {
        item.get("id") for item in sources if isinstance(item, dict) and item.get("id")
    }
    for source in sources:
        if not isinstance(source, dict):
            continue
        for field in ("id", "title", "kind", "locator"):
            if not source.get(field):
                errors.append(f"source entry missing {field}: {source}")
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        fact_id = fact.get("id", "<missing-id>")
        if not fact.get("claim"):
            errors.append(f"fact missing claim: {fact_id}")
        refs = require_list(fact.get("source_ids"), f"fact {fact_id}.source_ids", errors)
        if not refs:
            errors.append(f"fact has no sources: {fact_id}")
        for source_id in refs:
            if source_id not in source_ids:
                errors.append(f"fact {fact_id} references unknown source: {source_id}")
        if fact.get("confidence") not in {"verified", "reported", "provisional"}:
            errors.append(f"fact {fact_id} has invalid confidence")

    components = require_list(components_doc.get("components"), "components.components", errors)
    for duplicate in duplicate_ids(components):
        errors.append(f"duplicate component id: {duplicate}")
    component_ids = {
        item.get("id") for item in components if isinstance(item, dict) and item.get("id")
    }
    recommendations = require_dict(
        components_doc.get("recommendations"), "components.recommendations", errors
    )
    for article_type, ids_raw in recommendations.items():
        if article_type not in article_types:
            errors.append(f"component recommendations use unknown article type: {article_type}")
        ids = require_list(ids_raw, f"recommendations.{article_type}", errors)
        for component_id in ids:
            if component_id not in component_ids:
                errors.append(f"recommendations.{article_type} references unknown component: {component_id}")

    assets = require_list(assets_doc.get("assets"), "assets.assets", errors)
    for duplicate in duplicate_ids(assets):
        errors.append(f"duplicate asset id: {duplicate}")
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        asset_id = asset.get("id", "<missing-id>")
        for field in ("id", "kind", "title", "location", "origin"):
            if not asset.get(field):
                errors.append(f"asset {asset_id} missing {field}")
        uses = asset.get("uses")
        if not isinstance(uses, list) or any(
            not isinstance(value, str) or not value.strip() for value in uses
        ):
            errors.append(f"asset {asset_id}.uses must be a list of non-empty strings")
        if asset.get("kind") in {"logo", "qr"} and asset.get("origin") not in SAFE_IDENTITY_ORIGINS:
            errors.append(f"asset {asset_id} is {asset.get('kind')} but origin is not official/user-supplied")
        location = asset.get("location")
        if isinstance(location, str) and location and not re.match(r"^(?:https?://|data:)", location):
            if not (pack_dir / location).resolve().exists():
                errors.append(f"missing local asset: {asset_id} -> {location}")
        source_id = asset.get("source_id")
        if source_id and source_id not in source_ids:
            errors.append(f"asset {asset_id} references unknown source: {source_id}")
        roles = asset.get("roles")
        role_items: list[Any] = []
        if roles is not None:
            role_values = require_list(roles, f"asset {asset_id}.roles", errors)
            for role in role_values:
                if not isinstance(role, str) or role not in VISUAL_KIT_ROLES:
                    errors.append(f"asset {asset_id} has unknown visual-kit role: {role}")
                else:
                    role_items.append(role)
        generated_for_articles = asset.get("generated_for_articles")
        if generated_for_articles is not None:
            values = require_list(
                generated_for_articles,
                f"asset {asset_id}.generated_for_articles",
                errors,
            )
            if any(not isinstance(value, str) or not SLUG.fullmatch(value) for value in values):
                errors.append(f"asset {asset_id}.generated_for_articles must contain article slugs")
        visual_role = asset.get("visual_role")
        if visual_role is not None and visual_role not in VISUAL_ASSET_ROLES:
            errors.append(f"asset {asset_id}.visual_role is invalid")
        is_article_micro = visual_role == "article-micro" or bool(role_items)
        if visual_role == "article-micro" and not role_items:
            errors.append(f"article-micro asset {asset_id} requires at least one visual-kit role")
        if is_article_micro:
            quality = asset.get("quality")
            cutout_evidence = quality.get("cutout_evidence") if isinstance(quality, dict) else None
            if (
                not isinstance(quality, dict)
                or quality.get("alpha_verified") is not True
                or quality.get("cutout_verified") is not True
                or not isinstance(cutout_evidence, dict)
            ):
                errors.append(
                    f"article-micro asset {asset_id} lacks stored P0 cutout verification"
                )
            if (
                isinstance(location, str)
                and location
                and not re.match(r"^(?:https?://|data:)", location)
            ):
                candidate = (pack_dir / location).resolve()
                if candidate.is_file():
                    for role in role_items:
                        current = validate_micro_asset(candidate, role)
                        if not current["ok"]:
                            errors.extend(
                                f"article-micro asset {asset_id} cutout gate: {message}"
                                for message in current["errors"]
                            )
                        inspection = current.get("inspection", {})
                        if (
                            not isinstance(quality, dict)
                            or quality.get("sha256") != inspection.get("sha256")
                            or quality.get("width_px") != inspection.get("width_px")
                            or quality.get("height_px") != inspection.get("height_px")
                        ):
                            errors.append(
                                f"article-micro asset {asset_id} stored cutout evidence does not match current pixels"
                            )
                        if not isinstance(cutout_evidence, dict) or any(
                            field not in cutout_evidence
                            or cutout_evidence[field] != inspection.get(field)
                            for field in MICRO_CUTOUT_EVIDENCE_FIELDS
                        ):
                            errors.append(
                                f"article-micro asset {asset_id} detailed cutout evidence does not match current pixels"
                            )
                else:
                    errors.append(f"article-micro asset {asset_id} requires a readable local PNG")
            else:
                errors.append(f"article-micro asset {asset_id} requires a local PNG for cutout verification")
        family_id = asset.get("background_family_id")
        variant = asset.get("background_variant")
        if family_id is not None or variant is not None:
            if asset.get("kind") != "background" or asset.get("origin") != "generated-illustrative":
                errors.append(f"asset {asset_id} background family metadata requires a generated background")
            if not isinstance(family_id, str) or not family_id:
                errors.append(f"asset {asset_id} background_family_id is required")
            if variant not in {"master", "companion"}:
                errors.append(f"asset {asset_id} background_variant must be master or companion")
    asset_registry = {
        item.get("id"): item for item in assets if isinstance(item, dict) and item.get("id")
    }
    if calibration_status == "approved" and isinstance(background_family, dict):
        family_id = background_family.get("id")
        master_id = background_family.get("master_asset_id")
        raw_companion_ids = background_family.get("companion_asset_ids", [])
        companion_ids = raw_companion_ids if isinstance(raw_companion_ids, list) else []
        for asset_id, expected_variant in [
            (master_id, "master"),
            *((asset_id, "companion") for asset_id in companion_ids if isinstance(asset_id, str)),
        ]:
            asset = asset_registry.get(asset_id)
            if not asset:
                errors.append(f"approved background family references unknown asset: {asset_id}")
                continue
            if asset.get("kind") != "background" or asset.get("origin") != "generated-illustrative":
                errors.append(f"background family asset must be a generated background: {asset_id}")
            if asset.get("background_family_id") != family_id:
                errors.append(f"background family asset has mismatched family ID: {asset_id}")
            if asset.get("background_variant") != expected_variant:
                errors.append(
                    f"background family asset {asset_id} must declare background_variant={expected_variant}"
                )
        family_assets: list[tuple[str, Path]] = []
        for asset_id in [master_id, *companion_ids]:
            asset = asset_registry.get(asset_id)
            location = asset.get("location") if isinstance(asset, dict) else None
            if not isinstance(location, str) or re.match(r"^(?:https?://|data:)", location):
                errors.append(f"background family requires a local PNG for tonal analysis: {asset_id}")
                continue
            candidate = (pack_dir / location).resolve()
            if candidate.exists():
                family_assets.append((asset_id, candidate))
        if len(family_assets) == 1 + len(companion_ids):
            background_quality = validate_background_family_assets(
                family_assets,
                surface_mode=background_family.get("surface_mode"),
                copy_safe_zone=background_family.get("copy_safe_zone", {}),
                body_text_color=background_family.get("body_text_color", ""),
                minimum_contrast_ratio=background_family.get("minimum_contrast_ratio", 4.5),
                maximum_copy_safe_stddev=background_family.get("maximum_copy_safe_stddev", 0.10),
            )
            errors.extend(background_quality["errors"])

    provenance = require_dict(org.get("provenance"), "organization.provenance", errors)
    watermark_config = provenance.get("generated_image_watermark")
    if watermark_config is None:
        warnings.append(
            "watermark.migration-needed: organization has no generated_image_watermark policy"
        )
    elif not isinstance(watermark_config, dict):
        errors.append("organization.provenance.generated_image_watermark must be an object")
    else:
        if watermark_config.get("mode") not in WATERMARK_POLICY_MODES:
            errors.append(
                "organization.provenance.generated_image_watermark.mode must be optional or required"
            )
        if watermark_config.get("scheme") != WATERMARK_SCHEME:
            errors.append(
                "organization.provenance.generated_image_watermark.scheme must be "
                + WATERMARK_SCHEME
            )
        key_id = watermark_config.get("key_id")
        if not valid_watermark_key_id(key_id):
            errors.append(
                "organization.provenance.generated_image_watermark.key_id must be a short "
                "lowercase non-secret slug"
            )
    provenance_source_ids = require_list(
        provenance.get("source_ids"),
        "organization.provenance.source_ids",
        errors,
    )
    for source_id in provenance_source_ids:
        if source_id not in source_ids:
            errors.append(f"organization.provenance references unknown source: {source_id}")
    policy = provenance.get("visual_reference_policy")
    if policy is not None and policy not in ALLOWED_VISUAL_REFERENCE_POLICIES:
        errors.append(
            "organization.provenance.visual_reference_policy must be source-zero "
            "or explicit-style-grammar"
        )
    visual_input_source_ids = require_list(
        provenance.get("visual_input_source_ids", []),
        "organization.provenance.visual_input_source_ids",
        errors,
    )
    for source_id in visual_input_source_ids:
        if source_id not in source_ids:
            errors.append(f"organization visual input references unknown source: {source_id}")
    exclusions = require_list(
        provenance.get("excluded_visual_reference_kinds", []),
        "organization.provenance.excluded_visual_reference_kinds",
        errors,
    )
    if policy == "explicit-style-grammar":
        style_reference_source_ids = require_list(
            provenance.get("style_reference_source_ids"),
            "organization.provenance.style_reference_source_ids",
            errors,
        )
        if not style_reference_source_ids:
            errors.append("explicit-style-grammar provenance requires style_reference_source_ids")
        for source_id in style_reference_source_ids:
            if source_id not in source_ids:
                errors.append(f"organization style reference uses unknown source: {source_id}")
            if source_id not in provenance_source_ids:
                errors.append(
                    "organization style reference source must also appear in "
                    f"provenance.source_ids: {source_id}"
                )
        if provenance.get("style_reference_scope") != EXPLICIT_STYLE_REFERENCE_SCOPE:
            errors.append(
                "explicit-style-grammar provenance requires "
                f"style_reference_scope={EXPLICIT_STYLE_REFERENCE_SCOPE}"
            )
        try:
            datetime.fromisoformat(
                str(provenance.get("reference_reviewed_at")).replace("Z", "+00:00")
            )
        except ValueError:
            errors.append("explicit-style-grammar provenance requires ISO reference_reviewed_at")
        non_copy_constraints = require_list(
            provenance.get("style_reference_non_copy_constraints"),
            "organization.provenance.style_reference_non_copy_constraints",
            errors,
        )
        missing_non_copy = sorted(
            REQUIRED_STYLE_NON_COPY_CONSTRAINTS
            - {item for item in non_copy_constraints if isinstance(item, str)}
        )
        if missing_non_copy:
            errors.append(
                "explicit-style-grammar provenance is missing non-copy constraints: "
                + ", ".join(missing_non_copy)
            )
        grammar_count = 0
        for index, route in enumerate(routes):
            route_id = route.get("id", str(index)) if isinstance(route, dict) else str(index)
            grammar = route.get("style_grammar") if isinstance(route, dict) else None
            if grammar is None:
                continue
            grammar_errors = style_grammar_errors(
                grammar,
                f"visual route {route_id}.style_grammar",
            )
            errors.extend(grammar_errors)
            if not grammar_errors:
                grammar_count += 1
        if grammar_count == 0:
            errors.append(
                "explicit-style-grammar requires at least one route.style_grammar selection"
            )
    if org.get("status") == "confirmed":
        if policy not in ALLOWED_VISUAL_REFERENCE_POLICIES:
            errors.append(
                "confirmed organization requires source-zero or explicit-style-grammar provenance"
            )
        if not visual_input_source_ids:
            errors.append("confirmed organization requires visual_input_source_ids")
        if policy == "source-zero":
            missing_exclusions = sorted(SOURCE_ZERO_EXCLUSIONS - set(exclusions))
            if missing_exclusions:
                errors.append(
                    "confirmed organization is missing excluded visual reference kinds: "
                    + ", ".join(missing_exclusions)
                )
            isolation_reviewed_at = provenance.get("isolation_reviewed_at")
            try:
                datetime.fromisoformat(str(isolation_reviewed_at).replace("Z", "+00:00"))
            except ValueError:
                errors.append("confirmed organization requires ISO isolation_reviewed_at")
    elif policy not in ALLOWED_VISUAL_REFERENCE_POLICIES:
        warnings.append(
            "organization lacks a valid visual reference policy; full article production is blocked"
        )

    ardot_status = ardot_doc.get("status")
    if ardot_status not in {"not-linked", "linked"}:
        errors.append("ardot.status must be not-linked or linked")
    for field in ("variable_set", "variable_mode"):
        if not isinstance(ardot_doc.get(field), str) or not ardot_doc.get(field, "").strip():
            errors.append(f"ardot.{field} must be a non-empty string")
    design_file = require_dict(ardot_doc.get("design_file"), "ardot.design_file", errors)
    if ardot_status == "linked":
        file_url = design_file.get("url")
        if not isinstance(file_url, str) or not re.match(r"^https?://", file_url):
            errors.append("linked ardot.design_file.url must be an http(s) URL")
    require_dict(ardot_doc.get("page_names"), "ardot.page_names", errors)
    require_dict(ardot_doc.get("component_aliases"), "ardot.component_aliases", errors)

    watermark_status = watermark_inventory(org, assets_doc, pack_dir)
    errors.extend(watermark_status["errors"])
    warnings.extend(watermark_status["warnings"])

    return {
        "ok": not errors,
        "path": str(pack_dir.resolve()),
        "organization_id": org_id,
        "status": org.get("status"),
        "visual_calibration": {
            "status": calibration_status,
            "approved_routes": approved_routes,
            "background_family_quality": background_quality,
        },
        "provenance_watermark": watermark_status,
        "counts": {
            "routes": len(routes),
            "article_types": len(article_types),
            "sources": len(sources),
            "facts": len(facts),
            "components": len(components),
            "assets": len(assets),
        },
        "errors": list(dict.fromkeys(errors)),
        "warnings": list(dict.fromkeys(warnings)),
    }


def scaffold(org_id: str, name: str) -> dict[str, Any]:
    organization = {
        "schema_version": 1,
        "id": org_id,
        "status": "provisional",
        "identity": {
            "name": name,
            "short_name": name,
            "summary": "待调研确认的组织简介",
            "category": "待确认",
            "audiences": ["待确认核心受众"],
            "content_pillars": ["待确认内容支柱"],
        },
        "personality": {
            "authority": 50,
            "technical": 50,
            "warmth": 50,
            "experimental": 50,
            "action": 50,
        },
        "voice": {
            "traits": ["待调研确认"],
            "headline_patterns": [],
            "preferred_terms": [],
            "avoid_terms": ["夸大且无证据的表达"],
        },
        "visual": {
            "tokens": {
                "ink": "#111111",
                "body": "#4A4A4A",
                "accent": "#1F5EFF",
                "accent_alt": "#FFD84D",
                "surface": "#FFFFFF",
                "surface_alt": "#F4F2EC",
                "border": "#111111",
                "white": "#FFFFFF",
            },
            "motifs": ["待调研确认"],
            "avoid": ["通用科技光效", "生成中文", "虚假仪表盘"],
            "default_route": "provisional-editorial",
            "routes": [
                {
                    "id": "provisional-editorial",
                    "label": "待确认编辑路线",
                    "uses": ["introduction"],
                    "layout": "editorial",
                    "dominant_style": "evidence-led-editorial",
                    "rationale": "仅作为调研期间的中性起点，不代表组织最终品牌。",
                }
            ],
        },
        "article_types": {
            "introduction": {
                "label": "组织介绍",
                "route": "provisional-editorial",
                "recommended_blocks": [
                    "hero",
                    "lead",
                    "section",
                    "text",
                    "gallery",
                    "cta",
                    "footer",
                ],
            }
        },
        "asset_policy": {
            "logo": "official-or-user-supplied-only",
            "qr": "official-or-user-supplied-only",
            "photography": "prefer-real-for-real-people-and-events",
            "generation": "text-free-illustrative-only",
        },
        "publishing": {
            "authoring": "ardot-native",
            "delivery": "wechat-inline-html",
            "default_action": "draft-only",
            "formal_publish_requires_confirmation": True,
            "interaction_policy": {
                "default_payload": "static",
                "policy_version": "wechat-svg-smil-self-v1",
                "candidate_modes": ["svg-smil-self", "horizontal-swipe"],
                "requires_static_fallback": True,
                "account_capability_profile_location": "delivery-environment-only",
            },
        },
        "provenance": {
            "source_ids": [],
            "reviewed_at": None,
            "notes": "待完成首次组织调研",
            "visual_reference_policy": "source-zero",
            "visual_input_source_ids": [],
            "excluded_visual_reference_kinds": [
                "prior-article-layout",
                "prior-ardot-file",
                "prior-article-screenshot",
                "other-organization-visual-pack",
            ],
            "isolation_reviewed_at": None,
            "generated_image_watermark": {
                "mode": "required",
                "scheme": WATERMARK_SCHEME,
                "key_id": "external",
            },
        },
    }
    organization["visual"] = {
        "tokens": {
            "ink": "#263238", "body": "#526269", "accent": "#527B8C",
            "accent_alt": "#E9C46A", "surface": "#FFFFFF", "surface_alt": "#F4F7F8",
            "border": "#CBD7DB", "white": "#FFFFFF",
        },
        "motifs": ["待调研组织物件与行动"],
        "avoid": ["泛化 AI 光效", "与正文无关的装饰"],
        "default_route": "provisional-editorial",
        "routes": [{
            "id": "provisional-editorial", "label": "待校准编辑方向", "uses": ["introduction"],
            "layout": "editorial", "dominant_style": "organization-specific-editorial",
            "component_variants": {}, "rationale": "仅用于生成校准样张，未批准前不得制作全文。",
        }],
        "calibration": {
            "status": "not-started", "approved_routes": [], "benchmark": None,
            "density_mode": "compact-editorial", "background_family": None,
            "typography": {
                "strategy": "calibrate",
                "editable_text_required": True,
                "font_policy": "licensed-or-system-only",
                "body_copy_remains_standard": True,
                "approved_treatments": [],
                "approved_recipes": [],
                "maximum_moments_per_article": 4,
            },
            "reviewed_at": None, "review_basis": [],
        },
    }
    sources = {"schema_version": 1, "organization_id": org_id, "sources": [], "facts": []}
    components = {
        "schema_version": 1,
        "organization_id": org_id,
        "components": [
            {"id": f"core.{kind}", "kind": kind, "title": kind.replace("-", " ").title(), "uses": ["all"]}
            for kind in (
                "hero",
                "lead",
                "section",
                "text",
                "gallery",
                "cta",
                "footer",
            )
        ],
        "recommendations": {
            "introduction": [
                "core.hero",
                "core.lead",
                "core.section",
                "core.text",
                "core.gallery",
                "core.cta",
                "core.footer",
            ]
        },
    }
    assets = {"schema_version": 1, "organization_id": org_id, "assets": []}
    ardot = {
        "schema_version": 1,
        "organization_id": org_id,
        "status": "not-linked",
        "design_file": {"url": None, "file_id": None},
        "variable_set": "Org WeChat Brand",
        "variable_mode": org_id,
        "page_names": {
            "foundations": "00 Foundations",
            "components": "01 Components",
            "example": f"Calibration / {name}",
        },
        "component_aliases": {},
    }
    return {
        "organization.json": organization,
        "sources.json": sources,
        "components.json": components,
        "assets.json": assets,
        "ardot.json": ardot,
    }


def command_init(args: argparse.Namespace) -> None:
    if not SLUG.fullmatch(args.organization_id):
        raise SystemExit("organization ID must be a lowercase hyphenated slug")
    destination = (args.root / args.organization_id).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit(f"destination already exists and is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    for filename, value in scaffold(args.organization_id, args.name).items():
        write_json(destination / filename, value)
    asset_directories = [
        destination / "assets" / "official",
        destination / "assets" / "photos",
        destination / "assets" / "generated",
        destination / "assets" / "derived",
    ]
    for directory in asset_directories:
        directory.mkdir(parents=True, exist_ok=True)
    print(
        json.dumps(
            {
                "created": str(destination),
                "status": "provisional",
                "asset_directories": [str(path) for path in asset_directories],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def command_list(args: argparse.Namespace) -> None:
    roots = args.root or [Path.cwd() / "organizations"]
    results: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for root in roots:
        root = root.resolve()
        if root in seen or not root.exists():
            continue
        seen.add(root)
        for org_file in sorted(root.glob("*/organization.json")):
            org = read_json(org_file)
            results.append(
                {
                    "id": org.get("id"),
                    "name": org.get("identity", {}).get("name"),
                    "status": org.get("status"),
                    "path": str(org_file.parent),
                }
            )
    print(json.dumps(results, ensure_ascii=False, indent=2))


def command_validate(args: argparse.Namespace) -> None:
    report = validate_pack(args.pack)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


def command_show(args: argparse.Namespace) -> None:
    pack = load_pack(args.pack)
    org = pack["organization"]
    print(
        json.dumps(
            {
                "path": str(pack["path"]),
                "id": org["id"],
                "status": org["status"],
                "identity": org["identity"],
                "personality": org["personality"],
                "default_route": org["visual"]["default_route"],
                "routes": org["visual"]["routes"],
                "article_types": org["article_types"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def command_recommend(args: argparse.Namespace) -> None:
    pack = load_pack(args.pack)
    org = pack["organization"]
    article_types = org["article_types"]
    if args.article_type not in article_types:
        available = ", ".join(sorted(article_types))
        raise SystemExit(f"unknown article type: {args.article_type}; available: {available}")
    article_config = article_types[args.article_type]
    route_map = {route["id"]: route for route in org["visual"]["routes"]}
    component_map = {item["id"]: item for item in pack["components"]["components"]}
    recommendation_ids = pack["components"].get("recommendations", {}).get(args.article_type, [])
    print(
        json.dumps(
            {
                "organization_id": org["id"],
                "article_type": args.article_type,
                "article_config": article_config,
                "route": route_map.get(article_config["route"]),
                "components": [component_map[item_id] for item_id in recommendation_ids if item_id in component_map],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def searchable_text(item: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("id", "kind", "title", "style", "origin", "location"):
        value = item.get(key)
        if value is not None:
            values.append(str(value))
    for key in ("uses", "subjects", "tags"):
        value = item.get(key)
        if isinstance(value, list):
            values.extend(str(part) for part in value)
    return " ".join(values).lower()


def command_search(args: argparse.Namespace) -> None:
    pack = load_pack(args.pack)
    terms = [term.lower() for term in args.query.split() if term.strip()]
    results: list[dict[str, Any]] = []
    for registry_name in ("components", "assets"):
        for item in pack[registry_name][registry_name]:
            haystack = searchable_text(item)
            if all(term in haystack for term in terms):
                results.append({"registry": registry_name, **item})
    print(json.dumps(results, ensure_ascii=False, indent=2))


def matching_assets(
    pack: dict[str, Any], article_type: str, kinds: set[str]
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for item in pack["assets"].get("assets", []):
        if not isinstance(item, dict) or item.get("kind") not in kinds:
            continue
        uses = item.get("uses", [])
        if article_type in uses or "all" in uses or item.get("kind") in {"logo", "qr"}:
            matches.append(item)
    return matches


def prompt_blueprint(
    org: dict[str, Any],
    route: dict[str, Any],
    article_type: str,
    slot: str,
    aspect_ratio: str,
) -> str:
    tokens = org["visual"]["tokens"]
    palette = ", ".join(
        f"{name} {tokens[name]}"
        for name in ("ink", "accent", "accent_alt", "surface", "surface_alt")
    )
    motifs = "、".join(org["visual"].get("motifs", []))
    avoid = "、".join(org["visual"].get("avoid", []))
    style_grammar_instruction = style_grammar_prompt(org, route)
    return (
        f"Create a text-free {slot} bitmap for {org['identity']['name']} and its "
        f"{article_type} WeChat article. Use the {route['dominant_style']} route; "
        f"motifs: {motifs}; palette: {palette}; aspect ratio {aspect_ratio}; "
        f"{style_grammar_instruction}"
        f"keep a deliberate empty overlay zone and make the subject readable on a phone. "
        f"Avoid: {avoid}. No visible letters, numbers, watermark, signature, logo, or QR code. "
        "A hidden provenance watermark is applied by the workflow after generation."
    )


def style_grammar_prompt(org: dict[str, Any], route: dict[str, Any]) -> str:
    if org.get("provenance", {}).get("visual_reference_policy") != "explicit-style-grammar":
        return ""
    grammar = route.get("style_grammar")
    if not isinstance(grammar, dict):
        return ""
    tokens = json.dumps(
        grammar.get("tokens", {}),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        f"Apply only abstract style grammar {tokens} (SHA-256 {grammar.get('sha256')}); "
        "never copy reference text, photographs, logos, specific layout, component geometry, "
        "or artwork. "
    )


def micro_prompt_blueprint(
    org: dict[str, Any],
    route: dict[str, Any],
    article_type: str,
    purpose: str,
    aspect_ratio: str,
) -> str:
    tokens = org["visual"]["tokens"]
    palette = ", ".join(
        f"{name} {tokens[name]}"
        for name in ("ink", "accent", "accent_alt", "surface_alt")
    )
    motifs = "、".join(org["visual"].get("motifs", []))
    avoid = "、".join(org["visual"].get("avoid", []))
    style_grammar_instruction = style_grammar_prompt(org, route)
    return (
        f"Create one small, text-free {purpose} for {org['identity']['name']} and a "
        f"{article_type} WeChat article. Derive the subject from the article's concrete "
        f"objects, actions, or process rather than generic decoration. Follow the "
        f"{route['dominant_style']} route; motifs: {motifs}; palette: {palette}; aspect "
        f"ratio {aspect_ratio}. {style_grammar_instruction}"
        f"Use a transparent background or an open, soft-edged "
        f"composition with no rectangular panel, border, card, poster, UI frame, letters, "
        f"visible numbers, watermark, signature, logo, or QR code. Avoid: {avoid}. "
        "Hidden provenance marking, if any, is handled separately by workflow policy; "
        "this transparent micro asset remains unmarked in V1."
    )


def build_asset_plan(pack_dir: Path, article_type: str) -> dict[str, Any]:
    pack = load_pack(pack_dir)
    org = pack["organization"]
    article_types = org.get("article_types", {})
    if article_type not in article_types:
        available = ", ".join(sorted(article_types))
        raise ValueError(f"unknown article type: {article_type}; available: {available}")
    article_config = article_types[article_type]
    route_map = {route["id"]: route for route in org["visual"]["routes"]}
    route = route_map[article_config["route"]]
    style_grammar = (
        route.get("style_grammar")
        if org.get("provenance", {}).get("visual_reference_policy") == "explicit-style-grammar"
        else None
    )
    route_reference_policy = (
        "explicit-style-grammar" if isinstance(style_grammar, dict) else "source-zero"
    )
    blocks = set(article_config.get("recommended_blocks", []))
    slots: list[dict[str, Any]] = []

    def add_slot(
        slot_id: str,
        purpose: str,
        kinds: set[str],
        policy: str,
        aspect_ratio: str,
        required: bool,
        generate_allowed: bool,
        force_generate: bool = False,
        micro_component: bool = False,
    ) -> None:
        candidates = matching_assets(pack, article_type, kinds)
        if force_generate:
            status = "generate-required"
        elif candidates:
            status = "reuse-available"
        elif generate_allowed:
            status = "generate-or-source"
        else:
            status = "user-or-official-asset-required"
        if generate_allowed:
            suggested_directory = "assets/generated"
        elif kinds & {"logo", "qr"}:
            suggested_directory = "assets/official"
        else:
            suggested_directory = "assets/photos"
        slot: dict[str, Any] = {
            "id": slot_id,
            "purpose": purpose,
            "required": required,
            "status": status,
            "policy": policy,
            "aspect_ratio": aspect_ratio,
            "existing_candidates": [item["id"] for item in candidates],
            "suggested_directory": suggested_directory,
            "micro_component": micro_component,
        }
        if generate_allowed:
            prompt_builder = micro_prompt_blueprint if micro_component else prompt_blueprint
            slot["prompt_blueprint"] = prompt_builder(org, route, article_type, purpose, aspect_ratio)
        slots.append(slot)

    for slot_id, purpose, aspect_ratio in (
        ("kit.floating-spot", "floating spot illustration", "1:1 transparent"),
        ("kit.section-transition", "flowing section transition illustration", "4:1 transparent"),
        ("kit.inline-explainer", "small inline explanatory illustration", "4:3 open composition"),
        ("kit.closing-motif", "closing motif beside the call to action", "1:1 transparent"),
    ):
        add_slot(
            slot_id,
            purpose,
            {"illustration", "decoration"},
            "Generate before layout; keep it text-free, open-edged, and article-specific.",
            aspect_ratio,
            required=True,
            generate_allowed=True,
            force_generate=True,
            micro_component=True,
        )

    add_slot(
        "visual.hero",
        "cover or opening background",
        {"background", "illustration"},
        "Reuse a registered visual first; generated art must be text-free and illustrative.",
        "2:3 portrait",
        required=False,
        generate_allowed=True,
    )
    if "image" in blocks or "section" in blocks:
        add_slot(
            "visual.section",
            "major section visual",
            {"background", "illustration", "decoration"},
            "Use real evidence for real projects; otherwise a text-free explanatory visual is allowed.",
            "3:2 landscape",
            required=False,
            generate_allowed=True,
        )
    if "gallery" in blocks:
        add_slot(
            "photo.gallery",
            "people, event, project, or process gallery",
            {"photo"},
            "Use supplied or officially sourced photographs for real people, events, and projects.",
            "3:2 landscape",
            required=True,
            generate_allowed=False,
        )
    if "case" in blocks:
        add_slot(
            "photo.case-evidence",
            "project or case evidence",
            {"photo"},
            "Prefer real project evidence; generated imagery cannot stand in for claimed results.",
            "3:2 landscape",
            required=False,
            generate_allowed=False,
        )
    add_slot(
        "brand.logo",
        "canonical organization identity",
        {"logo"},
        "Official or user-supplied only; never redraw or generate.",
        "original",
        required=True,
        generate_allowed=False,
    )
    if "cta" in blocks:
        add_slot(
            "brand.qr",
            "registration or follow call to action",
            {"qr"},
            "Official or user-supplied only; never create or replace a QR code.",
            "1:1",
            required=False,
            generate_allowed=False,
        )
    return {
        "schema_version": 1,
        "organization_id": org["id"],
        "organization_name": org["identity"]["name"],
        "article_type": article_type,
        "route": route,
        "style_reference_policy": route_reference_policy,
        "style_grammar": style_grammar,
        "style_grammar_sha256": (
            style_grammar.get("sha256") if isinstance(style_grammar, dict) else None
        ),
        "style_preset_id": (
            style_grammar.get("preset_id") if isinstance(style_grammar, dict) else None
        ),
        "style_preset_label": (
            style_grammar.get("label") if isinstance(style_grammar, dict) else None
        ),
        "visual_tokens": org["visual"]["tokens"],
        "motifs": org["visual"].get("motifs", []),
        "avoid": org["visual"].get("avoid", []),
        "slots": slots,
        "rules": [
            "Generate and approve all four micro-component slots before assembling the article layout.",
            "Use four distinct article-specific micro assets; one bitmap cannot satisfy two roles.",
            "Run inspect_asset.py for each micro asset and require decoded PNG Alpha with real transparent pixels.",
            "Turn the approved micro illustrations into reusable Ardot spot, transition, explainer, and closing components before composing the long article.",
            "Record each native Ardot component file URL, node ID, and exact name on the article visual-kit item.",
            "Use only the calibrated background family master and companions for AI atmosphere continuity.",
            "Real photographs carry documentary evidence; generated backgrounds carry atmosphere and never substitute for events or outcomes.",
            "Generated images must not contain Chinese copy, dates, metrics, logos, or QR codes.",
            "Inspect every generated asset before registration.",
            "Register approved files in assets.json before article compilation.",
            "Do not compensate for missing visuals by wrapping text blocks in cards or bordered containers.",
        ],
    }


def command_asset_plan(args: argparse.Namespace) -> None:
    plan = build_asset_plan(args.pack, args.article_type)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.output, plan)
        print(
            json.dumps(
                {"created": str(args.output.resolve()), "slots": len(plan["slots"])},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(json.dumps(plan, ensure_ascii=False, indent=2))


def command_register_asset(args: argparse.Namespace) -> None:
    if args.kind in {"logo", "qr"} and args.origin not in SAFE_IDENTITY_ORIGINS:
        raise SystemExit("logo and QR assets must be official or user-supplied")
    location = args.location
    if not re.match(r"^(?:https?://|data:)", location):
        candidate = (args.pack / location).resolve()
        if not candidate.exists() or not candidate.is_file():
            raise SystemExit(f"asset file does not exist: {candidate}")
    else:
        candidate = None
    roles = getattr(args, "role", None) or []
    if roles:
        if args.origin != "generated-illustrative":
            raise SystemExit("micro-visual roles require generated-illustrative origin")
        if args.kind not in {"illustration", "decoration"}:
            raise SystemExit("micro-visual roles require illustration or decoration kind")
        if candidate is None:
            raise SystemExit("micro-visual alpha verification requires a local PNG file")
        quality_reports = [validate_micro_asset(candidate, role) for role in roles]
        failures = [error for report in quality_reports for error in report["errors"]]
        if failures:
            raise SystemExit("micro-visual quality check failed: " + "; ".join(failures))
    else:
        quality_reports = []
    background_family_id = getattr(args, "background_family_id", None)
    background_variant = getattr(args, "background_variant", None)
    visual_role = getattr(args, "visual_role", None)
    if background_family_id or background_variant:
        if args.kind != "background" or args.origin != "generated-illustrative":
            raise SystemExit("background family metadata requires a generated-illustrative background")
        if not background_family_id or not background_variant:
            raise SystemExit("use --background-family-id and --background-variant together")
    if args.kind == "photo" and visual_role == "documentary-evidence" and not args.source_id:
        raise SystemExit("documentary photo registration requires --source-id")
    assets_path = args.pack / "assets.json"
    document = read_json(assets_path)
    items = document.setdefault("assets", [])
    if any(item.get("id") == args.asset_id for item in items if isinstance(item, dict)):
        raise SystemExit(f"asset ID already exists: {args.asset_id}")
    item = {
        "id": args.asset_id,
        "kind": args.kind,
        "title": args.title,
        "location": location,
        "style": args.style,
        "uses": args.use or ["all"],
        "origin": args.origin,
    }
    if roles:
        item["roles"] = roles
        inspection = quality_reports[0]["inspection"]
        item["quality"] = {
            "alpha_verified": True,
            "cutout_verified": True,
            "sha256": inspection["sha256"],
            "width_px": inspection["width_px"],
            "height_px": inspection["height_px"],
            "transparent_pixel_ratio": inspection["transparent_pixel_ratio"],
            # Persist the actual gate evidence.  This makes an approved asset
            # auditable after it has been placed in an Ardot component, instead of
            # reducing the decision to an untraceable `alpha_verified` flag.
            "cutout_evidence": {
                field: inspection[field] for field in MICRO_CUTOUT_EVIDENCE_FIELDS
            },
        }
    if getattr(args, "generated_for", None):
        if args.origin != "generated-illustrative":
            raise SystemExit("--generated-for is only valid for generated-illustrative assets")
        item["generated_for_articles"] = args.generated_for
    if args.source_id:
        item["source_id"] = args.source_id
    if visual_role:
        item["visual_role"] = visual_role
    if background_family_id:
        item["background_family_id"] = background_family_id
        item["background_variant"] = background_variant
    watermark_requirement = asset_watermark_requirement(item, candidate)
    watermark_report_path = getattr(args, "watermark_report", None)
    watermark_source_path = getattr(args, "watermark_source", None)
    if watermark_requirement["in_scope"] and not watermark_requirement["eligible"]:
        reasons = ", ".join(watermark_requirement.get("reasons", []))
        raise SystemExit(
            "watermark.carrier.ineligible: generated background/cover must use a qualifying "
            f"opaque PNG carrier ({reasons})"
        )
    if watermark_requirement["eligible"]:
        if candidate is None:
            raise SystemExit("eligible watermark carriers must be local raster files")
        if watermark_report_path is None or watermark_source_path is None:
            raise SystemExit(
                "eligible generated backgrounds and generated covers require --watermark-source "
                "and --watermark-report; embed a new marked derivative before registration"
            )
        policy = watermark_policy(read_json(args.pack / "organization.json"))
        if (
            not policy["declared"]
            or policy.get("mode") not in WATERMARK_POLICY_MODES
            or policy.get("scheme") != WATERMARK_SCHEME
            or not valid_watermark_key_id(policy.get("key_id"))
        ):
            raise SystemExit(
                "declare organization.provenance.generated_image_watermark before registering "
                "an eligible carrier"
            )
        pack_root = args.pack.resolve()
        watermark_report_path = Path(watermark_report_path)
        if not watermark_report_path.is_absolute():
            watermark_report_path = pack_root / watermark_report_path
        watermark_report_path = watermark_report_path.resolve()
        watermark_source_path = Path(watermark_source_path)
        if not watermark_source_path.is_absolute():
            watermark_source_path = pack_root / watermark_source_path
        watermark_source_path = watermark_source_path.resolve()
        for label, path in (
            ("marked asset", candidate),
            ("watermark source", watermark_source_path),
            ("watermark report", watermark_report_path),
        ):
            try:
                path.relative_to(pack_root)
            except ValueError as exc:
                raise SystemExit(f"{label} must stay inside the organization pack") from exc
        try:
            watermark_report = read_json(watermark_report_path)
            if not isinstance(watermark_report, dict):
                raise ValueError("watermark report must be a JSON object")
            item["watermark"] = watermark_evidence_from_report(
                watermark_report,
                watermark_report_path,
                candidate,
                pack_dir=pack_root,
                source_path=watermark_source_path,
                key_id=str(policy["key_id"]),
            )
            from provenance_watermark import detect_watermark

            source_detection = detect_watermark(watermark_source_path)
            if source_detection.get("authenticated") is True:
                raise ValueError("watermark source must be an unwatermarked master")
            watermark_check = validate_asset_watermark(
                item,
                candidate,
                expected_scheme=str(policy["scheme"]),
                expected_key_id=str(policy["key_id"]),
                pack_dir=pack_root,
                require_evidence=True,
            )
        except ValueError as exc:
            raise SystemExit(f"watermark evidence validation failed: {exc}") from exc
        if watermark_check["errors"]:
            raise SystemExit(
                "watermark evidence validation failed: "
                + "; ".join(watermark_check["errors"])
            )
    elif watermark_report_path is not None or watermark_source_path is not None:
        raise SystemExit(
            "--watermark-source/--watermark-report are only valid for eligible local opaque "
            "generated backgrounds or generated covers"
        )
    items.append(item)
    write_json(assets_path, document)
    report = validate_pack(args.pack)
    if not report["ok"]:
        items.pop()
        write_json(assets_path, document)
        raise SystemExit(
            "asset registration failed validation: " + "; ".join(report["errors"])
        )
    print(
        json.dumps(
            {"registered": item, "asset_count": len(items)},
            ensure_ascii=False,
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a provisional organization pack")
    init_parser.add_argument("organization_id")
    init_parser.add_argument("--name", required=True)
    init_parser.add_argument("--root", type=Path, default=Path.cwd() / "organizations")
    init_parser.set_defaults(func=command_init)

    list_parser = subparsers.add_parser("list", help="List discoverable organization packs")
    list_parser.add_argument("--root", action="append", type=Path)
    list_parser.set_defaults(func=command_list)

    validate_parser = subparsers.add_parser("validate", help="Validate an organization pack")
    validate_parser.add_argument("pack", type=Path)
    validate_parser.set_defaults(func=command_validate)

    show_parser = subparsers.add_parser("show", help="Show organization identity and routes")
    show_parser.add_argument("pack", type=Path)
    show_parser.set_defaults(func=command_show)

    recommend_parser = subparsers.add_parser("recommend", help="Recommend a route and components")
    recommend_parser.add_argument("pack", type=Path)
    recommend_parser.add_argument("article_type")
    recommend_parser.set_defaults(func=command_recommend)

    search_parser = subparsers.add_parser("search", help="Search components and assets")
    search_parser.add_argument("pack", type=Path)
    search_parser.add_argument("query")
    search_parser.set_defaults(func=command_search)

    plan_parser = subparsers.add_parser(
        "asset-plan", help="Build a route-specific asset plan for an article type"
    )
    plan_parser.add_argument("pack", type=Path)
    plan_parser.add_argument("article_type")
    plan_parser.add_argument("--output", type=Path)
    plan_parser.set_defaults(func=command_asset_plan)

    register_parser = subparsers.add_parser(
        "register-asset", help="Register an approved asset in an organization pack"
    )
    register_parser.add_argument("pack", type=Path)
    register_parser.add_argument("--id", dest="asset_id", required=True)
    register_parser.add_argument("--kind", choices=sorted(ASSET_KINDS), required=True)
    register_parser.add_argument("--title", required=True)
    register_parser.add_argument("--location", required=True)
    register_parser.add_argument("--origin", choices=sorted(ASSET_ORIGINS), required=True)
    register_parser.add_argument("--style", required=True)
    register_parser.add_argument("--use", action="append")
    register_parser.add_argument("--role", action="append", choices=sorted(VISUAL_KIT_ROLES))
    register_parser.add_argument(
        "--generated-for",
        action="append",
        help="Article slug this illustration was freshly generated for",
    )
    register_parser.add_argument("--source-id")
    register_parser.add_argument("--visual-role", choices=sorted(VISUAL_ASSET_ROLES))
    register_parser.add_argument("--background-family-id")
    register_parser.add_argument("--background-variant", choices=("master", "companion"))
    register_parser.add_argument(
        "--watermark-source",
        type=Path,
        help="Pack-local unwatermarked master used to create the marked derivative",
    )
    register_parser.add_argument(
        "--watermark-report",
        type=Path,
        help="Public local_verified report created while embedding this marked derivative",
    )
    register_parser.set_defaults(func=command_register_asset)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except ValueError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

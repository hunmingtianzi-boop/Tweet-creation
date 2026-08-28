#!/usr/bin/env python3
"""Shared quality gates for organization calibration and article authoring."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from asset_quality import file_sha256, inspect_png


SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REQUIRED_VISUAL_CHECKS = {
    "subject_relevance",
    "style_coherence",
    "no_clipped_ornaments",
    "scale_variation",
    "photo_illustration_harmony",
    "no_generic_ai_decoration",
    "no_unexplained_labels",
    "editorial_rhythm",
    "mobile_legibility",
    "open_composition",
    "information_density",
    "background_family_coherence",
    "expressive_typography",
    "no_baked_art_text",
    "art_type_construction",
    "background_surface_unity",
    "reading_surface_contrast",
}
REQUIRED_SCREENSHOT_ROLES = {"hero", "chapter", "evidence", "complex-section", "cta"}
ALLOWED_DENSITY_MODES = {"compact-editorial", "standard", "spacious-feature"}
DENSITY_BANDS = {
    "compact-editorial": {
        "body_font_px": (15.0, 17.0),
        "body_line_height_ratio": (1.45, 1.62),
        "letter_spacing_px": (-0.2, 0.0),
        "paragraph_gap_px": (8.0, 14.0),
        "major_gap_px": (24.0, 40.0),
    },
    "standard": {
        "body_font_px": (15.0, 17.0),
        "body_line_height_ratio": (1.50, 1.68),
        "letter_spacing_px": (-0.1, 0.0),
        "paragraph_gap_px": (10.0, 16.0),
        "major_gap_px": (28.0, 48.0),
    },
    "spacious-feature": {
        "body_font_px": (16.0, 18.0),
        "body_line_height_ratio": (1.55, 1.72),
        "letter_spacing_px": (0.0, 0.1),
        "paragraph_gap_px": (12.0, 20.0),
        "major_gap_px": (40.0, 64.0),
    },
}
ALLOWED_COMPOSITION_ROLES = {"anchor", "motion", "connector", "punctuation"}
ALLOWED_TYPOGRAPHY_STRATEGIES = {"expressive-native", "restrained-native"}
ALLOWED_ART_TYPE_ROLES = {"hero-title", "chapter-title", "statement", "key-phrase", "cta-title"}
ALLOWED_ART_TYPE_TREATMENTS = {
    "mixed-weight",
    "stacked-title",
    "baseline-shift",
    "stroke-offset",
    "outline-shadow",
    "hand-drawn-accent",
    "compressed-display",
    "vertical-accent",
}
ALLOWED_ART_TYPE_TECHNIQUES = {
    "intentional-line-break",
    "scale-contrast",
    "baseline-offset",
    "rotation",
    "color-contrast",
    "mixed-weight",
    "outline-layer",
    "offset-layer",
    "vector-accent",
    "vertical-flow",
}
GENERIC_VISUAL_SUBJECTS = {
    "ai",
    "ai科技",
    "科技",
    "创新",
    "未来",
    "想法",
    "模块",
    "箭头",
    "装饰",
    "technology",
    "innovation",
    "future",
    "idea",
    "module",
    "arrow",
    "decoration",
}
GENERIC_SUBJECT_PATTERN = re.compile(
    r"^(?:ai|人工智能|科技|创新|未来|生态|数字)"
    r"(?:图标|符号|装饰|模块|节点|箭头|光球|界面|芯片|大脑|网络)?$",
    re.I,
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


REQUIRED_SOURCE_ZERO_EXCLUSIONS = {
    "prior-article-layout",
    "prior-ardot-file",
    "prior-article-screenshot",
    "other-organization-visual-pack",
}


def _is_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def source_isolation_state(organization: dict[str, Any]) -> dict[str, Any]:
    provenance = organization.get("provenance")
    if not isinstance(provenance, dict):
        provenance = {}
    reasons: list[str] = []
    if provenance.get("visual_reference_policy") != "source-zero":
        reasons.append("organization provenance must use visual_reference_policy=source-zero")
    visual_inputs = provenance.get("visual_input_source_ids")
    if not isinstance(visual_inputs, list) or not visual_inputs or not all(
        isinstance(item, str) and item for item in visual_inputs
    ):
        reasons.append("source-zero provenance requires visual_input_source_ids")
        visual_inputs = []
    exclusions = provenance.get("excluded_visual_reference_kinds")
    exclusion_set = {item for item in exclusions if isinstance(item, str)} if isinstance(exclusions, list) else set()
    missing_exclusions = sorted(REQUIRED_SOURCE_ZERO_EXCLUSIONS - exclusion_set)
    if missing_exclusions:
        reasons.append(
            "source-zero provenance is missing excluded visual reference kinds: "
            + ", ".join(missing_exclusions)
        )
    if not _is_iso_datetime(provenance.get("isolation_reviewed_at")):
        reasons.append("source-zero provenance requires isolation_reviewed_at")
    return {
        "ready": not reasons,
        "policy": provenance.get("visual_reference_policy", "missing"),
        "visual_input_source_ids": visual_inputs,
        "excluded_visual_reference_kinds": sorted(exclusion_set),
        "blocking_reasons": reasons,
    }


def background_family_state(
    organization: dict[str, Any], assets_doc: dict[str, Any] | None = None
) -> dict[str, Any]:
    calibration = organization.get("visual", {}).get("calibration")
    family = calibration.get("background_family") if isinstance(calibration, dict) else None
    reasons: list[str] = []
    if not isinstance(family, dict):
        family = {}
        reasons.append("visual calibration requires a generated background_family")
    if family.get("strategy") != "generated-family":
        reasons.append("background_family.strategy must be generated-family")
    family_id = family.get("id")
    if not isinstance(family_id, str) or not family_id.strip():
        reasons.append("background_family.id is required")
    master_id = family.get("master_asset_id")
    companions = family.get("companion_asset_ids")
    if not isinstance(master_id, str) or not master_id:
        reasons.append("background_family.master_asset_id is required")
    if not isinstance(companions, list) or not 1 <= len(companions) <= 3 or not all(
        isinstance(item, str) and item for item in companions
    ):
        reasons.append("background_family requires 1 to 3 companion_asset_ids")
        companions = []
    ids = [item for item in [master_id, *companions] if isinstance(item, str) and item]
    if len(ids) != len(set(ids)):
        reasons.append("background_family master and companion asset IDs must be distinct")
    if family.get("surface_mode") not in {"light", "dark"}:
        reasons.append("background_family.surface_mode must be light or dark")
    copy_safe_zone = family.get("copy_safe_zone")
    if not isinstance(copy_safe_zone, dict):
        copy_safe_zone = {}
        reasons.append("background_family.copy_safe_zone must be a normalized geometry object")
    else:
        for field in ("x", "y", "width", "height"):
            value = copy_safe_zone.get(field)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                reasons.append(f"background_family.copy_safe_zone.{field} must be numeric")
    body_text_color = family.get("body_text_color")
    if not isinstance(body_text_color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", body_text_color):
        reasons.append("background_family.body_text_color must be a #RRGGBB color")
    minimum_contrast_ratio = family.get("minimum_contrast_ratio")
    if not isinstance(minimum_contrast_ratio, (int, float)) or isinstance(minimum_contrast_ratio, bool) or minimum_contrast_ratio < 4.5:
        reasons.append("background_family.minimum_contrast_ratio must be at least 4.5")
    maximum_copy_safe_stddev = family.get("maximum_copy_safe_stddev")
    if not isinstance(maximum_copy_safe_stddev, (int, float)) or isinstance(maximum_copy_safe_stddev, bool) or not 0 < maximum_copy_safe_stddev <= 0.12:
        reasons.append("background_family.maximum_copy_safe_stddev must be between 0 and 0.12")
    if assets_doc is not None:
        registry = {
            item.get("id"): item
            for item in assets_doc.get("assets", [])
            if isinstance(item, dict) and item.get("id")
        }
        for asset_id in ids:
            asset = registry.get(asset_id)
            if not asset:
                reasons.append(f"background family references unknown asset: {asset_id}")
                continue
            if asset.get("kind") != "background" or asset.get("origin") != "generated-illustrative":
                reasons.append(f"background family asset must be a generated background: {asset_id}")
            if asset.get("background_family_id") != family_id:
                reasons.append(f"background family asset has mismatched family ID: {asset_id}")
        if isinstance(master_id, str) and master_id in registry:
            if registry[master_id].get("background_variant") != "master":
                reasons.append("background family master asset must declare background_variant=master")
        for asset_id in companions:
            if asset_id in registry and registry[asset_id].get("background_variant") != "companion":
                reasons.append(f"background companion must declare background_variant=companion: {asset_id}")
    return {
        "ready": not reasons,
        "id": family_id,
        "strategy": family.get("strategy"),
        "master_asset_id": master_id,
        "companion_asset_ids": companions,
        "surface_mode": family.get("surface_mode"),
        "copy_safe_zone": copy_safe_zone,
        "body_text_color": body_text_color,
        "minimum_contrast_ratio": minimum_contrast_ratio,
        "maximum_copy_safe_stddev": maximum_copy_safe_stddev,
        "blocking_reasons": reasons,
    }


def typography_calibration_state(organization: dict[str, Any]) -> dict[str, Any]:
    calibration = organization.get("visual", {}).get("calibration")
    typography = calibration.get("typography") if isinstance(calibration, dict) else None
    reasons: list[str] = []
    if not isinstance(typography, dict):
        typography = {}
        reasons.append("visual calibration requires a typography strategy")
    strategy = typography.get("strategy")
    if strategy not in ALLOWED_TYPOGRAPHY_STRATEGIES:
        reasons.append("typography.strategy must be expressive-native or restrained-native")
    if typography.get("editable_text_required") is not True:
        reasons.append("typography must require editable native text")
    if typography.get("font_policy") != "licensed-or-system-only":
        reasons.append("typography.font_policy must be licensed-or-system-only")
    if typography.get("body_copy_remains_standard") is not True:
        reasons.append("typography must keep body copy on a standard readable style")
    approved_treatments = typography.get("approved_treatments")
    if not isinstance(approved_treatments, list) or not approved_treatments:
        approved_treatments = []
        reasons.append("typography requires approved_treatments")
    else:
        invalid = sorted(
            treatment
            for treatment in approved_treatments
            if treatment not in ALLOWED_ART_TYPE_TREATMENTS
        )
        if invalid:
            reasons.append("typography has invalid approved treatments: " + ", ".join(invalid))
    maximum = typography.get("maximum_moments_per_article")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or not 2 <= maximum <= 4:
        reasons.append("typography.maximum_moments_per_article must be 2 to 4")
        maximum = 4
    recipes_raw = typography.get("approved_recipes")
    recipes = [item for item in recipes_raw if isinstance(item, dict)] if isinstance(recipes_raw, list) else []
    if strategy == "expressive-native" and len(recipes) < 2:
        reasons.append("expressive typography requires at least 2 approved construction recipes")
    recipe_ids: set[str] = set()
    for index, recipe in enumerate(recipes):
        recipe_id = recipe.get("id")
        if not isinstance(recipe_id, str) or not SLUG.fullmatch(recipe_id):
            reasons.append(f"typography recipe {index} requires a slug id")
        elif recipe_id in recipe_ids:
            reasons.append(f"typography recipe id is duplicated: {recipe_id}")
        else:
            recipe_ids.add(recipe_id)
        if recipe.get("treatment") not in approved_treatments:
            reasons.append(f"typography recipe {index} must use an approved treatment")
        techniques = recipe.get("techniques")
        technique_set = {item for item in techniques if isinstance(item, str)} if isinstance(techniques, list) else set()
        if len(technique_set) < 2:
            reasons.append(f"typography recipe {index} needs at least 2 non-font construction techniques")
        invalid_techniques = sorted(technique_set - ALLOWED_ART_TYPE_TECHNIQUES)
        if invalid_techniques:
            reasons.append(
                f"typography recipe {index} has invalid techniques: " + ", ".join(invalid_techniques)
            )
        minimum_layers = recipe.get("minimum_editable_layers")
        if not isinstance(minimum_layers, int) or isinstance(minimum_layers, bool) or minimum_layers < 2:
            reasons.append(f"typography recipe {index} minimum_editable_layers must be at least 2")
        if not isinstance(recipe.get("fallback_text_style"), str) or not recipe.get("fallback_text_style"):
            reasons.append(f"typography recipe {index} requires fallback_text_style")
    return {
        "ready": not reasons,
        "strategy": strategy,
        "approved_treatments": approved_treatments,
        "maximum_moments_per_article": maximum,
        "approved_recipes": recipes,
        "blocking_reasons": reasons,
    }


def calibration_state(
    organization: dict[str, Any],
    route_id: str | None = None,
    assets_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    calibration = organization.get("visual", {}).get("calibration")
    if not isinstance(calibration, dict):
        calibration = {}
    approved_routes = {
        value for value in calibration.get("approved_routes", []) if isinstance(value, str)
    }
    organization_status = organization.get("status")
    reasons: list[str] = []
    isolation = source_isolation_state(organization)
    background_family = background_family_state(organization, assets_doc)
    typography = typography_calibration_state(organization)
    reasons.extend(isolation["blocking_reasons"])
    if organization_status == "provisional":
        reasons.append("organization status is provisional")
    if calibration.get("status") != "approved":
        reasons.append("organization visual calibration is not approved")
    if route_id and route_id not in approved_routes:
        reasons.append(f"route is not approved by visual calibration: {route_id}")
    benchmark = calibration.get("benchmark")
    if (
        not isinstance(benchmark, dict)
        or not benchmark.get("file_url")
        or not benchmark.get("page_name")
        or not benchmark.get("article_node_id")
    ):
        reasons.append("visual calibration lacks an Ardot benchmark file, page, and article node")
    reasons.extend(background_family["blocking_reasons"])
    reasons.extend(typography["blocking_reasons"])
    return {
        "ready": not reasons,
        "status": calibration.get("status", "missing"),
        "approved_routes": sorted(approved_routes),
        "benchmark": benchmark,
        "source_isolation": isolation,
        "background_family": background_family,
        "typography": typography,
        "blocking_reasons": reasons,
    }


def article_texts(article: dict[str, Any]) -> list[str]:
    values: list[str] = []

    def visit(value: Any, key: str | None = None) -> None:
        if isinstance(value, str):
            if key not in {"source_id", "component", "src", "background", "role", "id"}:
                stripped = value.strip()
                if stripped:
                    values.append(stripped)
        elif isinstance(value, list):
            for item in value:
                visit(item, key)
        elif isinstance(value, dict):
            for child_key, child in value.items():
                if child_key not in {"visual_kit", "visual_review_file", "layout_review"}:
                    visit(child, child_key)

    visit(article.get("blocks", []))
    return values


def source_text_is_grounded(source_text: Any, texts: list[str]) -> bool:
    if not isinstance(source_text, str) or len(source_text.strip()) < 6:
        return False
    normalized = source_text.strip()
    return any(normalized in text or text in normalized for text in texts)


def concrete_subject_is_specific(subject: Any) -> bool:
    if not isinstance(subject, str):
        return False
    normalized = re.sub(r"\s+", "", subject).lower()
    return (
        len(normalized) >= 4
        and normalized not in GENERIC_VISUAL_SUBJECTS
        and not GENERIC_SUBJECT_PATTERN.fullmatch(normalized)
    )


def validate_typography_plan(
    article: dict[str, Any],
    organization: dict[str, Any],
    ardot: dict[str, Any],
) -> dict[str, Any]:
    calibration = typography_calibration_state(organization)
    errors: list[str] = []
    plan = article.get("typography")
    strategy = calibration["strategy"]
    if strategy == "restrained-native" and not isinstance(plan, dict):
        return {
            "ready": calibration["ready"],
            "strategy": strategy,
            "moment_count": 0,
            "roles": [],
            "treatments": [],
            "errors": calibration["blocking_reasons"],
        }
    if not isinstance(plan, dict):
        plan = {}
        errors.append("expressive-native typography requires article.typography")
    if plan.get("status") != "approved":
        errors.append("article.typography.status must be approved")
    moments_raw = plan.get("moments")
    moments = [item for item in moments_raw if isinstance(item, dict)] if isinstance(moments_raw, list) else []
    minimum = 2 if strategy == "expressive-native" else 0
    maximum = calibration["maximum_moments_per_article"]
    if not minimum <= len(moments) <= maximum:
        errors.append(f"article typography requires {minimum} to {maximum} expressive moments")
    grounded_texts = article_texts(article)
    storyboard = article.get("storyboard") if isinstance(article.get("storyboard"), dict) else {}
    chapter_ids = {
        item.get("id")
        for item in storyboard.get("chapters", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    roles: set[str] = set()
    treatments: set[str] = set()
    text_node_ids: set[str] = set()
    design_file = ardot.get("design_file") if isinstance(ardot.get("design_file"), dict) else {}
    design_url = design_file.get("url")
    approved_treatments = set(calibration["approved_treatments"])
    recipes = {
        item.get("id"): item
        for item in calibration.get("approved_recipes", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    construction_node_ids: set[str] = set()
    for index, moment in enumerate(moments):
        role = moment.get("role")
        if role not in ALLOWED_ART_TYPE_ROLES:
            errors.append(f"typography moment {index} has invalid role: {role}")
        else:
            roles.add(role)
        chapter_id = moment.get("storyboard_chapter")
        if chapter_id not in chapter_ids:
            errors.append(f"typography moment {index} references unknown storyboard chapter: {chapter_id}")
        source_text = moment.get("source_text")
        if not source_text_is_grounded(source_text, grounded_texts):
            errors.append(f"typography moment {index} source_text is not grounded in article copy")
        elif len(source_text.strip()) > 40:
            errors.append(f"typography moment {index} source_text is too long for display lettering")
        treatment = moment.get("treatment")
        if treatment not in approved_treatments:
            errors.append(f"typography moment {index} uses an unapproved treatment: {treatment}")
        else:
            treatments.add(treatment)
        if moment.get("editable_text") is not True:
            errors.append(f"typography moment {index} must remain editable native text")
        if moment.get("font_source") != "licensed-or-system":
            errors.append(f"typography moment {index} font_source must be licensed-or-system")
        if not isinstance(moment.get("fallback_text_style"), str) or not moment.get("fallback_text_style"):
            errors.append(f"typography moment {index} requires fallback_text_style")
        recipe_id = moment.get("recipe_id")
        recipe = recipes.get(recipe_id)
        if not recipe:
            errors.append(f"typography moment {index} must reference an approved recipe_id")
            recipe = {}
        elif recipe.get("treatment") != treatment:
            errors.append(f"typography moment {index} treatment must match its approved recipe")
        construction = moment.get("construction")
        if not isinstance(construction, dict):
            construction = {}
            errors.append(f"typography moment {index} requires a construction plan")
        techniques_raw = construction.get("techniques")
        technique_set = {
            item for item in techniques_raw if isinstance(item, str)
        } if isinstance(techniques_raw, list) else set()
        if len(technique_set) < 2:
            errors.append(
                f"typography moment {index} needs at least 2 non-font construction techniques; font swap alone is forbidden"
            )
        invalid_techniques = sorted(technique_set - ALLOWED_ART_TYPE_TECHNIQUES)
        if invalid_techniques:
            errors.append(
                f"typography moment {index} has invalid construction techniques: "
                + ", ".join(invalid_techniques)
            )
        required_techniques = {
            item for item in recipe.get("techniques", []) if isinstance(item, str)
        }
        if recipe and not required_techniques.issubset(technique_set):
            missing = sorted(required_techniques - technique_set)
            errors.append(
                f"typography moment {index} is missing recipe techniques: " + ", ".join(missing)
            )
        native_nodes_raw = construction.get("native_text_node_ids")
        native_nodes = [item for item in native_nodes_raw if isinstance(item, str) and item] if isinstance(native_nodes_raw, list) else []
        accent_nodes_raw = construction.get("accent_node_ids", [])
        accent_nodes = [item for item in accent_nodes_raw if isinstance(item, str) and item] if isinstance(accent_nodes_raw, list) else []
        editable_layers = len(set(native_nodes + accent_nodes))
        minimum_layers = recipe.get("minimum_editable_layers", 2)
        if editable_layers < minimum_layers:
            errors.append(
                f"typography moment {index} requires at least {minimum_layers} editable construction layers"
            )
        for node_id in native_nodes + accent_nodes:
            if node_id in construction_node_ids:
                errors.append(f"typography moment {index} reuses an expressive construction node: {node_id}")
            construction_node_ids.add(node_id)
        line_count = construction.get("line_count")
        if not isinstance(line_count, int) or isinstance(line_count, bool) or not 1 <= line_count <= 4:
            errors.append(f"typography moment {index} line_count must be between 1 and 4")
        if "scale-contrast" in technique_set:
            scale_ratio = construction.get("scale_ratio")
            if not isinstance(scale_ratio, (int, float)) or isinstance(scale_ratio, bool) or scale_ratio < 1.15:
                errors.append(f"typography moment {index} scale-contrast requires scale_ratio >= 1.15")
        text_style = moment.get("ardot_text_style")
        if not isinstance(text_style, dict):
            errors.append(f"typography moment {index} requires ardot_text_style evidence")
            continue
        for field in ("file_url", "node_id", "style_id", "name"):
            if not isinstance(text_style.get(field), str) or not text_style.get(field):
                errors.append(f"typography moment {index} ardot_text_style.{field} is required")
        if text_style.get("file_url") != design_url:
            errors.append(f"typography moment {index} text style must belong to the organization Ardot file")
        text_node_id = text_style.get("node_id")
        if isinstance(text_node_id, str) and text_node_id:
            if text_node_id in text_node_ids:
                errors.append(f"typography moment {index} reuses an Ardot text node")
            text_node_ids.add(text_node_id)
            if native_nodes and text_node_id not in native_nodes:
                errors.append(
                    f"typography moment {index} ardot text node must appear in construction.native_text_node_ids"
                )
        forbidden_asset_fields = {"asset_id", "src", "image", "raster_text"} & set(moment)
        if forbidden_asset_fields:
            errors.append(
                f"typography moment {index} must not use baked text assets: "
                + ", ".join(sorted(forbidden_asset_fields))
            )
    if strategy == "expressive-native" and len(roles) < 2:
        errors.append("expressive typography requires at least 2 different semantic roles")
    if strategy == "expressive-native" and len(treatments) < 2:
        errors.append("expressive typography requires at least 2 different treatments")
    return {
        "ready": calibration["ready"] and not errors,
        "strategy": strategy,
        "moment_count": len(moments),
        "roles": sorted(roles),
        "treatments": sorted(treatments),
        "errors": calibration["blocking_reasons"] + errors,
    }


def validate_visual_review(
    review: dict[str, Any],
    article: dict[str, Any],
    article_path: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    if review.get("schema_version") != 2:
        errors.append("visual review schema_version must be 2")
    if review.get("article_id") != article.get("article_id"):
        errors.append("visual review article_id must match the article")
    if review.get("organization_id") != article.get("organization_id"):
        errors.append("visual review organization_id must match the article")
    ardot = review.get("ardot")
    if not isinstance(ardot, dict):
        errors.append("visual review requires ardot metadata")
        ardot = {}
    for field in ("file_url", "page_id", "article_node_id"):
        if not isinstance(ardot.get(field), str) or not ardot.get(field):
            errors.append(f"visual review ardot.{field} is required")
    capture = review.get("capture")
    if not isinstance(capture, dict):
        capture = {}
        errors.append("visual review requires capture metadata")
    if capture.get("source") != "ardot-node-export":
        errors.append("visual review capture.source must be ardot-node-export")
    if not _is_iso_datetime(capture.get("captured_at")):
        errors.append("visual review capture.captured_at must be an ISO timestamp")
    if capture.get("article_root_node_id") != ardot.get("article_node_id"):
        errors.append("visual review capture must reference the Ardot article root node")
    screenshots = review.get("screenshots")
    screenshot_items = [item for item in screenshots if isinstance(item, dict)] if isinstance(screenshots, list) else []
    roles = {item.get("role") for item in screenshot_items if isinstance(item.get("role"), str)}
    for role in sorted(REQUIRED_SCREENSHOT_ROLES - roles):
        errors.append(f"visual review is missing screenshot role: {role}")
    node_ids: set[str] = set()
    screenshot_hashes: dict[str, str] = {}
    screenshot_chapters: dict[str, str] = {}
    seen_hashes: set[str] = set()
    screenshot_locations: set[Path] = set()
    for index, item in enumerate(screenshot_items):
        node_id = item.get("node_id")
        if not isinstance(node_id, str) or not node_id:
            errors.append(f"visual review screenshot {index} requires node_id")
        else:
            node_ids.add(node_id)
        location = item.get("location")
        if not isinstance(location, str) or not location:
            errors.append(f"visual review screenshot {index} requires location")
        elif re.match(r"^https?://", location):
            errors.append("visual review screenshots must be local immutable exports, not URLs")
        else:
            candidate = (article_path.parent / location).resolve()
            if not candidate.exists() or not candidate.is_file():
                errors.append(f"visual review screenshot is missing: {location}")
            else:
                if candidate in screenshot_locations:
                    errors.append(f"visual review screenshot file is reused: {location}")
                screenshot_locations.add(candidate)
                declared_hash = item.get("sha256")
                actual_hash = file_sha256(candidate)
                if declared_hash != actual_hash:
                    errors.append(f"visual review screenshot {index} sha256 does not match the file")
                if actual_hash in seen_hashes:
                    errors.append(f"visual review screenshot {index} duplicates another screenshot's pixels")
                seen_hashes.add(actual_hash)
                if isinstance(node_id, str):
                    screenshot_hashes[node_id] = actual_hash
                    if isinstance(item.get("chapter_id"), str):
                        screenshot_chapters[node_id] = item["chapter_id"]
                try:
                    image = inspect_png(candidate)
                except ValueError as exc:
                    errors.append(f"visual review screenshot {index} is not a valid PNG: {exc}")
                else:
                    if image["width_px"] != 390:
                        errors.append(
                            f"visual review screenshot {index} must be a 390 px Ardot export; found {image['width_px']}"
                        )
                    if item.get("width_px") != image["width_px"] or item.get("height_px") != image["height_px"]:
                        errors.append(f"visual review screenshot {index} pixel dimensions do not match the file")
        if not isinstance(item.get("chapter_id"), str) or not item.get("chapter_id"):
            errors.append(f"visual review screenshot {index} requires chapter_id")
    if len(node_ids) < 5:
        errors.append("visual review requires at least 5 distinct Ardot node screenshots")
    density = review.get("density")
    if not isinstance(density, dict):
        density = {}
        errors.append("visual review density must be an object")
    density_mode = density.get("mode")
    if density_mode not in ALLOWED_DENSITY_MODES:
        errors.append("visual review density.mode is invalid")
        density_mode = "compact-editorial"
    if density.get("measured_from") != "ardot-node-properties-and-screenshot":
        errors.append("visual review density.measured_from must bind Ardot node properties to screenshots")
    if not _is_iso_datetime(density.get("measured_at")):
        errors.append("visual review density.measured_at must be an ISO timestamp")
    samples = density.get("samples")
    sample_items = [item for item in samples if isinstance(item, dict)] if isinstance(samples, list) else []
    density_node_ids: set[str] = set()
    band = DENSITY_BANDS[density_mode]
    for index, sample in enumerate(sample_items):
        node_id = sample.get("node_id")
        if not isinstance(node_id, str) or node_id not in node_ids:
            errors.append(f"density sample {index} must reference a screenshot node_id")
        else:
            density_node_ids.add(node_id)
            if sample.get("screenshot_sha256") != screenshot_hashes.get(node_id):
                errors.append(f"density sample {index} screenshot_sha256 does not match its screenshot")
        if not isinstance(sample.get("chapter_id"), str) or not sample.get("chapter_id"):
            errors.append(f"density sample {index} requires chapter_id")
        elif isinstance(node_id, str) and sample.get("chapter_id") != screenshot_chapters.get(node_id):
            errors.append(f"density sample {index} chapter_id must match its screenshot")
        for metric, (minimum, maximum) in band.items():
            value = sample.get(metric)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"density sample {index} requires numeric {metric}")
            elif not minimum <= float(value) <= maximum:
                errors.append(
                    f"density sample {index} {metric} must be between {minimum} and {maximum} for {density_mode}"
                )
        intentional = sample.get("intentional_whitespace") is True
        occupancy = sample.get("content_occupancy_ratio")
        occupancy_minimum = 0.45 if intentional else 0.68
        if not isinstance(occupancy, (int, float)) or isinstance(occupancy, bool):
            errors.append(f"density sample {index} requires numeric content_occupancy_ratio")
        elif not occupancy_minimum <= float(occupancy) <= 0.90:
            errors.append(
                f"density sample {index} content_occupancy_ratio must be between {occupancy_minimum} and 0.9"
            )
        largest_empty = sample.get("largest_empty_region_ratio")
        empty_maximum = 0.40 if intentional else 0.20
        if not isinstance(largest_empty, (int, float)) or isinstance(largest_empty, bool):
            errors.append(f"density sample {index} requires numeric largest_empty_region_ratio")
        elif not 0 <= float(largest_empty) <= empty_maximum:
            errors.append(
                f"density sample {index} largest_empty_region_ratio must be at most {empty_maximum}"
            )
        if intentional and not sample.get("intentional_whitespace_reason"):
            errors.append(f"density sample {index} intentional whitespace requires a reason")
        contrast = sample.get("body_text_contrast_ratio")
        if not isinstance(contrast, (int, float)) or isinstance(contrast, bool):
            errors.append(f"density sample {index} requires numeric body_text_contrast_ratio")
        elif float(contrast) < 4.5:
            errors.append(f"density sample {index} body_text_contrast_ratio must be at least 4.5")
    if len(density_node_ids) < 5:
        errors.append("visual review requires density samples for at least 5 distinct screenshot nodes")
    checks = review.get("checks")
    if not isinstance(checks, dict):
        checks = {}
        errors.append("visual review checks must be an object")
    for check in sorted(REQUIRED_VISUAL_CHECKS):
        if checks.get(check) != "pass":
            errors.append(f"visual review check must pass: {check}")
    if review.get("status") != "approved":
        errors.append("visual review status must be approved")
    if not _is_iso_datetime(review.get("reviewed_at")):
        errors.append("visual review reviewed_at must be an ISO timestamp")
    return {
        "ready": not errors,
        "errors": errors,
        "screenshot_count": len(screenshot_items),
        "screenshot_roles": sorted(role for role in roles if role),
        "node_count": len(node_ids),
        "density_mode": density_mode,
        "density_sample_count": len(sample_items),
        "passed_checks": sorted(
            check for check in REQUIRED_VISUAL_CHECKS if checks.get(check) == "pass"
        ),
    }

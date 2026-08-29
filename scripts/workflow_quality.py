#!/usr/bin/env python3
"""Shared quality gates for organization calibration and article authoring."""

from __future__ import annotations

import hashlib
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
ALLOWED_INTERACTION_AUTHORING_MODES = {"dynamic-default", "static-exception"}
ALLOWED_INTERACTION_PATTERNS = {
    "tap-reveal-group",
    "progressive-reveal",
    "metric-reveal",
    "process-reveal",
    "horizontal-swipe",
}
ALLOWED_INTERACTION_TRANSPORT_MODES = {"svg-smil-self", "horizontal-swipe"}
ALLOWED_INTERACTION_PLACEMENT_BANDS = {"early", "middle", "late"}
ALLOWED_STATIC_EXCEPTION_CATEGORIES = {
    "user-requested-static",
    "short-utility-notice",
    "editorially-unsuitable",
    "accessibility-priority",
}
INTERACTION_STATE_NAMES = ("closed", "open", "fallback")
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

ALLOWED_VISUAL_REFERENCE_POLICIES = {"source-zero", "explicit-style-grammar"}
EXPLICIT_STYLE_REFERENCE_SCOPE = "abstract-visual-grammar-only"
REQUIRED_STYLE_NON_COPY_CONSTRAINTS = {
    "text",
    "photographs",
    "logos",
    "specific-layout",
    "component-geometry",
    "artwork",
}
REQUIRED_STYLE_GRAMMAR_TOKENS = {
    "color_motion",
    "saturation",
    "material",
    "lighting",
    "layering",
    "edge_energy",
    "copy_safe_zone",
    "photo_responsibility",
    "background_responsibility",
}
STYLE_PRESET_DIRECTORY = Path(__file__).resolve().parent.parent / "style-presets"
STYLE_GRAMMAR_URL_PATTERN = re.compile(
    r"(?:https?://|www\.|data:|mp\.weixin\.qq\.com)",
    re.I,
)
STYLE_GRAMMAR_COPY_INSTRUCTION_PATTERN = re.compile(
    r"\b(?:copy|replicate|reproduce|verbatim)\b.{0,120}"
    r"\b(?:exact\s+)?(?:headline|title|layout|cover\s+geometry|photo(?:graph)?|logo|artwork)\b",
    re.I,
)


def _is_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _style_grammar_payload(grammar: dict[str, Any]) -> dict[str, Any]:
    """Return the normalized, order-independent payload covered by the grammar hash."""
    raw_tokens = grammar.get("tokens")
    tokens = raw_tokens if isinstance(raw_tokens, dict) else {}
    normalized_tokens = {
        str(key): value.strip() if isinstance(value, str) else value
        for key, value in sorted(tokens.items(), key=lambda item: str(item[0]))
    }
    raw_constraints = grammar.get("non_copy_constraints")
    constraints = (
        sorted({item.strip() for item in raw_constraints if isinstance(item, str) and item.strip()})
        if isinstance(raw_constraints, list)
        else []
    )
    return {
        "tokens": normalized_tokens,
        "non_copy_constraints": constraints,
    }


def style_grammar_sha256(grammar: dict[str, Any]) -> str:
    """Hash the complete abstract grammar and its non-copy boundary deterministically."""
    payload = json.dumps(
        _style_grammar_payload(grammar),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _style_preset_catalog_entry(preset_id: str) -> tuple[dict[str, Any] | None, str | None]:
    path = STYLE_PRESET_DIRECTORY / f"{preset_id}.json"
    if not path.is_file():
        return None, f"unknown style preset: {preset_id}"
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"invalid style preset catalog entry {preset_id}: {exc}"
    if not isinstance(entry, dict):
        return None, f"style preset catalog entry must be an object: {preset_id}"
    return entry, None


def style_grammar_errors(
    grammar: Any,
    label: str = "style_grammar",
    *,
    verify_preset_catalog: bool = True,
) -> list[str]:
    """Validate a route grammar without accepting reference-content-shaped fields."""
    if not isinstance(grammar, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    allowed_fields = {
        "preset_id",
        "label",
        "tokens",
        "non_copy_constraints",
        "sha256",
    }
    unsupported_fields = sorted(set(grammar) - allowed_fields)
    if unsupported_fields:
        errors.append(
            f"{label} contains unsupported or reference-content fields: "
            + ", ".join(unsupported_fields)
        )
    preset_id = grammar.get("preset_id")
    if preset_id is not None and (
        not isinstance(preset_id, str) or not SLUG.fullmatch(preset_id)
    ):
        errors.append(f"{label}.preset_id must be a lowercase hyphenated slug")
    preset_label = grammar.get("label")
    if preset_label is not None and (
        not isinstance(preset_label, str) or not preset_label.strip()
    ):
        errors.append(f"{label}.label must be a non-empty string")
    tokens = grammar.get("tokens")
    if not isinstance(tokens, dict):
        tokens = {}
        errors.append(f"{label}.tokens must be an object")
    missing_tokens = sorted(REQUIRED_STYLE_GRAMMAR_TOKENS - set(tokens))
    if missing_tokens:
        errors.append(f"{label}.tokens is missing abstract tokens: " + ", ".join(missing_tokens))
    unsupported_tokens = sorted(set(tokens) - REQUIRED_STYLE_GRAMMAR_TOKENS)
    if unsupported_tokens:
        errors.append(
            f"{label}.tokens contains unsupported or reference-shaped fields: "
            + ", ".join(unsupported_tokens)
        )
    for key, value in tokens.items():
        if not isinstance(key, str) or not key.strip():
            errors.append(f"{label}.tokens keys must be non-empty strings")
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{label}.tokens.{key} must be a non-empty abstract description")
            continue
        if STYLE_GRAMMAR_URL_PATTERN.search(value):
            errors.append(f"{label}.tokens.{key} must not contain a URL")
        if STYLE_GRAMMAR_COPY_INSTRUCTION_PATTERN.search(value):
            errors.append(
                f"{label}.tokens.{key} contains an explicit reference-copy instruction"
            )
    constraints = grammar.get("non_copy_constraints")
    constraint_set = (
        {item for item in constraints if isinstance(item, str)}
        if isinstance(constraints, list)
        else set()
    )
    if not isinstance(constraints, list):
        errors.append(f"{label}.non_copy_constraints must be an array")
    missing_constraints = sorted(REQUIRED_STYLE_NON_COPY_CONSTRAINTS - constraint_set)
    if missing_constraints:
        errors.append(
            f"{label} is missing non-copy constraints: " + ", ".join(missing_constraints)
        )
    digest = grammar.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        errors.append(f"{label}.sha256 must be a lowercase SHA-256")
    elif digest != style_grammar_sha256(grammar):
        errors.append(f"{label}.sha256 does not match the canonical grammar payload")
    if (
        verify_preset_catalog
        and isinstance(preset_id, str)
        and SLUG.fullmatch(preset_id)
    ):
        preset, preset_error = _style_preset_catalog_entry(preset_id)
        if preset_error:
            errors.append(f"{label}.preset_id references {preset_error}")
        elif isinstance(preset, dict):
            if preset.get("preset_id") != preset_id:
                errors.append(
                    f"style preset catalog ID does not match filename: {preset_id}"
                )
            canonical = preset.get("grammar")
            canonical_errors = style_grammar_errors(
                canonical,
                f"style preset {preset_id}.grammar",
                verify_preset_catalog=False,
            )
            if isinstance(canonical, dict) and canonical.get("preset_id") != preset_id:
                errors.append(
                    f"style preset canonical grammar ID does not match catalog ID: {preset_id}"
                )
            if canonical_errors:
                errors.extend(canonical_errors)
            elif isinstance(canonical, dict) and digest != canonical.get("sha256"):
                errors.append(
                    f"{label}.sha256 does not match canonical preset {preset_id}"
                )
    return errors


def source_isolation_state(organization: dict[str, Any]) -> dict[str, Any]:
    provenance = organization.get("provenance")
    if not isinstance(provenance, dict):
        provenance = {}
    reasons: list[str] = []
    policy = provenance.get("visual_reference_policy")
    if policy not in ALLOWED_VISUAL_REFERENCE_POLICIES:
        reasons.append(
            "organization provenance must use visual_reference_policy=source-zero "
            "or explicit-style-grammar"
        )
    visual_inputs = provenance.get("visual_input_source_ids")
    if not isinstance(visual_inputs, list) or not visual_inputs or not all(
        isinstance(item, str) and item for item in visual_inputs
    ):
        reasons.append(f"{policy or 'visual'} provenance requires visual_input_source_ids")
        visual_inputs = []
    exclusions = provenance.get("excluded_visual_reference_kinds")
    exclusion_set = {item for item in exclusions if isinstance(item, str)} if isinstance(exclusions, list) else set()
    style_reference_source_ids: list[str] = []
    style_reference_scope = provenance.get("style_reference_scope")
    reference_reviewed_at = provenance.get("reference_reviewed_at")
    raw_non_copy = provenance.get("style_reference_non_copy_constraints")
    style_reference_non_copy_constraints = (
        sorted({item for item in raw_non_copy if isinstance(item, str)})
        if isinstance(raw_non_copy, list)
        else []
    )
    route_grammar_hashes: dict[str, str] = {}
    if policy == "source-zero":
        missing_exclusions = sorted(REQUIRED_SOURCE_ZERO_EXCLUSIONS - exclusion_set)
        if missing_exclusions:
            reasons.append(
                "source-zero provenance is missing excluded visual reference kinds: "
                + ", ".join(missing_exclusions)
            )
        if not _is_iso_datetime(provenance.get("isolation_reviewed_at")):
            reasons.append("source-zero provenance requires isolation_reviewed_at")
    elif policy == "explicit-style-grammar":
        raw_reference_ids = provenance.get("style_reference_source_ids")
        if not isinstance(raw_reference_ids, list) or not raw_reference_ids or not all(
            isinstance(item, str) and item for item in raw_reference_ids
        ):
            reasons.append("explicit-style-grammar provenance requires style_reference_source_ids")
        else:
            style_reference_source_ids = raw_reference_ids
        if style_reference_scope != EXPLICIT_STYLE_REFERENCE_SCOPE:
            reasons.append(
                "explicit-style-grammar provenance requires "
                f"style_reference_scope={EXPLICIT_STYLE_REFERENCE_SCOPE}"
            )
        if not _is_iso_datetime(reference_reviewed_at):
            reasons.append("explicit-style-grammar provenance requires reference_reviewed_at")
        missing_non_copy = sorted(
            REQUIRED_STYLE_NON_COPY_CONSTRAINTS
            - set(style_reference_non_copy_constraints)
        )
        if missing_non_copy:
            reasons.append(
                "explicit-style-grammar provenance is missing non-copy constraints: "
                + ", ".join(missing_non_copy)
            )
        routes = organization.get("visual", {}).get("routes", [])
        if not isinstance(routes, list) or not routes:
            reasons.append("explicit-style-grammar requires visual routes")
        else:
            grammar_count = 0
            for index, route in enumerate(routes):
                route_id = route.get("id", str(index)) if isinstance(route, dict) else str(index)
                grammar = route.get("style_grammar") if isinstance(route, dict) else None
                if grammar is None:
                    continue
                grammar_reasons = style_grammar_errors(
                    grammar,
                    f"visual route {route_id}.style_grammar",
                )
                reasons.extend(grammar_reasons)
                if not grammar_reasons and isinstance(grammar, dict):
                    grammar_count += 1
                    route_grammar_hashes[str(route_id)] = grammar["sha256"]
            if grammar_count == 0:
                reasons.append(
                    "explicit-style-grammar requires at least one route.style_grammar selection"
                )
    return {
        "ready": not reasons,
        "policy": policy or "missing",
        "visual_input_source_ids": visual_inputs,
        "excluded_visual_reference_kinds": sorted(exclusion_set),
        "style_reference_source_ids": style_reference_source_ids,
        "style_reference_scope": style_reference_scope,
        "reference_reviewed_at": reference_reviewed_at,
        "style_reference_non_copy_constraints": style_reference_non_copy_constraints,
        "route_grammar_hashes": route_grammar_hashes,
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


def interaction_semantic_hash(source_texts: list[str]) -> str:
    """Hash the ordered, normalized copy represented by one transport instance."""
    normalized = [re.sub(r"\s+", " ", item).strip() for item in source_texts]
    payload = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_interaction_plan(
    article: dict[str, Any],
    ardot: dict[str, Any],
    article_path: Path | None = None,
    *,
    require_evidence: bool = True,
) -> dict[str, Any]:
    """Validate 2–3 authored modules, then optionally require final Ardot evidence."""
    errors: list[str] = []
    plan = article.get("interaction_plan")
    if not isinstance(plan, dict):
        plan = {}
        errors.append(
            "article requires interaction_plan; the default authoring mode uses 2 to 3 semantic dynamic modules"
        )
    if plan.get("status") != "approved":
        errors.append("article.interaction_plan.status must be approved")
    authoring_mode = plan.get("authoring_mode")
    if authoring_mode not in ALLOWED_INTERACTION_AUTHORING_MODES:
        errors.append(
            "article.interaction_plan.authoring_mode must be dynamic-default or static-exception"
        )
    modules_raw = plan.get("modules")
    modules = [item for item in modules_raw if isinstance(item, dict)] if isinstance(modules_raw, list) else []
    if not isinstance(modules_raw, list) or len(modules) != len(modules_raw):
        errors.append("article.interaction_plan.modules must be an array of objects")
    target_count = plan.get("target_module_count")
    if not isinstance(target_count, int) or isinstance(target_count, bool):
        errors.append("article.interaction_plan.target_module_count must be an integer")
        target_count = -1
    if authoring_mode == "dynamic-default":
        if target_count not in {2, 3}:
            errors.append("dynamic-default interaction plans require target_module_count of 2 or 3")
        if not 2 <= len(modules) <= 3:
            errors.append("dynamic-default interaction plans require 2 to 3 semantic modules")
        if target_count != len(modules):
            errors.append("interaction target_module_count must equal the number of semantic modules")
        if isinstance(plan.get("exception"), dict):
            errors.append("dynamic-default interaction plans must not declare a static exception")
    elif authoring_mode == "static-exception":
        if target_count not in {0, 1} or len(modules) not in {0, 1} or target_count != len(modules):
            errors.append("static-exception interaction plans may contain at most one semantic module")
        exception = plan.get("exception")
        if not isinstance(exception, dict):
            exception = {}
            errors.append("static-exception interaction plans require an explicit exception record")
        if exception.get("category") not in ALLOWED_STATIC_EXCEPTION_CATEGORIES:
            errors.append("static interaction exception category is invalid")
        reason = exception.get("reason")
        if not isinstance(reason, str) or len(reason.strip()) < 12:
            errors.append("static interaction exception requires a specific reason of at least 12 characters")
        if exception.get("confirmed_by") not in {"user", "editor"}:
            errors.append("static interaction exception must be confirmed_by user or editor")

    revision_hash = plan.get("ardot_revision_hash")
    if require_evidence and modules and not isinstance(revision_hash, str):
        errors.append("final interaction evidence requires ardot_revision_hash")
    elif require_evidence and modules and not re.fullmatch(r"[0-9a-f]{64}", revision_hash or ""):
        errors.append("interaction ardot_revision_hash must be a lowercase SHA-256")
    article_root_node_id = plan.get("article_root_node_id")
    if require_evidence and modules and (
        not isinstance(article_root_node_id, str) or not article_root_node_id
    ):
        errors.append("final interaction evidence requires article_root_node_id")

    storyboard = article.get("storyboard") if isinstance(article.get("storyboard"), dict) else {}
    storyboard_chapters = [
        item
        for item in storyboard.get("chapters", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]
    chapter_by_id = {
        item.get("id"): item
        for item in storyboard_chapters
    }
    chapter_ids = set(chapter_by_id)
    chapter_index_by_id = {
        item["id"]: index for index, item in enumerate(storyboard_chapters)
    }
    article_blocks = article.get("blocks") if isinstance(article.get("blocks"), list) else []
    design_file = ardot.get("design_file") if isinstance(ardot.get("design_file"), dict) else {}
    design_url = design_file.get("url")
    module_ids: set[str] = set()
    instance_ids: set[str] = set()
    fallback_keys: set[str] = set()
    semantic_hashes: set[str] = set()
    module_chapters: set[str] = set()
    placement_bands: set[str] = set()
    purposes: set[str] = set()
    evidence_node_ids: set[str] = set()
    evidence_paths: set[Path] = set()
    source_text_count = 0
    instance_count = 0
    module_reports: list[dict[str, Any]] = []
    for index, module in enumerate(modules):
        prefix = f"interaction module {index}"
        module_id = module.get("id")
        if not isinstance(module_id, str) or not SLUG.fullmatch(module_id):
            errors.append(f"{prefix} requires a lowercase hyphenated id")
        elif module_id in module_ids:
            errors.append(f"interaction module id is duplicated: {module_id}")
        else:
            module_ids.add(module_id)
        pattern = module.get("pattern")
        if pattern not in ALLOWED_INTERACTION_PATTERNS:
            errors.append(f"{prefix} has unsupported pattern: {pattern}")
        candidate_modes_raw = module.get("candidate_modes")
        candidate_modes = (
            [item for item in candidate_modes_raw if isinstance(item, str)]
            if isinstance(candidate_modes_raw, list)
            else []
        )
        if (
            not isinstance(candidate_modes_raw, list)
            or not candidate_modes
            or len(candidate_modes) != len(candidate_modes_raw)
            or len(candidate_modes) != len(set(candidate_modes))
        ):
            errors.append(f"{prefix} requires one or more distinct candidate_modes")
        unsupported_modes = sorted(set(candidate_modes) - ALLOWED_INTERACTION_TRANSPORT_MODES)
        if unsupported_modes:
            errors.append(f"{prefix} has unsupported candidate_modes: {', '.join(unsupported_modes)}")
        expected_transport = "horizontal-swipe" if pattern == "horizontal-swipe" else "svg-smil-self"
        if pattern in ALLOWED_INTERACTION_PATTERNS and expected_transport not in candidate_modes:
            errors.append(f"{prefix} pattern {pattern} requires candidate mode {expected_transport}")
        chapter_id = module.get("storyboard_chapter")
        if chapter_id not in chapter_ids:
            errors.append(f"{prefix} references unknown storyboard chapter: {chapter_id}")
        elif chapter_id in module_chapters:
            errors.append(f"dynamic modules must be distributed across distinct chapters: {chapter_id}")
        else:
            module_chapters.add(chapter_id)
        placement_band = module.get("placement_band")
        if placement_band not in ALLOWED_INTERACTION_PLACEMENT_BANDS:
            errors.append(f"{prefix} has invalid placement_band: {placement_band}")
        elif placement_band in placement_bands:
            errors.append(f"dynamic modules must use distinct placement bands: {placement_band}")
        else:
            placement_bands.add(placement_band)
        if chapter_id in chapter_index_by_id and storyboard_chapters:
            chapter_index = chapter_index_by_id[chapter_id]
            expected_band = ("early", "middle", "late")[
                min(2, chapter_index * 3 // len(storyboard_chapters))
            ]
            if placement_band in ALLOWED_INTERACTION_PLACEMENT_BANDS and placement_band != expected_band:
                errors.append(
                    f"{prefix} chapter {chapter_id} belongs to {expected_band}, not {placement_band}"
                )
        purpose = module.get("purpose")
        if not isinstance(purpose, str) or len(purpose.strip()) < 8:
            errors.append(f"{prefix} requires a specific editorial purpose")
        else:
            normalized_purpose = re.sub(r"\s+", "", purpose).lower()
            if normalized_purpose in purposes:
                errors.append(f"interaction modules must use distinct editorial purposes: {purpose}")
            purposes.add(normalized_purpose)
        block_indices_raw = module.get("source_block_indices")
        block_indices = (
            [item for item in block_indices_raw if isinstance(item, int) and not isinstance(item, bool)]
            if isinstance(block_indices_raw, list)
            else []
        )
        if (
            not isinstance(block_indices_raw, list)
            or not block_indices
            or len(block_indices) != len(block_indices_raw)
        ):
            errors.append(f"{prefix} requires integer source_block_indices")
        elif len(block_indices) != len(set(block_indices)):
            errors.append(f"{prefix} source_block_indices must be distinct")
        valid_block_indices = [item for item in block_indices if 0 <= item < len(article_blocks)]
        if len(valid_block_indices) != len(block_indices):
            errors.append(f"{prefix} has an out-of-range source block index")
        chapter_block_indices = set(chapter_by_id.get(chapter_id, {}).get("block_indices", []))
        if valid_block_indices and not set(valid_block_indices).issubset(chapter_block_indices):
            errors.append(f"{prefix} source blocks must belong to storyboard chapter {chapter_id}")
        module_texts = article_texts(
            {"blocks": [article_blocks[item] for item in valid_block_indices]}
        )

        instances_raw = module.get("instances")
        instances = (
            [item for item in instances_raw if isinstance(item, dict)]
            if isinstance(instances_raw, list)
            else []
        )
        if (
            not isinstance(instances_raw, list)
            or not instances
            or len(instances) != len(instances_raw)
        ):
            errors.append(f"{prefix} requires one or more transport instances")
        instance_reports: list[dict[str, Any]] = []
        for instance_index, instance in enumerate(instances):
            instance_prefix = f"{prefix} instance {instance_index}"
            instance_id = instance.get("id")
            if not isinstance(instance_id, str) or not SLUG.fullmatch(instance_id):
                errors.append(f"{instance_prefix} requires a lowercase hyphenated id")
            elif instance_id in instance_ids:
                errors.append(f"interaction instance id is duplicated: {instance_id}")
            else:
                instance_ids.add(instance_id)
            source_texts_raw = instance.get("source_texts")
            source_texts = (
                [item for item in source_texts_raw if isinstance(item, str) and item.strip()]
                if isinstance(source_texts_raw, list)
                else []
            )
            if (
                not isinstance(source_texts_raw, list)
                or not source_texts
                or len(source_texts) != len(source_texts_raw)
            ):
                errors.append(f"{instance_prefix} requires one or more source_texts")
            if len(source_texts) != len(set(source_texts)):
                errors.append(f"{instance_prefix} source_texts must be distinct")
            for source_text in source_texts:
                if not source_text_is_grounded(source_text, module_texts):
                    errors.append(
                        f"{instance_prefix} source_text is not grounded in its source blocks: {source_text}"
                    )
            source_text_count += len(source_texts)
            expected_hash = interaction_semantic_hash(source_texts)
            semantic_hash = instance.get("semantic_hash")
            if semantic_hash != expected_hash:
                errors.append(f"{instance_prefix} semantic_hash does not match its ordered source_texts")
            elif semantic_hash in semantic_hashes:
                errors.append(f"interaction semantic content is duplicated: {semantic_hash}")
            else:
                semantic_hashes.add(semantic_hash)
            fallback_key = instance.get("fallback_key")
            if not isinstance(fallback_key, str) or not SLUG.fullmatch(fallback_key):
                errors.append(f"{instance_prefix} requires a lowercase hyphenated fallback_key")
            elif fallback_key in fallback_keys:
                errors.append(f"interaction fallback_key is duplicated: {fallback_key}")
            else:
                fallback_keys.add(fallback_key)
            instance_reports.append(
                {
                    "id": instance_id,
                    "source_text_count": len(source_texts),
                    "fallback_key": fallback_key,
                    "semantic_hash": expected_hash,
                }
            )
        instance_count += len(instances)

        if require_evidence:
            component = module.get("ardot_component")
            if not isinstance(component, dict):
                component = {}
                errors.append(f"{prefix} requires ardot_component evidence")
            if component.get("revision_hash") != revision_hash:
                errors.append(f"{prefix} Ardot evidence revision_hash must match the article plan")
            expected_instance_ids = [item["id"] for item in instance_reports]
            if component.get("covered_instance_ids") != expected_instance_ids:
                errors.append(
                    f"{prefix} Ardot evidence must cover every transport instance in order"
                )
            expected_semantic_hashes = [item["semantic_hash"] for item in instance_reports]
            if component.get("covered_semantic_hashes") != expected_semantic_hashes:
                errors.append(
                    f"{prefix} Ardot evidence must cover every transport semantic hash in order"
                )
            if component.get("file_url") != design_url:
                errors.append(f"{prefix} must belong to the organization Ardot file")
            if not isinstance(component.get("name"), str) or not component.get("name"):
                errors.append(f"{prefix} ardot_component.name is required")
            states = component.get("states")
            if not isinstance(states, dict):
                states = {}
                errors.append(f"{prefix} requires closed/open/fallback Ardot states")
            state_nodes: set[str] = set()
            state_paths: set[Path] = set()
            state_hashes: dict[str, str] = {}
            for state_name in INTERACTION_STATE_NAMES:
                state = states.get(state_name)
                if not isinstance(state, dict):
                    errors.append(f"{prefix} is missing Ardot state: {state_name}")
                    continue
                node_id = state.get("node_id")
                if not isinstance(node_id, str) or not node_id:
                    errors.append(f"{prefix} {state_name} state requires node_id")
                elif node_id in state_nodes or node_id in evidence_node_ids:
                    errors.append(f"{prefix} reuses an Ardot state node: {node_id}")
                else:
                    state_nodes.add(node_id)
                    evidence_node_ids.add(node_id)
                screenshot = state.get("screenshot")
                declared_hash = state.get("sha256")
                if not isinstance(declared_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", declared_hash):
                    errors.append(f"{prefix} {state_name} state requires a lowercase screenshot SHA-256")
                else:
                    state_hashes[state_name] = declared_hash
                if not isinstance(screenshot, str) or not screenshot:
                    errors.append(f"{prefix} {state_name} state requires a local screenshot")
                    continue
                if re.match(r"^https?://", screenshot):
                    errors.append(f"{prefix} {state_name} screenshot must be a local immutable export")
                    continue
                if article_path is None:
                    errors.append(f"{prefix} cannot verify state screenshots without article_path")
                    continue
                screenshot_path = (article_path.parent / screenshot).resolve()
                if screenshot_path in state_paths or screenshot_path in evidence_paths:
                    errors.append(f"{prefix} reuses an interaction state screenshot: {screenshot}")
                    continue
                state_paths.add(screenshot_path)
                evidence_paths.add(screenshot_path)
                if not screenshot_path.exists() or not screenshot_path.is_file():
                    errors.append(f"{prefix} interaction state screenshot is missing: {screenshot}")
                    continue
                actual_hash = file_sha256(screenshot_path)
                if declared_hash != actual_hash:
                    errors.append(f"{prefix} {state_name} screenshot sha256 does not match the file")
                try:
                    inspection = inspect_png(screenshot_path)
                except ValueError as exc:
                    errors.append(f"{prefix} {state_name} screenshot is not a valid PNG: {exc}")
                else:
                    if inspection["width_px"] != 390:
                        errors.append(
                            f"{prefix} {state_name} screenshot must be a 390 px Ardot export; found {inspection['width_px']}"
                        )
            if state_hashes.get("closed") == state_hashes.get("open") and state_hashes.get("closed"):
                errors.append(f"{prefix} closed and open evidence must show different states")
        module_reports.append(
            {
                "id": module_id,
                "pattern": pattern,
                "candidate_modes": candidate_modes,
                "storyboard_chapter": chapter_id,
                "placement_band": placement_band,
                "source_block_indices": valid_block_indices,
                "instance_count": len(instances),
                "instances": instance_reports,
            }
        )

    if authoring_mode == "dynamic-default" and len(modules) == 2 and placement_bands != {"early", "middle"}:
        errors.append("a 2-module dynamic-default plan must distribute modules across early and middle")
    if authoring_mode == "dynamic-default" and len(modules) == 3 and placement_bands != {"early", "middle", "late"}:
        errors.append("a 3-module dynamic-default plan must distribute modules across early, middle, and late")

    return {
        "ready": not errors,
        "status": plan.get("status"),
        "authoring_mode": authoring_mode,
        "target_module_count": target_count,
        "module_count": len(modules),
        "instance_count": instance_count,
        "source_text_count": source_text_count,
        "modules": module_reports,
        "evidence_required": require_evidence,
        "policy_version": "wechat-svg-smil-self-v1",
        "production_default": "static-fallback-until-account-runtime-certification",
        "errors": errors,
    }


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
    interaction_plan = (
        article.get("interaction_plan")
        if isinstance(article.get("interaction_plan"), dict)
        else {}
    )
    interaction_modules = interaction_plan.get("modules")
    if isinstance(interaction_modules, list) and interaction_modules:
        if ardot.get("article_node_id") != interaction_plan.get("article_root_node_id"):
            errors.append("visual review article root must match interaction_plan.article_root_node_id")
        if capture.get("revision_hash") != interaction_plan.get("ardot_revision_hash"):
            errors.append("visual review capture revision_hash must match the interaction plan")
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

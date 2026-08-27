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
    if not isinstance(family.get("copy_safe_zone"), str) or not family.get("copy_safe_zone", "").strip():
        reasons.append("background_family.copy_safe_zone is required")
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
    return {
        "ready": not reasons,
        "status": calibration.get("status", "missing"),
        "approved_routes": sorted(approved_routes),
        "benchmark": benchmark,
        "source_isolation": isolation,
        "background_family": background_family,
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

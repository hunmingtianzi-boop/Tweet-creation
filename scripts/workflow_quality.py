#!/usr/bin/env python3
"""Shared quality gates for organization calibration and article authoring."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


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
}
REQUIRED_SCREENSHOT_ROLES = {"hero", "chapter", "evidence", "complex-section", "cta"}
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


def calibration_state(organization: dict[str, Any], route_id: str | None = None) -> dict[str, Any]:
    calibration = organization.get("visual", {}).get("calibration")
    if not isinstance(calibration, dict):
        calibration = {}
    approved_routes = {
        value for value in calibration.get("approved_routes", []) if isinstance(value, str)
    }
    organization_status = organization.get("status")
    reasons: list[str] = []
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
    return {
        "ready": not reasons,
        "status": calibration.get("status", "missing"),
        "approved_routes": sorted(approved_routes),
        "benchmark": benchmark,
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
    if review.get("schema_version") != 1:
        errors.append("visual review schema_version must be 1")
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
    screenshots = review.get("screenshots")
    screenshot_items = [item for item in screenshots if isinstance(item, dict)] if isinstance(screenshots, list) else []
    roles = {item.get("role") for item in screenshot_items if isinstance(item.get("role"), str)}
    for role in sorted(REQUIRED_SCREENSHOT_ROLES - roles):
        errors.append(f"visual review is missing screenshot role: {role}")
    node_ids: set[str] = set()
    for index, item in enumerate(screenshot_items):
        node_id = item.get("node_id")
        if not isinstance(node_id, str) or not node_id:
            errors.append(f"visual review screenshot {index} requires node_id")
        else:
            node_ids.add(node_id)
        location = item.get("location")
        if not isinstance(location, str) or not location:
            errors.append(f"visual review screenshot {index} requires location")
        elif not re.match(r"^https?://", location):
            candidate = (article_path.parent / location).resolve()
            if not candidate.exists() or not candidate.is_file():
                errors.append(f"visual review screenshot is missing: {location}")
    if len(node_ids) < 5:
        errors.append("visual review requires at least 5 distinct Ardot node screenshots")
    checks = review.get("checks")
    if not isinstance(checks, dict):
        checks = {}
        errors.append("visual review checks must be an object")
    for check in sorted(REQUIRED_VISUAL_CHECKS):
        if checks.get(check) != "pass":
            errors.append(f"visual review check must pass: {check}")
    if review.get("status") != "approved":
        errors.append("visual review status must be approved")
    if not review.get("reviewed_at"):
        errors.append("visual review reviewed_at is required")
    return {
        "ready": not errors,
        "errors": errors,
        "screenshot_count": len(screenshot_items),
        "screenshot_roles": sorted(role for role in roles if role),
        "node_count": len(node_ids),
        "passed_checks": sorted(
            check for check in REQUIRED_VISUAL_CHECKS if checks.get(check) == "pass"
        ),
    }

#!/usr/bin/env python3
"""One executable asset-duty matrix shared by authoring and delivery layers.

The public entry point deliberately returns stable, human-readable error strings
instead of raising.  Callers can add their own asset/block prefix while reusing
the same truth table in pack validation, compilation, and transport readback.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


DOCUMENTARY_ORIGINS = frozenset({"photographed", "user-supplied", "official"})
GENERATED_ORIGINS = frozenset({"generated-illustrative", "derived"})
IDENTITY_ORIGINS = frozenset({"user-supplied", "official"})
MICRO_KINDS = frozenset({"illustration", "decoration"})

VALIDATION_CONTEXTS = frozenset(
    {
        "registry",
        "evidence-use",
        "article-micro",
        "background-use",
        "identity-use",
        "functional-use",
    }
)


def _error(code: str, message: str) -> str:
    return f"asset.role.{code}: {message}"


def validate_asset_role(
    asset: Mapping[str, Any], context: str = "registry"
) -> list[str]:
    """Validate one asset against the organization-wide duty matrix.

    `context` may tighten the base registry rules for a concrete use.  The
    function intentionally does not inspect files; pixel, Alpha, and watermark
    validators remain separate gates.
    """

    errors: list[str] = []
    if context not in VALIDATION_CONTEXTS:
        return [_error("context.invalid", f"unknown validation context: {context}")]

    kind = asset.get("kind")
    origin = asset.get("origin")
    visual_role = asset.get("visual_role")
    source_id = asset.get("source_id")
    roles = asset.get("roles")
    role_items = roles if isinstance(roles, list) else []

    is_documentary = visual_role == "documentary-evidence"
    is_micro = visual_role == "article-micro" or bool(role_items)

    if kind in {"logo", "qr"} and origin not in IDENTITY_ORIGINS:
        errors.append(
            _error(
                "identity.origin_forbidden",
                "logo and QR assets must be official or user-supplied",
            )
        )

    if kind == "photo" and origin in GENERATED_ORIGINS:
        errors.append(
            _error(
                "photo.generated_forbidden",
                "generated or derived pixels cannot be registered as a photo",
            )
        )

    if is_documentary:
        if kind != "photo":
            errors.append(
                _error(
                    "documentary.kind_mismatch",
                    "documentary evidence must be registered as kind=photo",
                )
            )
        if origin not in DOCUMENTARY_ORIGINS:
            errors.append(
                _error(
                    "documentary.origin_forbidden",
                    "documentary evidence must be photographed, user-supplied, or official",
                )
            )
        if not isinstance(source_id, str) or not source_id.strip():
            errors.append(
                _error(
                    "documentary.source_missing",
                    "documentary evidence requires a concrete source_id",
                )
            )

    if origin in GENERATED_ORIGINS and visual_role == "documentary-evidence":
        errors.append(
            _error(
                "generated.documentary_forbidden",
                "generated assets can never serve as documentary evidence",
            )
        )

    if is_micro:
        if kind not in MICRO_KINDS:
            errors.append(
                _error(
                    "micro.kind_mismatch",
                    "article micro-components must be illustration or decoration assets",
                )
            )
        if origin != "derived":
            errors.append(
                _error(
                    "micro.derived_required",
                    "official article micro-components must use origin=derived",
                )
            )
        if visual_role != "article-micro":
            errors.append(
                _error(
                    "micro.visual_role_required",
                    "a visual-kit role requires visual_role=article-micro",
                )
            )
        if len(role_items) != 1:
            errors.append(
                _error(
                    "micro.single_role_required",
                    "a derived article micro-component must declare exactly one semantic role",
                )
            )

    if kind == "background" and origin == "generated-illustrative":
        if visual_role != "illustrative-atmosphere":
            errors.append(
                _error(
                    "background.visual_role_mismatch",
                    "generated backgrounds must use visual_role=illustrative-atmosphere",
                )
            )

    if context == "evidence-use" and not (
        kind == "photo"
        and origin in DOCUMENTARY_ORIGINS
        and visual_role == "documentary-evidence"
        and isinstance(source_id, str)
        and source_id.strip()
    ):
        errors.append(
            _error(
                "evidence.use_forbidden",
                "evidence use requires a source-bound documentary photo",
            )
        )
    elif context == "article-micro" and not is_micro:
        errors.append(
            _error("micro.use_forbidden", "article-micro use requires a semantic micro role")
        )
    elif context == "background-use" and not (
        kind == "background"
        and origin == "generated-illustrative"
        and visual_role == "illustrative-atmosphere"
    ):
        errors.append(
            _error(
                "background.use_forbidden",
                "generated article backgrounds require the background/atmosphere duty",
            )
        )
    elif context == "identity-use" and not (
        kind in {"logo", "qr"} and origin in IDENTITY_ORIGINS
    ):
        errors.append(
            _error("identity.use_forbidden", "identity use requires an official/user asset")
        )
    elif context == "functional-use" and visual_role != "functional":
        errors.append(
            _error("functional.use_forbidden", "functional use requires visual_role=functional")
        )

    # Preserve first occurrence while keeping stable ordering for reports/tests.
    return list(dict.fromkeys(errors))


def is_documentary_photo(asset: Mapping[str, Any]) -> bool:
    """Return True only for an asset that passes the evidence-use matrix."""

    return not validate_asset_role(asset, "evidence-use")

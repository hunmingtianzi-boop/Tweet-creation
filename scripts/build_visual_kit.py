#!/usr/bin/env python3
"""Plan the mandatory article-specific micro-illustration kit before layout."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

if __name__ == "__main__":
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/build_visual_kit.py")

from asset_quality import validate_micro_asset
from build_storyboard import build_storyboard_plan
from orgs import load_pack, validate_cutout_derivation_report, validate_pack
from pack_assets import PackAssetResolutionError, resolve_pack_asset
from provider_acquisition_authority import LiveAuthorityCallback
from workflow_quality import (
    ALLOWED_COMPOSITION_ROLES,
    article_texts,
    calibration_state,
    concrete_subject_is_specific,
    source_text_is_grounded,
    validate_production_preferences,
)

try:
    from safe_paths import (
        SafePathError,
        existing_directory,
        existing_regular_file,
        new_file_path,
        write_text_create_once,
    )
except ImportError:  # pragma: no cover - package import fallback
    from .safe_paths import (  # type: ignore
        SafePathError,
        existing_directory,
        existing_regular_file,
        new_file_path,
        write_text_create_once,
    )


RUNTIME_ROOT = Path(__file__).resolve().parent.parent


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

KEY_BACKGROUND_CANDIDATES = (
    "#00FF3C",
    "#FF00D4",
    "#00E5FF",
    "#5B00FF",
    "#FF5A00",
)


def _hex_rgb(value: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"#([0-9A-Fa-f]{6})", value)
    if not match:
        return None
    encoded = match.group(1)
    return tuple(int(encoded[index : index + 2], 16) for index in (0, 2, 4))


def ranked_key_backgrounds(tokens: dict[str, Any]) -> list[str]:
    """Prefer chroma keys that are furthest from the calibrated organization palette."""

    palette = [
        parsed
        for value in tokens.values()
        if isinstance(value, str) and (parsed := _hex_rgb(value)) is not None
    ]

    def distance(candidate: str) -> float:
        rgb = _hex_rgb(candidate)
        if rgb is None or not palette:
            return 0.0
        return min(
            sum((channel - reference) ** 2 for channel, reference in zip(rgb, item))
            for item in palette
        )

    return sorted(KEY_BACKGROUND_CANDIDATES, key=distance, reverse=True)


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


def visual_kit_assets(article: dict[str, Any]) -> list[dict[str, Any]]:
    visual_kit = article.get("visual_kit")
    if not isinstance(visual_kit, dict):
        return []
    assets = visual_kit.get("assets")
    return [item for item in assets if isinstance(item, dict)] if isinstance(assets, list) else []


def selected_kit_roles(
    article: dict[str, Any],
    requested_count: int,
) -> tuple[list[str], list[str]]:
    """Resolve the user-selected role subset without hiding an invalid choice.

    The fixed role catalog remains the semantic vocabulary, but it is no longer
    a four-item minimum.  Invalid or missing selections return no executable
    slots; the accompanying errors keep ``ready_for_layout`` false.  This keeps
    the role catalog from becoming an implicit article choice.
    """

    catalog = [str(item["role"]) for item in KIT_ROLES]
    visual_kit = article.get("visual_kit")
    raw_roles = visual_kit.get("selected_roles") if isinstance(visual_kit, dict) else None
    errors: list[str] = []
    if not isinstance(raw_roles, list) or not all(
        isinstance(item, str) for item in raw_roles
    ):
        errors.append("article.visual_kit.selected_roles must be an array of role ids")
        return [], errors
    selected = [str(item) for item in raw_roles]
    if len(selected) != len(set(selected)):
        errors.append("article.visual_kit.selected_roles must not contain duplicates")
    unsupported = sorted(set(selected) - set(catalog))
    if unsupported:
        errors.append(
            "article.visual_kit.selected_roles contains unsupported roles: "
            + ", ".join(unsupported)
        )
    canonical = [role for role in catalog if role in selected]
    if selected != canonical:
        errors.append(
            "article.visual_kit.selected_roles must follow the canonical role order"
        )
    if len(selected) != requested_count:
        errors.append(
            "article.visual_kit.selected_roles length must equal "
            "production_preferences.micro_component_count"
        )
    if errors:
        return [], errors
    return canonical, errors


def build_visual_kit_plan(
    article_path: Path,
    org_dir: Path,
    *,
    live_authority: LiveAuthorityCallback | None = None,
    portable_trust_store: Path | None = None,
) -> dict[str, Any]:
    report = validate_pack(
        org_dir,
        live_authority=live_authority,
        portable_trust_store=portable_trust_store,
    )
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
    production_preferences = validate_production_preferences(
        article,
        resolved_route_id=route["id"],
    )
    requested_count_raw = production_preferences.get("micro_component_count")
    requested_count = (
        requested_count_raw
        if isinstance(requested_count_raw, int)
        and not isinstance(requested_count_raw, bool)
        and 0 <= requested_count_raw <= len(KIT_ROLES)
        # Invalid or missing preferences are already blocking errors.  Use a
        # zero-work sentinel so validation never schedules the legacy four
        # slots as an implicit choice.
        else 0
    )
    selected_roles, selection_errors = selected_kit_roles(article, requested_count)
    selected_role_set = set(selected_roles)
    selected_definitions = [
        definition for definition in KIT_ROLES if definition["role"] in selected_role_set
    ]
    organization_reference_policy = organization.get("provenance", {}).get(
        "visual_reference_policy", "source-zero"
    )
    style_grammar = (
        route.get("style_grammar")
        if organization_reference_policy == "explicit-style-grammar"
        else None
    )
    reference_policy = (
        "explicit-style-grammar" if isinstance(style_grammar, dict) else "source-zero"
    )
    if isinstance(style_grammar, dict):
        grammar_tokens = json.dumps(
            style_grammar.get("tokens", {}),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        grammar_instruction = (
            f"Apply only abstract style grammar {grammar_tokens} "
            f"(SHA-256 {style_grammar.get('sha256')}); never copy reference text, "
            "photographs, logos, specific layout, component geometry, or artwork. "
        )
    else:
        grammar_instruction = ""
    calibration = calibration_state(
        organization,
        route["id"],
        pack["assets"],
        require_background_family=production_preferences.get("generate_backgrounds") is True,
    )
    storyboard = build_storyboard_plan(article_path)
    storyboard_by_id = {
        item.get("id"): item for item in storyboard["chapters"] if item.get("id")
    }
    registered = {
        item.get("id"): item
        for item in pack["assets"].get("assets", [])
        if isinstance(item, dict) and item.get("id")
    }
    approved_assets = visual_kit_assets(article)
    visual_kit_document = article.get("visual_kit")
    raw_visual_kit_assets = (
        visual_kit_document.get("assets")
        if isinstance(visual_kit_document, dict)
        else None
    )
    visual_kit_shape_errors: list[str] = []
    if not isinstance(raw_visual_kit_assets, list):
        visual_kit_shape_errors.append("article.visual_kit.assets must be an array")
    elif any(not isinstance(item, dict) for item in raw_visual_kit_assets):
        visual_kit_shape_errors.append(
            "article.visual_kit.assets entries must be objects"
        )
    visual_kit_status = (
        article.get("visual_kit", {}).get("status")
        if isinstance(article.get("visual_kit"), dict)
        else None
    )
    by_role: dict[str, dict[str, Any]] = {}
    asset_selection_errors: list[str] = []
    for item in approved_assets:
        role = item.get("role")
        if not isinstance(role, str):
            asset_selection_errors.append(
                "article.visual_kit.assets entries require a role"
            )
            continue
        if role not in selected_role_set:
            asset_selection_errors.append(
                f"article.visual_kit asset role is not selected: {role}"
            )
            continue
        if role in by_role:
            asset_selection_errors.append(
                f"article.visual_kit contains more than one asset for selected role: {role}"
            )
            continue
        by_role[role] = item
    grounded_texts = article_texts(article)
    motifs = "、".join(organization.get("visual", {}).get("motifs", []))
    avoid = "、".join(organization.get("visual", {}).get("avoid", []))
    tokens = organization["visual"]["tokens"]
    palette = ", ".join(
        f"{name} {tokens[name]}"
        for name in ("ink", "accent", "accent_alt", "surface_alt")
    )
    key_backgrounds = ranked_key_backgrounds(tokens)
    slots: list[dict[str, Any]] = []
    missing_roles: list[str] = []
    semantic_errors: list[str] = [
        *production_preferences["errors"],
        *selection_errors,
        *visual_kit_shape_errors,
        *asset_selection_errors,
    ]
    composition_roles: set[str] = set()
    registered_generated_ids: set[str] = set()
    native_component_node_ids: set[str] = set()
    validated_lineage_entries: list[dict[str, str]] = []
    for slot_index, definition in enumerate(selected_definitions):
        role = definition["role"]
        validated_lineage: dict[str, Any] | None = None
        acquisition_assurance: dict[str, Any] | None = None
        controlled_key_color = key_backgrounds[slot_index % len(key_backgrounds)]
        approved = by_role.get(role)
        asset_id = approved.get("id") if approved else None
        chapter_id = approved.get("storyboard_chapter") if approved else None
        source_text = approved.get("source_text") if approved else None
        concrete_subject = approved.get("concrete_subject") if approved else None
        action = approved.get("action") if approved else None
        composition_role = approved.get("composition_role") if approved else None
        placement = approved.get("placement") if approved else definition["placement"]
        chapter = storyboard_by_id.get(chapter_id)
        if approved:
            if not chapter:
                semantic_errors.append(f"visual role {role} references unknown storyboard chapter: {chapter_id}")
            if not source_text_is_grounded(source_text, grounded_texts):
                semantic_errors.append(f"visual role {role} source_text is not grounded in article copy")
            if not concrete_subject_is_specific(concrete_subject):
                semantic_errors.append(f"visual role {role} concrete_subject is generic or missing")
            if not isinstance(action, str) or len(action.strip()) < 2:
                semantic_errors.append(f"visual role {role} action is missing")
            if composition_role not in ALLOWED_COMPOSITION_ROLES:
                semantic_errors.append(f"visual role {role} has invalid composition_role: {composition_role}")
            else:
                composition_roles.add(composition_role)
        registered_asset = registered.get(asset_id) if asset_id else None
        expected_component_name = f"WeChat/Ornament/{''.join(part.title() for part in role.split('-'))}/{pack['ardot']['variable_mode']}"
        ready = bool(
            registered_asset
            # Legacy generated micros remain readable as migration inputs, but
            # they can never unlock a current article layout without verified
            # provider acquisition and raw -> derived cutout lineage.
            and registered_asset.get("origin") == "derived"
            and isinstance(registered_asset.get("cutout"), dict)
            and article_id in (registered_asset.get("generated_for_articles") or [])
        )
        if registered_asset:
            if role not in (registered_asset.get("roles") or []):
                semantic_errors.append(f"visual role {role} is not declared on registered asset {asset_id}")
                ready = False
            if registered_asset.get("visual_role") != "article-micro":
                semantic_errors.append(f"visual role {role} asset {asset_id} must declare visual_role=article-micro")
                ready = False
            location = registered_asset.get("location")
            try:
                asset_path = resolve_pack_asset(
                    org_dir,
                    location,
                    label=f"visual role {role} registered asset location",
                )
            except PackAssetResolutionError as exc:
                semantic_errors.append(str(exc))
                ready = False
                alpha_report = {"ok": False, "errors": ["local PNG required"]}
            else:
                alpha_report = validate_micro_asset(asset_path, role)
                if not alpha_report["ok"]:
                    semantic_errors.extend(
                        f"visual role {role} alpha/shape check: {error}"
                        for error in alpha_report["errors"]
                    )
                    ready = False
                lineage = registered_asset.get("cutout")
                report_location = (
                    lineage.get("report_location") if isinstance(lineage, dict) else None
                )
                if not isinstance(report_location, str) or not report_location:
                    semantic_errors.append(
                        f"visual role {role} asset {asset_id} lacks revalidatable acquisition lineage"
                    )
                    ready = False
                else:
                    try:
                        report_path = resolve_pack_asset(
                            org_dir,
                            report_location,
                            label=f"visual role {role} cutout report location",
                        )
                    except PackAssetResolutionError as exc:
                        semantic_errors.append(str(exc))
                        lineage_validation = None
                    else:
                        lineage_validation = validate_cutout_derivation_report(
                            org_dir,
                            report_path,
                            asset_path,
                            role,
                            live_authority=live_authority,
                            portable_trust_store=portable_trust_store,
                        )
                    if lineage_validation is None:
                        ready = False
                    elif not lineage_validation["ok"]:
                        semantic_errors.extend(
                            f"visual role {role} acquisition/derivative revalidation: {error}"
                            for error in lineage_validation["errors"]
                        )
                        ready = False
                    elif isinstance(lineage_validation.get("lineage"), dict):
                        validated_lineage = lineage_validation["lineage"]
                stored_quality = registered_asset.get("quality")
                actual_inspection = alpha_report.get("inspection", {})
                if (
                    not isinstance(stored_quality, dict)
                    or stored_quality.get("alpha_verified") is not True
                    or stored_quality.get("sha256") != actual_inspection.get("sha256")
                    or stored_quality.get("width_px") != actual_inspection.get("width_px")
                    or stored_quality.get("height_px") != actual_inspection.get("height_px")
                ):
                    semantic_errors.append(
                        f"visual role {role} stored Alpha quality evidence does not match asset {asset_id}"
                    )
                    ready = False
                approved_sha256 = approved.get("asset_sha256") if approved else None
                if approved_sha256 != actual_inspection.get("sha256"):
                    semantic_errors.append(
                        f"visual role {role} article asset_sha256 must match the approved cutout pixels"
                    )
                    ready = False
            native_component = approved.get("ardot_component") if approved else None
            if not isinstance(native_component, dict):
                semantic_errors.append(f"visual role {role} requires native Ardot component evidence")
                ready = False
            else:
                for field in ("file_url", "node_id", "name"):
                    if not isinstance(native_component.get(field), str) or not native_component.get(field):
                        semantic_errors.append(f"visual role {role} ardot_component.{field} is required")
                        ready = False
                if native_component.get("name") != expected_component_name:
                    semantic_errors.append(
                        f"visual role {role} Ardot component name must be {expected_component_name}"
                    )
                    ready = False
                if native_component.get("file_url") != pack["ardot"].get("design_file", {}).get("url"):
                    semantic_errors.append(
                        f"visual role {role} Ardot component must belong to the organization design file"
                    )
                    ready = False
                component_node_id = native_component.get("node_id")
                if isinstance(component_node_id, str) and component_node_id:
                    if component_node_id in native_component_node_ids:
                        semantic_errors.append(
                            f"visual role {role} reuses an Ardot component node: {component_node_id}"
                        )
                        ready = False
                    native_component_node_ids.add(component_node_id)
        else:
            alpha_report = {"ok": False, "errors": ["asset is not registered"]}
        if ready and asset_id:
            authority_scope = (
                validated_lineage.get("authority_scope_at_creation")
                if isinstance(validated_lineage, dict)
                else None
            )
            authority_assurance = (
                validated_lineage.get("acquisition_assurance")
                if isinstance(validated_lineage, dict)
                else None
            )
            host_attested = (
                validated_lineage.get("host_attested")
                if isinstance(validated_lineage, dict)
                else None
            )
            portable = (
                validated_lineage.get("portable")
                if isinstance(validated_lineage, dict)
                else None
            )
            if authority_scope == "current-session-operator-harness-trusted":
                if (
                    authority_assurance
                    != "operator-harness-trusted-current-session"
                    or host_attested is not False
                    or portable is not False
                ):
                    semantic_errors.append(
                        f"visual role {role} current-session acquisition overclaims assurance"
                    )
                    ready = False
            elif authority_scope == "portable-signed":
                if (
                    authority_assurance != "portable-ed25519-double-signed"
                    or host_attested is not True
                    or portable is not True
                ):
                    semantic_errors.append(
                        f"visual role {role} portable acquisition assurance is incomplete"
                    )
                    ready = False
            else:
                semantic_errors.append(
                    f"visual role {role} lacks an accepted acquisition assurance mode"
                )
                ready = False
            acquisition_assurance = {
                "mode": authority_scope,
                "assurance": authority_assurance,
                "host_attested": host_attested,
                "portable": portable,
            }
            required_lineage = {
                "source_sha256": (
                    validated_lineage.get("source_sha256")
                    if isinstance(validated_lineage, dict)
                    else None
                ),
                "authority_binding_sha256": (
                    validated_lineage.get("authority_binding_sha256")
                    if isinstance(validated_lineage, dict)
                    else None
                ),
                "accepted_provider_request_id": (
                    validated_lineage.get("accepted_provider_request_id")
                    if isinstance(validated_lineage, dict)
                    else None
                ),
            }
            missing_lineage = [
                name
                for name, value in required_lineage.items()
                if not isinstance(value, str) or not value
            ]
            if missing_lineage:
                semantic_errors.append(
                    f"visual role {role} lacks unique-source lineage fields: "
                    + ", ".join(missing_lineage)
                )
                ready = False
            else:
                validated_lineage_entries.append(
                    {"role": role, **required_lineage}  # type: ignore[arg-type]
                )
                registered_generated_ids.add(asset_id)
        if not ready:
            missing_roles.append(role)
        prompt_prefix = (
            f"Create one text-free {definition['purpose']} for {organization['identity']['name']}. "
            f"Concrete subject: {concrete_subject or '[choose from the named chapter]'}. "
            f"Depict this action: {action or '[define a visible action]'}. "
            f"Ground it only in this approved copy: {source_text or '[quote one exact article sentence]'}. "
            f"Chapter visual intent: {(chapter or {}).get('visual_intent', '[bind to an approved storyboard chapter]')}. "
            f"Its composition job is {composition_role or '[anchor/motion/connector/punctuation]'} at {placement}. "
            f"Follow the calibrated {route['dominant_style']} direction with motifs "
            f"{motifs} and palette {palette}. {grammar_instruction}"
            f"Aspect ratio {definition['aspect_ratio']}. Generate one isolated subject. All editorial spacing will be "
            f"created later in Ardot, never baked into the source canvas. Show only the subject and an "
            f"open effect that does not cast onto a ground plane. "
            f"Do not create a rectangle, card, UI panel, border, poster, generic blob, letters, "
            f"numbers, watermark, signature, logo, or QR code. Transparent article micros are not "
            f"watermark carriers. Never reuse a neutral migration calibration mark or its "
            f"grayscale test treatment. Avoid: {avoid}."
        )
        prompt = (
            prompt_prefix
            + " Return the provider-original PNG with a genuinely transparent background and real "
            "pixel alpha. Background pixels must have alpha 0. Keep a clean 6–12% transparent safety "
            "margin around every substantive pixel. Do not simulate transparency with white, black, "
            "a colored plane, checkerboard pixels, haze, or a rectangular matte. Codex will download "
            "the original PNG and verify its actual Alpha channel locally."
        )
        controlled_key_prompt = (
            prompt_prefix
            + f" Return the provider-original PNG on a perfectly flat {controlled_key_color} key "
            "background, keeping a clean 6–12% key-colored border around every substantive pixel. "
            "The key color must not appear in the subject. Do not add a shadow or semi-transparent "
            "effect onto the background. This may be selected as the first real-asset source when "
            "uniform key separation is safer than relying on provider-native transparency."
        )
        native_prompt_sha256 = "sha256:" + hashlib.sha256(
            prompt.encode("utf-8")
        ).hexdigest()
        controlled_key_prompt_sha256 = "sha256:" + hashlib.sha256(
            controlled_key_prompt.encode("utf-8")
        ).hexdigest()
        slots.append(
            {
                **definition,
                "asset_slot_id": f"kit.{role}",
                "status": "approved-and-registered" if ready else "generate-required",
                "asset_id": asset_id,
                "storyboard_chapter": chapter_id,
                "source_text": source_text,
                "concrete_subject": concrete_subject,
                "action": action,
                "composition_role": composition_role,
                "placement": placement,
                "prompt": prompt,
                "prompt_sha256": native_prompt_sha256,
                "controlled_key_prompt": controlled_key_prompt,
                "controlled_key_prompt_sha256": controlled_key_prompt_sha256,
                # Compatibility aliases for readers of the previous plan shape.
                # They do not make controlled-key secondary or require a failed
                # native-alpha request.
                "fallback_prompt": controlled_key_prompt,
                "fallback_prompt_sha256": controlled_key_prompt_sha256,
                "source_generation": {
                    "route": "chatgpt-web-image-route-v1",
                    "provider_skill": "chatgpt-web-image-route",
                    "raw_output_contract": "original-png-v1",
                    "alpha_claim_trusted": False,
                    "acquisition_preference": "native-alpha-or-controlled-key-per-real-asset",
                    "preferred_mode": "select-per-real-asset",
                    "allowed_initial_modes": ["native-alpha", "controlled-key"],
                    "processor_args_by_mode": {
                        "native-alpha": ["--require-native-alpha"],
                        "controlled-key": ["--key-color", controlled_key_color],
                    },
                    "controlled_key_color": controlled_key_color,
                    "source_options": [
                        {
                            "mode": "native-alpha",
                            "prompt_field": "prompt",
                            "prompt_sha256": native_prompt_sha256,
                            "processor_args": ["--require-native-alpha"],
                            "allowed_as_first_attempt": True,
                        },
                        {
                            "mode": "controlled-key",
                            "prompt_field": "controlled_key_prompt",
                            "prompt_sha256": controlled_key_prompt_sha256,
                            "processor_args": ["--key-color", controlled_key_color],
                            "key_color": controlled_key_color,
                            "allowed_as_first_attempt": True,
                        },
                    ],
                    # Deprecated aliases retained for plan readers from the
                    # previous release; canonical readers use source_options.
                    "preferred_processor_args": ["--require-native-alpha"],
                    "maximum_source_attempts": 2,
                    "fallback_mode": "controlled-key",
                    "fallback_key_color": controlled_key_color,
                    "fallback_processor_args": ["--key-color", controlled_key_color],
                    "legacy_compatibility": {
                        "alias_fields": [
                            "preferred_processor_args",
                            "fallback_mode",
                            "fallback_key_color",
                            "fallback_processor_args",
                            "attempt_prompts",
                        ],
                        "implies_native_first": False,
                        "canonical_field": "source_options",
                    },
                    "attempt_prompts": [
                        {
                            "source_option": 1,
                            "mode": "native-alpha",
                            "prompt_sha256": native_prompt_sha256,
                            "allowed_as_first_attempt": True,
                        },
                        {
                            "source_option": 2,
                            "mode": "controlled-key",
                            "prompt_sha256": controlled_key_prompt_sha256,
                            "allowed_as_first_attempt": True,
                        },
                    ],
                    "request_recovery": {
                        "separate_from_source_attempts": True,
                        "resume_same_provider_request_first": True,
                        "duplicate_submission_allowed_while_status_unknown": False,
                        "browser_control_failure_consumes_source_attempt": False,
                    },
                    "processor": "scripts/prepare_micro_cutout.py",
                    "output_contract": "subject-cutout-rgba8-v1",
                },
                "registration": {
                    "source_origin": "generated-illustrative",
                    "origin": "derived",
                    "role": role,
                    "generated_for": article_id,
                    "cutout_report_required": True,
                },
                "alpha_validation": alpha_report,
                "acquisition_assurance": acquisition_assurance,
                "ardot_component_name": expected_component_name,
            }
        )
    minimum_unique_assets = requested_count
    minimum_composition_roles = min(3, requested_count)
    lineage_uniqueness = {
        field: len({entry[field] for entry in validated_lineage_entries})
        for field in (
            "source_sha256",
            "authority_binding_sha256",
            "accepted_provider_request_id",
        )
    }
    for field, unique_count in lineage_uniqueness.items():
        if unique_count < requested_count:
            semantic_errors.append(
                f"visual kit requires {requested_count} distinct {field} values; found {unique_count}"
            )
    expected_status = "not-requested" if requested_count == 0 else "approved"
    ready_for_layout = (
        calibration["ready"]
        and storyboard["ready_for_visual_kit"]
        and visual_kit_status == expected_status
        and not missing_roles
        and not semantic_errors
        and len(composition_roles) >= minimum_composition_roles
        and len(registered_generated_ids) >= minimum_unique_assets
    )
    blocking_reasons = calibration["blocking_reasons"] + storyboard["errors"]
    blocking_reasons.extend(f"missing visual role: {role}" for role in missing_roles)
    blocking_reasons.extend(semantic_errors)
    if visual_kit_status != expected_status:
        blocking_reasons.append(
            f"article.visual_kit.status must be {expected_status} for the selected component count"
        )
    if len(registered_generated_ids) < minimum_unique_assets:
        blocking_reasons.append(
            f"needs at least {minimum_unique_assets} unique generated micro assets; found {len(registered_generated_ids)}"
        )
    if len(composition_roles) < minimum_composition_roles:
        blocking_reasons.append(
            f"visual kit needs at least {minimum_composition_roles} composition roles; found {len(composition_roles)}"
        )
    required_sequence = [
        "STOP if the organization route has no approved Ardot calibration benchmark",
        "STOP if the narrative storyboard is not approved and complete",
    ]
    if requested_count == 0:
        required_sequence.extend(
            [
                "no generated micro component was requested; keep visual_kit.status=not-requested and assets=[]",
                "assemble the long article without generated micro-component slots",
            ]
        )
    else:
        required_sequence.extend(
            [
                "load chatgpt-web-image-route and codex-with-chatgpt, then generate every selected missing slot through one visible built-in-browser ChatGPT session before any article layout",
                "download each original PNG; screenshots, preview canvases, clipboard pixels, and copied remote URLs are forbidden substitutes",
                "select native-alpha or the plan's uniform controlled-key source for each real component; run prepare_micro_cutout.py with the matching explicit arguments and never infer a background",
                "run inspect_asset.py for each role; reject unsafe source separation, missing/opaque final Alpha, wrong aspect, matte, halo, debris, framing, generic subjects, or text",
                f"save raw sources under assets/generated and register only approved derived RGBA cutouts with generated_for_articles={article_id}",
                "record the registered IDs under article.visual_kit.assets",
                f"create {requested_count} distinct native Ardot ornament components and record file_url, node_id, and exact name on each selected article.visual_kit asset",
                "only then assemble the long article",
            ]
        )
    return {
        "schema_version": 1,
        "kind": "org-wechat-visual-kit-plan",
        "organization_id": organization["id"],
        "article_id": article_id,
        "article_title": article.get("title"),
        "article_type": article.get("article_type"),
        "route_id": route["id"],
        "style_reference_policy": reference_policy,
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
        "production_preferences": production_preferences,
        "calibration": calibration,
        "storyboard": storyboard,
        "requested_micro_component_count": requested_count,
        "selected_roles": selected_roles,
        "minimum_micro_component_roles": requested_count,
        "minimum_unique_generated_micro_assets": minimum_unique_assets,
        "minimum_composition_roles": minimum_composition_roles,
        "lineage_uniqueness": {
            "required_distinct_per_field": requested_count,
            "validated_role_count": len(validated_lineage_entries),
            **lineage_uniqueness,
        },
        "generation_route": {
            "required": requested_count > 0,
            "default": "chatgpt-web-image-route-v1",
            "provider_skill": "chatgpt-web-image-route",
            "session_skill": "codex-with-chatgpt",
            "browser_skill": "browser:control-in-app-browser",
            "computer_use_allowed": False,
            "raw_download_required": True,
            "alpha_claim_trusted": False,
            "acquisition_preference": "native-alpha-or-controlled-key-per-real-asset",
            "processor": "scripts/prepare_micro_cutout.py",
            "output_contract": "subject-cutout-rgba8-v1",
            "current_session_assurance": (
                "operator-harness-trusted-current-session; host_attested=false; "
                "portable=false"
            ),
            "optional_policy_hook_can_upgrade_assurance": False,
            "portable_assurance": "portable-ed25519-double-signed",
        },
        "visual_kit_status": visual_kit_status,
        "ready_for_layout": ready_for_layout,
        "missing_roles": missing_roles,
        "blocking_reasons": blocking_reasons,
        "semantic_errors": semantic_errors,
        "slots": slots,
        "required_sequence": required_sequence,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("article", type=Path)
    parser.add_argument("--org", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--portable-trust-store",
        type=Path,
        help=(
            "Protected host trust store for portable-signed provider receipts; "
            "current-session readiness uses the migration/request/ingestion/pixel chain"
        ),
    )
    args = parser.parse_args()
    try:
        article = existing_regular_file(args.article, label="article")
        organization = existing_directory(args.org, label="organization pack")
        trust_store = (
            existing_regular_file(
                args.portable_trust_store,
                label="portable trust store",
            )
            if args.portable_trust_store is not None
            else None
        )
        output = new_file_path(
            args.output,
            label="visual kit output",
            forbidden_root=RUNTIME_ROOT,
        )
        plan = build_visual_kit_plan(
            article,
            organization,
            portable_trust_store=trust_store,
        )
        write_text_create_once(
            output,
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
            label="visual kit output",
            forbidden_root=RUNTIME_ROOT,
        )
    except (SafePathError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(
        json.dumps(
            {
                "created": str(output),
                "ready_for_layout": plan["ready_for_layout"],
                "missing_roles": plan["missing_roles"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

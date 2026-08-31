#!/usr/bin/env python3
"""Plan the mandatory article-specific micro-illustration kit before layout."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from asset_quality import validate_micro_asset
from build_storyboard import build_storyboard_plan
from orgs import load_pack, validate_pack
from workflow_quality import (
    ALLOWED_COMPOSITION_ROLES,
    article_texts,
    calibration_state,
    concrete_subject_is_specific,
    source_text_is_grounded,
)


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
    calibration = calibration_state(organization, route["id"], pack["assets"])
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
    semantic_errors: list[str] = []
    composition_roles: set[str] = set()
    registered_generated_ids: set[str] = set()
    native_component_node_ids: set[str] = set()
    for slot_index, definition in enumerate(KIT_ROLES):
        role = definition["role"]
        key_color = key_backgrounds[slot_index % len(key_backgrounds)]
        fallback_key_color = key_backgrounds[(slot_index + 1) % len(key_backgrounds)]
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
            # New registrations are always `derived` and carry a verified
            # raw-source -> cutout lineage.  Keep legacy generated entries
            # readable so existing organization packs can be migrated, while
            # `orgs.py register-asset` prevents creating new legacy micros.
            and registered_asset.get("origin") in {"derived", "generated-illustrative"}
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
            if not isinstance(location, str) or re.match(r"^(?:https?://|data:)", location):
                semantic_errors.append(f"visual role {role} requires a local PNG for alpha verification")
                ready = False
                alpha_report = {"ok": False, "errors": ["local PNG required"]}
            else:
                alpha_report = validate_micro_asset((org_dir / location).resolve(), role)
                if not alpha_report["ok"]:
                    semantic_errors.extend(
                        f"visual role {role} alpha/shape check: {error}"
                        for error in alpha_report["errors"]
                    )
                    ready = False
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
            registered_generated_ids.add(asset_id)
        if not ready:
            missing_roles.append(role)
        prompt = (
            f"Create one text-free {definition['purpose']} for {organization['identity']['name']}. "
            f"Concrete subject: {concrete_subject or '[choose from the named chapter]'}. "
            f"Depict this action: {action or '[define a visible action]'}. "
            f"Ground it only in this approved copy: {source_text or '[quote one exact article sentence]'}. "
            f"Chapter visual intent: {(chapter or {}).get('visual_intent', '[bind to an approved storyboard chapter]')}. "
            f"Its composition job is {composition_role or '[anchor/motion/connector/punctuation]'} at {placement}. "
            f"Follow the calibrated {route['dominant_style']} direction with motifs "
            f"{motifs} and palette {palette}. {grammar_instruction}"
            f"Aspect ratio {definition['aspect_ratio']}. Generate one isolated subject on a perfectly "
            f"flat {key_color} key background, keeping a clean 6–12% key-colored border around every "
            f"substantive pixel. The key color must not appear in the subject. Do not draw a "
            f"checkerboard or claim transparency in the preview; Codex will download the original PNG "
            f"and derive or verify the real Alpha channel locally. All editorial spacing will be "
            f"created later in Ardot, never baked into the source canvas. Show only the subject and an "
            f"open effect that does not cast onto a ground plane. "
            f"Do not create a rectangle, card, UI panel, border, poster, generic blob, letters, "
            f"numbers, watermark, signature, logo, or QR code. Transparent article micros are not "
            f"watermark carriers. Avoid: {avoid}."
        )
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
                "source_generation": {
                    "route": "chatgpt-web-image-route-v1",
                    "provider_skill": "chatgpt-web-image-route",
                    "raw_output_contract": "original-png-v1",
                    "alpha_claim_trusted": False,
                    "key_color": key_color,
                    "fallback_key_color": fallback_key_color,
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
                "ardot_component_name": expected_component_name,
            }
        )
    minimum_unique_assets = 4
    ready_for_layout = (
        calibration["ready"]
        and storyboard["ready_for_visual_kit"]
        and visual_kit_status == "approved"
        and not missing_roles
        and not semantic_errors
        and len(composition_roles) >= 3
        and len(registered_generated_ids) >= minimum_unique_assets
    )
    blocking_reasons = calibration["blocking_reasons"] + storyboard["errors"]
    blocking_reasons.extend(f"missing visual role: {role}" for role in missing_roles)
    blocking_reasons.extend(semantic_errors)
    if visual_kit_status != "approved":
        blocking_reasons.append("article.visual_kit.status must be approved after image inspection")
    if len(registered_generated_ids) < minimum_unique_assets:
        blocking_reasons.append(
            f"needs at least {minimum_unique_assets} unique generated micro assets; found {len(registered_generated_ids)}"
        )
    if len(composition_roles) < 3:
        blocking_reasons.append(
            f"visual kit needs at least 3 composition roles; found {len(composition_roles)}"
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
        "calibration": calibration,
        "storyboard": storyboard,
        "minimum_micro_component_roles": len(KIT_ROLES),
        "minimum_unique_generated_micro_assets": minimum_unique_assets,
        "generation_route": {
            "default": "chatgpt-web-image-route-v1",
            "provider_skill": "chatgpt-web-image-route",
            "session_skill": "codex-with-chatgpt",
            "browser_skill": "browser:control-in-app-browser",
            "computer_use_allowed": False,
            "raw_download_required": True,
            "alpha_claim_trusted": False,
            "processor": "scripts/prepare_micro_cutout.py",
            "output_contract": "subject-cutout-rgba8-v1",
        },
        "visual_kit_status": visual_kit_status,
        "ready_for_layout": ready_for_layout,
        "missing_roles": missing_roles,
        "blocking_reasons": blocking_reasons,
        "semantic_errors": semantic_errors,
        "slots": slots,
        "required_sequence": [
            "STOP if the organization route has no approved Ardot calibration benchmark",
            "STOP if the narrative storyboard is not approved and complete",
            "load chatgpt-web-image-route and codex-with-chatgpt, then generate every missing slot through one visible built-in-browser ChatGPT session before any article layout",
            "download each original PNG; screenshots, preview canvases, clipboard pixels, and copied remote URLs are forbidden substitutes",
            "run prepare_micro_cutout.py and inspect_asset.py for each role; reject unsafe key backgrounds, missing/opaque Alpha, wrong aspect, matte, halo, debris, framing, generic subjects, or text",
            f"save raw sources under assets/generated and register only approved derived RGBA cutouts with generated_for_articles={article_id}",
            "record the registered IDs under article.visual_kit.assets",
            "create four distinct native Ardot ornament components and record file_url, node_id, and exact name on each article.visual_kit asset",
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

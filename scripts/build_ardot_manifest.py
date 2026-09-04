#!/usr/bin/env python3
"""Build a deterministic Ardot assembly manifest from an article and organization pack."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

if __name__ == "__main__":
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/build_ardot_manifest.py")

from build_visual_kit import build_visual_kit_plan
from build_storyboard import build_storyboard_plan
from asset_role_policy import validate_background_assignment
from orgs import load_pack, validate_pack
from pack_assets import PackAssetResolutionError, resolve_pack_asset
from workflow_quality import (
    WORKFLOW_ATTRIBUTION_MARKER,
    WORKFLOW_ATTRIBUTION_TEXT,
    WORKFLOW_ATTRIBUTION_TEXT_SHA256,
    calibration_state,
    validate_interaction_plan,
    validate_production_preferences,
    validate_typography_plan,
    watermark_inventory,
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

MICRO_COMPONENT_POLICY = {
    "copy_enclosure": "none",
    "copy_emphasis": "native editable scale contrast plus one non-frame technique",
    "minimum_primary_copy_px": 22,
    "minimum_primary_copy_scale_ratio": 1.35,
    "maximum_image_width_ratio": 0.72,
    "maximum_component_width_ratio": 0.82,
    "placement_evidence": "scale to the confirmed selected component count",
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
        try:
            local_path = str(
                resolve_pack_asset(
                    pack["path"],
                    location,
                    label=f"registered asset {ref} location",
                )
            )
        except PackAssetResolutionError as exc:
            raise ValueError(str(exc)) from exc
        return {
            "ref": ref,
            "registered": True,
            "kind": item.get("kind"),
            "origin": item.get("origin"),
            "visual_role": item.get("visual_role"),
            "background_family_id": item.get("background_family_id"),
            "location": location,
            "local_path": local_path,
            "watermark": item.get("watermark"),
        }
    return {
        "ref": ref,
        "registered": False,
        "location": ref,
        # Article-local and remote paths are not an alternate asset registry.
        # Requiring registration prevents another pack, old output or arbitrary
        # external file from entering a source-zero compile.
        "local_path": None,
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
    provenance = organization.get("provenance", {})
    organization_reference_policy = provenance.get(
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
    production_preferences = validate_production_preferences(
        article,
        resolved_route_id=route["id"],
    )
    calibration = calibration_state(
        organization,
        route["id"],
        pack["assets"],
        require_background_family=production_preferences.get("generate_backgrounds") is True,
    )
    calibration["background_family_quality"] = report.get("visual_calibration", {}).get(
        "background_family_quality"
    )
    provenance_watermark = report.get("provenance_watermark")
    if not isinstance(provenance_watermark, dict):
        provenance_watermark = watermark_inventory(
            organization,
            pack["assets"],
            pack["path"],
        )
    storyboard = build_storyboard_plan(article_path)
    visual_kit_plan = build_visual_kit_plan(article_path, org_dir)
    requested_micro_component_count = visual_kit_plan[
        "requested_micro_component_count"
    ]
    selected_micro_roles = visual_kit_plan["selected_roles"]
    selected_micro_role_set = set(selected_micro_roles)
    minimum_micro_composition_relations = min(3, requested_micro_component_count)
    minimum_micro_screenshot_sections = min(3, requested_micro_component_count)
    if requested_micro_component_count == 0:
        micro_staggering = "not applicable; no micro components were requested"
    elif requested_micro_component_count == 1:
        micro_staggering = "use one content-grounded partial-width placement"
    elif requested_micro_component_count == 2:
        micro_staggering = "use both left and right offsets with visible scale variation"
    else:
        micro_staggering = (
            "use both left and right offsets, at least 3 distinct offsets, and at "
            "least 3 composition relations across the selected roles"
        )
    ardot = pack["ardot"]
    typography = validate_typography_plan(article, organization, ardot)
    interaction_plan = validate_interaction_plan(
        article,
        ardot,
        article_path,
        require_evidence=False,
    )
    kit_asset_by_role = {
        item["role"]: item.get("asset_id")
        for item in visual_kit_plan["slots"]
        if item.get("asset_id")
    }
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
        block_kit_roles = [
            role for role in kit_roles if role in selected_micro_role_set
        ]
        kit_assets = [
            kit_asset_by_role[role]
            for role in block_kit_roles
            if role in kit_asset_by_role
        ]
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
                "micro_component_policy": {
                    **MICRO_COMPONENT_POLICY,
                    "staggering": micro_staggering,
                },
                "micro_visual_roles": block_kit_roles,
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
    unresolved = [item["ref"] for item in assets if not item.get("local_path")]
    asset_by_ref = {item["ref"]: item for item in assets}
    background_refs = list(
        dict.fromkeys(
            raw.get("background")
            for raw in article.get("blocks", [])
            if isinstance(raw, dict)
            and isinstance(raw.get("background"), str)
            and raw.get("background")
        )
    )
    background_assignment_errors: list[str] = []
    forbidden_background_assignments: list[str] = []
    for background_ref in background_refs:
        background_asset = asset_by_ref.get(background_ref)
        if not isinstance(background_asset, dict) or not background_asset.get("registered"):
            continue
        assignment_errors = validate_background_assignment(
            background_asset,
            generated_backgrounds_enabled=(
                production_preferences.get("generate_backgrounds") is True
            ),
        )
        if assignment_errors:
            forbidden_background_assignments.append(background_ref)
            background_assignment_errors.extend(
                f"background {background_ref}: {message}"
                for message in assignment_errors
            )
    block_by_index = {item["index"]: item for item in blocks}
    chapters = []
    for chapter in storyboard["chapters"]:
        chapter_blocks = [
            block_by_index[index]
            for index in chapter.get("block_indices", [])
            if index in block_by_index
        ]
        chapters.append({
            **chapter,
            "blocks": chapter_blocks,
            "assembly_policy": "bespoke-chapter-composition",
            "component_policy": "reuse primitives selectively; do not wrap every semantic block",
        })
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
        },
        "style_reference": {
            "policy": reference_policy,
            "source_ids": (
                provenance.get("style_reference_source_ids", [])
                if reference_policy == "explicit-style-grammar"
                else []
            ),
            "scope": (
                provenance.get("style_reference_scope")
                if reference_policy == "explicit-style-grammar"
                else None
            ),
            "reference_reviewed_at": (
                provenance.get("reference_reviewed_at")
                if reference_policy == "explicit-style-grammar"
                else None
            ),
            "non_copy_constraints": (
                provenance.get("style_reference_non_copy_constraints", [])
                if reference_policy == "explicit-style-grammar"
                else []
            ),
            "grammar_sha256": (
                style_grammar.get("sha256") if isinstance(style_grammar, dict) else None
            ),
            "preset_id": (
                style_grammar.get("preset_id") if isinstance(style_grammar, dict) else None
            ),
            "preset_label": (
                style_grammar.get("label") if isinstance(style_grammar, dict) else None
            ),
        },
        "calibration": calibration,
        "provenance_watermark": provenance_watermark,
        "workflow_attribution": {
            "required": True,
            "policy_id": WORKFLOW_ATTRIBUTION_MARKER,
            "classification": "repository-usage-credit",
            "text": WORKFLOW_ATTRIBUTION_TEXT,
            "text_sha256": f"sha256:{WORKFLOW_ATTRIBUTION_TEXT_SHA256}",
            "marker": WORKFLOW_ATTRIBUTION_MARKER,
            "placement": "terminal-after-all-article-blocks",
            "component_name": f"WeChat/Footer/WorkflowAttribution/{mode}",
            "native_editable_text": True,
            "organization_identity": False,
        },
        "storyboard": storyboard,
        "variables": variables,
        "visual_kit": visual_kit_plan,
        "production_preferences": production_preferences,
        "typography": typography,
        "interaction_plan": interaction_plan,
        "chapters": chapters,
        "blocks": blocks,
        "assets": assets,
        "assembly": [
            "STOP if calibration.ready is false",
            "STOP if storyboard.ready_for_visual_kit is false",
            "STOP if visual_kit.ready_for_layout is false",
            "STOP if typography.ready is false",
            "STOP if interaction_plan.ready is false",
            "STOP if provenance_watermark.ready is false for a required generated-image watermark policy",
            "when style_reference.policy is explicit-style-grammar, preserve the canonical grammar SHA-256 and copy no reference text, photographs, logos, specific layout, component geometry, or artwork",
            (
                "no generated micro illustration was selected; do not fabricate one to satisfy a legacy four-item gate"
                if requested_micro_component_count == 0
                else f"generate the {requested_micro_component_count} selected distinct micro illustrations, verify final RGBA pixels and lineage, register them, and record native Ardot component evidence before article layout"
            ),
            (
                "author 2–3 semantic dynamic modules; a repeated card group counts as one module"
                if production_preferences.get("use_svg") is True
                else "author no SVG modules; keep the confirmed static-selected interaction plan"
            ),
            (
                "build every dynamic module as native editable closed, open, and information-equivalent fallback states from the current Ardot revision"
                if production_preferences.get("use_svg") is True
                else "skip dynamic state construction"
            ),
            (
                "place only the pixel-validated background-family master and companions on the declared surface mode, varying crop and opacity instead of style"
                if production_preferences.get("generate_backgrounds") is True
                else "use only continuous Ardot-native surfaces, gradients, and open vectors; do not create raster atmosphere backgrounds"
            ),
            "apply 2–4 approved expressive typography recipes with at least two non-font construction techniques and native editable text/accent layers; keep body copy standard and never bake Chinese display text into images",
            "apply or update the organization variable mode",
            "fetch reusable components by exact ardot_component name",
            "create missing semantic component variants before article assembly",
            "create one 390px article root and assemble approved storyboard chapters in narrative order",
            "give each chapter a bespoke composition; reuse primitives selectively instead of instantiating one box per block",
            (
                "skip micro-illustration placement because zero components were selected"
                if requested_micro_component_count == 0
                else "place micro illustrations between and beside open text flows; never use them as card backgrounds"
            ),
            (
                "micro-component copy policy is not applicable because zero components were selected"
                if requested_micro_component_count == 0
                else "never draw a closed frame, badge, chip, or filled rectangle around micro-component copy; emphasize primary copy with native scale contrast and one additional non-frame technique"
            ),
            (
                "skip micro-component placement evidence because zero components were selected"
                if requested_micro_component_count == 0
                else "keep every selected micro image at or below 72 percent of the 390 px row and every micro component at or below 82 percent; "
                + micro_staggering
            ),
            "export every actual visual-kit instance from the article root into the hashed inventory and node-property evidence; repeated roles are allowed but no instance may be omitted",
            "upload registered image assets to their named image slots",
            "use the already-watermarked registered derivative; never embed a watermark for the first time in Ardot or during WeChat compile",
            "append the exact workflow_attribution text once as the final native editable text component after all article and user-authored footer blocks; it is repository usage credit, not organization identity, and must not be renamed, hidden, rasterized, or moved earlier",
            "capture section screenshots and iterate before any WeChat handoff",
        ],
        "qa": {
            "ready_for_layout": (
                calibration["ready"]
                and provenance_watermark["ready"]
                and storyboard["ready_for_visual_kit"]
                and visual_kit_plan["ready_for_layout"]
                and typography["ready"]
                and interaction_plan["ready"]
                and not unresolved
                and not forbidden_background_assignments
            ),
            "blocking": [
                "organization or selected route lacks an approved Ardot calibration benchmark",
                "a selected generated background or generated cover lacks locally verified watermark evidence",
                "an article background assignment conflicts with generate_backgrounds or uses a non-background asset duty",
                "when generated backgrounds are selected, family pixels fail surface-mode unity, copy-zone variance, tonal continuity, or 4.5:1 body-text contrast",
                "article lacks an approved narrative storyboard with complete block coverage",
                "article-specific visual kit does not exactly match the confirmed selected role/count contract",
                "expressive typography is missing, font-swap-only, flattened, ungrounded, unlicensed, or lacks approved recipe/construction/node evidence",
                "interaction plan conflicts with the confirmed SVG/static choice, or a dynamic plan lacks grounded transport instances, valid chapter distribution, or current-revision state evidence",
                "layout started before micro illustrations became native Ardot components",
                "missing component variant",
                "unresolved asset",
                "clipped or overflowed text",
                "more than 20 percent of content sections use a closed box",
                "two boxed sections appear consecutively",
                "every semantic block has its own background, border, or rounded container",
                "micro illustration is rectangular, framed, generic, or used as a panel background",
                "micro-component copy is enclosed by a frame, chip, badge, filled rectangle, or enclosing shape node",
                "a selected micro image exceeds 72 percent of the row, a selected micro component exceeds 82 percent, or the count-scaled placement evidence is incomplete",
                "copy-bearing micro components lack native text nodes, at least 22 px primary type, 1.35x body scale contrast, or a second non-frame emphasis technique",
                "organization mode or organization_id mismatch",
                "terminal workflow attribution is missing, changed, hidden, rasterized, or not the final visible text",
            ],
            "layout_policy": {
                "maximum_boxed_section_ratio": 0.2,
                "maximum_consecutive_boxed_sections": 1,
                "requested_micro_component_count": requested_micro_component_count,
                "selected_micro_component_roles": selected_micro_roles,
                "minimum_micro_illustration_roles": requested_micro_component_count,
                "minimum_unique_generated_micro_assets": requested_micro_component_count,
                "minimum_asymmetric_or_edge_breaking_moments": 3,
                "maximum_micro_image_width_ratio": 0.72,
                "maximum_micro_component_width_ratio": 0.82,
                "minimum_micro_copy_font_px": 22,
                "minimum_micro_copy_scale_ratio": 1.35,
                "micro_copy_enclosure": "none",
                "minimum_micro_component_screenshot_sections": minimum_micro_screenshot_sections,
                "minimum_micro_composition_relations": minimum_micro_composition_relations,
                "default_container": "none",
                "expressive_typography_moments": "2-4 when strategy is expressive-native",
                "expressive_typography_recipe": "at least 2 non-font techniques and 2 editable construction layers",
                "use_svg": production_preferences.get("use_svg"),
                "dynamic_modules_per_article": (
                    "2-3 semantic modules"
                    if production_preferences.get("use_svg") is True
                    else "0; static-selected"
                ),
                "dynamic_group_counting": "one repeated-card group equals one semantic module",
                "dynamic_transport_default": "static fallback until target-account iOS/Android certification",
                "generate_backgrounds": production_preferences.get("generate_backgrounds"),
                "background_family_surface": (
                    "one light/dark mode with pixel-checked copy safety and contrast >= 4.5"
                    if production_preferences.get("generate_backgrounds") is True
                    else "not applicable; use Ardot-native surfaces with contrast >= 4.5"
                ),
                "body_copy_typography": "standard-readable",
            },
            "unresolved_assets": unresolved,
            "forbidden_generated_backgrounds": forbidden_background_assignments,
            "forbidden_background_assignments": forbidden_background_assignments,
            "background_assignment_errors": background_assignment_errors,
            "requires_visual_review": True,
        },
        "handoff": {
            "contract_schema_version": 5,
            "revision_algorithm": "ardot-root-revision-v1",
            "transport_revision_algorithm": "ardot-transport-revision-v1",
            "source_of_truth": "ardot-native",
            "wechat_adapter": "frozen-ardot-layer-transport",
            "publish_action": "draft-only",
            "required_transport_fidelity": {
                "source": "ardot-current-root-layer-export-v1",
                "article_width_px": 390,
                "background_export_scale": 3,
                "chapter_mapping": "one-to-one-continuous-article-root-y",
                "current_root_transport_sections": "exact",
                "current_root_body_asset_ids": "exact",
                "current_root_visible_component_coverage": "exact-once",
                "fresh_live_root_reread": "required-separate-host-capture",
                "fresh_live_root_receipt": "host-ed25519-signed-max-10-minutes",
                "native_text": "required",
                "native_font_and_render_style": "allowlisted-and-exact",
                "interaction_state_nodes": "closed-open-fallback-distinct-tree-sha256",
                "section_composites": "forbidden",
                "independent_cutout_decorations": "required",
                "compiled_html_artifact_binding": "signed-intended-path-device-inode-sha256-bytes-handoff-revision",
                "saved_draft_readback": "required",
                "saved_draft_readback_receipt": "host-ed25519-signed-complete-byte-chain",
            },
            "required_workflow_attribution": {
                "policy_id": WORKFLOW_ATTRIBUTION_MARKER,
                "classification": "repository-usage-credit",
                "text": WORKFLOW_ATTRIBUTION_TEXT,
                "text_sha256": f"sha256:{WORKFLOW_ATTRIBUTION_TEXT_SHA256}",
                "evidence": [
                    "ardot_node_id",
                    "component_name",
                    "node_kind",
                    "native_editable_text",
                    "visible",
                    "terminal",
                    "node_export_file",
                    "node_export_sha256",
                ],
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("article", type=Path)
    parser.add_argument("--org", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        article = existing_regular_file(args.article, label="article")
        organization = existing_directory(args.org, label="organization pack")
        output = new_file_path(
            args.output,
            label="Ardot manifest output",
            forbidden_root=RUNTIME_ROOT,
        )
        manifest = build_manifest(article, organization)
        write_text_create_once(
            output,
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            label="Ardot manifest output",
            forbidden_root=RUNTIME_ROOT,
        )
    except (SafePathError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({"created": str(output), "blocks": len(manifest["blocks"]), "ok": not manifest["qa"]["unresolved_assets"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

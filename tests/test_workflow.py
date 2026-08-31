from __future__ import annotations

import binascii
import base64
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from typing import Any
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from asset_quality import (  # noqa: E402
    MICRO_CUTOUT_EVIDENCE_FIELDS,
    file_sha256,
    validate_micro_asset,
)
from build_ardot_manifest import build_manifest  # noqa: E402
from build_storyboard import build_storyboard_plan  # noqa: E402
from build_visual_directions import build_directions  # noqa: E402
from build_visual_kit import build_visual_kit_plan  # noqa: E402
from compile_wechat import compile_article  # noqa: E402
from orgs import (  # noqa: E402
    build_asset_plan,
    command_init,
    command_register_asset,
    scaffold,
    validate_pack,
    write_json,
)
from provenance_watermark import embed_watermark, measure_psnr  # noqa: E402
from workflow_quality import (  # noqa: E402
    WORKFLOW_ATTRIBUTION_MARKER,
    WORKFLOW_ATTRIBUTION_TEXT,
    WORKFLOW_ATTRIBUTION_TEXT_SHA256,
    WATERMARK_SCHEME,
    asset_watermark_requirement,
    interaction_semantic_hash,
    style_grammar_errors,
    style_grammar_sha256,
    validate_interaction_plan,
    watermark_evidence_from_report,
    watermark_inventory,
)


ROLES = (
    ("floating-spot", "spot.opening", 256, 256, "anchor", "opening", "第一步从一个真实问题开始。"),
    ("section-transition", "visual.transition", 512, 128, "connector", "identity", "不同能力沿同一条路径汇合。"),
    ("inline-explainer", "visual.explainer", 320, 240, "motion", "evidence", "原型在四个动作之间逐步完成。"),
    ("closing-motif", "spot.closing", 256, 256, "punctuation", "join", "把已经完成的原型交给下一位伙伴。"),
)

TEST_WATERMARK_KEY = b"workflow-test-watermark-key-material-v1"
TEST_WATERMARK_ENV = "base64:" + base64.b64encode(TEST_WATERMARK_KEY).decode("ascii")


def write_png(
    path: Path,
    width: int,
    height: int,
    *,
    alpha: bool = True,
    color: tuple[int, int, int] = (30, 100, 180),
    alpha_shape: str = "organic",
    pattern_strength: int = 0,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    color_type = 6 if alpha else 2
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            delta = 0
            if pattern_strength:
                span = pattern_strength * 2 + 1
                delta = (
                    ((x // 4) * 17 + (y // 4) * 31 + (x // 13) * 11 + (y // 17) * 7)
                    % span
                ) - pattern_strength
            row.extend(max(0, min(255, channel + delta)) for channel in color)
            if alpha:
                if alpha_shape == "rectangular":
                    border = min(x, y, width - 1 - x, height - 1 - y)
                    row.append(0 if border < 8 else 255)
                else:
                    horizontal = (x - (width - 1) / 2) / max(1, width * 0.46)
                    vertical = (y - (height - 1) / 2) / max(1, height * 0.46)
                    row.append(255 if horizontal * horizontal + vertical * vertical <= 1 else 0)
        rows.append(b"\x00" + bytes(row))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = binascii.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + chunk(b"IEND", b"")
    )


def make_pack(root: Path) -> Path:
    pack = root / "fresh-organization"
    pack.mkdir(parents=True)
    documents = scaffold("fresh-organization", "全新组织")
    organization = documents["organization.json"]
    organization["status"] = "confirmed"
    organization["identity"].update(
        {
            "summary": "基于本轮原始材料建立的组织模型",
            "category": "community",
            "audiences": ["current audience"],
            "content_pillars": ["projects"],
        }
    )
    organization["voice"]["traits"] = ["direct"]
    organization["visual"]["routes"].append(
        {
            "id": "field-notes",
            "label": "行动记录",
            "uses": ["introduction"],
            "layout": "editorial",
            "dominant_style": "material-led-field-notes",
            "component_variants": {},
            "rationale": "由当前组织物件与动作证据推导",
        }
    )
    organization["visual"]["default_route"] = "field-notes"
    organization["article_types"]["introduction"]["route"] = "field-notes"
    organization["visual"]["calibration"] = {
        "status": "approved",
        "approved_routes": ["field-notes"],
        "benchmark": {
            "file_url": "https://ardot.example/fresh",
            "page_name": "Calibration / Fresh",
            "article_node_id": "10:1",
        },
        "density_mode": "compact-editorial",
        "background_family": {
            "id": "fresh-action-family",
            "strategy": "generated-family",
            "master_asset_id": "background.master",
            "companion_asset_ids": ["background.companion"],
            "surface_mode": "dark",
            "copy_safe_zone": {"x": 0.12, "y": 0.16, "width": 0.76, "height": 0.58},
            "body_text_color": "#FFFFFF",
            "minimum_contrast_ratio": 4.5,
            "maximum_copy_safe_stddev": 0.10,
        },
        "typography": {
            "strategy": "expressive-native",
            "editable_text_required": True,
            "font_policy": "licensed-or-system-only",
            "body_copy_remains_standard": True,
            "approved_treatments": ["stacked-title", "mixed-weight", "stroke-offset"],
            "approved_recipes": [
                {
                    "id": "hero-stack",
                    "treatment": "stacked-title",
                    "techniques": ["intentional-line-break", "scale-contrast", "vector-accent"],
                    "minimum_editable_layers": 3,
                    "fallback_text_style": "Display/Hero/Fallback",
                },
                {
                    "id": "chapter-mix",
                    "treatment": "mixed-weight",
                    "techniques": ["mixed-weight", "color-contrast"],
                    "minimum_editable_layers": 2,
                    "fallback_text_style": "Display/Chapter/Fallback",
                },
            ],
            "maximum_moments_per_article": 4,
        },
        "reviewed_at": "2026-08-27T09:00:00+08:00",
        "review_basis": ["source.current-materials"],
    }
    organization["provenance"] = {
        "source_ids": ["source.current-materials"],
        "reviewed_at": "2026-08-27",
        "notes": "Only current raw materials were used.",
        "visual_reference_policy": "source-zero",
        "visual_input_source_ids": ["source.current-materials"],
        "excluded_visual_reference_kinds": [
            "prior-article-layout",
            "prior-ardot-file",
            "prior-article-screenshot",
            "other-organization-visual-pack",
        ],
        "isolation_reviewed_at": "2026-08-27T09:00:00+08:00",
    }
    documents["sources.json"] = {
        "schema_version": 1,
        "organization_id": "fresh-organization",
        "sources": [
            {
                "id": "source.current-materials",
                "title": "Current raw materials",
                "kind": "user-supplied",
                "locator": "current-input/",
            }
        ],
        "facts": [],
    }
    documents["ardot.json"].update(
        {
            "status": "linked",
            "design_file": {"url": "https://ardot.example/fresh", "file_id": "fresh"},
            "variable_mode": "Fresh",
        }
    )
    generated = pack / "assets" / "generated"
    write_png(generated / "background-master.png", 390, 780, alpha=False)
    write_png(generated / "background-companion.png", 390, 780, alpha=False)
    assets = [
        {
            "id": "background.master",
            "kind": "background",
            "title": "Master background",
            "location": "assets/generated/background-master.png",
            "style": "fresh-action",
            "uses": ["introduction"],
            "origin": "generated-illustrative",
            "visual_role": "illustrative-atmosphere",
            "background_family_id": "fresh-action-family",
            "background_variant": "master",
        },
        {
            "id": "background.companion",
            "kind": "background",
            "title": "Companion background",
            "location": "assets/generated/background-companion.png",
            "style": "fresh-action",
            "uses": ["introduction"],
            "origin": "generated-illustrative",
            "visual_role": "illustrative-atmosphere",
            "background_family_id": "fresh-action-family",
            "background_variant": "companion",
        },
    ]
    for role, asset_id, width, height, *_ in ROLES:
        filename = asset_id.replace(".", "-") + ".png"
        asset_path = generated / filename
        # A synthetic micro fixture must contain real subject variation; a flat
        # colored ellipse is deliberately rejected as a matte/backplate.
        write_png(asset_path, width, height, pattern_strength=22)
        quality = validate_micro_asset(asset_path, role)
        assert quality["ok"], quality
        inspection = quality["inspection"]
        assets.append(
            {
                "id": asset_id,
                "kind": "illustration",
                "title": role,
                "location": f"assets/generated/{filename}",
                "style": "article-specific",
                "uses": ["introduction"],
                "origin": "generated-illustrative",
                "visual_role": "article-micro",
                "roles": [role],
                "generated_for_articles": ["fresh-article"],
                "quality": {
                    "alpha_verified": True,
                    "cutout_verified": True,
                    "sha256": inspection["sha256"],
                    "width_px": width,
                    "height_px": height,
                    "transparent_pixel_ratio": inspection["transparent_pixel_ratio"],
                    "cutout_evidence": {
                        key: inspection[key] for key in MICRO_CUTOUT_EVIDENCE_FIELDS
                    },
                },
            }
        )
    documents["assets.json"] = {
        "schema_version": 1,
        "organization_id": "fresh-organization",
        "assets": assets,
    }
    for filename, document in documents.items():
        write_json(pack / filename, document)
    return pack


def enable_required_watermark(pack: Path) -> dict[str, dict[str, Any]]:
    """Replace fixture backgrounds with marked derivatives and public evidence."""
    organization = json.loads((pack / "organization.json").read_text(encoding="utf-8"))
    organization["provenance"]["generated_image_watermark"] = {
        "mode": "required",
        "scheme": WATERMARK_SCHEME,
        "key_id": "test-external-key",
    }
    write_json(pack / "organization.json", organization)

    assets_doc = json.loads((pack / "assets.json").read_text(encoding="utf-8"))
    reports: dict[str, dict[str, Any]] = {}
    report_dir = pack / "assets" / "generated" / "watermark-reports"
    source_dir = pack / "assets" / "generated" / "unwatermarked-masters"
    report_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    background_index = 0
    for asset in assets_doc["assets"]:
        if asset.get("id") not in {"background.master", "background.companion"}:
            continue
        background_index += 1
        stem = str(asset["id"]).replace(".", "-")
        source_path = source_dir / f"{stem}.png"
        marked_path = pack / asset["location"]
        base_color = (32 + background_index * 2, 94, 158 + background_index * 2)
        write_png(
            source_path,
            390,
            780,
            alpha=False,
            color=base_color,
            pattern_strength=22,
        )
        if marked_path.is_file():
            marked_path.unlink()
        report = embed_watermark(
            source_path,
            marked_path,
            key=TEST_WATERMARK_KEY,
            key_epoch=7,
            wm_id=f"{background_index:016x}",
        )
        report_path = report_dir / f"{stem}.json"
        write_json(report_path, report)
        with mock.patch.dict(
            os.environ,
            {"PROVENANCE_WATERMARK_KEY": TEST_WATERMARK_ENV},
        ):
            asset["watermark"] = watermark_evidence_from_report(
                report,
                report_path,
                marked_path,
                pack_dir=pack,
                source_path=source_path,
                key_id="test-external-key",
            )
        reports[str(asset["id"])] = report
    write_json(pack / "assets.json", assets_doc)
    return reports


def enable_explicit_style_reference(pack: Path) -> dict[str, object]:
    sources = json.loads((pack / "sources.json").read_text(encoding="utf-8"))
    sources["sources"].append(
        {
            "id": "source.style-reference",
            "title": "User-authorized visual style reference",
            "kind": "visual-style-reference",
            "locator": "https://example.test/style-reference",
        }
    )
    write_json(pack / "sources.json", sources)

    organization = json.loads((pack / "organization.json").read_text(encoding="utf-8"))
    organization["provenance"].update(
        {
            "source_ids": ["source.current-materials", "source.style-reference"],
            "visual_reference_policy": "explicit-style-grammar",
            "style_reference_source_ids": ["source.style-reference"],
            "style_reference_scope": "abstract-visual-grammar-only",
            "reference_reviewed_at": "2026-08-29T12:00:00+08:00",
            "style_reference_non_copy_constraints": [
                "text",
                "photographs",
                "logos",
                "specific-layout",
                "component-geometry",
                "artwork",
            ],
        }
    )
    selected_grammar: dict[str, object] | None = None
    for route in organization["visual"]["routes"]:
        if route["id"] != "field-notes":
            continue
        preset = json.loads(
            (ROOT / "style-presets" / "prismatic-paper-editorial.json").read_text(
                encoding="utf-8"
            )
        )
        grammar = json.loads(json.dumps(preset["grammar"], ensure_ascii=False))
        route["style_grammar"] = grammar
        selected_grammar = grammar
    write_json(pack / "organization.json", organization)
    assert selected_grammar is not None
    return selected_grammar


def make_article(root: Path, pack: Path) -> Path:
    mode = json.loads((pack / "ardot.json").read_text(encoding="utf-8"))["variable_mode"]
    registered_assets = {
        item["id"]: item
        for item in json.loads((pack / "assets.json").read_text(encoding="utf-8"))["assets"]
    }
    blocks = [
        {"type": "hero", "title": "第一步从一个真实问题开始。", "background": "background.master", "background_alt": "连续氛围底图"},
        {"type": "lead", "paragraphs": ["不同能力沿同一条路径汇合。"]},
        {"type": "text", "paragraphs": ["原型在四个动作之间逐步完成。"]},
        {"type": "cta", "title": "把已经完成的原型交给下一位伙伴。"},
    ]
    chapter_ids = ["opening", "identity", "evidence", "join"]
    chapters = [
        {
            "id": chapter_id,
            "label": f"Chapter {index + 1}",
            "thesis": blocks[index].get("title", blocks[index].get("paragraphs", [""])[0]),
            "composition": f"composition-{index + 1}",
            "visual_intent": f"current-material visual action {index + 1}",
            "density_intent": "compact-editorial with no accidental empty region",
            "block_indices": [index],
        }
        for index, chapter_id in enumerate(chapter_ids)
    ]
    visual_assets = []
    for role, asset_id, _, _, composition, chapter_id, source_text in ROLES:
        component_name = "WeChat/Ornament/" + "".join(part.title() for part in role.split("-")) + f"/{mode}"
        visual_assets.append(
            {
                "id": asset_id,
                "asset_sha256": registered_assets[asset_id]["quality"]["sha256"],
                "role": role,
                "storyboard_chapter": chapter_id,
                "source_text": source_text,
                "concrete_subject": f"{chapter_id} project prototype",
                "action": "moves along the current reading path",
                "composition_role": composition,
                "placement": f"{chapter_id} text edge",
                "ardot_component": {
                    "file_url": "https://ardot.example/fresh",
                    "node_id": f"20:{len(visual_assets) + 1}",
                    "name": component_name,
                },
            }
        )
    interaction_specs = [
        {
            "id": "capability-reveal",
            "pattern": "tap-reveal-group",
            "candidate_modes": ["svg-smil-self", "horizontal-swipe"],
            "storyboard_chapter": "identity",
            "placement_band": "early",
            "purpose": "让读者按需展开能力之间的关系",
            "source_block_indices": [1],
            "instances": [
                {
                    "id": "capability-path",
                    "source_texts": ["不同能力沿同一条路径汇合。"],
                    "fallback_key": "capability-path",
                }
            ],
        },
        {
            "id": "prototype-process",
            "pattern": "process-reveal",
            "candidate_modes": ["svg-smil-self"],
            "storyboard_chapter": "evidence",
            "placement_band": "middle",
            "purpose": "把原型完成过程拆成可逐步读取的信息",
            "source_block_indices": [2],
            "instances": [
                {
                    "id": "prototype-steps",
                    "source_texts": ["原型在四个动作之间逐步完成。"],
                    "fallback_key": "prototype-steps",
                }
            ],
        },
    ]
    interaction_modules = []
    state_names = ("closed", "open", "fallback")
    for module_index, spec in enumerate(interaction_specs, 1):
        states = {}
        for state_index, state_name in enumerate(state_names, 1):
            screenshot = root / "qa" / f"interaction-{module_index}-{state_name}.png"
            write_png(
                screenshot,
                390,
                240 + module_index,
                alpha=False,
                color=(30 + module_index * 35, 60 + state_index * 30, 100 + state_index * 25),
            )
            states[state_name] = {
                "node_id": f"50:{module_index * 10 + state_index}",
                "screenshot": f"qa/{screenshot.name}",
                "sha256": file_sha256(screenshot),
            }
        instances = [
            {
                **instance,
                "semantic_hash": interaction_semantic_hash(instance["source_texts"]),
            }
            for instance in spec["instances"]
        ]
        interaction_modules.append(
            {
                **spec,
                "instances": instances,
                "ardot_component": {
                    "file_url": "https://ardot.example/fresh",
                    "name": f"WeChat/Interaction/{spec['id']}/Fresh",
                    "revision_hash": "a" * 64,
                    "covered_instance_ids": [item["id"] for item in instances],
                    "covered_semantic_hashes": [item["semantic_hash"] for item in instances],
                    "states": states,
                },
            }
        )
    article = {
        "schema_version": 1,
        "article_id": "fresh-article",
        "organization_id": "fresh-organization",
        "article_type": "introduction",
        "title": "Fresh article",
        "storyboard": {"status": "approved", "chapters": chapters},
        "visual_kit": {"status": "approved", "assets": visual_assets},
        "interaction_plan": {
            "status": "approved",
            "authoring_mode": "dynamic-default",
            "target_module_count": 2,
            "article_root_node_id": "30:0",
            "ardot_revision_hash": "a" * 64,
            "modules": interaction_modules,
        },
        "typography": {
            "status": "approved",
            "moments": [
                {
                    "role": "hero-title",
                    "storyboard_chapter": "opening",
                    "source_text": "第一步从一个真实问题开始。",
                    "treatment": "stacked-title",
                    "recipe_id": "hero-stack",
                    "construction": {
                        "techniques": ["intentional-line-break", "scale-contrast", "vector-accent"],
                        "native_text_node_ids": ["41:1", "41:1a"],
                        "accent_node_ids": ["42:1"],
                        "line_count": 2,
                        "scale_ratio": 1.3,
                    },
                    "editable_text": True,
                    "font_source": "licensed-or-system",
                    "fallback_text_style": "Display/Hero/Fallback",
                    "ardot_text_style": {
                        "file_url": "https://ardot.example/fresh",
                        "node_id": "41:1",
                        "style_id": "40:1",
                        "name": "Type/Display/Stacked/Fresh",
                    },
                },
                {
                    "role": "chapter-title",
                    "storyboard_chapter": "identity",
                    "source_text": "不同能力沿同一条路径汇合。",
                    "treatment": "mixed-weight",
                    "recipe_id": "chapter-mix",
                    "construction": {
                        "techniques": ["mixed-weight", "color-contrast"],
                        "native_text_node_ids": ["41:2", "41:2a"],
                        "accent_node_ids": [],
                        "line_count": 1,
                    },
                    "editable_text": True,
                    "font_source": "licensed-or-system",
                    "fallback_text_style": "Display/Chapter/Fallback",
                    "ardot_text_style": {
                        "file_url": "https://ardot.example/fresh",
                        "node_id": "41:2",
                        "style_id": "40:2",
                        "name": "Type/Display/MixedWeight/Fresh",
                    },
                },
            ],
        },
        "blocks": blocks,
    }
    article_path = root / "article.json"
    write_json(article_path, article)
    return article_path


def add_visual_review(article_path: Path) -> Path:
    article = json.loads(article_path.read_text(encoding="utf-8"))
    qa = article_path.parent / "qa"
    asset_document = json.loads(
        (article_path.parent / article["organization_id"] / "assets.json").read_text(
            encoding="utf-8"
        )
    )
    registered_assets = {
        item["id"]: item for item in asset_document["assets"] if isinstance(item, dict)
    }
    screenshots = []
    density_samples = []
    roles = ("hero", "chapter", "evidence", "complex-section", "cta")
    chapters = ("opening", "identity", "evidence", "evidence", "join")
    for index, (role, chapter_id) in enumerate(zip(roles, chapters), 1):
        image_path = qa / f"{role}.png"
        height = 600 + index
        write_png(image_path, 390, height)
        digest = file_sha256(image_path)
        node_id = f"30:{index}"
        screenshots.append(
            {
                "role": role,
                "chapter_id": chapter_id,
                "node_id": node_id,
                "location": f"qa/{role}.png",
                "sha256": digest,
                "width_px": 390,
                "height_px": height,
            }
        )
        density_samples.append(
            {
                "node_id": node_id,
                "chapter_id": chapter_id,
                "screenshot_sha256": digest,
                "body_font_px": 16,
                "body_line_height_ratio": 1.54,
                "letter_spacing_px": -0.1,
                "paragraph_gap_px": 10,
                "major_gap_px": 32,
                "content_occupancy_ratio": 0.78,
                "largest_empty_region_ratio": 0.14,
                "body_text_contrast_ratio": 7.0,
            }
        )
    visual_component_by_role = {
        item["role"]: item["ardot_component"]["node_id"]
        for item in article["visual_kit"]["assets"]
    }
    placement_specs = [
        ("opening-floating-spot", "floating-spot", 0, 0.36, -0.22, 0.28, "text-edge-entry", 24, "mixed-weight"),
        ("identity-section-transition", "section-transition", 1, 0.68, 0.16, 0.60, "chapter-bridge", None, None),
        ("evidence-inline-explainer", "inline-explainer", 2, 0.48, -0.11, 0.38, "between-paragraphs", 23, "color-contrast"),
        ("join-closing-motif", "closing-motif", 4, 0.42, 0.24, 0.32, "cta-anchor", None, None),
    ]
    micro_placements = []
    inventory_instances = []
    for placement_index, (
        placement_id,
        role,
        screenshot_index,
        component_width_ratio,
        horizontal_offset_ratio,
        image_width_ratio,
        relation,
        primary_font_px,
        secondary_technique,
    ) in enumerate(placement_specs, 1):
        source_component_node_id = visual_component_by_role[role]
        instance_node_id = f"80:{placement_index}"
        component_width = component_width_ratio * 390
        component_center_x = (0.5 + horizontal_offset_ratio) * 390
        component_x = component_center_x - component_width / 2
        image_width = image_width_ratio * 390
        nodes = [
            {
                "node_id": f"{instance_node_id}:image",
                "kind": "illustration",
                "asset_id": next(
                    item["id"] for item in article["visual_kit"]["assets"] if item["role"] == role
                ),
                "asset_sha256": next(
                    item["asset_sha256"]
                    for item in article["visual_kit"]["assets"]
                    if item["role"] == role
                ),
                "bounds": {"x": component_x, "y": 80, "width": image_width, "height": 96},
            }
        ]
        image_node = nodes[0]
        approved_asset = registered_assets[image_node["asset_id"]]
        source_asset = (
            article_path.parent / article["organization_id"] / approved_asset["location"]
        )
        rendered_asset = qa / f"micro-{placement_index}-rendered.png"
        shutil.copyfile(source_asset, rendered_asset)
        image_node["rendered_asset_file"] = rendered_asset.name
        image_node["rendered_asset_sha256"] = file_sha256(rendered_asset)
        if primary_font_px is not None:
            nodes.extend(
                [
                    {
                        "node_id": f"70:{placement_index}",
                        "kind": "text",
                        "role": "primary-copy",
                        "font_size_px": primary_font_px,
                        "emphasis_techniques": ["scale-contrast", secondary_technique],
                        "bounds": {"x": component_x + 18, "y": 188, "width": 112, "height": 34},
                    },
                    {
                        "node_id": f"72:{placement_index}",
                        "kind": "vector-accent",
                        "is_closed": False,
                        "bounds": {"x": component_x + 4, "y": 182, "width": 8, "height": 44},
                    },
                ]
            )
        properties = {
            "schema_version": 1,
            "source": "ardot-node-properties",
            "article_root_node_id": "30:0",
            "article_width_px": 390,
            "instance": {
                "node_id": instance_node_id,
                "source_component_node_id": source_component_node_id,
                "bounds": {"x": component_x, "y": 72, "width": component_width, "height": 168},
            },
            "complete_descendant_census": True,
            "visible_descendant_count": len(nodes),
            "nodes": nodes,
        }
        properties_path = qa / f"micro-{placement_index}-nodes.json"
        write_json(properties_path, properties)
        micro_placements.append(
            {
                "id": placement_id,
                "role": role,
                "source_component_node_id": source_component_node_id,
                "instance_node_id": instance_node_id,
                "screenshot_node_id": screenshots[screenshot_index]["node_id"],
                "screenshot_sha256": screenshots[screenshot_index]["sha256"],
                "node_properties_file": f"qa/{properties_path.name}",
                "node_properties_sha256": file_sha256(properties_path),
                "composition_relation": relation,
            }
        )
        inventory_instances.append(
            {
                "instance_node_id": instance_node_id,
                "source_component_node_id": source_component_node_id,
            }
        )
    inventory_path = qa / "micro-component-inventory.json"
    write_json(
        inventory_path,
        {
            "schema_version": 1,
            "source": "ardot-article-instance-inventory",
            "article_root_node_id": "30:0",
            "article_width_px": 390,
            "instances": inventory_instances,
        },
    )
    review = {
        "schema_version": 3,
        "article_id": article["article_id"],
        "organization_id": article["organization_id"],
        "ardot": {"file_url": "https://ardot.example/fresh", "page_id": "0:1", "article_node_id": "30:0"},
        "capture": {
            "source": "ardot-node-export",
            "captured_at": "2026-08-27T10:00:00+08:00",
            "article_root_node_id": "30:0",
            "revision_hash": article["interaction_plan"].get("ardot_revision_hash", "0" * 64),
        },
        "screenshots": screenshots,
        "micro_component_layout": {
            "measured_from": "ardot-node-properties-and-screenshot",
            "measured_at": "2026-08-27T10:04:00+08:00",
            "inventory_file": "qa/micro-component-inventory.json",
            "inventory_sha256": file_sha256(inventory_path),
            "placements": micro_placements,
        },
        "density": {
            "mode": "compact-editorial",
            "measured_from": "ardot-node-properties-and-screenshot",
            "measured_at": "2026-08-27T10:05:00+08:00",
            "samples": density_samples,
        },
        "checks": {
            name: "pass"
            for name in (
                "subject_relevance", "style_coherence", "no_clipped_ornaments", "scale_variation",
                "photo_illustration_harmony", "no_generic_ai_decoration", "no_unexplained_labels",
                "editorial_rhythm", "mobile_legibility", "open_composition", "information_density",
                "background_family_coherence",
                "expressive_typography", "no_baked_art_text",
                "art_type_construction", "background_surface_unity", "reading_surface_contrast",
                "no_framed_micro_copy", "no_full_width_micro_image",
                "staggered_micro_composition", "micro_copy_hierarchy",
            )
        },
        "status": "approved",
        "reviewed_at": "2026-08-27T10:10:00+08:00",
    }
    review_path = article_path.parent / "visual-review.json"
    write_json(review_path, review)
    article["visual_review_file"] = "visual-review.json"
    write_json(article_path, article)
    return review_path


class FreshWorkflowTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pack = make_pack(self.root)
        self.article = make_article(self.root, self.pack)

    def tearDown(self) -> None:
        self.temp.cleanup()


class OrganizationPackTests(FreshWorkflowTestCase):
    def test_fresh_pack_validates_without_bundled_examples(self) -> None:
        report = validate_pack(self.pack)
        self.assertTrue(report["ok"], report["errors"])

    def test_scaffold_starts_source_zero_but_remains_blocked(self) -> None:
        pack = self.root / "new-org"
        pack.mkdir()
        documents = scaffold("new-org", "新组织")
        for filename, value in documents.items():
            write_json(pack / filename, value)
        self.assertEqual(
            documents["organization.json"]["provenance"]["generated_image_watermark"],
            {
                "mode": "required",
                "scheme": WATERMARK_SCHEME,
                "key_id": "external",
            },
        )
        directions = build_directions(pack, "introduction")
        self.assertFalse(directions["full_article_allowed"])
        self.assertEqual(directions["source_isolation"]["policy"], "source-zero")
        self.assertTrue(any("visual_input_source_ids" in item for item in directions["blocking_reasons"]))

    def test_explicit_style_grammar_pack_validates(self) -> None:
        grammar = enable_explicit_style_reference(self.pack)
        report = validate_pack(self.pack)
        self.assertTrue(report["ok"], report["errors"])
        directions = build_directions(self.pack, "introduction")
        self.assertTrue(directions["full_article_allowed"], directions["blocking_reasons"])
        self.assertEqual(
            directions["source_isolation"]["policy"],
            "explicit-style-grammar",
        )
        selected = next(item for item in directions["directions"] if item["route_id"] == "field-notes")
        baseline = next(
            item for item in directions["directions"] if item["route_id"] == "provisional-editorial"
        )
        self.assertEqual(selected["style_grammar_sha256"], grammar["sha256"])
        self.assertEqual(selected["style_preset_id"], "prismatic-paper-editorial")
        self.assertEqual(selected["style_preset_label"], "绚烂纸本")
        self.assertEqual(selected["style_reference_policy"], "explicit-style-grammar")
        self.assertEqual(baseline["style_reference_policy"], "source-zero")
        self.assertIsNone(baseline["style_grammar"])

    def test_style_preset_metadata_does_not_change_approved_grammar_hash(self) -> None:
        grammar = enable_explicit_style_reference(self.pack)
        original_hash = grammar["sha256"]
        renamed = dict(grammar)
        renamed["preset_id"] = "another-reviewed-preset-name"
        renamed["label"] = "另一个展示名"
        self.assertEqual(style_grammar_sha256(renamed), original_hash)

    def test_prismatic_paper_preset_is_selectable_not_default_and_hash_valid(self) -> None:
        preset_path = ROOT / "style-presets" / "prismatic-paper-editorial.json"
        preset = json.loads(preset_path.read_text(encoding="utf-8"))
        grammar = preset["grammar"]
        self.assertEqual(preset["preset_id"], "prismatic-paper-editorial")
        self.assertEqual(preset["label"], "绚烂纸本")
        self.assertTrue(preset["selectable"])
        self.assertFalse(preset["default"])
        self.assertEqual(preset["selection_scope"], "visual-route-only")
        self.assertEqual(style_grammar_errors(grammar, "preset.grammar"), [])
        self.assertEqual(grammar["sha256"], style_grammar_sha256(grammar))
        self.assertFalse(
            preset["provenance_requirements"][
                "reopen_original_reference_for_future_organizations"
            ]
        )

    def test_explicit_style_grammar_rejects_incomplete_provenance(self) -> None:
        enable_explicit_style_reference(self.pack)
        organization = json.loads((self.pack / "organization.json").read_text(encoding="utf-8"))
        organization["provenance"]["style_reference_source_ids"] = ["source.unknown"]
        organization["provenance"].pop("style_reference_scope")
        organization["provenance"]["reference_reviewed_at"] = "not-a-date"
        organization["provenance"]["style_reference_non_copy_constraints"].remove("artwork")
        write_json(self.pack / "organization.json", organization)
        report = validate_pack(self.pack)
        self.assertFalse(report["ok"])
        self.assertTrue(any("unknown source" in item for item in report["errors"]))
        self.assertTrue(any("style_reference_scope" in item for item in report["errors"]))
        self.assertTrue(any("reference_reviewed_at" in item for item in report["errors"]))
        self.assertTrue(any("artwork" in item for item in report["errors"]))

    def test_explicit_style_grammar_rejects_tamper_and_reference_fields(self) -> None:
        enable_explicit_style_reference(self.pack)
        organization = json.loads((self.pack / "organization.json").read_text(encoding="utf-8"))
        grammar = next(
            route["style_grammar"]
            for route in organization["visual"]["routes"]
            if "style_grammar" in route
        )
        grammar["tokens"]["reference_text"] = "copied headline"
        grammar["reference_artwork"] = "copied image payload"
        grammar["sha256"] = "0" * 64
        write_json(self.pack / "organization.json", organization)
        report = validate_pack(self.pack)
        self.assertFalse(report["ok"])
        self.assertTrue(
            any("reference-shaped fields" in item for item in report["errors"]),
            report["errors"],
        )
        self.assertTrue(any("reference-content fields" in item for item in report["errors"]))
        self.assertTrue(any("canonical grammar payload" in item for item in report["errors"]))

    def test_explicit_preset_rejects_self_rehashed_material_change(self) -> None:
        enable_explicit_style_reference(self.pack)
        organization = json.loads((self.pack / "organization.json").read_text(encoding="utf-8"))
        grammar = next(
            route["style_grammar"]
            for route in organization["visual"]["routes"]
            if "style_grammar" in route
        )
        grammar["tokens"]["material"] = "polished black glass and chrome"
        grammar["sha256"] = style_grammar_sha256(grammar)
        write_json(self.pack / "organization.json", organization)
        report = validate_pack(self.pack)
        self.assertFalse(report["ok"])
        self.assertTrue(
            any("does not match canonical preset" in item for item in report["errors"]),
            report["errors"],
        )

    def test_explicit_preset_rejects_unknown_preset_id(self) -> None:
        enable_explicit_style_reference(self.pack)
        organization = json.loads((self.pack / "organization.json").read_text(encoding="utf-8"))
        grammar = next(
            route["style_grammar"]
            for route in organization["visual"]["routes"]
            if "style_grammar" in route
        )
        grammar["preset_id"] = "unknown-reviewed-preset"
        write_json(self.pack / "organization.json", organization)
        report = validate_pack(self.pack)
        self.assertFalse(report["ok"])
        self.assertTrue(any("unknown style preset" in item for item in report["errors"]))

    def test_explicit_style_grammar_rejects_copy_instruction_and_url(self) -> None:
        enable_explicit_style_reference(self.pack)
        organization = json.loads((self.pack / "organization.json").read_text(encoding="utf-8"))
        grammar = next(
            route["style_grammar"]
            for route in organization["visual"]["routes"]
            if "style_grammar" in route
        )
        grammar["tokens"]["material"] = (
            "Copy exact headline 求是潮 and exact cover geometry"
        )
        grammar["tokens"]["lighting"] = "sample https://example.test/reference.png"
        grammar["sha256"] = style_grammar_sha256(grammar)
        write_json(self.pack / "organization.json", organization)
        report = validate_pack(self.pack)
        self.assertFalse(report["ok"])
        self.assertTrue(
            any("explicit reference-copy instruction" in item for item in report["errors"]),
            report["errors"],
        )
        self.assertTrue(any("must not contain a URL" in item for item in report["errors"]))

    def test_init_creates_isolated_asset_directories(self) -> None:
        args = type("Args", (), {"organization_id": "new-org", "name": "新组织", "root": self.root})()
        command_init(args)
        for folder in ("official", "photos", "generated", "derived"):
            self.assertTrue((self.root / "new-org" / "assets" / folder).is_dir())

    def test_generated_background_family_is_mandatory(self) -> None:
        organization = json.loads((self.pack / "organization.json").read_text(encoding="utf-8"))
        organization["visual"]["calibration"]["background_family"] = None
        write_json(self.pack / "organization.json", organization)
        report = validate_pack(self.pack)
        self.assertFalse(report["ok"])
        self.assertTrue(any("background_family" in item for item in report["errors"]))

    def test_background_family_rejects_black_white_surface_jump(self) -> None:
        companion = self.pack / "assets" / "generated" / "background-companion.png"
        write_png(companion, 390, 780, alpha=False, color=(250, 250, 250))
        report = validate_pack(self.pack)
        self.assertFalse(report["ok"])
        self.assertTrue(
            any("surface mode" in item or "luminance span" in item for item in report["errors"]),
            report["errors"],
        )

    def test_background_family_rejects_low_contrast_copy_surface(self) -> None:
        organization = json.loads((self.pack / "organization.json").read_text(encoding="utf-8"))
        organization["visual"]["calibration"]["background_family"]["body_text_color"] = "#1E64B4"
        write_json(self.pack / "organization.json", organization)
        report = validate_pack(self.pack)
        self.assertFalse(report["ok"])
        self.assertTrue(any("contrast" in item for item in report["errors"]), report["errors"])

    def test_background_family_requires_final_opaque_pixels(self) -> None:
        companion = self.pack / "assets" / "generated" / "background-companion.png"
        write_png(companion, 390, 780, alpha=True)
        report = validate_pack(self.pack)
        self.assertFalse(report["ok"])
        self.assertTrue(any("final opaque PNG" in item for item in report["errors"]), report["errors"])

    def test_typography_calibration_is_mandatory(self) -> None:
        organization = json.loads((self.pack / "organization.json").read_text(encoding="utf-8"))
        organization["visual"]["calibration"].pop("typography")
        write_json(self.pack / "organization.json", organization)
        report = validate_pack(self.pack)
        self.assertFalse(report["ok"])
        self.assertTrue(any("typography" in item for item in report["errors"]))

    def test_opaque_micro_asset_fails_pixel_alpha_check(self) -> None:
        opaque = self.pack / "assets" / "generated" / "opaque.png"
        write_png(opaque, 256, 256, alpha=False)
        report = validate_micro_asset(opaque, "floating-spot")
        self.assertFalse(report["ok"])
        self.assertTrue(any("alpha" in item.lower() for item in report["errors"]))

    def test_rectangular_alpha_tile_is_rejected_as_a_micro_asset(self) -> None:
        tiled = self.pack / "assets" / "generated" / "rectangular-tile.png"
        write_png(tiled, 256, 256, alpha=True, alpha_shape="rectangular")
        report = validate_micro_asset(tiled, "floating-spot")
        self.assertFalse(report["ok"])
        self.assertIn("micro.asset.rectangular_alpha_tile", report["error_codes"])


class WatermarkWorkflowTests(FreshWorkflowTestCase):
    def _declare_optional_policy(self) -> None:
        organization = json.loads(
            (self.pack / "organization.json").read_text(encoding="utf-8")
        )
        organization["provenance"]["generated_image_watermark"] = {
            "mode": "optional",
            "scheme": WATERMARK_SCHEME,
            "key_id": "test-external-key",
        }
        write_json(self.pack / "organization.json", organization)

    def test_eligible_registration_requires_source_and_public_report(self) -> None:
        self._declare_optional_policy()
        source = self.pack / "assets/generated/unwatermarked-masters/cover.png"
        marked = self.pack / "assets/generated/cover-marked.png"
        report_path = self.pack / "assets/generated/watermark-reports/cover.json"
        write_png(source, 512, 512, alpha=False, pattern_strength=22)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = embed_watermark(
            source,
            marked,
            key=TEST_WATERMARK_KEY,
            key_epoch=7,
            wm_id="11" * 8,
        )
        write_json(report_path, report)

        tampered_psnr = json.loads(json.dumps(report))
        tampered_psnr["psnr_db"] = float(report["psnr_db"]) + 1.0
        tampered_psnr_path = report_path.with_name("cover-tampered-psnr.json")
        write_json(tampered_psnr_path, tampered_psnr)
        with mock.patch.dict(
            os.environ, {"PROVENANCE_WATERMARK_KEY": TEST_WATERMARK_ENV}
        ):
            with self.assertRaisesRegex(ValueError, "psnr_db does not match"):
                watermark_evidence_from_report(
                    tampered_psnr,
                    tampered_psnr_path,
                    marked,
                    pack_dir=self.pack,
                    source_path=source,
                    key_id="test-external-key",
                )

        low_quality = marked.with_name("cover-low-quality.png")
        write_png(low_quality, 512, 512, alpha=False, color=(30, 100, 180))
        low_quality_report = json.loads(json.dumps(report))
        low_quality_report["post_sha256"] = file_sha256(low_quality)
        low_quality_report_path = report_path.with_name("cover-low-quality.json")
        write_json(low_quality_report_path, low_quality_report)
        with mock.patch.dict(
            os.environ, {"PROVENANCE_WATERMARK_KEY": TEST_WATERMARK_ENV}
        ):
            with self.assertRaisesRegex(ValueError, "below 42.0"):
                watermark_evidence_from_report(
                    low_quality_report,
                    low_quality_report_path,
                    low_quality,
                    pack_dir=self.pack,
                    source_path=source,
                    key_id="test-external-key",
                )

        base = {
            "pack": self.pack,
            "asset_id": "cover.generated",
            "kind": "illustration",
            "title": "Generated cover",
            "location": "assets/generated/cover-marked.png",
            "origin": "generated-illustrative",
            "style": "article-cover",
            "use": ["cover"],
            "role": None,
            "generated_for": None,
            "source_id": None,
            "visual_role": "illustrative-atmosphere",
            "background_family_id": None,
            "background_variant": None,
        }
        missing_both = type(
            "Args", (), {**base, "watermark_source": None, "watermark_report": None}
        )()
        with self.assertRaisesRegex(SystemExit, "--watermark-source"):
            command_register_asset(missing_both)
        missing_source = type(
            "Args",
            (),
            {
                **base,
                "watermark_source": None,
                "watermark_report": Path("assets/generated/watermark-reports/cover.json"),
            },
        )()
        with self.assertRaisesRegex(SystemExit, "--watermark-source"):
            command_register_asset(missing_source)

        complete = type(
            "Args",
            (),
            {
                **base,
                "watermark_source": Path(
                    "assets/generated/unwatermarked-masters/cover.png"
                ),
                "watermark_report": Path(
                    "assets/generated/watermark-reports/cover.json"
                ),
            },
        )()
        with mock.patch.dict(os.environ, {"PROVENANCE_WATERMARK_KEY": TEST_WATERMARK_ENV}):
            command_register_asset(complete)
        assets_doc = json.loads((self.pack / "assets.json").read_text(encoding="utf-8"))
        registered = next(
            item for item in assets_doc["assets"] if item.get("id") == "cover.generated"
        )
        evidence = registered["watermark"]
        self.assertEqual(evidence["scheme"], WATERMARK_SCHEME)
        self.assertEqual(evidence["key_id"], "test-external-key")
        self.assertEqual(evidence["key_epoch"], 7)
        self.assertEqual(
            evidence["source_location"],
            "assets/generated/unwatermarked-masters/cover.png",
        )
        self.assertEqual(
            evidence["report_location"],
            "assets/generated/watermark-reports/cover.json",
        )
        self.assertNotIn("wm_id", json.dumps(evidence, ensure_ascii=False))

    def test_v1_excludes_real_identity_micro_svg_remote_and_derived_assets(self) -> None:
        opaque = self.pack / "assets/generated/background-master.png"
        transparent = self.pack / "assets/generated/spot-opening.png"
        fixtures = [
            ({"location": "photo.png", "kind": "photo", "origin": "photographed"}, opaque, False),
            ({"location": "logo.png", "kind": "logo", "origin": "official"}, opaque, False),
            ({"location": "qr.png", "kind": "qr", "origin": "user-supplied"}, opaque, False),
            (
                {
                    "location": "evidence.png",
                    "kind": "illustration",
                    "origin": "generated-illustrative",
                    "visual_role": "documentary-evidence",
                },
                opaque,
                False,
            ),
            (
                {
                    "location": "micro.png",
                    "kind": "illustration",
                    "origin": "generated-illustrative",
                    "visual_role": "article-micro",
                    "uses": ["cover"],
                },
                transparent,
                False,
            ),
            (
                {
                    "location": "motion.svg",
                    "kind": "background",
                    "origin": "generated-illustrative",
                },
                self.pack / "motion.svg",
                True,
            ),
            (
                {
                    "location": "https://example.test/background.png",
                    "kind": "background",
                    "origin": "generated-illustrative",
                },
                None,
                True,
            ),
            (
                {
                    "location": "derived-cover.png",
                    "kind": "illustration",
                    "origin": "derived",
                    "uses": ["cover"],
                },
                opaque,
                False,
            ),
        ]
        for asset, path, expected_in_scope in fixtures:
            with self.subTest(asset=asset):
                requirement = asset_watermark_requirement(asset, path)
                self.assertEqual(requirement["in_scope"], expected_in_scope)
                self.assertFalse(requirement["eligible"])

    def test_malformed_cover_uses_and_outside_pack_paths_cannot_bypass_policy(self) -> None:
        outside = self.root / "outside-cover.png"
        write_png(outside, 512, 512, alpha=False, pattern_strength=22)
        scalar_cover = {
            "id": "cover.outside",
            "kind": "illustration",
            "origin": "generated-illustrative",
            "location": "../outside-cover.png",
            "uses": "cover",
        }
        requirement = asset_watermark_requirement(scalar_cover, outside)
        self.assertTrue(requirement["in_scope"])

        organization = {
            "provenance": {
                "generated_image_watermark": {
                    "mode": "required",
                    "scheme": WATERMARK_SCHEME,
                    "key_id": "test-external-key",
                }
            }
        }
        inventory = watermark_inventory(
            organization,
            {"assets": [scalar_cover]},
            self.pack,
        )
        self.assertFalse(inventory["ready"])
        self.assertTrue(
            any("watermark.path.outside_pack" in item for item in inventory["errors"]),
            inventory["errors"],
        )

    def test_forged_authenticated_report_cannot_substitute_unmarked_pixels(self) -> None:
        source = self.pack / "assets/generated/unwatermarked-masters/forged-source.png"
        genuine = self.pack / "assets/generated/forged-genuine.png"
        unmarked = self.pack / "assets/generated/forged-unmarked.png"
        report_path = self.pack / "assets/generated/watermark-reports/forged.json"
        write_png(
            source,
            512,
            512,
            alpha=False,
            color=(30, 100, 180),
            pattern_strength=22,
        )
        genuine_report = embed_watermark(
            source,
            genuine,
            key=TEST_WATERMARK_KEY,
            key_epoch=7,
            wm_id="22" * 8,
        )
        write_png(
            unmarked,
            512,
            512,
            alpha=False,
            color=(31, 101, 181),
            pattern_strength=22,
        )
        forged = json.loads(json.dumps(genuine_report))
        forged["post_sha256"] = file_sha256(unmarked)
        forged["psnr_db"] = round(measure_psnr(source, unmarked), 4)
        forged["detection"]["status"] = "payload_authenticated"
        forged["detection"]["authenticated"] = True
        forged["detection"]["detected"] = True
        forged["detection"]["input_sha256"] = file_sha256(unmarked)
        forged["detection"]["input_bytes"] = unmarked.stat().st_size
        report_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(report_path, forged)

        with mock.patch.dict(os.environ, {"PROVENANCE_WATERMARK_KEY": TEST_WATERMARK_ENV}):
            with self.assertRaisesRegex(
                ValueError,
                r"watermark\.detect\.unauthenticated|watermark\.transport\.failed",
            ):
                watermark_evidence_from_report(
                    forged,
                    report_path,
                    unmarked,
                    pack_dir=self.pack,
                    source_path=source,
                    key_id="test-external-key",
                )

    def test_public_report_schema_rejects_unknown_private_nan_and_unbound_input(self) -> None:
        source = self.pack / "assets/generated/unwatermarked-masters/schema-source.png"
        marked = self.pack / "assets/generated/schema-marked.png"
        report_dir = self.pack / "assets/generated/watermark-reports"
        write_png(source, 512, 512, alpha=False, pattern_strength=22)
        report = embed_watermark(
            source,
            marked,
            key=TEST_WATERMARK_KEY,
            key_epoch=7,
            wm_id="33" * 8,
        )
        cases: list[tuple[str, dict[str, Any], str]] = []

        unknown_top = json.loads(json.dumps(report))
        unknown_top["reader_id"] = "must-not-be-public"
        cases.append(("reader-id", unknown_top, "private identifiers|unknown fields"))

        unknown_nested = json.loads(json.dumps(report))
        unknown_nested["detection"]["secret"] = "must-not-be-public"
        cases.append(("nested-secret", unknown_nested, "private identifiers|unknown fields"))

        raw_identifier = json.loads(json.dumps(report))
        raw_identifier["carrier"]["raw_identifier"] = "opaque-looking-but-private"
        cases.append(("raw-identifier", raw_identifier, "private identifiers|unknown fields"))

        nan_psnr = json.loads(json.dumps(report))
        nan_psnr["psnr_db"] = float("nan")
        cases.append(("nan-psnr", nan_psnr, "psnr_db must be a finite number"))

        wrong_input = json.loads(json.dumps(report))
        wrong_input["carrier"]["input_sha256"] = "0" * 64
        cases.append(("wrong-input", wrong_input, "carrier.input_sha256"))

        forged_reason = json.loads(json.dumps(report))
        forged_reason["carrier"]["reason"] = "secret-material-in-allowed-field"
        cases.append(("forged-reason", forged_reason, "carrier differs"))

        forged_mode = json.loads(json.dumps(report))
        forged_mode["detection"]["image"]["mode"] = "secret-material-in-allowed-field"
        cases.append(("forged-mode", forged_mode, "detection differs"))

        report_dir.mkdir(parents=True, exist_ok=True)
        for name, candidate, message in cases:
            with self.subTest(name=name):
                candidate_path = report_dir / f"schema-{name}.json"
                write_json(candidate_path, candidate)
                with mock.patch.dict(
                    os.environ,
                    {"PROVENANCE_WATERMARK_KEY": TEST_WATERMARK_ENV},
                ):
                    with self.assertRaisesRegex(ValueError, message):
                        watermark_evidence_from_report(
                            candidate,
                            candidate_path,
                            marked,
                            pack_dir=self.pack,
                            source_path=source,
                            key_id="test-external-key",
                        )

    def test_transport_claim_is_rejected_when_independent_simulation_fails(self) -> None:
        source = self.pack / "assets/generated/unwatermarked-masters/transport-source.png"
        marked = self.pack / "assets/generated/transport-marked.png"
        report_path = self.pack / "assets/generated/watermark-reports/transport.json"
        write_png(source, 512, 512, alpha=False, pattern_strength=22)
        report = embed_watermark(
            source,
            marked,
            key=TEST_WATERMARK_KEY,
            key_epoch=7,
            wm_id="44" * 8,
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(report_path, report)
        failed_transport = dict(report["transport_simulation"])
        failed_transport.update(
            {
                "status": "not_detected",
                "payload_authenticated": False,
                "payload_fingerprint": None,
            }
        )
        with mock.patch.dict(os.environ, {"PROVENANCE_WATERMARK_KEY": TEST_WATERMARK_ENV}):
            with mock.patch(
                "provenance_watermark.verify_transport_simulation",
                return_value=failed_transport,
            ):
                with self.assertRaisesRegex(ValueError, r"watermark\.transport"):
                    watermark_evidence_from_report(
                        report,
                        report_path,
                        marked,
                        pack_dir=self.pack,
                        source_path=source,
                        key_id="test-external-key",
                    )

    def test_policy_rejects_invalid_or_secret_like_key_ids(self) -> None:
        original = json.loads(
            (self.pack / "organization.json").read_text(encoding="utf-8")
        )
        for key_id in ("Uppercase-Key", "a" * 65, "0123456789abcdef" * 4):
            with self.subTest(key_id=key_id):
                organization = json.loads(json.dumps(original))
                organization["provenance"]["generated_image_watermark"] = {
                    "mode": "optional",
                    "scheme": WATERMARK_SCHEME,
                    "key_id": key_id,
                }
                write_json(self.pack / "organization.json", organization)
                report = validate_pack(self.pack)
                self.assertFalse(report["ok"])
                self.assertTrue(
                    any(
                        "generated_image_watermark.key_id" in item
                        for item in report["errors"]
                    ),
                    report["errors"],
                )
                inventory = watermark_inventory(
                    organization,
                    json.loads((self.pack / "assets.json").read_text(encoding="utf-8")),
                    self.pack,
                )
                self.assertFalse(inventory["ready"])
                self.assertTrue(
                    any("watermark.policy.invalid" in item for item in inventory["errors"]),
                    inventory["errors"],
                )

    def test_inventory_itself_rejects_invalid_policy_mode_and_scheme(self) -> None:
        assets_doc = json.loads((self.pack / "assets.json").read_text(encoding="utf-8"))
        for policy in (
            {"mode": "disabled", "scheme": WATERMARK_SCHEME, "key_id": "external"},
            {"mode": "optional", "scheme": "unknown-scheme", "key_id": "external"},
        ):
            with self.subTest(policy=policy):
                inventory = watermark_inventory(
                    {"provenance": {"generated_image_watermark": policy}},
                    assets_doc,
                    self.pack,
                )
                self.assertFalse(inventory["ready"])
                self.assertTrue(
                    any("watermark.policy.invalid" in item for item in inventory["errors"]),
                    inventory["errors"],
                )

    def test_required_policy_blocks_ineligible_and_unmarked_in_scope_carriers(self) -> None:
        organization = json.loads(
            (self.pack / "organization.json").read_text(encoding="utf-8")
        )
        organization["provenance"]["generated_image_watermark"] = {
            "mode": "required",
            "scheme": WATERMARK_SCHEME,
            "key_id": "test-external-key",
        }
        write_json(self.pack / "organization.json", organization)
        report = validate_pack(self.pack)
        self.assertFalse(report["ok"])
        self.assertTrue(
            any("watermark.carrier.ineligible" in item for item in report["errors"]),
            report["errors"],
        )

        for filename, color in (
            ("background-master.png", (32, 94, 160)),
            ("background-companion.png", (35, 96, 162)),
        ):
            write_png(
                self.pack / "assets/generated" / filename,
                390,
                780,
                alpha=False,
                color=color,
                pattern_strength=22,
            )
        report = validate_pack(self.pack)
        self.assertFalse(report["ok"])
        self.assertTrue(
            any("watermark.required" in item for item in report["errors"]),
            report["errors"],
        )

    def test_required_policy_blocks_remote_and_svg_generated_backgrounds(self) -> None:
        organization = {
            "provenance": {
                "generated_image_watermark": {
                    "mode": "required",
                    "scheme": WATERMARK_SCHEME,
                    "key_id": "test-external-key",
                }
            }
        }
        assets_doc = {
            "assets": [
                {
                    "id": "background.remote",
                    "kind": "background",
                    "origin": "generated-illustrative",
                    "location": "https://example.test/generated.png",
                },
                {
                    "id": "background.svg",
                    "kind": "background",
                    "origin": "generated-illustrative",
                    "location": "assets/generated/background.svg",
                },
            ]
        }
        inventory = watermark_inventory(organization, assets_doc, self.pack)
        self.assertFalse(inventory["ready"])
        carrier_errors = [
            item for item in inventory["errors"] if "watermark.carrier.ineligible" in item
        ]
        self.assertEqual(len(carrier_errors), 2, inventory["errors"])

    def test_public_evidence_report_hash_and_pack_paths_are_immutable(self) -> None:
        reports = enable_required_watermark(self.pack)
        with mock.patch.dict(os.environ, {"PROVENANCE_WATERMARK_KEY": TEST_WATERMARK_ENV}):
            report = validate_pack(self.pack)
        self.assertTrue(report["ok"], report["errors"])
        assets_doc = json.loads((self.pack / "assets.json").read_text(encoding="utf-8"))
        serialized = json.dumps(assets_doc, ensure_ascii=False)
        self.assertNotIn("wm_id", serialized)
        self.assertNotIn("private_record", serialized)

        report_path = self.pack / "assets/generated/watermark-reports/background-master.json"
        tampered = dict(reports["background.master"])
        tampered["untrusted_note"] = "changed after registration"
        write_json(report_path, tampered)
        with mock.patch.dict(os.environ, {"PROVENANCE_WATERMARK_KEY": TEST_WATERMARK_ENV}):
            invalid = validate_pack(self.pack)
        self.assertFalse(invalid["ok"])
        self.assertTrue(
            any("watermark.report_hash.mismatch" in item for item in invalid["errors"]),
            invalid["errors"],
        )

        write_json(report_path, reports["background.master"])
        assets_doc["assets"][0]["watermark"]["report_location"] = "../../outside.json"
        write_json(self.pack / "assets.json", assets_doc)
        with mock.patch.dict(os.environ, {"PROVENANCE_WATERMARK_KEY": TEST_WATERMARK_ENV}):
            invalid = validate_pack(self.pack)
        self.assertFalse(invalid["ok"])
        self.assertTrue(
            any("watermark.path.outside_pack" in item for item in invalid["errors"]),
            invalid["errors"],
        )

    def test_validate_pack_and_manifest_block_when_external_key_is_missing(self) -> None:
        enable_required_watermark(self.pack)
        with mock.patch.dict(os.environ, {}, clear=True):
            report = validate_pack(self.pack)
            self.assertFalse(report["ok"])
            self.assertTrue(
                any("watermark.detect.failed" in item for item in report["errors"]),
                report["errors"],
            )
            self.assertFalse(report["provenance_watermark"]["ready"])
            with self.assertRaisesRegex(ValueError, "watermark.detect.failed"):
                build_manifest(self.article, self.pack)

    def test_manifest_and_compile_preserve_and_reverify_marked_derivative(self) -> None:
        enable_required_watermark(self.pack)
        with mock.patch.dict(os.environ, {"PROVENANCE_WATERMARK_KEY": TEST_WATERMARK_ENV}):
            manifest = build_manifest(self.article, self.pack)
        self.assertTrue(manifest["provenance_watermark"]["ready"])
        master = next(item for item in manifest["assets"] if item["ref"] == "background.master")
        self.assertEqual(master["watermark"]["scheme"], WATERMARK_SCHEME)
        self.assertIn("payload_fingerprint", master["watermark"])

        def absolute_strings(value: Any) -> list[str]:
            if isinstance(value, dict):
                return [
                    item
                    for child in value.values()
                    for item in absolute_strings(child)
                ]
            if isinstance(value, list):
                return [item for child in value for item in absolute_strings(child)]
            if isinstance(value, str) and Path(value).is_absolute():
                return [value]
            return []

        self.assertEqual(absolute_strings(manifest["provenance_watermark"]), [])

        add_visual_review(self.article)
        output = self.root / "watermarked-output"
        with mock.patch.dict(os.environ, {"PROVENANCE_WATERMARK_KEY": TEST_WATERMARK_ENV}):
            report = compile_article(self.article, self.pack, output, check=True)
        self.assertTrue(report["ok"], report["errors"])
        watermark = report["provenance_watermark"]
        self.assertTrue(watermark["ready"])
        self.assertEqual(watermark["used_verified_asset_ids"], ["background.master"])
        self.assertEqual(len(watermark["copy_checks"]), 1)
        copy_check = watermark["copy_checks"][0]
        self.assertEqual(copy_check["source_sha256"], copy_check["output_sha256"])
        self.assertEqual(copy_check["detection"]["status"], "payload_authenticated")
        self.assertTrue(copy_check["detection"]["authenticated"])
        self.assertEqual(
            copy_check["transport_simulation"]["status"],
            "payload_authenticated",
        )
        self.assertTrue(copy_check["transport_simulation"]["payload_authenticated"])
        self.assertNotIn("source", copy_check)
        self.assertNotIn("local_path", copy_check)
        self.assertEqual(absolute_strings(watermark), [])
        serialized_report = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("wm_id", serialized_report)
        self.assertNotIn(str(self.root.resolve()), serialized_report)
        self.assertTrue(
            all(
                not Path(item["source"]).is_absolute()
                for item in report["copied_assets"]
            )
        )

        with mock.patch.dict(os.environ, {}, clear=True):
            missing_key = compile_article(
                self.article,
                self.pack,
                self.root / "watermarked-output-no-key",
                check=True,
            )
        self.assertFalse(missing_key["ok"])
        self.assertTrue(
            any("watermark.detect.failed" in item for item in missing_key["errors"]),
            missing_key["errors"],
        )


class VisualKitTests(FreshWorkflowTestCase):
    def test_chatgpt_web_is_default_source_and_alpha_is_never_trusted(self) -> None:
        plan = build_visual_kit_plan(self.article, self.pack)
        route = plan["generation_route"]
        self.assertEqual(route["default"], "chatgpt-web-image-route-v1")
        self.assertEqual(route["session_skill"], "codex-with-chatgpt")
        self.assertFalse(route["computer_use_allowed"])
        self.assertFalse(route["alpha_claim_trusted"])
        self.assertEqual(route["processor"], "scripts/prepare_micro_cutout.py")
        self.assertEqual(route["output_contract"], "subject-cutout-rgba8-v1")
        self.assertEqual(len({slot["source_generation"]["key_color"] for slot in plan["slots"]}), 4)
        for slot in plan["slots"]:
            source = slot["source_generation"]
            self.assertEqual(slot["asset_slot_id"], f"kit.{slot['role']}")
            self.assertEqual(source["route"], "chatgpt-web-image-route-v1")
            self.assertNotEqual(source["key_color"], source["fallback_key_color"])
            self.assertIn(source["key_color"], slot["prompt"])
            self.assertIn("download the original PNG", slot["prompt"])
            self.assertNotIn("real 8-bit RGBA PNG", slot["prompt"])

    def test_four_distinct_grounded_alpha_components_unlock_layout(self) -> None:
        plan = build_visual_kit_plan(self.article, self.pack)
        self.assertTrue(plan["ready_for_layout"], plan["blocking_reasons"])
        self.assertEqual(plan["minimum_unique_generated_micro_assets"], 4)
        self.assertTrue(all(slot["alpha_validation"]["ok"] for slot in plan["slots"]))

    def test_one_asset_cannot_cover_two_micro_roles(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        article["visual_kit"]["assets"][3]["id"] = article["visual_kit"]["assets"][0]["id"]
        write_json(self.article, article)
        plan = build_visual_kit_plan(self.article, self.pack)
        self.assertFalse(plan["ready_for_layout"])
        self.assertTrue(any("4 unique" in item for item in plan["blocking_reasons"]))

    def test_native_ardot_component_evidence_is_required(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        article["visual_kit"]["assets"][0].pop("ardot_component")
        write_json(self.article, article)
        plan = build_visual_kit_plan(self.article, self.pack)
        self.assertFalse(plan["ready_for_layout"])
        self.assertTrue(any("native Ardot" in item for item in plan["semantic_errors"]))

    def test_replaced_alpha_asset_must_match_registered_hash(self) -> None:
        replacement = self.pack / "assets" / "generated" / "spot-opening.png"
        write_png(replacement, 300, 300)
        with self.assertRaisesRegex(ValueError, "stored cutout evidence"):
            build_visual_kit_plan(self.article, self.pack)

    def test_empty_or_stale_cutout_evidence_is_rejected(self) -> None:
        assets = json.loads((self.pack / "assets.json").read_text(encoding="utf-8"))
        micro = next(item for item in assets["assets"] if item.get("visual_role") == "article-micro")
        micro["quality"]["cutout_evidence"] = {}
        write_json(self.pack / "assets.json", assets)

        report = validate_pack(self.pack)
        self.assertFalse(report["ok"])
        self.assertTrue(
            any("detailed cutout evidence" in error for error in report["errors"]),
            report["errors"],
        )

    def test_article_micro_cutout_gate_runs_regardless_of_origin(self) -> None:
        assets = json.loads((self.pack / "assets.json").read_text(encoding="utf-8"))
        micro = next(item for item in assets["assets"] if item.get("visual_role") == "article-micro")
        micro["origin"] = "user-supplied"
        asset_path = self.pack / micro["location"]
        write_png(asset_path, micro["quality"]["width_px"], micro["quality"]["height_px"], alpha=False)
        micro["quality"]["sha256"] = file_sha256(asset_path)
        write_json(self.pack / "assets.json", assets)

        report = validate_pack(self.pack)
        self.assertFalse(report["ok"])
        self.assertTrue(
            any("article-micro asset" in error and "cutout gate" in error for error in report["errors"]),
            report["errors"],
        )

    def test_article_micro_asset_without_roles_is_rejected(self) -> None:
        assets = json.loads((self.pack / "assets.json").read_text(encoding="utf-8"))
        micro = next(item for item in assets["assets"] if item.get("visual_role") == "article-micro")
        micro.pop("roles")
        write_json(self.pack / "assets.json", assets)

        report = validate_pack(self.pack)
        self.assertFalse(report["ok"])
        self.assertTrue(
            any("requires at least one visual-kit role" in error for error in report["errors"]),
            report["errors"],
        )

    def test_visual_directions_have_five_source_zero_calibration_samples(self) -> None:
        plan = build_directions(self.pack, "introduction")
        self.assertEqual(len(plan["directions"]), 2)
        self.assertTrue(all(len(item["calibration_strip"]) == 5 for item in plan["directions"]))
        family_trial = plan["directions"][0]["background_family_trial"]
        self.assertEqual(family_trial["approval_contract"]["minimum_contrast_ratio"], 4.5)
        self.assertIn("one of light or dark", family_trial["approval_contract"]["surface_mode"])
        typography_trial = plan["directions"][0]["typography_trial"]
        self.assertTrue(typography_trial["approve_as_recipes"])
        self.assertIn("A font swap alone", typography_trial["forbidden"])
        serialized = json.dumps(plan, ensure_ascii=False)
        self.assertIn("prior article layouts", serialized)
        self.assertIn("background_family_trial", serialized)
        self.assertIn("typography_trial", serialized)

    def test_explicit_style_grammar_hash_propagates_to_all_build_plans(self) -> None:
        grammar = enable_explicit_style_reference(self.pack)
        expected_hash = grammar["sha256"]
        asset_plan = build_asset_plan(self.pack, "introduction")
        visual_kit = build_visual_kit_plan(self.article, self.pack)
        manifest = build_manifest(self.article, self.pack)
        self.assertEqual(asset_plan["style_grammar_sha256"], expected_hash)
        self.assertEqual(visual_kit["style_grammar_sha256"], expected_hash)
        self.assertEqual(manifest["route"]["style_grammar_sha256"], expected_hash)
        self.assertEqual(manifest["style_reference"]["grammar_sha256"], expected_hash)
        self.assertEqual(asset_plan["style_preset_id"], "prismatic-paper-editorial")
        self.assertEqual(visual_kit["style_preset_label"], "绚烂纸本")
        self.assertEqual(manifest["route"]["style_preset_id"], "prismatic-paper-editorial")
        self.assertEqual(manifest["style_reference"]["preset_label"], "绚烂纸本")
        self.assertEqual(asset_plan["style_grammar"], visual_kit["style_grammar"])
        self.assertEqual(visual_kit["style_grammar"], manifest["route"]["style_grammar"])
        self.assertIn(str(expected_hash), visual_kit["slots"][0]["prompt"])
        self.assertIn("never copy reference text", visual_kit["slots"][0]["prompt"])

    def test_art_type_must_remain_native_editable_text(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        article["typography"]["moments"][0]["editable_text"] = False
        article["typography"]["moments"][0]["asset_id"] = "generated-title.png"
        write_json(self.article, article)
        manifest = build_manifest(self.article, self.pack)
        self.assertFalse(manifest["qa"]["ready_for_layout"])
        self.assertTrue(any("baked text assets" in item for item in manifest["typography"]["errors"]))

    def test_art_type_moments_require_distinct_native_text_nodes(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        article["typography"]["moments"][1]["ardot_text_style"]["node_id"] = "41:1"
        write_json(self.article, article)
        manifest = build_manifest(self.article, self.pack)
        self.assertFalse(manifest["qa"]["ready_for_layout"])
        self.assertTrue(any("reuses an Ardot text node" in item for item in manifest["typography"]["errors"]))

    def test_art_type_font_swap_without_construction_is_blocked(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        article["typography"]["moments"][0]["construction"] = {
            "techniques": [],
            "native_text_node_ids": ["41:1"],
            "accent_node_ids": [],
            "line_count": 1,
        }
        write_json(self.article, article)
        manifest = build_manifest(self.article, self.pack)
        self.assertFalse(manifest["qa"]["ready_for_layout"])
        self.assertTrue(
            any("font swap alone" in item for item in manifest["typography"]["errors"]),
            manifest["typography"]["errors"],
        )

    def test_storyboard_density_intent_is_mandatory(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        article["storyboard"]["chapters"][1].pop("density_intent")
        write_json(self.article, article)
        report = build_storyboard_plan(self.article)
        self.assertFalse(report["ready_for_visual_kit"])


class InteractionPlanTests(FreshWorkflowTestCase):
    def _report(self, *, require_evidence: bool = True) -> dict:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        ardot = json.loads((self.pack / "ardot.json").read_text(encoding="utf-8"))
        return validate_interaction_plan(
            article,
            ardot,
            self.article,
            require_evidence=require_evidence,
        )

    def test_default_plan_has_two_semantic_modules(self) -> None:
        report = self._report()
        self.assertTrue(report["ready"], report["errors"])
        self.assertEqual(report["module_count"], 2)
        self.assertEqual(report["instance_count"], 2)
        self.assertEqual(
            report["production_default"],
            "static-fallback-until-account-runtime-certification",
        )

    def test_four_reveal_cards_count_as_one_module_and_four_instances(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        card_copy = [
            "不同能力沿同一条路径汇合。",
            "策划部门把问题整理成清晰任务。",
            "技术部门把任务推进为可测试原型。",
            "传播部门把成果翻译成读者能理解的故事。",
        ]
        article["blocks"][1]["paragraphs"] = card_copy
        instances = [
            {
                "id": f"department-{index}",
                "source_texts": [text],
                "fallback_key": f"department-{index}",
                "semantic_hash": interaction_semantic_hash([text]),
            }
            for index, text in enumerate(card_copy, 1)
        ]
        article["interaction_plan"]["modules"][0]["instances"] = instances
        component = article["interaction_plan"]["modules"][0]["ardot_component"]
        component["covered_instance_ids"] = [item["id"] for item in instances]
        component["covered_semantic_hashes"] = [item["semantic_hash"] for item in instances]
        write_json(self.article, article)
        report = self._report()
        self.assertTrue(report["ready"], report["errors"])
        self.assertEqual(report["module_count"], 2)
        self.assertEqual(report["instance_count"], 5)
        self.assertEqual(report["modules"][0]["instance_count"], 4)

    def test_default_plan_rejects_more_than_three_modules(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        article["interaction_plan"]["target_module_count"] = 4
        article["interaction_plan"]["modules"].extend(
            [
                {
                    **article["interaction_plan"]["modules"][0],
                    "id": "extra-reveal-one",
                },
                {
                    **article["interaction_plan"]["modules"][1],
                    "id": "extra-reveal-two",
                },
            ]
        )
        write_json(self.article, article)
        report = self._report(require_evidence=False)
        self.assertFalse(report["ready"])
        self.assertTrue(any("2 to 3 semantic modules" in item for item in report["errors"]))

    def test_static_exception_requires_explicit_editorial_record(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        article["interaction_plan"] = {
            "status": "approved",
            "authoring_mode": "static-exception",
            "target_module_count": 0,
            "modules": [],
            "exception": {
                "category": "user-requested-static",
                "reason": "用户明确要求本篇只保留静态阅读体验。",
                "confirmed_by": "user",
            },
        }
        write_json(self.article, article)
        report = self._report()
        self.assertTrue(report["ready"], report["errors"])
        article["interaction_plan"]["exception"].pop("reason")
        write_json(self.article, article)
        report = self._report()
        self.assertFalse(report["ready"])
        self.assertTrue(any("specific reason" in item for item in report["errors"]))

    def test_modules_must_be_distributed_across_early_and_middle(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        article["interaction_plan"]["modules"][1]["placement_band"] = "early"
        write_json(self.article, article)
        report = self._report(require_evidence=False)
        self.assertFalse(report["ready"])
        self.assertTrue(any("early and middle" in item for item in report["errors"]))

    def test_placement_band_must_match_actual_storyboard_position(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        module = article["interaction_plan"]["modules"][0]
        module["storyboard_chapter"] = "join"
        module["source_block_indices"] = [3]
        source = "把已经完成的原型交给下一位伙伴。"
        module["instances"][0]["source_texts"] = [source]
        module["instances"][0]["semantic_hash"] = interaction_semantic_hash([source])
        write_json(self.article, article)
        report = self._report(require_evidence=False)
        self.assertFalse(report["ready"])
        self.assertTrue(any("belongs to late, not early" in item for item in report["errors"]))

    def test_modules_must_have_distinct_editorial_purposes(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        article["interaction_plan"]["modules"][1]["purpose"] = (
            article["interaction_plan"]["modules"][0]["purpose"]
        )
        write_json(self.article, article)
        report = self._report(require_evidence=False)
        self.assertFalse(report["ready"])
        self.assertTrue(any("distinct editorial purposes" in item for item in report["errors"]))

    def test_transport_instance_hash_is_bound_to_source_copy(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        article["interaction_plan"]["modules"][0]["instances"][0]["semantic_hash"] = (
            "sha256:" + "0" * 64
        )
        write_json(self.article, article)
        report = self._report(require_evidence=False)
        self.assertFalse(report["ready"])
        self.assertTrue(any("semantic_hash" in item for item in report["errors"]))

    def test_manifest_allows_planning_before_evidence_but_compile_does_not(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        article["interaction_plan"].pop("ardot_revision_hash")
        article["interaction_plan"].pop("article_root_node_id")
        for module in article["interaction_plan"]["modules"]:
            module.pop("ardot_component")
        write_json(self.article, article)
        manifest = build_manifest(self.article, self.pack)
        self.assertTrue(manifest["interaction_plan"]["ready"])
        self.assertFalse(manifest["interaction_plan"]["evidence_required"])
        add_visual_review(self.article)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("final interaction evidence" in item for item in report["errors"]))

    def test_tampered_interaction_state_screenshot_blocks_compile(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        relative = article["interaction_plan"]["modules"][0]["ardot_component"]["states"]["closed"]["screenshot"]
        write_png(self.root / relative, 390, 241, alpha=False, color=(240, 20, 20))
        add_visual_review(self.article)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("interaction module 0 closed screenshot sha256" in item for item in report["errors"]))

    def test_group_evidence_must_cover_every_transport_instance(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        component = article["interaction_plan"]["modules"][0]["ardot_component"]
        component["covered_instance_ids"] = []
        write_json(self.article, article)
        report = self._report()
        self.assertFalse(report["ready"])
        self.assertTrue(any("cover every transport instance" in item for item in report["errors"]))

    def test_visual_review_revision_must_match_interaction_evidence(self) -> None:
        review_path = add_visual_review(self.article)
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review["capture"]["revision_hash"] = "b" * 64
        write_json(review_path, review)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("revision_hash must match" in item for item in report["errors"]))


class ArdotAndCompilerTests(FreshWorkflowTestCase):
    def _mutate_micro_node_evidence(self, review_path: Path, index: int, mutate: Any) -> None:
        review = json.loads(review_path.read_text(encoding="utf-8"))
        placement = review["micro_component_layout"]["placements"][index]
        properties_path = review_path.parent / placement["node_properties_file"]
        properties = json.loads(properties_path.read_text(encoding="utf-8"))
        mutate(properties)
        write_json(properties_path, properties)
        placement["node_properties_sha256"] = file_sha256(properties_path)
        write_json(review_path, review)

    def test_manifest_is_native_dense_and_open(self) -> None:
        manifest = build_manifest(self.article, self.pack)
        self.assertTrue(manifest["qa"]["ready_for_layout"])
        self.assertEqual(manifest["handoff"]["source_of_truth"], "ardot-native")
        self.assertEqual(manifest["qa"]["layout_policy"]["minimum_unique_generated_micro_assets"], 4)
        self.assertTrue(manifest["calibration"]["background_family_quality"]["ok"])
        self.assertEqual(
            manifest["qa"]["layout_policy"]["background_family_surface"],
            "one light/dark mode with pixel-checked copy safety and contrast >= 4.5",
        )
        self.assertEqual(
            manifest["qa"]["layout_policy"]["maximum_micro_image_width_ratio"],
            0.72,
        )
        self.assertEqual(
            manifest["qa"]["layout_policy"]["minimum_micro_copy_scale_ratio"],
            1.35,
        )
        self.assertEqual(
            manifest["qa"]["layout_policy"]["micro_copy_enclosure"],
            "none",
        )
        self.assertTrue(manifest["typography"]["ready"])
        self.assertEqual(manifest["typography"]["moment_count"], 2)
        self.assertTrue(manifest["interaction_plan"]["ready"])
        self.assertEqual(manifest["interaction_plan"]["module_count"], 2)
        self.assertFalse(manifest["interaction_plan"]["evidence_required"])
        self.assertEqual(
            manifest["workflow_attribution"]["text"],
            WORKFLOW_ATTRIBUTION_TEXT,
        )
        self.assertEqual(
            manifest["workflow_attribution"]["marker"],
            WORKFLOW_ATTRIBUTION_MARKER,
        )
        self.assertEqual(
            manifest["workflow_attribution"]["policy_id"],
            WORKFLOW_ATTRIBUTION_MARKER,
        )
        self.assertEqual(
            manifest["workflow_attribution"]["placement"],
            "terminal-after-all-article-blocks",
        )
        self.assertEqual(
            manifest["workflow_attribution"]["text_sha256"],
            f"sha256:{WORKFLOW_ATTRIBUTION_TEXT_SHA256}",
        )
        self.assertTrue(manifest["workflow_attribution"]["native_editable_text"])
        self.assertFalse(manifest["workflow_attribution"]["organization_identity"])
        self.assertTrue(
            manifest["workflow_attribution"]["component_name"].startswith(
                "WeChat/Footer/WorkflowAttribution/"
            )
        )
        self.assertEqual(manifest["handoff"]["contract_schema_version"], 5)
        self.assertEqual(
            manifest["handoff"]["transport_revision_algorithm"],
            "ardot-transport-revision-v1",
        )
        self.assertEqual(
            manifest["handoff"]["revision_algorithm"],
            "ardot-root-revision-v1",
        )
        self.assertEqual(
            manifest["handoff"]["required_workflow_attribution"]["policy_id"],
            WORKFLOW_ATTRIBUTION_MARKER,
        )
        self.assertIn(
            "node_export_sha256",
            manifest["handoff"]["required_workflow_attribution"]["evidence"],
        )
        self.assertTrue(all(block["container_policy"] == "open-by-default" for block in manifest["blocks"]))

    def test_compile_passes_only_with_hashed_390px_ardot_evidence(self) -> None:
        add_visual_review(self.article)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertTrue(report["ok"], report["errors"])
        self.assertFalse(report["delivery_eligible"])
        self.assertEqual(
            report["delivery_blocker"]["code"],
            "transport.source.article_json_renderer_forbidden",
        )
        self.assertTrue((self.root / "output" / "authoring-preview.html").exists())
        self.assertFalse((self.root / "output" / "wechat.html").exists())
        self.assertEqual(
            report["interaction_policy"]["policy_version"],
            "wechat-svg-smil-self-v1",
        )
        self.assertEqual(report["interaction_policy"]["status"], "static")
        self.assertEqual(report["interaction_authoring"]["module_count"], 2)
        self.assertEqual(
            report["interaction_authoring"]["production_default"],
            "static-fallback-until-account-runtime-certification",
        )
        self.assertTrue(report["workflow_attribution"]["ready"])
        self.assertTrue(report["workflow_attribution"]["terminal"])
        self.assertEqual(
            report["workflow_attribution"]["policy_id"],
            WORKFLOW_ATTRIBUTION_MARKER,
        )
        self.assertEqual(
            report["workflow_attribution"]["text_sha256"],
            f"sha256:{WORKFLOW_ATTRIBUTION_TEXT_SHA256}",
        )
        body = (self.root / "output" / "authoring-preview.html").read_text(encoding="utf-8")
        self.assertEqual(body.count(WORKFLOW_ATTRIBUTION_TEXT), 1)
        self.assertEqual(
            body.count(f'data-workflow-attribution="{WORKFLOW_ATTRIBUTION_MARKER}"'),
            1,
        )
        self.assertGreater(
            body.rfind(WORKFLOW_ATTRIBUTION_TEXT),
            body.rfind('data-component="'),
        )

    def test_missing_terminal_workflow_attribution_blocks_transport(self) -> None:
        add_visual_review(self.article)
        output = self.root / "output"
        with mock.patch("compile_wechat.render_workflow_attribution", return_value=""):
            report = compile_article(self.article, self.pack, output, check=True)
        self.assertFalse(report["ok"])
        self.assertFalse(report["workflow_attribution"]["ready"])
        self.assertTrue(
            any("workflow attribution" in item for item in report["errors"]),
            report["errors"],
        )
        self.assertFalse((output / "authoring-preview.html").exists())

    def test_user_footer_precedes_single_reserved_workflow_attribution(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        article["blocks"].append(
            {
                "type": "footer",
                "name": "Fresh organization",
                "tagline": "A user-authored footer",
                "credits": "编辑：测试编辑组",
            }
        )
        article["storyboard"]["chapters"][-1]["block_indices"].append(4)
        write_json(self.article, article)
        add_visual_review(self.article)
        output = self.root / "output"
        report = compile_article(self.article, self.pack, output, check=True)
        self.assertTrue(report["ok"], report["errors"])
        body = (output / "authoring-preview.html").read_text(encoding="utf-8")
        self.assertEqual(body.count(WORKFLOW_ATTRIBUTION_TEXT), 1)
        self.assertLess(body.index("编辑：测试编辑组"), body.index(WORKFLOW_ATTRIBUTION_TEXT))

    def test_article_cannot_duplicate_reserved_workflow_attribution(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        article["blocks"].append(
            {"type": "footer", "credits": WORKFLOW_ATTRIBUTION_TEXT}
        )
        article["storyboard"]["chapters"][-1]["block_indices"].append(4)
        write_json(self.article, article)
        add_visual_review(self.article)
        output = self.root / "output"
        report = compile_article(self.article, self.pack, output, check=True)
        self.assertFalse(report["ok"])
        self.assertFalse(report["workflow_attribution"]["present_once"])
        self.assertFalse((output / "authoring-preview.html").exists())

    def test_organization_tokens_cannot_hide_workflow_attribution(self) -> None:
        organization_path = self.pack / "organization.json"
        organization = json.loads(organization_path.read_text(encoding="utf-8"))
        organization["visual"]["tokens"]["body"] = organization["visual"]["tokens"][
            "surface"
        ]
        write_json(organization_path, organization)
        add_visual_review(self.article)
        output = self.root / "output"
        report = compile_article(self.article, self.pack, output, check=True)
        self.assertTrue(report["ok"], report["errors"])
        attribution = report["workflow_attribution"]
        self.assertTrue(attribution["contrast_ready"])
        self.assertGreaterEqual(attribution["contrast_ratio"], 4.5)
        self.assertNotEqual(attribution["text_color"], attribution["surface_color"])
        body = (output / "authoring-preview.html").read_text(encoding="utf-8")
        self.assertIn(
            f'data-workflow-attribution-contrast="{attribution["contrast_ratio"]}"',
            body,
        )

    def test_static_transport_keeps_micro_components_partial_width_and_unframed(self) -> None:
        add_visual_review(self.article)
        output = self.root / "output"
        report = compile_article(self.article, self.pack, output, check=True)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["visual_kit"]["transport_instance_count"], 4)
        body = (output / "authoring-preview.html").read_text(encoding="utf-8")
        self.assertEqual(body.count('data-visual-role="article-micro"'), 4)
        for role, *_ in ROLES:
            self.assertIn(f'data-micro-role="{role}"', body)
        ratios = [float(value) for value in re.findall(r'data-micro-width-ratio="([0-9.]+)"', body)]
        self.assertEqual(len(ratios), 4)
        self.assertTrue(all(value <= 0.72 for value in ratios))
        for section in re.findall(
            r'<section data-visual-role="article-micro".*?</section>',
            body,
            flags=re.S,
        ):
            self.assertNotIn("border:", section)
            self.assertNotIn("border-radius:", section)
            self.assertIn('data-micro-copy="none"', section)

    def test_repeated_micro_role_instances_are_all_reviewed_and_transported(self) -> None:
        review_path = add_visual_review(self.article)
        review = json.loads(review_path.read_text(encoding="utf-8"))
        layout = review["micro_component_layout"]
        source_component_node_id = layout["placements"][0]["source_component_node_id"]
        article = json.loads(self.article.read_text(encoding="utf-8"))
        floating_asset = next(
            item for item in article["visual_kit"]["assets"] if item["role"] == "floating-spot"
        )
        rendered_asset_path = review_path.parent / "qa/micro-5-rendered.png"
        shutil.copyfile(review_path.parent / "qa/micro-1-rendered.png", rendered_asset_path)
        properties_path = review_path.parent / "qa/micro-5-nodes.json"
        write_json(
            properties_path,
            {
                "schema_version": 1,
                "source": "ardot-node-properties",
                "article_root_node_id": "30:0",
                "article_width_px": 390,
                "instance": {
                    "node_id": "80:5",
                    "source_component_node_id": source_component_node_id,
                    "bounds": {"x": 151.5, "y": 260, "width": 117, "height": 130},
                },
                "complete_descendant_census": True,
                "visible_descendant_count": 1,
                "nodes": [
                    {
                        "node_id": "80:5:image",
                        "kind": "illustration",
                        "asset_id": floating_asset["id"],
                        "asset_sha256": floating_asset["asset_sha256"],
                        "rendered_asset_file": rendered_asset_path.name,
                        "rendered_asset_sha256": file_sha256(rendered_asset_path),
                        "bounds": {"x": 151.5, "y": 270, "width": 101.4, "height": 90},
                    }
                ],
            },
        )
        layout["placements"].append(
            {
                "id": "identity-floating-spot-2",
                "role": "floating-spot",
                "source_component_node_id": source_component_node_id,
                "instance_node_id": "80:5",
                "screenshot_node_id": review["screenshots"][1]["node_id"],
                "screenshot_sha256": review["screenshots"][1]["sha256"],
                "node_properties_file": "qa/micro-5-nodes.json",
                "node_properties_sha256": file_sha256(properties_path),
                "composition_relation": "continuous-path",
            }
        )
        inventory_path = review_path.parent / layout["inventory_file"]
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        inventory["instances"].append(
            {
                "instance_node_id": "80:5",
                "source_component_node_id": source_component_node_id,
            }
        )
        write_json(inventory_path, inventory)
        layout["inventory_sha256"] = file_sha256(inventory_path)
        write_json(review_path, review)

        output = self.root / "output"
        report = compile_article(self.article, self.pack, output, check=True)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(
            report["visual_review"]["micro_component_layout"]["inventory_instance_count"],
            5,
        )
        self.assertEqual(report["visual_kit"]["transport_instance_count"], 5)
        body = (output / "authoring-preview.html").read_text(encoding="utf-8")
        self.assertEqual(body.count('data-visual-role="article-micro"'), 5)
        self.assertIn('data-micro-instance="80:5"', body)

    def test_tampered_screenshot_hash_blocks_transport(self) -> None:
        review_path = add_visual_review(self.article)
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review["screenshots"][0]["sha256"] = "0" * 64
        write_json(review_path, review)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("sha256" in item for item in report["errors"]))

    def test_compact_editorial_major_gap_is_enforced(self) -> None:
        review_path = add_visual_review(self.article)
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review["density"]["samples"][2]["major_gap_px"] = 72
        write_json(review_path, review)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("major_gap_px" in item for item in report["errors"]))

    def test_body_text_contrast_is_enforced(self) -> None:
        review_path = add_visual_review(self.article)
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review["density"]["samples"][1]["body_text_contrast_ratio"] = 2.4
        write_json(review_path, review)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("contrast" in item for item in report["errors"]))

    def test_framed_micro_component_copy_is_blocked(self) -> None:
        review_path = add_visual_review(self.article)
        def add_frame(properties: dict[str, Any]) -> None:
            properties["nodes"].append(
                {
                    "node_id": "71:1",
                    "kind": "closed-shape",
                    "fill_alpha": 1,
                    "stroke_width_px": 1,
                    "bounds": {"x": 50, "y": 176, "width": 160, "height": 58},
                }
            )

        self._mutate_micro_node_evidence(review_path, 0, add_frame)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertIn(
            "micro.copy.framed",
            report["visual_review"]["micro_component_layout"]["error_codes"],
        )

    def test_full_width_micro_image_is_blocked(self) -> None:
        review_path = add_visual_review(self.article)
        def widen(properties: dict[str, Any]) -> None:
            properties["instance"]["bounds"]["x"] = 8
            properties["instance"]["bounds"]["width"] = 374
            properties["nodes"][0]["bounds"]["x"] = 8
            properties["nodes"][0]["bounds"]["width"] = 366

        self._mutate_micro_node_evidence(review_path, 1, widen)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertIn(
            "micro.image.full_width",
            report["visual_review"]["micro_component_layout"]["error_codes"],
        )

    def test_micro_component_placements_must_be_staggered(self) -> None:
        review_path = add_visual_review(self.article)
        for index in range(4):
            def center(properties: dict[str, Any]) -> None:
                width = properties["instance"]["bounds"]["width"]
                properties["instance"]["bounds"]["x"] = (390 - width) / 2

            self._mutate_micro_node_evidence(review_path, index, center)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertIn(
            "micro.layout.not_staggered",
            report["visual_review"]["micro_component_layout"]["error_codes"],
        )

    def test_micro_component_copy_requires_large_scale_contrast(self) -> None:
        review_path = add_visual_review(self.article)
        def flatten_copy(properties: dict[str, Any]) -> None:
            primary = next(node for node in properties["nodes"] if node.get("role") == "primary-copy")
            primary["font_size_px"] = 18
            primary["emphasis_techniques"] = ["mixed-weight"]

        self._mutate_micro_node_evidence(review_path, 0, flatten_copy)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        codes = report["visual_review"]["micro_component_layout"]["error_codes"]
        self.assertIn("micro.copy.scale_insufficient", codes)
        self.assertIn("micro.copy.scale_technique_missing", codes)

    def test_micro_component_review_must_cover_every_ardot_instance(self) -> None:
        review_path = add_visual_review(self.article)
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review["micro_component_layout"]["placements"].pop()
        write_json(review_path, review)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertIn(
            "micro.inventory.coverage_mismatch",
            report["visual_review"]["micro_component_layout"]["error_codes"],
        )

    def test_micro_component_instance_must_use_approved_cutout_pixels(self) -> None:
        review_path = add_visual_review(self.article)

        def swap_asset(properties: dict[str, Any]) -> None:
            image = next(
                node for node in properties["nodes"] if node.get("kind") == "illustration"
            )
            image["asset_sha256"] = "f" * 64

        self._mutate_micro_node_evidence(review_path, 0, swap_asset)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertIn(
            "micro.component.asset_mismatch",
            report["visual_review"]["micro_component_layout"]["error_codes"],
        )

    def test_micro_component_requires_complete_descendant_census(self) -> None:
        review_path = add_visual_review(self.article)

        def omit_census(properties: dict[str, Any]) -> None:
            properties.pop("complete_descendant_census")
            properties["visible_descendant_count"] -= 1

        self._mutate_micro_node_evidence(review_path, 0, omit_census)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertIn(
            "micro.component.incomplete_descendant_census",
            report["visual_review"]["micro_component_layout"]["error_codes"],
        )

    def test_rendered_ardot_layer_pixels_must_match_approved_cutout(self) -> None:
        review_path = add_visual_review(self.article)

        def replace_rendered_layer(properties: dict[str, Any]) -> None:
            image = next(
                node for node in properties["nodes"] if node.get("kind") == "illustration"
            )
            replacement = review_path.parent / "qa" / image["rendered_asset_file"]
            write_png(replacement, 256, 256, pattern_strength=31)
            image["rendered_asset_sha256"] = file_sha256(replacement)

        self._mutate_micro_node_evidence(review_path, 0, replace_rendered_layer)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertIn(
            "micro.component.rendered_asset_mismatch",
            report["visual_review"]["micro_component_layout"]["error_codes"],
        )

    def test_micro_component_image_cannot_have_a_visible_backplate(self) -> None:
        review_path = add_visual_review(self.article)

        def add_backplate(properties: dict[str, Any]) -> None:
            image = next(
                node for node in properties["nodes"] if node.get("kind") == "illustration"
            )
            properties["nodes"].append(
                {
                    "node_id": "80:1:backplate",
                    "kind": "closed-shape",
                    "fill_alpha": 1,
                    "stroke_width_px": 0,
                    "bounds": dict(image["bounds"]),
                }
            )

        self._mutate_micro_node_evidence(review_path, 0, add_backplate)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertIn(
            "micro.component.image_backplate",
            report["visual_review"]["micro_component_layout"]["error_codes"],
        )

    def test_unknown_visible_ardot_node_kind_fails_closed(self) -> None:
        review_path = add_visual_review(self.article)

        def add_unknown_backplate(properties: dict[str, Any]) -> None:
            image = next(
                node for node in properties["nodes"] if node.get("kind") == "illustration"
            )
            properties["nodes"].append(
                {
                    "node_id": "80:1:unknown-backplate",
                    "kind": "rectangle",
                    "fill_alpha": 1,
                    "stroke_width_px": 0,
                    "bounds": dict(image["bounds"]),
                }
            )

        self._mutate_micro_node_evidence(review_path, 0, add_unknown_backplate)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertIn(
            "micro.component.unknown_node_kind",
            report["visual_review"]["micro_component_layout"]["error_codes"],
        )

    def test_closed_shape_with_missing_visibility_fields_fails_closed(self) -> None:
        review_path = add_visual_review(self.article)

        def add_malformed_backplate(properties: dict[str, Any]) -> None:
            image = next(
                node for node in properties["nodes"] if node.get("kind") == "illustration"
            )
            properties["nodes"].append(
                {
                    "node_id": "80:1:malformed-backplate",
                    "kind": "closed-shape",
                    "bounds": dict(image["bounds"]),
                }
            )

        self._mutate_micro_node_evidence(review_path, 0, add_malformed_backplate)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertIn(
            "micro.component.invalid_closed_shape",
            report["visual_review"]["micro_component_layout"]["error_codes"],
        )

    def test_multiple_closed_shapes_cannot_form_a_union_backplate(self) -> None:
        review_path = add_visual_review(self.article)

        def add_split_backplate(properties: dict[str, Any]) -> None:
            image = next(
                node for node in properties["nodes"] if node.get("kind") == "illustration"
            )
            bounds = image["bounds"]
            half_width = bounds["width"] / 2
            for index, x in enumerate((bounds["x"], bounds["x"] + half_width), 1):
                properties["nodes"].append(
                    {
                        "node_id": f"80:1:split-backplate-{index}",
                        "kind": "closed-shape",
                        "fill_alpha": 1,
                        "stroke_width_px": 0,
                        "bounds": {
                            "x": x,
                            "y": bounds["y"],
                            "width": half_width,
                            "height": bounds["height"],
                        },
                    }
                )

        self._mutate_micro_node_evidence(review_path, 0, add_split_backplate)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertIn(
            "micro.component.image_backplate",
            report["visual_review"]["micro_component_layout"]["error_codes"],
        )

    def test_source_zero_declaration_is_a_compile_gate(self) -> None:
        add_visual_review(self.article)
        organization = json.loads((self.pack / "organization.json").read_text(encoding="utf-8"))
        organization["provenance"].pop("isolation_reviewed_at")
        write_json(self.pack / "organization.json", organization)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("isolation_reviewed_at" in item for item in report["errors"]))

    def test_generated_art_cannot_pose_as_gallery_evidence(self) -> None:
        add_visual_review(self.article)
        article = json.loads(self.article.read_text(encoding="utf-8"))
        article["blocks"][2] = {
            "type": "gallery",
            "images": [{"src": "background.master", "alt": "claimed event evidence"}],
        }
        write_json(self.article, article)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("documentary photo" in item for item in report["errors"]))


if __name__ == "__main__":
    unittest.main()

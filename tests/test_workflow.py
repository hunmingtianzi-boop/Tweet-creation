from __future__ import annotations

import binascii
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from asset_quality import file_sha256, validate_micro_asset  # noqa: E402
from build_ardot_manifest import build_manifest  # noqa: E402
from build_storyboard import build_storyboard_plan  # noqa: E402
from build_visual_directions import build_directions  # noqa: E402
from build_visual_kit import build_visual_kit_plan  # noqa: E402
from compile_wechat import compile_article  # noqa: E402
from orgs import command_init, scaffold, validate_pack, write_json  # noqa: E402


ROLES = (
    ("floating-spot", "spot.opening", 256, 256, "anchor", "opening", "第一步从一个真实问题开始。"),
    ("section-transition", "visual.transition", 512, 128, "connector", "identity", "不同能力沿同一条路径汇合。"),
    ("inline-explainer", "visual.explainer", 320, 240, "motion", "evidence", "原型在四个动作之间逐步完成。"),
    ("closing-motif", "spot.closing", 256, 256, "punctuation", "join", "把已经完成的原型交给下一位伙伴。"),
)


def write_png(path: Path, width: int, height: int, *, alpha: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    color_type = 6 if alpha else 2
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            row.extend((30, 100, 180))
            if alpha:
                border = min(x, y, width - 1 - x, height - 1 - y)
                row.append(0 if border < 8 else 255)
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
            "copy_safe_zone": "center 68% remains near-solid",
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
        write_png(asset_path, width, height)
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
                    "sha256": inspection["sha256"],
                    "width_px": width,
                    "height_px": height,
                    "transparent_pixel_ratio": inspection["transparent_pixel_ratio"],
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


def make_article(root: Path, pack: Path) -> Path:
    mode = json.loads((pack / "ardot.json").read_text(encoding="utf-8"))["variable_mode"]
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
    article = {
        "schema_version": 1,
        "article_id": "fresh-article",
        "organization_id": "fresh-organization",
        "article_type": "introduction",
        "title": "Fresh article",
        "storyboard": {"status": "approved", "chapters": chapters},
        "visual_kit": {"status": "approved", "assets": visual_assets},
        "blocks": blocks,
    }
    article_path = root / "article.json"
    write_json(article_path, article)
    return article_path


def add_visual_review(article_path: Path) -> Path:
    article = json.loads(article_path.read_text(encoding="utf-8"))
    qa = article_path.parent / "qa"
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
            }
        )
    review = {
        "schema_version": 2,
        "article_id": article["article_id"],
        "organization_id": article["organization_id"],
        "ardot": {"file_url": "https://ardot.example/fresh", "page_id": "0:1", "article_node_id": "30:0"},
        "capture": {
            "source": "ardot-node-export",
            "captured_at": "2026-08-27T10:00:00+08:00",
            "article_root_node_id": "30:0",
        },
        "screenshots": screenshots,
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
        for filename, value in scaffold("new-org", "新组织").items():
            write_json(pack / filename, value)
        directions = build_directions(pack, "introduction")
        self.assertFalse(directions["full_article_allowed"])
        self.assertEqual(directions["source_isolation"]["policy"], "source-zero")
        self.assertTrue(any("visual_input_source_ids" in item for item in directions["blocking_reasons"]))

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

    def test_opaque_micro_asset_fails_pixel_alpha_check(self) -> None:
        opaque = self.pack / "assets" / "generated" / "opaque.png"
        write_png(opaque, 256, 256, alpha=False)
        report = validate_micro_asset(opaque, "floating-spot")
        self.assertFalse(report["ok"])
        self.assertTrue(any("alpha" in item.lower() for item in report["errors"]))


class VisualKitTests(FreshWorkflowTestCase):
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
        plan = build_visual_kit_plan(self.article, self.pack)
        self.assertFalse(plan["ready_for_layout"])
        self.assertTrue(any("quality evidence" in item for item in plan["semantic_errors"]))

    def test_visual_directions_have_five_source_zero_calibration_samples(self) -> None:
        plan = build_directions(self.pack, "introduction")
        self.assertEqual(len(plan["directions"]), 2)
        self.assertTrue(all(len(item["calibration_strip"]) == 5 for item in plan["directions"]))
        serialized = json.dumps(plan, ensure_ascii=False)
        self.assertIn("prior article layouts", serialized)
        self.assertIn("background_family_trial", serialized)

    def test_storyboard_density_intent_is_mandatory(self) -> None:
        article = json.loads(self.article.read_text(encoding="utf-8"))
        article["storyboard"]["chapters"][1].pop("density_intent")
        write_json(self.article, article)
        report = build_storyboard_plan(self.article)
        self.assertFalse(report["ready_for_visual_kit"])


class ArdotAndCompilerTests(FreshWorkflowTestCase):
    def test_manifest_is_native_dense_and_open(self) -> None:
        manifest = build_manifest(self.article, self.pack)
        self.assertTrue(manifest["qa"]["ready_for_layout"])
        self.assertEqual(manifest["handoff"]["source_of_truth"], "ardot-native")
        self.assertEqual(manifest["qa"]["layout_policy"]["minimum_unique_generated_micro_assets"], 4)
        self.assertTrue(all(block["container_policy"] == "open-by-default" for block in manifest["blocks"]))

    def test_compile_passes_only_with_hashed_390px_ardot_evidence(self) -> None:
        add_visual_review(self.article)
        report = compile_article(self.article, self.pack, self.root / "output", check=True)
        self.assertTrue(report["ok"], report["errors"])
        self.assertTrue((self.root / "output" / "wechat.html").exists())

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

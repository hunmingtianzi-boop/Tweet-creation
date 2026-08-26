from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from compile_wechat import compile_article  # noqa: E402
from build_ardot_manifest import build_manifest  # noqa: E402
from build_visual_kit import build_visual_kit_plan  # noqa: E402
from build_storyboard import build_storyboard_plan  # noqa: E402
from build_visual_directions import build_directions  # noqa: E402
from orgs import (  # noqa: E402
    build_asset_plan,
    command_init,
    command_register_asset,
    scaffold,
    validate_pack,
    write_json,
)


class OrganizationPackTests(unittest.TestCase):
    def test_bundled_packs_validate(self) -> None:
        for pack in sorted((ROOT / "organizations").iterdir()):
            if not pack.is_dir():
                continue
            with self.subTest(pack=pack.name):
                report = validate_pack(pack)
                self.assertTrue(report["ok"], report["errors"])

    def test_scaffold_is_structurally_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pack = Path(temp) / "example-org"
            pack.mkdir()
            for filename, value in scaffold("example-org", "示例组织").items():
                write_json(pack / filename, value)
            report = validate_pack(pack)
            self.assertTrue(report["ok"], report["errors"])
            self.assertEqual(report["status"], "provisional")

    def test_init_creates_asset_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            args = type(
                "Args",
                (),
                {"organization_id": "example-org", "name": "示例组织", "root": Path(temp)},
            )()
            command_init(args)
            pack = Path(temp) / "example-org"
            for folder in ("official", "photos", "generated", "derived"):
                self.assertTrue((pack / "assets" / folder).is_dir())
            ardot = json.loads((pack / "ardot.json").read_text(encoding="utf-8"))
            self.assertEqual(ardot["status"], "not-linked")
            self.assertEqual(ardot["variable_mode"], "example-org")

    def test_asset_plan_uses_organization_route_and_asset_boundaries(self) -> None:
        recruitment = build_asset_plan(
            ROOT / "organizations" / "zju-ocean-robot-association", "recruitment"
        )
        technical = build_asset_plan(
            ROOT / "organizations" / "zju-ocean-robot-association", "popular-science"
        )
        self.assertEqual(recruitment["route"]["id"], "hands-on-community")
        self.assertEqual(technical["route"]["id"], "light-engineering")
        self.assertNotEqual(
            recruitment["slots"][0]["prompt_blueprint"],
            technical["slots"][0]["prompt_blueprint"],
        )
        logo = next(slot for slot in recruitment["slots"] if slot["id"] == "brand.logo")
        self.assertEqual(logo["status"], "reuse-available")
        micro_slots = [slot for slot in recruitment["slots"] if slot["micro_component"]]
        self.assertEqual(len(micro_slots), 4)
        self.assertTrue(all(slot["status"] == "generate-required" for slot in micro_slots))
        self.assertTrue(all("no rectangular panel" in slot["prompt_blueprint"] for slot in micro_slots))

    def test_register_asset_updates_registry_and_preserves_identity_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            init_args = type(
                "InitArgs",
                (),
                {"organization_id": "example-org", "name": "示例组织", "root": root},
            )()
            command_init(init_args)
            pack = root / "example-org"
            asset = pack / "assets" / "generated" / "hero.png"
            asset.write_bytes(b"test image placeholder")
            register_args = type(
                "RegisterArgs",
                (),
                {
                    "pack": pack,
                    "asset_id": "visual.hero",
                    "kind": "background",
                    "title": "Hero background",
                    "location": "assets/generated/hero.png",
                    "origin": "generated-illustrative",
                    "style": "provisional-editorial",
                    "use": ["introduction"],
                    "source_id": None,
                },
            )()
            command_register_asset(register_args)
            document = json.loads((pack / "assets.json").read_text(encoding="utf-8"))
            self.assertEqual(document["assets"][0]["id"], "visual.hero")
            self.assertTrue(validate_pack(pack)["ok"])

            unsafe_logo_args = type(
                "UnsafeLogoArgs",
                (),
                {
                    **register_args.__dict__,
                    "asset_id": "brand.logo",
                    "kind": "logo",
                    "origin": "generated-illustrative",
                },
            )()
            with self.assertRaises(SystemExit):
                command_register_asset(unsafe_logo_args)


class CompilerTests(unittest.TestCase):
    def test_bundled_examples_compile(self) -> None:
        cases = (
            ("ocean-recruitment.json", "zju-ocean-robot-association"),
        )
        with tempfile.TemporaryDirectory() as temp:
            for article_name, org_id in cases:
                with self.subTest(article=article_name):
                    output = Path(temp) / article_name.removesuffix(".json")
                    report = compile_article(
                        ROOT / "examples" / article_name,
                        ROOT / "organizations" / org_id,
                        output,
                        check=True,
                    )
                    self.assertTrue(report["ok"], report["errors"])
                    self.assertTrue((output / "index.html").exists())
                    fragment = (output / "wechat.html").read_text(encoding="utf-8")
                    self.assertNotIn("<script", fragment.lower())
                    self.assertNotIn("<style", fragment.lower())
                    self.assertEqual(report["article"]["organization_id"], org_id)
                    self.assertTrue(report["visual_kit"]["ready"])
                    self.assertTrue(report["visual_review"]["ready"])

    def test_failed_ardot_screenshot_review_blocks_final_check(self) -> None:
        org_id = "zju-ocean-robot-association"
        source = json.loads(
            (ROOT / "examples" / "ocean-recruitment.json").read_text(encoding="utf-8")
        )
        review = json.loads(
            (ROOT / "examples" / "ocean-recruitment-visual-review.json").read_text(encoding="utf-8")
        )
        review["checks"]["editorial_rhythm"] = "fail"
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            spec = temp_path / "article.json"
            review_path = temp_path / "visual-review.json"
            source["visual_review_file"] = str(review_path)
            spec.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            review_path.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
            report = compile_article(
                spec,
                ROOT / "organizations" / org_id,
                temp_path / "output",
                check=True,
            )
            self.assertFalse(report["ok"])
            self.assertFalse(report["visual_review"]["ready"])
            self.assertTrue(any("editorial_rhythm" in error for error in report["errors"]))
            self.assertFalse((temp_path / "output" / "wechat.html").exists())
            self.assertIsNone(report["outputs"]["wechat"])

    def test_metric_without_source_fails_final_check(self) -> None:
        org_id = "zju-ocean-robot-association"
        article = {
            "schema_version": 1,
            "organization_id": org_id,
            "article_type": "project-update",
            "title": "Metric check",
            "blocks": [
                {"type": "hero", "title": "Metric check"},
                {"type": "metrics", "items": [{"value": "42", "label": "projects"}]},
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            spec = temp_path / "article.json"
            spec.write_text(json.dumps(article, ensure_ascii=False), encoding="utf-8")
            report = compile_article(
                spec,
                ROOT / "organizations" / org_id,
                temp_path / "output",
                check=True,
            )
            self.assertFalse(report["ok"])
            self.assertTrue(any("requires source_id" in error for error in report["errors"]))

    def test_placeholder_fails_final_check(self) -> None:
        org_id = "zju-ocean-robot-association"
        article = {
            "schema_version": 1,
            "organization_id": org_id,
            "article_type": "recruitment",
            "title": "待确认标题",
            "blocks": [{"type": "hero", "title": "待确认标题"}],
        }
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            spec = temp_path / "article.json"
            spec.write_text(json.dumps(article, ensure_ascii=False), encoding="utf-8")
            report = compile_article(
                spec,
                ROOT / "organizations" / org_id,
                temp_path / "output",
                check=True,
            )
            self.assertFalse(report["ok"])
            self.assertTrue(any("placeholders" in error for error in report["errors"]))


class ArdotManifestTests(unittest.TestCase):
    def test_ocean_example_builds_linked_ardot_assembly(self) -> None:
        ocean = build_manifest(
            ROOT / "examples" / "ocean-recruitment.json",
            ROOT / "organizations" / "zju-ocean-robot-association",
        )
        self.assertEqual(ocean["handoff"]["source_of_truth"], "ardot-native")
        self.assertEqual(ocean["design_target"]["variable_mode"], "Ocean")
        self.assertEqual(ocean["blocks"][0]["ardot_component"], "WeChat/Hero/ImageStage/Ocean")
        self.assertTrue(ocean["visual_kit"]["ready_for_layout"])
        self.assertTrue(ocean["calibration"]["ready"])
        self.assertTrue(ocean["storyboard"]["ready_for_visual_kit"])
        self.assertEqual(len(ocean["chapters"]), 5)
        self.assertTrue(ocean["qa"]["ready_for_layout"])
        self.assertEqual(ocean["qa"]["layout_policy"]["maximum_boxed_section_ratio"], 0.2)
        self.assertTrue(all(block["container_policy"] == "open-by-default" for block in ocean["blocks"]))
        self.assertFalse(ocean["qa"]["unresolved_assets"])

    def test_visual_kit_blocks_layout_until_micro_assets_are_recorded(self) -> None:
        source = json.loads(
            (ROOT / "examples" / "ocean-recruitment.json").read_text(encoding="utf-8")
        )
        source.pop("visual_kit")
        with tempfile.TemporaryDirectory() as temp:
            article = Path(temp) / "article.json"
            article.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            plan = build_visual_kit_plan(
                article,
                ROOT / "organizations" / "zju-ocean-robot-association",
            )
            self.assertFalse(plan["ready_for_layout"])
            self.assertEqual(set(plan["missing_roles"]), {
                "floating-spot",
                "section-transition",
                "inline-explainer",
                "closing-motif",
            })

    def test_visual_prompts_are_chapter_grounded_not_article_dumps(self) -> None:
        article = ROOT / "examples" / "ocean-recruitment.json"
        plan = build_visual_kit_plan(
            article, ROOT / "organizations" / "zju-ocean-robot-association"
        )
        self.assertTrue(plan["ready_for_layout"], plan["blocking_reasons"])
        self.assertFalse(plan["semantic_errors"])
        self.assertGreaterEqual(
            len({slot["composition_role"] for slot in plan["slots"]}), 3
        )
        for slot in plan["slots"]:
            self.assertIn(slot["concrete_subject"], slot["prompt"])
            self.assertIn(slot["source_text"], slot["prompt"])
            self.assertLess(len(slot["prompt"]), 1400)

    def test_generic_ai_subject_cannot_unlock_visual_layout(self) -> None:
        source = json.loads(
            (ROOT / "examples" / "ocean-recruitment.json").read_text(encoding="utf-8")
        )
        source["visual_kit"]["assets"][0]["concrete_subject"] = "AI装饰"
        with tempfile.TemporaryDirectory() as temp:
            article = Path(temp) / "article.json"
            article.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            plan = build_visual_kit_plan(
                article, ROOT / "organizations" / "zju-ocean-robot-association"
            )
            self.assertFalse(plan["ready_for_layout"])
            self.assertTrue(any("concrete_subject" in item for item in plan["semantic_errors"]))

    def test_storyboard_and_visual_directions_are_explicit_gates(self) -> None:
        org = ROOT / "organizations" / "zju-ocean-robot-association"
        storyboard = build_storyboard_plan(ROOT / "examples" / "ocean-recruitment.json")
        directions = build_directions(org, "recruitment")
        self.assertTrue(storyboard["ready_for_visual_kit"], storyboard["errors"])
        self.assertGreaterEqual(storyboard["composition_count"], 3)
        self.assertGreaterEqual(len(directions["directions"]), 2)
        self.assertTrue(directions["full_article_allowed"])

    def test_provisional_org_is_blocked_before_full_article(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pack = Path(temp) / "example-org"
            pack.mkdir()
            for filename, value in scaffold("example-org", "示例组织").items():
                write_json(pack / filename, value)
            directions = build_directions(pack, "introduction")
            self.assertFalse(directions["full_article_allowed"])
            self.assertTrue(any("provisional" in item for item in directions["blocking_reasons"]))


if __name__ == "__main__":
    unittest.main()

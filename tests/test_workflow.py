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
        ocean = build_asset_plan(
            ROOT / "organizations" / "zju-ocean-robot-association", "recruitment"
        )
        tuozhe = build_asset_plan(
            ROOT / "organizations" / "tuozhe-ai-ecosystem", "tutorial"
        )
        self.assertEqual(ocean["route"]["id"], "hands-on-community")
        self.assertEqual(tuozhe["route"]["id"], "technical-editorial")
        self.assertNotEqual(
            ocean["slots"][0]["prompt_blueprint"],
            tuozhe["slots"][0]["prompt_blueprint"],
        )
        ocean_logo = next(slot for slot in ocean["slots"] if slot["id"] == "brand.logo")
        tuozhe_logo = next(slot for slot in tuozhe["slots"] if slot["id"] == "brand.logo")
        self.assertEqual(ocean_logo["status"], "reuse-available")
        self.assertEqual(tuozhe_logo["status"], "user-or-official-asset-required")

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
            ("tuozhe-tutorial.json", "tuozhe-ai-ecosystem"),
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

    def test_metric_without_source_fails_final_check(self) -> None:
        org_id = "tuozhe-ai-ecosystem"
        article = {
            "schema_version": 1,
            "organization_id": org_id,
            "article_type": "project-showcase",
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
        org_id = "tuozhe-ai-ecosystem"
        article = {
            "schema_version": 1,
            "organization_id": org_id,
            "article_type": "tutorial",
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
    def test_examples_build_distinct_ardot_assemblies(self) -> None:
        ocean = build_manifest(
            ROOT / "examples" / "ocean-recruitment.json",
            ROOT / "organizations" / "zju-ocean-robot-association",
        )
        tuozhe = build_manifest(
            ROOT / "examples" / "tuozhe-tutorial.json",
            ROOT / "organizations" / "tuozhe-ai-ecosystem",
        )
        self.assertEqual(ocean["handoff"]["source_of_truth"], "ardot-native")
        self.assertEqual(ocean["design_target"]["variable_mode"], "Ocean")
        self.assertEqual(tuozhe["design_target"]["variable_mode"], "Tuozhe")
        self.assertNotEqual(ocean["variables"]["Ink"], tuozhe["variables"]["Ink"])
        self.assertEqual(ocean["blocks"][0]["ardot_component"], "WeChat/Hero/ImageStage/Ocean")
        self.assertEqual(tuozhe["blocks"][0]["ardot_component"], "WeChat/Hero/PosterStage/Tuozhe")
        self.assertFalse(ocean["qa"]["unresolved_assets"])
        self.assertFalse(tuozhe["qa"]["unresolved_assets"])


if __name__ == "__main__":
    unittest.main()

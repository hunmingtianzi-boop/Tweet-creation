from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from asset_quality import validate_micro_asset  # noqa: E402
from orgs import command_register_asset, validate_cutout_derivation_report  # noqa: E402
from prepare_micro_cutout import (  # noqa: E402
    CutoutPreparationError,
    prepare_micro_cutout,
)


PROMPT_SHA = "sha256:" + "a" * 64
ROUTE = "chatgpt-web/codex-with-chatgpt"
KEY = (255, 0, 255)
ARTICLE_ID = "current-article"
ASSET_SLOT_ID = "kit.floating-spot"


def write_controlled_source(path: Path, *, touch_edge: bool = False, antialias: bool = True) -> None:
    width = height = 512
    scale = 4 if antialias else 1
    large_size = (width * scale, height * scale)
    foreground = Image.new("RGB", large_size)
    pixels = foreground.load()
    for y in range(large_size[1]):
        for x in range(large_size[0]):
            pixels[x, y] = (
                25 + ((x * 7 + y * 3) % 135),
                80 + ((x * 3 + y * 11) % 150),
                20 + ((x * 13 + y * 5) % 140),
            )
    mask = Image.new("L", large_size, 0)
    draw = ImageDraw.Draw(mask)
    left = -20 if touch_edge else 62 * scale
    draw.ellipse((left, 70 * scale, 445 * scale, 438 * scale), fill=255)
    draw.polygon(
        (
            (105 * scale, 150 * scale),
            ((0 if touch_edge else 35) * scale, 250 * scale),
            (142 * scale, 292 * scale),
        ),
        fill=255,
    )
    if antialias:
        mask = mask.resize((width, height), Image.Resampling.LANCZOS)
        foreground = foreground.resize((width, height), Image.Resampling.LANCZOS)
    background = Image.new("RGB", (width, height), KEY)
    background.paste(foreground, mask=mask)
    path.parent.mkdir(parents=True, exist_ok=True)
    background.save(path)


def write_native_rgba(path: Path) -> None:
    image = Image.new("RGBA", (360, 360), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((48, 42, 304, 318), fill=(42, 126, 184, 255))
    draw.ellipse((154, 106, 330, 284), fill=(228, 132, 52, 255))
    draw.polygon(((82, 94), (24, 158), (116, 176)), fill=(54, 154, 112, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


class PrepareMicroCutoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _paths(self, stem: str = "micro") -> tuple[Path, Path, Path]:
        source = self.root / "assets" / "generated" / f"{stem}-source.png"
        output = self.root / "assets" / "derived" / f"{stem}.png"
        report = self.root / "assets" / "derived" / f"{stem}-cutout.json"
        return source, output, report

    def _prepare(self, stem: str = "micro") -> tuple[dict, Path, Path, Path]:
        source, output, report = self._paths(stem)
        write_controlled_source(source)
        result = prepare_micro_cutout(
            source,
            output,
            report,
            role="floating-spot",
            article_id=ARTICLE_ID,
            asset_slot_id=ASSET_SLOT_ID,
            prompt_sha256=PROMPT_SHA,
            generation_route=ROUTE,
            key_color="#FF00FF",
        )
        return result, source, output, report

    def test_controlled_rgb_source_becomes_canonical_rgba_with_lineage(self) -> None:
        result, source, output, report = self._prepare()

        self.assertTrue(output.is_file())
        self.assertTrue(report.is_file())
        self.assertEqual(result["kind"], "org-wechat-micro-cutout-derivation-v1")
        self.assertEqual(result["processor"]["method"], "border-connected-chroma-matting-v1")
        self.assertEqual(result["generation"]["prompt_sha256"], PROMPT_SHA)
        self.assertEqual(result["generation"]["route"], ROUTE)
        self.assertTrue(result["generation"]["alpha_was_not_assumed"])
        self.assertTrue(result["background_assessment"]["source_background_removable"])
        self.assertEqual(result["output"]["mode"], "RGBA8")
        self.assertTrue(result["output"]["transparent_rgb_zeroed"])
        self.assertTrue(result["final_validation"]["ok"])
        self.assertTrue(validate_micro_asset(output, "floating-spot")["ok"])
        with Image.open(output) as image:
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.info, {})
            pixels = image.load()
            for x in range(image.width):
                self.assertEqual(pixels[x, 0][3], 0)
                self.assertEqual(pixels[x, image.height - 1][3], 0)
            for y in range(image.height):
                self.assertEqual(pixels[0, y][3], 0)
                self.assertEqual(pixels[image.width - 1, y][3], 0)
            self.assertTrue(
                all(pixel[:3] == (0, 0, 0) for pixel in image.getdata() if pixel[3] == 0)
            )
        self.assertNotEqual(source.read_bytes(), output.read_bytes())

    def test_same_source_and_config_produce_identical_png_bytes(self) -> None:
        first, source, first_output, _ = self._prepare("first")
        second_output = self.root / "assets" / "derived" / "second.png"
        second_report = self.root / "assets" / "derived" / "second.json"
        second = prepare_micro_cutout(
            source,
            second_output,
            second_report,
            role="floating-spot",
            article_id=ARTICLE_ID,
            asset_slot_id=ASSET_SLOT_ID,
            prompt_sha256=PROMPT_SHA,
            generation_route=ROUTE,
            key_color="#FF00FF",
        )

        self.assertEqual(first_output.read_bytes(), second_output.read_bytes())
        self.assertEqual(first["output"]["file_sha256"], second["output"]["file_sha256"])
        self.assertEqual(first["processor"]["config_sha256"], second["processor"]["config_sha256"])

    def test_native_rgba_must_pass_gate_then_is_tightly_normalized(self) -> None:
        source, output, report = self._paths("native")
        write_native_rgba(source)
        result = prepare_micro_cutout(
            source,
            output,
            report,
            role="floating-spot",
            article_id=ARTICLE_ID,
            asset_slot_id=ASSET_SLOT_ID,
            prompt_sha256=PROMPT_SHA,
            generation_route=ROUTE,
        )

        self.assertEqual(result["processor"]["method"], "native-rgba-normalize-v1")
        self.assertTrue(result["background_assessment"]["native_alpha_accepted"])
        self.assertTrue(validate_micro_asset(output, "floating-spot")["ok"])

    def test_nonuniform_background_and_touching_subject_fail_without_outputs(self) -> None:
        source, output, report = self._paths("gradient")
        image = Image.new("RGB", (512, 512))
        pixels = image.load()
        for y in range(512):
            for x in range(512):
                pixels[x, y] = (255, min(150, x // 3), max(105, 255 - y // 3))
        source.parent.mkdir(parents=True, exist_ok=True)
        image.save(source)
        with self.assertRaises(CutoutPreparationError) as failure:
            prepare_micro_cutout(
                source,
                output,
                report,
                role="floating-spot",
                article_id=ARTICLE_ID,
                asset_slot_id=ASSET_SLOT_ID,
                prompt_sha256=PROMPT_SHA,
                generation_route=ROUTE,
            )
        self.assertEqual(failure.exception.code, "cutout.source.background_not_uniform")
        self.assertFalse(output.exists())
        self.assertFalse(report.exists())

        source, output, report = self._paths("touching")
        write_controlled_source(source, touch_edge=True)
        with self.assertRaises(CutoutPreparationError) as failure:
            prepare_micro_cutout(
                source,
                output,
                report,
                role="floating-spot",
                article_id=ARTICLE_ID,
                asset_slot_id=ASSET_SLOT_ID,
                prompt_sha256=PROMPT_SHA,
                generation_route=ROUTE,
            )
        self.assertEqual(failure.exception.code, "cutout.source.background_not_uniform")
        self.assertFalse(output.exists())
        self.assertFalse(report.exists())

    def test_complex_ambiguous_transparency_fails_and_regenerates(self) -> None:
        source, output, report = self._paths("ambiguous")
        image = Image.new("RGB", (512, 512), KEY)
        ImageDraw.Draw(image).rectangle((70, 70, 442, 442), fill=(220, 25, 235))
        source.parent.mkdir(parents=True, exist_ok=True)
        image.save(source)
        with self.assertRaises(CutoutPreparationError) as failure:
            prepare_micro_cutout(
                source,
                output,
                report,
                role="floating-spot",
                article_id=ARTICLE_ID,
                asset_slot_id=ASSET_SLOT_ID,
                prompt_sha256=PROMPT_SHA,
                generation_route=ROUTE,
            )
        self.assertIn(
            failure.exception.code,
            {"cutout.source.complex_transparency", "cutout.output.quality_failed"},
        )
        self.assertFalse(output.exists())
        self.assertFalse(report.exists())

    def test_outputs_are_create_once_and_symlink_sources_are_rejected(self) -> None:
        _, source, output, report = self._prepare("once")
        with self.assertRaises(CutoutPreparationError) as failure:
            prepare_micro_cutout(
                source,
                output,
                report,
                role="floating-spot",
                article_id=ARTICLE_ID,
                asset_slot_id=ASSET_SLOT_ID,
                prompt_sha256=PROMPT_SHA,
                generation_route=ROUTE,
            )
        self.assertEqual(failure.exception.code, "cutout.output.create_once")

        link = self.root / "linked-source.png"
        link.symlink_to(source)
        with self.assertRaises(CutoutPreparationError) as failure:
            prepare_micro_cutout(
                link,
                self.root / "linked-output.png",
                self.root / "linked-report.json",
                role="floating-spot",
                article_id=ARTICLE_ID,
                asset_slot_id=ASSET_SLOT_ID,
                prompt_sha256=PROMPT_SHA,
                generation_route=ROUTE,
            )
        self.assertEqual(failure.exception.code, "cutout.path.symlink_forbidden")

    def test_report_verifier_binds_source_output_config_and_current_inspection(self) -> None:
        _, source, output, report = self._prepare("verify")
        verification = validate_cutout_derivation_report(
            self.root, report, output, "floating-spot"
        )
        self.assertTrue(verification["ok"], verification["errors"])
        self.assertEqual(verification["lineage"]["source_location"], source.relative_to(self.root).as_posix())

        payload = json.loads(report.read_text(encoding="utf-8"))
        payload["processor"]["config"]["soft_distance_rgb"] = 61.0
        report.write_text(json.dumps(payload), encoding="utf-8")
        tampered = validate_cutout_derivation_report(
            self.root, report, output, "floating-spot"
        )
        self.assertFalse(tampered["ok"])
        self.assertTrue(any("config SHA-256" in error for error in tampered["errors"]))

    def test_report_verifier_recomputes_pixel_processor_and_probe_evidence(self) -> None:
        tamper_cases = (
            ("source-pixel", ("source", "pixel_sha256"), "sha256:" + "b" * 64, "source pixel_sha256"),
            ("output-pixel", ("output", "pixel_sha256"), "sha256:" + "b" * 64, "output pixel_sha256"),
            ("processor", ("processor", "script_sha256"), "sha256:" + "b" * 64, "processor script binding"),
            ("probe", ("composite_probes", 0, "pixel_sha256"), "sha256:" + "b" * 64, "composite probe"),
        )
        for stem, path, replacement, expected_error in tamper_cases:
            with self.subTest(stem=stem):
                _, _, output, report = self._prepare(stem)
                payload = json.loads(report.read_text(encoding="utf-8"))
                target: object = payload
                for component in path[:-1]:
                    target = target[component]  # type: ignore[index]
                target[path[-1]] = replacement  # type: ignore[index]
                report.write_text(json.dumps(payload), encoding="utf-8")
                verification = validate_cutout_derivation_report(
                    self.root, report, output, "floating-spot"
                )
                self.assertFalse(verification["ok"])
                self.assertTrue(
                    any(expected_error in error for error in verification["errors"]),
                    verification["errors"],
                )

    def test_new_micro_registration_requires_derived_lineage(self) -> None:
        _, _, output, report = self._prepare("registered")
        (self.root / "assets.json").write_text(
            json.dumps({"schema_version": 1, "organization_id": "test", "assets": []}),
            encoding="utf-8",
        )
        base = {
            "pack": self.root,
            "asset_id": "micro.registered",
            "kind": "illustration",
            "title": "Registered micro",
            "location": output.relative_to(self.root).as_posix(),
            "origin": "derived",
            "style": "article-specific",
            "use": ["introduction"],
            "role": ["floating-spot"],
            "generated_for": ["current-article"],
            "source_id": None,
            "visual_role": "article-micro",
            "background_family_id": None,
            "background_variant": None,
            "watermark_source": None,
            "watermark_report": None,
            "cutout_report": report.relative_to(self.root),
        }
        with mock.patch(
            "orgs.validate_pack",
            return_value={"ok": True, "errors": [], "warnings": []},
        ):
            command_register_asset(type("Args", (), base)())
        registered = json.loads((self.root / "assets.json").read_text(encoding="utf-8"))["assets"][0]
        self.assertEqual(registered["origin"], "derived")
        self.assertEqual(registered["cutout"]["report_location"], report.relative_to(self.root).as_posix())
        self.assertEqual(registered["cutout"]["output_sha256"], "sha256:" + registered["quality"]["sha256"])

        legacy = dict(base)
        legacy["asset_id"] = "micro.legacy-new"
        legacy["origin"] = "generated-illustrative"
        with self.assertRaisesRegex(SystemExit, "origin=derived"):
            command_register_asset(type("Args", (), legacy)())


if __name__ == "__main__":
    unittest.main()

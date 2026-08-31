from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from asset_quality import validate_micro_asset  # noqa: E402


class CutoutGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _save(self, name: str, image: Image.Image) -> Path:
        path = self.root / name
        image.save(path)
        return path

    def test_organic_rgba_cutout_passes_and_ignores_fly_pixel(self) -> None:
        image = Image.new("RGBA", (320, 320), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((54, 46, 270, 276), fill=(42, 126, 184, 255))
        draw.ellipse((142, 112, 292, 252), fill=(228, 132, 52, 255))
        draw.polygon(((76, 82), (30, 132), (104, 152)), fill=(54, 154, 112, 255))
        # This isolated low-alpha generator artifact must not expand the cutout bbox.
        image.putpixel((1, 1), (255, 255, 255, 8))
        report = validate_micro_asset(self._save("organic.png", image), "floating-spot")

        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["inspection"]["alpha_visible_bbox"]["x"], 30)
        self.assertGreater(report["inspection"]["alpha_padding_ratio"]["left"], 0.08)
        self.assertEqual(report["inspection"]["alpha_raw_visible_bbox"]["x"], 1)

    def test_oversized_transparent_canvas_fails(self) -> None:
        image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((205, 205, 310, 310), fill=(42, 126, 184, 255))
        # Projection-only geometry can be fooled by supported pixels near every
        # corner. The largest connected subject must still be judged as tiny.
        for bounds in (
            (5, 5, 10, 10),
            (501, 5, 506, 10),
            (5, 501, 10, 506),
            (501, 501, 506, 506),
        ):
            draw.rectangle(bounds, fill=(255, 255, 255, 32))
        report = validate_micro_asset(self._save("oversized.png", image), "floating-spot")

        self.assertFalse(report["ok"])
        self.assertIn("micro.asset.oversized_transparent_canvas", report["error_codes"])

    def test_rectangular_and_rounded_white_mattes_fail(self) -> None:
        rectangle = Image.new("RGBA", (320, 320), (0, 0, 0, 0))
        ImageDraw.Draw(rectangle).rectangle((18, 18, 301, 301), fill=(64, 120, 168, 255))
        rectangular_report = validate_micro_asset(
            self._save("rectangle.png", rectangle), "floating-spot"
        )
        self.assertIn("micro.asset.rectangular_alpha_tile", rectangular_report["error_codes"])

        rounded = Image.new("RGBA", (320, 320), (0, 0, 0, 0))
        ImageDraw.Draw(rounded).rounded_rectangle(
            (18, 18, 301, 301), radius=56, fill=(255, 255, 255, 255)
        )
        rounded_report = validate_micro_asset(self._save("rounded.png", rounded), "floating-spot")
        self.assertFalse(rounded_report["ok"])
        self.assertIn("micro.asset.white_matte", rounded_report["error_codes"])

    def test_colored_and_black_elliptical_mattes_fail(self) -> None:
        for name, color in (
            ("colored-matte.png", (118, 42, 190, 255)),
            ("black-matte.png", (0, 0, 0, 255)),
        ):
            image = Image.new("RGBA", (320, 320), (0, 0, 0, 0))
            ImageDraw.Draw(image).ellipse((18, 18, 301, 301), fill=color)
            report = validate_micro_asset(self._save(name, image), "floating-spot")
            self.assertFalse(report["ok"], name)
            self.assertIn("micro.asset.solid_color_matte", report["error_codes"])

    def test_semitransparent_white_and_black_edge_halos_fail(self) -> None:
        for name, halo_color, expected_code in (
            ("white-halo.png", (255, 255, 255, 80), "micro.asset.white_halo"),
            ("black-halo.png", (0, 0, 0, 80), "micro.asset.black_halo"),
        ):
            image = Image.new("RGBA", (320, 320), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.ellipse((38, 38, 282, 282), fill=halo_color)
            draw.ellipse((54, 54, 266, 266), fill=(42, 126, 184, 255))
            draw.ellipse((132, 98, 248, 226), fill=(228, 132, 52, 255))
            report = validate_micro_asset(self._save(name, image), "floating-spot")
            self.assertFalse(report["ok"], name)
            self.assertIn(expected_code, report["error_codes"])

    def test_subject_touching_canvas_edge_fails_as_clipped(self) -> None:
        image = Image.new("RGBA", (320, 320), (0, 0, 0, 0))
        ImageDraw.Draw(image).ellipse((-18, 52, 276, 288), fill=(42, 126, 184, 255))
        report = validate_micro_asset(self._save("clipped.png", image), "floating-spot")

        self.assertFalse(report["ok"])
        self.assertIn("micro.asset.clipped_subject", report["error_codes"])


if __name__ == "__main__":
    unittest.main()

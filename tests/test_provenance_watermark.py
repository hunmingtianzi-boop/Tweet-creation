from __future__ import annotations

import hashlib
import binascii
import json
import math
import os
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from provenance_watermark import (  # noqa: E402
    ALGORITHM,
    CarrierRejectedError,
    VerificationError,
    WatermarkError,
    assess_carrier,
    detect_watermark,
    embed_watermark,
    file_sha256,
    measure_psnr,
    verify_transport_simulation,
)
import provenance_watermark as watermark_module  # noqa: E402


TEST_KEY = b"test-only-provenance-key-32bytes!"
WRONG_KEY = b"D" * 32
FIXED_WM_ID = bytes.fromhex("0011223344556677")
_RESAMPLING = getattr(Image, "Resampling", Image)


def write_textured_png(path: Path, width: int = 640, height: int = 800, *, rgba: bool = False) -> None:
    pixels: list[tuple[int, ...]] = []
    for y in range(height):
        for x in range(width):
            wave = int(19 * math.sin(x / 7.3) + 15 * math.cos(y / 10.1) + 9 * math.sin((x + y) / 4.7))
            grain = ((x * 37 + y * 61 + (x * y) % 29) % 23) - 11
            red = max(8, min(247, 78 + (x * 107 // width) + wave + grain))
            green = max(8, min(247, 56 + (y * 136 // height) - wave // 2 + grain))
            blue = max(8, min(247, 142 + ((x + y) * 57 // (width + height)) + wave // 3 - grain))
            pixels.append((red, green, blue, 255) if rgba else (red, green, blue))
    image = Image.new("RGBA" if rgba else "RGB", (width, height))
    image.putdata(pixels)
    image.save(path, format="PNG")


def write_header_only_png(path: Path, width: int, height: int) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = binascii.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b""))


class ProvenanceWatermarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls._temporary.name)
        cls.master = cls.root / "master.png"
        cls.derivative = cls.root / "master-watermarked.png"
        write_textured_png(cls.master)
        cls.pre_hash = file_sha256(cls.master)
        cls.report = embed_watermark(
            cls.master,
            cls.derivative,
            key=TEST_KEY,
            key_epoch=7,
            wm_id=FIXED_WM_ID,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def test_embed_preserves_master_and_public_report_is_private_safe(self) -> None:
        self.assertEqual(file_sha256(self.master), self.pre_hash)
        self.assertNotEqual(file_sha256(self.derivative), self.pre_hash)
        self.assertEqual(self.report["algorithm"], ALGORITHM)
        self.assertEqual(self.report["status"], "local_verified")
        self.assertTrue(self.report["local_verified"])
        self.assertTrue(self.report["detection"]["authenticated"])
        self.assertEqual(self.report["detection"]["status"], "payload_authenticated")
        self.assertNotIn("local_verified", self.report["detection"])
        self.assertEqual(self.report["payload_fingerprint"], self.report["detection"]["payload_fingerprint"])
        self.assertEqual(self.report["key_epoch"], 7)
        self.assertEqual(self.report["purpose"], 1)
        self.assertGreaterEqual(self.report["psnr_db"], 42.0)
        self.assertEqual(self.report["psnr_threshold_db"], 42.0)
        self.assertEqual(
            self.report["detection"]["input_sha256"],
            self.report["post_sha256"],
        )
        self.assertEqual(
            self.report["detection"]["input_bytes"],
            self.derivative.stat().st_size,
        )
        self.assertNotIn("confidence", self.report["detection"])
        self.assertIn("repeat_vote_agreement", self.report["detection"])
        simulation = self.report["transport_simulation"]
        self.assertEqual(simulation["status"], "payload_authenticated")
        self.assertTrue(simulation["payload_authenticated"])
        self.assertEqual(simulation["width"], 390)
        self.assertEqual(simulation["jpeg_quality"], 75)
        public_json = json.dumps(self.report, sort_keys=True)
        self.assertNotIn("wm_id", public_json)
        self.assertNotIn(FIXED_WM_ID.hex(), public_json)
        self.assertNotIn(TEST_KEY.decode("ascii"), public_json)

    def test_detects_after_metadata_strip_jpeg_q75_and_390px_resize(self) -> None:
        with Image.open(self.derivative) as opened:
            stripped_path = self.root / "transport-stripped.png"
            opened.convert("RGB").save(stripped_path, format="PNG", optimize=True)

            jpeg_only_path = self.root / "transport-q75.jpg"
            opened.convert("RGB").save(
                jpeg_only_path,
                format="JPEG",
                quality=75,
                subsampling=2,
            )

            resized = opened.convert("RGB").resize(
                (390, round(opened.height * 390 / opened.width)),
                _RESAMPLING.LANCZOS,
            )
            resized_path = self.root / "transport-390.png"
            resized.save(resized_path, format="PNG", optimize=True)

            jpeg_path = self.root / "transport-390-q75.jpg"
            resized.save(jpeg_path, format="JPEG", quality=75, subsampling=2)
        for candidate in (stripped_path, jpeg_only_path, resized_path, jpeg_path):
            with self.subTest(candidate=candidate.name):
                detected = detect_watermark(candidate, key=TEST_KEY)
                self.assertTrue(detected["authenticated"], detected)
                self.assertEqual(
                    detected["payload_fingerprint"],
                    self.report["payload_fingerprint"],
                )
                self.assertEqual(detected["key_epoch"], 7)

    def test_wrong_key_and_unwatermarked_carrier_are_negative(self) -> None:
        wrong = detect_watermark(self.derivative, key=WRONG_KEY)
        clean = detect_watermark(self.master, key=TEST_KEY)
        for report in (wrong, clean):
            self.assertEqual(report["status"], "not_detected")
            self.assertFalse(report["detected"])
            self.assertFalse(report["authenticated"])
            self.assertIsNone(report["payload_fingerprint"])
            self.assertIsNone(report["key_epoch"])
            self.assertNotIn("private_record", report)

    def test_raw_identifier_requires_explicit_private_record(self) -> None:
        private = detect_watermark(self.derivative, key=TEST_KEY, include_private_record=True)
        self.assertEqual(private["private_record"]["wm_id"], FIXED_WM_ID.hex())
        self.assertNotIn("wm_id", json.dumps({key: value for key, value in private.items() if key != "private_record"}))

    def test_cli_stdout_is_public_and_private_record_is_mode_0600(self) -> None:
        private_root = self.root / "private-store"
        private_root.mkdir()
        private_path = private_root / "private-record.json"
        environment = os.environ.copy()
        environment["TEST_WATERMARK_KEY"] = "base64:" + __import__("base64").b64encode(TEST_KEY).decode("ascii")
        environment["PROVENANCE_WATERMARK_PRIVATE_ROOT"] = str(private_root)
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "provenance_watermark.py"),
                "detect",
                str(self.derivative),
                "--key-env",
                "TEST_WATERMARK_KEY",
                "--private-record",
                str(private_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        stdout = json.loads(result.stdout)
        self.assertNotIn("private_record", stdout)
        self.assertNotIn("wm_id", result.stdout)
        private = json.loads(private_path.read_text(encoding="utf-8"))
        self.assertEqual(private["wm_id"], FIXED_WM_ID.hex())
        self.assertEqual(stat.S_IMODE(private_path.stat().st_mode), 0o600)

    def test_rgba_is_eligible_only_when_fully_opaque(self) -> None:
        opaque = self.root / "opaque-rgba.png"
        opaque_derivative = self.root / "opaque-rgba-watermarked.png"
        transparent = self.root / "transparent.png"
        write_textured_png(opaque, 400, 400, rgba=True)
        with Image.open(opaque) as opened:
            altered = opened.copy()
        altered.putpixel((20, 20), (*altered.getpixel((20, 20))[:3], 254))
        altered.save(transparent)
        self.assertTrue(assess_carrier(opaque)["eligible"])
        rgba_report = embed_watermark(
            opaque,
            opaque_derivative,
            key=TEST_KEY,
            key_epoch=8,
            wm_id=bytes.fromhex("ffeeddccbbaa9988"),
        )
        self.assertTrue(rgba_report["local_verified"])
        with Image.open(opaque_derivative) as derivative:
            self.assertEqual(derivative.mode, "RGBA")
            self.assertEqual(derivative.getchannel("A").getextrema(), (255, 255))
        rgba_detection = detect_watermark(opaque_derivative, key=TEST_KEY)
        self.assertEqual(rgba_detection["image"]["mode"], "RGBA")
        assessment = assess_carrier(transparent)
        self.assertFalse(assessment["eligible"])
        self.assertIn("transparent_pixels", assessment["reason_codes"])
        with self.assertRaises(CarrierRejectedError):
            embed_watermark(transparent, self.root / "transparent-watermarked.png", key=TEST_KEY)

    def test_small_smooth_and_source_overwrite_are_rejected(self) -> None:
        smooth = self.root / "smooth.png"
        Image.new("RGB", (500, 500), (90, 120, 160)).save(smooth)
        assessment = assess_carrier(smooth)
        self.assertFalse(assessment["eligible"])
        self.assertIn("insufficient_texture", assessment["reason_codes"])
        with self.assertRaises(CarrierRejectedError):
            embed_watermark(smooth, self.root / "smooth-watermarked.png", key=TEST_KEY)
        with self.assertRaises(WatermarkError):
            embed_watermark(self.master, self.master, key=TEST_KEY)

        oversized_embed = self.root / "embed-memory-limit.png"
        Image.new("RGB", (1501, 1000), (80, 110, 160)).save(oversized_embed)
        oversized_assessment = assess_carrier(oversized_embed)
        self.assertFalse(oversized_assessment["eligible"])
        self.assertIn(
            "carrier_too_large_for_embedding",
            oversized_assessment["reason_codes"],
        )

    def test_payload_fingerprint_is_one_way_and_stable(self) -> None:
        fingerprint = self.report["payload_fingerprint"]
        self.assertEqual(len(fingerprint), hashlib.sha256().digest_size * 2)
        self.assertNotEqual(fingerprint, FIXED_WM_ID.hex())
        redetected = detect_watermark(self.derivative, key=TEST_KEY)
        self.assertEqual(redetected["payload_fingerprint"], fingerprint)

    def test_psnr_below_threshold_fails_closed_without_output(self) -> None:
        rejected_output = self.root / "below-threshold-must-not-exist.png"
        with mock.patch.object(watermark_module, "MIN_PSNR_DB", 99.0):
            with self.assertRaises(VerificationError):
                embed_watermark(
                    self.master,
                    rejected_output,
                    key=TEST_KEY,
                    key_epoch=9,
                    wm_id=bytes.fromhex("1020304050607080"),
                )
        self.assertFalse(rejected_output.exists())

    def test_public_psnr_measurement_recomputes_report_value(self) -> None:
        measured = measure_psnr(self.master, self.derivative)
        self.assertAlmostEqual(measured, self.report["psnr_db"], places=4)

        wrong_size = self.root / "wrong-size.png"
        write_textured_png(wrong_size, 400, 400)
        with self.assertRaises(ValueError):
            measure_psnr(self.master, wrong_size)

        transparent = self.root / "psnr-transparent.png"
        with Image.open(self.derivative) as opened:
            rgba = opened.convert("RGBA")
        rgba.putpixel((0, 0), (*rgba.getpixel((0, 0))[:3], 0))
        rgba.save(transparent)
        with self.assertRaises(WatermarkError):
            measure_psnr(self.master, transparent)

    def test_transport_simulation_can_be_independently_recomputed(self) -> None:
        measured = verify_transport_simulation(self.derivative, key=TEST_KEY)
        self.assertEqual(measured, self.report["transport_simulation"])
        self.assertTrue(measured["payload_authenticated"])
        self.assertGreaterEqual(measured["repeat_vote_agreement"], 0.5)

    def test_reports_use_recursive_public_allowlists(self) -> None:
        self.assertEqual(set(self.report), set(watermark_module._EMBED_PUBLIC_SCHEMA))
        self.assertEqual(
            set(self.report["detection"]),
            set(watermark_module._DETECTION_PUBLIC_SCHEMA),
        )
        mutated = json.loads(json.dumps(self.report))
        mutated["unexpected_top_secret"] = "secret"
        mutated["carrier"]["unexpected_carrier_secret"] = "secret"
        mutated["detection"]["unexpected_detection_secret"] = "secret"
        mutated["detection"]["image"]["unexpected_image_secret"] = "secret"
        mutated["transport_simulation"]["unexpected_transport_secret"] = "secret"
        sanitized = watermark_module._strict_public_report(mutated)
        rendered = json.dumps(sanitized, sort_keys=True)
        self.assertNotIn("unexpected", rendered)
        self.assertNotIn("secret", rendered)
        non_finite = json.loads(json.dumps(self.report))
        non_finite["psnr_db"] = math.inf
        with self.assertRaises(WatermarkError):
            watermark_module._strict_public_report(non_finite)
        nested_secret = json.loads(json.dumps(self.report))
        nested_secret["detection"]["payload_fingerprint"] = {
            "wm_id": FIXED_WM_ID.hex()
        }
        with self.assertRaises(WatermarkError):
            watermark_module._strict_public_report(nested_secret)
        tuple_infinity = json.loads(json.dumps(self.report))
        tuple_infinity["detection"]["repeat_vote_agreement"] = (math.inf,)
        with self.assertRaises(WatermarkError):
            watermark_module._strict_public_report(tuple_infinity)

    def test_existing_and_crossed_output_paths_are_never_overwritten(self) -> None:
        existing_image = self.root / "existing-image.png"
        existing_image.write_bytes(b"image-sentinel")
        with self.assertRaises(WatermarkError):
            embed_watermark(self.master, existing_image, key=TEST_KEY)
        self.assertEqual(existing_image.read_bytes(), b"image-sentinel")

        broken_link = self.root / "broken-output.png"
        os.symlink(self.root / "missing-target.png", broken_link)
        with self.assertRaises(WatermarkError):
            embed_watermark(self.master, broken_link, key=TEST_KEY)
        self.assertTrue(os.path.lexists(broken_link))

        private_root = self.root / "exclusive-private-root"
        private_root.mkdir()
        encoded_key = "base64:" + __import__("base64").b64encode(TEST_KEY).decode("ascii")
        environment = os.environ.copy()
        environment["TEST_WATERMARK_KEY"] = encoded_key
        environment["PROVENANCE_WATERMARK_PRIVATE_ROOT"] = str(private_root)

        existing_report = self.root / "existing-public-report.json"
        existing_report.write_text("public-sentinel", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "provenance_watermark.py"),
                "detect",
                str(self.derivative),
                "--key-env",
                "TEST_WATERMARK_KEY",
                "--report",
                str(existing_report),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(existing_report.read_text(encoding="utf-8"), "public-sentinel")

        existing_private = private_root / "existing-private.json"
        existing_private.write_text("private-sentinel", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "provenance_watermark.py"),
                "detect",
                str(self.derivative),
                "--key-env",
                "TEST_WATERMARK_KEY",
                "--private-record",
                str(existing_private),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(existing_private.read_text(encoding="utf-8"), "private-sentinel")

        cross_output_report = self.root / "cross-output-report.png"
        cross_output_private = private_root / "cross-output-private.png"
        cross_report_private = private_root / "cross-report-private.json"
        cross_cases = (
            ["--report", str(cross_output_report), str(cross_output_report)],
            ["--private-record", str(cross_output_private), str(cross_output_private)],
            [
                "--report",
                str(cross_report_private),
                "--private-record",
                str(cross_report_private),
                str(self.root / "cross-third-output.png"),
            ],
        )
        for suffix in cross_cases:
            output = Path(suffix[-1])
            command = [
                sys.executable,
                str(ROOT / "scripts" / "provenance_watermark.py"),
                "embed",
                str(self.master),
                *suffix[:-1],
                str(output),
                "--key-env",
                "TEST_WATERMARK_KEY",
            ]
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(os.path.lexists(output))

    def test_atomic_commit_does_not_overwrite_racing_destination(self) -> None:
        raced_output = self.root / "raced-output.png"
        original_publish = watermark_module._publish_bytes_exclusive

        def competing_publish(
            destination: Path,
            data: bytes,
            *,
            label: str,
            mode: int = 0o600,
        ) -> None:
            destination.write_bytes(b"racing-writer")
            original_publish(destination, data, label=label, mode=mode)

        with mock.patch.object(
            watermark_module,
            "_publish_bytes_exclusive",
            side_effect=competing_publish,
        ):
            with self.assertRaises(WatermarkError):
                embed_watermark(
                    self.master,
                    raced_output,
                    key=TEST_KEY,
                    wm_id=bytes.fromhex("8090a0b0c0d0e0f0"),
                )
        self.assertEqual(raced_output.read_bytes(), b"racing-writer")

    def test_private_record_requires_non_git_configured_root(self) -> None:
        encoded_key = "base64:" + __import__("base64").b64encode(TEST_KEY).decode("ascii")
        base_environment = os.environ.copy()
        base_environment["TEST_WATERMARK_KEY"] = encoded_key
        base_environment.pop("PROVENANCE_WATERMARK_PRIVATE_ROOT", None)
        outside = self.root / "outside-private.json"

        def run(environment: dict[str, str], target: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "provenance_watermark.py"),
                    "detect",
                    str(self.derivative),
                    "--key-env",
                    "TEST_WATERMARK_KEY",
                    "--private-record",
                    str(target),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

        missing_root = run(base_environment, outside)
        self.assertEqual(missing_root.returncode, 2)

        private_root = self.root / "policy-private-root"
        private_root.mkdir()
        outside_environment = base_environment.copy()
        outside_environment["PROVENANCE_WATERMARK_PRIVATE_ROOT"] = str(private_root)
        outside_result = run(outside_environment, outside)
        self.assertEqual(outside_result.returncode, 2)

        git_environment = base_environment.copy()
        git_environment["PROVENANCE_WATERMARK_PRIVATE_ROOT"] = str(ROOT)
        git_target = ROOT / "p1-private-record-must-not-exist.json"
        git_result = run(git_environment, git_target)
        self.assertEqual(git_result.returncode, 2)
        self.assertFalse(git_target.exists())
        for result in (missing_root, outside_result, git_result):
            self.assertNotIn("Traceback", result.stderr)

    def test_resource_limits_non_regular_and_malformed_inputs_fail_safely(self) -> None:
        fifo = self.root / "input.fifo"
        os.mkfifo(fifo)
        symlink = self.root / "input-symlink.png"
        os.symlink(self.master, symlink)
        loop_a = self.root / "loop-a.png"
        loop_b = self.root / "loop-b.png"
        os.symlink(loop_b, loop_a)
        os.symlink(loop_a, loop_b)
        oversized = self.root / "oversized.bin"
        with oversized.open("wb") as destination:
            destination.truncate(watermark_module.MAX_INPUT_BYTES + 1)
        too_many_pixels = self.root / "too-many-pixels.png"
        write_header_only_png(too_many_pixels, 5001, 5000)
        too_long = self.root / "too-long.png"
        write_header_only_png(too_long, watermark_module.MAX_IMAGE_EDGE + 1, 1000)
        too_wide = self.root / "too-wide.png"
        write_header_only_png(too_wide, 1200, 99)
        animated = self.root / "animated.gif"
        Image.new("RGB", (100, 100), "red").save(
            animated,
            save_all=True,
            append_images=[Image.new("RGB", (100, 100), "blue")],
            duration=100,
            loop=0,
        )
        truncated = self.root / "truncated.png"
        encoded = self.derivative.read_bytes()
        truncated.write_bytes(encoded[: len(encoded) // 2])

        candidates = (
            fifo,
            symlink,
            oversized,
            too_many_pixels,
            too_long,
            too_wide,
            animated,
            truncated,
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate.name):
                with self.assertRaises(WatermarkError):
                    detect_watermark(candidate, key=TEST_KEY)

        with mock.patch.object(Image, "MAX_IMAGE_PIXELS", 100):
            with self.assertRaises(WatermarkError):
                detect_watermark(self.derivative, key=TEST_KEY)

        environment = os.environ.copy()
        environment["TEST_WATERMARK_KEY"] = "base64:" + __import__("base64").b64encode(TEST_KEY).decode("ascii")
        cli_result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "provenance_watermark.py"),
                "detect",
                str(oversized),
                "--key-env",
                "TEST_WATERMARK_KEY",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(cli_result.returncode, 2)
        self.assertNotIn("Traceback", cli_result.stderr)

        loop_result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "provenance_watermark.py"),
                "detect",
                str(loop_a),
                "--key-env",
                "TEST_WATERMARK_KEY",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(loop_result.returncode, 2)
        self.assertNotIn("Traceback", loop_result.stderr)

    def test_key_policy_rejects_short_bytes_and_raw_environment_strings(self) -> None:
        with self.assertRaises(WatermarkError):
            detect_watermark(self.derivative, key=b"x" * 31)
        environment = os.environ.copy()
        environment["RAW_WATERMARK_KEY"] = "this-is-a-raw-password-even-though-it-is-long-enough"
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "provenance_watermark.py"),
                "detect",
                str(self.derivative),
                "--key-env",
                "RAW_WATERMARK_KEY",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(environment["RAW_WATERMARK_KEY"], result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_transport_simulation_failure_does_not_publish_output(self) -> None:
        rejected_output = self.root / "simulation-failed-output.png"
        with mock.patch.object(
            watermark_module,
            "_simulate_transport",
            side_effect=VerificationError("simulation failed"),
        ):
            with self.assertRaises(VerificationError):
                embed_watermark(
                    self.master,
                    rejected_output,
                    key=TEST_KEY,
                    wm_id=bytes.fromhex("1122334455667788"),
                )
        self.assertFalse(os.path.lexists(rejected_output))
        with self.assertRaises(VerificationError):
            watermark_module._simulate_transport(
                Image.new("RGB", (1600, 320), "gray"),
                key=TEST_KEY,
                expected_fingerprint="0" * 64,
            )


if __name__ == "__main__":
    unittest.main()

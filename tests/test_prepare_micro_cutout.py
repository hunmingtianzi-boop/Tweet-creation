from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from asset_quality import validate_micro_asset  # noqa: E402
from ingest_browser_download import ingest_download  # noqa: E402
from orgs import command_register_asset, validate_cutout_derivation_report  # noqa: E402
from prepare_micro_cutout import (  # noqa: E402
    CutoutPreparationError,
    prepare_micro_cutout,
    validate_acquisition_report,
)
from provider_acquisition_authority import (  # noqa: E402
    article_request_metadata,
    live_provider_acquisition_authority,
)
import provider_acquisition_authority as authority_module  # noqa: E402


PROMPT_SHA = "sha256:" + "a" * 64
ROUTE = "chatgpt-web-image-route-v1"
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


def write_neutral_open_stroke_probe(path: Path) -> None:
    """Approximate the migration prompt's connected, low-fill calibration mark."""

    image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.line(
        (
            (92, 156),
            (182, 88),
            (286, 126),
            (402, 102),
            (334, 218),
            (414, 302),
            (312, 408),
            (236, 296),
            (104, 394),
            (142, 260),
            (238, 224),
            (356, 360),
        ),
        fill=(119, 119, 119, 255),
        width=40,
        joint="curve",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


class PrepareMicroCutoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.live_authority = live_provider_acquisition_authority(lambda challenge: True)
        self.live_authority.__enter__()

    def tearDown(self) -> None:
        self.live_authority.__exit__(None, None, None)
        self.temp.cleanup()

    def _runtime_binding(self) -> tuple[dict, str, str]:
        runtime_root = self.root / "runtime"
        runtime_root.mkdir(exist_ok=True)
        adapter = ROOT / "runtime" / "adapters" / "codex-desktop.json"
        adapter_sha = "sha256:" + hashlib.sha256(adapter.read_bytes()).hexdigest()
        census = runtime_root / "registry-census.json"
        if not census.exists():
            census.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "org-wechat-host-registry-census-v1",
                        "harness": {
                            "session_id": "host-session",
                            "adapter_sha256": adapter_sha,
                        },
                        "installed_release": {
                            "release_sha256": "7" * 64,
                        },
                        "registry_digest": "sha256:" + "8" * 64,
                    }
                ),
                encoding="utf-8",
            )
        census_sha = "sha256:" + hashlib.sha256(census.read_bytes()).hexdigest()
        nonce = "N" * 32
        digest = "sha256:" + "9" * 64
        migration = runtime_root / "migration-current-session.json"
        if not migration.exists():
            migration.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "org-wechat-migration-current-session-report-v1",
                        "binding_nonce": nonce,
                        "binding_digest": digest,
                        "ok": True,
                        "operational_ready": True,
                        "phase_ready": False,
                        "assurance": "current-session-observed-path-not-portable-signed",
                        "local": {
                            "installed_registry_verified": True,
                            "registry_census_sha256": census_sha,
                            "installed_release_sha256": "7" * 64,
                            "registry_digest": "sha256:" + "8" * 64,
                        },
                        "resolved_harness": {"adapter_sha256": adapter_sha},
                        "resolved_capabilities": {
                            "rgba_cutout_generation": {"generation_route_id": ROUTE}
                        },
                        "continuation": {
                            "scope": "same-host-session-only",
                            "provider_session_id": "test-session",
                            "adapter_sha256": adapter_sha,
                            "generation_route_id": ROUTE,
                            "installed_release_sha256": "7" * 64,
                            "registry_digest": "sha256:" + "8" * 64,
                        },
                    }
                ),
                encoding="utf-8",
            )
        def binding(path: Path) -> dict[str, str]:
            return {
                "location": str(path),
                "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        return {
            "adapter": binding(adapter),
            "registry_census": binding(census),
            "migration_result": binding(migration),
        }, nonce, digest

    def _paths(self, stem: str = "micro") -> tuple[Path, Path, Path]:
        source = self.root / "assets" / "generated" / f"{stem}-source.png"
        output = self.root / "assets" / "derived" / f"{stem}.png"
        report = self.root / "assets" / "derived" / f"{stem}-cutout.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        return source, output, report

    def _acquisition(
        self,
        source: Path,
        *,
        mode: str,
        article_id: str = ARTICLE_ID,
        asset_slot_id: str = ASSET_SLOT_ID,
    ) -> Path:
        path = source.with_name(source.stem.replace("-source", "") + "-acquisition.json")
        if path.exists():
            return path
        runtime_binding, nonce, digest = self._runtime_binding()
        provider_root = self.root / "provider-downloads"
        provider_root.mkdir(exist_ok=True)
        accepted_payload = source.read_bytes()
        source.unlink()
        completed_at = datetime.now(timezone.utc)
        first_downloaded_at = completed_at - timedelta(minutes=2)
        accepted_downloaded_at = completed_at - timedelta(minutes=1)
        attempts = []
        if mode == "controlled-key":
            rejected_download = provider_root / f"{source.stem}-native.png"
            rejected_download.write_bytes(b"\x89PNG\r\n\x1a\nrejected-native" + source.stem.encode())
            rejected_target = source.with_name(source.stem + "-native-rejected.png")
            rejected_ingestion = source.with_name(source.stem + "-native-ingestion.json")
            rejected_metadata = article_request_metadata(
                binding_nonce=nonce,
                binding_digest=digest,
                article_id=article_id,
                asset_slot_id=asset_slot_id,
                attempt_index=1,
                acquisition_mode="native-alpha",
                generation_route_id=ROUTE,
                prompt_sha256=PROMPT_SHA,
            )
            rejected_metadata_sha = "sha256:" + hashlib.sha256(
                json.dumps(rejected_metadata, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            ingest_download(
                rejected_download,
                rejected_target,
                rejected_ingestion,
                source.parent,
                binding_nonce=nonce,
                binding_digest=digest,
                provider_session_id="test-session",
                provider_request_id=f"{source.stem}-native-request",
                observed_download_id=f"download-{source.stem}-native",
                request_metadata_sha256=rejected_metadata_sha,
            )
            attempts.append(
                {
                    "attempt_index": 1,
                    "mode": "native-alpha",
                    "outcome": "rejected",
                    "failure_code": "cutout.source.native_alpha_required",
                    "provider_request_id": f"{source.stem}-native-request",
                    "observed_download_id": f"download-{source.stem}-native",
                    "request_metadata_sha256": rejected_metadata_sha,
                    "download_ingestion": {
                        "location": str(rejected_ingestion),
                        "sha256": "sha256:" + hashlib.sha256(rejected_ingestion.read_bytes()).hexdigest(),
                    },
                    "downloaded_at": first_downloaded_at.isoformat(),
                    "source_file_sha256": "sha256:" + hashlib.sha256(rejected_target.read_bytes()).hexdigest(),
                }
            )
        accepted_index = len(attempts) + 1
        accepted_download = provider_root / f"{source.stem}-{mode}.png"
        accepted_download.write_bytes(accepted_payload)
        accepted_ingestion = source.with_name(source.stem + "-accepted-ingestion.json")
        accepted_metadata = article_request_metadata(
            binding_nonce=nonce,
            binding_digest=digest,
            article_id=article_id,
            asset_slot_id=asset_slot_id,
            attempt_index=accepted_index,
            acquisition_mode=mode,
            generation_route_id=ROUTE,
            prompt_sha256=PROMPT_SHA,
        )
        accepted_metadata_sha = "sha256:" + hashlib.sha256(
            json.dumps(accepted_metadata, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        accepted_request_id = f"{source.stem}-{mode}-request"
        accepted_download_id = f"download-{source.stem}-accepted"
        ingest_download(
            accepted_download,
            source,
            accepted_ingestion,
            source.parent,
            binding_nonce=nonce,
            binding_digest=digest,
            provider_session_id="test-session",
            provider_request_id=accepted_request_id,
            observed_download_id=accepted_download_id,
            request_metadata_sha256=accepted_metadata_sha,
        )
        source_sha = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
        attempts.append(
            {
                "attempt_index": accepted_index,
                "mode": mode,
                "outcome": "accepted",
                "provider_request_id": accepted_request_id,
                "observed_download_id": accepted_download_id,
                "request_metadata_sha256": accepted_metadata_sha,
                "download_ingestion": {
                    "location": str(accepted_ingestion),
                    "sha256": "sha256:" + hashlib.sha256(accepted_ingestion.read_bytes()).hexdigest(),
                },
                "downloaded_at": accepted_downloaded_at.isoformat(),
                "source_file_sha256": source_sha,
                **({"key_color": "#FF00FF"} if mode == "controlled-key" else {}),
            }
        )
        path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "kind": "org-wechat-provider-image-acquisition-v2",
                    "article_id": article_id,
                    "asset_slot_id": asset_slot_id,
                    "prompt_sha256": PROMPT_SHA,
                    "generation_route": ROUTE,
                    "host_trace": {
                        "provider": "test-chatgpt-web",
                        "session_id": "test-session",
                        "download_id": f"download-{source.stem}",
                        "completed_at": completed_at.isoformat(),
                    },
                    "runtime_binding": runtime_binding,
                    "attempts": attempts,
                }
            ),
            encoding="utf-8",
        )
        return path

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
            acquisition_report_path=self._acquisition(source, mode="controlled-key"),
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
            acquisition_report_path=self._acquisition(source, mode="controlled-key"),
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
            acquisition_report_path=self._acquisition(source, mode="native-alpha"),
            require_native_alpha=True,
        )

        self.assertEqual(result["processor"]["method"], "native-rgba-normalize-v1")
        self.assertTrue(result["background_assessment"]["native_alpha_accepted"])
        self.assertTrue(validate_micro_asset(output, "floating-spot")["ok"])

    def test_native_alpha_attempt_rejects_opaque_source_without_keying(self) -> None:
        source, output, report = self._paths("native-required-opaque")
        write_controlled_source(source)
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
                acquisition_report_path=self._acquisition(source, mode="native-alpha"),
                require_native_alpha=True,
            )

        self.assertEqual(failure.exception.code, "cutout.source.native_alpha_required")
        self.assertFalse(output.exists())
        self.assertFalse(report.exists())

    def test_native_alpha_and_key_routes_are_mutually_exclusive(self) -> None:
        source, output, report = self._paths("conflicting-routes")
        write_native_rgba(source)
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
                key_color="#FF00FF",
                require_native_alpha=True,
            )

        self.assertEqual(failure.exception.code, "cutout.config.conflicting_alpha_route")

    def test_implicit_background_inference_route_is_rejected(self) -> None:
        source, output, report = self._paths("implicit-route")
        write_controlled_source(source)
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

        self.assertEqual(
            failure.exception.code,
            "cutout.config.explicit_alpha_route_required",
        )
        self.assertFalse(output.exists())
        self.assertFalse(report.exists())

    def test_formal_cutout_fails_closed_without_acquisition_report(self) -> None:
        source, output, report = self._paths("missing-acquisition")
        write_native_rgba(source)
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
                require_native_alpha=True,
            )
        self.assertEqual(failure.exception.code, "cutout.acquisition.report_required")
        self.assertFalse(output.exists())
        self.assertFalse(report.exists())

    def test_controlled_key_fallback_rejects_relabelled_native_attempt(self) -> None:
        source, output, report = self._paths("relabelled-fallback")
        write_controlled_source(source)
        acquisition = self._acquisition(source, mode="controlled-key")
        payload = json.loads(acquisition.read_text(encoding="utf-8"))
        payload["attempts"][0]["source_file_sha256"] = payload["attempts"][1][
            "source_file_sha256"
        ]
        acquisition.write_text(json.dumps(payload), encoding="utf-8")
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
                acquisition_report_path=acquisition,
                key_color="#FF00FF",
            )
        self.assertEqual(failure.exception.code, "cutout.acquisition.invalid")
        self.assertIn("newly generated source", str(failure.exception))
        self.assertFalse(output.exists())
        self.assertFalse(report.exists())

    def test_acquisition_timestamps_require_timezone_freshness_and_order(self) -> None:
        cases = ("naive", "future", "stale", "out-of-order")
        for case in cases:
            with self.subTest(case=case):
                source, output, report = self._paths(f"timestamp-{case}")
                write_controlled_source(source)
                acquisition = self._acquisition(source, mode="controlled-key")
                payload = json.loads(acquisition.read_text(encoding="utf-8"))
                if case == "naive":
                    payload["host_trace"]["completed_at"] = "2026-09-01T10:00:00"
                    payload["attempts"][0]["downloaded_at"] = "2026-09-01T09:58:00"
                    payload["attempts"][1]["downloaded_at"] = "2026-09-01T09:59:00"
                elif case == "future":
                    payload["host_trace"]["completed_at"] = (
                        datetime.now(timezone.utc) + timedelta(days=1)
                    ).isoformat()
                elif case == "stale":
                    stale = datetime.now(timezone.utc) - timedelta(days=8)
                    payload["host_trace"]["completed_at"] = stale.isoformat()
                    payload["attempts"][0]["downloaded_at"] = (
                        stale - timedelta(minutes=2)
                    ).isoformat()
                    payload["attempts"][1]["downloaded_at"] = (
                        stale - timedelta(minutes=1)
                    ).isoformat()
                else:
                    payload["attempts"][0]["downloaded_at"], payload["attempts"][1][
                        "downloaded_at"
                    ] = (
                        payload["attempts"][1]["downloaded_at"],
                        payload["attempts"][0]["downloaded_at"],
                    )
                acquisition.write_text(json.dumps(payload), encoding="utf-8")
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
                        acquisition_report_path=acquisition,
                        key_color="#FF00FF",
                    )
                self.assertEqual(failure.exception.code, "cutout.acquisition.invalid")
                self.assertFalse(output.exists())
                self.assertFalse(report.exists())

    def test_key_route_rejects_native_rgba_instead_of_dead_end_keying(self) -> None:
        source, output, report = self._paths("native-on-key-route")
        write_native_rgba(source)
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
                acquisition_report_path=self._acquisition(source, mode="controlled-key"),
                key_color="#FF00FF",
            )
        self.assertEqual(failure.exception.code, "cutout.source.route_mismatch_native_rgba")
        self.assertFalse(output.exists())
        self.assertFalse(report.exists())

    def test_neutral_open_stroke_migration_probe_passes_native_gate(self) -> None:
        source, output, report = self._paths("neutral-open-stroke-probe")
        write_neutral_open_stroke_probe(source)
        source_validation = validate_micro_asset(source, "floating-spot")
        self.assertTrue(source_validation["ok"], source_validation["errors"])
        self.assertLess(
            source_validation["inspection"]["alpha_bbox_fill_ratio"],
            0.60,
        )

        result = prepare_micro_cutout(
            source,
            output,
            report,
            role="floating-spot",
            article_id="migration-route-probe",
            asset_slot_id="migration.rgba-route-probe",
            prompt_sha256=PROMPT_SHA,
            generation_route=ROUTE,
            acquisition_report_path=self._acquisition(
                source,
                mode="native-alpha",
                article_id="migration-route-probe",
                asset_slot_id="migration.rgba-route-probe",
            ),
            require_native_alpha=True,
        )

        self.assertEqual(result["processor"]["method"], "native-rgba-normalize-v1")
        self.assertTrue(result["final_validation"]["ok"])

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
                acquisition_report_path=self._acquisition(source, mode="controlled-key"),
                key_color="#FF00FF",
            )
        self.assertIn(
            failure.exception.code,
            {"cutout.source.background_not_uniform", "cutout.source.key_mismatch"},
        )
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
                acquisition_report_path=self._acquisition(source, mode="controlled-key"),
                key_color="#FF00FF",
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
                acquisition_report_path=self._acquisition(source, mode="controlled-key"),
                key_color="#FF00FF",
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
                acquisition_report_path=self._acquisition(source, mode="controlled-key"),
                key_color="#FF00FF",
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
                key_color="#FF00FF",
            )
        self.assertEqual(failure.exception.code, "cutout.path.symlink_forbidden")

    def test_source_output_and_report_parent_symlinks_fail_before_any_write(self) -> None:
        real_source_parent = self.root / "real-source-parent"
        real_source_parent.mkdir()
        real_source = real_source_parent / "source.png"
        write_native_rgba(real_source)
        source_parent_link = self.root / "source-parent-link"
        source_parent_link.symlink_to(real_source_parent, target_is_directory=True)
        acquisition = self._acquisition(real_source, mode="native-alpha")
        output = self.root / "source-parent-output.png"
        report = self.root / "source-parent-report.json"
        with self.assertRaises(CutoutPreparationError) as failure:
            prepare_micro_cutout(
                source_parent_link / "source.png",
                output,
                report,
                role="floating-spot",
                article_id=ARTICLE_ID,
                asset_slot_id=ASSET_SLOT_ID,
                prompt_sha256=PROMPT_SHA,
                generation_route=ROUTE,
                acquisition_report_path=acquisition,
                require_native_alpha=True,
            )
        self.assertEqual(failure.exception.code, "cutout.path.symlink_forbidden")
        self.assertFalse(output.exists())
        self.assertFalse(report.exists())

        for symlinked_target in ("output", "report"):
            with self.subTest(symlinked_target=symlinked_target):
                real_parent = self.root / f"real-{symlinked_target}-parent"
                real_parent.mkdir()
                parent_link = self.root / f"{symlinked_target}-parent-link"
                parent_link.symlink_to(real_parent, target_is_directory=True)
                safe_output = self.root / f"safe-{symlinked_target}.png"
                safe_report = self.root / f"safe-{symlinked_target}.json"
                candidate_output = (
                    parent_link / "derived.png"
                    if symlinked_target == "output"
                    else safe_output
                )
                candidate_report = (
                    parent_link / "derivation.json"
                    if symlinked_target == "report"
                    else safe_report
                )
                with self.assertRaises(CutoutPreparationError) as blocked:
                    prepare_micro_cutout(
                        real_source,
                        candidate_output,
                        candidate_report,
                        role="floating-spot",
                        article_id=ARTICLE_ID,
                        asset_slot_id=ASSET_SLOT_ID,
                        prompt_sha256=PROMPT_SHA,
                        generation_route=ROUTE,
                        acquisition_report_path=acquisition,
                        require_native_alpha=True,
                    )
                self.assertEqual(
                    blocked.exception.code, "cutout.path.symlink_forbidden"
                )
                self.assertFalse(candidate_output.exists())
                self.assertFalse(candidate_report.exists())

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

    def test_report_verifier_rejects_implicit_or_mislabeled_alpha_route(self) -> None:
        _, _, output, report = self._prepare("route-contract")
        payload = json.loads(report.read_text(encoding="utf-8"))
        payload["processor"]["config"]["key_color"] = None
        config_bytes = json.dumps(
            payload["processor"]["config"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        payload["processor"]["config_sha256"] = (
            "sha256:" + hashlib.sha256(config_bytes).hexdigest()
        )
        report.write_text(json.dumps(payload), encoding="utf-8")
        implicit = validate_cutout_derivation_report(
            self.root, report, output, "floating-spot"
        )
        self.assertFalse(implicit["ok"])
        self.assertTrue(
            any("explicit controlled key" in error for error in implicit["errors"]),
            implicit["errors"],
        )

        native_source, native_output, native_report = self._paths("native-route-contract")
        write_native_rgba(native_source)
        prepare_micro_cutout(
            native_source,
            native_output,
            native_report,
            role="floating-spot",
            article_id=ARTICLE_ID,
            asset_slot_id=ASSET_SLOT_ID,
            prompt_sha256=PROMPT_SHA,
            generation_route=ROUTE,
            acquisition_report_path=self._acquisition(native_source, mode="native-alpha"),
            require_native_alpha=True,
        )
        native_payload = json.loads(native_report.read_text(encoding="utf-8"))
        native_payload["processor"]["config"]["require_native_alpha"] = False
        native_config_bytes = json.dumps(
            native_payload["processor"]["config"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        native_payload["processor"]["config_sha256"] = (
            "sha256:" + hashlib.sha256(native_config_bytes).hexdigest()
        )
        native_report.write_text(json.dumps(native_payload), encoding="utf-8")
        mislabeled = validate_cutout_derivation_report(
            self.root, native_report, native_output, "floating-spot"
        )
        self.assertFalse(mislabeled["ok"])
        self.assertTrue(
            any("explicit native-alpha" in error for error in mislabeled["errors"]),
            mislabeled["errors"],
        )

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

    def test_serialized_callback_claim_cannot_upgrade_current_session_assurance(self) -> None:
        source, output, report = self._paths("serialized-callback")
        write_native_rgba(source)
        acquisition = self._acquisition(source, mode="native-alpha")
        payload = json.loads(acquisition.read_text(encoding="utf-8"))
        payload["live_authority_callback"] = {
            "authorized": True,
            "mode": "current-session-nonportable",
        }
        acquisition.write_text(json.dumps(payload), encoding="utf-8")
        token = authority_module._LIVE_AUTHORITY.set(None)
        try:
            result = prepare_micro_cutout(
                source,
                output,
                report,
                role="floating-spot",
                article_id=ARTICLE_ID,
                asset_slot_id=ASSET_SLOT_ID,
                prompt_sha256=PROMPT_SHA,
                generation_route=ROUTE,
                acquisition_report_path=acquisition,
                require_native_alpha=True,
            )
        finally:
            authority_module._LIVE_AUTHORITY.reset(token)
        generation = result["generation"]
        self.assertEqual(
            generation["authority_scope_at_creation"],
            "current-session-operator-harness-trusted",
        )
        self.assertEqual(
            generation["acquisition_assurance"],
            "operator-harness-trusted-current-session",
        )
        self.assertFalse(generation["host_attested"])
        self.assertFalse(generation["portable"])
        self.assertFalse(generation["portable_host_receipt_verified"])
        self.assertFalse(generation["policy_hook_evaluated"])

    def test_plain_true_callback_does_not_create_attestation_or_portability(self) -> None:
        result, _, _, _ = self._prepare("plain-true-hook")
        generation = result["generation"]
        self.assertTrue(generation["policy_hook_evaluated"])
        self.assertFalse(generation["host_attested"])
        self.assertFalse(generation["portable"])
        self.assertFalse(generation["portable_host_receipt_verified"])
        self.assertEqual(
            generation["acquisition_assurance"],
            "operator-harness-trusted-current-session",
        )

    def test_false_policy_hook_blocks_current_session_acquisition(self) -> None:
        source, output, report = self._paths("policy-denied")
        write_native_rgba(source)
        acquisition = self._acquisition(source, mode="native-alpha")
        with live_provider_acquisition_authority(lambda challenge: False):
            with self.assertRaisesRegex(CutoutPreparationError, "policy hook denied"):
                prepare_micro_cutout(
                    source,
                    output,
                    report,
                    role="floating-spot",
                    article_id=ARTICLE_ID,
                    asset_slot_id=ASSET_SLOT_ID,
                    prompt_sha256=PROMPT_SHA,
                    generation_route=ROUTE,
                    acquisition_report_path=acquisition,
                    require_native_alpha=True,
                )
        self.assertFalse(output.exists())
        self.assertFalse(report.exists())

    def test_legacy_v1_and_operator_selected_generation_route_are_rejected(self) -> None:
        for stem, mutate, route in (
            (
                "legacy-v1",
                lambda payload: payload.update(
                    {
                        "schema_version": 1,
                        "kind": "org-wechat-provider-image-acquisition-v1",
                    }
                ),
                ROUTE,
            ),
            (
                "fake-route",
                lambda payload: payload.update(
                    {"generation_route": "synthetic-offline-provider-v1"}
                ),
                "synthetic-offline-provider-v1",
            ),
        ):
            with self.subTest(stem=stem):
                source, output, report = self._paths(stem)
                write_native_rgba(source)
                acquisition = self._acquisition(source, mode="native-alpha")
                payload = json.loads(acquisition.read_text(encoding="utf-8"))
                mutate(payload)
                acquisition.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(CutoutPreparationError) as failure:
                    prepare_micro_cutout(
                        source,
                        output,
                        report,
                        role="floating-spot",
                        article_id=ARTICLE_ID,
                        asset_slot_id=ASSET_SLOT_ID,
                        prompt_sha256=PROMPT_SHA,
                        generation_route=route,
                        acquisition_report_path=acquisition,
                        require_native_alpha=True,
                    )
                self.assertEqual(failure.exception.code, "cutout.acquisition.invalid")

    def test_ingestion_raw_bytes_are_revalidated_before_preparation(self) -> None:
        source, output, report = self._paths("ingestion-tamper")
        write_native_rgba(source)
        acquisition = self._acquisition(source, mode="native-alpha")
        acquisition_payload = json.loads(acquisition.read_text(encoding="utf-8"))
        ingestion_ref = acquisition_payload["attempts"][0]["download_ingestion"]
        ingestion_path = Path(ingestion_ref["location"])
        ingestion_payload = json.loads(ingestion_path.read_text(encoding="utf-8"))
        ingestion_payload["target"]["byte_length"] += 1
        ingestion_path.write_text(json.dumps(ingestion_payload), encoding="utf-8")
        ingestion_ref["sha256"] = "sha256:" + hashlib.sha256(
            ingestion_path.read_bytes()
        ).hexdigest()
        acquisition.write_text(json.dumps(acquisition_payload), encoding="utf-8")
        with self.assertRaisesRegex(CutoutPreparationError, "exact raw bytes"):
            prepare_micro_cutout(
                source,
                output,
                report,
                role="floating-spot",
                article_id=ARTICLE_ID,
                asset_slot_id=ASSET_SLOT_ID,
                prompt_sha256=PROMPT_SHA,
                generation_route=ROUTE,
                acquisition_report_path=acquisition,
                require_native_alpha=True,
            )

    def test_real_portable_signature_can_attach_without_hash_cycle(self) -> None:
        source, output, report = self._paths("portable")
        write_native_rgba(source)
        acquisition = self._acquisition(source, mode="native-alpha")
        acquisition_payload = json.loads(acquisition.read_text(encoding="utf-8"))
        migration_ref = acquisition_payload["runtime_binding"]["migration_result"]
        migration_path = Path(migration_ref["location"])
        migration = json.loads(migration_path.read_text(encoding="utf-8"))
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        migration_issued = datetime.now(timezone.utc)
        continuation_expires = migration_issued + timedelta(hours=1)
        migration_receipt_unsigned = {
            "schema_version": 1,
            "kind": "org-wechat-migration-probe-host-receipt-v1",
            "receipt_id": "migration-receipt-test",
            "issued_at": migration_issued.isoformat(),
            "expires_at": (migration_issued + timedelta(minutes=5)).isoformat(),
            "continuation_expires_at": continuation_expires.isoformat(),
            "binding": {
                "binding_nonce": migration["binding_nonce"],
                "binding_digest": migration["binding_digest"],
                "installed_release_sha256": migration["local"]["installed_release_sha256"],
                "registry_digest": migration["local"]["registry_digest"],
                "registry_census_sha256": migration["local"]["registry_census_sha256"],
                "adapter_sha256": migration["resolved_harness"]["adapter_sha256"],
                "generation_route_id": migration["resolved_capabilities"][
                    "rgba_cutout_generation"
                ]["generation_route_id"],
            },
            "replay_protection": {
                "single_use": True,
                "host_nonce_consumed": True,
                "host_ledger_id": "test-host-ledger",
            },
            "host": {
                "capability": "host.migration.finalize",
                "provider": "test-host",
                "session_id": "test-host-session",
                "request_id": "test-migration-request",
            },
        }
        migration_signature = private_key.sign(
            json.dumps(
                migration_receipt_unsigned,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        migration_receipt = dict(migration_receipt_unsigned)
        migration_receipt["signature"] = {
            "algorithm": "ed25519",
            "key_id": "test-provider-key",
            "value_base64": __import__("base64").b64encode(migration_signature).decode("ascii"),
        }
        migration.update(
            {
                "kind": "org-wechat-migration-final-report-v1",
                "phase_ready": True,
                "host_attestation": "migration-host-receipt-verified",
                "migration_host_receipt": migration_receipt,
                "migration_selftest": {"receipt_id": "migration-receipt-test"},
            }
        )
        migration["continuation"].update(
            {
                "receipt_id": "migration-receipt-test",
                "expires_at": continuation_expires.isoformat(),
            }
        )
        migration.pop("assurance", None)
        migration_path.write_text(json.dumps(migration), encoding="utf-8")
        migration_ref["sha256"] = "sha256:" + hashlib.sha256(
            migration_path.read_bytes()
        ).hexdigest()
        acquisition.write_text(json.dumps(acquisition_payload), encoding="utf-8")

        token = authority_module._LIVE_AUTHORITY.set(None)
        try:
            structural = validate_acquisition_report(
                acquisition,
                source,
                article_id=ARTICLE_ID,
                asset_slot_id=ASSET_SLOT_ID,
                prompt_sha256=PROMPT_SHA,
                generation_route=ROUTE,
                expected_mode="native-alpha",
                key_color=None,
                require_authority=False,
            )
        finally:
            authority_module._LIVE_AUTHORITY.reset(token)
        self.assertTrue(structural["ok"], structural["errors"])
        challenge = structural["authority"]["challenge"]
        issued = datetime.now(timezone.utc)
        receipt_unsigned = {
            "schema_version": 1,
            "kind": "org-wechat-provider-image-host-receipt-v1",
            "issued_at": issued.isoformat(),
            "expires_at": (issued + timedelta(minutes=5)).isoformat(),
            "binding": challenge,
            "host": {
                "capability": "host.receipt.attest",
                "provider": "test-host",
                "session_id": "test-host-session",
                "request_id": "test-host-request",
            },
        }
        signature = private_key.sign(
            json.dumps(
                receipt_unsigned,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        receipt = dict(receipt_unsigned)
        receipt["signature"] = {
            "algorithm": "ed25519",
            "key_id": "test-provider-key",
            "value_base64": __import__("base64").b64encode(signature).decode("ascii"),
        }
        receipt_path = source.with_name("portable-host-receipt.json")
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        acquisition_payload = json.loads(acquisition.read_text(encoding="utf-8"))
        acquisition_payload["portable_host_receipt"] = {
            "location": str(receipt_path),
            "sha256": "sha256:" + hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        }
        acquisition.write_text(json.dumps(acquisition_payload), encoding="utf-8")

        token = authority_module._LIVE_AUTHORITY.set(None)
        try:
            with mock.patch(
                "provider_acquisition_authority._load_protected_keys",
                return_value={"test-provider-key": public_key},
            ):
                result = prepare_micro_cutout(
                    source,
                    output,
                    report,
                    role="floating-spot",
                    article_id=ARTICLE_ID,
                    asset_slot_id=ASSET_SLOT_ID,
                    prompt_sha256=PROMPT_SHA,
                    generation_route=ROUTE,
                    acquisition_report_path=acquisition,
                    portable_trust_store=self.root / "protected-trust-store.json",
                    require_native_alpha=True,
                )
        finally:
            authority_module._LIVE_AUTHORITY.reset(token)
        self.assertEqual(result["generation"]["authority_scope_at_creation"], "portable-signed")
        self.assertTrue(result["generation"]["portable_host_receipt_verified"])
        tampered_migration = json.loads(json.dumps(migration))
        tampered_migration["migration_host_receipt"]["binding"]["registry_digest"] = (
            "sha256:" + "0" * 64
        )
        with mock.patch(
            "provider_acquisition_authority._load_protected_keys",
            return_value={"test-provider-key": public_key},
        ):
            migration_errors = authority_module._verify_embedded_migration_receipt(
                tampered_migration,
                trust_store=self.root / "protected-trust-store.json",
                now=datetime.now(timezone.utc),
            )
        self.assertTrue(migration_errors)
        self.assertTrue(
            any("registry_digest" in error or "verification failed" in error for error in migration_errors),
            migration_errors,
        )
        missing_receipt = json.loads(json.dumps(migration))
        missing_receipt.pop("migration_host_receipt")
        self.assertTrue(
            any(
                "lacks its embedded signed migration_host_receipt" in error
                for error in authority_module._verify_embedded_migration_receipt(
                    missing_receipt,
                    trust_store=self.root / "protected-trust-store.json",
                    now=datetime.now(timezone.utc),
                )
            )
        )
        missing_continuation = json.loads(json.dumps(migration))
        missing_continuation.pop("continuation")
        with mock.patch(
            "provider_acquisition_authority._load_protected_keys",
            return_value={"test-provider-key": public_key},
        ):
            continuation_errors = authority_module._verify_embedded_migration_receipt(
                missing_continuation,
                trust_store=self.root / "protected-trust-store.json",
                now=datetime.now(timezone.utc),
            )
        self.assertTrue(
            any("continuation" in error for error in continuation_errors),
            continuation_errors,
        )


if __name__ == "__main__":
    unittest.main()

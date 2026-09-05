from __future__ import annotations

import json
import hashlib
import io
import base64
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from tests import test_transport_fidelity as transport_test_helpers
from tests import test_runtime_preflight as runtime_test_helpers

from scripts.ingest_wechat_readback_capture import (
    ReadbackCaptureIngestionError,
    ingest_wechat_readback_capture,
)
from scripts.release_skills import install_packages, write_manifest
from scripts.runtime_preflight import (
    build_current_session_registry_census,
    build_runtime_profile_from_census,
    validate_runtime_profile,
)
from scripts import wechat_publisher as publisher_module
from scripts.compile_wechat import (
    compile_frozen_session_draft,
    compile_frozen_transport,
)
from scripts.transport_fidelity import validate_transport_fidelity_diagnostic
from transport_fidelity import (
    PUBLICATION_CONFIRMATION_RECEIPT_SOURCE,
    verify_host_publication_confirmation_receipt,
)
from scripts.wechat_publisher import (
    AmbiguousMutation,
    CONFIRMATION_SOURCE,
    CurrentSessionPublicationAuthorization,
    HostScreenshotCapture,
    HTTPResponse,
    PublisherStore,
    WeChatAPIError,
    WeChatAPIProvider,
    WeChatPublisher,
    _file_digest,
)


class FakeHostAuthority:
    def __init__(self, screenshot_source: Path, *, mutate_capture: bool = True) -> None:
        self.screenshot_source = screenshot_source
        self.mutate_capture = mutate_capture
        self.capture_calls = 0
        self.authorization_calls = 0

    def capture_wechat_chapters(
        self,
        *,
        target_account_ref: str,
        draft_media_id: str,
        article_revision: str,
        chapter_ids: tuple[str, ...],
    ) -> dict[str, HostScreenshotCapture]:
        self.capture_calls += 1
        image = Image.open(self.screenshot_source).convert("RGBA")
        if self.mutate_capture:
            pixel = image.getpixel((0, 0))
            image.putpixel(
                (0, 0), ((pixel[0] + 1) % 256, pixel[1], pixel[2], pixel[3])
            )
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return {
            chapter_id: HostScreenshotCapture(
                png_bytes=buffer.getvalue(),
                captured_at=datetime.now(timezone.utc).isoformat(),
                capture_event_id=f"host-capture-{index:04d}",
            )
            for index, chapter_id in enumerate(chapter_ids, start=1)
        }

    def verify_mobile_evidence(self, **kwargs) -> bool:
        return True

    def authorize_publication(self, challenge):
        self.authorization_calls += 1
        return CurrentSessionPublicationAuthorization(
            target_account_ref=challenge.target_account_ref,
            article_revision=challenge.article_revision,
            draft_media_id=challenge.draft_media_id,
            draft_payload_sha256=challenge.draft_payload_sha256,
            compile_report_sha256=challenge.compile_report_sha256,
            readback_sha256=challenge.readback_sha256,
            ardot_live_root_sha256=challenge.live_root_sha256,
            confirmation_nonce=challenge.confirmation_nonce,
            host_session_id="host-live-session-test",
            confirmation_event_id="user-confirmation-event-test",
            confirmed_at=datetime.now(timezone.utc).isoformat(),
        )


def synthetic_viewport_review(handoff, provider, media_id):
    """Synthetic measurements for contract tests, never live browser evidence."""
    export = json.loads(handoff.read_text())["transport_fidelity"]["export"]
    review = {"source": "wechat-render-viewport-review-v1", "target_account_ref": provider.account_ref,
              "draft_id": media_id, "content_sha256": "sha256:" + hashlib.sha256(provider.saved_article["content"].encode()).hexdigest(), "samples": []}
    for width in (320, 390, 430):
        path = handoff.parent / f"synthetic-viewport-{width}.png"
        Image.new("RGB", (width, round(export["artboard"]["height_px"] * width / 390)), "white").save(path)
        layers = []
        for chapter in export["chapters"]:
            for node in chapter["visible_text_nodes"]:
                scale = width / 390
                layers.append({"node_id": node["node_id"], "font_size_px": node["style"]["font_size_px"] * scale,
                    "letter_spacing_px": node["style"]["letter_spacing_px"] * scale,
                    "width_px": node["geometry"]["width"] * scale, "height_px": node["geometry"]["height"] * scale,
                    "scroll_width_px": node["geometry"]["width"] * scale, "scroll_height_px": node["geometry"]["height"] * scale})
        review["samples"].append({"width_px": width, "captured_at": datetime.now(timezone.utc).isoformat(),
            "capture_event_id": f"synthetic-{width}", "screenshot": {"path": path.name, "sha256": _file_digest(path)}, "text_layers": layers})
    path = handoff.parent / "synthetic-viewport-review.json"
    path.write_text(json.dumps(review))
    return path


class FakeProvider:
    def __init__(self) -> None:
        self.account_ref = "test-visible-account"
        self.timeout = 1
        self.uploadimg_calls = 0
        self.material_calls = 0
        self.draft_add_calls = 0
        self.draft_update_calls = 0
        self.submit_calls = 0
        self.get_status_calls = 0
        self.draft_get_calls = 0
        self.transport_calls = 0
        self.saved_article: dict | None = None
        self.cdn: dict[str, bytes] = {}
        self.publish_statuses: list[dict] = [
            {
                "publish_status": 0,
                "article_detail": {
                    "item": [{"article_url": "https://mp.weixin.qq.com/s/test"}]
                },
            }
        ]

    def account_preflight(self, target_account_ref: str) -> dict:
        return {
            "status": "passed",
            "target_account_ref": target_account_ref,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "credential_binding": "sha256:" + "1" * 64,
            "capabilities": {
                "draft_read": True,
                "material_read": True,
                "uploadimg": "proven-only-by-upload-transaction",
                "material_write": "proven-only-by-upload-transaction",
                "draft_write": "proven-only-by-draft-transaction",
                "freepublish": "proven-only-by-submit-and-status-readback",
            },
        }

    def uploadimg(self, path: Path) -> dict:
        self.uploadimg_calls += 1
        url = f"https://mmbiz.qpic.cn/body-{_file_digest(path)[7:23]}"
        self.cdn[url] = path.read_bytes()
        return {"url": url}

    def add_material(self, path: Path, *, material_type: str = "image") -> dict:
        self.material_calls += 1
        url = "https://mmbiz.qpic.cn/cover-test"
        self.cdn[url] = path.read_bytes()
        return {"media_id": "permanent-cover-media-id", "url": url}

    def draft_add(self, news: list[dict]) -> dict:
        self.draft_add_calls += 1
        self.saved_article = dict(news[0])
        self.saved_article["thumb_url"] = "https://mmbiz.qpic.cn/cover-test"
        return {"media_id": "draft-media-id"}

    def draft_update(self, media_id: str, article: dict, index: int = 0) -> dict:
        self.draft_update_calls += 1
        self.saved_article = dict(article)
        self.saved_article["thumb_url"] = "https://mmbiz.qpic.cn/cover-test"
        return {"errcode": 0}

    def draft_get_with_receipt(
        self, media_id: str
    ) -> tuple[dict, HTTPResponse, str]:
        self.draft_get_calls += 1
        if self.saved_article is None:
            raise AssertionError("draft was not saved")
        payload = {"news_item": [dict(self.saved_article)]}
        return (
            payload,
            HTTPResponse(200, {"content-type": "application/json"}, b"{}"),
            "request-id-test",
        )

    def freepublish_submit(self, media_id: str) -> dict:
        self.submit_calls += 1
        return {"publish_id": "publish-job-id"}

    def freepublish_get(self, publish_id: str) -> dict:
        self.get_status_calls += 1
        if len(self.publish_statuses) > 1:
            return self.publish_statuses.pop(0)
        return self.publish_statuses[0]

    def transport(
        self,
        method: str,
        url: str,
        headers: dict,
        body: bytes | None,
        timeout: float,
    ) -> HTTPResponse:
        self.transport_calls += 1
        if method != "GET" or url not in self.cdn:
            return HTTPResponse(404, {"content-type": "text/plain"}, b"missing")
        return HTTPResponse(200, {"content-type": "image/png"}, self.cdn[url])


class WeChatPublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.secure_runtime = patch("secure_runtime.require_secure_runtime")
        self.secure_runtime.start()
        self.addCleanup(self.secure_runtime.stop)

    def make_context(self) -> tuple:
        case = transport_test_helpers.TransportFidelityTests("run")
        temporary, handoff_path, manifest = case.make_bundle()
        provider = FakeProvider()
        store = PublisherStore(handoff_path.parent / "publisher.sqlite3")
        self.addCleanup(store.close)
        self.addCleanup(temporary.cleanup)
        authority = FakeHostAuthority(handoff_path.parent / "ardot-chapter-1.png")
        publisher = WeChatPublisher(
            provider, store, current_session_authority=authority
        )
        return case, handoff_path, manifest, provider, store, publisher

    def prepare_and_compile(self) -> tuple:
        case, handoff, manifest, provider, store, publisher = self.make_context()
        upload_map = handoff.parent / "upload-map.json"
        publisher.prepare_uploads(
            handoff,
            target_account_ref="test-visible-account",
            output_path=upload_map,
        )
        output = handoff.parent / "compiled"
        live_root = case.live_root(handoff, output / "wechat-candidate.html")
        with patch("secure_runtime.require_secure_runtime"):
            compiled = compile_frozen_session_draft(
                handoff,
                output,
                live_root_path=live_root,
                upload_map_path=upload_map,
                check=True,
            )
        self.assertTrue(compiled["ok"], compiled)
        return (
            case,
            handoff,
            manifest,
            provider,
            store,
            publisher,
            upload_map,
            output,
            live_root,
            compiled,
        )

    def make_installed_readback_runtime(
        self, root: Path
    ) -> tuple[Path, Path, Path, str, str]:
        """Create one real installed-release/census/profile binding for ingestion."""

        root = root.resolve()
        source_manifest = root / "readback-source-release.json"
        skills_root = root / "readback-installed-skills"
        write_manifest(source_manifest, runtime_test_helpers.ROOT)
        installed = install_packages(
            skills_root,
            source_manifest,
            runtime_test_helpers.ROOT,
        )
        release_manifest = Path(installed["installed_manifest"])
        session_id = "wechat-readback-session-test"
        capture_tool_id = "scripts/ingest_wechat_readback_capture.py"
        census = build_current_session_registry_census(
            [
                "browser:control-in-app-browser",
                "mcp__node_repl__js",
                "view_image",
            ],
            runtime_test_helpers.ROOT,
            phase="delivery",
            session_id=session_id,
            adapter_path=(
                runtime_test_helpers.ROOT
                / "runtime"
                / "adapters"
                / "codex-desktop.json"
            ),
            skills_root=skills_root,
            release_manifest_path=release_manifest,
        )
        census_path = root / "readback-registry-census.json"
        census_path.write_text(
            json.dumps(census, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        target = {
            "schema_version": 1,
            "kind": "org-wechat-runtime-target-v1",
            "links": {
                "ardot_current_workspace": {
                    "url": (
                        "https://ardot.tencent.com/file/123456789?"
                        "web_only=1&node_id=1%3A2"
                    ),
                    "purpose": "current test workspace",
                },
                "wechat_current_account": {
                    "url": "https://api.weixin.qq.com/",
                    "purpose": "current API target",
                },
            },
            "targets": {
                "ardot": {
                    "workspace_link": "ardot_current_workspace",
                    "expected_file_id": "123456789",
                    "expected_root_id": "1:2",
                },
                "wechat": {
                    "mode": "api",
                    "terminal_state": "draft",
                    "account_link": "wechat_current_account",
                    "target_account_ref": "test-visible-account",
                },
            },
            "artifact_inventory": {
                "census_complete": True,
                "source_sha256": "sha256:" + "9" * 64,
                "eligible_watermark_carriers": [],
            },
        }
        profile = build_runtime_profile_from_census(
            census,
            census_path,
            target,
            runtime_test_helpers.ROOT,
            "delivery",
        )
        profile_path = root / "readback-runtime-profile.json"
        profile_path.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        report = validate_runtime_profile(
            profile,
            runtime_test_helpers.ROOT,
            "delivery",
            now=datetime.now(timezone.utc),
            environment={},
            binding_only=True,
        )
        self.assertTrue(report["binding_ready"], report["errors"])
        report_path = root / "readback-runtime-report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return profile_path, report_path, census_path, session_id, capture_tool_id

    def make_capture_bundle(
        self,
        *,
        handoff: Path,
        compile_report: Path,
        raw_draft: Path,
        saved: dict,
        compiled: dict,
        nonce: str,
        output_dir: Path,
        capture_source: Path | None = None,
    ) -> dict:
        profile, report, census, session_id, capture_tool_id = (
            self.make_installed_readback_runtime(handoff.parent)
        )
        source = capture_source or (handoff.parent / "ardot-chapter-1.png")
        captured = handoff.parent / f"browser-capture-{nonce[:8]}.png"
        with Image.open(source) as image:
            image = image.convert("RGBA")
            pixel = image.getpixel((0, 0))
            image.putpixel(
                (0, 0),
                ((pixel[0] + 1) % 256, pixel[1], pixel[2], pixel[3]),
            )
            image.save(captured)
        return ingest_wechat_readback_capture(
            handoff_path=handoff,
            compile_report_path=compile_report,
            raw_draft_path=raw_draft,
            runtime_profile_path=profile,
            runtime_report_path=report,
            registry_census_path=census,
            target_account_ref="test-visible-account",
            draft_id=saved["media_id"],
            article_revision=compiled["revision_hash"],
            host_session_id=session_id,
            capture_tool_id=capture_tool_id,
            observed_url="https://mp.weixin.qq.com/cgi-bin/appmsg",
            nonce=nonce,
            chapter_captures=[
                {
                    "chapter_id": "chapter-1",
                    "path": captured,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "capture_event_id": "browser-capture-event-0001",
                }
            ],
            output_dir=output_dir,
        )

    def test_account_preflight_does_not_self_assert_capabilities(self) -> None:
        def invalid_transport(method, url, headers, body, timeout):
            if "draft/count" in url:
                return HTTPResponse(200, {}, b'{"errcode":0}')
            return HTTPResponse(
                200,
                {},
                b'{"voice_count":0,"video_count":0,"image_count":0,"news_count":0}',
            )

        provider = WeChatAPIProvider(
            access_token="secret-token",
            app_id="appid12",
            transport=invalid_transport,
            sleeper=lambda _: None,
        )
        with self.assertRaisesRegex(WeChatAPIError, "did not prove"):
            provider.account_preflight("appid:appid12")

    def test_standalone_account_preflight_is_read_only_and_create_once(self) -> None:
        provider = FakeProvider()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = PublisherStore(root / "publisher.sqlite3")
            self.addCleanup(store.close)
            publisher = WeChatPublisher(provider, store)
            output = root / "account-preflight.json"
            result = publisher.preflight_account(
                target_account_ref="test-visible-account",
                output_path=output,
            )
            self.assertEqual(result["mutations_attempted"], 0)
            self.assertEqual(
                result["provider_calls"],
                ["draft/count", "material/get_materialcount"],
            )
            self.assertTrue(output.is_file())
            self.assertEqual(provider.uploadimg_calls, 0)
            self.assertEqual(provider.material_calls, 0)
            self.assertEqual(provider.draft_add_calls, 0)
            with self.assertRaisesRegex(ValueError, "already exists"):
                publisher.preflight_account(
                    target_account_ref="test-visible-account",
                    output_path=output,
                )

    def test_programmatic_publisher_requires_locked_runtime(self) -> None:
        self.secure_runtime.stop()
        try:
            with tempfile.TemporaryDirectory() as directory:
                store = PublisherStore(Path(directory) / "publisher.sqlite3")
                self.addCleanup(store.close)
                with self.assertRaises(SystemExit):
                    WeChatPublisher(FakeProvider(), store)
        finally:
            self.secure_runtime.start()

    def test_active_provider_account_must_match_every_mutation(self) -> None:
        _case, handoff, _manifest, provider, _store, publisher = self.make_context()
        provider.account_ref = "another-account"
        with self.assertRaisesRegex(ValueError, "active WeChat credential"):
            publisher.prepare_uploads(
                handoff,
                target_account_ref="test-visible-account",
                output_path=handoff.parent / "wrong-account-upload-map.json",
            )
        self.assertEqual(provider.uploadimg_calls, 0)
        self.assertEqual(provider.material_calls, 0)

    def test_upload_output_collision_or_unsafe_parent_stops_before_upload(self) -> None:
        _case, handoff, _manifest, provider, _store, publisher = self.make_context()
        existing = handoff.parent / "existing-upload-map.json"
        original = b"do-not-overwrite\n"
        existing.write_bytes(original)
        with self.assertRaisesRegex(ValueError, "already exists"):
            publisher.prepare_uploads(
                handoff,
                target_account_ref="test-visible-account",
                output_path=existing,
            )
        self.assertEqual(existing.read_bytes(), original)
        self.assertEqual(provider.uploadimg_calls, 0)
        self.assertEqual(provider.material_calls, 0)
        self.assertFalse(
            existing.with_name(f".{existing.name}.upload-journal.jsonl").exists()
        )

        missing_parent = handoff.parent / "missing-parent" / "upload-map.json"
        with self.assertRaisesRegex(ValueError, "parent must already exist"):
            publisher.prepare_uploads(
                handoff,
                target_account_ref="test-visible-account",
                output_path=missing_parent,
            )
        self.assertEqual(provider.uploadimg_calls, 0)
        self.assertEqual(provider.material_calls, 0)

        real_parent = handoff.parent / "real-output-parent"
        real_parent.mkdir()
        linked_parent = handoff.parent / "linked-output-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "must not traverse a symlink"):
            publisher.prepare_uploads(
                handoff,
                target_account_ref="test-visible-account",
                output_path=linked_parent / "upload-map.json",
            )
        self.assertEqual(provider.uploadimg_calls, 0)
        self.assertEqual(provider.material_calls, 0)

    def test_portable_confirmation_requires_a_real_host_signature(self) -> None:
        provider = FakeProvider()
        now = datetime.now(timezone.utc)
        expected = {
            "target_account_ref": "test-visible-account",
            "article_revision": "sha256:" + "1" * 64,
            "draft_media_id": "draft-media-id",
            "draft_payload_sha256": "sha256:" + "2" * 64,
            "compile_report_sha256": "sha256:" + "3" * 64,
            "readback_sha256": "sha256:" + "4" * 64,
        }
        handwritten = {
            "schema_version": 1,
            "source": CONFIRMATION_SOURCE,
            "action": "freepublish",
            **{key: value for key, value in expected.items() if key != "draft_payload_sha256" and key != "readback_sha256"},
            "nonce": "ab" * 16,
            "confirmed_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
        }
        with self.assertRaisesRegex(ValueError, "missing or unsigned extra fields"):
            verify_host_publication_confirmation_receipt(handwritten, **expected)
        self.assertEqual(provider.submit_calls, 0)

        receipt = {
            "schema_version": 1,
            "source": PUBLICATION_CONFIRMATION_RECEIPT_SOURCE,
            "signature_algorithm": "ed25519",
            "key_id": "test-host-receipt-key",
            "nonce": "cd" * 16,
            "provider": "test-user-confirmation-provider",
            "session_id": "test-host-session",
            "request_id": "test-confirmation-request",
            "confirmation_event_id": "test-user-click-event",
            "action": "freepublish",
            "user_intent": "explicit-publish-confirmation",
            **expected,
            "confirmed_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
        }
        encoded = json.dumps(
            receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        receipt["signature"] = "ed25519:" + base64.b64encode(
            transport_test_helpers.TransportFidelityTests.LIVE_RECEIPT_PRIVATE_KEY.sign(
                encoded
            )
        ).decode("ascii")
        with patch(
            "transport_fidelity._host_receipt_trust_material",
            return_value=(
                "test-host-receipt-key",
                transport_test_helpers.TransportFidelityTests.LIVE_RECEIPT_PRIVATE_KEY.public_key(),
            ),
        ):
            nonce, expires_at = verify_host_publication_confirmation_receipt(
                receipt, **expected
            )
            self.assertEqual(nonce, "cd" * 16)
            self.assertGreater(expires_at, now)
            forged = dict(receipt)
            forged["readback_sha256"] = "sha256:" + "5" * 64
            with self.assertRaisesRegex(ValueError, "not bound"):
                verify_host_publication_confirmation_receipt(forged, **expected)
        self.assertEqual(provider.submit_calls, 0)

    def test_portable_publish_rejects_handwritten_confirmation_before_submit(self) -> None:
        case, handoff, _manifest, provider, store, publisher = self.make_context()
        upload_map = handoff.parent / "portable-upload-map.json"
        publisher.prepare_uploads(
            handoff,
            target_account_ref="test-visible-account",
            output_path=upload_map,
        )
        output = handoff.parent / "portable-compiled"
        live_root = case.live_root(handoff, output / "wechat.html")
        trust_patch = patch(
            "transport_fidelity._host_receipt_trust_material",
            return_value=(
                "test-host-receipt-key",
                transport_test_helpers.TransportFidelityTests.LIVE_RECEIPT_PRIVATE_KEY.public_key(),
            ),
        )
        with (
            trust_patch,
            patch("secure_runtime.require_secure_runtime"),
            patch("transport_fidelity._require_secure_transport_finalization_runtime"),
        ):
            compiled = compile_frozen_transport(
                handoff,
                output,
                live_root_path=live_root,
                live_receipt_path=case.live_receipt(handoff),
                upload_map_path=upload_map,
                check=True,
            )
            self.assertTrue(compiled["ok"], compiled)
            saved = publisher.save_draft(
                handoff,
                output / "compile-report.json",
                target_account_ref="test-visible-account",
            )

            screenshot = handoff.parent / "portable-wechat-chapter.png"
            image = Image.open(handoff.parent / "ardot-chapter-1.png").convert("RGBA")
            pixel = image.getpixel((0, 0))
            image.putpixel(
                (0, 0), ((pixel[0] + 1) % 256, pixel[1], pixel[2], pixel[3])
            )
            image.save(screenshot)
            now = datetime.now(timezone.utc)
            screenshot_manifest = handoff.parent / "portable-screenshots.json"
            screenshot_manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "source": "wechat-host-chapter-screenshots-v1",
                        "target_account_ref": "test-visible-account",
                        "draft_id": saved["media_id"],
                        "chapters": [
                            {
                                "chapter_id": "chapter-1",
                                "path": str(screenshot),
                                "captured_at": now.isoformat(),
                                "capture_event_id": "portable-host-capture-0001",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            captured = publisher.capture_readback(
                handoff,
                output / "compile-report.json",
                media_id=saved["media_id"],
                target_account_ref="test-visible-account",
                output_dir=handoff.parent / "portable-readback",
                viewport_review_path=synthetic_viewport_review(handoff, provider, saved["media_id"]),
                screenshot_manifest_path=screenshot_manifest,
            )
            readback = Path(captured["readback"])
            readback_receipt = case.write_readback_receipt(
                handoff,
                readback=readback,
                compiled_html=output / "wechat.html",
                compile_report=output / "compile-report.json",
            )

            def binding(path: Path) -> dict:
                return {"path": str(path.resolve()), "sha256": _file_digest(path)}

            gate = handoff.parent / "portable-publication-gate.json"
            gate.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "source": "wechat-publication-input-bindings-v2",
                        "assurance_scope": "portable-signed",
                        "target_account_ref": "test-visible-account",
                        "article_revision": compiled["revision_hash"],
                        "draft_media_id": saved["media_id"],
                        "handoff": binding(handoff),
                        "compile_report": binding(output / "compile-report.json"),
                        "upload_map": binding(upload_map),
                        "readback": binding(readback),
                        "watermark_report": binding(
                            readback.parent / "watermark-carrier-census.json"
                        ),
                        "live_root": binding(live_root),
                        "live_receipt": binding(case.live_receipt(handoff)),
                        "readback_receipt": binding(readback_receipt),
                        "mobile_profile": None,
                    }
                ),
                encoding="utf-8",
            )
            handwritten = handoff.parent / "handwritten-confirmation.json"
            handwritten.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "source": CONFIRMATION_SOURCE,
                        "action": "freepublish",
                        "target_account_ref": "test-visible-account",
                        "article_revision": compiled["revision_hash"],
                        "draft_media_id": saved["media_id"],
                        "compile_report_sha256": _file_digest(
                            output / "compile-report.json"
                        ),
                        "nonce": "ef" * 16,
                        "confirmed_at": now.isoformat(),
                        "expires_at": (now + timedelta(minutes=5)).isoformat(),
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "missing or unsigned extra fields"):
                publisher.publish(
                    target_account_ref="test-visible-account",
                    article_revision=compiled["revision_hash"],
                    compile_report_path=output / "compile-report.json",
                    confirmation_path=handwritten,
                    publication_gate_path=gate,
                    poll_attempts=1,
                    sleeper=lambda _: None,
                )
            self.assertEqual(provider.submit_calls, 0)

            receipt = {
                "schema_version": 1,
                "source": PUBLICATION_CONFIRMATION_RECEIPT_SOURCE,
                "signature_algorithm": "ed25519",
                "key_id": "test-host-receipt-key",
                "nonce": "fa" * 16,
                "provider": "test-user-confirmation-provider",
                "session_id": "test-portable-session",
                "request_id": "test-portable-request",
                "confirmation_event_id": "test-portable-confirmation-event",
                "action": "freepublish",
                "user_intent": "explicit-publish-confirmation",
                "target_account_ref": "test-visible-account",
                "article_revision": compiled["revision_hash"],
                "draft_media_id": saved["media_id"],
                "draft_payload_sha256": saved["payload_sha256"],
                "compile_report_sha256": _file_digest(
                    output / "compile-report.json"
                ),
                "readback_sha256": _file_digest(readback),
                "confirmed_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=5)).isoformat(),
            }
            encoded = json.dumps(
                receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            receipt["signature"] = "ed25519:" + base64.b64encode(
                transport_test_helpers.TransportFidelityTests.LIVE_RECEIPT_PRIVATE_KEY.sign(
                    encoded
                )
            ).decode("ascii")
            signed_confirmation = handoff.parent / "signed-confirmation.json"
            signed_confirmation.write_text(json.dumps(receipt), encoding="utf-8")
            published = publisher.publish(
                target_account_ref="test-visible-account",
                article_revision=compiled["revision_hash"],
                compile_report_path=output / "compile-report.json",
                confirmation_path=signed_confirmation,
                publication_gate_path=gate,
                poll_attempts=1,
                sleeper=lambda _: None,
            )
            self.assertEqual(published["state"], "published")
            self.assertTrue(published["portable_audit_verified"])
            self.assertEqual(
                published["publication_authority_assurance"],
                "portable-host-signed",
            )
            self.assertEqual(provider.submit_calls, 1)

    def test_unsafe_http_and_protocol_failures_are_ambiguous(self) -> None:
        responses = [
            HTTPResponse(500, {}, b'{"errcode":-1,"errmsg":"busy"}'),
            HTTPResponse(200, {}, b"truncated"),
        ]
        for response in responses:
            provider = WeChatAPIProvider(
                access_token="secret-token",
                app_id="appid12",
                transport=lambda *args, value=response: value,
                sleeper=lambda _: None,
            )
            with self.assertRaises(AmbiguousMutation):
                provider.draft_add([{"title": "already may have committed"}])
            with tempfile.TemporaryDirectory() as directory:
                image = Path(directory) / "image.png"
                image.write_bytes(b"\x89PNG\r\n\x1a\nbytes")
                with self.assertRaises(AmbiguousMutation):
                    provider.uploadimg(image)

    def test_upload_claim_is_atomic_across_store_connections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "publisher.sqlite3"
            first = PublisherStore(database)
            second = PublisherStore(database)
            self.addCleanup(first.close)
            self.addCleanup(second.close)
            self.assertIsNone(first.claim_upload("account", "sha256:test", "body"))
            with self.assertRaisesRegex(AmbiguousMutation, "pending"):
                second.claim_upload("account", "sha256:test", "body")
            committed = {
                "url": "https://mmbiz.qpic.cn/test",
                "media_id": None,
                "response_sha256": "sha256:" + "1" * 64,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }
            first.finish_upload("account", "sha256:test", "body", committed)
            self.assertEqual(
                second.claim_upload("account", "sha256:test", "body"), committed
            )

    def test_publisher_store_rejects_symlinks_and_missing_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real.sqlite3"
            alias = root / "alias.sqlite3"
            alias.symlink_to(real)
            with self.assertRaisesRegex(ValueError, "must not traverse a symlink"):
                PublisherStore(alias)
            self.assertFalse(real.exists())

            real_parent = root / "real-parent"
            real_parent.mkdir()
            parent_alias = root / "parent-alias"
            parent_alias.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "must not traverse a symlink"):
                PublisherStore(parent_alias / "publisher.sqlite3")
            self.assertEqual(list(real_parent.iterdir()), [])

            missing = root / "missing" / "publisher.sqlite3"
            with self.assertRaisesRegex(ValueError, "parent must already exist"):
                PublisherStore(missing)
            self.assertFalse(missing.parent.exists())

    def test_upload_and_draft_transactions_are_idempotent_and_default_to_draft(self) -> None:
        case, handoff, manifest, provider, store, publisher = self.make_context()
        upload_a = handoff.parent / "upload-a.json"
        upload_b = handoff.parent / "upload-b.json"
        first = publisher.prepare_uploads(
            handoff,
            target_account_ref="test-visible-account",
            output_path=upload_a,
        )
        body_call_count = provider.uploadimg_calls
        second = publisher.prepare_uploads(
            handoff,
            target_account_ref="test-visible-account",
            output_path=upload_b,
        )
        self.assertEqual(provider.uploadimg_calls, body_call_count)
        self.assertEqual(provider.material_calls, 1)
        self.assertEqual(first["body_assets"], second["body_assets"])

        output = handoff.parent / "compiled"
        live_root = case.live_root(handoff, output / "wechat-candidate.html")
        with patch("secure_runtime.require_secure_runtime"):
            compiled = compile_frozen_session_draft(
                handoff,
                output,
                live_root_path=live_root,
                upload_map_path=upload_a,
                check=True,
            )
        self.assertTrue(compiled["ok"], compiled)
        detached_store = PublisherStore(handoff.parent / "detached.sqlite3")
        self.addCleanup(detached_store.close)
        detached_publisher = WeChatPublisher(FakeProvider(), detached_store)
        with self.assertRaisesRegex(ValueError, "committed account preflight"):
            detached_publisher.save_draft(
                handoff,
                output / "candidate-report.json",
                target_account_ref="test-visible-account",
            )
        saved = publisher.save_draft(
            handoff,
            output / "candidate-report.json",
            target_account_ref="test-visible-account",
        )
        replay = publisher.save_draft(
            handoff,
            output / "candidate-report.json",
            target_account_ref="test-visible-account",
        )
        self.assertEqual(saved["media_id"], replay["media_id"])
        self.assertEqual(provider.draft_add_calls, 1)
        self.assertEqual(provider.submit_calls, 0)
        self.assertFalse(saved["published"])
        provider.saved_article["title"] = "remote-tamper"
        repaired = publisher.save_draft(
            handoff,
            output / "candidate-report.json",
            target_account_ref="test-visible-account",
        )
        self.assertEqual(repaired["state"], "draft-saved")
        self.assertEqual(provider.draft_update_calls, 1)
        self.assertEqual(provider.saved_article["title"], manifest["article"]["title"])

        forged = json.loads(
            (output / "candidate-report.json").read_text(encoding="utf-8")
        )
        forged["assurance_scope"] = "diagnostic-candidate"
        forged_path = output / "forged-candidate-report.json"
        forged_path.write_text(json.dumps(forged), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "diagnostic candidates"):
            publisher.save_draft(
                handoff,
                forged_path,
                target_account_ref="test-visible-account",
            )

    def test_interrupted_upload_batch_resumes_from_journal_without_reupload(self) -> None:
        _case, handoff, _manifest, provider, _store, publisher = self.make_context()
        upload_map = handoff.parent / "resumable-upload-map.json"
        original_add_material = provider.add_material
        failed_once = False

        def fail_known_cover(path: Path, *, material_type: str = "image") -> dict:
            nonlocal failed_once
            if not failed_once:
                failed_once = True
                raise ValueError("known local cover failure")
            return original_add_material(path, material_type=material_type)

        provider.add_material = fail_known_cover
        with self.assertRaisesRegex(ValueError, "known local cover failure"):
            publisher.prepare_uploads(
                handoff,
                target_account_ref="test-visible-account",
                output_path=upload_map,
            )
        first_body_calls = provider.uploadimg_calls
        self.assertGreater(first_body_calls, 0)
        self.assertEqual(provider.material_calls, 0)
        self.assertFalse(upload_map.exists())

        journal = upload_map.with_name(
            f".{upload_map.name}.upload-journal.jsonl"
        )
        events_before = [
            json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()
        ]
        self.assertIn("upload-failed", [event["event"] for event in events_before])

        result = publisher.prepare_uploads(
            handoff,
            target_account_ref="test-visible-account",
            output_path=upload_map,
        )
        self.assertTrue(upload_map.is_file())
        self.assertEqual(provider.uploadimg_calls, first_body_calls)
        self.assertEqual(provider.material_calls, 1)
        self.assertEqual(result["cover"]["status"], "uploaded")
        events_after = [
            json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()
        ]
        self.assertIn("resumed", [event["event"] for event in events_after])
        self.assertEqual(events_after[-1]["event"], "final-map-committed")

        body_calls = provider.uploadimg_calls
        material_calls = provider.material_calls
        with self.assertRaisesRegex(ValueError, "already exists"):
            publisher.prepare_uploads(
                handoff,
                target_account_ref="test-visible-account",
                output_path=upload_map,
            )
        self.assertEqual(provider.uploadimg_calls, body_calls)
        self.assertEqual(provider.material_calls, material_calls)

    def test_upload_journal_refuses_replacement_or_inconsistent_store(self) -> None:
        _case, handoff, _manifest, provider, store, publisher = self.make_context()
        upload_map = handoff.parent / "store-bound-upload-map.json"
        provider.add_material = lambda path, material_type="image": (_ for _ in ()).throw(
            ValueError("known cover failure")
        )
        with self.assertRaisesRegex(ValueError, "known cover failure"):
            publisher.prepare_uploads(
                handoff,
                target_account_ref="test-visible-account",
                output_path=upload_map,
            )
        body_calls = provider.uploadimg_calls
        material_calls = provider.material_calls
        self.assertGreater(body_calls, 0)

        replacement_store = PublisherStore(handoff.parent / "replacement-publisher.sqlite3")
        self.addCleanup(replacement_store.close)
        replacement = WeChatPublisher(provider, replacement_store)
        with self.assertRaisesRegex(ValueError, "reconcile manually"):
            replacement.prepare_uploads(
                handoff,
                target_account_ref="test-visible-account",
                output_path=upload_map,
            )
        self.assertEqual(provider.uploadimg_calls, body_calls)
        self.assertEqual(provider.material_calls, material_calls)

        committed = store.connection.execute(
            "SELECT source_sha256 FROM uploads WHERE target_account_ref=? "
            "AND kind='body' AND state='complete' LIMIT 1",
            ("test-visible-account",),
        ).fetchone()
        self.assertIsNotNone(committed)
        store.connection.execute(
            "DELETE FROM uploads WHERE target_account_ref=? AND source_sha256=? AND kind='body'",
            ("test-visible-account", committed["source_sha256"]),
        )
        with self.assertRaisesRegex(ValueError, "reconcile manually"):
            publisher.prepare_uploads(
                handoff,
                target_account_ref="test-visible-account",
                output_path=upload_map,
            )
        self.assertEqual(provider.uploadimg_calls, body_calls)
        self.assertEqual(provider.material_calls, material_calls)

    def test_interaction_probe_updates_existing_draft_and_never_becomes_publishable(self) -> None:
        (
            case,
            handoff,
            _manifest,
            provider,
            store,
            publisher,
            upload_map,
            baseline_output,
            _baseline_live_root,
            baseline,
        ) = self.prepare_and_compile()
        saved = publisher.save_draft(
            handoff,
            baseline_output / "candidate-report.json",
            target_account_ref="test-visible-account",
        )
        self.assertEqual(baseline["selected_payload"], "static")

        probe_output = handoff.parent / "interaction-probe"
        probe_live_root = case.live_root(
            handoff, probe_output / "wechat-candidate.html"
        )
        with patch("secure_runtime.require_secure_runtime"):
            probe = compile_frozen_session_draft(
                handoff,
                probe_output,
                live_root_path=probe_live_root,
                upload_map_path=upload_map,
                interaction_probe=True,
                check=True,
            )
        self.assertTrue(probe["ok"], probe)
        self.assertEqual(probe["selected_payload"], "dynamic")
        self.assertEqual(
            probe["assurance_scope"], "current-session-interaction-probe"
        )
        self.assertTrue(probe["interaction_probe_only"])
        self.assertFalse(probe["draft_write_eligible"])
        self.assertFalse(probe["publication_preflight_eligible"])

        updated = publisher.save_draft(
            handoff,
            probe_output / "candidate-report.json",
            target_account_ref="test-visible-account",
        )
        self.assertEqual(updated["media_id"], saved["media_id"])
        self.assertFalse(updated["created"])
        self.assertEqual(provider.draft_add_calls, 1)
        self.assertEqual(provider.draft_update_calls, 1)

        captured = publisher.capture_readback(
            handoff,
            probe_output / "candidate-report.json",
            media_id=saved["media_id"],
            target_account_ref="test-visible-account",
            output_dir=handoff.parent / "interaction-probe-readback",
            viewport_review_path=synthetic_viewport_review(handoff, provider, saved["media_id"]),
            screenshot_manifest_path=None,
        )
        validation = validate_transport_fidelity_diagnostic(
            handoff,
            html_path=probe_output / "wechat-candidate.html",
            live_root_path=probe_live_root,
            require_live_root=True,
            compile_report_path=probe_output / "candidate-report.json",
            require_compile_report=True,
            readback_path=Path(captured["readback"]),
            require_readback=True,
            expected_target_account_ref="test-visible-account",
            upload_map_path=upload_map,
            require_upload_map=True,
        )
        self.assertTrue(validation["ok"], validation)
        self.assertEqual(
            validation["assurance_scope"], "current-session-interaction-probe"
        )
        self.assertFalse(validation["current_session_publication_preflight_eligible"])

        # Synthetic two-device review exercises the real compiler -> publisher
        # interface. It is not evidence of a live WeChat interaction.
        from scripts.wechat_interaction_policy import MOBILE_PROFILE_SOURCE, POLICY_VERSION
        raw_content = handoff.parent / "synthetic-interaction-readback.html"
        raw_content.write_text(provider.saved_article["content"])
        now = datetime.now(timezone.utc)
        profile = {"schema_version": 2, "source": MOBILE_PROFILE_SOURCE, "signature_algorithm": None,
            "assurance_scope": "current-session-editor-reviewed", "key_id": None, "signature": None,
            "nonce": "12" * 16, "policy_version": POLICY_VERSION, "status": "passed", "target_account_id": provider.account_ref,
            "draft_id": saved["media_id"], "verified_at": now.isoformat(), "valid_until": (now + timedelta(hours=1)).isoformat(),
            "probe_sha256": _file_digest(raw_content), "readback_sha256": _file_digest(raw_content),
            "host_session_id": "synthetic-test", "host_trace_sha256": "sha256:" + "1" * 64,
            "editor_review": {"reviewed_by": "synthetic-editor", "review_event_id": "synthetic-review", "scope": "exact-draft-and-both-mobile-interactions"}, "clients": []}
        for platform in ("ios", "android"):
            screenshot = handoff.parent / f"synthetic-{platform}.png"
            Image.new("RGB", (390, 844), "white" if platform == "ios" else "ivory").save(screenshot)
            profile["clients"].append({"platform": platform, "wechat_version": "synthetic", "result": "passed",
                "preview_evidence": {"path": screenshot.name, "sha256": _file_digest(screenshot), "byte_length": screenshot.stat().st_size,
                    "captured_at": now.isoformat(), "device_session_id": platform}})
        profile_path = handoff.parent / "synthetic-mobile-review.json"
        profile_path.write_text(json.dumps(profile))
        reviewed_output = handoff.parent / "editor-reviewed"
        reviewed_live_root = case.live_root(handoff, reviewed_output / "wechat-candidate.html")
        with patch("secure_runtime.require_secure_runtime"):
            reviewed = compile_frozen_session_draft(handoff, reviewed_output, live_root_path=reviewed_live_root,
                upload_map_path=upload_map, mobile_profile_path=profile_path, interaction_readback_path=raw_content,
                allow_editor_review=True, check=True)
        self.assertTrue(reviewed["ok"], reviewed)
        self.assertEqual(reviewed["selected_payload"], "dynamic", reviewed)
        with self.assertRaisesRegex(ValueError, "mobile/readback evidence is invalid"):
            publisher.save_draft(handoff, reviewed_output / "candidate-report.json", target_account_ref=provider.account_ref)
        publisher.allow_editor_review = True
        reviewed_saved = publisher.save_draft(handoff, reviewed_output / "candidate-report.json", target_account_ref=provider.account_ref)
        self.assertEqual(reviewed_saved["media_id"], saved["media_id"])
        self.assertEqual(provider.draft_add_calls, 1)
        self.assertEqual(provider.submit_calls, 0)

        store.connection.execute(
            "DELETE FROM drafts WHERE target_account_ref=? AND article_revision=?",
            ("test-visible-account", probe["revision_hash"]),
        )
        with self.assertRaisesRegex(ValueError, "only update an existing saved draft"):
            publisher.save_draft(
                handoff,
                probe_output / "candidate-report.json",
                target_account_ref="test-visible-account",
            )

    def test_ambiguous_upload_is_not_replayed(self) -> None:
        case, handoff, manifest, provider, store, publisher = self.make_context()
        provider.uploadimg = lambda path: (_ for _ in ()).throw(
            AmbiguousMutation("unknown outcome")
        )
        with self.assertRaises(AmbiguousMutation):
            publisher.prepare_uploads(
                handoff,
                target_account_ref="test-visible-account",
                output_path=handoff.parent / "ambiguous-map.json",
            )
        with self.assertRaisesRegex(AmbiguousMutation, "reconcile before retry"):
            publisher.prepare_uploads(
                handoff,
                target_account_ref="test-visible-account",
                output_path=handoff.parent / "retry-map.json",
            )

    def test_capture_destinations_fail_before_account_or_provider_calls(self) -> None:
        (
            _case,
            handoff,
            _manifest,
            provider,
            _store,
            publisher,
            _upload_map,
            output,
            _live_root,
            _compiled,
        ) = self.prepare_and_compile()
        saved = publisher.save_draft(
            handoff,
            output / "candidate-report.json",
            target_account_ref="test-visible-account",
        )

        existing_raw = handoff.parent / "existing-raw.json"
        existing_raw.write_bytes(b"do-not-overwrite\n")
        symlink_target = handoff.parent / "raw-symlink-target.json"
        symlink_target.write_bytes(b"target-must-not-change\n")
        direct_raw_link = handoff.parent / "raw-direct-link.json"
        direct_raw_link.symlink_to(symlink_target)
        raw_real_parent = handoff.parent / "raw-real-parent"
        raw_real_parent.mkdir()
        raw_parent_link = handoff.parent / "raw-parent-link"
        raw_parent_link.symlink_to(raw_real_parent, target_is_directory=True)
        raw_cases = [
            existing_raw,
            direct_raw_link,
            raw_parent_link / "raw.json",
            handoff.parent / "raw-missing-parent" / "raw.json",
            runtime_test_helpers.ROOT / "forbidden-runtime-raw.json",
        ]
        for destination in raw_cases:
            with self.subTest(raw_destination=destination):
                with patch.object(
                    publisher,
                    "_require_provider_account",
                    wraps=publisher._require_provider_account,
                ) as account_check:
                    with self.assertRaises(ValueError):
                        publisher.capture_raw_draft(
                            saved["media_id"],
                            target_account_ref="test-visible-account",
                            output_path=destination,
                        )
                    account_check.assert_not_called()
                self.assertEqual(provider.draft_get_calls, 0)
        self.assertEqual(existing_raw.read_bytes(), b"do-not-overwrite\n")
        self.assertEqual(symlink_target.read_bytes(), b"target-must-not-change\n")
        self.assertEqual(list(raw_real_parent.iterdir()), [])
        self.assertFalse((handoff.parent / "raw-missing-parent").exists())

        existing_readback_file = handoff.parent / "existing-readback-file"
        existing_readback_file.write_bytes(b"do-not-overwrite\n")
        real_readback_dir = handoff.parent / "real-readback-dir"
        real_readback_dir.mkdir()
        direct_readback_link = handoff.parent / "direct-readback-link"
        direct_readback_link.symlink_to(
            real_readback_dir,
            target_is_directory=True,
        )
        readback_real_parent = handoff.parent / "readback-real-parent"
        readback_real_parent.mkdir()
        readback_parent_link = handoff.parent / "readback-parent-link"
        readback_parent_link.symlink_to(
            readback_real_parent,
            target_is_directory=True,
        )
        readback_cases = [
            existing_readback_file,
            real_readback_dir,
            direct_readback_link,
            readback_parent_link / "new-readback",
            handoff.parent / "readback-missing-parent" / "new-readback",
            runtime_test_helpers.ROOT / "forbidden-runtime-readback",
        ]
        for destination in readback_cases:
            with self.subTest(readback_destination=destination):
                with patch.object(
                    publisher,
                    "_require_provider_account",
                    wraps=publisher._require_provider_account,
                ) as account_check:
                    with self.assertRaises(ValueError):
                        publisher.capture_readback(
                            handoff,
                            output / "candidate-report.json",
                            media_id=saved["media_id"],
                            target_account_ref="test-visible-account",
                            output_dir=destination,
                            screenshot_manifest_path=None,
                        )
                    account_check.assert_not_called()
                self.assertEqual(provider.draft_get_calls, 0)
                self.assertEqual(provider.transport_calls, 0)
        self.assertEqual(existing_readback_file.read_bytes(), b"do-not-overwrite\n")
        self.assertEqual(list(real_readback_dir.iterdir()), [])
        self.assertEqual(list(readback_real_parent.iterdir()), [])
        self.assertFalse((handoff.parent / "readback-missing-parent").exists())

    def test_capture_raw_cli_collision_stops_before_account_and_draft_get(self) -> None:
        (
            _case,
            handoff,
            _manifest,
            provider,
            _store,
            publisher,
            _upload_map,
            output,
            _live_root,
            _compiled,
        ) = self.prepare_and_compile()
        saved = publisher.save_draft(
            handoff,
            output / "candidate-report.json",
            target_account_ref="test-visible-account",
        )
        collision = handoff.parent / "cli-existing-raw.json"
        collision.write_bytes(b"cli-do-not-overwrite\n")
        argv = [
            "wechat_publisher.py",
            "--store",
            str(handoff.parent / "publisher.sqlite3"),
            "capture-raw",
            saved["media_id"],
            "--target-account",
            "test-visible-account",
            "--output",
            str(collision),
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.dict(
                os.environ,
                {
                    "WECHAT_ACCESS_TOKEN": "test-secret-token",
                    "WECHAT_APP_ID": "testappid",
                },
            ),
            patch.object(
                publisher_module,
                "WeChatAPIProvider",
                return_value=provider,
            ),
            patch.object(
                publisher_module.WeChatPublisher,
                "_require_provider_account",
                autospec=True,
            ) as account_check,
        ):
            with self.assertRaises(ValueError):
                publisher_module.main()
            account_check.assert_not_called()
        self.assertEqual(provider.draft_get_calls, 0)
        self.assertEqual(collision.read_bytes(), b"cli-do-not-overwrite\n")

    def test_installed_browser_capture_bundle_e2e_and_forgery_rejection(self) -> None:
        (
            _case,
            handoff,
            _manifest,
            provider,
            store,
            publisher,
            upload_map,
            output,
            live_root,
            compiled,
        ) = self.prepare_and_compile()
        saved = publisher.save_draft(
            handoff,
            output / "candidate-report.json",
            target_account_ref="test-visible-account",
        )
        raw_path = handoff.parent / "api-draft-get-raw.json"
        publisher.capture_raw_draft(
            saved["media_id"],
            target_account_ref="test-visible-account",
            output_path=raw_path,
        )
        self.assertEqual(provider.draft_get_calls, 1)
        bundle_result = self.make_capture_bundle(
            handoff=handoff,
            compile_report=output / "candidate-report.json",
            raw_draft=raw_path,
            saved=saved,
            compiled=compiled,
            nonce="readback_capture_nonce_000000000001",
            output_dir=handoff.parent / "ingested-readback-capture",
        )
        bundle_path = Path(bundle_result["bundle"])
        original_bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        self.assertFalse(bundle_result["host_attested"])
        self.assertFalse(bundle_result["portable"])
        self.assertFalse(bundle_result["publication_authority"])

        variants: dict[str, callable] = {
            "wrong-account": lambda value: value["target"].__setitem__(
                "target_account_ref", "wrong-account"
            ),
            "wrong-draft": lambda value: value["target"].__setitem__(
                "draft_id", "wrong-draft"
            ),
            "wrong-revision": lambda value: value["target"].__setitem__(
                "article_revision", "sha256:" + "1" * 64
            ),
            "wrong-raw-sha": lambda value: value["raw_draft"].__setitem__(
                "sha256", "sha256:" + "2" * 64
            ),
            "wrong-census": lambda value: value["runtime"][
                "registry_census"
            ].__setitem__("sha256", "sha256:" + "3" * 64),
            "wrong-session": lambda value: value["runtime"]["host"].__setitem__(
                "session_id", "wrong-session"
            ),
            "credential-url": lambda value: value["browser_observation"].__setitem__(
                "credential_free_url",
                "https://mp.weixin.qq.com/cgi-bin/appmsg?token=secret",
            ),
            "capture-after-bundle": lambda value: value["chapters"][0].__setitem__(
                "captured_at",
                (
                    datetime.fromisoformat(value["created_at"])
                    + timedelta(seconds=1)
                ).isoformat(),
            ),
            "fake-portable": lambda value: value.__setitem__("portable", True),
            "fake-authority-boundary": lambda value: value.__setitem__(
                "truth_boundary", "portable host authority"
            ),
            "duplicate-chapter-bytes": lambda value: value["chapters"].append(
                dict(value["chapters"][0])
            ),
        }
        provider_counts = (provider.draft_get_calls, provider.transport_calls)
        for name, mutate in variants.items():
            with self.subTest(bundle_forgery=name):
                forged = json.loads(json.dumps(original_bundle))
                mutate(forged)
                forged_path = handoff.parent / f"forged-{name}.json"
                forged_path.write_text(
                    json.dumps(forged, ensure_ascii=False),
                    encoding="utf-8",
                )
                with self.assertRaises((ValueError, ReadbackCaptureIngestionError)):
                    WeChatPublisher(provider, store).capture_readback(
                        handoff,
                        output / "candidate-report.json",
                        media_id=saved["media_id"],
                        target_account_ref="test-visible-account",
                        output_dir=handoff.parent / f"rejected-{name}",
                        screenshot_manifest_path=None,
                        capture_bundle_path=forged_path,
                    )
                self.assertEqual(
                    (provider.draft_get_calls, provider.transport_calls),
                    provider_counts,
                )

        runtime = original_bundle["runtime"]
        with self.assertRaisesRegex(
            ReadbackCaptureIngestionError,
            "Ardot reference cannot masquerade",
        ):
            ingest_wechat_readback_capture(
                handoff_path=handoff,
                compile_report_path=output / "candidate-report.json",
                raw_draft_path=raw_path,
                runtime_profile_path=Path(runtime["profile"]["path"]),
                runtime_report_path=Path(runtime["binding_report"]["path"]),
                registry_census_path=Path(runtime["registry_census"]["path"]),
                target_account_ref="test-visible-account",
                draft_id=saved["media_id"],
                article_revision=compiled["revision_hash"],
                host_session_id=runtime["host"]["session_id"],
                capture_tool_id=runtime["host"]["capture_tool_id"],
                observed_url="https://mp.weixin.qq.com/cgi-bin/appmsg",
                nonce="readback_capture_nonce_ardot_000001",
                chapter_captures=[
                    {
                        "chapter_id": "chapter-1",
                        "path": handoff.parent / "ardot-chapter-1.png",
                        "captured_at": datetime.now(timezone.utc).isoformat(),
                        "capture_event_id": "ardot-reference-event-0001",
                    }
                ],
                output_dir=handoff.parent / "rejected-ardot-reference",
            )
        self.assertFalse((handoff.parent / "rejected-ardot-reference").exists())

        standalone = WeChatPublisher(provider, store)
        captured = standalone.capture_readback(
            handoff,
            output / "candidate-report.json",
            media_id=saved["media_id"],
            target_account_ref="test-visible-account",
            output_dir=handoff.parent / "browser-bundle-readback",
            viewport_review_path=synthetic_viewport_review(handoff, provider, saved["media_id"]),
            screenshot_manifest_path=None,
            capture_bundle_path=bundle_path,
        )
        self.assertEqual(captured["assurance_scope"], "current-session-readback-nonportable")
        self.assertFalse(captured["host_attested"])
        self.assertFalse(captured["portable"])
        self.assertFalse(captured["publication_authority"])
        self.assertEqual(provider.draft_get_calls, 1)
        readback = Path(captured["readback"])
        validation = validate_transport_fidelity_diagnostic(
            handoff,
            html_path=output / "wechat-candidate.html",
            live_root_path=live_root,
            require_live_root=True,
            compile_report_path=output / "candidate-report.json",
            require_compile_report=True,
            readback_path=readback,
            require_readback=True,
            expected_target_account_ref="test-visible-account",
            upload_map_path=upload_map,
            require_upload_map=True,
        )
        self.assertTrue(validation["ok"], validation)

        provider_counts = (provider.draft_get_calls, provider.transport_calls)
        with self.assertRaisesRegex(ValueError, "nonce has already been consumed"):
            standalone.capture_readback(
                handoff,
                output / "candidate-report.json",
                media_id=saved["media_id"],
                target_account_ref="test-visible-account",
                output_dir=handoff.parent / "replayed-bundle-readback",
                screenshot_manifest_path=None,
                capture_bundle_path=bundle_path,
            )
        self.assertEqual(
            (provider.draft_get_calls, provider.transport_calls),
            provider_counts,
        )
        self.assertFalse((handoff.parent / "replayed-bundle-readback").exists())

        now = datetime.now(timezone.utc)
        confirmation = handoff.parent / "bundle-confirmation.json"
        confirmation.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source": CONFIRMATION_SOURCE,
                    "action": "freepublish",
                    "target_account_ref": "test-visible-account",
                    "article_revision": compiled["revision_hash"],
                    "draft_media_id": saved["media_id"],
                    "compile_report_sha256": _file_digest(
                        output / "candidate-report.json"
                    ),
                    "nonce": "cd" * 16,
                    "confirmed_at": now.isoformat(),
                    "expires_at": (now + timedelta(minutes=5)).isoformat(),
                }
            ),
            encoding="utf-8",
        )

        def binding(path: Path) -> dict:
            return {"path": str(path.resolve()), "sha256": _file_digest(path)}

        gate = handoff.parent / "bundle-publication-gate.json"
        gate.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "source": "wechat-publication-input-bindings-v2",
                    "assurance_scope": "current-session-live",
                    "target_account_ref": "test-visible-account",
                    "article_revision": compiled["revision_hash"],
                    "draft_media_id": saved["media_id"],
                    "handoff": binding(handoff),
                    "compile_report": binding(output / "candidate-report.json"),
                    "upload_map": binding(upload_map),
                    "readback": binding(readback),
                    "watermark_report": binding(
                        readback.parent / "watermark-carrier-census.json"
                    ),
                    "live_root": binding(live_root),
                    "live_receipt": None,
                    "readback_receipt": None,
                    "mobile_profile": None,
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            ValueError,
            "standalone file-only current-session publication",
        ):
            standalone.publish(
                target_account_ref="test-visible-account",
                article_revision=compiled["revision_hash"],
                compile_report_path=output / "candidate-report.json",
                confirmation_path=confirmation,
                publication_gate_path=gate,
                poll_attempts=1,
                sleeper=lambda _: None,
            )
        self.assertEqual(provider.submit_calls, 0)

    def test_v2_readback_and_current_session_publish_without_signer(self) -> None:
        (
            case,
            handoff,
            manifest,
            provider,
            store,
            publisher,
            upload_map,
            output,
            live_root,
            compiled,
        ) = self.prepare_and_compile()
        saved = publisher.save_draft(
            handoff,
            output / "candidate-report.json",
            target_account_ref="test-visible-account",
        )

        good_authority = publisher.current_session_authority
        publisher.current_session_authority = FakeHostAuthority(
            handoff.parent / "ardot-chapter-1.png", mutate_capture=False
        )
        # An independent capture may legitimately render identical pixels.
        identical = publisher.capture_readback(
            handoff,
            output / "candidate-report.json",
            media_id=saved["media_id"],
            target_account_ref="test-visible-account",
            output_dir=handoff.parent / "identical-pixels-readback",
            screenshot_manifest_path=None,
        )
        self.assertEqual(identical["state"], "readback-captured")
        publisher.current_session_authority = good_authority

        captured = publisher.capture_readback(
            handoff,
            output / "candidate-report.json",
            media_id=saved["media_id"],
            target_account_ref="test-visible-account",
            output_dir=handoff.parent / "readback-v2",
            viewport_review_path=synthetic_viewport_review(handoff, provider, saved["media_id"]),
            screenshot_manifest_path=None,
        )
        readback = Path(captured["readback"])
        validation = validate_transport_fidelity_diagnostic(
            handoff,
            html_path=output / "wechat-candidate.html",
            live_root_path=live_root,
            require_live_root=True,
            compile_report_path=output / "candidate-report.json",
            require_compile_report=True,
            readback_path=readback,
            require_readback=True,
            expected_target_account_ref="test-visible-account",
            upload_map_path=upload_map,
            require_upload_map=True,
        )
        self.assertTrue(validation["ok"], validation)
        self.assertTrue(validation["readback_evidence_verified"])
        self.assertEqual(validation["watermark_transport_status"], "not-applicable")
        self.assertTrue(validation["current_session_publication_preflight_eligible"])

        fake_gate = handoff.parent / "fake-gate.json"
        fake_gate.write_text(
            json.dumps({"ok": True, "readback_verified": True}), encoding="utf-8"
        )
        confirmation = handoff.parent / "confirmation.json"
        now = datetime.now(timezone.utc)
        confirmation.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source": CONFIRMATION_SOURCE,
                    "action": "freepublish",
                    "target_account_ref": "test-visible-account",
                    "article_revision": compiled["revision_hash"],
                    "draft_media_id": saved["media_id"],
                    "compile_report_sha256": _file_digest(
                        output / "candidate-report.json"
                    ),
                    "nonce": "ab" * 16,
                    "confirmed_at": now.isoformat(),
                    "expires_at": (now + timedelta(minutes=5)).isoformat(),
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "missing or self-asserted"):
            publisher.publish(
                target_account_ref="test-visible-account",
                article_revision=compiled["revision_hash"],
                compile_report_path=output / "candidate-report.json",
                confirmation_path=confirmation,
                publication_gate_path=fake_gate,
            )
        self.assertEqual(provider.submit_calls, 0)

        def binding(path: Path) -> dict:
            return {"path": str(path.resolve()), "sha256": _file_digest(path)}

        gate = handoff.parent / "publication-gate.json"
        gate.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "source": "wechat-publication-input-bindings-v2",
                    "assurance_scope": "current-session-live",
                    "target_account_ref": "test-visible-account",
                    "article_revision": compiled["revision_hash"],
                    "draft_media_id": saved["media_id"],
                    "handoff": binding(handoff),
                    "compile_report": binding(output / "candidate-report.json"),
                    "upload_map": binding(upload_map),
                    "readback": binding(readback),
                    "watermark_report": binding(
                        readback.parent / "watermark-carrier-census.json"
                    ),
                    "live_root": binding(live_root),
                    "live_receipt": None,
                    "readback_receipt": None,
                    "mobile_profile": None,
                }
            ),
            encoding="utf-8",
        )
        provider.publish_statuses = [
            {"publish_status": 1},
            {
                "publish_status": 0,
                "article_detail": {
                    "item": [{"article_url": "https://mp.weixin.qq.com/s/final"}]
                },
            },
        ]
        standalone = WeChatPublisher(provider, store)
        with self.assertRaisesRegex(
            ValueError, "standalone file-only current-session publication"
        ):
            standalone.publish(
                target_account_ref="test-visible-account",
                article_revision=compiled["revision_hash"],
                compile_report_path=output / "candidate-report.json",
                confirmation_path=confirmation,
                publication_gate_path=gate,
                poll_attempts=1,
                sleeper=lambda _: None,
            )
        self.assertEqual(provider.submit_calls, 0)
        published = publisher.publish(
            target_account_ref="test-visible-account",
            article_revision=compiled["revision_hash"],
            compile_report_path=output / "candidate-report.json",
            confirmation_path=confirmation,
            publication_gate_path=gate,
            poll_attempts=3,
            sleeper=lambda _: None,
        )
        self.assertEqual(published["state"], "published")
        self.assertEqual(
            published["article_urls"], ["https://mp.weixin.qq.com/s/final"]
        )
        self.assertFalse(published["portable_audit_verified"])
        self.assertEqual(
            published["publication_authority_assurance"],
            "trusted-harness-policy-hook-not-independently-attested",
        )
        self.assertEqual(provider.submit_calls, 1)
        with self.assertRaisesRegex(ValueError, "publication job already owns"):
            publisher.save_draft(
                handoff,
                output / "candidate-report.json",
                target_account_ref="test-visible-account",
            )
        self.assertEqual(provider.draft_update_calls, 0)
        resumed = publisher.publish(
            target_account_ref="test-visible-account",
            article_revision=compiled["revision_hash"],
            compile_report_path=output / "candidate-report.json",
            confirmation_path=confirmation,
            publication_gate_path=gate,
            poll_attempts=1,
            sleeper=lambda _: None,
        )
        self.assertEqual(resumed["state"], "published")
        self.assertEqual(provider.submit_calls, 1)
        store.connection.execute(
            "DELETE FROM publication_jobs WHERE target_account_ref=? AND article_revision=?",
            ("test-visible-account", compiled["revision_hash"]),
        )
        crash_recovered = publisher.publish(
            target_account_ref="test-visible-account",
            article_revision=compiled["revision_hash"],
            compile_report_path=output / "candidate-report.json",
            confirmation_path=confirmation,
            publication_gate_path=gate,
            poll_attempts=1,
            sleeper=lambda _: None,
        )
        self.assertEqual(crash_recovered["state"], "published")
        self.assertEqual(provider.submit_calls, 1)
        store.connection.execute(
            "DELETE FROM publication_jobs WHERE target_account_ref=? AND article_revision=?",
            ("test-visible-account", compiled["revision_hash"]),
        )
        operation_key = store.connection.execute(
            "SELECT operation_key FROM operations WHERE kind='freepublish-submit'"
        ).fetchone()[0]
        store.connection.execute(
            "DELETE FROM operations WHERE operation_key=?", (operation_key,)
        )
        with self.assertRaisesRegex(ValueError, "already been consumed"):
            publisher.publish(
                target_account_ref="test-visible-account",
                article_revision=compiled["revision_hash"],
                compile_report_path=output / "candidate-report.json",
                confirmation_path=confirmation,
                publication_gate_path=gate,
                poll_attempts=1,
                sleeper=lambda _: None,
            )

    def test_publication_status_terminal_failures_and_timeout_are_truthful(self) -> None:
        case, handoff, manifest, provider, store, publisher = self.make_context()
        for status, expected in {
            2: "originality-check-failed",
            3: "failed",
            4: "audit-rejected",
            5: "all-articles-deleted",
            6: "all-articles-blocked",
        }.items():
            revision = f"revision-{status}"
            store.connection.execute(
                "INSERT INTO publication_jobs"
                "(target_account_ref,article_revision,draft_media_id,draft_payload_sha256,"
                "compile_report_sha256,publish_id,state,status_code,result_json,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    "account",
                    revision,
                    "draft",
                    "sha256:" + "1" * 64,
                    "sha256:" + "2" * 64,
                    f"job-{status}",
                    "submitted",
                    None,
                    "{}",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            provider.publish_statuses = [{"publish_status": status}]
            result = publisher._poll_publication_status(
                target_account_ref="account",
                article_revision=revision,
                publish_id=f"job-{status}",
                portable=False,
                poll_attempts=1,
                sleeper=lambda _: None,
            )
            self.assertEqual(result["state"], expected)
            self.assertEqual(result["article_urls"], [])
        revision = "revision-timeout"
        store.connection.execute(
            "INSERT INTO publication_jobs"
            "(target_account_ref,article_revision,draft_media_id,draft_payload_sha256,"
            "compile_report_sha256,publish_id,state,status_code,result_json,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                "account",
                revision,
                "draft",
                "sha256:" + "1" * 64,
                "sha256:" + "2" * 64,
                "job-timeout",
                "submitted",
                None,
                "{}",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        provider.publish_statuses = [{"publish_status": 1}]
        result = publisher._poll_publication_status(
            target_account_ref="account",
            article_revision=revision,
            publish_id="job-timeout",
            portable=False,
            poll_attempts=2,
            sleeper=lambda _: None,
        )
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(provider.submit_calls, 0)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from ingest_browser_download import IngestionError, ingest_download  # noqa: E402


class DownloadIngestionTests(unittest.TestCase):
    def arguments(self) -> dict[str, str]:
        return {
            "binding_nonce": "N" * 32,
            "binding_digest": "sha256:" + "1" * 64,
            "provider_session_id": "provider-session-1",
            "provider_request_id": "provider-request-1",
            "observed_download_id": "browser-download-1",
            "request_metadata_sha256": "sha256:" + "2" * 64,
        }

    def test_create_once_copy_binds_source_and_target_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            download = root / "download.png"
            staging = root / "staging"
            staging.mkdir()
            payload = b"\x89PNG\r\n\x1a\n" + b"test-bytes" * 1024
            download.write_bytes(payload)
            target = staging / "provider-original.png"
            report = staging / "ingestion.json"
            result = ingest_download(
                download,
                target,
                report,
                staging,
                **self.arguments(),
            )
            digest = "sha256:" + hashlib.sha256(payload).hexdigest()
            self.assertEqual(target.read_bytes(), payload)
            self.assertEqual(result["source"]["sha256"], digest)
            self.assertEqual(result["target"]["sha256"], digest)
            self.assertFalse(result["browser_event_attested"])
            on_disk = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(on_disk["binding"]["binding_nonce"], "N" * 32)
            self.assertEqual(
                on_disk["truth_boundary"],
                result["truth_boundary"],
            )

    def test_refuses_overwrite_symlink_and_out_of_root_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "source.png"
            source.write_bytes(b"png")
            staging = root / "staging"
            staging.mkdir()
            target = staging / "target.png"
            report = staging / "report.json"
            target.write_bytes(b"old")
            with self.assertRaises(IngestionError):
                ingest_download(source, target, report, staging, **self.arguments())
            target.unlink()
            source_link = root / "source-link.png"
            source_link.symlink_to(source)
            with self.assertRaises(IngestionError):
                ingest_download(source_link, target, report, staging, **self.arguments())
            with self.assertRaises(IngestionError):
                ingest_download(
                    source,
                    root / "outside.png",
                    report,
                    staging,
                    **self.arguments(),
                )


if __name__ == "__main__":
    unittest.main()

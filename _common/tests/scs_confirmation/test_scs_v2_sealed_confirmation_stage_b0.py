import hashlib
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd


downloader = importlib.import_module("ncei.code.scs_confirmation.acquire_scs_v2_sealed_confirmation_stage_b")
verifier = importlib.import_module("ncei.code.scs_confirmation.verify_scs_v2_sealed_confirmation_stage_b")


LOCKED_URL = "https://data.ngdc.noaa.gov/platforms/ocean/test/file.mb58.gz"
LOCKED_LAST_MODIFIED = "Mon, 01 Jan 2024 00:00:00 GMT"


class FakeResponse:
    def __init__(self, *, url=LOCKED_URL, last_modified=LOCKED_LAST_MODIFIED, chunks=None):
        self.status = 200
        self._url = url
        self.headers = {}
        if last_modified is not None:
            self.headers["Last-Modified"] = last_modified
        self._chunks = list(chunks or [])
        self.read_count = 0

    def geturl(self):
        return self._url

    def read(self, _size=-1):
        self.read_count += 1
        return self._chunks.pop(0) if self._chunks else b""

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        return False


class SCSV2SealedConfirmationStageB0Test(unittest.TestCase):
    def test_last_modified_failure_does_not_read_body(self):
        cases = [
            (None, "missing"),
            ("Tue, 02 Jan 2024 00:00:00 GMT", "mismatch"),
        ]
        for response_value, label in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                response = FakeResponse(last_modified=response_value, chunks=[b"forbidden"])
                destination = Path(directory) / "objects" / "test.bin"
                with mock.patch.object(downloader.urllib.request, "urlopen", return_value=response):
                    with self.assertRaises(RuntimeError):
                        downloader.download_object(
                            LOCKED_URL,
                            destination,
                            len(b"forbidden"),
                            LOCKED_LAST_MODIFIED,
                            5,
                            "unit-test",
                        )
                self.assertEqual(response.read_count, 0)
                self.assertFalse(destination.parent.exists())

    def test_redirect_failure_does_not_read_body(self):
        redirected_urls = [
            "https://example.com/platforms/ocean/test/file.mb58.gz",
            "https://data.ngdc.noaa.gov/platforms/ocean/test/replaced.mb58.gz",
        ]
        for redirected_url in redirected_urls:
            with self.subTest(url=redirected_url), tempfile.TemporaryDirectory() as directory:
                response = FakeResponse(url=redirected_url, chunks=[b"forbidden"])
                destination = Path(directory) / "objects" / "test.bin"
                with mock.patch.object(downloader.urllib.request, "urlopen", return_value=response):
                    with self.assertRaises((ValueError, RuntimeError)):
                        downloader.download_object(
                            LOCKED_URL,
                            destination,
                            len(b"forbidden"),
                            LOCKED_LAST_MODIFIED,
                            5,
                            "unit-test",
                        )
                self.assertEqual(response.read_count, 0)
                self.assertFalse(destination.parent.exists())

    def test_authorization_hash_or_run_id_mismatch_has_no_network_request(self):
        final_lock = {"run_id": "20260805T221441Z", "primary_physical_object_lock_sha256": "physical"}
        expected = downloader.authorization_contract(
            final_lock,
            "a2-manifest",
            "a2-verification",
            "a2-final-lock",
            "future-stage-b-run",
            downloader.STAGE_B_OUTPUT_ROOT,
        )
        expected.update({"authorized_by": "user", "authorized_utc": "2026-08-06T00:00:00Z"})
        mutations = {
            "a2_manifest_sha256": "wrong",
            "a2_verification_sha256": "wrong",
            "a2_final_download_lock_sha256": "wrong",
            "primary_physical_object_lock_sha256": "wrong",
            "stage_b_downloader_sha256": "wrong",
            "stage_b_verifier_sha256": "wrong",
            "acquisition_run_id": "other-run",
        }
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            downloader.urllib.request, "urlopen"
        ) as urlopen:
            for key, value in mutations.items():
                with self.subTest(key=key):
                    receipt = dict(expected)
                    receipt[key] = value
                    path = Path(directory) / f"{key}.json"
                    path.write_text(json.dumps(receipt), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        downloader.validate_authorization_receipt(
                            path,
                            final_lock,
                            "a2-manifest",
                            "a2-verification",
                            "a2-final-lock",
                            "future-stage-b-run",
                            downloader.STAGE_B_OUTPUT_ROOT,
                        )
            urlopen.assert_not_called()

    def test_path_escape_and_unsafe_run_ids_are_rejected(self):
        for run_id in (
            "../escape",
            "a/b",
            "a\\b",
            "/absolute",
            "two..dots",
            ".",
            "..",
            "",
            "<REQUIRED_SAFE_SINGLE_SEGMENT_ID>",
        ):
            with self.subTest(run_id=run_id):
                with self.assertRaises(ValueError):
                    downloader.validate_acquisition_run_id(run_id)
        for relative in ("../escape.bin", "objects/OTHER/file.bin", "/objects/TN352/file.bin"):
            with self.subTest(relative=relative):
                with self.assertRaises(AssertionError):
                    verifier.validate_relative_path(relative, "TN352")

    def test_zero_byte_object_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            response = FakeResponse(chunks=[])
            destination = Path(directory) / "objects" / "zero.fnv"
            with mock.patch.object(downloader.urllib.request, "urlopen", return_value=response):
                result = downloader.download_object(
                    LOCKED_URL,
                    destination,
                    0,
                    LOCKED_LAST_MODIFIED,
                    5,
                    "unit-test",
                )
            self.assertEqual(response.read_count, 1)
            self.assertEqual(destination.stat().st_size, 0)
            self.assertEqual(result["sha256"], hashlib.sha256(b"").hexdigest())
            self.assertFalse(result["content_parsed"])

    def test_verifier_detects_post_download_tamper(self):
        payload = b"sealed bytes"
        with tempfile.TemporaryDirectory() as directory:
            acquisition_dir = Path(directory)
            relative = Path("objects/TN352/file.mb58.gz")
            path = acquisition_dir / relative
            path.parent.mkdir(parents=True)
            path.write_bytes(payload)
            path.chmod(0o444)
            frame = pd.DataFrame([{
                "official_cruise_id": "TN352",
                "filename": path.name,
                "source_object_role": "raw_multibeam",
                "format": "mb58.gz",
                "sealed_role": "sealed_unprocessed",
                "original_url": LOCKED_URL,
                "resolved_url": LOCKED_URL,
                "relative_path": relative.as_posix(),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "expected_last_modified": LOCKED_LAST_MODIFIED,
                "response_last_modified": LOCKED_LAST_MODIFIED,
                "etag": "",
                "http_status": 200,
                "downloaded_utc": "2026-08-06T00:00:00Z",
                "content_parsed": False,
            }], columns=verifier.REQUIRED_MANIFEST_COLUMNS)
            result = verifier.verify_downloaded_objects(frame, acquisition_dir)
            self.assertEqual(result["object_count"], 1)
            path.chmod(0o644)
            path.write_bytes(b"tampered")
            with self.assertRaises(AssertionError):
                verifier.verify_downloaded_objects(frame, acquisition_dir)

    def test_downloader_and_verifier_have_no_parser_imports(self):
        downloader_result = verifier.assert_no_parser_logic(Path(downloader.__file__).resolve())
        verifier_result = verifier.assert_no_parser_logic(Path(verifier.__file__).resolve())
        self.assertEqual(downloader_result["forbidden_imports"], 0)
        self.assertEqual(verifier_result["forbidden_calls"], 0)

    def test_failure_receipt_is_machine_readable_and_unsealed(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            retained = run_dir / "objects" / "TN352" / "partial.mb58.gz.part"
            retained.parent.mkdir(parents=True)
            retained.write_bytes(b"partial")
            authorization = run_dir / "authorization.json"
            authorization.write_text("{}\n", encoding="utf-8")
            downloader.write_failure_receipt(
                run_dir,
                RuntimeError("test failure"),
                None,
                [],
                {"physical_object_count": 768, "exact_total_bytes": 9_626_893_507},
                authorization,
                "future-stage-b-run",
            )
            receipt = json.loads((run_dir / "failure_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "failed_unsealed")
            self.assertFalse(receipt["sealed"])
            self.assertEqual(receipt["verification_status"], "not_run")
            self.assertTrue(retained.exists())
            self.assertFalse((run_dir / "sealed_archive_manifest.parquet").exists())


if __name__ == "__main__":
    unittest.main()

import ast
import importlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock


stage_a2 = importlib.import_module("ncei.code.scs_confirmation.finalize_scs_v2_sealed_confirmation_stage_a2")
downloader = importlib.import_module("ncei.code.scs_confirmation.acquire_scs_v2_sealed_confirmation_stage_b")


class SCSV2SealedConfirmationStageA2Test(unittest.TestCase):
    def test_listing_parser_recovers_only_exact_integer_sizes(self):
        body = b"""
        <table>
        <tr><td><a href="zero.fnv">zero.fnv</a></td><td>2020-01-01</td><td>  0 </td></tr>
        <tr><td><a href="rounded.fnv">rounded.fnv</a></td><td>2020-01-01</td><td>3.5K</td></tr>
        </table>
        """
        sizes = stage_a2.parse_exact_listing_sizes(body, "https://data.ngdc.noaa.gov/root/")
        self.assertEqual(sizes, {"https://data.ngdc.noaa.gov/root/zero.fnv": 0})

    def test_primary_set_is_exact_and_ordered(self):
        expected = ["EQT20210702", "EQT190012", "EQT180002", "TN352"]
        stage_a2.validate_primary_ids(expected)
        with self.assertRaises(ValueError):
            stage_a2.validate_primary_ids(expected + ["TN358"])

    def test_download_cap_uses_binary_gib(self):
        self.assertEqual(stage_a2.DOWNLOAD_CAP_BYTES, 12 * 1024**3)
        self.assertTrue(stage_a2.within_download_cap(9_626_893_507, stage_a2.DOWNLOAD_CAP_BYTES))
        self.assertFalse(stage_a2.within_download_cap(stage_a2.DOWNLOAD_CAP_BYTES + 1, stage_a2.DOWNLOAD_CAP_BYTES))

    def test_dry_run_source_has_no_network_call(self):
        source = Path("ncei/code/scs_confirmation/acquire_scs_v2_sealed_confirmation_stage_b.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_dry_run")
        segment = ast.get_source_segment(source, function) or ""
        self.assertNotIn("urlopen", segment)
        self.assertNotIn("Request(", segment)

    def test_execute_rejects_before_network_without_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(downloader.urllib.request, "urlopen") as urlopen:
                with self.assertRaises(ValueError):
                    downloader.validate_authorization_receipt(
                        Path(directory) / "missing.json",
                        {"run_id": "a2", "primary_physical_object_lock_sha256": "lock"},
                        "manifest",
                        "verification",
                        "final-lock",
                        "future-stage-b-run",
                        downloader.STAGE_B_OUTPUT_ROOT,
                    )
                urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()

import hashlib
import unittest
from pathlib import Path

from ncei.code.scs_v2_stage_c_processing import (
    canonical_authorization_receipt_sha256,
    iter_mblist_rows,
    load_output_schemas,
    scan_time_contract,
    sounding_row,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / ".trellis/tasks/08-06-scs-v2-stage-c0-source-internal-planning/research/stage-c01-output-schema.yaml"


class SCSV2StageCProcessingTest(unittest.TestCase):
    def test_missing_and_invalid_time_have_distinct_frozen_codes(self):
        path = REPO_ROOT / ".tmp-stage-c-time-contract.tsv"
        try:
            path.write_text("\t1\t0\t120\t10\t100\t90\n", encoding="ascii")
            self.assertEqual(scan_time_contract(path, check_mode=3)[1], "TIME_UTC_MISSING")
            path.write_text("not-a-time\t1\t0\t120\t10\t100\t90\n", encoding="ascii")
            self.assertEqual(scan_time_contract(path, check_mode=3)[1], "TIME_UTC_INVALID")
        finally:
            path.unlink(missing_ok=True)

    def test_flagged_sounding_keeps_navigation_cell_but_is_not_eligible(self):
        object_record = {
            "relative_path": "objects/TN352/example.mb58.gz",
            "sha256": hashlib.sha256(b"example").hexdigest(),
            "official_cruise_id": "TN352",
        }
        row = sounding_row(
            {
                "source_object_id": "20260805T230449Z/objects/TN352/example.mb58.gz",
                "parser_ping_index": 3,
                "native_ping_counter": 7,
                "beam_index": 2,
                "epoch_us": 1_700_000_000_000_000,
                "lon_deg": 120.0,
                "lat_deg": 10.0,
                "parser_depth_value": 250.0,
                "depth_m_positive_down": None,
                "heading_deg": 45.0,
                "native_quality_state": "flagged",
            },
            "20260806T000000Z",
            "20260805T230449Z",
            object_record,
            "env-digest",
            "command-digest",
            set(),
        )
        self.assertEqual(row["cell_id"], "1min_6000_18000")
        self.assertIsNotNone(row["lon_bin"])
        self.assertFalse(row["qc_eligible_for_cell"])
        self.assertIsNone(row["depth_m_positive_down"])

    def test_output_schema_is_frozen_and_time_nonnullable(self):
        schemas = load_output_schemas(SCHEMA_PATH)
        self.assertEqual(len(schemas["sounding_lineage.parquet"]), 60)
        self.assertFalse(schemas["sounding_lineage.parquet"].field("time_utc").nullable)

    def test_authorization_hash_excludes_only_self_field(self):
        receipt = {"stage_c_authorized": True, "processing_run_id": "20260806T000000Z"}
        first = canonical_authorization_receipt_sha256(receipt)
        receipt["authorization_receipt_sha256"] = first
        self.assertEqual(canonical_authorization_receipt_sha256(receipt), first)
        receipt["processing_run_id"] = "20260806T000001Z"
        self.assertNotEqual(canonical_authorization_receipt_sha256(receipt), first)

    def test_mblist_rows_require_exact_seven_ascii_fields(self):
        path = REPO_ROOT / ".tmp-stage-c-mblist.tsv"
        try:
            path.write_text("1700000000.000000\t1\t2\t-240\t10\t250\t90\n", encoding="ascii")
            rows = list(iter_mblist_rows(path, check_mode=0))
            self.assertEqual(len(rows), 1)
            self.assertAlmostEqual(rows[0][0].lon_deg, -240.0)
            path.write_text("1700000000\t1\t2\t120\t10\t250\t90\textra\n", encoding="ascii")
            with self.assertRaises(ValueError):
                list(iter_mblist_rows(path, check_mode=0))
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

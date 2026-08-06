import hashlib
import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pyarrow.parquet as pq

from ncei.code.scs_v2_stage_c_processing import (
    canonical_authorization_receipt_sha256,
    iter_mblist_rows,
    load_output_schemas,
    ping_review_codes,
    _raw_from_object,
    scan_time_contract,
    sounding_batch_table,
    sounding_row,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / ".trellis/tasks/08-06-scs-v2-stage-c0-source-internal-planning/research/stage-c01-output-schema.yaml"


class SCSV2StageCProcessingTest(unittest.TestCase):
    def test_column_batch_matches_row_contract_on_golden_fixture(self):
        fixture = REPO_ROOT / "_common/tests/fixtures/scs_v2_stage_c1"
        object_record = {
            "relative_path": "objects/TN352/example.mb58.gz",
            "sha256": hashlib.sha256(b"example").hexdigest(),
            "official_cruise_id": "TN352",
        }
        schema = load_output_schemas(SCHEMA_PATH)["sounding_lineage.parquet"]
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            raw_path = directory / "raw.parquet"
            _raw_from_object(
                "20260805T230449Z/objects/TN352/example.mb58.gz",
                fixture / "synthetic_all_u3.tsv",
                fixture / "synthetic_good_u0.tsv",
                directory / "u0.sqlite",
                raw_path,
            )
            review = ping_review_codes(raw_path)
            batch = next(pq.ParquetFile(raw_path).iter_batches())
            vectorized = sounding_batch_table(
                batch,
                "run",
                "20260805T230449Z",
                object_record,
                "env",
                "cmd",
                review,
                schema,
            ).to_pylist()
            rowwise = [
                sounding_row(
                    raw,
                    "run",
                    "20260805T230449Z",
                    object_record,
                    "env",
                    "cmd",
                    review.get(int(raw["parser_ping_index"]), set()),
                )
                for raw in batch.to_pylist()
            ]
            self.assertEqual(len(vectorized), len(rowwise))
            for vectorized_row, rowwise_row in zip(vectorized, rowwise):
                for field in vectorized_row:
                    if field == "time_utc":
                        self.assertEqual(vectorized_row[field].timestamp(), rowwise_row[field].timestamp())
                    elif isinstance(vectorized_row[field], float) and math.isnan(vectorized_row[field]):
                        self.assertTrue(math.isnan(rowwise_row[field]), field)
                    else:
                        self.assertEqual(vectorized_row[field], rowwise_row[field], field)

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

    def test_navigation_range_is_retained_for_source_internal_qc(self):
        path = REPO_ROOT / ".tmp-stage-c-navigation-range.tsv"
        try:
            path.write_text("1700000000.000000\t1\t2\t240\t95\t250\t360\n", encoding="ascii")
            rows = list(iter_mblist_rows(path, check_mode=3))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0].lat_deg, 95.0)
            self.assertEqual(rows[0][0].heading_deg, 360.0)
        finally:
            path.unlink(missing_ok=True)

    def test_parser_contract_failure_is_atomic_and_has_no_raw_rows(self):
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            u3 = directory / "u3.tsv"
            u0 = directory / "u0.tsv"
            line = "1700000000.000000\t1\t2\t120\t10\t250\t90\n"
            u3.write_text(line + line, encoding="ascii")
            u0.write_text(line, encoding="ascii")
            raw = directory / "raw.parquet"
            result = _raw_from_object("object", u3, u0, directory / "u0.sqlite", raw)
            self.assertEqual(result[2], "PARSER_CONTRACT_FAILURE")
            self.assertFalse(raw.exists())


if __name__ == "__main__":
    unittest.main()

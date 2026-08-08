import hashlib
import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from ncei.code.scs_v2_stage_c_processing import (
    canonical_authorization_receipt_sha256,
    find_placeholder_fields,
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
QC_PATH = REPO_ROOT / ".trellis/tasks/08-06-scs-v2-stage-c0-source-internal-planning/research/stage-c01-source-internal-qc.yaml"
VERIFICATION_CONTRACT_PATH = REPO_ROOT / ".trellis/tasks/08-06-scs-v2-stage-c0-source-internal-planning/research/stage-c01-verification-contract.yaml"


class SCSV2StageCProcessingTest(unittest.TestCase):
    def setUp(self):
        self._tmpdirs = []

    def tearDown(self):
        for d in self._tmpdirs:
            d.cleanup()

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
                "u3_navigation_finite": True,
                "u0_navigation_finite": None,
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
        sounding_schema = schemas["sounding_lineage.parquet"]
        schema_spec = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(schema_spec["schema_version"], 4)
        self.assertEqual(len(sounding_schema), 63)
        self.assertFalse(sounding_schema.field("time_utc").nullable)
        self.assertEqual(sounding_schema.field("u3_navigation_finite").type, pa.bool_())
        self.assertFalse(sounding_schema.field("u3_navigation_finite").nullable)
        self.assertEqual(sounding_schema.field("u0_navigation_finite").type, pa.bool_())
        self.assertTrue(sounding_schema.field("u0_navigation_finite").nullable)
        self.assertEqual(sounding_schema.field("navigation_valid").type, pa.bool_())
        self.assertFalse(sounding_schema.field("navigation_valid").nullable)

    def test_qc_and_verification_contracts_bind_dual_source_navigation(self):
        qc = yaml.safe_load(QC_PATH.read_text(encoding="utf-8"))
        navigation = qc["navigation_validity"]
        self.assertEqual(navigation["u0_key_absent"], "not_a_navigation_failure_by_itself")
        self.assertEqual(navigation["u3_xy_nonfinite"], "navigation_valid_false")
        self.assertEqual(navigation["present_u0_xy_nonfinite"], "navigation_valid_false")
        h03 = next(rule for rule in qc["hard_rules"] if rule["id"] == "H03_navigation_finite_range")
        self.assertIn("navigation_valid", h03["expression"])

        verification = yaml.safe_load(VERIFICATION_CONTRACT_PATH.read_text(encoding="utf-8"))
        checks = verification["future_stage_c_post_processing_checks"]
        self.assertIn("u3_nonfinite_navigation_is_h03_only_and_has_no_cell", checks)
        self.assertIn("present_u0_nonfinite_navigation_is_h03_only_and_has_no_cell", checks)
        self.assertIn("dual_nonfinite_navigation_is_h03_only_and_has_no_cell", checks)
        self.assertIn("navigation_valid_recomputed_from_persisted_source_states", checks)
        self.assertIn("forged_navigation_or_source_state_is_rejected", checks)

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

    def _object_record(self):
        return {
            "relative_path": "objects/TN352/example.mb58.gz",
            "sha256": hashlib.sha256(b"example").hexdigest(),
            "official_cruise_id": "TN352",
        }

    def _process(self, u3_text, u0_text):
        self._tmpdirs.append(TemporaryDirectory())
        directory = Path(self._tmpdirs[-1].name)
        (directory / "u3.tsv").write_text(u3_text, encoding="ascii")
        (directory / "u0.tsv").write_text(u0_text, encoding="ascii")
        raw = directory / "raw.parquet"
        result = _raw_from_object(
            "20260805T230449Z/objects/TN352/example.mb58.gz",
            directory / "u3.tsv",
            directory / "u0.tsv",
            directory / "u0.sqlite",
            raw,
        )
        return directory, raw, result

    def _sounding_rows(self, directory, raw):
        review = ping_review_codes(raw)
        rows = [
            sounding_row(
                r,
                "run",
                "20260805T230449Z",
                self._object_record(),
                "env",
                "cmd",
                review.get(int(r["parser_ping_index"]), set()),
            )
            for r in pq.ParquetFile(raw).read().to_pylist()
        ]
        return rows

    _VALID = "1700000000.000000\t1\t2\t120\t10\t250\t90\n"

    def test_xy_nan_row_is_demoted_not_aborted(self):
        # U3 X=NaN (0168-like); U0 keeps finite X/Y (U0 is the strict crosscheck).
        u3 = self._VALID + "1700000001.000000\t1\t3\tnan\t10\t250\t90\n"
        u0 = self._VALID + "1700000001.000000\t1\t3\t120\t10\t250\t90\n"
        directory, raw, result = self._process(u3, u0)
        self.assertIsNone(result[2], f"object should not abort: {result}")
        rows = self._sounding_rows(directory, raw)
        nan_row = next(r for r in rows if r["parser_ping_index"] == 1)
        self.assertIn("H03_NAVIGATION_RANGE", nan_row["qc_hard_failure_codes"])
        self.assertFalse(nan_row["qc_hard_pass"])
        self.assertFalse(nan_row["qc_eligible_for_cell"])
        self.assertIsNone(nan_row["lon_bin"])
        self.assertIsNone(nan_row["lat_bin"])
        self.assertIsNone(nan_row["cell_id"])

    def test_y_nan_row_is_demoted_not_aborted(self):
        u3 = self._VALID + "1700000001.000000\t1\t4\t120\tnan\t250\t90\n"
        u0 = self._VALID + "1700000001.000000\t1\t4\t120\t10\t250\t90\n"
        directory, raw, result = self._process(u3, u0)
        self.assertIsNone(result[2])
        rows = self._sounding_rows(directory, raw)
        nan_row = next(r for r in rows if r["parser_ping_index"] == 1)
        self.assertIn("H03_NAVIGATION_RANGE", nan_row["qc_hard_failure_codes"])
        self.assertFalse(nan_row["qc_eligible_for_cell"])
        self.assertIsNone(nan_row["cell_id"])

    def test_valid_prefix_then_xy_nan_keeps_prefix(self):
        u3 = self._VALID + "1700000001.000000\t1\t5\tnan\t10\t250\t90\n"
        u0 = self._VALID + "1700000001.000000\t1\t5\t120\t10\t250\t90\n"
        directory, raw, result = self._process(u3, u0)
        self.assertIsNone(result[2])
        rows = self._sounding_rows(directory, raw)
        valid = next(r for r in rows if r["parser_ping_index"] == 0)
        self.assertTrue(valid["qc_eligible_for_cell"])
        self.assertIsNotNone(valid["cell_id"])

    def test_time_nan_still_aborts_object(self):
        # U3 M=NaN must still abort the whole object (frozen time contract).
        u3 = "nan\t1\t2\t120\t10\t250\t90\n"
        u0 = self._VALID
        directory, raw, result = self._process(u3, u0)
        self.assertEqual(result[2], "TIME_UTC_INVALID")
        self.assertFalse(raw.exists())

    def test_duplicate_key_still_aborts_object(self):
        line = self._VALID
        directory, raw, result = self._process(line, line + line)
        self.assertEqual(result[2], "PARSER_CONTRACT_FAILURE")
        self.assertFalse(raw.exists())

    def test_ineligible_sounding_excluded_from_aggregation(self):
        u3 = self._VALID + "1700000001.000000\t1\t6\tnan\t10\t250\t90\n"
        u0 = self._VALID + "1700000001.000000\t1\t6\t120\t10\t250\t90\n"
        directory, raw, result = self._process(u3, u0)
        rows = self._sounding_rows(directory, raw)
        eligible = [r for r in rows if r["qc_eligible_for_cell"]]
        self.assertEqual(len(eligible), 1)
        self.assertIsNotNone(eligible[0]["cell_id"])

    # --- C.2.1: U0 X/Y non-finite demotion (C.2 only relaxed U3) ---

    def test_u0_xy_nan_row_is_demoted_not_aborted(self):
        # A present U0 key keeps native quality good, but its non-finite X is a
        # navigation failure even when the U3 coordinates are finite.
        u3 = self._VALID + "1700000001.000000\t1\t7\t120\t10\t250\t90\n"
        u0 = self._VALID + "1700000001.000000\t1\t7\tnan\t10\t250\t90\n"
        directory, raw, result = self._process(u3, u0)
        self.assertIsNone(result[2], f"object should not abort: {result}")
        rows = self._sounding_rows(directory, raw)
        nan_row = next(r for r in rows if r["parser_ping_index"] == 1)
        self.assertEqual(nan_row["native_quality_state"], "good")
        self.assertEqual(nan_row["qc_hard_failure_codes"], ["H03_NAVIGATION_RANGE"])
        self.assertAlmostEqual(nan_row["depth_m_positive_down"], 250.0)
        self.assertFalse(nan_row["qc_hard_pass"])
        self.assertFalse(nan_row["qc_eligible_for_cell"])
        self.assertIsNone(nan_row["lon_bin"])
        self.assertIsNone(nan_row["lat_bin"])
        self.assertIsNone(nan_row["cell_id"])

    def test_nonfinite_navigation_row_and_batch_paths_match(self):
        cases = {
            "u3_nan": ("nan", "10", "120", "10", False, True, False),
            "u3_inf": ("inf", "10", "120", "10", False, True, False),
            "u0_nan": ("120", "10", "nan", "10", True, False, False),
            "both_nonfinite": ("inf", "10", "120", "-inf", False, False, False),
            "u0_absent": ("120", "10", None, None, True, None, True),
            "finite_out_of_range": ("120", "95", "120", "95", True, True, False),
        }
        for name, (u3_x, u3_y, u0_x, u0_y, expected_u3, expected_u0, expected_nav) in cases.items():
            with self.subTest(name=name):
                u3 = self._VALID + f"1700000001.000000\t1\t7\t{u3_x}\t{u3_y}\t250\t90\n"
                u0 = self._VALID
                if u0_x is not None:
                    u0 += f"1700000001.000000\t1\t7\t{u0_x}\t{u0_y}\t250\t90\n"
                directory, raw, result = self._process(u3, u0)
                self.assertIsNone(result[2])
                raw_table = pq.read_table(raw)
                raw_rows = raw_table.to_pylist()
                review = ping_review_codes(raw)
                rowwise = [
                    sounding_row(
                        item,
                        "run",
                        "20260805T230449Z",
                        self._object_record(),
                        "env",
                        "cmd",
                        review.get(int(item["parser_ping_index"]), set()),
                    )
                    for item in raw_rows
                ]
                batch = sounding_batch_table(
                    raw_table.to_batches()[0],
                    "run",
                    "20260805T230449Z",
                    self._object_record(),
                    "env",
                    "cmd",
                    review,
                    load_output_schemas(SCHEMA_PATH)["sounding_lineage.parquet"],
                ).to_pylist()
                for batch_row, rowwise_row in zip(batch, rowwise):
                    for field, value in batch_row.items():
                        if isinstance(value, float) and math.isnan(value):
                            self.assertTrue(math.isnan(rowwise_row[field]), field)
                        else:
                            self.assertEqual(value, rowwise_row[field], field)
                invalid = next(item for item in batch if item["parser_ping_index"] == 1)
                self.assertIs(invalid["u3_navigation_finite"], expected_u3)
                self.assertIs(invalid["u0_navigation_finite"], expected_u0)
                self.assertIs(invalid["navigation_valid"], expected_nav)
                self.assertFalse(invalid["qc_eligible_for_cell"])
                if not expected_nav:
                    self.assertEqual(invalid["native_quality_state"], "good")
                    self.assertEqual(invalid["qc_hard_failure_codes"], ["H03_NAVIGATION_RANGE"])
                    self.assertAlmostEqual(invalid["depth_m_positive_down"], 250.0)
                    self.assertIsNone(invalid["cell_id"])
                else:
                    self.assertEqual(invalid["native_quality_state"], "flagged")
                    self.assertEqual(
                        invalid["qc_hard_failure_codes"],
                        ["H02_NATIVE_NOT_GOOD", "H04_DEPTH_RANGE"],
                    )
                    self.assertIsNotNone(invalid["cell_id"])

    def test_u0_y_nan_row_is_demoted_not_aborted(self):
        u3 = self._VALID + "1700000001.000000\t1\t8\t120\t10\t250\t90\n"
        u0 = self._VALID + "1700000001.000000\t1\t8\t120\tnan\t250\t90\n"
        directory, raw, result = self._process(u3, u0)
        self.assertIsNone(result[2])
        rows = self._sounding_rows(directory, raw)
        nan_row = next(r for r in rows if r["parser_ping_index"] == 1)
        self.assertEqual(nan_row["native_quality_state"], "good")
        self.assertEqual(nan_row["qc_hard_failure_codes"], ["H03_NAVIGATION_RANGE"])
        self.assertFalse(nan_row["qc_eligible_for_cell"])
        self.assertIsNone(nan_row["cell_id"])

    def test_u0_xy_inf_row_is_demoted_not_aborted(self):
        # Inf in U0 also no longer aborts the object; sqlite reads inf back as
        # inf (not None). native stays good, no H02.
        u3 = self._VALID + "1700000001.000000\t1\t9\t120\t10\t250\t90\n"
        u0 = self._VALID + "1700000001.000000\t1\t9\tinf\t10\t250\t90\n"
        directory, raw, result = self._process(u3, u0)
        self.assertIsNone(result[2])
        rows = self._sounding_rows(directory, raw)
        bad_row = next(r for r in rows if r["parser_ping_index"] == 1)
        self.assertEqual(bad_row["native_quality_state"], "good")
        self.assertEqual(bad_row["qc_hard_failure_codes"], ["H03_NAVIGATION_RANGE"])
        self.assertAlmostEqual(bad_row["depth_m_positive_down"], 250.0)
        self.assertFalse(bad_row["qc_eligible_for_cell"])
        self.assertIsNone(bad_row["cell_id"])

    def test_u3_and_u0_nonfinite_navigation_is_h03_only(self):
        u3 = self._VALID + "1700000001.000000\t1\t14\tnan\t10\t250\t90\n"
        u0 = self._VALID + "1700000001.000000\t1\t14\t120\tinf\t250\t90\n"
        directory, raw, result = self._process(u3, u0)
        self.assertIsNone(result[2])
        invalid = next(
            item for item in self._sounding_rows(directory, raw)
            if item["parser_ping_index"] == 1
        )
        self.assertEqual(invalid["native_quality_state"], "good")
        self.assertEqual(invalid["qc_hard_failure_codes"], ["H03_NAVIGATION_RANGE"])
        self.assertAlmostEqual(invalid["depth_m_positive_down"], 250.0)
        self.assertFalse(invalid["navigation_valid"])
        self.assertFalse(invalid["qc_eligible_for_cell"])
        self.assertIsNone(invalid["lon_bin"])
        self.assertIsNone(invalid["lat_bin"])
        self.assertIsNone(invalid["cell_id"])

    def test_negative_time_still_aborts_object(self):
        u3 = "-1.000000\t1\t2\t120\t10\t250\t90\n"
        directory, raw, result = self._process(u3, self._VALID)
        self.assertEqual(result[2], "TIME_UTC_INVALID")
        self.assertFalse(raw.exists())

    def test_u0_nan_prefix_then_valid_keeps_valid(self):
        # Valid prefix retained and eligible when a later U0 NaN row appears.
        u3 = self._VALID + "1700000001.000000\t1\t10\t120\t10\t250\t90\n"
        u0 = self._VALID + "1700000001.000000\t1\t10\tnan\t10\t250\t90\n"
        directory, raw, result = self._process(u3, u0)
        self.assertIsNone(result[2])
        rows = self._sounding_rows(directory, raw)
        valid = next(r for r in rows if r["parser_ping_index"] == 0)
        self.assertTrue(valid["qc_eligible_for_cell"])
        self.assertIsNotNone(valid["cell_id"])

    def test_u3_nan_nav_with_present_u0_keeps_native_good_and_h03_only(self):
        # Requirement 3 core case: the sounding's own navigation is non-finite
        # (U3 X=NaN), U0 key present with finite nav. native_quality_state must
        # stay "good" and the ONLY failure is H03 (no H02); valid depth retained
        # but qc_eligible_for_cell=False with empty cell fields.
        u3 = self._VALID + "1700000001.000000\t1\t11\tnan\t10\t250\t90\n"
        u0 = self._VALID + "1700000001.000000\t1\t11\t120\t10\t250\t90\n"
        directory, raw, result = self._process(u3, u0)
        rows = self._sounding_rows(directory, raw)
        nan_row = next(r for r in rows if r["parser_ping_index"] == 1)
        self.assertEqual(nan_row["native_quality_state"], "good")
        self.assertEqual(nan_row["qc_hard_failure_codes"], ["H03_NAVIGATION_RANGE"])
        self.assertNotIn("H02_NATIVE_NOT_GOOD", nan_row["qc_hard_failure_codes"])
        self.assertIsNotNone(nan_row["depth_m_positive_down"])
        self.assertAlmostEqual(nan_row["depth_m_positive_down"], 250.0)
        self.assertFalse(nan_row["qc_eligible_for_cell"])
        self.assertIsNone(nan_row["lon_bin"])
        self.assertIsNone(nan_row["lat_bin"])
        self.assertIsNone(nan_row["cell_id"])

    def test_u0_finite_nav_mismatch_still_aborts_object(self):
        # A genuine finite-value lon mismatch still raises and aborts the object.
        u3 = self._VALID + "1700000001.000000\t1\t12\t120\t10\t250\t90\n"
        u0 = self._VALID + "1700000001.000000\t1\t12\t130\t10\t250\t90\n"
        directory, raw, result = self._process(u3, u0)
        self.assertEqual(result[2], "PARSER_CONTRACT_FAILURE")
        self.assertFalse(raw.exists())

    def test_u0_join_count_closes_with_mixed_nan_nav(self):
        # seen_u0 == u0_count must hold even with present NaN-nav keys: the
        # second row joins (u0_rowid present) so it counts, and both rows were
        # scanned. The result tuple returns (u3_count, seen_u0, error, detail).
        u3 = self._VALID + "1700000001.000000\t1\t13\t120\t10\t250\t90\n"
        u0 = self._VALID + "1700000001.000000\t1\t13\tnan\t10\t250\t90\n"
        directory, raw, result = self._process(u3, u0)
        self.assertIsNone(result[2])
        # u3_count == 2, seen_u0 == 2 (both U0 keys present, one NaN-nav).
        self.assertEqual(result[0], 2)
        self.assertEqual(result[1], 2)

    # --- C.2.1: recursive placeholder scanning ---

    def test_find_placeholder_fields_is_recursive(self):
        clean = {"a": "x", "permitted_body_read_counts": {".mb58.gz": 192}, "list": ["a", "b"]}
        self.assertEqual(find_placeholder_fields(clean), [])
        nested = {
            "permitted_body_read_counts": {".mb58.gz": "<REQUIRED_COUNT>"},
            "roles": ["ok", {"hidden": "<REQUIRED_SHA256>"}],
            "top": "<REQUIRED_ID>",
        }
        hits = find_placeholder_fields(nested)
        self.assertIn("top", hits)
        self.assertIn("permitted_body_read_counts..mb58.gz", hits)
        self.assertIn("roles[1].hidden", hits)
        self.assertEqual(len(hits), 3)


if __name__ == "__main__":
    unittest.main()

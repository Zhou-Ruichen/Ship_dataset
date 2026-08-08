import hashlib
import unittest
from pathlib import Path

import pandas as pd
import yaml

from ncei.code.prepare_scs_v2_stage_c1a_readiness import normalize_ldd_snapshot
from ncei.code.scs_v2_stage_c1_contract import ACQUISITION_RUN_ID, source_object_id
from ncei.code.scs_v2_stage_c1a_contract import (
    PASS_STATUS,
    TIME_FAILURE_STATUS,
    parse_source_streams_atomically,
)
from ncei.code.verify_scs_v2_stage_c1a_source_internal import verify_tables


REPO_ROOT = Path(__file__).resolve().parents[2]
C1_FIXTURES = REPO_ROOT / "_common/tests/fixtures/scs_v2_stage_c1"
C1A_FIXTURES = REPO_ROOT / "_common/tests/fixtures/scs_v2_stage_c1a"
TASK_RESEARCH = (
    REPO_ROOT
    / ".trellis/tasks/08-06-scs-v2-stage-c0-source-internal-planning/research"
)


class SCSV2StageC1aReadinessTest(unittest.TestCase):
    def test_c2_3_readiness_binds_production_chain_and_contracts(self):
        from ncei.code.prepare_scs_v2_stage_c1a_readiness import (
            AUTHORIZATION_TEMPLATE_SOURCE_PATH,
            CONTRACT_FILES,
            SOURCE_FILES,
        )
        from ncei.code.scs_v2_stage_c_processing import (
            STAGE_C2_3_TEMPLATE_PATH,
            STAGE_C2_3_TEMPLATE_SOURCE_PATH,
        )

        self.assertEqual(AUTHORIZATION_TEMPLATE_SOURCE_PATH, STAGE_C2_3_TEMPLATE_SOURCE_PATH)
        self.assertNotEqual(AUTHORIZATION_TEMPLATE_SOURCE_PATH.resolve(), STAGE_C2_3_TEMPLATE_PATH.resolve())
        self.assertIn("stage-c2-1-contract.yaml", CONTRACT_FILES)
        self.assertIn("stage-c2-2-contract.yaml", CONTRACT_FILES)
        self.assertIn("stage-c2-3-contract.yaml", CONTRACT_FILES)
        self.assertTrue(
            {
                "c1a_readiness_producer",
                "c1a_readiness_verifier",
                "stage_c_processor",
                "stage_c_authorizer",
                "stage_c_verifier",
                "stage_c_processing_helper",
                "stage_c_tests",
                "stage_c_verifier_tests",
            }.issubset(SOURCE_FILES)
        )

    def test_c2_3_readiness_verifier_requires_all_frozen_bindings(self):
        from ncei.code.verify_scs_v2_stage_c1a_readiness import (
            REQUIRED_READINESS_EVIDENCE_KEYS,
            REQUIRED_READINESS_SHA_KEYS,
        )

        self.assertTrue(
            {
                "authorization_template_sha256",
                "stage_c_processing_helper_sha256",
                "stage_c_processor_sha256",
                "stage_c_authorizer_sha256",
                "stage_c_verifier_sha256",
                "readiness_producer_sha256",
                "readiness_verifier_sha256",
                "stage_c_tests_sha256",
                "stage_c_verifier_tests_sha256",
                "base_tests_sha256",
                "c1a_tests_sha256",
                "stage_c2_1_contract_sha256",
                "stage_c2_2_contract_sha256",
                "stage_c2_3_contract_sha256",
                "stage_c0_planning_lock_sha256",
                "output_schema_sha256",
                "qc_contract_sha256",
                "verification_contract_sha256",
            }.issubset(REQUIRED_READINESS_SHA_KEYS)
        )
        self.assertIn("stage_c0_planning_commit", REQUIRED_READINESS_EVIDENCE_KEYS)

    def _valid_texts(self) -> tuple[str, str]:
        return (
            (C1_FIXTURES / "synthetic_all_u3.tsv").read_text(encoding="ascii"),
            (C1_FIXTURES / "synthetic_good_u0.tsv").read_text(encoding="ascii"),
        )

    def test_missing_time_in_u3_aborts_without_partial_output(self):
        _, good = self._valid_texts()
        outcome = parse_source_streams_atomically(
            ACQUISITION_RUN_ID,
            "objects/TN352/test-missing.mb58.gz",
            (C1A_FIXTURES / "synthetic_missing_time_u3.tsv").read_text(encoding="ascii"),
            good,
        )
        self.assertEqual(outcome.parse_status, TIME_FAILURE_STATUS)
        self.assertEqual(outcome.error_code, "TIME_UTC_MISSING")
        self.assertEqual(outcome.parsed_row_count, 0)
        self.assertEqual(outcome.soundings, ())
        self.assertFalse(outcome.time_utc_field_available)

    def test_invalid_time_in_u3_aborts_without_partial_output(self):
        _, good = self._valid_texts()
        outcome = parse_source_streams_atomically(
            ACQUISITION_RUN_ID,
            "objects/TN352/test-invalid.mb58.gz",
            (C1A_FIXTURES / "synthetic_invalid_time_u3.tsv").read_text(encoding="ascii"),
            good,
        )
        self.assertEqual(outcome.parse_status, TIME_FAILURE_STATUS)
        self.assertEqual(outcome.error_code, "TIME_UTC_INVALID")
        self.assertEqual(outcome.soundings, ())

    def test_invalid_time_in_u0_aborts_without_partial_output(self):
        all_text, _ = self._valid_texts()
        outcome = parse_source_streams_atomically(
            ACQUISITION_RUN_ID,
            "objects/TN352/test-invalid-u0.mb58.gz",
            all_text,
            (C1A_FIXTURES / "synthetic_invalid_time_u0.tsv").read_text(encoding="ascii"),
        )
        self.assertEqual(outcome.parse_status, TIME_FAILURE_STATUS)
        self.assertEqual(outcome.error_code, "TIME_UTC_INVALID")
        self.assertEqual(outcome.parsed_row_count, 0)

    def test_valid_stream_assigns_ping_index_only_after_time_preflight(self):
        all_text, good_text = self._valid_texts()
        outcome = parse_source_streams_atomically(
            ACQUISITION_RUN_ID,
            "objects/TN352/test-valid.mb58.gz",
            all_text,
            good_text,
        )
        self.assertEqual(outcome.parse_status, PASS_STATUS)
        self.assertEqual(outcome.parsed_row_count, 5)
        self.assertEqual({row["parser_ping_index"] for row in outcome.soundings}, {0})
        self.assertTrue(outcome.time_utc_field_available)

    def _tables(self) -> dict[str, pd.DataFrame]:
        valid_path = "objects/TN352/valid.mb58.gz"
        failed_path = "objects/TN352/missing-time.mb58.gz"
        valid_id = source_object_id(ACQUISITION_RUN_ID, valid_path)
        failed_id = source_object_id(ACQUISITION_RUN_ID, failed_path)
        valid_sha = hashlib.sha256(b"valid").hexdigest()
        failed_sha = hashlib.sha256(b"invalid-time").hexdigest()
        objects = pd.DataFrame(
            {
                "acquisition_run_id": [ACQUISITION_RUN_ID, ACQUISITION_RUN_ID],
                "source_object_id": [valid_id, failed_id],
                "source_object_relative_path": [valid_path, failed_path],
                "source_object_sha256": [valid_sha, failed_sha],
                "official_cruise_id": ["TN352", "TN352"],
                "official_cruise_id_status": ["verified_from_source_metadata"] * 2,
                "parse_status": [PASS_STATUS, TIME_FAILURE_STATUS],
                "parsed_row_count": [1, 0],
                "error_code": [None, "TIME_UTC_MISSING"],
            }
        )
        sounding = pd.DataFrame(
            {
                "source_object_id": [valid_id],
                "source_object_relative_path": [valid_path],
                "source_object_sha256": [valid_sha],
                "official_cruise_id": ["TN352"],
                "official_cruise_id_status": ["verified_from_source_metadata"],
                "parser_ping_index": [0],
                "parser_ping_index_status": ["known"],
                "native_ping_counter": [7],
                "native_ping_counter_status": ["verified_from_source_metadata"],
                "beam_index": [0],
                "beam_index_status": ["known"],
                "time_utc": [pd.Timestamp("2024-01-01T00:00:00.125000Z")],
                "time_utc_status": ["verified_from_source_metadata"],
                "lon_deg": [120.0],
                "lon_deg_status": ["verified_from_source_metadata"],
                "lat_deg": [10.0],
                "lat_deg_status": ["verified_from_source_metadata"],
                "parser_depth_value": [100.0],
                "depth_m_positive_down": [100.0],
                "depth_m_positive_down_status": ["verified_from_source_metadata"],
                "elev_m": [-100.0],
                "native_quality_state": ["good"],
                "native_quality_state_status": ["known"],
                "qc_eligible_for_cell": [True],
                "lon_bin": [18000],
                "lat_bin": [6000],
                "cell_id": ["1min_6000_18000"],
                "held_out": [True],
                "use_for_training": [False],
                "use_for_tuning": [False],
                "use_for_threshold_selection": [False],
                "role_v2_h": ["held_out_candidate_mrar_out"],
                "role_v2_w": ["blocked_source_independence_unknown"],
                "confirmation_role_eligible": [False],
            }
        )
        contributors = pd.DataFrame(
            {
                "cell_id": ["1min_6000_18000"],
                "official_cruise_id": ["TN352"],
                "source_object_id": [valid_id],
                "source_object_relative_path": [valid_path],
                "source_object_sha256": [valid_sha],
            }
        )
        candidates = pd.DataFrame(
            {"cell_id": ["1min_6000_18000"], "official_cruise_id": ["TN352"]}
        )
        ledger = pd.DataFrame(
            {
                "official_cruise_id": ["TN352", "TN352"],
                "source_object_id": [valid_id, failed_id],
                "source_object_relative_path": [valid_path, failed_path],
                "source_object_sha256": [valid_sha, failed_sha],
                "field_name": ["time_utc", "time_utc"],
                "field_available": [True, False],
                "field_status": ["verified_from_source_metadata", "known"],
                "evidence_kind": ["decoded_format58_M_field", "parser_preflight_failure"],
            }
        )
        return {
            "source_object_processing": objects,
            "sounding_lineage": sounding,
            "cell_cruise_contributors": contributors,
            "cell_cruise_candidates": candidates,
            "field_recovery_ledger": ledger,
        }

    def test_independent_verifier_accepts_atomic_failure_evidence(self):
        result = verify_tables(self._tables())
        self.assertEqual(result["stage_c1a_time_contract"], "pass")
        self.assertEqual(result["invalid_time_object_count"], 1)
        self.assertFalse(result["time_utc_nullable_in_emitted_soundings"])

    def test_independent_verifier_rejects_failed_object_sounding(self):
        tables = self._tables()
        invalid = tables["sounding_lineage"].iloc[[0]].copy()
        failed = tables["source_object_processing"].iloc[1]
        invalid["source_object_id"] = failed["source_object_id"]
        invalid["source_object_relative_path"] = failed["source_object_relative_path"]
        invalid["source_object_sha256"] = failed["source_object_sha256"]
        tables["sounding_lineage"] = pd.concat([tables["sounding_lineage"], invalid], ignore_index=True)
        with self.assertRaisesRegex(AssertionError, "invalid-time object emitted sounding rows"):
            verify_tables(tables)

    def test_contract_keeps_time_nonnullable_and_forbids_external_actions(self):
        contract = yaml.safe_load(
            (TASK_RESEARCH / "stage-c1a-time-and-output-contract.yaml").read_text(encoding="utf-8")
        )
        policy = contract["unique_missing_or_invalid_time_policy"]
        self.assertEqual(policy["action"], "abort_source_object_atomically")
        self.assertFalse(policy["sounding_lineage"]["time_utc_nullable"])
        self.assertEqual(policy["sounding_lineage"]["rows_emitted"], 0)
        self.assertFalse(policy["field_recovery_ledger"]["field_available"])

    def test_ldd_snapshot_normalization_removes_only_aslr_addresses(self):
        first = "libx.so => /fixed/libx.so (0x00007f111111)\n"
        second = "libx.so => /fixed/libx.so (0x00007f999999)\n"
        expected = "libx.so => /fixed/libx.so (0xADDR)\n"
        self.assertEqual(normalize_ldd_snapshot(first), expected)
        self.assertEqual(normalize_ldd_snapshot(second), expected)


if __name__ == "__main__":
    unittest.main()

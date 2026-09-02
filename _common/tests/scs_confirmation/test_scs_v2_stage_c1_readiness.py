import hashlib
import math
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import pandas as pd

from _common.scs_v2_stage_c1_oracle import iter_datagrams, read_format58_fixture
from ncei.code.scs_confirmation.scs_v2_stage_c1_contract import (
    ACQUISITION_RUN_ID,
    cell_assignment,
    join_all_and_good,
    normalize_longitude,
    parse_mblist_tsv,
    source_object_id,
)
from ncei.code.scs_confirmation.verify_scs_v2_stage_c_source_internal import verify_tables


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "_common/tests/fixtures/scs_v2_stage_c1"
GOLDEN = FIXTURE_ROOT / "MGL1104-9999-eight-ping.mb58"
ENVIRONMENT_ROOT = (
    REPO_ROOT
    / "ncei/derived/scs_v2_sealed_confirmation/environments"
    / "mbsystem-5.8.3beta16-1d9a52ce"
)
MBLIST = ENVIRONMENT_ROOT / "build/mbsystem/src/utilities/mblist"
MBINFO = ENVIRONMENT_ROOT / "build/mbsystem/src/utilities/mbinfo"


class SCSV2StageC1ReadinessTest(unittest.TestCase):
    def test_empty_content_hash_is_not_object_identity(self):
        empty_sha = hashlib.sha256(b"").hexdigest()
        objects = [
            {
                "source_object_relative_path": "objects/TN352/em302/a.fnv",
                "source_object_sha256": empty_sha,
            },
            {
                "source_object_relative_path": "objects/TN352/em302/b.fnv",
                "source_object_sha256": empty_sha,
            },
        ]
        for item in objects:
            item["source_object_id"] = source_object_id(
                ACQUISITION_RUN_ID, item["source_object_relative_path"]
            )
        self.assertEqual(len({item["source_object_sha256"] for item in objects}), 1)
        self.assertEqual(len({item["source_object_id"] for item in objects}), 2)
        self.assertEqual(len({item["source_object_id"]: item for item in objects}), 2)

    def test_object_identity_rejects_noncanonical_paths(self):
        for value in ("", "/absolute", "../escape", "objects/../escape", "objects\\escape"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                source_object_id(ACQUISITION_RUN_ID, value)
        for run_id in ("", ".", "..", "../run", "run/id", "run..id"):
            with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                source_object_id(run_id, "objects/TN352/a.fnv")

    def test_synthetic_adapter_good_flagged_null_and_units(self):
        all_rows = parse_mblist_tsv(
            (FIXTURE_ROOT / "synthetic_all_u3.tsv").read_text(encoding="ascii"), check_mode=3
        )
        good_rows = parse_mblist_tsv(
            (FIXTURE_ROOT / "synthetic_good_u0.tsv").read_text(encoding="ascii"), check_mode=0
        )
        joined = join_all_and_good(
            ACQUISITION_RUN_ID,
            "fixtures/synthetic.mb58",
            all_rows,
            good_rows,
        )
        self.assertEqual([item["native_quality_state"] for item in joined], ["good", "good", "good", "flagged", "null"])
        self.assertEqual([item["depth_m_positive_down"] for item in joined[:3]], [10.0, 11.0, 12.0])
        self.assertIsNone(joined[3]["depth_m_positive_down"])
        self.assertIsNone(joined[4]["depth_m_positive_down"])
        self.assertTrue(math.isnan(joined[4]["parser_depth_value"]))
        self.assertEqual(joined[0]["epoch_seconds_utc"].as_tuple().exponent, -6)
        self.assertEqual([item["lon_deg"] for item in joined[:3]], [-180.0, -180.0, -1.0])
        self.assertTrue(all(item["source_object_id"].startswith(f"{ACQUISITION_RUN_ID}/") for item in joined))

    def test_parser_contract_rejects_column_and_delimiter_drift(self):
        invalid = [
            "1,2,3,4,5,6,7\n",
            "1\t2\t3\t4\t5\t6\n",
            "1\t2\t3\t4\t5\t6\t7\t8\n",
            "1\t2\t3\t4\t5\t6\t7\r\n",
        ]
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_mblist_tsv(text, check_mode=3)
        with self.assertRaises(ValueError):
            parse_mblist_tsv("1\t2\t3\t4\t5\tNaN\t7\n", check_mode=0)

    def test_grid_boundary_adjacent_float_and_existing_contract(self):
        boundary = 120.0
        below = boundary - 1.0e-10
        above = boundary + 1.0e-10
        self.assertEqual(cell_assignment(below, 10.0)[0], 17999)
        self.assertEqual(cell_assignment(boundary, 10.0)[0], 18000)
        self.assertEqual(cell_assignment(above, 10.0)[0], 18000)
        # This is the historical float64 behavior of floor((lon + 180) * 60):
        # adding 180 rounds the immediate predecessor back onto the boundary.
        self.assertEqual(cell_assignment(math.nextafter(boundary, -math.inf), 10.0)[0], 18000)

        lat_boundary = 10.0
        self.assertEqual(cell_assignment(120.0, lat_boundary - 1.0e-10)[1], 5999)
        self.assertEqual(cell_assignment(120.0, lat_boundary)[1], 6000)
        self.assertEqual(cell_assignment(120.0, lat_boundary + 1.0e-10)[1], 6000)
        self.assertEqual(cell_assignment(120.0, math.nextafter(lat_boundary, -math.inf))[1], 6000)

        self.assertEqual(normalize_longitude(180.0), -180.0)
        self.assertEqual(normalize_longitude(540.0), -180.0)
        self.assertEqual(cell_assignment(180.0, 0.0), (0, 5400, "1min_5400_0"))
        self.assertEqual(
            cell_assignment(105.00833333333333, 0.14166666666666572)[2],
            "1min_5408_17100",
        )
        self.assertEqual(cell_assignment(-180.0, -90.0), (0, 0, "1min_0_0"))
        self.assertEqual(cell_assignment(-180.0, 90.0), (0, 10800, "1min_10800_0"))

    def test_oracle_rejects_truncated_datagram(self):
        data = GOLDEN.read_bytes()
        with self.assertRaises(ValueError):
            list(iter_datagrams(data[:-1]))

    def test_future_verifier_uses_source_object_id_not_content_hash(self):
        empty_sha = hashlib.sha256(b"").hexdigest()
        relative_paths = ["objects/TN352/em302/a.fnv", "objects/TN352/em302/b.fnv"]
        object_ids = [source_object_id(ACQUISITION_RUN_ID, path) for path in relative_paths]
        objects = pd.DataFrame(
            {
                "acquisition_run_id": [ACQUISITION_RUN_ID] * 2,
                "source_object_id": object_ids,
                "source_object_relative_path": relative_paths,
                "source_object_sha256": [empty_sha, empty_sha],
                "official_cruise_id": ["TN352", "TN352"],
                "official_cruise_id_status": ["verified_from_source_metadata"] * 2,
            }
        )
        sounding = pd.DataFrame(
            {
                "source_object_id": [object_ids[0]],
                "source_object_relative_path": [relative_paths[0]],
                "source_object_sha256": [empty_sha],
                "official_cruise_id": ["TN352"],
                "official_cruise_id_status": ["verified_from_source_metadata"],
                "parser_ping_index": [0],
                "parser_ping_index_status": ["known"],
                "native_ping_counter": [1],
                "native_ping_counter_status": ["verified_from_source_metadata"],
                "beam_index": [0],
                "beam_index_status": ["known"],
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
                "source_object_id": [object_ids[0]],
                "source_object_relative_path": [relative_paths[0]],
                "source_object_sha256": [empty_sha],
            }
        )
        candidates = pd.DataFrame({"cell_id": ["1min_6000_18000"], "official_cruise_id": ["TN352"]})
        ledger = pd.DataFrame(
            {
                "official_cruise_id": ["TN352", "TN352"],
                "source_object_id": object_ids,
                "source_object_relative_path": relative_paths,
                "source_object_sha256": [empty_sha, empty_sha],
                "field_name": ["navigation", "navigation"],
                "field_status": ["officially_unknown", "officially_unknown"],
            }
        )
        result = verify_tables(
            {
                "source_object_processing": objects,
                "sounding_lineage": sounding,
                "cell_cruise_contributors": contributors,
                "cell_cruise_candidates": candidates,
                "field_recovery_ledger": ledger,
            }
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["source_object_count"], 2)
        self.assertFalse(result["source_object_sha256_used_as_identity"])

    def test_pinned_binary_help(self):
        for binary, name in ((MBLIST, "MBLIST"), (MBINFO, "MBINFO")):
            with self.subTest(binary=binary):
                completed = subprocess.run([str(binary), "-h"], text=True, capture_output=True, check=False)
                combined = completed.stdout + completed.stderr
                self.assertEqual(completed.returncode, 0)
                self.assertIn(f"Program {name}", combined)
                self.assertIn("MB-system Version 5.8.3beta16", combined)

    def test_noncandidate_format58_golden_against_independent_oracle(self):
        self.assertEqual(GOLDEN.stat().st_size, 377_852)
        self.assertEqual(
            hashlib.sha256(GOLDEN.read_bytes()).hexdigest(),
            "03dae8f817bcb4d9b5262bc4094367cbcd011d37cf8c35685aee6fd3d33af2a0",
        )
        oracle = read_format58_fixture(GOLDEN)
        oracle_counts = Counter(row.quality_state for row in oracle)
        self.assertEqual(len(oracle), 3_456)
        self.assertEqual(oracle_counts, {"good": 3_450, "flagged": 6})
        self.assertEqual(sorted({row.native_ping_counter for row in oracle}), list(range(4592, 4600)))

        with tempfile.TemporaryDirectory() as directory:
            all_path = Path(directory) / "all-u3.tsv"
            good_path = Path(directory) / "good-u0.tsv"
            commands = [
                [str(MBLIST), f"-I{GOLDEN}", "-F58", "-P1", "-L0", "-MA", "-U3", "-OMN#XYzH", f"-X{all_path}"],
                [str(MBLIST), f"-I{GOLDEN}", "-F58", "-P1", "-L0", "-MA", "-U0", "-OMN#XYzH", f"-X{good_path}"],
            ]
            for command in commands:
                completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
                self.assertEqual(completed.returncode, 0, completed.stderr)
            all_rows = parse_mblist_tsv(all_path.read_text(encoding="ascii"), check_mode=3)
            good_rows = parse_mblist_tsv(good_path.read_text(encoding="ascii"), check_mode=0)

        joined = join_all_and_good(ACQUISITION_RUN_ID, "fixtures/MGL1104.mb58", all_rows, good_rows)
        self.assertEqual(len(all_rows), 3_456)
        self.assertEqual(len(good_rows), 3_450)
        self.assertEqual(Counter(item["native_quality_state"] for item in joined), oracle_counts)

        for actual, expected in zip(all_rows, oracle):
            self.assertEqual(actual.native_ping_counter, expected.native_ping_counter)
            self.assertEqual(actual.beam_index, expected.beam_index)
            self.assertLessEqual(abs(float(actual.epoch_seconds_utc) - expected.epoch_seconds_utc), 1.0e-6)
            self.assertLessEqual(abs(actual.lon_deg - expected.lon_deg), 5.0e-8)
            self.assertLessEqual(abs(actual.lat_deg - expected.lat_deg), 5.0e-8)
            self.assertLessEqual(abs(actual.parser_depth_value - expected.parser_depth_value), 1.1e-4)
            self.assertLessEqual(abs(actual.heading_deg - expected.heading_deg), 1.0e-3)

        actual_good_keys = {row.join_key for row in good_rows}
        expected_good_keys = {
            row.join_key
            for row, expected in zip(all_rows, oracle)
            if expected.quality_state == "good"
        }
        self.assertEqual(actual_good_keys, expected_good_keys)
        flagged_keys = [
            (row.native_ping_counter, row.beam_index)
            for row in oracle
            if row.quality_state == "flagged"
        ]
        self.assertEqual(flagged_keys, [(4598, beam) for beam in range(18, 24)])


if __name__ == "__main__":
    unittest.main()

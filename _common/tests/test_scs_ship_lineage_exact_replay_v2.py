import importlib.util
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "ncei/code/audit_scs_ship_lineage_exact_replay_v2.py"
SPEC = importlib.util.spec_from_file_location("scs_ship_lineage_exact_replay_v2", MODULE_PATH)
audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(audit)


def sample_points() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "canonical_cell_id": "cell_a", "source_provider": "jamstec",
            "file_id": "A::one.dat", "official_cruise_id": "A",
            "contributor_group_key": "official_cruise:A", "raw_file": "one.dat",
            "raw_row_id": 1, "lon": 120.0, "lat": 20.0,
            "depth_m_positive_down": 0.0,
        },
        {
            "canonical_cell_id": "cell_a", "source_provider": "jamstec",
            "file_id": "A::one.dat", "official_cruise_id": "A",
            "contributor_group_key": "official_cruise:A", "raw_file": "one.dat",
            "raw_row_id": 2, "lon": 120.0, "lat": 20.0,
            "depth_m_positive_down": 0.0,
        },
        {
            "canonical_cell_id": "cell_a", "source_provider": "jamstec",
            "file_id": "A::one.dat", "official_cruise_id": "A",
            "contributor_group_key": "official_cruise:A", "raw_file": "one.dat",
            "raw_row_id": 3, "lon": 120.0, "lat": 20.0,
            "depth_m_positive_down": 0.0,
        },
        {
            "canonical_cell_id": "cell_a", "source_provider": "jamstec",
            "file_id": "A::one.dat", "official_cruise_id": "A",
            "contributor_group_key": "official_cruise:A", "raw_file": "one.dat",
            "raw_row_id": 4, "lon": 120.0, "lat": 20.0,
            "depth_m_positive_down": 100.0,
        },
        {
            "canonical_cell_id": "cell_a", "source_provider": "jamstec",
            "file_id": "A::two.dat", "official_cruise_id": "A",
            "contributor_group_key": "official_cruise:A", "raw_file": "two.dat",
            "raw_row_id": 8, "lon": 120.0, "lat": 20.0,
            "depth_m_positive_down": 100.0,
        },
        {
            "canonical_cell_id": "cell_b", "source_provider": "mrar",
            "file_id": "mrar", "official_cruise_id": None,
            "contributor_group_key": "unresolved_source:mrar", "raw_file": "mrar.txt",
            "raw_row_id": 10, "lon": 121.0, "lat": 21.0,
            "depth_m_positive_down": 500.0,
        },
    ])


class TestSCSShipLineageExactReplayV2(unittest.TestCase):
    def test_exact_stats_use_all_raw_values(self):
        stats = audit.exact_stats(np.asarray([1.0, 2.0, 100.0, 101.0]))
        self.assertEqual(stats["point_count"], 4)
        self.assertEqual(stats["median_m"], 51.0)
        self.assertEqual(stats["range_m"], 100.0)
        self.assertAlmostEqual(stats["nmad_m"], 73.3887)

    def test_cruise_cell_median_is_not_median_of_file_medians(self):
        points = audit.add_raw_point_statuses(sample_points())
        file_cells = audit.build_file_cell_contributors(points, {})
        cruise_cells = audit.build_cell_cruise_contributors(points, {})
        file_balanced = file_cells.loc[file_cells.canonical_cell_id.eq("cell_a"), "exact_median_m"].median()
        cruise_raw = cruise_cells.loc[cruise_cells.canonical_cell_id.eq("cell_a"), "exact_median_m"].iloc[0]
        self.assertEqual(file_balanced, 50.0)
        self.assertEqual(cruise_raw, 0.0)

    def test_mrar_never_receives_a_cruise_identity(self):
        points = audit.add_raw_point_statuses(sample_points())
        cruise_cells = audit.build_cell_cruise_contributors(points, {})
        row = cruise_cells.loc[cruise_cells.source_provider.eq("mrar")].iloc[0]
        self.assertTrue(pd.isna(row.official_cruise_id))
        self.assertEqual(row.official_cruise_id_status, "not_recoverable")
        self.assertEqual(row.contributor_group_key, "unresolved_source:mrar")

    def test_raw_row_ranges_are_zero_based_inclusive(self):
        self.assertEqual(audit.compress_ranges([0, 1, 3, 4, 4]), [[0, 1], [3, 4]])

    def test_canonical_digest_is_row_order_invariant(self):
        frame = pd.DataFrame({"key": ["b", "a"], "value": [2.0, 1.0]})
        first = audit.canonical_frame_digest(frame, ["key"], ["key", "value"])
        second = audit.canonical_frame_digest(frame.iloc[::-1], ["key"], ["key", "value"])
        self.assertEqual(first, second)

    def test_status_pairs_reject_missing_and_invalid_status(self):
        valid = pd.DataFrame({"id": ["a"], "value": [1], "value_status": ["known"]})
        audit.validate_status_pairs(valid, {"id"})
        with self.assertRaises(ValueError):
            audit.validate_status_pairs(valid.drop(columns="value_status"), {"id"})
        invalid = valid.assign(value_status="assumed")
        with self.assertRaises(ValueError):
            audit.validate_status_pairs(invalid, {"id"})

    def test_status_census_includes_explicit_zeroes(self):
        frame = pd.DataFrame({"id": ["a", "b"], "value": [1, 2], "value_status": ["known", "known"]})
        census = audit.build_factual_status_counts({"example.parquet": frame})
        self.assertEqual(len(census), len(audit.FIELD_STATUSES))
        count = census.loc[
            census.field.eq("value") & census.factual_status.eq("not_recoverable"), "count"
        ].iloc[0]
        self.assertEqual(count, 0)

    def test_output_schema_forbids_correction_and_model_fields(self):
        audit.validate_output_schema(pd.DataFrame({"exact_median_m": [1.0]}), ["corrected", "model_error"])
        with self.assertRaises(ValueError):
            audit.validate_output_schema(pd.DataFrame({"corrected_depth_m": [1.0]}), ["corrected"])
        with self.assertRaises(ValueError):
            audit.validate_output_schema(pd.DataFrame({"model_error_m": [1.0]}), ["model_error"])


if __name__ == "__main__":
    unittest.main()

import importlib.util
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "ncei/code/scs_confirmation/audit_scs_ship_qc_v2_preflight.py"
SPEC = importlib.util.spec_from_file_location("scs_ship_qc_v2_preflight", MODULE_PATH)
audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(audit)


class TestSCSShipQCV2Preflight(unittest.TestCase):
    def test_expand_ranges_and_context_window_are_inclusive(self):
        self.assertEqual(audit.expand_ranges([[3, 5], [8, 8]]), [3, 4, 5, 8])
        self.assertEqual(audit.context_indices([0, 4], window=2), {0, 1, 2, 3, 4, 5, 6})

    def test_components_require_provider_and_difference_sign(self):
        frame = pd.DataFrame(
            [
                {"canonical_cell_id": "a", "lon_index": 0, "lat_index": 0, "source_provider": "mrar", "difference_sign": 1},
                {"canonical_cell_id": "b", "lon_index": 1, "lat_index": 1, "source_provider": "mrar", "difference_sign": 1},
                {"canonical_cell_id": "c", "lon_index": 1, "lat_index": 0, "source_provider": "mrar", "difference_sign": -1},
                {"canonical_cell_id": "d", "lon_index": 0, "lat_index": 1, "source_provider": "jamstec", "difference_sign": 1},
            ]
        )
        out = audit.assign_components(frame)
        component_by_id = dict(zip(out.canonical_cell_id, out.component_id))
        self.assertEqual(component_by_id["a"], component_by_id["b"])
        self.assertNotEqual(component_by_id["a"], component_by_id["c"])
        self.assertNotEqual(component_by_id["a"], component_by_id["d"])

    def test_controls_are_deterministic_disjoint_and_exact_stratum(self):
        cells = pd.DataFrame(
            [
                {"canonical_cell_id": "candidate", "source_provider": "mrar", "primary_raw_file": "x", "depth_band": "d1", "point_count_band": "p1", "is_candidate": True},
                {"canonical_cell_id": "z", "source_provider": "mrar", "primary_raw_file": "x", "depth_band": "d1", "point_count_band": "p1", "is_candidate": False},
                {"canonical_cell_id": "y", "source_provider": "mrar", "primary_raw_file": "x", "depth_band": "d1", "point_count_band": "p1", "is_candidate": False},
                {"canonical_cell_id": "wrong", "source_provider": "mrar", "primary_raw_file": "x", "depth_band": "d2", "point_count_band": "p1", "is_candidate": False},
            ]
        )
        first = audit.choose_controls(cells, seed="fixed", ratio=1)
        second = audit.choose_controls(cells.sample(frac=1, random_state=5), seed="fixed", ratio=1)
        self.assertEqual(first.canonical_cell_id.tolist(), second.canonical_cell_id.tolist())
        self.assertEqual(len(first), 1)
        self.assertNotIn("candidate", first.canonical_cell_id.tolist())
        self.assertEqual(first.iloc[0].depth_band, "d1")
        self.assertEqual(first.iloc[0].control_match_level, "same_file_depth_and_count")

    def test_controls_fall_back_within_same_file(self):
        cells = pd.DataFrame(
            [
                {"canonical_cell_id": "candidate", "source_provider": "jamstec", "primary_raw_file": "x", "depth_band": "d1", "point_count_band": "p1", "is_candidate": True},
                {"canonical_cell_id": "control", "source_provider": "jamstec", "primary_raw_file": "x", "depth_band": "d1", "point_count_band": "p2", "is_candidate": False},
                {"canonical_cell_id": "wrong_file", "source_provider": "jamstec", "primary_raw_file": "y", "depth_band": "d1", "point_count_band": "p1", "is_candidate": False},
            ]
        )
        result = audit.choose_controls(cells, seed="fixed", ratio=1)
        self.assertEqual(result.iloc[0].canonical_cell_id, "control")
        self.assertEqual(result.iloc[0].control_match_level, "same_file_depth")

    def test_raw_context_summary_uses_non_target_nearby_rows(self):
        rows = {
            8: (120.0, 20.0, 100.0, 3),
            9: (120.0, 20.0, 101.0, 3),
            10: (120.0, 20.0, 1000.0, 3),
            11: (120.0, 20.0, 99.0, 3),
        }
        result = audit.summarize_raw_rows(
            rows=rows,
            target_indices={10},
            cell_lon=120.0,
            cell_lat=20.0,
            radius_km=5.0,
        )
        self.assertEqual(result["target_record_count"], 1)
        self.assertEqual(result["nearby_context_record_count"], 3)
        self.assertAlmostEqual(result["context_depth_median_m"], 100.0)
        self.assertAlmostEqual(result["target_minus_context_m"], 900.0)
        self.assertAlmostEqual(result["context_nmad_m"], 1.4826)

    def test_aggregation_alternatives(self):
        records = [
            {"file_cell_median_m": 100.0, "raw_point_count": 100, "raw_file": "dense", "cruise_id": "A"},
            {"file_cell_median_m": 1000.0, "raw_point_count": 2, "raw_file": "sparse", "cruise_id": "B"},
        ]
        result = audit.aggregation_alternatives(records)
        self.assertEqual(result["replayed_unweighted_median_m"], 550.0)
        self.assertAlmostEqual(result["point_count_weighted_mean_m"], 117.6470588235294)
        self.assertEqual(result["point_count_weighted_median_m"], 100.0)
        self.assertEqual(result["dominant_contributor_median_m"], 100.0)
        self.assertEqual(result["contributor_range_m"], 900.0)

    def test_cell_context_excludes_other_cached_windows(self):
        selected = pd.DataFrame([{
            "canonical_cell_id": "cell",
            "sample_class": "candidate",
            "source_provider": "jamstec",
            "lon": 120.0,
            "lat": 20.0,
        }])
        targets = {"cell": {"raw.dat": {10}}}
        retained = {"raw.dat": {
            9: (120.0, 20.0, 100.0, 3),
            10: (120.0, 20.0, 1000.0, 3),
            11: (120.0, 20.0, 101.0, 3),
            1000: (120.0, 20.0, 9999.0, 3),
        }}
        result = audit.build_raw_context_features(selected, targets, retained, 5.0, 1)
        self.assertEqual(result.iloc[0].context_record_count, 2)
        self.assertEqual(result.iloc[0].nearby_context_record_count, 2)

    def test_parsed_window_with_no_nearby_rows_is_known_but_insufficient(self):
        result = audit.summarize_raw_rows(
            {10: (120.0, 20.0, 1000.0, 3), 11: (130.0, 30.0, 100.0, 3)},
            {10},
            120.0,
            20.0,
            5.0,
        )
        self.assertEqual(result["context_status"], "known")
        self.assertEqual(result["nearby_context_record_count"], 0)

    def test_raw_discontinuity_signal_is_raw_only(self):
        frame = pd.DataFrame({
            "context_status": ["known", "known", "known"],
            "nearby_context_record_count": [5, 2, 5],
            "target_minus_context_m": [1500.0, 1500.0, 1500.0],
            "context_nmad_m": [10.0, 10.0, 200.0],
        })
        config = {"raw_context": {
            "minimum_nearby_records": 3,
            "discontinuity_absolute_threshold_m": 1000.0,
            "discontinuity_nmad_multiplier": 10.0,
        }}
        result = audit.add_raw_discontinuity_signal(frame, config)
        self.assertEqual(result.raw_context_sufficient.tolist(), [True, False, True])
        self.assertEqual(result.raw_discontinuity_signal.tolist(), [True, False, False])

    def test_missing_context_and_closed_states(self):
        result = audit.summarize_raw_rows({}, set(), 0.0, 0.0, 5.0)
        self.assertEqual(result["context_status"], "not_recoverable")
        audit.validate_interpretation_state("terrain_or_source_ambiguous", {"terrain_or_source_ambiguous"})
        with self.assertRaises(ValueError):
            audit.validate_interpretation_state("delete", {"terrain_or_source_ambiguous"})

    def test_output_schema_guard(self):
        audit.validate_output_schema(pd.DataFrame({"canonical_cell_id": ["a"], "diagnostic_difference_m": [1.0]}), ["corrected", "exclude"])
        with self.assertRaises(ValueError):
            audit.validate_output_schema(pd.DataFrame({"corrected_depth_m": [1.0]}), ["corrected", "exclude"])

    def test_output_path_guard(self):
        audit.validate_output_path(Path("evidence/candidate_cells.parquet"), ["corrected", "prediction"])
        with self.assertRaises(ValueError):
            audit.validate_output_path(Path("evidence/corrected_cells.parquet"), ["corrected", "prediction"])


if __name__ == "__main__":
    unittest.main()

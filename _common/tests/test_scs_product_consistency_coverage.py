import importlib
import unittest

import numpy as np
import pandas as pd


audit = importlib.import_module("ncei.code.audit_scs_product_consistency_coverage")


class SCSProductConsistencyCoverageTest(unittest.TestCase):
    def test_target_centers_follow_half_open_pixel_registration(self):
        lon, lat = audit.target_centers(105.0, 125.0, 0.0, 25.0, 1)
        self.assertEqual((len(lat), len(lon)), (1500, 1200))
        self.assertAlmostEqual(lon[0], 105.0 + 1.0 / 120.0)
        self.assertAlmostEqual(lon[-1], 125.0 - 1.0 / 120.0)
        self.assertAlmostEqual(lat[0], 1.0 / 120.0)
        self.assertAlmostEqual(lat[-1], 25.0 - 1.0 / 120.0)

    def test_aligned_fine_grid_uses_exact_block_median(self):
        fine = np.arange(8 * 12, dtype=np.float64).reshape(8, 12)
        actual = audit.aggregate_aligned_fine_grid(fine, factor=4, reducer="median")
        expected = np.empty((2, 3), dtype=np.float64)
        for i in range(2):
            for j in range(3):
                expected[i, j] = np.median(fine[i * 4:(i + 1) * 4, j * 4:(j + 1) * 4])
        np.testing.assert_allclose(actual, expected)

    def test_elevation_to_depth_preserves_nonpositive_diagnostics(self):
        actual = audit.elevation_to_depth(np.array([-2000.0, 0.0, 15.0, np.nan]))
        np.testing.assert_allclose(actual[:3], np.array([2000.0, -0.0, -15.0]))
        self.assertTrue(np.isnan(actual[3]))

    def test_product_and_family_consensus_are_distinct(self):
        values = pd.DataFrame({
            "gebco_2024_depth_m": [100.0, 1000.0],
            "gebco_2025_depth_m": [102.0, 1002.0],
            "gebco_2026_depth_m": [104.0, 1004.0],
            "etopo_2022_depth_m": [200.0, 1100.0],
            "srtm15_v2_7_depth_m": [300.0, 1200.0],
            "topo_25_1_depth_m": [400.0, 1300.0],
            "sdust_2023_depth_m": [500.0, 1400.0],
        })
        actual = audit.add_consensus_columns(values.copy())
        self.assertEqual(actual.loc[0, "gebco_family_median_depth_m"], 102.0)
        self.assertEqual(actual.loc[0, "product_consensus_median_depth_m"], 200.0)
        self.assertEqual(actual.loc[0, "family_consensus_median_depth_m"], 300.0)
        self.assertEqual(actual.loc[0, "product_consensus_count"], 7)
        self.assertEqual(actual.loc[0, "family_consensus_count"], 5)

    def test_nmad_rows_matches_scalar_definition(self):
        values = np.array([[1.0, 2.0, 3.0], [5.0, 5.0, np.nan]])
        actual = audit.nmad_rows(values)
        np.testing.assert_allclose(actual, np.array([1.4826, 0.0]))

    def test_one_minute_cell_area_is_positive_and_latitude_dependent(self):
        equator = audit.cell_area_km2(np.array([1.0 / 120.0]), 1)[0]
        high_lat = audit.cell_area_km2(np.array([60.0 + 1.0 / 120.0]), 1)[0]
        self.assertAlmostEqual(equator, 3.434, places=2)
        self.assertLess(high_lat, equator)
        self.assertGreater(high_lat, 0.0)

    def test_nearest_distance_uses_great_circle_geometry(self):
        controls = audit.lonlat_to_unit_xyz(np.array([0.0]), np.array([0.0]))
        queries = audit.lonlat_to_unit_xyz(np.array([0.0, 1.0]), np.array([0.0, 0.0]))
        actual = audit.nearest_great_circle_km(queries, controls)
        self.assertAlmostEqual(actual[0], 0.0, places=9)
        self.assertAlmostEqual(actual[1], 111.195, places=3)

    def test_tid_groups_are_disjoint_and_close_over_all_pixels(self):
        groups = {
            "land": [0],
            "direct": [10, 11],
            "gravity": [40, 44],
            "other": [41, 70],
        }
        audit.validate_tid_groups(groups)
        fine = np.array([
            [10, 10, 40, 40],
            [10, 11, 44, 41],
            [0, 0, 70, 70],
            [0, 0, 70, 70],
        ], dtype=np.int16)
        fractions, counts = audit.aggregate_tid_groups(fine, 4, groups)
        self.assertEqual(counts, {0: 4, 10: 3, 11: 1, 40: 2, 41: 1, 44: 1, 70: 4})
        closure = sum(value[0, 0] for value in fractions.values())
        self.assertAlmostEqual(closure, 1.0)

    def test_tid_group_overlap_is_rejected(self):
        with self.assertRaises(ValueError):
            audit.validate_tid_groups({"a": [10, 11], "b": [11, 40]})

    def test_forbidden_union_columns_and_decision_outputs_are_rejected(self):
        audit.validate_union_columns({
            "canonical_cell_id", "lon", "lat", "representative_depth_m", "source_provider",
        })
        with self.assertRaises(ValueError):
            audit.validate_union_columns({"canonical_cell_id", "model_error_m"})
        audit.validate_diagnostic_output_columns(["canonical_cell_id", "family_consensus_nmad_m"])
        with self.assertRaises(ValueError):
            audit.validate_diagnostic_output_columns(["canonical_cell_id", "sample_weight"])


if __name__ == "__main__":
    unittest.main()

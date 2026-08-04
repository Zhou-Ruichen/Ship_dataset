import importlib
import unittest
from pathlib import Path

import numpy as np


audit = importlib.import_module("ncei.code.audit_scs_upstream_lineage")


class SCSLineageAuditTest(unittest.TestCase):
    def test_cell_assignment_matches_one_arc_minute_contract(self):
        ids = audit.cell_ids(
            np.array([105.00833333333333, 124.99166666666667]),
            np.array([0.14166666666666572, 5.291666666666671]),
        )
        self.assertEqual(ids.tolist(), ["1min_5408_17100", "1min_5717_18299"])

    def test_longitude_normalization_uses_half_open_interval(self):
        actual = audit.normalize_lon(np.array([0.0, 180.0, 181.0, 360.0]))
        np.testing.assert_allclose(actual, np.array([0.0, -180.0, -179.0, 0.0]))

    def test_mrar_longitude_normalization_matches_upstream_cleaner(self):
        actual = audit.normalize_mrar_lon(np.array([179.0, 180.0, 180.003]))
        np.testing.assert_allclose(actual, np.array([179.0, 180.0, -179.997]))

    def test_compress_ranges_is_sorted_unique_and_inclusive(self):
        self.assertEqual(
            audit.compress_ranges([8, 3, 4, 4, 7, 11]),
            [[3, 4], [7, 8], [11, 11]],
        )

    def test_official_file_entries_normalize_to_raw_dat_basename(self):
        self.assertEqual(audit.official_raw_filename("20030501.zip"), "20030501.dat")
        self.assertEqual(audit.official_raw_filename("KR13-18.dat.zip"), "KR13-18.dat")
        self.assertEqual(audit.official_raw_filename("20020117.dat"), "20020117.dat")
        self.assertEqual(
            audit.expected_official_archive("nested/2_OpenCheckData/KR13-18.dat"),
            "KR13-18.dat",
        )

    def test_nmad_requires_two_values(self):
        self.assertTrue(np.isnan(audit.nmad([2.0])))
        self.assertAlmostEqual(audit.nmad([1.0, 2.0, 3.0]), 1.4826)

    def test_grouped_nmad_matches_scalar_definition(self):
        import pandas as pd

        frame = pd.DataFrame({"group": ["a", "a", "a", "b"], "value": [1.0, 2.0, 3.0, 9.0]})
        actual = audit.grouped_nmad(frame, "group", "value")
        self.assertAlmostEqual(actual["a"], audit.nmad([1.0, 2.0, 3.0]))
        self.assertTrue(np.isnan(actual["b"]))

    def test_file_cell_diagnostics_separates_count_and_median_drift(self):
        import pandas as pd

        upstream = pd.DataFrame({
            "cell_id": ["a"], "file_id": ["f"], "n_points": [4],
            "median_depth_m_positive_down": [2.25],
        })
        raw = pd.DataFrame({
            "cell_id": ["a"], "file_id": ["f"], "raw_point_count": [4],
            "file_cell_median_m": [2.5],
        })
        result = audit.jamstec_file_cell_diagnostics(upstream, raw)
        self.assertEqual(result["raw_point_count_mismatch_rows"], 0)
        self.assertEqual(result["median_different_cells"], 1)

    def test_five_level_status_pair_validation(self):
        import pandas as pd

        valid = pd.DataFrame({"id": [1], "value": ["x"], "value_status": ["known"]})
        audit.validate_status_pairs(valid, {"id"})
        invalid = valid.copy()
        invalid["value_status"] = "guessed"
        with self.assertRaises(ValueError):
            audit.validate_status_pairs(invalid, {"id"})

    def test_forbidden_downstream_name_tokens_cover_model_outputs(self):
        self.assertIn("prediction", audit.FORBIDDEN_NAME_TOKENS)
        self.assertIn("residual", audit.FORBIDDEN_NAME_TOKENS)
        self.assertIn("error", audit.FORBIDDEN_NAME_TOKENS)

    def test_mrar_trailing_tab_does_not_shift_columns(self):
        import pandas as pd

        source = Path("ncei/archive/zhoushuai_processed_M/0-180E-0-85N.txt")
        row = pd.read_csv(
            source,
            sep="\t",
            header=None,
            names=["lon_raw", "lat_raw", "depth_raw"],
            usecols=["lon_raw", "lat_raw", "depth_raw"],
            nrows=1,
        ).iloc[0]
        self.assertEqual(row.to_dict(), {"lon_raw": 0.0, "lat_raw": 0.0, "depth_raw": -1979.0})


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import math
import unittest

import numpy as np

from ncei.code.scs_confirmation.audit_scs_tn352_mrar_support import (
    summarize_tail,
    validate_selected_source_object_count,
)
from ncei.code.scs_confirmation.freeze_scs_tn352_mrar_support import (
    assert_common_cell_count,
    compare_cell_id_sets,
    validate_matching_cell_rows,
)
from ncei.code.scs_confirmation.scs_tn352_support import (
    EARTH_RADIUS_M,
    SupportPoints,
    depth_summary,
    difference_metrics,
    great_circle_distance_m,
    mutual_nearest_pairs,
    occupancy_indices,
    spherical_centroid,
    unit_vectors,
)


def points(lon: list[float], lat: list[float], depth: list[float], groups: list[int] | None = None) -> SupportPoints:
    count = len(lon)
    return SupportPoints(
        cell_index=np.zeros(count, dtype=np.int32),
        group_code=np.asarray(groups if groups is not None else [0] * count, dtype=np.int32),
        first_index=np.arange(count, dtype=np.int64),
        second_index=np.zeros(count, dtype=np.int32),
        lon=np.asarray(lon, dtype=np.float64),
        lat=np.asarray(lat, dtype=np.float64),
        depth=np.asarray(depth, dtype=np.float64),
        navigation_valid=np.ones(count, dtype=bool),
        group_values=["a", "b"],
    )


class SupportGeometryUnitTests(unittest.TestCase):
    def test_great_circle_one_degree(self) -> None:
        left = unit_vectors(np.asarray([0.0]), np.asarray([0.0]))
        right = unit_vectors(np.asarray([1.0]), np.asarray([0.0]))
        actual = float(great_circle_distance_m(left, right)[0])
        self.assertAlmostEqual(actual, EARTH_RADIUS_M * math.pi / 180.0, places=8)

    def test_centroid_is_dateline_safe(self) -> None:
        lon, lat = spherical_centroid(np.asarray([179.0, -179.0]), np.asarray([0.0, 0.0]))
        self.assertAlmostEqual(abs(lon), 180.0, places=10)
        self.assertAlmostEqual(lat, 0.0, places=10)

    def test_mutual_pairs_are_computed_before_thresholding(self) -> None:
        tn = points([0.0, 0.001, 0.01], [0.0, 0.0, 0.0], [100.0, 110.0, 120.0])
        mrar = points([0.0001, 0.0101], [0.0, 0.0], [90.0, 100.0])
        tn_index, mrar_index, distance, minimum = mutual_nearest_pairs(tn, mrar)
        self.assertEqual(list(zip(tn_index.tolist(), mrar_index.tolist())), [(0, 0), (2, 1)])
        self.assertIsNotNone(minimum)
        self.assertTrue(np.all(distance < 20.0))

    def test_zero_match_cell_has_explicit_empty_result(self) -> None:
        empty = points([], [], [])
        nonempty = points([0.0], [0.0], [100.0])
        tn_index, mrar_index, distance, minimum = mutual_nearest_pairs(empty, nonempty)
        self.assertEqual(tn_index.size, 0)
        self.assertEqual(mrar_index.size, 0)
        self.assertEqual(distance.size, 0)
        self.assertIsNone(minimum)

    def test_equal_distance_tie_uses_lexicographic_target_key(self) -> None:
        tn = points([0.0], [0.0], [100.0])
        mrar = points([-0.001, 0.001], [0.0, 0.0], [90.0, 90.0], groups=[0, 1])
        tn_index, mrar_index, _distance, _minimum = mutual_nearest_pairs(tn, mrar)
        self.assertEqual(tn_index.tolist(), [0])
        self.assertEqual(mrar_index.tolist(), [0])

    def test_occupancy_is_anchored_at_cell_center(self) -> None:
        occupied = occupancy_indices(
            np.asarray([105.0, 105.001]),
            np.asarray([0.0, 0.0]),
            105.0,
            0.0,
        )
        self.assertEqual(occupied, {(0, 0), (1, 0)})

    def test_positive_down_difference_metrics(self) -> None:
        delta = np.asarray([100.0 - 80.0, 90.0 - 100.0])
        result = difference_metrics(delta)
        self.assertEqual(result["bias"], 5.0)
        self.assertEqual(result["mae"], 15.0)
        self.assertEqual(result["median_signed"], 5.0)

    def test_nmad_uses_registered_scale(self) -> None:
        result = depth_summary(np.asarray([10.0, 20.0, 30.0]))
        self.assertAlmostEqual(result["nmad"], 14.826)

    def test_inclusive_threshold_keeps_exact_boundary(self) -> None:
        distance = np.asarray([99.999, 100.0, 100.001])
        self.assertEqual((distance <= 100.0).tolist(), [True, True, False])

    def test_tail_contraction_requires_both_registered_ratios(self) -> None:
        rows = []
        for index in range(40):
            raw = 1000.0 if index < 20 else 100.0
            matched = 200.0 if index < 20 else 50.0
            row = {
                "raw_cell_median_delta_m": raw,
                "zero_footprint_overlap": False,
                "low_footprint_overlap": False,
                "high_relief": False,
                "small_source_support": False,
                "h03_associated_object": False,
                "unresolved_500m": False,
            }
            for threshold in (100, 250, 500):
                row[f"match_{threshold}m_count"] = 3
                row[f"match_{threshold}m_median_signed_m"] = matched
                row[f"match_{threshold}m_low_support"] = False
            rows.append(row)
        summary = summarize_tail(rows)
        matched_500 = next(row for row in summary if row["basis"] == "matched_500m" and row["stratum"] == "overall")
        self.assertEqual(matched_500["material_contraction_decision"], "materially_contracted")

    def test_tail_zero_denominator_is_not_applicable(self) -> None:
        rows = []
        for _index in range(30):
            row = {
                "raw_cell_median_delta_m": 0.0,
                "zero_footprint_overlap": False,
                "low_footprint_overlap": False,
                "high_relief": False,
                "small_source_support": False,
                "h03_associated_object": False,
                "unresolved_500m": False,
            }
            for threshold in (100, 250, 500):
                row[f"match_{threshold}m_count"] = 3
                row[f"match_{threshold}m_median_signed_m"] = 0.0
                row[f"match_{threshold}m_low_support"] = False
            rows.append(row)
        result = next(
            row
            for row in summarize_tail(rows)
            if row["basis"] == "matched_500m" and row["stratum"] == "overall"
        )
        self.assertEqual(result["material_contraction_decision"], "not_applicable")

    def test_common_cell_count_drift_fails_closed(self) -> None:
        assert_common_cell_count(2_244)
        with self.assertRaisesRegex(AssertionError, "2367 != 2244"):
            assert_common_cell_count(2_367)

    def test_frozen_ids_are_distinct_from_raw_support_only_ids(self) -> None:
        comparison = compare_cell_id_sets(
            ["1min_1_1", "1min_1_2"],
            {"1min_1_1", "1min_1_2", "1min_1_3", "1min_1_4"},
            {"1min_1_1", "1min_1_2", "1min_1_3"},
            expected_frozen_count=2,
        )
        self.assertEqual(comparison["frozen_missing_tn352"], [])
        self.assertEqual(comparison["frozen_missing_raw_support"], [])
        self.assertEqual(
            comparison["raw_support_only_not_in_frozen_scalar_pair"],
            ["1min_1_3"],
        )
        self.assertEqual(comparison["tn352_without_mrar_raw_support"], ["1min_1_4"])

    def test_missing_frozen_raw_support_is_reported_before_depth_access(self) -> None:
        comparison = compare_cell_id_sets(
            ["1min_1_1", "1min_1_2"],
            {"1min_1_1", "1min_1_2"},
            {"1min_1_1"},
            expected_frozen_count=2,
        )
        self.assertEqual(comparison["frozen_missing_raw_support"], ["1min_1_2"])

    def test_cross_source_cell_centers_allow_serialization_roundoff(self) -> None:
        tn352 = {
            "cell_id": "1min_6615_18297",
            "lon_bin": 18297,
            "lat_bin": 6615,
            "lon_center": 124.95833333333333,
            "lat_center": 20.258333333333333,
        }
        mrar = dict(tn352, lat_center=tn352["lat_center"] + 1.0e-14)
        validate_matching_cell_rows(tn352, mrar)
        with self.assertRaisesRegex(AssertionError, "latitude center differs"):
            validate_matching_cell_rows(tn352, dict(mrar, lat_center=tn352["lat_center"] + 2.0e-12))

    def test_selected_source_objects_may_be_fewer_than_all_sounding_objects(self) -> None:
        validate_selected_source_object_count(1, 2, "1min_6619_18285")
        with self.assertRaisesRegex(AssertionError, "exceeds all-sounding"):
            validate_selected_source_object_count(3, 2, "1min_6619_18285")


if __name__ == "__main__":
    unittest.main()

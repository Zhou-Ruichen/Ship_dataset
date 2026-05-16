"""Tests for `_common.r2_classifier` and `_common.io_helpers`.

Compatible with both `python -m unittest` and `pytest` (auto-discovers
unittest.TestCase classes). Real-fixture tests skip cleanly when their
files are missing (gitignored heavy data).
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

# Allow `python -m _common.tests.test_r2_classifier` or direct invocation.
TEST_DIR = Path(__file__).parent.resolve()
PKG_DIR = TEST_DIR.parent
REPO_ROOT = PKG_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

from _common.r2_classifier import (  # noqa: E402
    R2_BBOX_KM2_CUTOFF,
    R2_DENSITY_PPKM2_CUTOFF,
    R2_HARD_MB_POINTS,
    R2_HARD_SB_POINTS,
    classify,
    classify_from_arrays,
)


XYZ_DIR = REPO_ROOT / "ncei" / "tracklines_xyz"


def _make_track(n: int, lon_span_deg: float, lat_span_deg: float,
                lat_mid: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Construct n points roughly uniformly inside a bbox centered at lat_mid."""
    rng = np.random.default_rng(seed=42)
    lon = rng.uniform(-lon_span_deg / 2, lon_span_deg / 2, size=n)
    lat = rng.uniform(lat_mid - lat_span_deg / 2, lat_mid + lat_span_deg / 2, size=n)
    return lon, lat


class TestR2Hard(unittest.TestCase):
    """Hard-rule paths (point count alone determines label)."""

    def test_hard_mb(self) -> None:
        """1.5M points, sparse bbox → mb, hard_mb_points."""
        lon, lat = _make_track(1_500_000, 30.0, 30.0)
        res = classify(lon, lat)
        self.assertEqual(res.label, "mb")
        self.assertEqual(res.reason, "hard_mb_points")
        self.assertEqual(res.points, 1_500_000)
        self.assertIsNone(res.bbox_km2)
        self.assertIsNone(res.density_ppkm2)

    def test_hard_sb(self) -> None:
        """50k points → sb, hard_sb_points."""
        lon, lat = _make_track(50_000, 5.0, 5.0)
        res = classify(lon, lat)
        self.assertEqual(res.label, "sb")
        self.assertEqual(res.reason, "hard_sb_points")
        self.assertEqual(res.points, 50_000)
        self.assertIsNone(res.bbox_km2)
        self.assertIsNone(res.density_ppkm2)


class TestR2Borderline(unittest.TestCase):
    """Borderline band (100k–1M); rule = bbox<cutoff OR density>cutoff."""

    def test_borderline_swath_compact(self) -> None:
        """500k pts in a ~30x30 km bbox → mb (bbox below cutoff)."""
        # 30 km ≈ 0.27 deg lon at equator (111.32 km/deg).
        deg = 30.0 / 111.32
        lon, lat = _make_track(500_000, deg, deg)
        res = classify(lon, lat)
        self.assertEqual(res.label, "mb")
        self.assertEqual(res.reason, "borderline_bbox_below_cutoff")
        self.assertIsNotNone(res.bbox_km2)
        self.assertLess(res.bbox_km2, R2_BBOX_KM2_CUTOFF)

    def test_borderline_dense(self) -> None:
        """500k pts in a 100x100 km bbox → density 50 pts/km² → mb."""
        # 100 km ≈ 0.898 deg. 500k / 10,000 km² = 50 pts/km².
        # Bump to 0.85 deg to give density just above the cutoff (>50).
        deg = 0.85
        lon, lat = _make_track(500_000, deg, deg)
        res = classify(lon, lat)
        self.assertEqual(res.label, "mb")
        # bbox just clears the cutoff (~8800 km²), density > 50.
        self.assertIsNotNone(res.bbox_km2)
        self.assertIsNotNone(res.density_ppkm2)
        self.assertGreater(res.bbox_km2, R2_BBOX_KM2_CUTOFF)
        self.assertGreater(res.density_ppkm2, R2_DENSITY_PPKM2_CUTOFF)
        self.assertEqual(res.reason, "borderline_density_above_cutoff")

    def test_borderline_sparse_singlebeam(self) -> None:
        """500k pts over a long sparse transect → sb, default branch."""
        # 1000 km span ≈ 9 deg, lat span 1 deg (long thin transect).
        lon, lat = _make_track(500_000, 9.0, 1.0)
        res = classify(lon, lat)
        self.assertEqual(res.label, "sb")
        self.assertEqual(res.reason, "borderline_default_sb")
        self.assertIsNotNone(res.bbox_km2)
        self.assertGreater(res.bbox_km2, R2_BBOX_KM2_CUTOFF)
        self.assertLess(res.density_ppkm2, R2_DENSITY_PPKM2_CUTOFF)


class TestR2Edges(unittest.TestCase):
    """Edge cases (zero bbox, mismatched arrays, empty)."""

    def test_edge_zero_bbox(self) -> None:
        """Single-point trackline (all identical) → mb, density infinite."""
        n = 500_000
        lon = np.full(n, 10.0)
        lat = np.full(n, 5.0)
        res = classify(lon, lat)
        self.assertEqual(res.label, "mb")
        self.assertEqual(res.reason, "borderline_bbox_below_cutoff")
        # bbox is exactly 0 (degenerate); density is +inf by convention.
        self.assertEqual(res.bbox_km2, 0.0)
        self.assertTrue(math.isinf(res.density_ppkm2))

    def test_edge_mismatched_arrays(self) -> None:
        with self.assertRaises(ValueError):
            classify(np.array([1.0, 2.0]), np.array([3.0]))

    def test_edge_empty(self) -> None:
        with self.assertRaises(ValueError):
            classify(np.array([]), np.array([]))


class TestR2ClassifyFromArrays(unittest.TestCase):
    """Override-points path of classify_from_arrays."""

    def test_points_override_hard_mb(self) -> None:
        """Hard mb via explicit `points` (cheap path, no bbox computed)."""
        # Tiny actual arrays, but `points` says 2M → hard_mb_points.
        lon = np.array([0.0])
        lat = np.array([0.0])
        res = classify_from_arrays(lon, lat, points=2_000_000)
        self.assertEqual(res.label, "mb")
        self.assertEqual(res.reason, "hard_mb_points")
        self.assertEqual(res.points, 2_000_000)


class TestR2RealFixtures(unittest.TestCase):
    """Smoke checks against actual ncei/tracklines_xyz/ files.

    Skipped if the files are missing (gitignored / fresh clone).
    """

    @classmethod
    def setUpClass(cls) -> None:  # noqa: D401
        if not XYZ_DIR.is_dir():
            raise unittest.SkipTest(f"{XYZ_DIR} not present (gitignored heavy data)")
        from _common.io_helpers import read_xyz_lonlat
        cls._read = staticmethod(read_xyz_lonlat)

    def _classify_file(self, name: str):
        path = XYZ_DIR / name
        if not path.is_file():
            self.skipTest(f"{path} not present")
        lon, lat = self._read(path)
        return classify(lon, lat)

    def test_fixture_ra304_15_is_mb(self) -> None:
        """Confirmed multibeam: ra304-15.xyz (4.79M pts, ~130k km²)."""
        res = self._classify_file("ra304-15.xyz")
        self.assertEqual(res.label, "mb")
        # >1M points → hard mb path.
        self.assertEqual(res.reason, "hard_mb_points")
        self.assertGreater(res.points, R2_HARD_MB_POINTS)

    def test_fixture_short_sb_files(self) -> None:
        """Three clear short-track sb files → all sb."""
        # Files near the bottom of the size distribution (<5k pts each).
        for name in ("00373.xyz", "00574.xyz", "00873.xyz"):
            with self.subTest(file=name):
                res = self._classify_file(name)
                self.assertEqual(res.label, "sb")
                self.assertEqual(res.reason, "hard_sb_points")


if __name__ == "__main__":
    unittest.main(verbosity=2)

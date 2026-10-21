"""Regression checks for native quality, record lineage, and cell coverage."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[2]


def load(filename):
    spec = importlib.util.spec_from_file_location(filename, ROOT / "ncei/code" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QualityRevisionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extract = load("34_mb_round2_extract_points.py")
        cls.aggregate = load("07_aggregate_file_cells_1min.py")
        cls.sources = load("36_mb_round2_source_manifest_fragment.py")
        cls.revision = load("43_mb_round2_quality_revision.py")

    def test_rr1412_known_shard(self):
        path = ROOT / "ncei/derived/mb_round2/RR1412/_staging/761d2c6f1c51988d.parquet"
        df = pd.read_parquet(path)
        stats = self.extract.staging_statistics(path)
        self.assertEqual(
            [stats[k] for k in ("n_rows", "n_good", "n_flagged", "n_null", "n_unknown")],
            [189648, 163975, 25673, 0, 0],
        )
        df["depth_m_positive_down"] = df["depth_raw"]
        df["point_check_pass_basic"] = (
            np.isfinite(df["lon"]) & df["lon"].ge(-180) & df["lon"].lt(180)
            & np.isfinite(df["lat"]) & df["lat"].between(-90, 90)
            & np.isfinite(df["depth_raw"]) & df["depth_raw"].gt(0) & df["depth_raw"].le(11500)
        )
        mask = self.aggregate.point_selection_mask(df, "basic_native_good")
        self.assertEqual(int(mask.sum()), 163975)
        self.assertFalse(df.loc[mask, "native_quality_state"].eq("flagged").any())
        self.assertEqual(int(self.aggregate.point_selection_mask(df).sum()), 189648)

    def test_quality_missing_unknown_and_null(self):
        df = pd.DataFrame({
            "lon": [134.] * 6, "lat": [38.] * 6, "depth_m_positive_down": [2000.] * 6,
            "point_check_pass_basic": [True, True, True, True, True, False],
            "native_quality_state": ["good", "flagged", "null", "unknown", None, "good"],
        })
        self.assertEqual(self.aggregate.point_selection_mask(df, "basic_native_good").tolist(),
                         [True, False, False, False, False, False])
        no_quality = df.drop(columns="native_quality_state")
        self.assertEqual(int(self.aggregate.point_selection_mask(no_quality).sum()), 5)
        with self.assertRaisesRegex(ValueError, "native_quality_state"):
            self.aggregate.point_selection_mask(no_quality, "basic_native_good")

    def test_merge_and_streaming_lineage_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / "staging"
            staging.mkdir()
            df = pd.DataFrame({
                "file_ordinal": np.full(5, 119, dtype=np.int32),
                "point_index_in_file": [40, 41, 42, 43, 44],
                "time_us": np.arange(5, dtype=np.int64) + 1000000,
                "lon_raw": [134.] * 5, "lat_raw": [38.] * 5,
                "lon": [134.] * 5, "lat": [38.] * 5,
                "depth_raw": [2400., 10000., 0., 2000., 2500.],
                "native_quality_state": ["good", "flagged", "null", "unknown", "good"],
            })
            pq.write_table(pa.Table.from_pandas(df, schema=self.extract.STAGING_SCHEMA, preserve_index=False),
                           staging / "filekey.parquet")
            manifest = pd.DataFrame([{
                "filekey": "filekey", "file_ordinal": 119, "status": "skipped_exists",
                "mb_format": 41, "n_good": None, "n_rows": 5,
            }])
            old_extract_root, old_agg_root = self.extract.REPO_ROOT, self.aggregate.REPO_ROOT
            self.extract.REPO_ROOT = self.aggregate.REPO_ROOT = root
            try:
                summary = self.extract.merge_cruise("TEST", manifest, staging_dir=staging, output_dir=root / "l1")
                checked = root / summary["points_checked_path"]
                merged = pd.read_parquet(checked)
                self.assertEqual(merged["staging_row"].tolist(), list(range(5)))
                self.assertEqual(merged["point_index_in_file"].tolist(), [40, 41, 42, 43, 44])
                self.assertEqual(merged["native_quality_state"].tolist(), df["native_quality_state"].tolist())
                self.assertEqual(summary["n_pass_basic"], 4)
                self.assertEqual(summary["n_selected_basic_native_good"], 2)
                self.assertEqual(manifest.iloc[0]["n_good"], 2)
                self.assertEqual(summary["n_unknown"], 1)
                outputs = []
                for batch_size in (None, 2):
                    output = root / f"cells_{batch_size}.parquet"
                    result = self.aggregate.aggregate_track_file(
                        input_path=checked, output_path=output, track_id="test",
                        source_type="ncei_mb41", source_completeness="mb41_only",
                        instrument_class_pred="multibeam", branch="multibeam_ncei",
                        manual_review_flag=False, overwrite=False,
                        selection_policy="basic_native_good", batch_size=batch_size,
                    )
                    self.assertEqual(result["n_selected"], 2)
                    outputs.append(pd.read_parquet(output))
                pd.testing.assert_frame_equal(*outputs)
                result = self.aggregate.aggregate_track_file(
                    input_path=checked, output_path=root / "excluded.parquet", track_id="test",
                    source_type="ncei_mb41", source_completeness="mb41_only",
                    instrument_class_pred="multibeam", branch="multibeam_ncei",
                    manual_review_flag=False, overwrite=False, selection_policy="basic_native_good",
                    batch_size=2, excluded_records=pd.DataFrame([{
                        "filekey": "filekey", "file_ordinal": 119, "staging_row": 4,
                    }]),
                )
                self.assertEqual(result["n_selected"], 1)
                self.assertEqual(result["n_excluded_selected_records"], 1)
            finally:
                self.extract.REPO_ROOT, self.aggregate.REPO_ROOT = old_extract_root, old_agg_root

    def test_both_source_directory_layouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "ncei/raw_round2/platforms_tree"
            old_root = self.sources.REPO_ROOT
            self.sources.REPO_ROOT = root
            try:
                for prefix, cruise in (("ship/", "SHIPPED"), ("", "FLAT")):
                    path = raw / f"{prefix}{cruise}/sonar/data.gz"
                    path.parent.mkdir(parents=True)
                    path.touch()
                    source, manifest = self.sources.resolve_source_paths(
                        cruise, pd.DataFrame([{"relpath": f"{cruise}/sonar/data.gz"}]), raw
                    )
                    self.assertEqual(source, f"raw_round2/platforms_tree/{prefix}{cruise}")
                    self.assertEqual(manifest.iloc[0]["source_relpath"], f"{prefix}{cruise}/sonar/data.gz")
            finally:
                self.sources.REPO_ROOT = old_root

    def test_complete_edge_neighborhood_and_unique_cells(self):
        grid = self.revision.expected_cells(132.00833333333333, 38.00833333333333)
        duplicated = pd.concat([grid, grid])
        metrics = self.revision.coverage_metric(set(duplicated["cell_id"]), grid)
        self.assertEqual(metrics["core_coverage"], 1.)
        self.assertEqual(metrics["ring_coverage"], 1.)
        self.assertEqual(metrics["min_sector_coverage"], 1.)
        cropped = grid.loc[grid["lon_center"].ge(132)]
        truncated = self.revision.coverage_metric(set(cropped["cell_id"]), grid)
        self.assertLess(truncated["ring_coverage"], 1.)
        self.assertLess(truncated["core_coverage"], 1.)

    def test_diagnosis_and_final_file_quality_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            l1 = root / "TEST"
            (l1 / "points_checked").mkdir(parents=True)
            points = pd.DataFrame({
                "filekey": ["key"] * 4, "file_ordinal": [0] * 4, "staging_row": [0, 1, 2, 3],
                "lon": [134., 135., 134., 134.], "lat": [38.] * 4,
                "depth_m_positive_down": [2400., 10000., 2500., np.nan],
                "point_check_pass_basic": [True, True, True, False],
                "native_quality_state": ["good", "good", "flagged", "null"],
            })
            points.to_parquet(l1 / "points_checked/points.parquet", index=False)
            manifest = pd.DataFrame([{
                "filekey": "key", "file_ordinal": 0, "source_relpath": "ship/TEST/data.gz",
                "mb_format": 41, "n_rows": 4, "n_good": 2, "n_flagged": 1,
                "n_null": 1, "n_unknown": 0, "n_pass_basic": 3,
                "n_selected_basic_native_good": 2,
            }])
            empty = {column: 0 for column in manifest if column.startswith("n_")}
            empty.update(filekey="empty", file_ordinal=1, source_relpath="ship/TEST/empty.gz", mb_format=41)
            pd.concat([manifest, pd.DataFrame([empty])]).to_parquet(
                l1 / "extraction_manifest.parquet", index=False,
            )
            diagnosis = root / "diagnosis.parquet"
            pd.DataFrame([{
                "staging_stem": "key", "file_ordinal": 0, "staging_row": 1,
                "cell_id": "1min_7680_18900", "point_check_pass_basic": True,
                "native_quality_state": "good",
            }]).to_parquet(diagnosis, index=False)
            records = self.revision.read_record_list(diagnosis)
            self.assertEqual(records.iloc[0]["filekey"], "key")
            self.assertIn("cell_id", records)
            jam, strict = root / "jam.parquet", root / "strict.parquet"
            pd.DataFrame({"cell_id": ["a"], "median_depth_file_balanced": [2390.]}).to_parquet(jam)
            pd.DataFrame({"cell_id": ["a"], "representative_depth_m": [2390.]}).to_parquet(strict)
            l2 = pd.DataFrame({
                "track_id": ["test"], "cell_id": ["a"], "n_points_pass": [1], "median_depth_m": [2400.],
            })
            with patch.object(self.revision, "JAM", jam), patch.object(self.revision, "STRICT", strict), \
                    patch.object(self.revision, "read_cells", return_value=l2):
                files, cruises = self.revision.quality_tables(root, ["TEST"], root, diagnosis, diagnosis)
            self.assertEqual(files.iloc[0]["n_selected"], 1)
            self.assertEqual(files.iloc[0]["n_excluded_selected_records"], 1)
            self.assertEqual(files.iloc[0]["n_cells_1min"], 1)
            self.assertEqual(files.iloc[0]["flagged_proportion"], .25)
            self.assertEqual(files.iloc[0]["r2_affected_record_count"], 1)
            self.assertEqual(files.iloc[0]["source_relpath"], "ship/TEST/data.gz")
            self.assertTrue(pd.isna(files.iloc[1]["flagged_proportion"]))
            self.assertTrue(pd.isna(files.iloc[1]["has_native_edit_flag"]))
            self.assertEqual(cruises.iloc[0]["n_selected"], 1)
            self.assertEqual(cruises.iloc[1]["status"], "unprocessed_by_current_parser")


if __name__ == "__main__":
    unittest.main()

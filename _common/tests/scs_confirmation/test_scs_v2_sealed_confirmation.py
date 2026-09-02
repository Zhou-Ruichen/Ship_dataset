import ast
import importlib
import tempfile
import unittest
from pathlib import Path

import pandas as pd


discover = importlib.import_module("ncei.code.scs_confirmation.discover_scs_v2_sealed_confirmation")
verify = importlib.import_module("ncei.code.scs_confirmation.verify_scs_v2_sealed_confirmation")


class SCSV2SealedConfirmationStageATest(unittest.TestCase):
    def test_cruise_aliases_normalize_leg_without_collapsing_suffix(self):
        self.assertEqual(discover.cruise_aliases("ab_24-01_leg2"), {"AB-24-01-LEG2", "AB-24-01"})
        self.assertEqual(discover.cruise_aliases("AB24-01C"), {"AB24-01C"})
        self.assertTrue(discover.overlaps_ids("ab_24-01_leg2", ["AB-24-01"]))

    def test_bbox_uses_official_geometry_and_half_open_scs_boundary(self):
        geometry = {"paths": [[[104.0, -1.0], [106.0, 1.0], [126.0, 26.0]]]}
        bbox = discover.geometry_bbox(geometry)
        self.assertEqual(bbox, [104.0, -1.0, 126.0, 26.0])
        area = {"xmin": 105.0, "ymin": 0.0, "xmax": 125.0, "ymax": 25.0}
        self.assertTrue(discover.bbox_intersects(bbox, area))
        self.assertFalse(discover.bbox_intersects([125.0, 1.0, 126.0, 2.0], area))

    def test_polyline_intersection_handles_dateline_and_crossing_segments(self):
        area = {"xmin": 105.0, "ymin": 0.0, "xmax": 125.0, "ymax": 25.0}
        dateline = {"paths": [[[179.0, 22.0], [-179.0, 23.0]]]}
        crossing = {"paths": [[[100.0, 10.0], [130.0, 10.0]]]}
        upper_boundary = {"paths": [[[110.0, 25.0], [120.0, 25.0]]]}
        self.assertFalse(discover.geometry_intersects_area(dateline, area))
        self.assertTrue(discover.geometry_intersects_area(crossing, area))
        self.assertFalse(discover.geometry_intersects_area(upper_boundary, area))
        self.assertGreater(discover.geometry_track_length_in_area_km(crossing, area), 2000.0)
        self.assertEqual(discover.geometry_track_length_in_area_km(dateline, area), 0.0)
        self.assertEqual(
            discover.geometry_intersects_area(dateline, area),
            verify.geometry_intersects_area(dateline, area),
        )

    def test_detail_html_parses_metadata_without_following_archive_link(self):
        body = b"""
        <html><body><h2>Constraints</h2><p>Public access.</p>
        <a href="/files/list?survey=AB24-01">Cruise File List (download)</a>
        <div>Distribution Formats MBF_EM2040RAW INFO_TAR</div>
        <div>Vertical Datum: Mean Sea Level</div></body></html>
        """
        detail = discover.parse_detail_html(body, "https://www.ncei.noaa.gov/item/AB24-01")
        self.assertEqual(detail["download_url"], "https://www.ncei.noaa.gov/files/list?survey=AB24-01")
        self.assertTrue(detail["raw_archive_documented"])
        self.assertIn("MBF_EM2040RAW", detail["distribution_formats"])
        self.assertTrue(detail["vertical_datum"].startswith("Mean Sea Level"))

    def test_fetch_recorder_rejects_candidate_archive_role(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = discover.FetchRecorder(Path(directory), 1, "test", [], [])
            with self.assertRaises(ValueError):
                recorder.get("https://example.noaa.gov/a.zip", "a.zip", "candidate_archive")

    def test_candidate_factual_fields_require_closed_statuses(self):
        valid = pd.DataFrame({"value": ["x"], "value_status": ["known"]})
        discover.validate_status_pairs(valid)
        invalid = valid.copy()
        invalid["value_status"] = "guessed"
        with self.assertRaises(ValueError):
            discover.validate_status_pairs(invalid)

    def test_required_sealed_status_is_a_value_with_its_own_status_pair(self):
        frame = pd.DataFrame({
            "sealed_status": ["selected_unsealed"],
            "sealed_status_status": ["known"],
        })
        discover.validate_status_pairs(frame)
        self.assertEqual(verify.check_status_pairs(frame, "candidate"), {"value_columns": 1, "status_columns": 1})

    def test_zero_candidate_registry_is_contractually_valid(self):
        candidate = pd.DataFrame(columns=[
            "official_cruise_id", "archive", "date", "instrument", "bbox",
            "file_count", "available_fields", "vertical_datum_status",
            "overlap_with_current_19", "overlap_with_exposed_12",
            "possible_MRAR_overlap", "ever_read_by_repo", "sealed_status",
            "exclusion_reason", "geometry_intersects_scs", "geometry_basis",
            "scs_track_length_km",
        ])
        self.assertEqual(len(candidate), 0)
        self.assertTrue(verify.REQUIRED_CANDIDATE_COLUMNS.issubset(candidate.columns))

    def test_stage_a_producer_has_no_archive_or_sounding_reader_import(self):
        path = Path("ncei/code/scs_confirmation/discover_scs_v2_sealed_confirmation.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        self.assertFalse(imports & discover.FORBIDDEN_ARCHIVE_MODULES)

    def test_preliminary_rank_prefers_post_delivery_metadata(self):
        older = {"start_date": "2020-01-01", "official_cruise_id": "OLD", "date": "2020", "instrument": "A", "bbox": "[]", "archive": "u", "file_count": 1, "bathy_beams_documented": True}
        newer = {"start_date": "2026-06-01", "official_cruise_id": "NEW", "date": "2026", "instrument": "A", "bbox": "[]", "archive": "u", "file_count": 1, "bathy_beams_documented": True}
        cutoff = "2026-05-15"
        self.assertLess(discover.preliminary_sort_key(newer, cutoff), discover.preliminary_sort_key(older, cutoff))

    def test_filesystem_filename_hit_detects_raw_and_qc_exposure(self):
        inventory = pd.DataFrame({
            "repository": ["ship", "ship"],
            "relative_path": [
                "ncei/tracklines_nc/ab2401.nc",
                "ncei/derived/points_checked/other.parquet",
            ],
        })
        hits = discover.identity_filesystem_hits(inventory, "AB2401")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["scope"], "current_filesystem_filename")
        self.assertEqual(verify.inventory_identity_paths(inventory, "AB2401"), ["ncei/tracklines_nc/ab2401.nc"])

    def test_metadata_paths_are_rewritten_to_final_run(self):
        evidence = [{"path": "/tmp/.run/evidence/item.json"}]
        queries = [{"response_path": "/tmp/.run/evidence/item.json"}, {"response_path": ""}]
        final = Path("/data/discovery/run")
        discover.finalize_metadata_paths(evidence, queries, final)
        self.assertEqual(evidence[0]["path"], "/data/discovery/run/metadata_evidence/item.json")
        self.assertEqual(queries[0]["response_path"], "/data/discovery/run/metadata_evidence/item.json")
        self.assertEqual(queries[1]["response_path"], "")


if __name__ == "__main__":
    unittest.main()

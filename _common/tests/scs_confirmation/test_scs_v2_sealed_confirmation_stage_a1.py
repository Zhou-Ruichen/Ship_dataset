import ast
import importlib
import unittest
from pathlib import Path


stage_a1 = importlib.import_module("ncei.code.scs_confirmation.discover_scs_v2_sealed_confirmation_stage_a1")


class SCSV2SealedConfirmationStageA1Test(unittest.TestCase):
    def test_directory_link_parser_keeps_only_descendants(self):
        body = b"""
        <html><body>
          <a href="../">Parent Directory</a>
          <a href="?C=N;O=D">sort</a>
          <a href="raw/">raw/</a>
          <a href="file.all.gz">file.all.gz</a>
          <a href="https://example.org/escape.all">escape</a>
        </body></html>
        """
        directories, objects = stage_a1.parse_directory_listing(
            body,
            "https://data.ngdc.noaa.gov/root/",
            "https://data.ngdc.noaa.gov/root/",
            "data.ngdc.noaa.gov",
        )
        self.assertEqual(directories, ["https://data.ngdc.noaa.gov/root/raw/"])
        self.assertEqual(objects, ["https://data.ngdc.noaa.gov/root/file.all.gz"])

    def test_physical_object_format_and_role_are_filename_inferences(self):
        self.assertEqual(stage_a1.infer_format_role("line_001.all.gz"), (".all.gz", "raw_sounding_compressed"))
        self.assertEqual(stage_a1.infer_format_role("line_001.mb58.gz"), (".mb58.gz", "multibeam_data_compressed"))
        self.assertEqual(stage_a1.infer_format_role("line_001.fnv"), (".fnv", "navigation_sidecar"))
        self.assertEqual(stage_a1.infer_format_role("README.txt"), (".txt", "documentation"))

    def test_chronology_precedes_track_length(self):
        newer_short = {"date": "2021-01-01/2021-01-02", "scs_track_length_km": 1.0, "official_cruise_id": "NEW"}
        older_long = {"date": "2018-01-01/2018-01-02", "scs_track_length_km": 9999.0, "official_cruise_id": "OLD"}
        cutoff = "2026-05-15T12:26:27Z"
        self.assertLess(stage_a1.chronology_rank_key(newer_short, cutoff), stage_a1.chronology_rank_key(older_long, cutoff))

    def test_comparison_cohort_has_no_top_five_cap(self):
        rows = [
            {
                "official_cruise_id": f"C{index}",
                "date": f"20{18 + index % 4}-01-01/20{18 + index % 4}-01-02",
                "ever_read_by_repo": "false",
                "overlap_with_current_19": "false",
                "overlap_with_exposed_12": "false",
                "geometry_intersects_scs": True,
                "archive": f"https://data.ngdc.noaa.gov/root/C{index}/",
                "scs_track_length_km": float(index),
            }
            for index in range(8)
        ]
        selected = stage_a1.select_comparison_rows(rows, 2018, "data.ngdc.noaa.gov")
        self.assertEqual(len(selected), 8)

    def test_head_request_source_has_no_range_or_get_fallback(self):
        source = Path("ncei/code/scs_confirmation/discover_scs_v2_sealed_confirmation_stage_a1.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "head_physical_object")
        function_source = ast.get_source_segment(source, function)
        self.assertIn('method="HEAD"', function_source)
        self.assertNotIn('"Range"', function_source)
        self.assertNotIn("response.read", function_source)
        self.assertNotIn('method="GET"', function_source)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ncei.code.audit_scs_tn352_processing import build_change_rows, compare_candidates
from ncei.code.scs_tn352_audit_common import (
    CONTRACT_FIELDS,
    one_min_cell,
    read_contract_tsv,
    safe_run_id,
    write_contract_tsv,
)


class ProcessingAuditUnitTests(unittest.TestCase):
    def test_contract_tsv_round_trip_preserves_types(self) -> None:
        record = dict.fromkeys(CONTRACT_FIELDS)
        record.update(
            {
                "contract_item_id": "T-01",
                "category": "test",
                "item": "typed value",
                "status": "known_from_output",
                "observed_value": {"count": 3, "flags": [True, False]},
                "unit": None,
                "evidence_path": "example.json",
                "evidence_locator": "/value",
                "evidence_sha256": "a" * 64,
                "notes": "",
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.tsv"
            write_contract_tsv(path, [record])
            self.assertEqual(read_contract_tsv(path), [record])

    def test_candidate_comparison_separates_added_removed_and_changed(self) -> None:
        old = {
            "1min_1_1": {"median_depth_m_positive_down_exact": 10.0},
            "1min_1_2": {"median_depth_m_positive_down_exact": 20.0},
            "1min_1_4": {"median_depth_m_positive_down_exact": 40.0},
        }
        new = {
            "1min_1_1": {"median_depth_m_positive_down_exact": 10.0},
            "1min_1_2": {"median_depth_m_positive_down_exact": 21.0},
            "1min_1_3": {"median_depth_m_positive_down_exact": 30.0},
        }
        self.assertEqual(compare_candidates(old, new), (["1min_1_3"], ["1min_1_4"], ["1min_1_2"]))

    def test_change_row_uses_positive_down_new_minus_old(self) -> None:
        old = {
            "1min_5400_17100": {
                "n_qc_eligible": 3,
                "median_depth_m_positive_down_exact": 20.0,
            }
        }
        new = {
            "1min_5400_17100": {
                "lon_bin": 17100,
                "lat_bin": 5400,
                "lon_center": 105.00833333333334,
                "lat_center": 0.008333333333333333,
                "n_qc_eligible": 4,
                "median_depth_m_positive_down_exact": 25.0,
            }
        }
        recovered = {"1min_5400_17100": {"n_all": 1, "n_eligible": 1, "eligible_depths": [40.0]}}
        rows = build_change_rows(
            old,
            new,
            [],
            ["1min_5400_17100"],
            recovered,
            {"1min_5400_17100": [10.0, 20.0, 30.0]},
            {"1min_5400_17100": [10.0, 20.0, 30.0, 40.0]},
        )
        self.assertEqual(rows[0]["signed_median_change_m"], 5.0)
        self.assertEqual(rows[0]["recovered_above_old_median"], 1)

    def test_run_id_and_cell_formula(self) -> None:
        self.assertEqual(safe_run_id("20260810T010203Z"), "20260810T010203Z")
        with self.assertRaises(AssertionError):
            safe_run_id("../bad")
        self.assertEqual(one_min_cell(105.0, 0.0)[:3], (17100, 5400, "1min_5400_17100"))

    def test_report_checks_may_cross_markdown_line_breaks(self) -> None:
        report = "It ran no\nGGM, PINN, GEBCO comparison."
        self.assertIn("no GGM, PINN, GEBCO", " ".join(report.split()))


if __name__ == "__main__":
    unittest.main()

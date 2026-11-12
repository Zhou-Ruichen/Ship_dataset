"""Focused checks for the JAMSTEC package refactor."""

from __future__ import annotations

import contextlib
import io
import unittest

from jamstec.multibeam import __main__ as cli
from jamstec.multibeam.extreme_bias import _classify_action
from jamstec.multibeam.io import file_id_to_parquet_name
from jamstec.multibeam.rules import load_extreme_bias_rules, load_file_exclusion_rules


class JamstecPipelineTest(unittest.TestCase):
    def test_every_command_help_is_safe(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main([]), 0)
            for command in cli.COMMANDS:
                with self.subTest(command=command):
                    with self.assertRaises(SystemExit) as caught:
                        cli.main([command, "--help"])
                    self.assertEqual(caught.exception.code, 0)

    def test_file_id_shard_name_contract(self):
        self.assertEqual(
            file_id_to_parquet_name("KY12-08::20120614.dat"),
            "KY12-08__20120614.parquet",
        )
        self.assertEqual(
            file_id_to_parquet_name("group::nested/file.dat"),
            "group__nested__file.parquet",
        )

    def test_reviewed_exception_tables(self):
        extreme = load_extreme_bias_rules()
        self.assertEqual(
            set(extreme["rule_id"]),
            {"KY09_09_cruise", "KY12_08_20120614_file"},
        )
        exclusions = load_file_exclusion_rules()
        self.assertEqual(len(exclusions), 5)
        self.assertTrue(all(rule["exclude_from_primary_cells"] for rule in exclusions))

    def test_exception_action_semantics(self):
        action, reason = _classify_action(
            100, 600.0, 0.0, "KY09-09", "cruise"
        )
        self.assertEqual(action, "exclude_candidate")
        assert reason is not None
        self.assertTrue(reason.startswith("KY09-09:"))

        action, reason = _classify_action(
            100, 0.0, 0.0, "KY12-08::20120614.dat", "file", other_file_med=600.0
        )
        self.assertEqual(action, "exclude_candidate")
        assert reason is not None
        self.assertIn("other_file_median", reason)


if __name__ == "__main__":
    unittest.main()

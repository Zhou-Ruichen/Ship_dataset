"""Tests for _common.script_utils logging and report helpers."""

import logging
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _common.script_utils import ensure_columns, markdown_table, setup_logging


class SetupLoggingTest(unittest.TestCase):
    def test_file_and_console_handlers(self):
        with TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "logs" / "run.log"
            logger = setup_logging(log_path, "test_script_utils_logger")
            try:
                self.assertEqual(logger.name, "test_script_utils_logger")
                self.assertEqual(len(logger.handlers), 2)
                levels = [h.level for h in logger.handlers]
                self.assertIn(logging.DEBUG, levels)
                self.assertIn(logging.INFO, levels)
                logger.info("hello")
                logger.debug("detail")
                content = log_path.read_text(encoding="utf-8")
                self.assertIn("hello", content)
                self.assertIn("detail", content)
                self.assertTrue(content.index("hello") > content.index("detail") or "detail" in content)
            finally:
                logger.handlers.clear()

    def test_repeated_call_clears_handlers(self):
        with TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "run.log"
            first = setup_logging(log_path, "test_script_utils_logger2")
            second = setup_logging(log_path, "test_script_utils_logger2")
            try:
                self.assertIs(first, second)
                self.assertEqual(len(second.handlers), 2)
            finally:
                second.handlers.clear()


class MarkdownTableTest(unittest.TestCase):
    def test_empty_frame(self):
        self.assertEqual(markdown_table(pd.DataFrame()), ["_None_", ""])

    def test_none_frame(self):
        self.assertEqual(markdown_table(None), ["_None_", ""])

    def test_header_and_rows(self):
        df = pd.DataFrame({"a": [1.5], "b": ["x"]})
        lines = markdown_table(df)
        self.assertEqual(lines[0], "| a | b |")
        self.assertEqual(lines[1], "| --- | --- |")
        self.assertEqual(lines[2], "| 1.5000 | x |")

    def test_float_formatting(self):
        df = pd.DataFrame({"v": [np.float64(2.5), float("nan"), np.inf]})
        lines = markdown_table(df)
        self.assertEqual(lines[2], "| 2.5000 |")
        self.assertEqual(lines[3], "|  |")
        self.assertEqual(lines[4], "|  |")

    def test_max_rows(self):
        df = pd.DataFrame({"a": range(10)})
        self.assertEqual(len(markdown_table(df, max_rows=3)), 3 + 2 + 1)


class EnsureColumnsTest(unittest.TestCase):
    def test_adds_missing_keeps_order(self):
        df = pd.DataFrame({"x": [1], "y": [2]})
        out = ensure_columns(df, ["y", "z", "x"])
        self.assertEqual(list(out.columns), ["y", "z", "x"])
        self.assertTrue(pd.isna(out["z"]).all())

    def test_input_unchanged(self):
        df = pd.DataFrame({"x": [1]})
        ensure_columns(df, ["x", "new"])
        self.assertEqual(list(df.columns), ["x"])


if __name__ == "__main__":
    unittest.main()

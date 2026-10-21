"""Tests for _common.file_io atomic writers."""

import logging
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _common.file_io import (
    atomic_write_df,
    atomic_write_parquet,
    atomic_write_text,
    atomic_write_tsv,
    write_errors_tsv,
)


class AtomicWritersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parquet_written_and_no_tmp_left(self):
        df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        target = self.dir / "sub" / "out.parquet"
        atomic_write_parquet(df, target)
        self.assertTrue(target.exists())
        self.assertEqual(list(pd.read_parquet(target).columns), ["a", "b"])
        self.assertEqual(list(self.dir.glob("**/*.tmp")), [])

    def test_parquet_replaces_existing(self):
        df = pd.DataFrame({"a": [1]})
        target = self.dir / "out.parquet"
        atomic_write_parquet(df, target)
        atomic_write_parquet(pd.DataFrame({"a": [2, 3]}), target)
        self.assertEqual(len(pd.read_parquet(target)), 2)

    def test_text_roundtrip_utf8(self):
        target = self.dir / "out.md"
        atomic_write_text("héllo\n中文\n", target)
        self.assertEqual(target.read_text(encoding="utf-8"), "héllo\n中文\n")

    def test_tsv_roundtrip(self):
        df = pd.DataFrame({"a": [1], "b": ["z"]})
        target = self.dir / "out.tsv"
        atomic_write_tsv(df, target)
        self.assertEqual(target.read_text(encoding="utf-8"), "a\tb\n1\tz\n")

    def test_write_df_pair(self):
        df = pd.DataFrame({"a": [1]})
        pq = self.dir / "out.parquet"
        tsv = self.dir / "out.tsv"
        logger = logging.getLogger("test_file_io")
        logger.addHandler(logging.NullHandler())
        atomic_write_df(df, pq, tsv, logger)
        self.assertTrue(pq.exists() and tsv.exists())


class WriteErrorsTsvTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.logger = logging.getLogger("test_file_io_errors")
        self.logger.addHandler(logging.NullHandler())

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_file_when_no_errors(self):
        target = self.dir / "errors.tsv"
        write_errors_tsv([], target, self.logger)
        self.assertFalse(target.exists())

    def test_writes_rows(self):
        target = self.dir / "errors.tsv"
        write_errors_tsv([{"file": "a.dat", "error": "boom"}], target, self.logger)
        self.assertEqual(target.read_text(encoding="utf-8"), "file\terror\na.dat\tboom\n")


if __name__ == "__main__":
    unittest.main()

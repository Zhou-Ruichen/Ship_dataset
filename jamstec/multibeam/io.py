"""JAMSTEC-specific adapters for shared atomic writers."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

from _common.file_io import atomic_write_parquet as _atomic_write_parquet
from _common.file_io import atomic_write_tsv as _atomic_write_tsv


def atomic_write_parquet(df: pd.DataFrame, target: Path, logger: logging.Logger) -> None:
    """Write Parquet atomically and retain the historical log message."""
    _atomic_write_parquet(df, target)
    logger.info("Wrote %s (%d rows)", target, len(df))


def atomic_write_tsv(df: pd.DataFrame, target: Path, logger: logging.Logger) -> None:
    """Write TSV atomically and retain the historical log message."""
    _atomic_write_tsv(df, target)
    logger.info("Wrote %s (%d rows)", target, len(df))


def write_errors_tsv(errors: list[dict], target: Path, logger: logging.Logger) -> None:
    """Write an audit error table, including an empty table after a clean run."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    pd.DataFrame(errors).to_csv(tmp, sep="\t", index=False)
    os.replace(tmp, target)
    logger.info("Wrote %d error rows to %s", len(errors), target)


def file_id_to_parquet_name(file_id: str) -> str:
    """Map the stable ``subzip::filename`` identifier to its shard filename."""
    safe = file_id.replace("::", "__").replace("/", "__")
    if safe.endswith(".dat"):
        safe = safe[:-4]
    return safe + ".parquet"

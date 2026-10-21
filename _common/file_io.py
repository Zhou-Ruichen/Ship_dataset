"""Atomic file writers shared by the production pipelines.

Every writer builds its output at a ``.tmp`` sibling first and then
``os.replace``s it onto the final path, so a crashed run never leaves a
half-written parquet/tsv/text file that a later step could mistake for a
complete one.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd


def atomic_write_parquet(df: pd.DataFrame, target: Path) -> None:
    """Write a DataFrame to a parquet file atomically (tmp file + rename)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    df.to_parquet(tmp, index=False, engine="pyarrow")
    os.replace(tmp, target)


def atomic_write_text(text: str, target: Path) -> None:
    """Write UTF-8 text to a file atomically (tmp file + rename)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)


def atomic_write_tsv(df: pd.DataFrame, target: Path) -> None:
    """Write a DataFrame as tab-separated text atomically (tmp file + rename)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    os.replace(tmp, target)


def atomic_write_df(
    df: pd.DataFrame,
    target_parquet: Path,
    target_tsv: Path,
    logger: logging.Logger,
) -> None:
    """Write the same DataFrame to a parquet/tsv pair atomically.

    Both temp files are fully written before either rename happens, so a
    crash cannot leave a parquet file without its tsv twin.
    """
    target_parquet.parent.mkdir(parents=True, exist_ok=True)

    tmp_pq = target_parquet.with_suffix(".parquet.tmp")
    tmp_tsv = target_tsv.with_suffix(".tsv.tmp")

    df.to_parquet(tmp_pq, index=False)
    logger.info(f"Wrote temp parquet: {tmp_pq}")

    df.to_csv(tmp_tsv, sep="\t", index=False)
    logger.info(f"Wrote temp tsv: {tmp_tsv}")

    os.replace(tmp_pq, target_parquet)
    os.replace(tmp_tsv, target_tsv)
    logger.info(f"Renamed to final: {target_parquet.name}, {target_tsv.name}")


def write_errors_tsv(errors: list[dict], errors_path: Path, logger: logging.Logger) -> None:
    """Write per-file failure records to a TSV (skipped when there are none)."""
    if not errors:
        return
    errors_path.parent.mkdir(parents=True, exist_ok=True)
    df_err = pd.DataFrame(errors)
    df_err.to_csv(errors_path, sep="\t", index=False)
    logger.info(f"Wrote {len(errors)} errors to {errors_path}")

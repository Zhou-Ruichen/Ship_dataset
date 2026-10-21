"""Logging setup and markdown report helpers shared by the production pipelines.

``setup_logging`` gives every stage script the same dual sink: a DEBUG
file log next to the outputs plus an INFO stream handler for the
console. ``markdown_table`` renders a DataFrame preview as GitHub
markdown table lines for the per-stage report files.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def setup_logging(log_path: Path, name: str) -> logging.Logger:
    """Configure a per-script logger with a DEBUG file and INFO console handler.

    ``name`` becomes the logger name; each call clears previously
    installed handlers so re-running a script in one process cannot
    stack duplicate handlers.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s")
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(levelname)-8s %(message)s"))
    logger.addHandler(ch)
    return logger


def ensure_columns(df: pd.DataFrame, columns) -> pd.DataFrame:
    """Return ``df`` with exactly ``columns`` (missing ones filled with pd.NA)."""
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = pd.NA
    return out[list(columns)]


def markdown_table(df: pd.DataFrame, max_rows: int = 30) -> list[str]:
    """Render up to ``max_rows`` rows of ``df`` as markdown table lines.

    Floats (python or numpy) are printed with 4 decimals, non-finite
    floats and NaN render as empty cells, and an empty/None frame
    renders as a single ``_None_`` line.
    """
    if df is None or len(df) == 0:
        return ["_None_", ""]
    preview = df.head(max_rows).copy()
    cols = list(preview.columns)
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for _, row in preview.iterrows():
        vals: list[str] = []
        for col in cols:
            val = row[col]
            if isinstance(val, (float, np.floating)):
                vals.append(f"{val:.4f}" if np.isfinite(val) else "")
            elif pd.isna(val):
                vals.append("")
            else:
                vals.append(str(val))
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")
    return lines

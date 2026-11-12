"""Summarize discovered file formats without decoding source soundings."""

from __future__ import annotations

import pandas as pd

from .sources import Source


def census_rows(cruise: str, inputs: list[Source]) -> list[dict]:
    if not inputs:
        return [{"cruise": cruise, "mb_format": None, "supported": False,
                 "status": "no_source_files", "n_files": 0, "raw_bytes": 0}]
    groups = {}
    for source in inputs:
        counts = groups.setdefault((source.mb_format, source.supported), [0, 0])
        counts[0] += 1
        counts[1] += source.bytes
    return [{"cruise": cruise, "mb_format": fmt, "supported": supported,
             "status": "supported" if supported else "unsupported", "n_files": n, "raw_bytes": size}
            for (fmt, supported), (n, size) in groups.items()]

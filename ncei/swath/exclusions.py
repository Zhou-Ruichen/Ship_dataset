"""Build the default ping exclusions and the separate HNRO14RR beam keys."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from _common.file_io import atomic_write_parquet

from .selection import PING_ID
from .sources import HISTORICAL, ROOT

REVISION = ROOT / "ncei/derived/processing_revision_20261025/swath"
REVIEWS = (
    REVISION / "navigation_review/ping_navigation_review.parquet",
    REVISION / "navigation_review_hnro05rr/ping_navigation_review.parquet",
)
EXCLUSION_TABLE = "excluded_pings.parquet"
SENSITIVITY_TABLE = "hnro14rr_sensitivity_beams.parquet"
PING_KEYS = ["filekey", *PING_ID]
DIAGNOSIS = HISTORICAL / "_runs/20261021_hnro14rr_diagnosis/v2/affected_records_v1_union_v2.parquet"


def write_default(path: Path, revision_root: Path = REVISION) -> None:
    reviews = [revision_root / review.relative_to(REVISION) for review in REVIEWS]
    frames = [pd.read_parquet(review, columns=PING_KEYS, filters=[
        ("source_navigation_invalid_confirmed", "=", True),
    ]) for review in reviews]
    atomic_write_parquet(pd.concat(frames, ignore_index=True).sort_values(PING_KEYS), path)


def load(path: Path | None) -> dict[str, set[tuple[int, int, int]]]:
    if path is None:
        return {}
    rows = pd.read_parquet(path, columns=PING_KEYS)
    if rows.isna().any().any() or rows.duplicated().any():
        raise ValueError(f"missing or duplicate ping identities: {path}")
    return {key: set(group[PING_ID].itertuples(index=False, name=None))
            for key, group in rows.groupby("filekey")}


def write_sensitivity(path: Path, historical_root: Path = HISTORICAL) -> None:
    """Translate the reviewed MB41 beam keys without widening them to whole pings."""
    columns = ["staging_stem", "staging_row", "file_ordinal", "time_us", "ping_number", "beam_index"]
    diagnosis = pd.read_parquet(historical_root / DIAGNOSIS.relative_to(HISTORICAL), columns=columns).rename(columns={"staging_stem": "filekey"})
    frames = []
    for key, group in diagnosis.groupby("filekey", sort=False):
        staging = historical_root / "HNRO14RR/_staging" / f"{key}.parquet"
        table = pq.read_table(staging, columns=["file_ordinal", "time_us", "point_index_in_file"])
        beams = table.take(group.staging_row.to_numpy()).to_pandas()
        # The MB41 diagnosis matched 151 beams per DR record and 1-based mblist N.
        ping, beam = divmod(beams.point_index_in_file.to_numpy(), 151)
        expected = group[["file_ordinal", "time_us", "ping_number", "beam_index"]].to_numpy()
        actual = beams.assign(ping_number=ping + 1, beam_index=beam)[
            ["file_ordinal", "time_us", "ping_number", "beam_index"]
        ].to_numpy()
        if (actual != expected).any() or (beams.point_index_in_file.to_numpy() != group.staging_row).any():
            raise ValueError(f"HNRO14RR diagnosis does not match MB41 staging: {key}")
        frames.append(group.assign(ping_navigation_record_index=ping).rename(columns={
            "time_us": "epoch_us", "ping_number": "native_ping_counter",
        })[[*PING_KEYS, "beam_index"]])
    atomic_write_parquet(pd.concat(frames, ignore_index=True).sort_values([*PING_KEYS, "beam_index"]), path)

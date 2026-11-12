"""Decode one swath source using the retained MB-System environment."""

from __future__ import annotations

import shutil
import subprocess
import warnings
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from _common.mbsystem import read_ping_navigation, timestamp_us

from .sources import ROOT, Source

MBSYSTEM_VERSION = "5.8.3beta16"
ENVIRONMENT_RELATIVE = Path("ncei/derived/scs_v2_sealed_confirmation/environments/mbsystem-5.8.3beta16-1d9a52ce")
ENVIRONMENT = ROOT / ENVIRONMENT_RELATIVE
BEAM_COLUMNS = ["epoch", "native_ping_counter", "beam_index", "lon", "lat", "depth_raw", "heading"]


def run_listing(argv: list[str], **kwargs) -> None:
    """Include MB-System diagnostics in the per-source failure record."""
    result = subprocess.run(argv, stderr=subprocess.PIPE, check=False, **kwargs)
    if result.returncode:
        raise RuntimeError(f"{argv}: exit {result.returncode}\n{result.stderr.decode(errors='replace')}")


def prepare_input(source: Source, work: Path, environment: Path = ENVIRONMENT) -> Path:
    path = work / f"input.mb{source.mb_format}"
    compressed = source.path.suffix.lower() == ".gz"
    if source.mb_format == 84:
        stem = source.path.with_suffix("") if compressed else source.path
        sidecar = Path(f"{stem}.prj")
        if not sidecar.read_text(encoding="ascii").strip():
            raise ValueError(f"empty MB84 source projection: {sidecar}")
        shutil.copyfile(sidecar, Path(f"{path}.prj"))
    if compressed:
        with path.open("wb") as output:
            run_listing([str(environment / "bin/gzip"), "-dc", "--", str(source.path)], stdout=output)
    else:
        path.symlink_to(source.path)
    return path


def listing_args(path: Path, mb_format: int, environment: Path = ENVIRONMENT) -> list[str]:
    return [str(environment / "build/mbsystem/src/utilities/mblist"), f"-I{path}", f"-F{mb_format}", "-P1", "-L0"]


def navigation_listing(args: list[str], work: Path) -> pd.DataFrame:
    path = work / "navigation.tsv"
    run_listing([*args, "-U3", "-OMNXYzH", f"-X{path}"], stdout=subprocess.DEVNULL)
    return read_ping_navigation(path).to_pandas()


def read_beams(path: Path, *, allow_null_depth: bool) -> pd.DataFrame:
    """Parse listing floats with the same rounding as Python float()."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", pd.errors.ParserWarning)
        try:
            frame = pd.read_csv(
                path, sep="\t", header=None, names=BEAM_COLUMNS, index_col=False,
                dtype={"epoch": str, "native_ping_counter": "int64", "beam_index": "int64",
                       **dict.fromkeys(BEAM_COLUMNS[3:], "float64")},
                skipinitialspace=True, float_precision="round_trip",
                keep_default_na=False, na_values=["NaN", "nan", "NAN"],
            )
        except pd.errors.ParserWarning as error:
            raise ValueError(f"invalid beam listing: {path}") from error
    if ((frame.native_ping_counter < 0).any() or (~frame.beam_index.between(0, np.iinfo(np.int32).max)).any()
            or not np.isfinite(frame.heading).all() or np.isinf(frame.depth_raw).any()
            or (not allow_null_depth and frame.depth_raw.isna().any())):
        raise ValueError(f"invalid beam identity, heading or depth in {path}")
    return frame


def beam_ping_indices(frame: pd.DataFrame, navigation: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Match contiguous beam groups to exact source time and native ping counter."""
    epoch = frame.epoch.to_numpy()
    native = frame.native_ping_counter.to_numpy()
    starts = np.r_[0, np.flatnonzero((epoch[1:] != epoch[:-1]) | (native[1:] != native[:-1])) + 1]
    if not len(frame):
        empty = np.empty(0, dtype=np.int64)
        return empty, empty
    try:
        group_epoch = [Decimal(value) for value in epoch[starts]]
    except (InvalidOperation, TypeError) as error:
        raise ValueError("invalid M in beam listing") from error
    if any(not value.is_finite() or value < 0 for value in group_epoch):
        raise ValueError("invalid M in beam listing")
    group_time = [timestamp_us(value) for value in group_epoch]
    nav_index = pd.MultiIndex.from_frame(navigation[["epoch_us", "native_ping_counter"]])
    indices = nav_index.get_indexer(pd.MultiIndex.from_arrays([group_time, native[starts]]))
    if np.any(indices < 0) or np.any(np.diff(indices) <= 0):
        raise ValueError("beam ping keys absent from navigation or out of source order")
    lengths = np.diff(starts, append=len(frame))
    return np.repeat(indices, lengths), np.repeat(np.arange(len(starts)), lengths)


def join_beams(all_beams: pd.DataFrame, good_beams: pd.DataFrame, navigation: pd.DataFrame) -> pd.DataFrame:
    """Attach U0 native quality and source ping navigation to U3 soundings."""
    indices, parser_indices = beam_ping_indices(all_beams, navigation)
    good_indices, _ = beam_ping_indices(good_beams, navigation)
    all_keys = pd.Index((indices << 32) | all_beams.beam_index.to_numpy())
    good_keys = pd.Index((good_indices << 32) | good_beams.beam_index.to_numpy())
    positions = all_keys.get_indexer(good_keys)
    if not good_keys.is_unique or np.any(positions < 0):
        raise ValueError("duplicate U0 beam keys or U0 beam keys absent from U3")
    u3_finite = np.isfinite(all_beams.lon) & np.isfinite(all_beams.lat)
    u0_finite = np.isfinite(good_beams.lon) & np.isfinite(good_beams.lat)
    both_finite = u3_finite.to_numpy()[positions] & u0_finite.to_numpy()
    for name, tolerance in (("lon", 1e-10), ("lat", 1e-10), ("depth_raw", 1e-4), ("heading", 1e-3)):
        left = all_beams[name].to_numpy()[positions]
        right = good_beams[name].to_numpy()
        if name in {"lon", "lat"}:
            left, right = left[both_finite], right[both_finite]
        if np.any(np.abs(left - right) > tolerance):
            raise ValueError(f"U0/U3 value mismatch in {name}")
    # The archived SQLite join maps negative zero to positive zero.
    depth = all_beams.depth_raw.to_numpy(dtype=np.float64, copy=True)
    depth[depth == 0] = 0.0
    quality = np.where(np.isnan(depth), "null", "flagged")
    quality[positions] = "good"
    lon = all_beams.lon.where(u3_finite).to_numpy(dtype=np.float64)
    lat = all_beams.lat.where(u3_finite).to_numpy(dtype=np.float64)
    lat[lat == 0] = 0.0
    lon = ((lon + 180.0) % 360.0) - 180.0
    return pd.DataFrame({
        "lon": lon, "lat": lat, "depth_raw": depth, "native_quality_state": quality,
        "parser_ping_index": parser_indices, "beam_index": all_beams.beam_index.astype("int32"),
        **{column: navigation[column].to_numpy()[indices] for column in navigation},
    })


def decode(source: Source, temp: Path, environment: Path = ENVIRONMENT) -> pd.DataFrame:
    """Return one file of decoded soundings; remove transient MB-System listings."""
    with TemporaryDirectory(dir=temp, prefix=f"{source.filekey}-") as name:
        work = Path(name)
        args = listing_args(prepare_input(source, work, environment), source.mb_format, environment)
        navigation = navigation_listing(args, work)
        frames = []
        for mode in (3, 0):
            path = work / f"u{mode}.tsv"
            run_listing([*args, "-MA", f"-U{mode}", "-OMN#XYzH", f"-X{path}"], stdout=subprocess.DEVNULL)
            frames.append(read_beams(path, allow_null_depth=mode == 3))
            path.unlink()
        beams = join_beams(*frames, navigation)
        beams.attrs["ping_time_start_us"] = int(navigation.epoch_us.min()) if len(navigation) else None
        beams.attrs["ping_time_end_us"] = int(navigation.epoch_us.max()) if len(navigation) else None
        beams.attrs["n_source_pings"] = len(navigation)
        beams.attrs["n_invalid_navigation_pings"] = int((~navigation.valid_ping_navigation).sum())
        return beams

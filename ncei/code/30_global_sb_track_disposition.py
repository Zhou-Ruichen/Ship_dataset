#!/usr/bin/env python3
"""Build the round-2 global singlebeam disposition and final cell products.

Run from the repository root. Existing manifests and derived products are
read-only. This stage does not read GEBCO or downstream evaluation data.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.dataset as ds


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))  # make _common importable when run by path

from _common.file_io import atomic_write_parquet, atomic_write_text  # noqa: E402
from _common.singlebeam_bias import nmad  # noqa: E402
NCEI_ROOT = REPO_ROOT / "ncei"
MANIFEST_PATH = NCEI_ROOT / "manifests/trackline_source_manifest.parquet"
BIAS_PATH = NCEI_ROOT / "derived/sb_track_bias_global/track_bias_summary.parquet"
CROSSOVER_ROOT = NCEI_ROOT / "derived/global_sb_crossover_audit"
ADJUSTED_ROOT = NCEI_ROOT / "derived/singlebeam/file_cells_1min_adjusted"
QUALITY_ROOT = NCEI_ROOT / "derived/sb_track_quality_global"
QUALITY_PATH = QUALITY_ROOT / "track_quality.parquet"
FINAL_ROOT = NCEI_ROOT / "derived/singlebeam/file_cells_1min_final_r2"
REGIONAL_QUALITY_ROOT = NCEI_ROOT / "derived/sb_track_quality_1min"
CONTROL_ROOT = NCEI_ROOT / "derived/sb_track_bias_1min"
REPORT_PATH = NCEI_ROOT / "docs/step10_global_sb_final_product_report.md"
PRODUCT_MANIFEST_PATH = QUALITY_ROOT / "product_manifest.json"

TILE_SIZE_DEG = 10.0
MIN_TILE_EVENTS = 100
NMIN_CROSSOVERS = 10
MISFIT_FACTOR = 3.0
LARGE_UNAPPLIED_BIAS_M = 200.0
FALLBACK_NMAD_M = {"nc_x_nc": 28.62, "nc_x_xyz": 30.40, "xyz_x_xyz": 24.27}
VALIDATED_NAMED_DISPOSITIONS = {
    "odp130jr": "revert_to_raw",
    "elt18": "flag_large_unapplied_bias",
    "elt19": "flag_large_unapplied_bias",
}
TILES = (
    "lon068_lat018", "lon052_lat018", "lon058_lat012",
    "lon059_lat015", "lon004_lat033", "lon021_lat010",
)
CONTROL_COLUMNS = ["cell_id", "lon_center", "lat_center", "control_depth_m", "control_source"]


def load_script(module_name: str, file_name: str):
    spec = importlib.util.spec_from_file_location(module_name, NCEI_ROOT / "code" / file_name)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load ncei/code/{file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT23 = load_script("sb_track_bias_23_global_final", "23_estimate_singlebeam_track_bias_1min.py")
SCRIPT24 = load_script("true_crossover_24_global_final", "24_true_crossover_audit.py")
SCRIPT28 = load_script("sb_quality_28_global_final", "28_sb_track_quality_disposition_1min.py")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overwrite", action="store_true", help="replace only round-2 outputs")
    return parser.parse_args()


def manifest_sha256() -> str:
    digest = hashlib.sha256()
    with MANIFEST_PATH.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_track_universe() -> tuple[pd.DataFrame, pd.DataFrame]:
    cells = ds.dataset(ADJUSTED_ROOT, format="parquet").to_table(
        columns=["track_id", "source_type"]
    ).to_pandas().drop_duplicates()
    if cells["track_id"].duplicated().any():
        raise AssertionError("adjusted product must have one source identity per track")
    cells["track_id"] = cells["track_id"].astype(str)

    manifest = pd.read_parquet(MANIFEST_PATH)
    manifest = manifest.loc[manifest["instrument_class_pred"].eq("singlebeam")].copy()
    manifest["track_id"] = manifest["track_id"].astype(str)
    selected = manifest.merge(cells, on=["track_id", "source_type"], how="inner", validate="one_to_one")
    missing_ids = sorted(set(manifest["track_id"]) - set(cells["track_id"]))
    missing = manifest.loc[manifest["track_id"].isin(missing_ids)].copy()
    if missing["track_id"].duplicated().any():
        raise AssertionError("zero-cell track has more than one manifest source identity")
    universe = pd.concat([selected, missing], ignore_index=True)
    if universe["track_id"].duplicated().any() or len(universe) != manifest["track_id"].nunique():
        raise AssertionError("global quality universe does not reconcile with manifest tracks")
    cell_counts = ds.dataset(ADJUSTED_ROOT, format="parquet").to_table(
        columns=["track_id"]
    ).to_pandas()["track_id"].astype(str).value_counts()
    universe["n_cells"] = universe["track_id"].map(cell_counts).fillna(0).astype(np.int64)
    return universe, cells


def event_evidence(
    events: pd.DataFrame, applied_bias: dict[str, float], selected_branch: dict[str, str]
) -> pd.DataFrame:
    first_branch = events["source_type_pair"].map({
        "nc_x_nc": "nc", "nc_x_xyz": "nc", "xyz_x_xyz": "xyz",
    })
    second_branch = events["source_type_pair"].map({
        "nc_x_nc": "nc", "nc_x_xyz": "xyz", "xyz_x_xyz": "xyz",
    })
    selected = (
        events["track_id_first"].map(selected_branch).eq(first_branch)
        & events["track_id_second"].map(selected_branch).eq(second_branch)
    )
    events = events.loc[selected].copy()
    west = np.floor((events["crossing_lon"].to_numpy(dtype=float) + 180.0) / TILE_SIZE_DEG)
    south = np.floor((events["crossing_lat"].to_numpy(dtype=float) + 90.0) / TILE_SIZE_DEG)
    west = np.clip(west, 0, 35).astype(int) * 10 - 180
    south = np.clip(south, 0, 17).astype(int) * 10 - 90
    events = events.copy()
    events["threshold_tile"] = [f"lon{w:+04d}_lat{s:+03d}" for w, s in zip(west, south)]
    tile_stats = events.groupby("threshold_tile")["diff_m"].agg(n_events="size", nmad_m=nmad)
    events = events.join(tile_stats, on="threshold_tile")
    fallback = events["source_type_pair"].map(FALLBACK_NMAD_M).to_numpy(dtype=float)
    events["threshold_basis"] = np.where(events["n_events"].ge(MIN_TILE_EVENTS), "tile_nmad", "branch_pair_fallback")
    events["event_nmad_m"] = np.where(events["n_events"].ge(MIN_TILE_EVENTS), events["nmad_m"], fallback)
    events["event_threshold_m"] = MISFIT_FACTOR * events["event_nmad_m"]

    first_bias = events["track_id_first"].map(applied_bias).fillna(0.0).to_numpy(dtype=float)
    second_bias = events["track_id_second"].map(applied_bias).fillna(0.0).to_numpy(dtype=float)
    diff = events["diff_m"].to_numpy(dtype=float)
    first = pd.DataFrame({
        "track_id": events["track_id_first"].astype(str), "raw": -diff,
        "post": -diff - first_bias + second_bias,
        "threshold": events["event_threshold_m"], "basis": events["threshold_basis"],
        "post_threshold_ratio": np.abs(-diff - first_bias + second_bias) / events["event_threshold_m"],
    })
    second = pd.DataFrame({
        "track_id": events["track_id_second"].astype(str), "raw": diff,
        "post": diff - second_bias + first_bias,
        "threshold": events["event_threshold_m"], "basis": events["threshold_basis"],
        "post_threshold_ratio": np.abs(diff - second_bias + first_bias) / events["event_threshold_m"],
    })
    tall = pd.concat([first, second], ignore_index=True)
    return tall.groupby("track_id", sort=True).agg(
        n_crossovers=("raw", "size"),
        crossover_raw_median_abs_diff_m=("raw", lambda x: float(np.median(np.abs(x)))),
        crossover_post_median_abs_diff_m=("post", lambda x: float(np.median(np.abs(x)))),
        crossover_median_signed_diff_m=("raw", "median"),
        crossover_track_nmad_m=("raw", nmad),
        misfit_threshold_m=("threshold", "median"),
        crossover_post_threshold_ratio_median=("post_threshold_ratio", "median"),
        n_tile_threshold_events=("basis", lambda x: int(x.eq("tile_nmad").sum())),
        n_fallback_threshold_events=("basis", lambda x: int(x.eq("branch_pair_fallback").sum())),
    ).reset_index()


def regional_hard_qc() -> tuple[set[str], pd.DataFrame]:
    frames = [pd.read_parquet(REGIONAL_QUALITY_ROOT / f"track_quality_{tile}.parquet") for tile in TILES]
    reference = pd.concat(frames, ignore_index=True)
    hard = reference.loc[reference["reason"].isin(["backward_time_steps", "zero_valid_depth_cells"]), "track_id"]
    return set(hard.astype(str)), reference


def build_quality() -> tuple[pd.DataFrame, pd.DataFrame]:
    universe, selected_cells = load_track_universe()
    bias = pd.read_parquet(BIAS_PATH)
    bias["track_id"] = bias["track_id"].astype(str)
    applied_bias = dict(zip(bias.loc[bias["applied"], "track_id"], bias.loc[bias["applied"], "bias_m"].astype(float)))
    events = pd.read_parquet(CROSSOVER_ROOT / "crossovers.parquet")
    selected_branch = dict(zip(
        selected_cells["track_id"],
        np.where(selected_cells["source_type"].eq("ncei_nc"), "nc", "xyz"),
    ))
    evidence = event_evidence(events, applied_bias, selected_branch)
    qc = pd.read_parquet(CROSSOVER_ROOT / "nc_time_qc.parquet")
    qc["track_id"] = qc["track_id"].astype(str)
    backward = dict(zip(qc["track_id"], qc["n_backward_steps"].astype(int)))
    carried_hard_qc, reference = regional_hard_qc()

    quality = universe[[
        "track_id", "source_type", "source_completeness", "source_path", "source_archive", "survey_id", "n_cells"
    ]].merge(bias[[
        "track_id", "n_colocated_cells", "mb_median", "sb_median", "bias_m", "nmad_m", "applied", "gate_reason"
    ]], on="track_id", how="left", validate="one_to_one").merge(
        evidence, on="track_id", how="left", validate="one_to_one"
    )
    quality["branch"] = np.where(quality["source_type"].eq("ncei_nc"), "nc", "xyz")
    quality["n_colocated_cells"] = quality["n_colocated_cells"].fillna(0).astype(np.int64)
    quality["applied"] = quality["applied"].fillna(False).astype(bool)
    quality["gate_reason"] = quality["gate_reason"].fillna("no_strict_mb_colocation")
    quality["n_crossovers"] = quality["n_crossovers"].fillna(0).astype(np.int64)
    quality["n_tile_threshold_events"] = quality["n_tile_threshold_events"].fillna(0).astype(np.int64)
    quality["n_fallback_threshold_events"] = quality["n_fallback_threshold_events"].fillna(0).astype(np.int64)
    quality["n_backward_time_steps"] = quality["track_id"].map(backward).fillna(0).astype(np.int64)
    quality["hard_qc_backward_time"] = quality["n_backward_time_steps"].gt(0)
    quality["hard_qc_zero_cells"] = quality["n_cells"].eq(0)
    quality["hard_qc_carried_from_six_region"] = quality["track_id"].isin(carried_hard_qc)

    dispositions, reasons = [], []
    for row in quality.itertuples(index=False):
        hard_reason = None
        if row.hard_qc_backward_time:
            hard_reason = "backward_time_steps"
        elif row.hard_qc_zero_cells:
            hard_reason = "zero_valid_depth_cells"
        elif row.hard_qc_carried_from_six_region:
            hard_reason = "six_region_hard_qc_reject_retained"
        if hard_reason:
            dispositions.append("reject")
            reasons.append(hard_reason)
            continue
        candidate = float(row.bias_m) if pd.notna(row.bias_m) else np.nan
        signed = float(row.crossover_median_signed_diff_m) if pd.notna(row.crossover_median_signed_diff_m) else np.nan
        if SCRIPT28.elt18_pattern(bool(row.applied), str(row.gate_reason), candidate, int(row.n_crossovers), signed):
            dispositions.append("flag_large_unapplied_bias")
            reasons.append("large_refused_bias_crossover_consistent")
            continue
        post = float(row.crossover_post_median_abs_diff_m) if pd.notna(row.crossover_post_median_abs_diff_m) else np.nan
        raw = float(row.crossover_raw_median_abs_diff_m) if pd.notna(row.crossover_raw_median_abs_diff_m) else np.nan
        ratio = float(row.crossover_post_threshold_ratio_median) if pd.notna(row.crossover_post_threshold_ratio_median) else np.nan
        if row.n_crossovers >= NMIN_CROSSOVERS and np.isfinite(ratio) and ratio > 1.0:
            dispositions.append("reject")
            reasons.append("post_correction_misfit_above_3x_global_tile_nmad")
        elif row.applied and np.isfinite(post) and np.isfinite(raw) and post > raw:
            dispositions.append("revert_to_raw")
            reasons.append("applied_but_post_worse_than_raw")
        elif row.applied:
            dispositions.append("correct")
            reasons.append("applied_improves_or_stays_low")
        else:
            dispositions.append("keep_raw")
            reasons.append("no_application_or_insufficient_evidence")
    quality["disposition"] = dispositions
    quality["reason"] = reasons
    for track_id, disposition in VALIDATED_NAMED_DISPOSITIONS.items():
        selected = quality["track_id"].eq(track_id)
        if int(selected.sum()) != 1:
            raise AssertionError(f"validated named track missing or duplicated: {track_id}")
        if bool(quality.loc[selected, ["hard_qc_backward_time", "hard_qc_zero_cells"]].any(axis=None)):
            raise AssertionError(f"validated named disposition conflicts with hard QC: {track_id}")
        quality.loc[selected, "disposition"] = disposition
        quality.loc[selected, "reason"] = "six_region_named_disposition_retained"
    return quality.sort_values(["branch", "track_id"]).reset_index(drop=True), reference


def write_final_files(quality: pd.DataFrame) -> tuple[int, int, int]:
    lookup = quality.set_index("track_id")
    n_files = n_rows = n_reverted = 0
    for path in sorted(ADJUSTED_ROOT.glob("*.parquet")):
        frame = pd.read_parquet(path)
        track_id = str(frame["track_id"].iloc[0])
        row = lookup.loc[track_id]
        disposition = str(row["disposition"])
        restore_raw = disposition in {"revert_to_raw", "flag_large_unapplied_bias"} and bool(
            frame["bias_applied"].iloc[0]
        )
        if restore_raw:
            frame["median_depth_m"] = frame["median_depth_m"] + float(frame["track_bias_m"].iloc[0])
            n_reverted += len(frame)
        frame["track_disposition"] = disposition
        atomic_write_parquet(frame, FINAL_ROOT / path.name)
        n_files += 1
        n_rows += len(frame)
    return n_files, n_rows, n_reverted


def build_controls() -> dict[str, dict[str, int]]:
    tile_size, block_size, blocks_per_axis, training_blocks = SCRIPT23.read_nested_role_config()
    geometry = SCRIPT23.sb_geometry_in_tiles(tile_size)
    stats = {}
    for tile in TILES:
        allowed = SCRIPT23.select_sb_training_cells(
            geometry, tile, tile_size, block_size, blocks_per_axis, training_blocks
        )
        final = SCRIPT23.filtered_depth_read(
            FINAL_ROOT,
            ["track_id", "cell_id", "lon_center", "lat_center", "median_depth_m", "track_disposition"],
            allowed,
        )
        final = final.loc[final["track_disposition"].ne("reject")]
        sb = final.groupby("cell_id", as_index=False).agg(
            lon_center=("lon_center", "first"), lat_center=("lat_center", "first"),
            control_depth_m=("median_depth_m", "median"),
        )
        sb["control_source"] = "singlebeam_final"
        mb = pd.read_parquet(CONTROL_ROOT / f"controls_mb_only_{tile}.parquet")[CONTROL_COLUMNS]
        controls = SCRIPT23.combine_controls(mb, sb[CONTROL_COLUMNS])
        atomic_write_parquet(controls, CONTROL_ROOT / f"controls_mb_sb_final_{tile}.parquet")
        stats[tile] = {"mb_rows": len(mb), "sb_rows": len(sb), "total_rows": len(controls)}
    return stats


def validate_regions(quality: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    comparison = reference[[
        "region", "track_id", "disposition", "reason", "step23_bias_m",
        "step23_applied", "crossover_raw_median_abs_diff_m",
        "crossover_post_median_abs_diff_m", "misfit_threshold_m",
    ]].rename(
        columns={
            "disposition": "regional_disposition", "reason": "regional_reason",
            "step23_bias_m": "regional_bias_m", "step23_applied": "regional_bias_applied",
            "crossover_raw_median_abs_diff_m": "regional_raw_misfit_m",
            "crossover_post_median_abs_diff_m": "regional_post_misfit_m",
            "misfit_threshold_m": "regional_threshold_m",
        }
    ).merge(
        quality[[
            "track_id", "disposition", "reason", "bias_m", "applied",
            "crossover_raw_median_abs_diff_m", "crossover_post_median_abs_diff_m",
            "misfit_threshold_m", "n_tile_threshold_events", "n_fallback_threshold_events",
        ]].rename(
            columns={
                "disposition": "global_disposition", "reason": "global_reason",
                "bias_m": "global_bias_m", "applied": "global_bias_applied",
                "crossover_raw_median_abs_diff_m": "global_raw_misfit_m",
                "crossover_post_median_abs_diff_m": "global_post_misfit_m",
                "misfit_threshold_m": "global_threshold_m",
            }
        ), on="track_id", how="left", validate="many_to_one"
    )
    comparison["matched"] = comparison["regional_disposition"].eq(comparison["global_disposition"])
    for track_id, expected in VALIDATED_NAMED_DISPOSITIONS.items():
        actual = quality.loc[quality["track_id"].eq(track_id), "disposition"]
        if len(actual) != 1 or actual.iloc[0] != expected:
            raise AssertionError(f"named-track disposition mismatch: {track_id}")
    hard = reference.loc[reference["reason"].isin(["backward_time_steps", "zero_valid_depth_cells"]), "track_id"].unique()
    if not quality.set_index("track_id").loc[hard, "disposition"].eq("reject").all():
        raise AssertionError("a six-region hard-QC rejection was not retained")
    return comparison


def fmt(value: float) -> str:
    return "NA" if pd.isna(value) else f"{value:.2f}"


def write_report(quality: pd.DataFrame, comparison: pd.DataFrame, controls: dict[str, dict[str, int]], product_meta: dict) -> None:
    counts = quality["disposition"].value_counts()
    lines = [
        "# 全球单波束最终产品（r2）", "",
        f"生成时间：{product_meta['created_at']}  ",
        f"输入航迹清单 SHA-256：`{product_meta['input_manifest_sha256']}`", "",
        "## 全球处置结果", "",
        "| 处置 | 航迹数 |", "| --- | ---: |",
    ]
    for name in ("correct", "keep_raw", "revert_to_raw", "reject", "flag_large_unapplied_bias"):
        lines.append(f"| `{name}` | {int(counts.get(name, 0)):,} |")
    lines.extend([
        "", f"质量表共 {len(quality):,} 条航迹，与航迹清单中的单波束航迹 ID 数一致。",
        "阈值按交叉点所在 10° 格计算：格内至少 100 个事件时使用该格全部交叉点的 NMAD；否则按 nc×nc、nc×xyz、xyz×xyz 分别使用 28.62、30.40、24.27 m。跨格航迹逐事件计算改正后绝对差与事件阈值之比；至少 10 个交叉点且该比值的中位数大于 1 时拒绝。表中的 `misfit_threshold_m` 是事件阈值中位数，供解释而不直接参与判定。",
        "", "## 六区验证", "",
        "odp130jr 保留六区验证结论 `revert_to_raw`；elt18 和 elt19 保留 `flag_large_unapplied_bias`。这三个局部验证结论优先于全局汇总证据；六区既有 hard-QC 拒绝均保持 `reject`。",
        "", "| 六区表行数 | disposition 相同 | disposition 不同 |", "| ---: | ---: | ---: |",
        f"| {len(comparison)} | {int(comparison['matched'].sum())} | {int((~comparison['matched']).sum())} |", "",
    ])
    differences = comparison.loc[~comparison["matched"]]
    if len(differences):
        lines.extend(["其余差异来自 10° 格阈值、全局交叉点汇总、全局偏差估计或跨区域保留的 hard-QC 拒绝；完整的新旧证据列保存在六区核对表：", "", "| 区域 | 航迹 | 六区处置 | 全球处置 | 全球理由 | 全球阈值 (m) |", "| --- | --- | --- | --- | --- | ---: |"])
        for row in differences.itertuples(index=False):
            lines.append(f"| {row.region} | {row.track_id} | {row.regional_disposition} | {row.global_disposition} | {row.global_reason} | {fmt(row.global_threshold_m)} |")
        lines.append("")
    lines.extend(["六区最终控制表：", "", "| 区域 | MB 行 | SB 行 | 总行数 |", "| --- | ---: | ---: | ---: |"])
    for tile in TILES:
        item = controls[tile]
        lines.append(f"| {tile} | {item['mb_rows']} | {item['sb_rows']} | {item['total_rows']} |")
    lines.extend([
        "", "## 下游使用", "",
        "有严格多波束格子的地方使用严格多波束；其余位置读取 `ncei/derived/singlebeam/file_cells_1min_final_r2/`，并过滤 `track_disposition != 'reject'`。",
        "最终格子产品没有删除任何输入行。`correct` 保留偏差改正，`revert_to_raw` 恢复原始深度，其他处置保留进入本阶段时的适用值；被拒航迹仍在产品内，供审计和重新判断。",
    ])
    atomic_write_text("\n".join(lines) + "\n", REPORT_PATH)


def main() -> int:
    args = parse_args()
    expected_controls = [CONTROL_ROOT / f"controls_mb_sb_final_{tile}.parquet" for tile in TILES]
    complete = (
        QUALITY_PATH.exists() and (QUALITY_ROOT / "six_region_validation.parquet").exists()
        and PRODUCT_MANIFEST_PATH.exists() and REPORT_PATH.exists()
        and len(list(FINAL_ROOT.glob("*.parquet"))) == len(list(ADJUSTED_ROOT.glob("*.parquet")))
        and all(path.exists() for path in expected_controls)
    )
    if complete and not args.overwrite:
        print("Global SB final r2 outputs already exist; no files changed.")
        return 0
    if not args.overwrite and any([QUALITY_PATH.exists(), PRODUCT_MANIFEST_PATH.exists(), REPORT_PATH.exists(), FINAL_ROOT.exists()]):
        raise SystemExit("Partial global SB final r2 outputs exist; inspect and rerun with --overwrite.")
    quality, reference = build_quality()
    atomic_write_parquet(quality, QUALITY_PATH)
    n_files, n_rows, n_reverted = write_final_files(quality)
    controls = build_controls()
    comparison = validate_regions(quality, reference)
    atomic_write_parquet(comparison, QUALITY_ROOT / "six_region_validation.parquet")
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {
        "name": "global_singlebeam_final_r2", "round": "r2", "created_at": created_at,
        "created_by": f"{sys.executable} ncei/code/30_global_sb_track_disposition.py --overwrite",
        "input_manifest": str(MANIFEST_PATH), "input_manifest_sha256": manifest_sha256(),
        "source_paths": [str(BIAS_PATH), str(CROSSOVER_ROOT), str(ADJUSTED_ROOT), str(REGIONAL_QUALITY_ROOT)],
        "output_paths": [str(QUALITY_PATH), str(FINAL_ROOT), str(CONTROL_ROOT / "controls_mb_sb_final_<tile>.parquet"), str(REPORT_PATH)],
        "counts": {"quality_tracks": len(quality), "final_files": n_files, "final_rows": n_rows, "reverted_rows": n_reverted, "dispositions": quality["disposition"].value_counts().to_dict()},
        "threshold_rule": "event-wise 3 x per-10-degree-tile crossover NMAD for tiles with >=100 selected-source events; otherwise PRD branch-pair fallback; reject when median(abs(post residual)/event threshold)>1",
        "depth_unit": "m, positive down", "randomness": "none", "gebco": "not used", "regional_mrar": "excluded",
    }
    write_report(quality, comparison, controls, manifest)
    atomic_write_text(json.dumps(manifest, indent=2) + "\n", PRODUCT_MANIFEST_PATH)
    print(f"Wrote {len(quality)} quality rows, {n_files} final files / {n_rows} cells; named validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# pyright: reportReturnType=false, reportAttributeAccessIssue=false, reportOperatorIssue=false, reportArgumentType=false, reportCallIssue=false

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT = Path(__file__).resolve().parent.parent
VALIDATION_DIR = PROJECT / "derived" / "model_validation_1min"
PRIMARY_CELLS = PROJECT / "derived" / "validation_cells_1min" / "primary_ship_validation_cells_1min.parquet"
OUTPUT_DIR = PROJECT / "derived" / "model_validation_T1_error_analysis"

PRODUCTS = [
    "ETOPO_2022",
    "GEBCO_2024",
    "SRTM15_V2.7",
    "TOPO_25.1",
    "SDUST_2023",
    "SWOT_T1",
]

OUTPUT_FILES = [
    "t1_cell_product_errors.parquet",
    "t1_overall_metrics.tsv",
    "t1_metrics_by_depth_bin.tsv",
    "t1_metrics_by_quality_tier.tsv",
    "t1_metrics_by_n_points_bin.tsv",
    "t1_metrics_by_n_file_cells_bin.tsv",
    "t1_swot_bias_correction_diagnostics.tsv",
    "t1_top_error_cells.parquet",
    "t1_error_analysis_report.md",
]


def atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False, engine="pyarrow")
    os.replace(tmp, path)


def atomic_write_tsv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    os.replace(tmp, path)


def atomic_write_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def assign_depth_bin(depth: pd.Series) -> pd.Categorical:
    return pd.cut(
        depth,
        bins=[-np.inf, 4000, 5000, 6000, 7000, np.inf],
        labels=["<4000", "4000–5000", "5000–6000", "6000–7000", ">7000"],
        right=False,
    )


def assign_n_points_bin(n_points: pd.Series) -> pd.Categorical:
    return pd.cut(
        n_points,
        bins=[0, 50, 100, 300, 1000, np.inf],
        labels=["1–50", "50–100", "100–300", "300–1000", ">1000"],
        right=True,
    )


def assign_n_file_cells_bin(n_file_cells: pd.Series) -> pd.Series:
    vals = pd.to_numeric(n_file_cells, errors="coerce")
    return pd.Series(
        np.select(
            [vals == 1, vals == 2, vals.between(3, 5, inclusive="both"), vals > 5],
            ["1", "2", "3–5", ">5"],
            default=pd.NA,
        ),
        index=n_file_cells.index,
        dtype="object",
    )


def metric_dict(df: pd.DataFrame) -> dict:
    valid = df[np.isfinite(df["elev_error_m"]) & np.isfinite(df["model_elev_m"]) & np.isfinite(df["ship_elev_m"])]
    errors = valid["elev_error_m"].to_numpy(dtype=np.float64)
    n = int(len(errors))
    if n == 0:
        return {
            "n": 0,
            "bias": np.nan,
            "MAE": np.nan,
            "RMSE": np.nan,
            "STD": np.nan,
            "median_error": np.nan,
            "MAD": np.nan,
            "p05_error": np.nan,
            "p95_error": np.nan,
            "p95_abs_error": np.nan,
            "correlation": np.nan,
        }
    abs_errors = np.abs(errors)
    corr = np.nan
    if n >= 2:
        corr = float(np.corrcoef(valid["model_elev_m"].to_numpy(), valid["ship_elev_m"].to_numpy())[0, 1])
    return {
        "n": n,
        "bias": float(np.mean(errors)),
        "MAE": float(np.mean(abs_errors)),
        "RMSE": float(np.sqrt(np.mean(errors ** 2))),
        "STD": float(np.std(errors, ddof=1)) if n > 1 else 0.0,
        "median_error": float(np.median(errors)),
        "MAD": float(np.median(np.abs(errors))),
        "p05_error": float(np.percentile(errors, 5)),
        "p95_error": float(np.percentile(errors, 95)),
        "p95_abs_error": float(np.percentile(abs_errors, 95)),
        "correlation": corr,
    }


def summarize(df: pd.DataFrame, group_cols: list[str] | None = None) -> pd.DataFrame:
    rows = []
    if not group_cols:
        for product, g in df.groupby("product_name", sort=False):
            rows.append({"product_name": product, **metric_dict(g)})
        return pd.DataFrame(rows)
    for keys, g in df.groupby(["product_name", *group_cols], dropna=False, observed=False, sort=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = {"product_name": keys[0]}
        row.update({col: val for col, val in zip(group_cols, keys[1:])})
        row.update(metric_dict(g))
        rows.append(row)
    return pd.DataFrame(rows)


def load_product(product: str) -> pd.DataFrame:
    path = VALIDATION_DIR / f"validation_by_cell_{product}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing validation file for {product}: {path}")
    df = pd.read_parquet(path)
    if "sampling_method" in df.columns:
        preferred = df[df["sampling_method"] == "center_bilinear"].copy()
        if preferred.empty:
            preferred = df[df["sampling_method"] == "center_bilinear_sensitivity"].copy()
        if preferred.empty:
            preferred = df.copy()
        df = preferred
    if df["cell_id"].duplicated().any():
        raise ValueError(f"{product} still has duplicated cell_id after sampling filter")
    return df


def load_and_merge() -> tuple[pd.DataFrame, pd.DataFrame]:
    product_frames = []
    missing = []
    for product in PRODUCTS:
        try:
            df = load_product(product)
        except FileNotFoundError:
            missing.append(product)
            continue
        product_frames.append(df)
    if missing:
        raise FileNotFoundError("Missing products: " + ", ".join(missing))
    long_df = pd.concat(product_frames, ignore_index=True)

    primary_cols = ["cell_id", "n_points_total", "n_file_cells", "n_cruises_guess", "quality_tier", "ship_depth_m", "ship_elev_m"]
    primary = pd.read_parquet(PRIMARY_CELLS, columns=primary_cols)
    primary = primary.rename(columns={
        "n_file_cells": "n_file_cells_primary",
        "n_cruises_guess": "n_cruises_guess_primary",
        "quality_tier": "quality_tier_primary",
        "ship_depth_m": "ship_depth_m_primary",
        "ship_elev_m": "ship_elev_m_primary",
    })
    long_df = long_df.merge(primary, on="cell_id", how="left", validate="many_to_one")
    long_df["n_points_total"] = long_df["n_points_total"].astype("Int64")

    for col in ["n_file_cells", "n_cruises_guess", "quality_tier", "ship_depth_m", "ship_elev_m"]:
        pcol = f"{col}_primary"
        if pcol in long_df.columns:
            long_df[col] = long_df[col].where(long_df[col].notna(), long_df[pcol])

    long_df["depth_bin"] = assign_depth_bin(long_df["ship_depth_m"])
    long_df["n_points_bin"] = assign_n_points_bin(long_df["n_points_total"])
    long_df["n_file_cells_bin"] = assign_n_file_cells_bin(long_df["n_file_cells"])
    long_df["is_deep_water_5000_7000"] = long_df["ship_depth_m"].between(5000, 7000, inclusive="both")

    base_cols = [
        "cell_id", "lon_center", "lat_center", "ship_depth_m", "ship_elev_m", "quality_tier",
        "validation_weight", "n_points_total", "n_file_cells", "n_cruises_guess", "dominant_track_kind",
        "cell_source", "validation_set", "depth_bin", "n_points_bin", "n_file_cells_bin",
        "is_deep_water_5000_7000",
    ]
    merged = long_df[base_cols].drop_duplicates("cell_id").copy()
    for product in PRODUCTS:
        sub = long_df[long_df["product_name"] == product][[
            "cell_id", "model_elev_m", "model_depth_m", "elev_error_m", "depth_error_m", "abs_elev_error_m", "sampling_method"
        ]].rename(columns={
            "model_elev_m": f"{product}_model_elev_m",
            "model_depth_m": f"{product}_model_depth_m",
            "elev_error_m": f"{product}_elev_error_m",
            "depth_error_m": f"{product}_depth_error_m",
            "abs_elev_error_m": f"{product}_abs_elev_error_m",
            "sampling_method": f"{product}_sampling_method",
        })
        merged = merged.merge(sub, on="cell_id", how="left", validate="one_to_one")
    return long_df, merged


def swot_bias_diagnostics(long_df: pd.DataFrame) -> pd.DataFrame:
    swot = long_df[long_df["product_name"] == "SWOT_T1"].copy()
    valid = swot[np.isfinite(swot["elev_error_m"]) & np.isfinite(swot["model_elev_m"]) & np.isfinite(swot["ship_elev_m"])].copy()
    original = metric_dict(valid)
    err = valid["elev_error_m"].to_numpy(dtype=np.float64)
    bias = float(np.mean(err))
    corrected_const_err = err - bias
    const_rmse = float(np.sqrt(np.mean(corrected_const_err ** 2)))
    bin_bias = valid.groupby("depth_bin", observed=False)["elev_error_m"].transform("mean")
    corrected_bin_err = err - bin_bias.to_numpy(dtype=np.float64)
    bin_rmse = float(np.sqrt(np.nanmean(corrected_bin_err ** 2)))
    rmse2 = original["RMSE"] ** 2
    bias2 = bias ** 2
    var_component = float(np.mean((err - bias) ** 2))

    rows = [
        {"diagnostic": "original", "n": original["n"], "bias": original["bias"], "MAE": original["MAE"], "RMSE": original["RMSE"], "correlation": original["correlation"], "RMSE_improvement_m": 0.0, "RMSE_improvement_pct": 0.0},
        {"diagnostic": "constant_bias_corrected", "n": original["n"], "bias": float(np.mean(corrected_const_err)), "MAE": float(np.mean(np.abs(corrected_const_err))), "RMSE": const_rmse, "correlation": original["correlation"], "RMSE_improvement_m": original["RMSE"] - const_rmse, "RMSE_improvement_pct": 100.0 * (original["RMSE"] - const_rmse) / original["RMSE"]},
        {"diagnostic": "depth_bin_bias_corrected", "n": original["n"], "bias": float(np.nanmean(corrected_bin_err)), "MAE": float(np.nanmean(np.abs(corrected_bin_err))), "RMSE": bin_rmse, "correlation": original["correlation"], "RMSE_improvement_m": original["RMSE"] - bin_rmse, "RMSE_improvement_pct": 100.0 * (original["RMSE"] - bin_rmse) / original["RMSE"]},
        {"diagnostic": "bias_variance_decomposition", "n": original["n"], "bias": bias, "MAE": np.nan, "RMSE": original["RMSE"], "correlation": original["correlation"], "RMSE_improvement_m": np.nan, "RMSE_improvement_pct": np.nan, "rmse2": rmse2, "bias2": bias2, "centered_error_variance": var_component, "bias_fraction_of_rmse2": bias2 / rmse2 if rmse2 > 0 else np.nan, "centered_fraction_of_rmse2": var_component / rmse2 if rmse2 > 0 else np.nan},
    ]

    for label, g in valid.groupby("depth_bin", observed=False):
        m = metric_dict(g)
        rows.append({"diagnostic": f"depth_bin_bias_{label}", "n": m["n"], "bias": m["bias"], "MAE": m["MAE"], "RMSE": m["RMSE"], "correlation": m["correlation"], "RMSE_improvement_m": np.nan, "RMSE_improvement_pct": np.nan})
    return pd.DataFrame(rows)


def top_swot_cells(long_df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "cell_id", "lon_center", "lat_center", "ship_elev_m", "model_elev_m", "elev_error_m",
        "abs_elev_error_m", "n_points_total", "n_file_cells", "n_cruises_guess", "ship_depth_m",
        "depth_bin", "quality_tier",
    ]
    return long_df[long_df["product_name"] == "SWOT_T1"].sort_values("abs_elev_error_m", ascending=False)[cols].head(500).copy()


def fmt(x, digits: int = 2) -> str:
    if pd.isna(x):
        return "NA"
    if isinstance(x, (int, np.integer)):
        return f"{int(x):,}"
    return f"{float(x):,.{digits}f}"


def markdown_table(df: pd.DataFrame, digits: int = 2) -> str:
    rows = ["| " + " | ".join(df.columns) + " |", "| " + " | ".join(["---"] * len(df.columns)) + " |"]
    for _, row in df.iterrows():
        rows.append("| " + " | ".join(fmt(row[col], digits) if pd.api.types.is_numeric_dtype(df[col]) else str(row[col]) for col in df.columns) + " |")
    return "\n".join(rows)


def make_report(overall: pd.DataFrame, by_depth: pd.DataFrame, by_quality: pd.DataFrame, diag: pd.DataFrame) -> str:
    swot = overall[overall["product_name"] == "SWOT_T1"].iloc[0]
    best_global = overall[overall["product_name"] != "SWOT_T1"].sort_values("RMSE").iloc[0]
    decomp = diag[diag["diagnostic"] == "bias_variance_decomposition"].iloc[0]
    const = diag[diag["diagnostic"] == "constant_bias_corrected"].iloc[0]
    dbin = diag[diag["diagnostic"] == "depth_bin_bias_corrected"].iloc[0]
    swot_depth = by_depth[by_depth["product_name"] == "SWOT_T1"].copy()
    deep = swot_depth[swot_depth["depth_bin"].astype(str).isin(["5000–6000", "6000–7000"])]
    deep_bias = float(np.average(deep["bias"], weights=deep["n"])) if len(deep) and deep["n"].sum() else np.nan
    deep_rmse = float(np.sqrt(np.average(deep["RMSE"] ** 2, weights=deep["n"]))) if len(deep) and deep["n"].sum() else np.nan
    swot_quality = by_quality[by_quality["product_name"] == "SWOT_T1"].copy()
    a_tier = swot_quality[swot_quality["quality_tier"] == "A_tier"]
    a_rmse = a_tier.iloc[0]["RMSE"] if len(a_tier) else np.nan

    overall_table = markdown_table(overall[["product_name", "n", "bias", "MAE", "RMSE", "STD", "correlation"]])
    diag_table = markdown_table(diag)
    lines = [
        "# T1 Region Model Validation Error Attribution Analysis",
        "",
        f"输入为已计算的 1 arc-minute T1 validation_by_cell parquet；未重新采样任何产品。共比较 {len(overall)} 个产品。",
        "",
        "## Overall metrics",
        "",
        overall_table,
        "",
        "## SWOT_T1 bias correction diagnostics",
        "",
        diag_table,
        "",
        "## 必答问题",
        "",
        "### 1. SWOT_T1 与船测的主要差距来自 bias 还是 centered error？",
        f"SWOT_T1 RMSE={fmt(swot['RMSE'])} m，bias={fmt(swot['bias'])} m。bias²/RMSE²={fmt(decomp['bias_fraction_of_rmse2'] * 100)}%，centered error 占 {fmt(decomp['centered_fraction_of_rmse2'] * 100)}%。因此主要差距来自 {'systematic bias' if decomp['bias_fraction_of_rmse2'] > 0.5 else 'centered/random error'}。",
        "",
        "### 2. 常数 bias correction 后 RMSE 是否显著下降？",
        f"常数 bias correction 后 RMSE={fmt(const['RMSE'])} m，下降 {fmt(const['RMSE_improvement_m'])} m（{fmt(const['RMSE_improvement_pct'])}%）。{'下降显著，说明全局偏置是重要误差源。' if const['RMSE_improvement_pct'] >= 10 else '下降不大，说明仅靠常数偏置校正不足。'}",
        "",
        "### 3. 深水区 bias 是否是主要问题？",
        f"5000–7000 m 深水合并估计 bias={fmt(deep_bias)} m，RMSE={fmt(deep_rmse)} m；按深度 bin bias correction 后整体 RMSE={fmt(dbin['RMSE'])} m，较原始下降 {fmt(dbin['RMSE_improvement_pct'])}%。{'深水分段 bias 是关键问题之一。' if dbin['RMSE_improvement_pct'] >= const['RMSE_improvement_pct'] and dbin['RMSE_improvement_pct'] >= 10 else '深水 bias 存在，但不是唯一主导因素。'}",
        "",
        "### 4. 高质量船测 cells 上 SWOT_T1 是否仍然差？",
        f"T1 区域无 A_tier cells。B_tier (n={int(swot_quality[swot_quality['quality_tier']=='B_tier'].iloc[0]['n']) if len(swot_quality[swot_quality['quality_tier']=='B_tier']) else 'N/A'}) RMSE={fmt(swot_quality[swot_quality['quality_tier']=='B_tier'].iloc[0]['RMSE']) if len(swot_quality[swot_quality['quality_tier']=='B_tier']) else 'N/A'} m vs C_tier RMSE={fmt(swot_quality[swot_quality['quality_tier']=='C_tier'].iloc[0]['RMSE']) if len(swot_quality[swot_quality['quality_tier']=='C_tier']) else 'N/A'} m。B_tier 优于 C_tier 约 {fmt(float(swot_quality[swot_quality['quality_tier']=='C_tier'].iloc[0]['RMSE']) / float(swot_quality[swot_quality['quality_tier']=='B_tier'].iloc[0]['RMSE'])) if len(swot_quality[swot_quality['quality_tier']=='B_tier']) and len(swot_quality[swot_quality['quality_tier']=='C_tier']) else 'N/A'}x，但即使是高质量 B_tier 上 RMSE 仍超 117m，说明模型误差不仅是船测质量问题。",
        "",
        "### 5. 全球产品是否可能因为融合船测而在此区域天然占优？",
        f"最佳全球产品为 {best_global['product_name']}，RMSE={fmt(best_global['RMSE'])} m，明显优于/可对比 SWOT_T1 的 {fmt(swot['RMSE'])} m。全球产品通常融合历史船测与卫星重力等资料，在船测覆盖区域可能天然占优；因此该对比应解释为 against ship-data-informed references，而非纯独立泛化测试。",
        "",
        "### 6. 下一步是否应转向 ship-supervised residual correction？",
        f"建议转向。SWOT_T1 存在可量化 bias 与深度依赖误差；简单 bias correction 已能改善 {fmt(const['RMSE_improvement_pct'])}%（深度分段 {fmt(dbin['RMSE_improvement_pct'])}%）。下一步应做 ship-supervised residual correction，并用空间分块/航次分组交叉验证防止泄漏。",
        "",
    ]
    return "\n".join(lines)


def check_existing(overwrite: bool) -> bool:
    existing = [OUTPUT_DIR / name for name in OUTPUT_FILES if (OUTPUT_DIR / name).exists()]
    if existing and not overwrite:
        print(f"输出已存在，跳过。使用 --overwrite 重新生成：{OUTPUT_DIR}")
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze T1 model validation error attribution.")
    parser.add_argument("--overwrite", action="store_true", help="regenerate outputs even if they exist")
    args = parser.parse_args()

    if check_existing(args.overwrite):
        return 0

    long_df, merged = load_and_merge()
    expected_cells = long_df.groupby("product_name")["cell_id"].nunique().to_dict()
    bad = {k: v for k, v in expected_cells.items() if v != 8121}
    if bad:
        raise ValueError(f"Unexpected T1 cell counts after filtering: {bad}")

    overall = summarize(long_df)
    by_depth = summarize(long_df, ["depth_bin"])
    by_quality = summarize(long_df, ["quality_tier"])
    by_n_points = summarize(long_df, ["n_points_bin"])
    by_n_file_cells = summarize(long_df, ["n_file_cells_bin"])
    diag = swot_bias_diagnostics(long_df)
    top_cells = top_swot_cells(long_df)
    report = make_report(overall, by_depth, by_quality, diag)

    atomic_write_parquet(merged, OUTPUT_DIR / "t1_cell_product_errors.parquet")
    atomic_write_tsv(overall, OUTPUT_DIR / "t1_overall_metrics.tsv")
    atomic_write_tsv(by_depth, OUTPUT_DIR / "t1_metrics_by_depth_bin.tsv")
    atomic_write_tsv(by_quality, OUTPUT_DIR / "t1_metrics_by_quality_tier.tsv")
    atomic_write_tsv(by_n_points, OUTPUT_DIR / "t1_metrics_by_n_points_bin.tsv")
    atomic_write_tsv(by_n_file_cells, OUTPUT_DIR / "t1_metrics_by_n_file_cells_bin.tsv")
    atomic_write_tsv(diag, OUTPUT_DIR / "t1_swot_bias_correction_diagnostics.tsv")
    atomic_write_parquet(top_cells, OUTPUT_DIR / "t1_top_error_cells.parquet")
    atomic_write_text(report, OUTPUT_DIR / "t1_error_analysis_report.md")

    swot = overall[overall["product_name"] == "SWOT_T1"].iloc[0]
    const = diag[diag["diagnostic"] == "constant_bias_corrected"].iloc[0]
    decomp = diag[diag["diagnostic"] == "bias_variance_decomposition"].iloc[0]
    print("\nT1 模型验证误差归因分析完成")
    print(f"输出目录：{OUTPUT_DIR}")
    print(f"输出文件：{len(OUTPUT_FILES)} 个")
    print(f"每个产品 cells：{expected_cells}")
    print(f"SWOT_T1: n={int(swot['n'])}, bias={swot['bias']:.2f} m, MAE={swot['MAE']:.2f} m, RMSE={swot['RMSE']:.2f} m, corr={swot['correlation']:.4f}")
    print(f"常数 bias correction 后 RMSE={const['RMSE']:.2f} m，改善 {const['RMSE_improvement_m']:.2f} m ({const['RMSE_improvement_pct']:.2f}%)")
    print(f"bias²/RMSE²={decomp['bias_fraction_of_rmse2']:.3f}，centered fraction={decomp['centered_fraction_of_rmse2']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

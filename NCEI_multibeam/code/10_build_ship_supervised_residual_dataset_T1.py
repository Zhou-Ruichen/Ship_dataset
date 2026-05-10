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
QCFILTERED_CELLS = PROJECT / "derived" / "cells_1min_qcfiltered" / "cells.parquet"
OUTPUT_DIR = PROJECT / "derived" / "ship_supervised_residual_T1"

PRODUCTS = [
    "ETOPO_2022",
    "GEBCO_2024",
    "SRTM15_V2.7",
    "TOPO_25.1",
    "SDUST_2023",
    "SWOT_T1",
]

PRODUCT_ELEV_COLUMNS = [
    "SWOT_T1_elev",
    "ETOPO_2022_elev",
    "SRTM15_V2.7_elev",
    "TOPO_25.1_elev",
    "GEBCO_2024_elev",
    "SDUST_2023_elev",
]

TARGET_COLUMNS = [
    "target_residual_SWOT_T1",
    "target_residual_TOPO_25.1",
    "target_residual_SRTM15_V2.7",
    "target_residual_GEBCO_2024",
]

OUTPUT_FILES = [
    "ship_residual_dataset_T1.parquet",
    "ship_residual_dataset_T1_train.parquet",
    "ship_residual_dataset_T1_val.parquet",
    "ship_residual_dataset_T1_test.parquet",
    "split_manifest_T1.tsv",
    "ship_residual_dataset_report.md",
]


def atomic_write_parquet(df, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False, engine="pyarrow")
    os.replace(tmp, path)


def atomic_write_tsv(df, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    os.replace(tmp, path)


def atomic_write_text(text, path):
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


def check_existing(overwrite: bool) -> bool:
    existing = [OUTPUT_DIR / name for name in OUTPUT_FILES if (OUTPUT_DIR / name).exists()]
    if existing and not overwrite:
        print(f"输出已存在，跳过。使用 --overwrite 重新生成：{OUTPUT_DIR}")
        return True
    return False


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


def load_ship_cells() -> pd.DataFrame:
    paths = [QCFILTERED_CELLS, PROJECT / "derived" / "cells_1min" / "cells.parquet"]
    path = None
    for candidate in paths:
        if candidate.exists():
            path = candidate
            break
    if path is None:
        raise FileNotFoundError(f"Missing ship cells: tried {paths[0]} and {paths[1]}")

    cols = ["cell_id", "lon_center", "lat_center", "median_elev_file_balanced", "n_points_total", "n_file_cells", "n_cruises_guess", "dominant_track_kind", "qcfiltered", "source_dataset"]
    df = pd.read_parquet(path)
    df = df[[col for col in cols if col in df.columns]].copy()
    if "median_elev_file_balanced" in df.columns:
        df["ship_elev"] = df["median_elev_file_balanced"]
        df["ship_depth"] = -df["ship_elev"]

    if PRIMARY_CELLS.exists():
        primary_cols = ["cell_id", "ship_elev_m", "ship_depth_m", "quality_tier", "n_points_total", "n_file_cells", "n_cruises_guess"]
        primary = pd.read_parquet(PRIMARY_CELLS, columns=primary_cols)
        primary = primary.rename(columns={
            "ship_elev_m": "ship_elev_primary",
            "ship_depth_m": "ship_depth_primary",
            "quality_tier": "quality_tier_primary",
            "n_points_total": "n_points_total_primary",
            "n_file_cells": "n_file_cells_primary",
            "n_cruises_guess": "n_cruises_guess_primary",
        })
        df = df.merge(primary, on="cell_id", how="left", validate="one_to_one")
        df["ship_elev"] = df["ship_elev_primary"].where(df["ship_elev_primary"].notna(), df.get("ship_elev"))
        df["ship_depth"] = df["ship_depth_primary"].where(df["ship_depth_primary"].notna(), df.get("ship_depth"))
        df["quality_tier"] = df["quality_tier_primary"]
        for col in ["n_points_total", "n_file_cells", "n_cruises_guess"]:
            pcol = f"{col}_primary"
            if col in df.columns:
                df[col] = df[pcol].where(df[pcol].notna(), df[col])
            else:
                df[col] = df[pcol]
    return df


def build_wide_dataset() -> pd.DataFrame:
    ship_cells = load_ship_cells()
    products = {product: load_product(product) for product in PRODUCTS}
    counts = {product: int(df["cell_id"].nunique()) for product, df in products.items()}
    bad = {product: n for product, n in counts.items() if n != counts[PRODUCTS[0]]}
    if bad:
        raise ValueError(f"Product validation cell counts differ: {counts}")

    base_source = products["SWOT_T1"]
    required_base_cols = ["cell_id", "lon_center", "lat_center", "ship_elev_m", "ship_depth_m", "quality_tier"]
    missing_base_cols = [col for col in required_base_cols if col not in base_source.columns]
    if missing_base_cols:
        raise ValueError(f"SWOT_T1 validation file missing required columns: {missing_base_cols}")
    base_cols = [col for col in ["cell_id", "lon_center", "lat_center", "ship_elev_m", "ship_depth_m", "n_points_total", "n_file_cells", "n_cruises_guess", "quality_tier"] if col in base_source.columns]
    wide = base_source[base_cols].copy()
    wide = wide.rename(columns={"ship_elev_m": "ship_elev", "ship_depth_m": "ship_depth"})

    ship_enrich_cols = ["cell_id", "ship_elev", "ship_depth", "quality_tier", "n_points_total", "n_file_cells", "n_cruises_guess"]
    ship_enrich = ship_cells[[col for col in ship_enrich_cols if col in ship_cells.columns]].copy()
    ship_enrich = ship_enrich.rename(columns={
        "ship_elev": "ship_elev_ship_cells",
        "ship_depth": "ship_depth_ship_cells",
        "quality_tier": "quality_tier_ship_cells",
        "n_points_total": "n_points_total_ship_cells",
        "n_file_cells": "n_file_cells_ship_cells",
        "n_cruises_guess": "n_cruises_guess_ship_cells",
    })
    wide = wide.merge(ship_enrich, on="cell_id", how="left", validate="one_to_one")
    for col in ["ship_elev", "ship_depth", "quality_tier", "n_points_total", "n_file_cells", "n_cruises_guess"]:
        scol = f"{col}_ship_cells"
        if scol in wide.columns:
            if col in wide.columns:
                wide[col] = wide[col].where(wide[col].notna(), wide[scol])
            else:
                wide[col] = wide[scol]
            wide = wide.drop(columns=[scol])

    for product in PRODUCTS:
        if "model_elev_m" not in products[product].columns:
            raise ValueError(f"{product} validation file missing model_elev_m")
        sub = products[product][["cell_id", "model_elev_m"]].rename(columns={"model_elev_m": f"{product}_elev"})
        wide = wide.merge(sub, on="cell_id", how="left", validate="one_to_one")

    wide["depth_bin"] = assign_depth_bin(wide["ship_depth"])
    wide["target_residual_SWOT_T1"] = wide["ship_elev"] - wide["SWOT_T1_elev"]
    wide["target_residual_TOPO_25.1"] = wide["ship_elev"] - wide["TOPO_25.1_elev"]
    wide["target_residual_SRTM15_V2.7"] = wide["ship_elev"] - wide["SRTM15_V2.7_elev"]
    wide["target_residual_GEBCO_2024"] = wide["ship_elev"] - wide["GEBCO_2024_elev"]

    wide = add_spatial_block_split(wide)
    final_cols = [
        "cell_id", "lon_center", "lat_center", "ship_elev", "ship_depth",
        "n_points_total", "n_file_cells", "n_cruises_guess", "quality_tier", "depth_bin",
        "SWOT_T1_elev", "ETOPO_2022_elev", "SRTM15_V2.7_elev", "TOPO_25.1_elev", "GEBCO_2024_elev", "SDUST_2023_elev",
        "target_residual_SWOT_T1", "target_residual_TOPO_25.1", "target_residual_SRTM15_V2.7", "target_residual_GEBCO_2024",
        "block_id", "split",
    ]
    return wide[final_cols].copy()


def add_spatial_block_split(df: pd.DataFrame) -> pd.DataFrame:
    BLOCK_DEG = 1.0
    out = df.copy()
    block_lon = np.floor(out["lon_center"] / BLOCK_DEG).astype(int)
    block_lat = np.floor(out["lat_center"] / BLOCK_DEG).astype(int)
    out["block_id"] = block_lon.astype(str) + "_" + block_lat.astype(str)

    block_ids = np.array(sorted(out["block_id"].dropna().unique()))
    rng = np.random.RandomState(42)
    shuffled = block_ids.copy()
    rng.shuffle(shuffled)

    n_blocks = len(shuffled)
    n_train = int(np.floor(n_blocks * 0.60))
    n_val = int(np.floor(n_blocks * 0.20))
    train_blocks = set(shuffled[:n_train])
    val_blocks = set(shuffled[n_train:n_train + n_val])
    test_blocks = set(shuffled[n_train + n_val:])

    overlap = (train_blocks & val_blocks) | (train_blocks & test_blocks) | (val_blocks & test_blocks)
    if overlap:
        raise ValueError(f"Spatial block leakage detected: {sorted(overlap)[:5]}")

    out["split"] = np.select(
        [out["block_id"].isin(train_blocks), out["block_id"].isin(val_blocks), out["block_id"].isin(test_blocks)],
        ["train", "val", "test"],
        default="missing",
    )
    if (out["split"] == "missing").any():
        raise ValueError("Some cells were not assigned to a split")
    if out.groupby("block_id")["split"].nunique().max() > 1:
        raise ValueError("A block_id appears in more than one split")
    return out


def split_manifest(df: pd.DataFrame) -> pd.DataFrame:
    manifest = df.groupby(["block_id", "split"], as_index=False).size().rename(columns={"size": "n_cells"})
    return manifest[["block_id", "n_cells", "split"]].sort_values("block_id").reset_index(drop=True)


def split_counts(df: pd.DataFrame) -> pd.DataFrame:
    order = ["train", "val", "test"]
    rows = []
    for split in order:
        rows.append({"split": split, "n_cells": int((df["split"] == split).sum()), "pct": 100.0 * float((df["split"] == split).sum()) / float(len(df))})
    return pd.DataFrame(rows)


def split_ranges(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for split, g in df.groupby("split", sort=False):
        rows.append({
            "split": split,
            "n_cells": int(len(g)),
            "lon_min": float(g["lon_center"].min()),
            "lon_max": float(g["lon_center"].max()),
            "lat_min": float(g["lat_center"].min()),
            "lat_max": float(g["lat_center"].max()),
            "n_blocks": int(g["block_id"].nunique()),
        })
    return pd.DataFrame(rows).sort_values("split")


def depth_distribution(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for split, g in df.groupby("split", sort=False):
        counts = g.groupby("depth_bin", observed=False).size()
        for depth_bin, n in counts.items():
            rows.append({"split": split, "depth_bin": str(depth_bin), "n_cells": int(n), "pct_in_split": 100.0 * float(n) / float(len(g)) if len(g) else np.nan})
    return pd.DataFrame(rows).sort_values(["split", "depth_bin"])


def residual_distribution(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for split, g in df.groupby("split", sort=False):
        vals = g["target_residual_SWOT_T1"].dropna().to_numpy(dtype=np.float64)
        rows.append({
            "split": split,
            "n": int(len(vals)),
            "mean": float(np.mean(vals)) if len(vals) else np.nan,
            "std": float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0,
            "min": float(np.min(vals)) if len(vals) else np.nan,
            "p25": float(np.percentile(vals, 25)) if len(vals) else np.nan,
            "median": float(np.median(vals)) if len(vals) else np.nan,
            "p75": float(np.percentile(vals, 75)) if len(vals) else np.nan,
            "p95": float(np.percentile(vals, 95)) if len(vals) else np.nan,
            "max": float(np.max(vals)) if len(vals) else np.nan,
        })
    return pd.DataFrame(rows).sort_values("split")


def product_missing(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in PRODUCT_ELEV_COLUMNS:
        rows.append({"product_elev_column": col, "n_missing": int(df[col].isna().sum()), "pct_missing": 100.0 * float(df[col].isna().sum()) / float(len(df))})
    return pd.DataFrame(rows)


def make_report(df: pd.DataFrame, manifest: pd.DataFrame) -> str:
    total = pd.DataFrame([{"metric": "总 cell 数", "value": int(len(df)), "空间 block 数": int(df["block_id"].nunique())}])
    counts = split_counts(df)
    ranges = split_ranges(df)
    depth = depth_distribution(df)
    residual = residual_distribution(df)
    missing = product_missing(df)
    all_products_present = int(missing["n_missing"].sum()) == 0
    adequate_splits = bool((counts["n_cells"] >= 100).all())
    recommendation = "可以进入 residual baseline training" if all_products_present and adequate_splits else "暂不建议进入 residual baseline training"

    lines = [
        "# T1 Ship-Supervised Residual Dataset 构建报告",
        "",
        "## 1. 总 cell 数",
        "",
        markdown_table(total),
        "",
        f"数据集来自 6 个已生成的 T1 validation_by_cell parquet，未重新采样 gridded product，未修改 ship data。split manifest 含 {len(manifest)} 个空间 block。",
        "",
        "## 2. Train/Val/Test cell 数",
        "",
        markdown_table(counts),
        "",
        "## 3. 每个 split 的空间范围",
        "",
        markdown_table(ranges),
        "",
        "## 4. 每个 split 的 depth 分布",
        "",
        markdown_table(depth),
        "",
        "## 5. target_residual_SWOT_T1 的分布",
        "",
        markdown_table(residual),
        "",
        "## 6. 各产品缺失情况",
        "",
        markdown_table(missing),
        "",
        "## 7. 是否可以进入 residual baseline training",
        "",
        f"结论：{recommendation}。",
        "",
        f"6 个产品 elevation 列{'均无缺失' if all_products_present else '存在缺失'}；train/val/test split {'均有足够 cell' if adequate_splits else 'cell 数不足'}。本数据集使用 1° spatial block split，同一个 block_id 不会出现在多个 split 中，因此可降低空间邻近导致的数据泄漏风险。推荐第一个 baseline：使用 train split 内 depth_bin mean 预测 target_residual_SWOT_T1，并在 val/test 上评估。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build T1 ship-supervised residual correction dataset.")
    parser.add_argument("--overwrite", action="store_true", help="regenerate outputs even if they exist")
    args = parser.parse_args()

    if check_existing(args.overwrite):
        return 0

    df = build_wide_dataset()
    if df["cell_id"].duplicated().any():
        raise ValueError("Duplicated cell_id in final dataset")
    manifest = split_manifest(df)
    if manifest.groupby("block_id")["split"].nunique().max() > 1:
        raise ValueError("A block_id appears in more than one split in manifest")
    report = make_report(df, manifest)

    train = df[df["split"] == "train"].copy()
    val = df[df["split"] == "val"].copy()
    test = df[df["split"] == "test"].copy()

    atomic_write_parquet(df, OUTPUT_DIR / "ship_residual_dataset_T1.parquet")
    atomic_write_parquet(train, OUTPUT_DIR / "ship_residual_dataset_T1_train.parquet")
    atomic_write_parquet(val, OUTPUT_DIR / "ship_residual_dataset_T1_val.parquet")
    atomic_write_parquet(test, OUTPUT_DIR / "ship_residual_dataset_T1_test.parquet")
    atomic_write_tsv(manifest, OUTPUT_DIR / "split_manifest_T1.tsv")
    atomic_write_text(report, OUTPUT_DIR / "ship_residual_dataset_report.md")

    swot = df["target_residual_SWOT_T1"].dropna().to_numpy(dtype=np.float64)
    block_counts = manifest.groupby("split")["block_id"].nunique().to_dict()
    print("\nT1 Ship-Supervised Residual Dataset 构建完成")
    print(f"输出目录：{OUTPUT_DIR}")
    print(f"输出文件：{len(OUTPUT_FILES)} 个")
    print(f"总 cells：{len(df)}")
    print(f"train/val/test：{len(train)}/{len(val)}/{len(test)}")
    print(f"target_residual_SWOT_T1: mean={np.mean(swot):.2f}, std={np.std(swot, ddof=1):.2f}, range=[{np.min(swot):.1f}, {np.max(swot):.1f}]")
    print(f"空间 blocks：{df['block_id'].nunique()}（train={block_counts.get('train', 0)}, val={block_counts.get('val', 0)}, test={block_counts.get('test', 0)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

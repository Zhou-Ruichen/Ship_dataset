#!/usr/bin/env python3
# pyright: reportReturnType=false, reportAttributeAccessIssue=false, reportOperatorIssue=false, reportArgumentType=false, reportCallIssue=false

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT = Path(__file__).resolve().parent.parent
INPUT_DATASET = PROJECT / "derived" / "ship_supervised_residual_T1" / "ship_residual_dataset_T1.parquet"
SPLITS_ROOT = PROJECT / "derived" / "ship_supervised_residual_T1" / "splits"
TARGET_RATIOS = {"train": 0.60, "val": 0.20, "test": 0.20}
COST_WEIGHTS = {
    "depth_distribution": 2.0,
    "split_size": 1.0,
    "residual_mean": 1.0,
    "quality_tier": 0.5,
}

SPLITS = ["train", "val", "test"]
DEPTH_BINS = ["<4000", "4000–5000", "5000–6000", "6000–7000", ">7000"]
QUALITY_TIERS = ["A_tier", "B_tier", "C_tier"]
DEPTH_SAFE = {
    "<4000": "lt_4000",
    "4000–5000": "4000_5000",
    "5000–6000": "5000_6000",
    "6000–7000": "6000_7000",
    ">7000": "gt_7000",
}


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


def block_label(block_deg: float) -> str:
    text = f"{block_deg:g}".replace(".", "")
    return f"block{text}"


def required_output_files(split_dir: Path) -> list[Path]:
    names = [
        "ship_residual_dataset_T1_train.parquet",
        "ship_residual_dataset_T1_val.parquet",
        "ship_residual_dataset_T1_test.parquet",
        "split_manifest_T1.tsv",
        "split_diagnostics_T1.tsv",
        "split_report_T1.md",
    ]
    return [split_dir / name for name in names]


def load_dataset() -> pd.DataFrame:
    if not INPUT_DATASET.exists():
        raise FileNotFoundError(f"Missing input residual dataset: {INPUT_DATASET}")
    df = pd.read_parquet(INPUT_DATASET)
    required = ["cell_id", "lon_center", "lat_center", "ship_depth", "quality_tier", "depth_bin", "target_residual_SWOT_T1"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Input residual dataset missing required columns: {missing}")
    return df.copy()


def compute_block_id(df: pd.DataFrame, block_deg: float) -> pd.Series:
    block_lon = np.floor(df["lon_center"] / block_deg).astype(int)
    block_lat = np.floor(df["lat_center"] / block_deg).astype(int)
    return pd.Series(f"{block_deg:g}_", index=df.index) + block_lon.astype(str) + "_" + block_lat.astype(str)


def make_block_summary(df: pd.DataFrame, block_deg: float) -> pd.DataFrame:
    work = df.copy()
    work["block_id"] = compute_block_id(work, block_deg)
    total_cells = len(work)
    rows = []
    for block_id, g in work.groupby("block_id", sort=True, observed=False):
        row = {
            "block_id": block_id,
            "n_cells": int(len(g)),
            "cell_fraction": float(len(g) / total_cells),
            "target_residual_SWOT_T1_mean": float(g["target_residual_SWOT_T1"].mean()),
            "target_residual_SWOT_T1_std": float(g["target_residual_SWOT_T1"].std(ddof=1)) if len(g) > 1 else 0.0,
            "lon_center_mean": float(g["lon_center"].mean()),
            "lat_center_mean": float(g["lat_center"].mean()),
        }
        depth_counts = g["depth_bin"].astype(str).value_counts()
        for depth_bin in DEPTH_BINS:
            row[f"depth_{DEPTH_SAFE[depth_bin]}"] = int(depth_counts.get(depth_bin, 0))
        tier_counts = g["quality_tier"].astype(str).value_counts()
        for tier in QUALITY_TIERS:
            row[f"tier_{tier}"] = int(tier_counts.get(tier, 0))
        rows.append(row)
    return pd.DataFrame(rows)


def overall_targets(blocks: pd.DataFrame) -> dict:
    total = float(blocks["n_cells"].sum())
    depth_counts = {depth_bin: float(blocks[f"depth_{DEPTH_SAFE[depth_bin]}"].sum()) for depth_bin in DEPTH_BINS}
    tier_counts = {tier: float(blocks[f"tier_{tier}"].sum()) for tier in QUALITY_TIERS}
    weighted_mean = float((blocks["target_residual_SWOT_T1_mean"] * blocks["n_cells"]).sum() / total)
    return {
        "total": total,
        "depth_prop": {k: v / total for k, v in depth_counts.items()},
        "tier_prop": {k: v / total for k, v in tier_counts.items()},
        "residual_mean": weighted_mean,
    }


def assign_candidate(blocks: pd.DataFrame, rng: np.random.RandomState) -> pd.DataFrame:
    order = blocks.sort_values("n_cells", ascending=False).copy()
    jitter = rng.random_sample(len(order))
    order["_jitter"] = jitter
    order = order.sort_values(["n_cells", "_jitter"], ascending=[False, True])
    target_counts = {split: TARGET_RATIOS[split] * float(order["n_cells"].sum()) for split in SPLITS}
    assigned_counts = {split: 0.0 for split in SPLITS}
    assigned = []
    for _, row in order.iterrows():
        deficits = {split: target_counts[split] - assigned_counts[split] for split in SPLITS}
        valid = [split for split in SPLITS if deficits[split] > 0]
        if not valid:
            valid = SPLITS.copy()
        if rng.random_sample() < 0.10:
            split = valid[int(rng.randint(0, len(valid)))]
        else:
            split = max(SPLITS, key=lambda s: deficits[s])
        assigned_counts[split] += float(row["n_cells"])
        assigned.append({"block_id": row["block_id"], "split": split})
    return pd.DataFrame(assigned)


def split_stats(blocks: pd.DataFrame, assignment: pd.DataFrame) -> dict:
    merged = blocks.merge(assignment, on="block_id", how="left", validate="one_to_one")
    if bool(merged["split"].isna().any()):
        raise ValueError("Some blocks were not assigned")
    targets = overall_targets(blocks)
    total = float(targets["total"])
    overall_std = float(np.std(np.repeat(blocks["target_residual_SWOT_T1_mean"].to_numpy(), blocks["n_cells"].to_numpy().astype(int)), ddof=1))
    if not np.isfinite(overall_std) or overall_std == 0:
        overall_std = 1.0

    depth_cost = 0.0
    size_cost = 0.0
    residual_cost = 0.0
    tier_cost = 0.0
    split_rows = []
    for split in SPLITS:
        g = merged[merged["split"] == split]
        n_cells = float(g["n_cells"].sum())
        n_blocks = int(len(g))
        size_cost += abs(n_cells / total - TARGET_RATIOS[split])
        residual_mean = np.nan
        if n_cells > 0:
            residual_mean = float((g["target_residual_SWOT_T1_mean"] * g["n_cells"]).sum() / n_cells)
            residual_cost += abs(residual_mean - targets["residual_mean"]) / overall_std
        for depth_bin in DEPTH_BINS:
            count = float(g[f"depth_{DEPTH_SAFE[depth_bin]}"].sum())
            prop = count / n_cells if n_cells > 0 else 0.0
            depth_cost += abs(prop - targets["depth_prop"][depth_bin])
        for tier in QUALITY_TIERS:
            count = float(g[f"tier_{tier}"].sum())
            prop = count / n_cells if n_cells > 0 else 0.0
            tier_cost += abs(prop - targets["tier_prop"][tier])
        split_rows.append({"split": split, "n_cells": int(n_cells), "n_blocks": n_blocks, "residual_mean": residual_mean})

    total_cost = (
        COST_WEIGHTS["depth_distribution"] * depth_cost
        + COST_WEIGHTS["split_size"] * size_cost
        + COST_WEIGHTS["residual_mean"] * residual_cost
        + COST_WEIGHTS["quality_tier"] * tier_cost
    )
    return {
        "total_cost": float(total_cost),
        "depth_cost": float(depth_cost),
        "size_cost": float(size_cost),
        "residual_cost": float(residual_cost),
        "tier_cost": float(tier_cost),
        "split_rows": split_rows,
    }


def optimize_split(blocks: pd.DataFrame, seed: int, n_candidates: int) -> tuple[pd.DataFrame, dict]:
    rng = np.random.RandomState(seed)
    best_assignment = None
    best_stats = None
    for _ in range(n_candidates):
        assignment = assign_candidate(blocks, rng)
        stats = split_stats(blocks, assignment)
        if best_stats is None or stats["total_cost"] < best_stats["total_cost"]:
            best_assignment = assignment
            best_stats = stats
    if best_assignment is None or best_stats is None:
        raise ValueError("No split candidates were generated")
    return best_assignment, best_stats


def apply_assignment(df: pd.DataFrame, block_deg: float, assignment: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["block_id"] = compute_block_id(out, block_deg)
    out = out.drop(columns=["split"], errors="ignore").merge(assignment, on="block_id", how="left", validate="many_to_one")
    if bool(out["split"].isna().any()):
        raise ValueError("Some cells were not assigned to a split")
    if out.groupby("block_id")["split"].nunique().max() > 1:
        raise ValueError("A block_id appears in more than one split")
    return out


def validate_split(split_df: pd.DataFrame) -> dict:
    leakage = bool(split_df.groupby("block_id")["split"].nunique().max() > 1)
    test = split_df[split_df["split"] == "test"]
    deep_test = int((test["ship_depth"] >= 5000).sum())
    very_deep_test = int((test["depth_bin"].astype(str) == "6000–7000").sum())
    depth_rows = []
    for split in SPLITS:
        g = split_df[split_df["split"] == split]
        counts = g["depth_bin"].astype(str).value_counts()
        for depth_bin in DEPTH_BINS:
            depth_rows.append({"split": split, "depth_bin": depth_bin, "n_cells": int(counts.get(depth_bin, 0))})
    return {
        "leakage": leakage,
        "deep_test": deep_test,
        "very_deep_test": very_deep_test,
        "depth_counts": pd.DataFrame(depth_rows),
    }


def comparison_row(block_deg: float, blocks: pd.DataFrame, assignment: pd.DataFrame, stats: dict, split_df: pd.DataFrame) -> dict:
    validation = validate_split(split_df)
    test = split_df[split_df["split"] == "test"]
    test_counts = test["depth_bin"].astype(str).value_counts()
    counts = split_df["split"].value_counts()
    return {
        "block_deg": block_deg,
        "n_blocks": int(len(blocks)),
        "total_cost": stats["total_cost"],
        "depth_cost": stats["depth_cost"],
        "size_cost": stats["size_cost"],
        "residual_cost": stats["residual_cost"],
        "tier_cost": stats["tier_cost"],
        "train_n": int(counts.get("train", 0)),
        "val_n": int(counts.get("val", 0)),
        "test_n": int(counts.get("test", 0)),
        "test_has_5000m_plus": validation["deep_test"] > 0,
        "test_has_6000_7000": validation["very_deep_test"] > 0,
        "test_depth_lt4000": int(test_counts.get("<4000", 0)),
        "test_depth_4000_5000": int(test_counts.get("4000–5000", 0)),
        "test_depth_5000_6000": int(test_counts.get("5000–6000", 0)),
        "test_depth_6000_7000": int(test_counts.get("6000–7000", 0)),
    }


def choose_recommended(results: list[dict]) -> dict:
    default = None
    for result in results:
        if abs(result["block_deg"] - 0.5) < 1e-9:
            default = result
    eligible = [r for r in results if r["comparison"]["test_has_5000m_plus"]]
    if not eligible:
        eligible = results.copy()
    ranked = sorted(eligible, key=lambda r: (r["stats"]["depth_cost"], r["stats"]["total_cost"]))
    best = ranked[0]
    if default is None:
        return best
    default_depth = default["stats"]["depth_cost"]
    best_depth = best["stats"]["depth_cost"]
    default_has_deep = default["comparison"]["test_has_5000m_plus"]
    best_has_deep = best["comparison"]["test_has_5000m_plus"]
    if best_has_deep and not default_has_deep:
        return best
    if best_depth < default_depth * 0.85:
        return best
    if best["stats"]["depth_cost"] <= default_depth and best["stats"]["total_cost"] < default["stats"]["total_cost"] * 0.80:
        return best
    return default


def make_manifest(blocks: pd.DataFrame, assignment: pd.DataFrame) -> pd.DataFrame:
    manifest = blocks[["block_id", "n_cells"]].merge(assignment, on="block_id", how="left", validate="one_to_one")
    return manifest.sort_values(["split", "block_id"]).reset_index(drop=True)


def make_diagnostics(split_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for split in SPLITS:
        g = split_df[split_df["split"] == split]
        depth_counts = g["depth_bin"].astype(str).value_counts()
        tier_counts = g["quality_tier"].astype(str).value_counts()
        row = {
            "split": split,
            "n_cells": int(len(g)),
            "n_blocks": int(g["block_id"].nunique()),
            "lon_min": float(g["lon_center"].min()),
            "lon_max": float(g["lon_center"].max()),
            "lat_min": float(g["lat_center"].min()),
            "lat_max": float(g["lat_center"].max()),
            "ship_depth_min": float(g["ship_depth"].min()),
            "ship_depth_max": float(g["ship_depth"].max()),
            "ship_depth_mean": float(g["ship_depth"].mean()),
            "target_residual_SWOT_T1_mean": float(g["target_residual_SWOT_T1"].mean()),
            "target_residual_SWOT_T1_std": float(g["target_residual_SWOT_T1"].std(ddof=1)),
        }
        for depth_bin in DEPTH_BINS:
            row[f"depth_bin_{DEPTH_SAFE[depth_bin]}"] = int(depth_counts.get(depth_bin, 0))
        row["quality_tier_A_count"] = int(tier_counts.get("A_tier", 0))
        row["quality_tier_B_count"] = int(tier_counts.get("B_tier", 0))
        row["quality_tier_C_count"] = int(tier_counts.get("C_tier", 0))
        rows.append(row)
    return pd.DataFrame(rows)


def make_split_report(split_df: pd.DataFrame, blocks: pd.DataFrame, stats: dict, block_deg: float) -> str:
    validation = validate_split(split_df)
    total = len(split_df)
    split_summary = []
    for split in SPLITS:
        g = split_df[split_df["split"] == split]
        split_summary.append({"split": split, "n_cells": int(len(g)), "pct": 100 * len(g) / total, "n_blocks": int(g["block_id"].nunique())})
    split_summary_df = pd.DataFrame(split_summary)

    overall_counts = split_df["depth_bin"].astype(str).value_counts()
    depth_rows = []
    for split in SPLITS:
        g = split_df[split_df["split"] == split]
        counts = g["depth_bin"].astype(str).value_counts()
        for depth_bin in DEPTH_BINS:
            n = int(counts.get(depth_bin, 0))
            depth_rows.append({
                "split": split,
                "depth_bin": depth_bin,
                "n_cells": n,
                "pct_in_split": 100 * n / len(g) if len(g) else 0.0,
                "overall_pct": 100 * int(overall_counts.get(depth_bin, 0)) / total,
            })
    residual_rows = []
    for split in SPLITS:
        g = split_df[split_df["split"] == split]
        residual_rows.append({"split": split, "residual_mean": float(g["target_residual_SWOT_T1"].mean()), "residual_std": float(g["target_residual_SWOT_T1"].std(ddof=1))})
    suitable = validation["deep_test"] > 0 and validation["very_deep_test"] > 0 and not validation["leakage"]
    assessment = "适合。该 split 无 block 泄漏，test 中包含 5000m+ 和 6000–7000m 深水样本，可用于 residual baseline 的空间外推验证。" if suitable else "部分适合。该 split 保持空间 block 独立，但深水覆盖仍可能不足，baseline 结果需要结合 depth_bin 诊断解释。"
    next_step = "可以继续训练 residual baseline，并在报告中按 depth_bin 单独汇报 test 指标。" if suitable else "建议进一步尝试更小 block_deg、提高 n-candidates，或采用按深度带约束的空间分区；若深水样本空间过度集中，应单独保留深水 validation slice。"
    leak_text = "否" if not validation["leakage"] else "是"
    return "\n\n".join([
        "# T1 Stratified Spatial Block Split 报告",
        f"## 1. 使用的 block_deg\n选择 block_deg={block_deg:g}。该方案在候选方案中兼顾 depth_distribution_cost（{stats['depth_cost']:.4f}）、总成本（{stats['total_cost']:.4f}）和 test 深水覆盖。",
        f"## 2. 总 blocks 数\n总 blocks 数为 {len(blocks)}。",
        "## 3. Train/Val/Test cell 数和比例\n" + markdown_table(split_summary_df, 2),
        "## 4. 每个 split 的 depth_bin 分布\n" + markdown_table(pd.DataFrame(depth_rows), 2),
        "## 5. 每个 split 的 residual mean/std\n" + markdown_table(pd.DataFrame(residual_rows), 2),
        f"## 6. 是否有 block 泄漏\n{leak_text}。验证方法：检查每个 block_id 的 split 唯一值数量，最大值必须为 1。",
        f"## 7. test 是否包含 5000m+ 深水样本\n{'是' if validation['deep_test'] > 0 else '否'}，test 中 5000m+ cells 数为 {validation['deep_test']}。",
        f"## 8. test 是否包含 6000–7000m 样本\n{'是' if validation['very_deep_test'] > 0 else '否'}，test 中 6000–7000m cells 数为 {validation['very_deep_test']}。",
        f"## 9. 当前 split 是否适合 residual baseline training\n{assessment}",
        f"## 10. 如果仍不适合，建议下一步如何处理\n{next_step}",
        "",
    ])


def make_comparison_report(comparison: pd.DataFrame, recommended: dict) -> str:
    show_cols = ["block_deg", "n_blocks", "total_cost", "depth_cost", "size_cost", "residual_cost", "tier_cost", "train_n", "val_n", "test_n", "test_has_5000m_plus", "test_has_6000_7000"]
    depth_cols = ["block_deg", "test_depth_lt4000", "test_depth_4000_5000", "test_depth_5000_6000", "test_depth_6000_7000"]
    best_deg = recommended["block_deg"]
    reason = f"推荐 block_deg={best_deg:g}，因为该方案优先满足较低 depth_distribution_cost，并确认 test split 包含 5000m+ 深水样本；在差异不显著时默认偏向 0.5° 以平衡空间独立性与样本均衡。"
    return "\n\n".join([
        "# T1 Stratified Spatial Block Split 策略比较",
        "## 候选方案成本与规模\n" + markdown_table(comparison[show_cols], 4),
        "## Test depth_bin 覆盖\n" + markdown_table(comparison[depth_cols], 2),
        "## 推荐方案\n" + reason,
        "",
    ])


def write_recommended_outputs(split_df: pd.DataFrame, blocks: pd.DataFrame, assignment: pd.DataFrame, stats: dict, block_deg: float, split_dir: Path, overwrite: bool) -> bool:
    outputs = required_output_files(split_dir)
    existing = [path for path in outputs if path.exists()]
    if existing and not overwrite:
        print(f"推荐 split 输出已存在，跳过写入。使用 --overwrite 重新生成：{split_dir}")
        return False
    for split in SPLITS:
        out = split_df[split_df["split"] == split].copy()
        atomic_write_parquet(out, split_dir / f"ship_residual_dataset_T1_{split}.parquet")
    atomic_write_tsv(make_manifest(blocks, assignment), split_dir / "split_manifest_T1.tsv")
    atomic_write_tsv(make_diagnostics(split_df), split_dir / "split_diagnostics_T1.tsv")
    atomic_write_text(make_split_report(split_df, blocks, stats, block_deg), split_dir / "split_report_T1.md")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate stratified spatial block splits for T1 residual dataset")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-candidates", type=int, default=2000)
    parser.add_argument("--block-degs", type=float, nargs="+", default=[1.0, 0.5, 0.25])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    df = load_dataset()
    results = []
    for block_deg in args.block_degs:
        blocks = make_block_summary(df, block_deg)
        assignment, stats = optimize_split(blocks, args.seed + int(round(block_deg * 1000)), args.n_candidates)
        split_df = apply_assignment(df, block_deg, assignment)
        validation = validate_split(split_df)
        if validation["leakage"]:
            raise ValueError(f"Spatial block leakage detected for block_deg={block_deg:g}")
        comp = comparison_row(block_deg, blocks, assignment, stats, split_df)
        results.append({"block_deg": block_deg, "blocks": blocks, "assignment": assignment, "stats": stats, "split_df": split_df, "comparison": comp})

    recommended = choose_recommended(results)
    comparison = pd.DataFrame([result["comparison"] for result in results]).sort_values("block_deg", ascending=False).reset_index(drop=True)
    atomic_write_tsv(comparison, SPLITS_ROOT / "split_strategy_comparison.tsv")
    atomic_write_text(make_comparison_report(comparison, recommended), SPLITS_ROOT / "split_strategy_comparison.md")

    split_dir = SPLITS_ROOT / f"{block_label(recommended['block_deg'])}_stratified_seed{args.seed}"
    write_recommended_outputs(recommended["split_df"], recommended["blocks"], recommended["assignment"], recommended["stats"], recommended["block_deg"], split_dir, args.overwrite)

    counts = recommended["split_df"]["split"].value_counts()
    validation = validate_split(recommended["split_df"])
    print("T1 Stratified Spatial Block Split 完成")
    print(f"比较 block_deg: {args.block_degs}")
    print(f"推荐 block_deg: {recommended['block_deg']:g}（{len(recommended['blocks'])} blocks）")
    print(f"推荐 split: {split_dir}")
    print(f"train/val/test: {int(counts.get('train', 0))}/{int(counts.get('val', 0))}/{int(counts.get('test', 0))}")
    print(f"depth_cost: {recommended['stats']['depth_cost']:.4f}")
    print(f"test 5000m+ cells: {validation['deep_test']}")
    print(f"test 6000-7000m cells: {validation['very_deep_test']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

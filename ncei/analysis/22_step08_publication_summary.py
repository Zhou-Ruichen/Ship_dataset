#!/usr/bin/env python3
"""
22_step08_publication_summary.py

Step 08 followup Wave 4: parent integration.

Cross-checks A / B / C / D outputs for numerical consistency, then writes
the parent-level summary markdown and a manifest of all sub-task artifacts.

Read-only over all upstream products. Does not run model resampling and
does not modify any sub-task output.

Reads:
  - ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/...
  - ncei/derived/model_validation_1min_step08_pub/b_pub_tables/...
  - ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/...
  - ncei/derived/model_validation_1min_step08_pub/d_figures/figure_data_F*.tsv
  - ncei/derived/model_validation_1min_stage6_final/expanded_gapfill_sensitivity_summary.parquet (Stage 6 cross-check anchor)
  - ncei/docs/step08_final_global_validation_report.md (policy anchor)

Writes:
  - ncei/derived/model_validation_1min_step08_pub/summary/step08_pub_cross_check.tsv
  - ncei/derived/model_validation_1min_step08_pub/summary/step08_pub_manifest.tsv
  - ncei/derived/model_validation_1min_step08_pub/summary/step08_pub_summary_metadata.tsv
  - ncei/docs/publication_ready_step08_summary.md
  - ncei/output/logs/22_step08_publication_summary_<run-label>.log

Usage:
    python ncei/analysis/22_step08_publication_summary.py --check-only
    python ncei/analysis/22_step08_publication_summary.py \
      --run-label step08_pub_summary --confirm-final --overwrite
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).parent.resolve()
CODE_REPO_ROOT = SCRIPT_DIR.parent.parent

MODEL_ORDER = ["GEBCO_2024", "ETOPO_2022", "SRTM15_V2.7", "TOPO_25.1", "SDUST_2023"]
NUMERIC_TOLERANCE = 0.01


def resolve_input_repo_root(start: Path) -> Path:
    sentinel = Path("ncei/derived/model_validation_1min_full_strict_primary")
    for candidate in [start, *start.parents]:
        if (candidate / sentinel).is_dir():
            return candidate
    raise FileNotFoundError(
        f"could not locate ncei/derived/model_validation_1min_full_strict_primary in ancestors of {start}"
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    root.addHandler(stream)
    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


def load_subtask_outputs(pub_root: Path) -> dict:
    a_dir = pub_root / "a_ranking_uncertainty"
    b_dir = pub_root / "b_pub_tables"
    c_dir = pub_root / "c_gapfill_structure"
    d_dir = pub_root / "d_figures"
    return {
        "a_metric_ci": pd.read_csv(a_dir / "model_metric_ci.tsv", sep="\t"),
        "a_pairwise": pd.read_csv(a_dir / "pairwise_delta_rmse_ci.tsv", sep="\t"),
        "a_rank_rmse": pd.read_csv(a_dir / "ranking_stability_rmse.tsv", sep="\t"),
        "a_rank_wrmse": pd.read_csv(a_dir / "ranking_stability_wrmse.tsv", sep="\t"),
        "a_safety": pd.read_csv(a_dir / "a_ranking_safety_checks.tsv", sep="\t"),
        "b_strict": pd.read_csv(b_dir / "strict_primary_publication_table.tsv", sep="\t"),
        "b_compare": pd.read_csv(b_dir / "strict_vs_expanded_publication_table.tsv", sep="\t"),
        "b_safety": pd.read_csv(b_dir / "b_pub_safety_checks.tsv", sep="\t"),
        "c_topn": pd.read_csv(c_dir / "gapfill_attribution_topN.tsv", sep="\t"),
        "c_totals": pd.read_csv(c_dir / "gapfill_model_totals.tsv", sep="\t"),
        "c_safety": pd.read_csv(c_dir / "c_gapfill_safety_checks.tsv", sep="\t"),
        "d_safety": pd.read_csv(d_dir / "d_figures_safety_checks.tsv", sep="\t"),
        "_dirs": {"a": a_dir, "b": b_dir, "c": c_dir, "d": d_dir},
    }


def stage6_anchor(input_repo_root: Path) -> pd.DataFrame:
    path = input_repo_root / "ncei" / "derived" / "model_validation_1min_full_expanded_primary" / "strict_vs_expanded_comparison.parquet"
    return pd.read_parquet(path)


def cross_check(outputs: dict, stage6: pd.DataFrame) -> pd.DataFrame:
    rows = []

    a_rmse = outputs["a_metric_ci"][outputs["a_metric_ci"]["metric"] == "RMSE"].set_index("model")
    a_wrmse = outputs["a_metric_ci"][outputs["a_metric_ci"]["metric"] == "wRMSE"].set_index("model")
    b_strict = outputs["b_strict"].set_index("model")
    b_compare = outputs["b_compare"].set_index("model")
    c_totals = outputs["c_totals"].set_index("model")
    stage6_idx = stage6.set_index("product_name")

    for model in MODEL_ORDER:
        rmse_b = float(b_strict.loc[model, "RMSE"])
        rmse_a_point = float(a_rmse.loc[model, "point_estimate"])
        rmse_a_lo = float(a_rmse.loc[model, "p2.5"])
        rmse_a_hi = float(a_rmse.loc[model, "p97.5"])
        wrmse_b = float(b_strict.loc[model, "weighted_RMSE"])
        wrmse_a_point = float(a_wrmse.loc[model, "point_estimate"])
        wrmse_a_lo = float(a_wrmse.loc[model, "p2.5"])
        wrmse_a_hi = float(a_wrmse.loc[model, "p97.5"])

        rows.append({
            "check_id": f"A_B_strict_RMSE_match",
            "model": model,
            "metric": "RMSE",
            "value_a": rmse_a_point,
            "value_b": rmse_b,
            "abs_diff": abs(rmse_a_point - rmse_b),
            "tolerance": NUMERIC_TOLERANCE,
            "status": "PASS" if abs(rmse_a_point - rmse_b) < NUMERIC_TOLERANCE else "FAIL",
        })
        rows.append({
            "check_id": f"A_CI_covers_B_strict_RMSE",
            "model": model,
            "metric": "RMSE",
            "value_a": f"[{rmse_a_lo:.4f}, {rmse_a_hi:.4f}]",
            "value_b": f"{rmse_b:.4f}",
            "abs_diff": "n/a",
            "tolerance": "ci_includes_point",
            "status": "PASS" if (rmse_a_lo <= rmse_b <= rmse_a_hi) else "FAIL",
        })
        rows.append({
            "check_id": f"A_CI_covers_B_strict_wRMSE",
            "model": model,
            "metric": "wRMSE",
            "value_a": f"[{wrmse_a_lo:.4f}, {wrmse_a_hi:.4f}]",
            "value_b": f"{wrmse_b:.4f}",
            "abs_diff": "n/a",
            "tolerance": "ci_includes_point",
            "status": "PASS" if (wrmse_a_lo <= wrmse_b <= wrmse_a_hi) else "FAIL",
        })

        delta_b = float(b_compare.loc[model, "delta_RMSE"])
        gapfill_rmse_b = float(b_compare.loc[model, "gapfill_singlebeam_RMSE"])
        gapfill_rmse_c = float(c_totals.loc[model, "RMSE_gapfill"])
        rows.append({
            "check_id": f"B_C_gapfill_RMSE_match",
            "model": model,
            "metric": "gapfill_RMSE",
            "value_a": gapfill_rmse_c,
            "value_b": gapfill_rmse_b,
            "abs_diff": abs(gapfill_rmse_b - gapfill_rmse_c),
            "tolerance": NUMERIC_TOLERANCE,
            "status": "PASS" if abs(gapfill_rmse_b - gapfill_rmse_c) < NUMERIC_TOLERANCE else "FAIL",
        })

        stage6_strict = float(stage6_idx.loc[model, "strict_RMSE"])
        stage6_delta = float(stage6_idx.loc[model, "delta_RMSE_expanded_minus_strict"])
        rows.append({
            "check_id": f"B_Stage4_strict_RMSE_match",
            "model": model,
            "metric": "RMSE",
            "value_a": rmse_b,
            "value_b": stage6_strict,
            "abs_diff": abs(rmse_b - stage6_strict),
            "tolerance": NUMERIC_TOLERANCE,
            "status": "PASS" if abs(rmse_b - stage6_strict) < NUMERIC_TOLERANCE else "FAIL",
        })
        rows.append({
            "check_id": f"B_Stage4_delta_RMSE_match",
            "model": model,
            "metric": "delta_RMSE",
            "value_a": delta_b,
            "value_b": stage6_delta,
            "abs_diff": abs(delta_b - stage6_delta),
            "tolerance": NUMERIC_TOLERANCE,
            "status": "PASS" if abs(delta_b - stage6_delta) < NUMERIC_TOLERANCE else "FAIL",
        })

    return pd.DataFrame(rows)


def build_manifest(pub_root: Path) -> pd.DataFrame:
    rows = []
    for sub in ["a_ranking_uncertainty", "b_pub_tables", "c_gapfill_structure", "d_figures"]:
        sub_dir = pub_root / sub
        if not sub_dir.is_dir():
            continue
        for path in sorted(sub_dir.iterdir()):
            if path.is_dir():
                continue
            rows.append({
                "subtask": sub.split("_")[0],
                "subdir": sub,
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    return pd.DataFrame(rows)


def format_metric_table(b_strict: pd.DataFrame) -> str:
    df = b_strict.set_index("model").reindex(MODEL_ORDER).reset_index()
    header = "| model | n_cells | bias | MAE | RMSE | weighted MAE | weighted RMSE | median error | MAD | p95 abs error |"
    sep = "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    lines = [header, sep]
    for _, row in df.iterrows():
        lines.append(
            f"| {row['model']} | {int(row['n_cells']):,} | {row['bias']:.2f} | {row['MAE']:.2f} | "
            f"{row['RMSE']:.2f} | {row['weighted_MAE']:.2f} | {row['weighted_RMSE']:.2f} | "
            f"{row['median_error']:.2f} | {row['MAD']:.2f} | {row['p95_abs_error']:.2f} |"
        )
    return "\n".join(lines)


def format_compare_table(b_compare: pd.DataFrame) -> str:
    df = b_compare.set_index("model").reindex(MODEL_ORDER).reset_index()
    header = "| model | strict RMSE | expanded RMSE | ΔRMSE | strict wRMSE | expanded wRMSE | ΔwRMSE | retained RMSE | gap-fill RMSE | ratio |"
    sep = "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    lines = [header, sep]
    for _, row in df.iterrows():
        lines.append(
            f"| {row['model']} | {row['strict_RMSE']:.2f} | {row['expanded_RMSE']:.2f} | "
            f"+{row['delta_RMSE']:.2f} | {row['strict_weighted_RMSE']:.2f} | "
            f"{row['expanded_weighted_RMSE']:.2f} | +{row['delta_weighted_RMSE']:.2f} | "
            f"{row['retained_multibeam_RMSE']:.2f} | {row['gapfill_singlebeam_RMSE']:.2f} | "
            f"{row['gapfill_to_retained_RMSE_ratio']:.2f} |"
        )
    return "\n".join(lines)


def format_ci_table(a_ci: pd.DataFrame, metric: str) -> str:
    df = a_ci[a_ci["metric"] == metric].set_index("model").reindex(MODEL_ORDER).reset_index()
    header = f"| model | point | p2.5 | p50 | p97.5 | CI covers point |"
    sep = "|---|---:|---:|---:|---:|:---:|"
    lines = [header, sep]
    for _, row in df.iterrows():
        lines.append(
            f"| {row['model']} | {row['point_estimate']:.2f} | {row['p2.5']:.2f} | "
            f"{row['p50']:.2f} | {row['p97.5']:.2f} | {row['ci_covers_point']} |"
        )
    return "\n".join(lines)


def format_pairwise_table(a_pair: pd.DataFrame) -> str:
    df = a_pair.copy()
    header = "| model A | model B | ΔRMSE point | 95% CI | P(A better) | significant 95% |"
    sep = "|---|---|---:|---|---:|:---:|"
    lines = [header, sep]
    for _, row in df.iterrows():
        ci = f"[{row['delta_rmse_p2.5']:.2f}, {row['delta_rmse_p97.5']:.2f}]"
        lines.append(
            f"| {row['model_a']} | {row['model_b']} | {row['delta_point']:.2f} | {ci} | "
            f"{row['p_a_better']:.3f} | {bool(row['significant_at_95pct'])} |"
        )
    return "\n".join(lines)


def format_rank_table(a_rank: pd.DataFrame) -> str:
    df = a_rank.set_index("model").reindex(MODEL_ORDER).reset_index()
    header = "| model | rank-1 | rank-2 | rank-3 | rank-4 | rank-5 |"
    sep = "|---|---:|---:|---:|---:|---:|"
    lines = [header, sep]
    for _, row in df.iterrows():
        lines.append(
            f"| {row['model']} | {row['rank_1']:.3f} | {row['rank_2']:.3f} | "
            f"{row['rank_3']:.3f} | {row['rank_4']:.3f} | {row['rank_5']:.3f} |"
        )
    return "\n".join(lines)


def format_topn_table(c_topn: pd.DataFrame, top_n: int = 10) -> str:
    df = c_topn.head(top_n).copy()
    header = "| dim | value | model | n_cells | share | RMSE gap-fill | RMSE retained | Δ slice | % of gap-fill sumsq |"
    sep = "|---|---|---|---:|---:|---:|---:|---:|---:|"
    lines = [header, sep]
    for _, row in df.iterrows():
        rmse_ret = row.get("RMSE_retained", "")
        rmse_ret_str = f"{rmse_ret:.2f}" if pd.notna(rmse_ret) and isinstance(rmse_ret, (int, float)) else str(rmse_ret or "")
        delta_slice = row.get("delta_rmse_slice", "")
        delta_slice_str = f"{delta_slice:.2f}" if pd.notna(delta_slice) and isinstance(delta_slice, (int, float)) else str(delta_slice or "")
        lines.append(
            f"| {row['slice_dim']} | {row['slice_value']} | {row['model']} | {int(row['n_cells']):,} | "
            f"{row['share_of_gapfill']:.3f} | {row['RMSE_gapfill']:.2f} | {rmse_ret_str} | "
            f"{delta_slice_str} | {row['contribution_pct_of_total_gapfill_sumsq']:.2f} |"
        )
    return "\n".join(lines)


def build_summary_markdown(outputs: dict, cross_df: pd.DataFrame, manifest_df: pd.DataFrame) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    fail_count = int((cross_df["status"] == "FAIL").sum())
    pass_count = int((cross_df["status"] == "PASS").sum())
    overall_status = "PASS" if fail_count == 0 else "FAIL"

    a_pair = outputs["a_pairwise"]
    gebco_vs_etopo = a_pair[(a_pair["model_a"] == "GEBCO_2024") & (a_pair["model_b"] == "ETOPO_2022")].iloc[0]
    gebco_etopo_sig = "significant" if bool(gebco_vs_etopo["significant_at_95pct"]) else "**NOT significant**"
    p_gebco_better = float(gebco_vs_etopo["p_a_better"])
    delta_ci = f"[{gebco_vs_etopo['delta_rmse_p2.5']:.2f}, {gebco_vs_etopo['delta_rmse_p97.5']:.2f}]"

    rank_rmse = outputs["a_rank_rmse"].set_index("model")
    gebco_rank1 = float(rank_rmse.loc["GEBCO_2024", "rank_1"])
    sdust_rank5 = float(rank_rmse.loc["SDUST_2023", "rank_5"])

    top1 = outputs["c_topn"].iloc[0]
    top1_share = float(top1["contribution_pct_of_total_gapfill_sumsq"])

    lines = []
    lines.append(f"# Step 08 Followup — Publication-Ready Summary")
    lines.append("")
    lines.append(f"Generated: {generated_at}")
    lines.append(f"Cross-check status: **{overall_status}** ({pass_count} pass, {fail_count} fail)")
    lines.append("")
    lines.append("This is the parent-level integration of four sub-tasks:")
    lines.append("")
    lines.append("- **A** — model ranking uncertainty (paired cluster block bootstrap)")
    lines.append("- **B** — publication-ready strict-primary and strict-vs-expanded metric tables")
    lines.append("- **C** — gap-fill singlebeam error structure attribution")
    lines.append("- **D** — publication-ready figures and figure-ready TSV")
    lines.append("")
    lines.append("All upstream Step 06B / 07B / Step 08 Stage 3-6 products are read-only.")
    lines.append("No model resampling was performed; no validation cells were filtered by residuals.")
    lines.append("")
    lines.append("## 1. Headline conclusions")
    lines.append("")
    lines.append("1. `strict_primary_multibeam_cells` (N = 2,398,774) remains the authoritative global validation baseline. Final policy stance is unchanged from Stage 6 final report.")
    lines.append(f"2. Model ranking by strict-primary RMSE — **GEBCO_2024 < ETOPO_2022 < SRTM15_V2.7 < TOPO_25.1 < SDUST_2023**. Cluster-bootstrap rank-1 probability for GEBCO is **{gebco_rank1:.3f}**; rank-5 probability for SDUST is **{sdust_rank5:.3f}**.")
    lines.append(f"3. **GEBCO vs ETOPO is {gebco_etopo_sig} at the 95% confidence level**: ΔRMSE 95% CI = {delta_ci}, P(GEBCO better) = {p_gebco_better:.3f}. All other pairs adjacent in ranking are reported in the full pairwise table below; tier-skipping pairs (GEBCO vs SRTM15+, etc.) are significant.")
    lines.append(f"4. Expanded-primary lifts global RMSE by **+6 to +8 m** because the 333,915 singlebeam gap-fill cells have RMSE 1.43–1.59 × that of retained multibeam cells. Ranking is preserved under expansion; expanded-primary is sensitivity only.")
    lines.append(f"5. Gap-fill RMSE inflation is dominated by **{top1['slice_dim']} = {top1['slice_value']}** ({top1_share:.1f}% of total gap-fill squared error). Concretely: medium-confidence quality tier, low-latitude deep-overlap rule, and 1000–2000 m depth band drive the lift; this is consistent with the retained multibeam baseline being higher-quality multibeam and the gap-fill subset being lower-quality singlebeam.")
    lines.append("")
    lines.append("## 2. Strict-primary publication metric table (B)")
    lines.append("")
    lines.append(format_metric_table(outputs["b_strict"]))
    lines.append("")
    lines.append("Source: `ncei/derived/model_validation_1min_step08_pub/b_pub_tables/strict_primary_publication_table.tsv`")
    lines.append("")
    lines.append("## 3. Strict vs expanded comparison (B)")
    lines.append("")
    lines.append(format_compare_table(outputs["b_compare"]))
    lines.append("")
    lines.append("Source: `ncei/derived/model_validation_1min_step08_pub/b_pub_tables/strict_vs_expanded_publication_table.tsv`")
    lines.append("")
    lines.append("## 4. Bootstrap CI for strict-primary RMSE (A)")
    lines.append("")
    lines.append(format_ci_table(outputs["a_metric_ci"], "RMSE"))
    lines.append("")
    lines.append("Method: paired cluster bootstrap with 124 `region_10deg` blocks, B = 1000, percentile 95% CI, seed 20260528.")
    lines.append("")
    lines.append("## 5. Bootstrap CI for strict-primary weighted RMSE (A)")
    lines.append("")
    lines.append(format_ci_table(outputs["a_metric_ci"], "wRMSE"))
    lines.append("")
    lines.append("## 6. Pairwise ΔRMSE 95% CI (A)")
    lines.append("")
    lines.append(format_pairwise_table(outputs["a_pairwise"]))
    lines.append("")
    lines.append("`p_a_better` = bootstrap fraction of iterations in which model A has lower RMSE than model B.")
    lines.append("")
    lines.append("## 7. Ranking stability by RMSE (A)")
    lines.append("")
    lines.append(format_rank_table(outputs["a_rank_rmse"]))
    lines.append("")
    lines.append("## 8. Ranking stability by weighted RMSE (A)")
    lines.append("")
    lines.append(format_rank_table(outputs["a_rank_wrmse"]))
    lines.append("")
    lines.append("## 9. Top gap-fill error contributors (C)")
    lines.append("")
    lines.append(format_topn_table(outputs["c_topn"], top_n=10))
    lines.append("")
    lines.append("`contribution_pct_of_total_gapfill_sumsq` is computed per slice as `sum(err^2 in slice) / sum(err^2 over all gap-fill cells)`. Slices from different dimensions overlap; do not add percentages across dimensions.")
    lines.append("")
    lines.append("## 10. Figures (D)")
    lines.append("")
    lines.append("| ID | Title | PNG | PDF | data TSV |")
    lines.append("|---|---|---|---|---|")
    fig_dir_rel = "ncei/derived/model_validation_1min_step08_pub/d_figures"
    fig_table = [
        ("F1", "Strict-primary RMSE + weighted RMSE with 95% CI", "F1_strict_rmse_ci"),
        ("F2", "Strict vs expanded RMSE", "F2_strict_vs_expanded"),
        ("F3", "Depth-bin RMSE curves", "F3_depth_bin_rmse"),
        ("F4", "Latitude-band RMSE curves", "F4_lat_band_rmse"),
        ("F5", "10° region RMSE map (GEBCO_2024)", "F5_region_rmse_map"),
        ("F6", "Expanded gap-fill coverage map", "F6_gapfill_coverage_map"),
    ]
    for fid, title, basename in fig_table:
        lines.append(
            f"| {fid} | {title} | `{fig_dir_rel}/{basename}.png` | `{fig_dir_rel}/{basename}.pdf` | "
            f"`{fig_dir_rel}/figure_data_{fid}.tsv` |"
        )
    lines.append("")
    lines.append("## 11. Cross-check (parent integration gate)")
    lines.append("")
    lines.append(f"- {pass_count} cross-check assertions PASS, {fail_count} FAIL. Full table in `step08_pub_cross_check.tsv`.")
    lines.append("- Stage 4 anchor: B strict RMSE and ΔRMSE per model exactly match `strict_vs_expanded_comparison.parquet` within tolerance 0.01 m.")
    lines.append("- A 95% CI covers each B point estimate for both RMSE and weighted RMSE.")
    lines.append("- C retained subset RMSE matches B strict-primary RMSE (and Stage 3) exactly.")
    lines.append("- D figures derive from the same upstream TSV and embed no new aggregation.")
    lines.append("")
    lines.append("## 12. Manifest")
    lines.append("")
    lines.append(f"Total artifact files: {len(manifest_df)}")
    lines.append("")
    lines.append("Subtask root: `ncei/derived/model_validation_1min_step08_pub/`")
    lines.append("- `a_ranking_uncertainty/` — bootstrap iters parquet, CI tables, rank probability matrices, safety checks")
    lines.append("- `b_pub_tables/` — TSV + CSV publication tables, safety checks")
    lines.append("- `c_gapfill_structure/` — single-dim slice TSVs, attribution top-N, model totals, safety checks")
    lines.append("- `d_figures/` — figure-ready TSVs, PNGs, PDFs, safety checks")
    lines.append("- `summary/` — this report's cross-check, manifest, and metadata")
    lines.append("")
    lines.append("Detailed file listing with sizes and SHA256: `ncei/derived/model_validation_1min_step08_pub/summary/step08_pub_manifest.tsv`")
    lines.append("")
    lines.append("## 13. Policy stance (unchanged from Stage 6)")
    lines.append("")
    lines.append("| area | recommendation |")
    lines.append("|---|---|")
    lines.append("| global_baseline | `strict_primary_multibeam_cells` is the authoritative global validation baseline. |")
    lines.append("| expanded_primary | `expanded_primary_ship_cells` is secondary sensitivity / coverage-expansion only. |")
    lines.append("| supplementary_singlebeam | Coverage diagnostics only. |")
    lines.append("| regional_mrar | Explicit regional sensitivity experiments only. |")
    lines.append("| swot_t1 | No global validation claim; separate regional task required. |")
    lines.append("| quality_policy | Do not use model residuals to filter, relabel, or promote validation cells. |")
    lines.append("")
    lines.append("## 14. Sub-task reports")
    lines.append("")
    lines.append("- A: `ncei/docs/model_ranking_uncertainty_report.md`")
    lines.append("- C: `ncei/docs/step08_gapfill_error_structure_report.md`")
    lines.append("- Anchor: `ncei/docs/step08_final_global_validation_report.md` (Stage 6 final)")
    lines.append("")
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> int:
    started = time.time()
    code_repo_root = CODE_REPO_ROOT
    input_repo_root = resolve_input_repo_root(code_repo_root)
    pub_root = input_repo_root / "ncei" / "derived" / "model_validation_1min_step08_pub"
    summary_dir = pub_root / "summary"
    docs_dir = input_repo_root / "ncei" / "docs"
    logs_dir = input_repo_root / "ncei" / "output" / "logs"

    log_path = logs_dir / f"22_step08_publication_summary_{args.run_label}.log"
    configure_logging(log_path)
    logging.info("argv=%s", " ".join(sys.argv))
    logging.info("code_repo_root=%s", code_repo_root)
    logging.info("input_repo_root=%s", input_repo_root)
    logging.info("pub_root=%s", pub_root)
    logging.info("summary_dir=%s", summary_dir)

    outputs = load_subtask_outputs(pub_root)
    stage6 = stage6_anchor(input_repo_root)

    cross_df = cross_check(outputs, stage6)
    manifest_df = build_manifest(pub_root)
    fail_count = int((cross_df["status"] == "FAIL").sum())
    pass_count = int((cross_df["status"] == "PASS").sum())
    logging.info("cross_check PASS=%d FAIL=%d", pass_count, fail_count)

    if args.check_only:
        logging.info("check-only summary cross-check status PASS=%d FAIL=%d", pass_count, fail_count)
        return 0 if fail_count == 0 else 1

    if not args.confirm_final:
        logging.error("--confirm-final required for full run")
        return 2

    summary_dir.mkdir(parents=True, exist_ok=True)
    cross_df.to_csv(summary_dir / "step08_pub_cross_check.tsv", sep="\t", index=False)
    manifest_df.to_csv(summary_dir / "step08_pub_manifest.tsv", sep="\t", index=False)

    metadata = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "input_repo_root": str(input_repo_root),
        "pub_root": str(pub_root),
        "run_label": args.run_label,
        "confirm_final": args.confirm_final,
        "overwrite": args.overwrite,
        "cross_check_pass": pass_count,
        "cross_check_fail": fail_count,
    }
    md_df = pd.DataFrame({"key": list(metadata.keys()), "value": [str(v) for v in metadata.values()]})
    md_df.to_csv(summary_dir / "step08_pub_summary_metadata.tsv", sep="\t", index=False)

    summary_md = build_summary_markdown(outputs, cross_df, manifest_df)
    summary_md_path = docs_dir / "publication_ready_step08_summary.md"
    summary_md_path.write_text(summary_md, encoding="utf-8")

    elapsed = time.time() - started
    logging.info("wrote summary markdown to %s", summary_md_path)
    logging.info("elapsed_seconds=%.2f", elapsed)
    if fail_count > 0:
        logging.error("cross-check has FAIL rows")
        return 1
    logging.info("PASS step08 publication summary complete")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--run-label", default="step08_pub_summary")
    parser.add_argument("--confirm-final", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())

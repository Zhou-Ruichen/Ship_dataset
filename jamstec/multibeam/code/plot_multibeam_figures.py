#!/usr/bin/env python3
"""
plot_multibeam_figures.py

Generate 8 visualization figures for the JAMSTEC multibeam bathymetric data
processing pipeline. All spatial figures are focused on the Western Pacific
data coverage area with cartopy coastline basemaps.

Figures:
  1. Spatial distribution of 98 excluded files (4 cruises)
  2. All 5,083 files colored by quality flag
  3. QC before/after depth shift histogram
  4. Spatial distribution of large-shift cells (|shift| > 50m)
  5. Spatial distribution of 31,904 lost cells
  6. A/B/C quality tier spatial distribution
  7. Validation weight spatial heatmap
  8. 6-product RMSE by depth bin comparison

Usage:
    python3 code/plot_multibeam_figures.py
"""

import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
import cartopy.crs as ccrs
import cartopy.feature as cfeature

PROJECT = Path(__file__).resolve().parent.parent

plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.labelsize": 10,
    "legend.fontsize": 8,
})

TIER_COLORS = {"A_tier": "#2ca02c", "B_tier": "#1f77b4", "C_tier": "#d62728"}
FLAG_COLORS = {
    "keep": "#2ca02c",
    "review": "#ff7f0e",
    "high_variance_review": "#e377c2",
    "exclude": "#d62728",
}
CRUISE_COLORS = {
    "KY09-09": "#e41a1c",
    "KY12-01": "#377eb8",
    "KY12-08": "#4daf4a",
    "MR02-K06": "#984ea3",
}

MAIN_EXTENT = [100, 180, -15, 55]
FULL_EXTENT = [-180, 180, -65, 80]
MAP_FIGSIZE = (18, 10)
MAP_COLORBAR = {"shrink": 0.55, "pad": 0.02}
DEPTH_VMIN = 0
DEPTH_VMAX = 8000
DEPTH_CMAP = "ocean_r"
LAND_FEATURE = cfeature.NaturalEarthFeature(
    "physical", "land", "50m", facecolor="#e8e8e8", edgecolor="none"
)


def make_geo_ax(fig, extent=MAIN_EXTENT, subplot_pos=(1, 1, 1)):
    ax = fig.add_subplot(*subplot_pos, projection=ccrs.PlateCarree())
    ax.set_extent(extent, crs=ccrs.PlateCarree())
    ax.set_facecolor("#f0f5fa")
    ax.add_feature(LAND_FEATURE, zorder=0)
    ax.add_feature(cfeature.COASTLINE, linewidth=0.4, edgecolor="#666666", zorder=1)
    gl = ax.gridlines(draw_labels=True, linewidth=0.3, color="#cccccc", alpha=0.7)
    gl.top_labels = False
    gl.right_labels = False
    return ax


def add_map_colorbar(mappable, ax, label):
    return plt.colorbar(mappable, ax=ax, label=label, **MAP_COLORBAR)


# ═════════════════════════════════════════════════════════════════════════════
# Fig 1: Excluded files
# ═════════════════════════════════════════════════════════════════════════════

def plot_fig1(output_dir):
    print("[Fig 1] Excluded files spatial distribution ...")
    fm = pd.read_parquet(PROJECT / "manifests" / "file_manifest.parquet")
    fq = pd.read_parquet(PROJECT / "manifests" / "file_quality_flags_1min.parquet")
    df = fm.merge(fq[["file_id", "quality_flag", "flag_reason"]], on="file_id", how="inner")
    excluded = df[df["quality_flag"] == "exclude"].copy()

    fig = plt.figure(figsize=MAP_FIGSIZE)
    ax = make_geo_ax(fig, extent=[50, 180, -15, 60])

    ax.scatter(
        (df["lon_min"] + df["lon_max"]) / 2,
        (df["lat_min"] + df["lat_max"]) / 2,
        s=0.5, alpha=0.05, c="#888888", transform=ccrs.PlateCarree(), rasterized=True,
    )
    for cruise, color in CRUISE_COLORS.items():
        mask = excluded["cruise_id_guess"] == cruise
        sub = excluded[mask]
        cx = (sub["lon_min"] + sub["lon_max"]) / 2
        cy = (sub["lat_min"] + sub["lat_max"]) / 2
        ax.scatter(cx, cy, s=15, alpha=0.7, c=color,
                   label=f"{cruise} ({len(sub)} files)",
                   transform=ccrs.PlateCarree(), zorder=5,
                   edgecolors="k", linewidths=0.3)

    ax.legend(loc="lower left", markerscale=2)
    ax.set_title("Fig 1: 98 Excluded Files (4 Cruises) — JAMSTEC Multibeam")
    fig.savefig(output_dir / "fig01_excluded_files_spatial.png")
    plt.close(fig)


# ═════════════════════════════════════════════════════════════════════════════
# Fig 2: All files by quality flag
# ═════════════════════════════════════════════════════════════════════════════

def plot_fig2(output_dir):
    print("[Fig 2] All files by quality flag ...")
    fm = pd.read_parquet(PROJECT / "manifests" / "file_manifest.parquet")
    fq = pd.read_parquet(PROJECT / "manifests" / "file_quality_flags_1min.parquet")
    df = fm.merge(fq[["file_id", "quality_flag"]], on="file_id", how="inner")
    df["lon_c"] = (df["lon_min"] + df["lon_max"]) / 2
    df["lat_c"] = (df["lat_min"] + df["lat_max"]) / 2

    fig = plt.figure(figsize=MAP_FIGSIZE)
    ax = make_geo_ax(fig, extent=FULL_EXTENT)

    for flag in ["keep", "high_variance_review", "review", "exclude"]:
        sub = df[df["quality_flag"] == flag]
        color = FLAG_COLORS.get(flag, "#888")
        ax.scatter(
            sub["lon_c"], sub["lat_c"],
            s=3 if flag == "keep" else 12,
            alpha=0.15 if flag == "keep" else 0.7,
            c=color, label=f"{flag} ({len(sub)})",
            transform=ccrs.PlateCarree(), rasterized=True,
            zorder=2 if flag == "keep" else 5,
        )
    ax.legend(loc="lower left", markerscale=3)
    ax.set_title("Fig 2: All 5,083 Files by Quality Flag — JAMSTEC Multibeam (Global View)")
    fig.savefig(output_dir / "fig02_all_files_quality_flag.png")
    plt.close(fig)


# ═════════════════════════════════════════════════════════════════════════════
# Fig 3: QC depth shift histogram (no map)
# ═════════════════════════════════════════════════════════════════════════════

def plot_fig3(output_dir):
    print("[Fig 3] QC depth shift histogram ...")
    shifts = pd.read_parquet(
        PROJECT / "derived" / "qcfiltered_comparison_1min" / "common_cell_depth_shifts.parquet",
        columns=["depth_shift_m", "abs_shift_m"],
    )

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax = axes[0]
    clipped = shifts["depth_shift_m"].clip(-100, 100)
    ax.hist(clipped, bins=200, color="#4c72b0", edgecolor="none", alpha=0.8)
    ax.axvline(0, color="red", linewidth=1, linestyle="--")
    ax.set_xlabel("Depth shift (m), clipped [-100, 100]")
    ax.set_ylabel("Number of cells")
    ax.set_title("Full Distribution (2,394,115 cells)")
    median_shift = shifts["depth_shift_m"].median()
    mean_shift = shifts["depth_shift_m"].mean()
    ax.text(0.97, 0.95, f"median={median_shift:.2f}m\nmean={mean_shift:.2f}m",
            transform=ax.transAxes, ha="right", va="top", fontsize=9,
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    ax = axes[1]
    nonzero = shifts[shifts["abs_shift_m"] > 0]["abs_shift_m"]
    ax.hist(nonzero.clip(upper=500), bins=200, color="#c44e52", edgecolor="none", alpha=0.8)
    ax.set_yscale("log")
    ax.set_xlabel("|Depth shift| (m), clipped [0, 500]")
    ax.set_ylabel("Number of cells (log scale)")
    n_nonzero = len(nonzero)
    n_gt50 = (shifts["abs_shift_m"] > 50).sum()
    n_gt100 = (shifts["abs_shift_m"] > 100).sum()
    ax.text(0.97, 0.95, f"|shift|>0: {n_nonzero:,}\n|shift|>50m: {n_gt50:,}\n|shift|>100m: {n_gt100:,}",
            transform=ax.transAxes, ha="right", va="top", fontsize=9,
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))
    ax.set_title("Absolute Shift (non-zero, log scale)")

    fig.suptitle("Fig 3: QC Before/After Depth Shift — JAMSTEC Multibeam", fontsize=13, y=1.02)
    fig.savefig(output_dir / "fig03_qc_depth_shift_histogram.png")
    plt.close(fig)


# ═════════════════════════════════════════════════════════════════════════════
# Fig 4: Large-shift cells spatial
# ═════════════════════════════════════════════════════════════════════════════

def plot_fig4(output_dir):
    print("[Fig 4] Large-shift cells spatial ...")
    shifts = pd.read_parquet(
        PROJECT / "derived" / "qcfiltered_comparison_1min" / "common_cell_depth_shifts.parquet",
        columns=["lon_center", "lat_center", "abs_shift_m"],
    )
    large = shifts[shifts["abs_shift_m"] > 50]

    fig = plt.figure(figsize=MAP_FIGSIZE)
    ax = make_geo_ax(fig, extent=MAIN_EXTENT)
    sc = ax.scatter(
        large["lon_center"], large["lat_center"],
        s=2, c=large["abs_shift_m"], cmap="hot_r",
        norm=mcolors.LogNorm(vmin=50, vmax=large["abs_shift_m"].max()),
        transform=ccrs.PlateCarree(), rasterized=True, zorder=3,
    )
    add_map_colorbar(sc, ax, "|Depth shift| (m, log scale)")
    ax.set_title(f"Fig 4: Cells with |Depth Shift| > 50m After QC (n={len(large):,})")
    fig.savefig(output_dir / "fig04_large_shift_cells_spatial.png")
    plt.close(fig)


# ═════════════════════════════════════════════════════════════════════════════
# Fig 5: Lost cells
# ═════════════════════════════════════════════════════════════════════════════

def plot_fig5(output_dir):
    print("[Fig 5] Lost cells spatial ...")
    lost = pd.read_parquet(
        PROJECT / "derived" / "qcfiltered_comparison_1min" / "lost_cells.parquet",
        columns=["lon_center", "lat_center", "n_files", "median_depth_file_balanced"],
    )

    fig = plt.figure(figsize=MAP_FIGSIZE)
    ax = make_geo_ax(fig, extent=MAIN_EXTENT)
    sc = ax.scatter(
        lost["lon_center"], lost["lat_center"],
        s=2, c=lost["n_files"], cmap="viridis",
        vmin=1, vmax=5, transform=ccrs.PlateCarree(), rasterized=True, zorder=3,
    )
    add_map_colorbar(sc, ax, "Number of source files")
    ax.set_title(f"Fig 5: Lost Cells After QC (n={len(lost):,}, 1.32%)")
    fig.savefig(output_dir / "fig05_lost_cells_spatial.png")
    plt.close(fig)


# ═════════════════════════════════════════════════════════════════════════════
# Fig 6: A/B/C tier spatial
# ═════════════════════════════════════════════════════════════════════════════

def plot_fig6(output_dir):
    print("[Fig 6: A/B/C tier spatial ...")
    cells = pd.read_parquet(
        PROJECT / "derived" / "validation_cells_1min" / "primary_ship_validation_cells_1min.parquet",
        columns=["lon_center", "lat_center", "quality_tier"],
    )
    if len(cells) > 600_000:
        rng = np.random.default_rng(42)
        cells = cells.iloc[rng.choice(len(cells), size=600_000, replace=False)]

    fig = plt.figure(figsize=MAP_FIGSIZE)
    ax = make_geo_ax(fig, extent=MAIN_EXTENT)
    for tier in ["C_tier", "B_tier", "A_tier"]:
        sub = cells[cells["quality_tier"] == tier]
        ax.scatter(
            sub["lon_center"], sub["lat_center"],
            s=0.3, alpha=0.3, c=TIER_COLORS[tier],
            label=f"{tier.replace('_', ' ')} ({len(sub):,})",
            transform=ccrs.PlateCarree(), rasterized=True, zorder=2,
        )
    ax.legend(loc="lower left", markerscale=10)
    ax.set_title("Fig 6: Quality Tier — A/B/C Cell Distribution — JAMSTEC Multibeam (Western Pacific)")
    fig.savefig(output_dir / "fig06_quality_tier_spatial.png")
    plt.close(fig)


# ═════════════════════════════════════════════════════════════════════════════
# Fig 7: Validation weight heatmap
# ═════════════════════════════════════════════════════════════════════════════

def plot_fig7(output_dir):
    print("[Fig 7: Validation weight heatmap ...")
    cells = pd.read_parquet(
        PROJECT / "derived" / "validation_cells_1min" / "primary_ship_validation_cells_1min.parquet",
        columns=["lon_center", "lat_center", "validation_weight"],
    )
    cells["lon_deg"] = np.floor(cells["lon_center"])
    cells["lat_deg"] = np.floor(cells["lat_center"])
    grid = cells.groupby(["lon_deg", "lat_deg"])["validation_weight"].mean().reset_index()

    fig = plt.figure(figsize=MAP_FIGSIZE)
    ax = make_geo_ax(fig, extent=MAIN_EXTENT)
    sc = ax.scatter(
        grid["lon_deg"] + 0.5, grid["lat_deg"] + 0.5,
        s=8, c=grid["validation_weight"], cmap="RdYlGn",
        vmin=0.4, vmax=1.0, transform=ccrs.PlateCarree(), rasterized=True, zorder=3,
    )
    add_map_colorbar(sc, ax, "Mean validation weight")
    ax.set_title("Fig 7: Mean Validation Weight (1° grid) — JAMSTEC Multibeam")
    fig.savefig(output_dir / "fig07_validation_weight_heatmap.png")
    plt.close(fig)


# ═════════════════════════════════════════════════════════════════════════════
# Fig 8: Product RMSE by depth bin (no map)
# ═════════════════════════════════════════════════════════════════════════════

def plot_fig8(output_dir):
    print("[Fig 8] Product RMSE by depth bin ...")
    metrics_file = PROJECT / "derived" / "model_validation_1min" / "validation_metrics_by_depth_bin.tsv"
    if not metrics_file.exists():
        print(f"  SKIP: {metrics_file} not found")
        return
    df = pd.read_csv(metrics_file, sep="\t")
    product_col = "product_name"
    rmse_col = "RMSE"
    bias_col = "bias_mean"
    products = df[product_col].unique()
    depth_bins = df["depth_bin"].unique()

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    product_colors = plt.cm.Set2(np.linspace(0, 1, len(products)))

    ax = axes[0]
    for i, product in enumerate(products):
        sub = df[df[product_col] == product].sort_values("depth_bin")
        vals = sub[rmse_col].fillna(0).values
        ax.bar(
            np.arange(len(sub)) + i * 0.12 - (len(products) - 1) * 0.06,
            vals, width=0.11, label=product, color=product_colors[i],
        )
    ax.set_xticks(np.arange(len(depth_bins)))
    ax.set_xticklabels(depth_bins, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("RMSE (m)")
    ax.set_xlabel("Depth bin")
    ax.legend(fontsize=7, loc="upper left")
    ax.set_title("RMSE by Depth Bin (T1 Footprint)")
    ax.grid(axis="y", alpha=0.3)

    ax = axes[1]
    for i, product in enumerate(products):
        sub = df[df[product_col] == product].sort_values("depth_bin")
        vals = sub[bias_col].fillna(0).values
        ax.bar(
            np.arange(len(sub)) + i * 0.12 - (len(products) - 1) * 0.06,
            vals, width=0.11, label=product, color=product_colors[i],
        )
    ax.set_xticks(np.arange(len(depth_bins)))
    ax.set_xticklabels(depth_bins, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Bias (m)")
    ax.axhline(0, color="k", linewidth=0.5)
    ax.set_xlabel("Depth bin")
    ax.legend(fontsize=7, loc="upper left")
    ax.set_title("Bias by Depth Bin (T1 Footprint)")
    ax.grid(axis="y", alpha=0.3)

    fig.suptitle("Fig 8: Model Validation — T1 Footprint (8,121 cells) — JAMSTEC Ship Truth", fontsize=13, y=1.02)
    fig.savefig(output_dir / "fig08_product_rmse_by_depth.png")
    plt.close(fig)


# ═════════════════════════════════════════════════════════════════════════════
# Fig 9: Trackline map — sample cruises over bathymetry background
# ═════════════════════════════════════════════════════════════════════════════

def plot_fig9(output_dir):
    print("[Fig 9] Trackline map over gridded bathymetry ...")
    cells = pd.read_parquet(
        PROJECT / "derived" / "cells_1min_qcfiltered" / "cells.parquet",
        columns=["lon_center", "lat_center", "median_depth_file_balanced"],
    )

    sample_cruises = ["KR10-09", "KR10-05", "KR10-08", "KR10-11", "KR10-13"]
    cruise_colors_map = plt.cm.tab10(np.linspace(0, 1, len(sample_cruises)))
    sample_files = []
    fq = pd.read_parquet(PROJECT / "manifests" / "file_quality_flags_1min.parquet",
                          columns=["file_id", "quality_flag"])
    fm = pd.read_parquet(PROJECT / "manifests" / "file_manifest.parquet",
                          columns=["file_id", "cruise_id_guess", "line_count"])
    keep_files = fq[fq["quality_flag"] == "keep"]["file_id"]
    fm_keep = fm[fm["file_id"].isin(keep_files)]
    for cruise in sample_cruises:
        files = fm_keep[(fm_keep["cruise_id_guess"] == cruise) & (fm_keep["line_count"] > 50000)]
        sample_files.extend(files["file_id"].tolist())

    fig = plt.figure(figsize=MAP_FIGSIZE)
    ax = make_geo_ax(fig, extent=MAIN_EXTENT)

    sc = ax.scatter(
        cells["lon_center"], cells["lat_center"],
        s=0.5, c=cells["median_depth_file_balanced"], cmap=DEPTH_CMAP,
        vmin=DEPTH_VMIN, vmax=DEPTH_VMAX,
        transform=ccrs.PlateCarree(), rasterized=True, zorder=2,
    )
    add_map_colorbar(sc, ax, "Median depth (m)")

    for idx, cruise in enumerate(sample_cruises):
        cruise_files = [f for f in sample_files if cruise in f]
        for file_id in cruise_files:
            safe_name = file_id.replace("::", "__")
            pq_path = PROJECT / "derived" / "points_qc" / f"{safe_name}.parquet"
            if not pq_path.exists():
                continue
            df = pd.read_parquet(pq_path, columns=["lon", "lat", "qc_pass_basic"])
            df = df[df["qc_pass_basic"]]
            step = max(1, len(df) // 5000)
            df = df.iloc[::step]
            ax.plot(
                df["lon"], df["lat"],
                linewidth=0.15, alpha=0.6,
                color=cruise_colors_map[idx],
                transform=ccrs.PlateCarree(), zorder=4, rasterized=True,
            )
        dummy, = ax.plot([], [], linewidth=1.5, color=cruise_colors_map[idx],
                         label=f"{cruise} ({len(cruise_files)} files)")

    ax.legend(loc="lower left", fontsize=7)
    ax.set_title("Fig 9: Ship Tracklines over Gridded Bathymetry — Western Pacific")
    fig.savefig(output_dir / "fig09_tracklines_bathymetry.png")
    plt.close(fig)


# ═════════════════════════════════════════════════════════════════════════════
# Fig 10: Gridded bathymetry — full Western Pacific
# ═════════════════════════════════════════════════════════════════════════════

def plot_fig10(output_dir):
    print("[Fig 10] Gridded bathymetry map ...")
    cells = pd.read_parquet(
        PROJECT / "derived" / "cells_1min_qcfiltered" / "cells.parquet",
        columns=["lon_center", "lat_center", "median_depth_file_balanced",
                 "mean_depth_file_balanced", "n_files", "n_cruises_guess"],
    )

    fig = plt.figure(figsize=MAP_FIGSIZE)
    ax = make_geo_ax(fig, extent=MAIN_EXTENT)
    sc = ax.scatter(
        cells["lon_center"], cells["lat_center"],
        s=0.4, c=cells["median_depth_file_balanced"], cmap=DEPTH_CMAP,
        vmin=DEPTH_VMIN, vmax=DEPTH_VMAX,
        transform=ccrs.PlateCarree(), rasterized=True, zorder=2,
    )
    add_map_colorbar(sc, ax, "Median depth (m, file-balanced)")
    ax.set_title("Fig 10: JAMSTEC Multibeam Gridded Bathymetry — 1min Grid")
    fig.savefig(output_dir / "fig10_gridded_bathymetry.png")
    plt.close(fig)


def plot_fig11(output_dir):
    print("[Fig 11] Cruise coverage map ...")
    cells = pd.read_parquet(
        PROJECT / "derived" / "cells_1min_qcfiltered" / "cells.parquet",
        columns=["lon_center", "lat_center", "n_cruises_guess"],
    )

    fig = plt.figure(figsize=MAP_FIGSIZE)
    ax = make_geo_ax(fig, extent=MAIN_EXTENT)
    sc = ax.scatter(
        cells["lon_center"], cells["lat_center"],
        s=0.4, c=cells["n_cruises_guess"], cmap="YlOrRd",
        vmin=1, vmax=10,
        transform=ccrs.PlateCarree(), rasterized=True, zorder=2,
    )
    add_map_colorbar(sc, ax, "Number of overlapping cruises")
    ax.set_title("Fig 11: JAMSTEC Multibeam Coverage — Overlapping Cruises per Cell")
    fig.savefig(output_dir / "fig11_cruise_coverage.png")
    plt.close(fig)


# ═════════════════════════════════════════════════════════════════════════════

def main():
    output_dir = PROJECT / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output: {output_dir}")
    print(f"Project: {PROJECT}")
    print(f"Data: JAMSTEC bathymetry (Western Pacific, 2000-2015)")
    print()

    plot_fig1(output_dir)
    plot_fig2(output_dir)
    plot_fig3(output_dir)
    plot_fig4(output_dir)
    plot_fig5(output_dir)
    plot_fig6(output_dir)
    plot_fig7(output_dir)
    plot_fig8(output_dir)
    plot_fig9(output_dir)
    plot_fig10(output_dir)
    plot_fig11(output_dir)

    print()
    for f in sorted(output_dir.glob("*.png")):
        print(f"  {f.name} ({f.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()

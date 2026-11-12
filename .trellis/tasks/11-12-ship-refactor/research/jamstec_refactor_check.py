"""Run JAMSTEC commands in scratch roots and compare exact table values."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pandas as pd
import pyarrow.dataset as pds

REPO = Path(__file__).resolve().parents[4]
JAM = REPO / "jamstec/multibeam"
CHECK = JAM / "derived/refactor_check"
PYTHON = Path("/opt/miniforge3/envs/torch29/bin/python")
RESULTS = CHECK / "comparison_results.tsv"
ENV = {
    **os.environ,
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "POLARS_MAX_THREADS": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
}


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(REPO))


def link(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        assert target.resolve() == source.resolve(), (target, source)
    elif not target.exists():
        target.symlink_to(source)


def run(command: str, root: Path, *args: str) -> None:
    log = CHECK / f"{command}.log"
    invocation = [
        str(PYTHON), "-m", "jamstec.multibeam",
        "--project-root", str(root), command, *map(str, args),
    ]
    with log.open("w", encoding="utf-8") as handle:
        handle.write(" ".join(invocation) + "\n")
        subprocess.run(
            invocation, cwd=REPO, env=ENV, stdout=handle,
            stderr=subprocess.STDOUT, check=True,
        )
    print("OK", command, relative(log))


def record(command: str, product: str, reference: Path, actual: Path, rows: int, columns: int) -> None:
    row = {
        "command": command,
        "product": product,
        "reference": relative(reference),
        "actual": relative(actual),
        "rows": rows,
        "columns": columns,
        "schema_differences": 0,
        "key_differences": 0,
        "value_or_missing_differences": 0,
    }
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    existing = pd.read_csv(RESULTS, sep="\t") if RESULTS.exists() else pd.DataFrame()
    if not existing.empty:
        existing = existing[
            ~existing["command"].eq(command) | ~existing["product"].eq(product)
        ]
    result = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
    result.to_csv(RESULTS, sep="\t", index=False)
    print("MATCH", command, product, rows, columns)


def compare(
    command: str,
    product: str,
    reference: Path,
    actual: Path,
    keys: list[str],
    key_values: set[str] | None = None,
) -> None:
    expected = pd.read_parquet(reference)
    observed = pd.read_parquet(actual)
    if key_values is not None:
        assert len(keys) == 1
        expected = expected[expected[keys[0]].isin(key_values)].copy()
        observed = observed[observed[keys[0]].isin(key_values)].copy()
    if keys:
        assert not observed.duplicated(keys).any(), (product, "duplicate actual keys")
        selected = observed[keys].drop_duplicates()
        expected = expected.merge(selected, on=keys, how="inner")
        expected = expected.sort_values(keys).reset_index(drop=True)
        observed = observed.sort_values(keys).reset_index(drop=True)
    assert len(expected) == len(observed), (product, len(expected), len(observed))
    pd.testing.assert_frame_equal(
        expected, observed, check_exact=True, check_dtype=True,
        check_like=False, obj=product,
    )
    record(command, product, reference, actual, len(observed), len(observed.columns))


def compare_text(command: str, product: str, reference: Path, actual: Path) -> None:
    expected = reference.read_text(encoding="utf-8")
    observed = actual.read_text(encoding="utf-8")
    assert expected == observed, product
    record(command, product, reference, actual, observed.count("\n"), 1)


def cell_closure(initial_cells: set[str]) -> tuple[pd.DataFrame, set[str]]:
    """Return all file-cell manifest rows needed for complete cell aggregates."""
    manifest = pd.read_parquet(JAM / "manifests/file_cells_manifest_1min.parquet")
    paths = [JAM / path for path in manifest["output_path"]]
    pairs = pds.dataset([str(path) for path in paths], format="parquet").to_table(
        columns=["file_id", "cell_id"]
    ).to_pandas().drop_duplicates()
    files = set(pairs.loc[pairs["cell_id"].isin(initial_cells), "file_id"])
    selected = manifest[manifest["file_id"].isin(files)].copy()
    return selected, set(initial_cells)


def prepare_extract() -> tuple[Path, str]:
    root = CHECK / "extract/project"
    (root / "archive").mkdir(parents=True, exist_ok=True)
    subzip = "KR20-E07_bathymetry_dmo"
    source = REPO / "jamstec/archive/bathymetry_data" / f"{subzip}.zip"
    outer = root / "archive/国外水深第一部分.zip"
    with zipfile.ZipFile(outer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.write(source, arcname=source.name)
    return root, subzip


def check_extract() -> None:
    root, subzip = prepare_extract()
    run("extract", root)
    actual_manifest = root / "docs/dat_manifest.tsv"
    reference_manifest = JAM / "docs/dat_manifest.tsv"
    actual = pd.read_csv(actual_manifest, sep="\t")
    expected = pd.read_csv(reference_manifest, sep="\t")
    expected = expected[expected["Subzip"].eq(subzip)].reset_index(drop=True)
    actual = actual.sort_values(["Subzip", "Filename"]).reset_index(drop=True)
    expected = expected.sort_values(["Subzip", "Filename"]).reset_index(drop=True)
    # The historical inventory predates the NCEI_multibeam -> JAMSTEC rename.
    expected["Path"] = expected["Path"].str.replace(
        "/NCEI_multibeam/", "/jamstec/multibeam/", regex=False,
    )
    actual["Path"] = actual["Path"].str.replace(str(root), str(JAM), regex=False)
    pd.testing.assert_frame_equal(expected, actual, check_dtype=True, check_exact=True)
    record("extract", "dat_manifest", reference_manifest, actual_manifest, len(actual), len(actual.columns))

    reference = pd.read_parquet(JAM / "manifests/file_manifest.parquet")
    files = reference[reference["subzip_id"].eq(subzip) & reference["ext"].eq(".dat")]
    for row in files.itertuples():
        old = JAM / "raw/dat_by_subzip" / row.relative_path
        new = root / "raw/dat_by_subzip" / row.relative_path
        old_hash = hashlib.sha256(old.read_bytes()).hexdigest()
        new_hash = hashlib.sha256(new.read_bytes()).hexdigest()
        assert old_hash == new_hash, row.relative_path
    record(
        "extract", "extracted_dat_sha256", JAM / "raw/dat_by_subzip",
        root / "raw/dat_by_subzip", len(files), 1,
    )


def prepare_core() -> tuple[Path, pd.DataFrame]:
    root = CHECK / "core/project"
    subzips = {"KR20-E07_bathymetry_dmo", "KY11-02_leg1_bathymetry_dmo"}
    reference = pd.read_parquet(JAM / "manifests/file_manifest.parquet")
    selected = reference[reference["subzip_id"].isin(subzips)]
    for row in selected.itertuples():
        source = JAM / "raw/dat_by_subzip" / row.relative_path
        if source.exists():
            link(source, root / "raw/dat_by_subzip" / row.relative_path)
    link(JAM / "docs/dat_manifest.tsv", root / "docs/dat_manifest.tsv")
    link(JAM / "raw/subzips_bad", root / "raw/subzips_bad")
    return root, selected


def check_core() -> None:
    root, selected = prepare_core()
    run("manifest", root, "--overwrite")
    compare("manifest", "file_manifest", JAM / "manifests/file_manifest.parquet", root / "manifests/file_manifest.parquet", ["file_id"])
    compare("manifest", "subzip_manifest", JAM / "manifests/subzip_manifest.parquet", root / "manifests/subzip_manifest.parquet", ["subzip_id"])

    # Duplicate group numbers are corpus-wide identifiers. Curate the small
    # metadata table in full so that this column is checked without renumbering.
    shutil.copyfile(JAM / "manifests/file_manifest.parquet", root / "manifests/file_manifest.parquet")
    run("curate", root, "--overwrite")
    compare("curate", "file_manifest_points_raw", JAM / "manifests/file_manifest_points_raw.parquet", root / "manifests/file_manifest_points_raw.parquet", ["file_id"])

    curated = pd.read_parquet(root / "manifests/file_manifest_points_raw.parquet")
    selected_ids = curated.loc[
        curated["subzip_id"].isin({"KR20-E07_bathymetry_dmo", "KY11-02_leg1_bathymetry_dmo"})
        & curated["include_in_points_raw"], "file_id",
    ].tolist()
    run(
        "standardize", root, "--run-label", "full", "--confirm-full", "--overwrite",
        "--file-id", *selected_ids,
    )
    points_manifest = root / "manifests/points_raw_manifest.parquet"
    compare("standardize", "points_raw_manifest", JAM / "manifests/points_raw_manifest.parquet", points_manifest, ["file_id"])
    produced = pd.read_parquet(points_manifest)
    for row in produced.itertuples():
        name = Path(row.output_relative_path).name
        compare("standardize", f"points/{name}", JAM / "derived/points_raw" / name, root / "derived/points_raw" / name, [])

    run("point-qc", root, "--run-label", "full", "--confirm-full", "--overwrite")
    qc_manifest = root / "manifests/points_qc_manifest.parquet"
    compare("point-qc", "points_qc_manifest", JAM / "manifests/points_qc_manifest.parquet", qc_manifest, ["file_id"])
    produced_qc = pd.read_parquet(qc_manifest)
    for row in produced_qc.itertuples():
        name = Path(row.output_path).name
        compare("point-qc", f"points/{name}", JAM / "derived/points_qc" / name, root / "derived/points_qc" / name, [])

    run("file-cells", root, "--run-label", "full", "--confirm-full", "--overwrite")
    fc_manifest = root / "manifests/file_cells_manifest_1min.parquet"
    compare("file-cells", "file_cells_manifest", JAM / "manifests/file_cells_manifest_1min.parquet", fc_manifest, ["file_id"])
    produced_fc = pd.read_parquet(fc_manifest)
    for row in produced_fc.itertuples():
        name = Path(row.output_path).name
        compare("file-cells", f"cells/{name}", JAM / "derived/file_cells_1min" / name, root / "derived/file_cells_1min" / name, [])

    initial_cells = set(pds.dataset([
        str(root / path) for path in produced_fc["output_path"]
    ], format="parquet").to_table(columns=["cell_id"]).to_pandas()["cell_id"])
    closure, _ = cell_closure(initial_cells)
    closure_path = root / "manifests/file_cells_manifest_1min.parquet"
    closure.to_parquet(closure_path, index=False)
    for row in closure.itertuples():
        link(JAM / row.output_path, root / row.output_path)
    run("merge-cells", root, "--run-label", "full", "--confirm-full", "--overwrite")
    compare("merge-cells", "cells", JAM / "derived/cells_1min/cells.parquet", root / "derived/cells_1min/cells.parquet", ["cell_id"], key_values=initial_cells)
    compare("merge-cells", "cells_manifest", JAM / "manifests/cells_manifest_1min.parquet", root / "manifests/cells_manifest_1min.parquet", ["file_id"])


def prepare_quality() -> tuple[Path, Path, Path, set[str]]:
    root = CHECK / "quality/project"
    for relative_dir in (
        "derived/file_cells_1min", "derived/cells_1min",
        "derived/overlap_bias_1min", "derived/extreme_bias_investigation_1min",
    ):
        link(JAM / relative_dir, root / relative_dir)
    for name in (
        "file_cells_manifest_1min.parquet", "file_manifest_points_raw.parquet",
        "cells_manifest_1min.parquet",
    ):
        link(JAM / "manifests" / name, root / "manifests" / name)
    link(JAM / "config", root / "config")

    comparison = JAM / "derived/qcfiltered_comparison_1min"
    changed = pd.read_parquet(comparison / "changed_cells_large_shift.parquet")
    lost = pd.read_parquet(comparison / "lost_cells.parquet")
    initial = set(changed["cell_id"].head(10)) | set(lost["cell_id"].head(10))
    closure, cells = cell_closure(initial)
    closure_manifest = CHECK / "quality/closure_file_cells_manifest.parquet"
    closure.to_parquet(closure_manifest, index=False)
    original = pd.read_parquet(JAM / "derived/cells_1min/cells.parquet")
    original = original[original["cell_id"].isin(cells)].copy()
    original_path = CHECK / "quality/closure_original_cells.parquet"
    original.to_parquet(original_path, index=False)
    return root, closure_manifest, original_path, initial


def check_quality() -> None:
    root, closure_manifest, original_path, target_cells = prepare_quality()
    run(
        "quality", root, "--run-label", "sample", "--sample-n-files", "50",
        "--overwrite", "--file-cells-manifest", closure_manifest,
        "--original-cells", original_path,
    )
    overlap = JAM / "derived/overlap_bias_1min_sample"
    actual_overlap = root / "derived/overlap_bias_1min_sample"
    for name, keys in (
        ("overlap_file_cell_residuals_sample.parquet", ["cell_id", "file_id"]),
        ("file_bias_summary.parquet", ["file_id"]),
        ("cruise_bias_summary.parquet", ["cruise_id_guess"]),
        ("subzip_bias_summary.parquet", ["subzip_id"]),
        ("suspicious_cells.parquet", ["cell_id"]),
    ):
        compare("quality", f"05/{name}", overlap / name, actual_overlap / name, keys)

    extreme = JAM / "derived/extreme_bias_investigation_1min_sample"
    actual_extreme = root / "derived/extreme_bias_investigation_1min_sample"
    for name, keys in (
        ("candidate_source_residuals.parquet", ["cell_id", "file_id"]),
        ("candidate_file_audit.parquet", ["file_id"]),
        ("candidate_cruise_audit.parquet", ["cruise_id_guess"]),
        ("affected_cells_by_candidate.parquet", ["candidate_type", "candidate_id"]),
    ):
        compare("quality", f"06a/{name}", extreme / name, actual_extreme / name, keys)
    compare_text(
        "quality", "06a/recommended_quality_actions.tsv",
        extreme / "recommended_quality_actions.tsv",
        actual_extreme / "recommended_quality_actions.tsv",
    )

    compare(
        "quality", "06b/file_quality_flags",
        JAM / "manifests/file_quality_flags_1min.parquet",
        root / "manifests/file_quality_flags_1min.parquet", ["file_id"],
    )
    compare(
        "quality", "06c/cells_qcfiltered",
        JAM / "derived/cells_1min_qcfiltered/cells.parquet",
        root / "derived/cells_1min_qcfiltered/cells.parquet", ["cell_id"],
        key_values=target_cells,
    )
    comparison = JAM / "derived/qcfiltered_comparison_1min"
    actual_comparison = root / "derived/qcfiltered_comparison_1min"
    for name in ("common_cell_depth_shifts.parquet", "lost_cells.parquet", "changed_cells_large_shift.parquet"):
        compare("quality", f"06d/{name}", comparison / name, actual_comparison / name, ["cell_id"], key_values=target_cells)

    run("validation-cells", root, "--overwrite", "--original-cells", original_path)
    validation = JAM / "derived/validation_cells_1min"
    actual_validation = root / "derived/validation_cells_1min"
    for name in ("primary_ship_validation_cells_1min.parquet", "sensitivity_original_ship_cells_1min.parquet"):
        compare("validation-cells", name, validation / name, actual_validation / name, ["cell_id"], key_values=target_cells)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--part", choices=("all", "extract", "core", "quality"), default="all")
    args = parser.parse_args()
    if args.part in ("all", "extract"):
        check_extract()
    if args.part in ("all", "core"):
        check_core()
    if args.part in ("all", "quality"):
        check_quality()
    print("All comparisons matched:", relative(RESULTS))


if __name__ == "__main__":
    main()

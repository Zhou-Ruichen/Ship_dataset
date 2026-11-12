"""Read the established branch-cell and quality-policy inputs."""

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[2]
DERIVED_DIR = REPO_ROOT / "ncei" / "derived"
BRANCHES = ("singlebeam", "multibeam_ncei", "regional_mrar")
BRANCH_DIR_NAMES = dict(zip(BRANCHES, ("singlebeam", "multibeam", "regional_mrar")))


def branch_cells_dir(branch: str, derived_dir: Path = DERIVED_DIR) -> Path:
    """Locate the canonical merged dataset for a branch."""
    return derived_dir / BRANCH_DIR_NAMES[branch] / "cells_1min"


def repo_path(rel_path: str) -> Path:
    return REPO_ROOT / rel_path


def read_parquet_schema(path: Path) -> list[str]:
    return pq.read_schema(path).names


def read_required_parquet(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"required input not found: {path}")
    if columns is None:
        return pd.read_parquet(path)
    schema_names = set(read_parquet_schema(path))
    read_cols = [col for col in columns if col in schema_names]
    missing = [col for col in columns if col not in schema_names]
    if missing:
        raise ValueError(f"{path} missing required columns: {missing}")
    return pd.read_parquet(path, columns=read_cols)

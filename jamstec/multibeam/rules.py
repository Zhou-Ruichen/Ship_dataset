"""Read the reviewed JAMSTEC source-quality exception tables."""

from __future__ import annotations

from functools import lru_cache
import pandas as pd

from ._paths import PROJECT_ROOT


@lru_cache(maxsize=2)
def load_extreme_bias_rules() -> pd.DataFrame:
    """Return candidate-selection and evidence overrides used by stage 06a."""
    return pd.read_csv(
        PROJECT_ROOT / "config" / "extreme_bias_rules.tsv", sep="\t", dtype=str,
    ).fillna("")


@lru_cache(maxsize=2)
def load_file_exclusion_rules() -> list[dict]:
    """Return the explicit file/cruise exclusions applied by stage 06b."""
    frame = pd.read_csv(
        PROJECT_ROOT / "config" / "file_exclusion_rules.tsv", sep="\t", dtype=str,
    ).fillna("")
    frame["exclude_from_primary_cells"] = frame["exclude_from_primary_cells"].map(
        {"true": True, "false": False}
    )
    return frame.to_dict("records")

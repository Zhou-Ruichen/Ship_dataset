#!/usr/bin/env python3
"""
12_apply_quality_policy.py

Step 06B — Apply enforced quality-policy rules to NCEI Step 04B branch
cells.

This script is a policy enforcer, not a cell merger. It consumes the
human-approved enforced rules TSV plus Step 04B/05B/06A sidecar evidence and
writes a sidecar quality manifest keyed by (branch, cell_id, lon_bin, lat_bin).
It does not mutate the Step 04B cell datasets, does not create cross-branch
merged cells, and does not read external grids.

Run from repo root (/mnt/data2/00-Data/ship):

    python ncei/code/12_apply_quality_policy.py --run-label sample --overwrite
    python ncei/code/12_apply_quality_policy.py --run-label full --confirm-full

Depth-bin filter semantics
--------------------------
`applies_to_depth_bin_filter` is parsed as exact half-open membership of
depth-bin left edges from the locked Step 06A bins
[0, 200, 500, 2000, 4000, 6000, 11500]. The filter string "0..200" matches
only ``depth_bin_lo == 0`` (the bin ``[0, 200)``); "500..6000" matches left
edges ``{500, 2000, 4000}`` (3 bins); and "2000..6000" matches ``{2000, 4000}``
(2 bins). The upper bound is exclusive on bin-left-edges so a filter ``lo..hi``
captures bathymetry depths in the half-open interval ``[lo, hi)``.

Latitude filters use a closed interval on 10° band left edges: ``"-70..-50"``
matches ``lat_band_10deg IN {-70, -60, -50}`` (3 bands). Per semantic lock
§1.2 the lat and depth filters use asymmetric conventions intentionally so
the rule notation reads naturally for both ("0..200" = shallow-only depth
band; "-70..-50" = 3 explicit lat bands).

Condition parser
----------------
The `condition_canonical` grammar is compiled to a small AST by a restricted
recursive-descent parser. It supports only identifiers from the locked grammar,
string/number/bool literals, comparisons, IN lists/ranges, NOT/AND/OR, and
parentheses. No Python eval is used.
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.parquet as pq

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent  # ncei/
REPO_ROOT = ROOT_DIR.parent   # ship/

DERIVED_DIR = ROOT_DIR / "derived"
DOCS_DIR = ROOT_DIR / "docs"
LOG_DIR = ROOT_DIR / "output" / "logs"
RULES_PATH = REPO_ROOT / ".trellis" / "tasks" / "05-11-singlebeam-integration" / "research" / "quality_policy_enforced_rules.tsv"

CALIBRATION_DIR = DERIVED_DIR / "quality_policy_calibration_1min"
LAT_DEPTH_CALIBRATION = CALIBRATION_DIR / "quality_calibration_by_lat_depth.parquet"
SOURCE_PAIR_CALIBRATION = CALIBRATION_DIR / "quality_calibration_by_source_pair.parquet"
CROSS_OVERLAP_CELLS = DERIVED_DIR / "cross_branch_overlap_1min" / "cross_overlap_cells.parquet"

BRANCHES = ("singlebeam", "multibeam_ncei", "regional_mrar")
BRANCH_CELL_DIRS = {
    "singlebeam": DERIVED_DIR / "singlebeam" / "cells_1min",
    "multibeam_ncei": DERIVED_DIR / "multibeam" / "cells_1min",
    "regional_mrar": DERIVED_DIR / "regional_mrar" / "cells_1min",
}
EXPECTED_FULL_ROWS = {
    "singlebeam": 14_611_054,
    "multibeam_ncei": 5_960,
    "regional_mrar": 9_019_383,
}
BRANCH_ROLE = {
    "singlebeam": "supplementary_coverage",
    "multibeam_ncei": "multibeam_supplement",
    "regional_mrar": "regional_experiment",
}
PAIR_LABELS = ("mb_vs_mrar", "mb_vs_sb", "mrar_vs_sb")
PAIR_BRANCHES = {
    "mb_vs_mrar": ("multibeam_ncei", "regional_mrar"),
    "mb_vs_sb": ("multibeam_ncei", "singlebeam"),
    "mrar_vs_sb": ("regional_mrar", "singlebeam"),
}

VALID_RUN_LABELS = ("sample", "test100", "full")
POLICY_ENFORCE_VERSION = "ncei_policy_enforce_v0.1.0"

LAT_BAND_VALUES = list(range(-90, 90, 10))
DEPTH_BINS = [0, 200, 500, 2000, 4000, 6000, 11500]
DEPTH_BIN_LEFT_EDGES = DEPTH_BINS[:-1]
DUP_RATIO_BINS = [0.0, 0.01, 0.1, 0.5, 1.0]
N_UNIQUE_TRIPLES_BINS = [1, 10, 100, 1000, 10000, float("inf")]

# Sample mode keeps enough rows to exercise all branches without producing a
# large sidecar. The branch-specific 50/2000/5000 targets mirror the brief's
# requested small stratified sample sizes.
SAMPLE_TARGETS = {
    "sample": {"singlebeam": 5_000, "multibeam_ncei": 50, "regional_mrar": 2_000},
    "test100": {"singlebeam": 100_000, "multibeam_ncei": 5_960, "regional_mrar": 100_000},
}

REQUIRED_CELL_COLUMNS = [
    "branch",
    "cell_id",
    "lon_bin",
    "lat_bin",
    "lon_center",
    "lat_center",
    "median_depth_m",
    "n_track_cells",
    "n_unique_triples_total",
    "n_points_pass_total",
    "duplicate_ratio_cell",
    "manual_review_any",
    "manual_review_unique_triples_share",
]
OPTIONAL_CELL_COLUMNS = ["lat_band_10deg"]

OUTPUT_COLUMNS = [
    "branch",
    "cell_id",
    "lon_bin",
    "lat_bin",
    "quality_tier",
    "evidence_class",
    "validation_weight",
    "branch_role",
    "use_for_primary_validation",
    "use_for_supplementary_validation",
    "use_for_regional_experiment",
    "sensitivity_only_flag",
    "exclude_from_primary",
    "exclusion_or_review_reason",
    "matched_rule_id",
    "matched_rule_priority",
    "applied_rule_description",
    "rule_version",
    "n_unique_triples_total",
    "n_points_pass_total",
    "duplicate_ratio_cell",
    "n_track_cells",
    "manual_review_any",
    "manual_review_unique_triples_share",
    "low_evidence_flag",
    "overlap_evidence_class",
    "n_cross_branch_overlap",
    "lat_band_10deg",
    "depth_bin",
    "auv_sentry_flag",
    "source_risk_class",
]

ALLOWED_TIERS = {
    "high_confidence",
    "medium_confidence",
    "low_confidence",
    "review_or_sensitivity_only",
}

CELL_REF_NAMES = {
    "n_track_cells",
    "n_unique_triples_total",
    "n_points_pass_total",
    "duplicate_ratio_cell",
    "manual_review_any",
    "lat_band_10deg",
    "depth_bin",
    "branch",
    "in_cross_pair",
    "n_cross_branch_overlap",
}
SLICE_KEYS = {"within_branch", "cross_branch", "within_or_cross", "mb_vs_mrar", "mb_vs_sb", "mrar_vs_sb"}
SLICE_FIELDS = {
    "abs_residual_p95",
    "abs_residual_p99",
    "within_branch_abs_residual_p95",
    "cross_branch_abs_residual_p95",
    "cross_branch_abs_residual_max_p95",
    "cross_branch_abs_residual_p99",
    "rmse",
}


# ---------------------------------------------------------------------------
# Path / logging / atomic-write helpers
# ---------------------------------------------------------------------------
def suffix_for_run(run_label: str) -> str:
    return "" if run_label == "full" else f"_{run_label}"


def output_dir_for_run(run_label: str) -> Path:
    return DERIVED_DIR / f"quality_flags_1min{suffix_for_run(run_label)}"


def output_paths(run_label: str) -> dict[str, Path]:
    suffix = suffix_for_run(run_label)
    out_dir = output_dir_for_run(run_label)
    return {
        "out_dir": out_dir,
        "flags_parquet": out_dir / "cell_quality_flags_1min.parquet",
        "flags_tsv": out_dir / "cell_quality_flags_1min.tsv",
        "summary_branch": out_dir / "quality_summary_by_branch.parquet",
        "summary_lat_depth": out_dir / "quality_summary_by_lat_depth.parquet",
        "summary_rule": out_dir / "quality_summary_by_rule.parquet",
        "summary_evidence": out_dir / "quality_summary_by_evidence_class.parquet",
        "report": DOCS_DIR / f"step06b_cell_quality_flags_report{suffix}.md",
        "log": LOG_DIR / f"12_apply_quality_policy{suffix}.log",
    }


def atomic_write_parquet(df: pd.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    df.to_parquet(tmp, index=False, engine="pyarrow")
    os.replace(tmp, target)


def atomic_write_tsv(df: pd.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    os.replace(tmp, target)


def atomic_write_text(text: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)


def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("ncei_apply_quality_policy")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s")
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(levelname)-8s %(message)s"))
    logger.addHandler(ch)
    return logger


def existing_outputs(paths: dict[str, Path]) -> list[Path]:
    return [path for key, path in paths.items() if key not in {"out_dir", "log"} and path.exists()]


# ---------------------------------------------------------------------------
# Binning / sampling helpers
# ---------------------------------------------------------------------------
def compute_lat_band(lat_center: pd.Series) -> pd.Series:
    values = np.floor(pd.to_numeric(lat_center, errors="coerce").astype(float) / 10.0) * 10.0
    values = values.clip(-90, 80)
    return values.astype("Int64")


def right_open_bins(values: pd.Series, bins: Sequence[float]) -> pd.DataFrame:
    arr = pd.to_numeric(values, errors="coerce").to_numpy(dtype=np.float64)
    edges = np.asarray(bins, dtype=np.float64)
    idx = np.searchsorted(edges, arr, side="right") - 1
    idx = np.where(np.isnan(arr), -1, idx)
    idx = np.clip(idx, 0, len(edges) - 2)
    lo = np.where(np.isnan(arr), np.nan, edges[idx])
    hi = np.where(np.isnan(arr), np.nan, edges[idx + 1])
    return pd.DataFrame({"lo": lo, "hi": hi}, index=values.index)


def add_depth_bins(cells: pd.DataFrame) -> pd.DataFrame:
    out = cells.copy()
    clipped = pd.to_numeric(out["median_depth_m"], errors="coerce").clip(lower=0.0, upper=11500.0)
    bins = right_open_bins(clipped, DEPTH_BINS)
    out["depth_bin_lo"] = bins["lo"].astype("Int64")
    out["depth_bin_hi"] = bins["hi"].astype("Int64")
    out["depth_bin"] = out["depth_bin_lo"].astype("Int64")
    return out


def stratified_sample(df: pd.DataFrame, branch: str, run_label: str) -> pd.DataFrame:
    if run_label == "full" or df.empty:
        return df.reset_index(drop=True)
    target = SAMPLE_TARGETS.get(run_label, {}).get(branch, len(df))
    if len(df) <= target:
        return df.reset_index(drop=True)
    strata = ["lat_band_10deg", "depth_bin_lo"]
    base = max(1, math.ceil(target / max(1, df[strata].drop_duplicates().shape[0])))
    sampled = (
        df.sort_values(strata + ["cell_id"])
        .groupby(strata, dropna=False, group_keys=False)
        .head(base)
        .head(target)
        .reset_index(drop=True)
    )
    if len(sampled) < target:
        remaining = df.loc[~df["cell_id"].isin(sampled["cell_id"])]
        sampled = pd.concat([sampled, remaining.sort_values("cell_id").head(target - len(sampled))], ignore_index=True)
    return sampled.reset_index(drop=True)


def first_sentence(text: str) -> str:
    text = "" if pd.isna(text) else str(text).strip()
    if not text:
        return ""
    match = re.search(r"(?<=[.!?。！？])\s+", text)
    return text[: match.start()].strip() if match else text


def safe_bool_series(series: pd.Series, index: pd.Index) -> pd.Series:
    if not isinstance(series, pd.Series):
        return pd.Series(bool(series), index=index, dtype=bool)
    return series.reindex(index).fillna(False).astype(bool)


# ---------------------------------------------------------------------------
# Filter parser for applies_to_*_filter
# ---------------------------------------------------------------------------
def parse_exact_membership_filter(
    filter_text: str,
    allowed_values: Sequence[int],
    *,
    upper_inclusive: bool = True,
) -> set[int] | None:
    """Parse exact left-edge membership filters.

    Returns None for "*" (all values). For ranges, only exact members of
    `allowed_values` inside the interval are returned; range endpoints
    that are not valid bin/band left edges do not create synthetic members.

    The lat-band and depth-bin filters in the semantic lock (§1.2) use
    asymmetric interval conventions:

    * Lat-band ranges are closed on band labels: ``"-70..-50"`` →
      ``{-70, -60, -50}`` (3 bands). Use ``upper_inclusive=True``.
    * Depth-bin ranges are half-open on bin-left-edges: ``"0..200"`` →
      ``{0}`` (only the bin ``[0, 200)``), ``"500..6000"`` →
      ``{500, 2000, 4000}`` (3 bins). Use ``upper_inclusive=False``.
    """
    text = str(filter_text).strip()
    if text == "*" or text == "":
        return None
    allowed = [int(v) for v in allowed_values]
    selected: set[int] = set()
    for part in text.split(","):
        token = part.strip()
        if not token:
            continue
        if ".." in token:
            lo_s, hi_s = token.split("..", 1)
            lo = int(float(lo_s))
            hi = int(float(hi_s))
            if upper_inclusive:
                selected.update(v for v in allowed if lo <= v <= hi)
            else:
                selected.update(v for v in allowed if lo <= v < hi)
        else:
            val = int(float(token))
            if val in allowed:
                selected.add(val)
    return selected


# ---------------------------------------------------------------------------
# Restricted condition parser
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Token:
    kind: str
    value: object


TOKEN_RE = re.compile(
    r"\s*(?:(?P<NUMBER>-?\d+(?:\.\d+)?)|(?P<STRING>'[^']*'|\"[^\"]*\")|"
    r"(?P<OP>>=|<=|==|<|>)|(?P<RANGE>\.\.)|(?P<LPAREN>\()|(?P<RPAREN>\))|"
    r"(?P<LBRACK>\[)|(?P<RBRACK>\])|(?P<COMMA>,)|(?P<IDENT>[A-Za-z_][A-Za-z0-9_.]*))"
)


def tokenize(expr: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(expr):
        match = TOKEN_RE.match(expr, pos)
        if not match:
            raise ValueError(f"cannot tokenize condition near: {expr[pos:pos+40]!r}")
        pos = match.end()
        kind = match.lastgroup
        raw = match.group(kind) if kind else ""
        if kind == "NUMBER":
            value: object = float(raw) if "." in raw else int(raw)
            tokens.append(Token("NUMBER", value))
        elif kind == "STRING":
            tokens.append(Token("STRING", raw[1:-1]))
        elif kind == "IDENT":
            upper = raw.upper()
            if upper in {"AND", "OR", "NOT", "IN", "TRUE", "FALSE"}:
                tokens.append(Token(upper, upper))
            else:
                tokens.append(Token("IDENT", raw))
        elif kind:
            tokens.append(Token(kind, raw))
    tokens.append(Token("EOF", ""))
    return tokens


class ExprNode:
    def eval(self, df: pd.DataFrame, ctx: "EvalContext") -> pd.Series:
        raise NotImplementedError


class ValueNode:
    def value(self, df: pd.DataFrame, ctx: "EvalContext") -> object:
        raise NotImplementedError


@dataclass(frozen=True)
class Literal(ValueNode):
    raw: object

    def value(self, df: pd.DataFrame, ctx: "EvalContext") -> object:
        return self.raw


@dataclass(frozen=True)
class Ref(ValueNode):
    name: str

    def value(self, df: pd.DataFrame, ctx: "EvalContext") -> object:
        if self.name in CELL_REF_NAMES:
            if self.name not in df.columns:
                raise ValueError(f"condition references missing cell column {self.name!r}")
            return df[self.name]
        if self.name.startswith("slice."):
            parts = self.name.split(".")
            if len(parts) != 3 or parts[1] not in SLICE_KEYS or parts[2] not in SLICE_FIELDS:
                raise ValueError(f"invalid slice reference {self.name!r}")
            return ctx.lookup_slice(parts[1], parts[2])
        raise ValueError(f"condition references unsupported identifier {self.name!r}")


@dataclass(frozen=True)
class Compare(ExprNode):
    left: ValueNode
    op: str
    right: ValueNode

    def eval(self, df: pd.DataFrame, ctx: "EvalContext") -> pd.Series:
        left_val = self.left.value(df, ctx)
        right_val = self.right.value(df, ctx)
        index = df.index

        # Special membership-style equality for the pipe-delimited pair-label
        # sidecar: `in_cross_pair == 'mb_vs_mrar'` means "the cell appears in
        # that pair", not literal string equality against the whole list.
        if isinstance(self.left, Ref) and self.left.name == "in_cross_pair" and isinstance(right_val, str) and self.op == "==":
            return pd.Series(left_val, index=index).fillna("").astype(str).str.split("|").apply(lambda vals: right_val in vals)
        if isinstance(self.right, Ref) and self.right.name == "in_cross_pair" and isinstance(left_val, str) and self.op == "==":
            return pd.Series(right_val, index=index).fillna("").astype(str).str.split("|").apply(lambda vals: left_val in vals)

        if not isinstance(left_val, pd.Series):
            left_val = pd.Series(left_val, index=index)
        if not isinstance(right_val, pd.Series):
            right_val = pd.Series(right_val, index=index)
        left_val = left_val.reindex(index)
        right_val = right_val.reindex(index)

        if self.op == ">=":
            out = left_val >= right_val
        elif self.op == "<=":
            out = left_val <= right_val
        elif self.op == "==":
            out = left_val == right_val
        elif self.op == "<":
            out = left_val < right_val
        elif self.op == ">":
            out = left_val > right_val
        else:
            raise ValueError(f"unsupported comparison op {self.op!r}")
        return out.fillna(False).astype(bool)


@dataclass(frozen=True)
class InSet(ExprNode):
    left: ValueNode
    values: tuple[object, ...]

    def eval(self, df: pd.DataFrame, ctx: "EvalContext") -> pd.Series:
        left_val = self.left.value(df, ctx)
        if not isinstance(left_val, pd.Series):
            left_val = pd.Series(left_val, index=df.index)
        return left_val.reindex(df.index).isin(list(self.values)).fillna(False).astype(bool)


@dataclass(frozen=True)
class And(ExprNode):
    left: ExprNode
    right: ExprNode

    def eval(self, df: pd.DataFrame, ctx: "EvalContext") -> pd.Series:
        return safe_bool_series(self.left.eval(df, ctx), df.index) & safe_bool_series(self.right.eval(df, ctx), df.index)


@dataclass(frozen=True)
class Or(ExprNode):
    left: ExprNode
    right: ExprNode

    def eval(self, df: pd.DataFrame, ctx: "EvalContext") -> pd.Series:
        return safe_bool_series(self.left.eval(df, ctx), df.index) | safe_bool_series(self.right.eval(df, ctx), df.index)


@dataclass(frozen=True)
class Not(ExprNode):
    node: ExprNode

    def eval(self, df: pd.DataFrame, ctx: "EvalContext") -> pd.Series:
        return ~safe_bool_series(self.node.eval(df, ctx), df.index)


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def current(self) -> Token:
        return self.tokens[self.pos]

    def accept(self, kind: str) -> Token | None:
        if self.current().kind == kind:
            tok = self.current()
            self.pos += 1
            return tok
        return None

    def expect(self, kind: str) -> Token:
        tok = self.accept(kind)
        if tok is None:
            raise ValueError(f"expected {kind}, got {self.current().kind} ({self.current().value!r})")
        return tok

    def parse(self) -> ExprNode:
        node = self.parse_or()
        self.expect("EOF")
        return node

    def parse_or(self) -> ExprNode:
        node = self.parse_and()
        while self.accept("OR"):
            node = Or(node, self.parse_and())
        return node

    def parse_and(self) -> ExprNode:
        node = self.parse_not()
        while self.accept("AND"):
            node = And(node, self.parse_not())
        return node

    def parse_not(self) -> ExprNode:
        if self.accept("NOT"):
            return Not(self.parse_not())
        return self.parse_atom()

    def parse_atom(self) -> ExprNode:
        if self.accept("LPAREN"):
            node = self.parse_or()
            self.expect("RPAREN")
            return node
        left = self.parse_value()
        if self.accept("IN"):
            values = self.parse_in_values()
            return InSet(left, tuple(values))
        op = self.expect("OP").value
        right = self.parse_value()
        return Compare(left, str(op), right)

    def parse_in_values(self) -> list[object]:
        self.expect("LBRACK")
        first = self.parse_value()
        if self.accept("RANGE"):
            second = self.parse_value()
            self.expect("RBRACK")
            lo = first.raw if isinstance(first, Literal) else None
            hi = second.raw if isinstance(second, Literal) else None
            if not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)):
                raise ValueError("range values inside IN must be numeric literals")
            return list(range(int(lo), int(hi) + 1))
        values = [first.raw if isinstance(first, Literal) else _literal_from_ref_for_set(first)]
        while self.accept("COMMA"):
            value = self.parse_value()
            values.append(value.raw if isinstance(value, Literal) else _literal_from_ref_for_set(value))
        self.expect("RBRACK")
        return values

    def parse_value(self) -> ValueNode:
        tok = self.current()
        if tok.kind in {"NUMBER", "STRING"}:
            self.pos += 1
            return Literal(tok.value)
        if tok.kind == "TRUE":
            self.pos += 1
            return Literal(True)
        if tok.kind == "FALSE":
            self.pos += 1
            return Literal(False)
        if tok.kind == "IDENT":
            self.pos += 1
            return Ref(str(tok.value))
        raise ValueError(f"expected value, got {tok.kind} ({tok.value!r})")


def _literal_from_ref_for_set(value: ValueNode) -> object:
    # The locked grammar does not need cell refs in set literals; this helper
    # keeps failures explicit instead of silently treating refs as strings.
    raise ValueError(f"non-literal set member is unsupported: {value!r}")


def parse_condition(expr: str) -> ExprNode:
    return Parser(tokenize(expr)).parse()


# ---------------------------------------------------------------------------
# Rule model and slice lookup
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Rule:
    rule_id: str
    candidate_tier: str
    applies_to_branch: str
    lat_filter: set[int] | None
    depth_filter: set[int] | None
    recommended_weight: float
    exclude_from_primary: bool
    notes: str
    priority: int | None
    applies_as: str
    condition_canonical: str
    slice_lookup_table: str
    ast: ExprNode

    @property
    def description(self) -> str:
        return first_sentence(self.notes)


def parse_bool(value: object) -> bool:
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n", ""}:
        return False
    raise ValueError(f"cannot parse bool value {value!r}")


def load_rules(path: Path = RULES_PATH) -> tuple[list[Rule], list[Rule]]:
    if not path.exists():
        raise FileNotFoundError(f"enforced rules TSV not found: {path}")
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            rows.append(row)
    if len(rows) != 16:
        raise ValueError(f"expected 16 enforced-rule rows, got {len(rows)}")

    rules: list[Rule] = []
    for row in rows:
        tier = row["candidate_tier"].strip()
        if tier not in ALLOWED_TIERS:
            raise ValueError(f"{row['rule_id']}: invalid tier {tier!r}")
        applies_as = row["applies_as"].strip()
        priority_text = row["priority"].strip()
        priority = int(priority_text) if priority_text else None
        condition = row["condition_canonical"].strip()
        rules.append(
            Rule(
                rule_id=row["rule_id"].strip(),
                candidate_tier=tier,
                applies_to_branch=row["applies_to_branch"].strip(),
                lat_filter=parse_exact_membership_filter(row["applies_to_lat_band_filter"], LAT_BAND_VALUES),
                depth_filter=parse_exact_membership_filter(row["applies_to_depth_bin_filter"], DEPTH_BIN_LEFT_EDGES, upper_inclusive=False),
                recommended_weight=float(row["recommended_weight"]),
                exclude_from_primary=parse_bool(row["exclude_from_primary"]),
                notes=row["notes"],
                priority=priority,
                applies_as=applies_as,
                condition_canonical=condition,
                slice_lookup_table=row["slice_lookup_table"].strip(),
                ast=parse_condition(condition),
            )
        )

    first_match = [r for r in rules if r.applies_as == "first_match"]
    invariants = [r for r in rules if r.applies_as == "invariant"]
    if len(first_match) != 15 or len(invariants) != 1:
        raise ValueError(f"expected 15 first_match + 1 invariant, got {len(first_match)} + {len(invariants)}")
    priorities = [r.priority for r in first_match]
    if sorted(priorities) != list(range(1, 16)):
        raise ValueError(f"first_match priorities must be exactly 1..15, got {priorities}")
    if any(r.priority is not None for r in invariants):
        raise ValueError("invariant rules must not have priorities")
    return sorted(first_match, key=lambda r: int(r.priority or 99)), invariants


class SliceTables:
    def __init__(self, lat_depth: pd.DataFrame, source_pair: pd.DataFrame):
        self.lat_depth = lat_depth.copy()
        self.source_pair = source_pair.copy()
        self._normalize()

    def _normalize(self) -> None:
        if not self.lat_depth.empty:
            for col in ["lat_band_10deg", "depth_bin_lo", "depth_bin_hi"]:
                if col in self.lat_depth.columns:
                    self.lat_depth[col] = pd.to_numeric(self.lat_depth[col], errors="coerce").astype("Int64")
        if not self.source_pair.empty:
            for col in ["dup_bin_lo", "dup_bin_hi", "n_unique_lo", "n_unique_hi"]:
                if col in self.source_pair.columns:
                    self.source_pair[col] = pd.to_numeric(self.source_pair[col], errors="coerce")

    @staticmethod
    def load() -> "SliceTables":
        if not LAT_DEPTH_CALIBRATION.exists():
            raise FileNotFoundError(f"Step 06A by_lat_depth calibration not found: {LAT_DEPTH_CALIBRATION}")
        if not SOURCE_PAIR_CALIBRATION.exists():
            raise FileNotFoundError(f"Step 06A by_source_pair calibration not found: {SOURCE_PAIR_CALIBRATION}")
        return SliceTables(pd.read_parquet(LAT_DEPTH_CALIBRATION), pd.read_parquet(SOURCE_PAIR_CALIBRATION))

    def lookup_lat_depth(self, cells: pd.DataFrame, slice_key: str, slice_field: str) -> pd.Series:
        if self.lat_depth.empty:
            return pd.Series(np.nan, index=cells.index, dtype="float64")
        key_cols = ["branch", "lat_band_10deg", "depth_bin_lo", "depth_bin_hi"]
        missing = [col for col in key_cols if col not in self.lat_depth.columns]
        if missing:
            raise ValueError(f"by_lat_depth calibration missing join keys: {missing}")
        col = self._lat_depth_column(slice_key, slice_field)
        if col is None or col not in self.lat_depth.columns:
            return pd.Series(np.nan, index=cells.index, dtype="float64")
        lookup = self.lat_depth[key_cols + [col]].copy().rename(columns={col: "__slice_value"})
        merged = cells.reset_index(names="__idx")[ ["__idx"] + key_cols ].merge(lookup, on=key_cols, how="left")
        return merged.set_index("__idx")["__slice_value"].reindex(cells.index)

    def _lat_depth_column(self, slice_key: str, slice_field: str) -> str | None:
        if slice_key == "within_or_cross" and slice_field == "abs_residual_p95":
            return "__within_or_cross_abs_residual_p95"
        if slice_key == "within_branch" and slice_field in {"abs_residual_p95", "within_branch_abs_residual_p95"}:
            return "within_branch_residual_p95"
        if slice_key == "cross_branch" and slice_field in {"abs_residual_p95", "cross_branch_abs_residual_p95", "cross_branch_abs_residual_max_p95"}:
            for col in ("cross_branch_abs_residual_p95", "cross_branch_residual_max_p95"):
                if col in self.lat_depth.columns:
                    return col
        if slice_key == "cross_branch" and slice_field == "abs_residual_p99":
            for col in ("cross_branch_abs_residual_p99", "cross_branch_residual_max_p99", "cross_branch_residual_p99"):
                if col in self.lat_depth.columns:
                    return col
        return None

    def prepare_lat_depth_for_within_or_cross(self) -> None:
        if self.lat_depth.empty or "__within_or_cross_abs_residual_p95" in self.lat_depth.columns:
            return
        candidates = []
        if "within_branch_residual_p95" in self.lat_depth.columns:
            candidates.append(pd.to_numeric(self.lat_depth["within_branch_residual_p95"], errors="coerce"))
        for col in ("cross_branch_abs_residual_p95", "cross_branch_residual_max_p95"):
            if col in self.lat_depth.columns:
                candidates.append(pd.to_numeric(self.lat_depth[col], errors="coerce"))
                break
        if not candidates:
            self.lat_depth["__within_or_cross_abs_residual_p95"] = np.nan
        else:
            self.lat_depth["__within_or_cross_abs_residual_p95"] = pd.concat(candidates, axis=1).min(axis=1, skipna=True)

    def lookup_source_pair(self, cells: pd.DataFrame, slice_key: str, slice_field: str) -> pd.Series:
        if slice_key not in PAIR_LABELS:
            return pd.Series(np.nan, index=cells.index, dtype="float64")
        if self.source_pair.empty:
            return pd.Series(np.nan, index=cells.index, dtype="float64")
        col = self._source_pair_column(slice_field)
        if col is None or col not in self.source_pair.columns:
            return pd.Series(np.nan, index=cells.index, dtype="float64")

        work = cells[["duplicate_ratio_cell", "n_unique_triples_total", "in_cross_pair"]].copy()
        dup_bins = right_open_bins(pd.to_numeric(work["duplicate_ratio_cell"], errors="coerce").clip(0.0, 1.0), DUP_RATIO_BINS)
        uniq_bins = right_open_bins(pd.to_numeric(work["n_unique_triples_total"], errors="coerce").clip(lower=1), N_UNIQUE_TRIPLES_BINS)
        work["dup_bin_lo"] = dup_bins["lo"]
        work["dup_bin_hi"] = dup_bins["hi"]
        work["n_unique_lo"] = uniq_bins["lo"]
        work["n_unique_hi"] = uniq_bins["hi"]
        work["pair_label"] = slice_key
        work["__has_pair"] = work["in_cross_pair"].fillna("").astype(str).str.split("|").apply(lambda vals: slice_key in vals)

        key_cols = ["pair_label", "dup_bin_lo", "dup_bin_hi", "n_unique_lo", "n_unique_hi"]
        missing = [key for key in key_cols if key not in self.source_pair.columns]
        if missing:
            raise ValueError(f"by_source_pair calibration missing join keys: {missing}")
        lookup = self.source_pair[key_cols + [col]].copy().rename(columns={col: "__slice_value"})
        merged = work.reset_index(names="__idx").merge(lookup, on=key_cols, how="left")
        out = merged.set_index("__idx")["__slice_value"].reindex(cells.index)
        out = out.where(work["__has_pair"], np.nan)
        return out

    @staticmethod
    def _source_pair_column(slice_field: str) -> str | None:
        if slice_field in {"abs_residual_p95", "cross_branch_abs_residual_p95", "cross_branch_abs_residual_max_p95"}:
            return "abs_residual_p95"
        if slice_field in {"abs_residual_p99", "cross_branch_abs_residual_p99"}:
            return "abs_residual_p99"
        if slice_field == "rmse":
            return "rmse"
        return None


class EvalContext:
    def __init__(self, cells: pd.DataFrame, tables: SliceTables, rule: Rule):
        self.cells = cells
        self.tables = tables
        self.rule = rule
        self.cache: dict[tuple[str, str, str], pd.Series] = {}
        self.tables.prepare_lat_depth_for_within_or_cross()

    def lookup_slice(self, slice_key: str, slice_field: str) -> pd.Series:
        cache_key = (self.rule.slice_lookup_table, slice_key, slice_field)
        if cache_key in self.cache:
            return self.cache[cache_key]
        if self.rule.slice_lookup_table == "none":
            out = pd.Series(np.nan, index=self.cells.index, dtype="float64")
        elif self.rule.slice_lookup_table == "by_lat_depth":
            out = self.tables.lookup_lat_depth(self.cells, slice_key, slice_field)
        elif self.rule.slice_lookup_table == "by_source_pair":
            out = self.tables.lookup_source_pair(self.cells, slice_key, slice_field)
        else:
            raise ValueError(f"unsupported slice_lookup_table {self.rule.slice_lookup_table!r}")
        self.cache[cache_key] = out
        return out


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------
def read_required_parquet(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"required input not found: {path}")
    if columns is None:
        return pd.read_parquet(path)
    schema_names = set(pq.read_schema(path).names)
    read_cols = [col for col in columns if col in schema_names]
    missing = [col for col in columns if col not in schema_names]
    if missing:
        raise ValueError(f"{path} missing required columns: {missing}")
    return pd.read_parquet(path, columns=read_cols)


def read_branch_cells(branch: str, run_label: str, logger: logging.Logger) -> pd.DataFrame:
    path = BRANCH_CELL_DIRS[branch]
    if not path.exists():
        raise FileNotFoundError(f"Step 04B cells dataset not found for {branch}: {path}")
    dataset = ds.dataset(str(path), format="parquet", partitioning="hive")
    names = set(dataset.schema.names)
    missing = [col for col in REQUIRED_CELL_COLUMNS if col not in names]
    if missing:
        raise ValueError(f"{path} missing Step 04B columns: {missing}")
    columns = [col for col in REQUIRED_CELL_COLUMNS + OPTIONAL_CELL_COLUMNS if col in names]
    df = dataset.to_table(columns=columns).to_pandas()
    if "lat_band_10deg" not in df.columns:
        df["lat_band_10deg"] = compute_lat_band(df["lat_center"])
    df["branch"] = df["branch"].astype(str)
    got = set(df["branch"].dropna().unique().tolist())
    if got != {branch}:
        raise ValueError(f"{branch}: hive read returned unexpected branch values: {sorted(got)}")
    df = add_depth_bins(df)
    df["manual_review_any"] = df["manual_review_any"].where(df["manual_review_any"].notna(), False).astype(bool)
    df["manual_review_unique_triples_share"] = pd.to_numeric(df["manual_review_unique_triples_share"], errors="coerce").fillna(0.0)
    for col in ["lon_bin", "lat_bin", "n_unique_triples_total", "n_points_pass_total", "n_track_cells"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")
    df["duplicate_ratio_cell"] = pd.to_numeric(df["duplicate_ratio_cell"], errors="coerce")
    full_count = len(df)
    if run_label == "full" and full_count != EXPECTED_FULL_ROWS[branch]:
        raise ValueError(f"{branch}: expected {EXPECTED_FULL_ROWS[branch]:,} full cells, got {full_count:,}")
    if run_label != "full" and full_count != EXPECTED_FULL_ROWS[branch]:
        logger.warning("%s: expected full row count %s but source has %s (sample mode warning only)", branch, EXPECTED_FULL_ROWS[branch], full_count)
    sampled = stratified_sample(df, branch, run_label)
    logger.info("%s: loaded %d Step 04B cells (%d after %s sampling)", branch, full_count, len(sampled), run_label)
    return sampled.reset_index(drop=True)


def read_cross_overlap_index(path: Path = CROSS_OVERLAP_CELLS) -> pd.DataFrame:
    cols = ["pair_label", "left_branch", "right_branch", "cell_id"]
    cross = read_required_parquet(path, cols)
    for col in cols:
        cross[col] = cross[col].astype(str)
    return cross


def annotate_cross_overlap(cells: pd.DataFrame, cross: pd.DataFrame) -> pd.DataFrame:
    if cross.empty:
        cells = cells.copy()
        cells["n_cross_branch_overlap"] = 0
        cells["in_cross_pair"] = ""
        return cells
    frames: list[pd.DataFrame] = []
    left = cross[["pair_label", "left_branch", "cell_id"]].rename(columns={"left_branch": "branch"})
    right = cross[["pair_label", "right_branch", "cell_id"]].rename(columns={"right_branch": "branch"})
    frames.extend([left, right])
    long = pd.concat(frames, ignore_index=True)
    grouped = (
        long.groupby(["branch", "cell_id"], sort=False)
        .agg(
            n_cross_branch_overlap=("pair_label", "size"),
            in_cross_pair=("pair_label", lambda s: "|".join(sorted(set(map(str, s))))),
        )
        .reset_index()
    )
    out = cells.merge(grouped, on=["branch", "cell_id"], how="left")
    out["n_cross_branch_overlap"] = pd.to_numeric(out["n_cross_branch_overlap"], errors="coerce").fillna(0).astype("int64")
    out["in_cross_pair"] = out["in_cross_pair"].fillna("").astype(str)
    return out


# ---------------------------------------------------------------------------
# Rule application and derived policy fields
# ---------------------------------------------------------------------------
def rule_filter_mask(cells: pd.DataFrame, rule: Rule) -> pd.Series:
    mask = pd.Series(True, index=cells.index, dtype=bool)
    if rule.applies_to_branch != "*":
        mask &= cells["branch"].astype(str).eq(rule.applies_to_branch)
    if rule.lat_filter is not None:
        mask &= cells["lat_band_10deg"].isin(rule.lat_filter)
    if rule.depth_filter is not None:
        mask &= cells["depth_bin"].isin(rule.depth_filter)
    return mask.fillna(False).astype(bool)


def apply_first_match_rules(cells: pd.DataFrame, rules: list[Rule], tables: SliceTables, logger: logging.Logger) -> pd.DataFrame:
    out = cells.copy()
    out["matched_rule_id"] = pd.NA
    out["matched_rule_priority"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    out["quality_tier"] = pd.NA
    out["validation_weight"] = np.nan
    out["exclude_from_primary"] = pd.NA
    out["applied_rule_description"] = ""

    matched = pd.Series(False, index=out.index, dtype=bool)
    for rule in rules:
        ctx = EvalContext(out, tables, rule)
        mask_filter = rule_filter_mask(out, rule)
        if not mask_filter.any():
            logger.info("Rule %02s %-35s matched 0 cells (filter empty)", rule.priority, rule.rule_id)
            continue
        mask_cond = safe_bool_series(rule.ast.eval(out, ctx), out.index)
        mask = (~matched) & mask_filter & mask_cond
        n = int(mask.sum())
        if n:
            out.loc[mask, "matched_rule_id"] = rule.rule_id
            out.loc[mask, "matched_rule_priority"] = int(rule.priority or 99)
            out.loc[mask, "quality_tier"] = rule.candidate_tier
            out.loc[mask, "validation_weight"] = rule.recommended_weight
            out.loc[mask, "exclude_from_primary"] = rule.exclude_from_primary
            out.loc[mask, "applied_rule_description"] = rule.description
            matched |= mask
        logger.info("Rule %02s %-35s matched %d cells", rule.priority, rule.rule_id, n)

    default_mask = ~matched
    if default_mask.any():
        out.loc[default_mask, "matched_rule_id"] = "default_unmatched"
        out.loc[default_mask, "matched_rule_priority"] = 99
        out.loc[default_mask, "quality_tier"] = "low_confidence"
        out.loc[default_mask, "validation_weight"] = 0.25
        out.loc[default_mask, "exclude_from_primary"] = False
        out.loc[default_mask, "applied_rule_description"] = "No enforced rule matched; default low_confidence safeguard."
    logger.info("Default unmatched safeguard assigned %d cells", int(default_mask.sum()))
    return out


def add_policy_sidecars(cells: pd.DataFrame) -> pd.DataFrame:
    out = cells.copy()
    within = pd.to_numeric(out["n_track_cells"], errors="coerce").fillna(0) >= 2
    cross = pd.to_numeric(out["n_cross_branch_overlap"], errors="coerce").fillna(0) >= 1
    out["evidence_class"] = np.select(
        [within & cross, within, cross],
        ["both", "within", "cross"],
        default="none",
    )
    out["low_evidence_flag"] = out["evidence_class"].eq("none")
    out["overlap_evidence_class"] = out["evidence_class"]

    out["branch_role"] = out["branch"].map(BRANCH_ROLE).fillna("")
    out["sensitivity_only_flag"] = out["quality_tier"].eq("review_or_sensitivity_only")
    out["auv_sentry_flag"] = out["matched_rule_id"].eq("mb_v0_highdup_sentry_downweight")

    out["source_risk_class"] = ""
    out.loc[out["auv_sentry_flag"], "source_risk_class"] = "auv_sentry_highdup"
    out.loc[out["matched_rule_id"].eq("any_v0_dup_heavy_downweight") & ~out["auv_sentry_flag"], "source_risk_class"] = "high_dup_unsupported"
    out.loc[out["low_evidence_flag"] & out["source_risk_class"].eq(""), "source_risk_class"] = "low_evidence"

    usable_tier_primary = out["quality_tier"].isin(["high_confidence", "medium_confidence"])
    usable_tier_supp = out["quality_tier"].isin(["high_confidence", "medium_confidence", "low_confidence"])
    out["use_for_primary_validation"] = out["branch_role"].ne("regional_experiment") & (~out["exclude_from_primary"].astype(bool)) & usable_tier_primary
    out["use_for_supplementary_validation"] = (~out["exclude_from_primary"].astype(bool)) & usable_tier_supp
    # Regional experiments are a separate analysis stream: all M.rar cells with
    # nonzero policy weight remain eligible for that stream even when their tier
    # is review_or_sensitivity_only. Primary-validation exclusion is controlled
    # independently by exclude_from_primary.
    out["use_for_regional_experiment"] = out["branch_role"].eq("regional_experiment") & (pd.to_numeric(out["validation_weight"], errors="coerce") > 0)

    out["exclusion_or_review_reason"] = ""
    excl = out["exclude_from_primary"].astype(bool)
    review = out["quality_tier"].eq("review_or_sensitivity_only")
    out.loc[excl & review, "exclusion_or_review_reason"] = out.loc[excl & review, "matched_rule_id"].astype(str) + ":sensitivity_only"
    out.loc[excl & ~review, "exclusion_or_review_reason"] = out.loc[excl & ~review, "matched_rule_id"].astype(str) + ":excluded_from_primary"
    out.loc[~excl & review, "exclusion_or_review_reason"] = out.loc[~excl & review, "matched_rule_id"].astype(str) + ":review_only"

    out["rule_version"] = POLICY_ENFORCE_VERSION
    return out


def enforce_output_schema(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in OUTPUT_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    out = out[OUTPUT_COLUMNS]
    int_cols = [
        "lon_bin",
        "lat_bin",
        "matched_rule_priority",
        "n_unique_triples_total",
        "n_points_pass_total",
        "n_track_cells",
        "n_cross_branch_overlap",
        "lat_band_10deg",
        "depth_bin",
    ]
    for col in int_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype("int64")
    bool_cols = [
        "use_for_primary_validation",
        "use_for_supplementary_validation",
        "use_for_regional_experiment",
        "sensitivity_only_flag",
        "exclude_from_primary",
        "manual_review_any",
        "low_evidence_flag",
        "auv_sentry_flag",
    ]
    for col in bool_cols:
        # Coerce to bool without triggering pandas 2.x silent-downcasting
        # FutureWarning. Mapping via .map(bool) on object/nullable columns
        # yields a plain Python-bool object series, then astype(bool) lands
        # at the final numpy bool dtype.
        series = out[col]
        if series.dtype == bool:
            continue
        out[col] = series.where(series.notna(), False).astype(bool)
    float_cols = ["validation_weight", "duplicate_ratio_cell", "manual_review_unique_triples_share"]
    for col in float_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    str_cols = [col for col in OUTPUT_COLUMNS if col not in int_cols + bool_cols + float_cols]
    for col in str_cols:
        out[col] = out[col].fillna("").astype(str)
    return out


# ---------------------------------------------------------------------------
# Invariants, summaries, report
# ---------------------------------------------------------------------------
def validate_invariants(flags: pd.DataFrame, first_match_rules: list[Rule], invariant_rules: list[Rule], logger: logging.Logger) -> list[str]:
    lines: list[str] = []
    manual_only_first_match = [
        r.rule_id for r in first_match_rules if r.condition_canonical.strip().upper() in {"MANUAL_REVIEW_ANY == TRUE", "MANUAL_REVIEW_ANY==TRUE"}
    ]
    if manual_only_first_match:
        raise AssertionError(f"manual_review-only first-match rules are forbidden: {manual_only_first_match}")
    lines.append("PASS: no manual_review_any-only first_match rule can exclude or upgrade cells")
    logger.info(lines[-1])

    invariant_ids = [r.rule_id for r in invariant_rules]
    if invariant_ids != ["manual_review_not_exclusion"]:
        raise AssertionError(f"expected only manual_review_not_exclusion invariant, got {invariant_ids}")
    lines.append("PASS: manual_review_not_exclusion is invariant-only and not used for tier assignment")
    logger.info(lines[-1])

    zero_weight = int((pd.to_numeric(flags["validation_weight"], errors="coerce") == 0).sum())
    if zero_weight:
        logger.warning("Invariant warning: %d cells have validation_weight == 0 (not raised per brief allowance)", zero_weight)
        lines.append(f"WARN: {zero_weight} cells have validation_weight == 0")
    else:
        lines.append("PASS: no cells have validation_weight == 0")
        logger.info(lines[-1])

    mrar = flags[flags["branch"] == "regional_mrar"]
    if not mrar.empty:
        share_excluded = float(mrar["exclude_from_primary"].mean())
        if share_excluded < 0.99:
            raise AssertionError(f"regional_mrar exclude_from_primary share {share_excluded:.4f} < 0.99")
        lines.append(f"PASS: regional_mrar exclude_from_primary share = {share_excluded:.4f} (>=0.99)")
        logger.info(lines[-1])

    sentry = flags[flags["matched_rule_id"] == "mb_v0_highdup_sentry_downweight"]
    if not sentry.empty:
        ok = sentry["auv_sentry_flag"].all() and sentry["source_risk_class"].eq("auv_sentry_highdup").all()
        if not bool(ok):
            raise AssertionError("AUV Sentry rule matches without required auv_sentry_flag/source_risk_class")
    lines.append(f"PASS: AUV Sentry rule sidecars correct (matched cells={len(sentry)})")
    logger.info(lines[-1])
    return lines


def build_summaries(flags: pd.DataFrame) -> dict[str, pd.DataFrame]:
    by_branch = (
        flags.groupby(["branch", "quality_tier", "branch_role", "use_for_primary_validation", "use_for_supplementary_validation", "use_for_regional_experiment"], dropna=False)
        .agg(
            n_cells=("cell_id", "size"),
            mean_weight=("validation_weight", "mean"),
            n_auv_sentry=("auv_sentry_flag", "sum"),
            n_low_evidence=("low_evidence_flag", "sum"),
        )
        .reset_index()
    )
    by_lat_depth = (
        flags.groupby(["branch", "lat_band_10deg", "depth_bin", "quality_tier"], dropna=False)
        .agg(n_cells=("cell_id", "size"), mean_weight=("validation_weight", "mean"))
        .reset_index()
        .sort_values(["branch", "lat_band_10deg", "depth_bin", "quality_tier"])
    )
    by_rule = (
        flags.groupby(["matched_rule_priority", "matched_rule_id", "quality_tier", "exclude_from_primary"], dropna=False)
        .agg(n_cells=("cell_id", "size"), mean_weight=("validation_weight", "mean"), n_auv_sentry=("auv_sentry_flag", "sum"))
        .reset_index()
        .sort_values(["matched_rule_priority", "matched_rule_id"])
    )
    by_evidence = (
        flags.groupby(["branch", "evidence_class", "quality_tier"], dropna=False)
        .agg(n_cells=("cell_id", "size"), mean_weight=("validation_weight", "mean"))
        .reset_index()
        .sort_values(["branch", "evidence_class", "quality_tier"])
    )
    return {
        "summary_branch": by_branch,
        "summary_lat_depth": by_lat_depth,
        "summary_rule": by_rule,
        "summary_evidence": by_evidence,
    }


def markdown_table(df: pd.DataFrame, max_rows: int = 40) -> list[str]:
    if df.empty:
        return ["_None_", ""]
    preview = df.head(max_rows).copy()
    cols = list(preview.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in preview.iterrows():
        vals: list[str] = []
        for col in cols:
            val = row[col]
            if isinstance(val, (float, np.floating)):
                vals.append(f"{val:.4f}" if np.isfinite(val) else "")
            elif pd.isna(val):
                vals.append("")
            else:
                vals.append(str(val))
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")
    return lines


def make_report(
    *,
    run_label: str,
    elapsed_s: float,
    flags: pd.DataFrame,
    summaries: dict[str, pd.DataFrame],
    invariant_lines: list[str],
    paths: dict[str, Path],
) -> str:
    lines: list[str] = []
    lines.append("# NCEI Step 06B — Cell Quality Flags Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Run label: `{run_label}`")
    lines.append(f"Policy enforce version: `{POLICY_ENFORCE_VERSION}`")
    lines.append(f"Elapsed: {elapsed_s:.1f}s")
    lines.append("")
    lines.append("This report is generated at runtime by `ncei/code/12_apply_quality_policy.py`. The script writes a sidecar quality manifest and does not mutate Step 04B cells.")
    if run_label != "full":
        lines.append("")
        lines.append("> Sample/test100 note: row counts and distributions reflect a stratified subset of each branch, not the full production population.")
    lines.append("")

    lines.append("## 1. Row counts")
    lines.append("")
    row_counts = flags.groupby("branch").size().reset_index(name="n_rows")
    lines.extend(markdown_table(row_counts))

    lines.append("## 2. Rule match distribution")
    lines.append("")
    lines.extend(markdown_table(summaries["summary_rule"], max_rows=60))

    lines.append("## 3. Per-branch tier/use distribution")
    lines.append("")
    lines.extend(markdown_table(summaries["summary_branch"], max_rows=80))

    lines.append("## 4. Evidence-class distribution")
    lines.append("")
    lines.extend(markdown_table(summaries["summary_evidence"], max_rows=80))

    lines.append("## 5. Invariant checks")
    lines.append("")
    for item in invariant_lines:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## 6. Spot checks")
    lines.append("")
    spot_rows = []
    for branch in BRANCHES:
        sub = flags[flags["branch"] == branch]
        if not sub.empty:
            row = sub.iloc[0]
            spot_rows.append({"branch": branch, "cell_id": row["cell_id"], "rule_id": row["matched_rule_id"], "weight": row["validation_weight"]})
    lines.extend(markdown_table(pd.DataFrame(spot_rows)))

    lines.append("## 7. Output paths")
    lines.append("")
    out_rows = [
        {"kind": key, "path": str(path.relative_to(REPO_ROOT))}
        for key, path in paths.items()
        if key not in {"out_dir", "log"}
    ]
    lines.extend(markdown_table(pd.DataFrame(out_rows), max_rows=20))

    lines.append("## 8. Cross-links")
    lines.append("")
    lines.append("- Spec: `.trellis/spec/backend/pipeline-design-decisions.md` §13 (data layers) / §14 (branch labels) / §15 (Step 05B cross-branch overlap) / §16 (Step 06 prerequisites) / §17 (Step 06A quality policy calibration).")
    lines.append("- Enforced rules TSV: `.trellis/tasks/05-11-singlebeam-integration/research/quality_policy_enforced_rules.tsv` (18 cols × 16 rows; this script's only rule source).")
    lines.append("- Semantic lock report: `ncei/docs/step06b_semantic_lock_report.md` (Step 06B implementation contract — §1.2 filter grammar, §1.3 invariant rule, §1.4 AUV Sentry handling).")
    lines.append("- Predecessor (Step 06A): `ncei/code/11_quality_policy_calibration_audit.py` + `ncei/derived/quality_policy_calibration_1min/`.")
    lines.append("")
    return "\n".join(lines)


def tsv_subset(flags: pd.DataFrame, run_label: str) -> pd.DataFrame:
    if run_label != "full":
        return flags
    return flags.sort_values(["branch", "lat_band_10deg", "depth_bin", "cell_id"]).groupby("branch", group_keys=False).head(1000)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Step 06B — apply enforced quality-policy rules to NCEI Step 04B branch cells. "
            "Run from repo root (/mnt/data2/00-Data/ship)."
        )
    )
    parser.add_argument("--run-label", choices=VALID_RUN_LABELS, default="sample")
    parser.add_argument("--confirm-full", action="store_true", help="Required when --run-label=full")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing Step 06B outputs")
    args = parser.parse_args(argv)

    paths = output_paths(args.run_label)
    logger = setup_logging(paths["log"])
    t0 = datetime.now()

    logger.info("=" * 60)
    logger.info("12_apply_quality_policy.py START")
    logger.info("Args: %s", vars(args))
    logger.info("Policy enforce version: %s", POLICY_ENFORCE_VERSION)

    if args.run_label == "full" and not args.confirm_full:
        logger.error("ABORTED: --run-label=full requires --confirm-full")
        return 2
    if Path.cwd().resolve() != REPO_ROOT:
        logger.warning("Expected to run from repo root %s; current cwd is %s", REPO_ROOT, Path.cwd().resolve())

    if not args.overwrite:
        exists = existing_outputs(paths)
        if exists:
            logger.error("ABORTED: outputs exist; use --overwrite. Existing: %s", exists)
            return 2

    try:
        first_match_rules, invariant_rules = load_rules(RULES_PATH)
        logger.info("Loaded %d first_match rules + %d invariant rules from %s", len(first_match_rules), len(invariant_rules), RULES_PATH)
        tables = SliceTables.load()
        cross = read_cross_overlap_index(CROSS_OVERLAP_CELLS)
        logger.info("Loaded %d Step 05B cross-overlap rows", len(cross))

        branch_frames: list[pd.DataFrame] = []
        for branch in BRANCHES:
            cells = read_branch_cells(branch, args.run_label, logger)
            cells = annotate_cross_overlap(cells, cross)
            flagged = apply_first_match_rules(cells, first_match_rules, tables, logger)
            flagged = add_policy_sidecars(flagged)
            flagged = enforce_output_schema(flagged)
            branch_frames.append(flagged)
            spot = flagged.iloc[0] if not flagged.empty else None
            if spot is not None:
                logger.info("Spot-check %s: cell_id=%s rule=%s weight=%.3f", branch, spot["cell_id"], spot["matched_rule_id"], spot["validation_weight"])

        flags = pd.concat(branch_frames, ignore_index=True, copy=False) if branch_frames else pd.DataFrame(columns=OUTPUT_COLUMNS)
        flags = enforce_output_schema(flags)
        invariant_lines = validate_invariants(flags, first_match_rules, invariant_rules, logger)
        summaries = build_summaries(flags)

        elapsed_s = (datetime.now() - t0).total_seconds()
        report_text = make_report(run_label=args.run_label, elapsed_s=elapsed_s, flags=flags, summaries=summaries, invariant_lines=invariant_lines, paths=paths)

        atomic_write_parquet(flags, paths["flags_parquet"])
        atomic_write_tsv(tsv_subset(flags, args.run_label), paths["flags_tsv"])
        atomic_write_parquet(summaries["summary_branch"], paths["summary_branch"])
        atomic_write_parquet(summaries["summary_lat_depth"], paths["summary_lat_depth"])
        atomic_write_parquet(summaries["summary_rule"], paths["summary_rule"])
        atomic_write_parquet(summaries["summary_evidence"], paths["summary_evidence"])
        atomic_write_text(report_text, paths["report"])

        logger.info("Wrote %s (%d rows)", paths["flags_parquet"], len(flags))
        logger.info("Wrote %s (%d rows)", paths["flags_tsv"], len(tsv_subset(flags, args.run_label)))
        logger.info("Wrote summary parquets under %s", paths["out_dir"])
        logger.info("Wrote %s", paths["report"])
        logger.info("Elapsed: %.1fs", elapsed_s)
        logger.info("12_apply_quality_policy.py DONE")

        print(f"Cell quality flags: {paths['flags_parquet']} ({len(flags):,} rows)")
        print(f"Rule summary:       {paths['summary_rule']}")
        print(f"Report:             {paths['report']}")
        return 0

    except Exception as exc:  # noqa: BLE001 - pipeline top-level guard
        logger.exception("ABORTED with error: %r", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

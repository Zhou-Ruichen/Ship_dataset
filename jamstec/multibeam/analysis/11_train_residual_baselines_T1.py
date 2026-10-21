#!/usr/bin/env python3
# pyright: reportReturnType=false, reportAttributeAccessIssue=false, reportOperatorIssue=false, reportArgumentType=false, reportCallIssue=false

import argparse
import os
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd


HAS_SKLEARN = False
HAS_XGBOOST = False
HAS_LIGHTGBM = False
LinearRegression = None
Ridge = None
RandomForestRegressor = None
StandardScaler = None
xgb = None
lgb = None
try:
    from sklearn.linear_model import LinearRegression, Ridge
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.preprocessing import StandardScaler
    HAS_SKLEARN = True
except ImportError:
    pass
try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    pass
try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    pass


PROJECT = Path(__file__).resolve().parent.parent
SPLIT_DIR = PROJECT / "derived" / "ship_supervised_residual_T1" / "splits" / "block025_stratified_seed42"
OUTPUT_DIR = PROJECT / "derived" / "ship_supervised_residual_T1" / "baselines_block025"
MODELS_DIR = OUTPUT_DIR / "models"

TARGET_COL = "target_residual_SWOT_T1"
BASE_MODEL = "no_correction"
GLOBAL_BIAS_MODEL = "global_bias_correction"
BIN_BIAS_MODEL = "swot_pred_depth_bin_bias_correction"
LINEAR_MODEL = "linear_regression"
RIDGE_MODEL = "ridge_regression"
RF_MODEL = "random_forest_regressor"
BOOST_MODEL = "xgboost_or_lightgbm"

FEATURE_SETS = {
    "swot_only_inference": {
        "label": "A",
        "numeric": ["lon_center", "lat_center", "SWOT_T1_elev", "SWOT_T1_depth"],
        "categorical": ["SWOT_T1_pred_depth_bin"],
        "allow_bin_bias": True,
    },
    "global_product_fusion_diagnostic": {
        "label": "B",
        "numeric": ["lon_center", "lat_center", "SWOT_T1_elev", "ETOPO_2022_elev", "SRTM15_V2.7_elev", "TOPO_25.1_elev", "GEBCO_2024_elev", "SDUST_2023_elev"],
        "categorical": [],
        "allow_bin_bias": False,
    },
    "oracle_ship_quality_diagnostic": {
        "label": "C",
        "numeric": ["lon_center", "lat_center", "SWOT_T1_elev", "SWOT_T1_depth", "n_points_total", "n_file_cells", "n_cruises_guess"],
        "categorical": ["SWOT_T1_pred_depth_bin", "quality_tier"],
        "allow_bin_bias": True,
    },
}

OUTPUT_FILES = [
    "residual_baseline_metrics.tsv",
    "residual_baseline_metrics_by_depth_bin.tsv",
    "residual_baseline_metrics_by_quality_tier.tsv",
    "residual_baseline_predictions_test.parquet",
    "residual_baseline_predictions_val.parquet",
    "residual_baseline_report.md",
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


def assign_pred_depth_bin(swot_depth: pd.Series) -> pd.Categorical:
    return pd.cut(
        swot_depth,
        bins=[-np.inf, 4000, 5000, 6000, 7000, np.inf],
        labels=["<4000", "4000–5000", "5000–6000", "6000–7000", ">7000"],
        right=False,
    )


def check_existing(overwrite: bool) -> bool:
    existing = [OUTPUT_DIR / name for name in OUTPUT_FILES if (OUTPUT_DIR / name).exists()]
    if existing and not overwrite:
        print(f"输出已存在，跳过。使用 --overwrite 重新生成：{OUTPUT_DIR}")
        return True
    return False


def load_splits() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    paths = {
        "train": SPLIT_DIR / "ship_residual_dataset_T1_train.parquet",
        "val": SPLIT_DIR / "ship_residual_dataset_T1_val.parquet",
        "test": SPLIT_DIR / "ship_residual_dataset_T1_test.parquet",
    }
    missing_paths = [str(path) for path in paths.values() if not path.exists()]
    if missing_paths:
        raise FileNotFoundError("Missing split parquet files: " + ", ".join(missing_paths))
    train = pd.read_parquet(paths["train"]).copy()
    val = pd.read_parquet(paths["val"]).copy()
    test = pd.read_parquet(paths["test"]).copy()
    total = len(train) + len(val) + len(test)
    if total != 8121:
        raise ValueError(f"Expected total cells = 8121, got {total}")
    required = ["cell_id", "lon_center", "lat_center", "ship_elev", "SWOT_T1_elev", "depth_bin", "quality_tier", TARGET_COL]
    for name, df in [("train", train), ("val", val), ("test", test)]:
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"{name} split missing required columns: {missing}")
        df["SWOT_T1_depth"] = -df["SWOT_T1_elev"]
        df["SWOT_T1_pred_depth_bin"] = assign_pred_depth_bin(df["SWOT_T1_depth"])
    return train, val, test


def one_hot_from_train(train_s: pd.Series, s: pd.Series, prefix: str) -> tuple[pd.DataFrame, list[str]]:
    cats = [str(x) for x in pd.Series(train_s).dropna().astype(str).unique().tolist()]
    cats = sorted(cats)
    out = pd.DataFrame(index=s.index)
    vals = s.astype(str)
    for cat in cats:
        out[f"{prefix}_{cat}"] = (vals == cat).astype(np.float64)
    return out, cats


def prepare_feature_set(train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame, feature_set: str) -> dict:
    spec = FEATURE_SETS[feature_set]
    numeric_cols = spec["numeric"]
    categorical_cols = spec["categorical"]
    required = list(numeric_cols) + list(categorical_cols)
    for name, df in [("train", train), ("val", val), ("test", test)]:
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"{feature_set} {name} missing feature columns: {missing}")

    frames = {}
    categories = {}
    for name, df in [("train", train), ("val", val), ("test", test)]:
        parts = [df[numeric_cols].apply(pd.to_numeric, errors="coerce").astype(np.float64).reset_index(drop=True)]
        for col in categorical_cols:
            if name == "train":
                oh, cats = one_hot_from_train(train[col], df[col], col)
                categories[col] = cats
            else:
                oh = pd.DataFrame(index=df.index)
                vals = df[col].astype(str)
                for cat in categories[col]:
                    oh[f"{col}_{cat}"] = (vals == cat).astype(np.float64)
            parts.append(oh.reset_index(drop=True))
        mat = pd.concat(parts, axis=1)
        if mat.isna().any().any():
            bad = mat.columns[mat.isna().any()].tolist()
            raise ValueError(f"{feature_set} {name} has NaN in feature columns: {bad}")
        frames[name] = mat
    return {
        "X_train": frames["train"].to_numpy(dtype=np.float64),
        "X_val": frames["val"].to_numpy(dtype=np.float64),
        "X_test": frames["test"].to_numpy(dtype=np.float64),
        "feature_names": frames["train"].columns.tolist(),
        "categories": categories,
    }


def compute_metrics(y_true, y_pred, n) -> dict:
    error = y_pred - y_true
    return {
        "n": n,
        "bias": float(np.mean(error)),
        "MAE": float(np.mean(np.abs(error))),
        "RMSE": float(np.sqrt(np.mean(error**2))),
        "STD": float(np.std(error, ddof=1)),
        "median_error": float(np.median(error)),
        "MAD": float(np.median(np.abs(error))),
        "p95_abs_error": float(np.percentile(np.abs(error), 95)),
        "correlation": float(np.corrcoef(y_pred, y_true)[0, 1]) if n >= 2 else np.nan,
    }


def safe_compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    n = int(mask.sum())
    if n == 0:
        return {"n": 0, "bias": np.nan, "MAE": np.nan, "RMSE": np.nan, "STD": np.nan, "median_error": np.nan, "MAD": np.nan, "p95_abs_error": np.nan, "correlation": np.nan}
    if n == 1:
        error = y_pred[mask] - y_true[mask]
        return {"n": 1, "bias": float(error[0]), "MAE": float(abs(error[0])), "RMSE": float(abs(error[0])), "STD": 0.0, "median_error": float(error[0]), "MAD": float(abs(error[0])), "p95_abs_error": float(abs(error[0])), "correlation": np.nan}
    return compute_metrics(y_true[mask], y_pred[mask], n)


def evaluate_corrected(df: pd.DataFrame, pred_residual: np.ndarray) -> dict:
    corrected = df["SWOT_T1_elev"].to_numpy(dtype=np.float64) + pred_residual
    ship = df["ship_elev"].to_numpy(dtype=np.float64)
    return safe_compute_metrics(ship, corrected)


def val_rmse(df: pd.DataFrame, pred_residual: np.ndarray) -> float:
    return float(evaluate_corrected(df, pred_residual)["RMSE"])


def save_pickle(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        pickle.dump(obj, f)
    os.replace(tmp, path)


def fit_bin_bias(train: pd.DataFrame) -> dict:
    global_mean = float(train[TARGET_COL].mean())
    means = train.groupby("SWOT_T1_pred_depth_bin", observed=False)[TARGET_COL].mean().dropna()
    return {"global_mean": global_mean, "bin_means": {str(k): float(v) for k, v in means.items()}}


def predict_bin_bias(model: dict, df: pd.DataFrame) -> np.ndarray:
    vals = df["SWOT_T1_pred_depth_bin"].astype(str)
    mapped = vals.map(model["bin_means"]).astype(float)
    return mapped.fillna(model["global_mean"]).to_numpy(dtype=np.float64)


def fit_linear(X_train: np.ndarray, y_train: np.ndarray) -> dict:
    if not HAS_SKLEARN or StandardScaler is None or LinearRegression is None:
        raise RuntimeError("sklearn is required for linear_regression")
    scaler = StandardScaler()
    model = LinearRegression(fit_intercept=True)
    Xs = scaler.fit_transform(X_train)
    model.fit(Xs, y_train)
    return {"type": LINEAR_MODEL, "scaler": scaler, "model": model}


def predict_scaled(bundle: dict, X: np.ndarray) -> np.ndarray:
    return bundle["model"].predict(bundle["scaler"].transform(X)).astype(np.float64)


def fit_ridge_grid(X_train: np.ndarray, y_train: np.ndarray, X_val: np.ndarray, val: pd.DataFrame) -> dict:
    if not HAS_SKLEARN or StandardScaler is None or Ridge is None:
        raise RuntimeError("sklearn is required for ridge_regression")
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_val_s = scaler.transform(X_val)
    best = None
    rows = []
    for alpha in [0.1, 1, 10, 100]:
        model = Ridge(alpha=alpha)
        model.fit(X_train_s, y_train)
        pred = model.predict(X_val_s).astype(np.float64)
        rmse = val_rmse(val, pred)
        rows.append({"alpha": alpha, "val_RMSE": rmse})
        if best is None or rmse < best["val_RMSE"]:
            best = {"alpha": alpha, "val_RMSE": rmse, "model": model}
    if best is None:
        raise ValueError("No ridge model was fitted")
    return {"type": RIDGE_MODEL, "scaler": scaler, "model": best["model"], "best_params": {"alpha": best["alpha"]}, "search_results": rows}


def fit_rf_grid(X_train: np.ndarray, y_train: np.ndarray, X_val: np.ndarray, val: pd.DataFrame) -> dict:
    if not HAS_SKLEARN or RandomForestRegressor is None:
        raise RuntimeError("sklearn is required for random_forest_regressor")
    best = None
    rows = []
    for n_estimators in [100, 300]:
        for max_depth in [3, 5, 8, None]:
            for min_samples_leaf in [5, 20, 50]:
                model = RandomForestRegressor(n_estimators=n_estimators, max_depth=max_depth, min_samples_leaf=min_samples_leaf, random_state=42, n_jobs=-1)
                model.fit(X_train, y_train)
                pred = model.predict(X_val).astype(np.float64)
                rmse = val_rmse(val, pred)
                row = {"n_estimators": n_estimators, "max_depth": max_depth, "min_samples_leaf": min_samples_leaf, "val_RMSE": rmse}
                rows.append(row)
                if best is None or rmse < best["val_RMSE"]:
                    best = {"val_RMSE": rmse, "model": model, "params": row}
    if best is None:
        raise ValueError("No random forest model was fitted")
    return {"type": RF_MODEL, "model": best["model"], "best_params": {k: v for k, v in best["params"].items() if k != "val_RMSE"}, "search_results": rows}


def fit_boost_grid(X_train: np.ndarray, y_train: np.ndarray, X_val: np.ndarray, val: pd.DataFrame) -> dict | None:
    if HAS_XGBOOST:
        lib = "xgboost"
    elif HAS_LIGHTGBM:
        lib = "lightgbm"
    else:
        return None
    best = None
    rows = []
    for n_estimators in [100, 300]:
        for max_depth in [3, 5, 8]:
            for learning_rate in [0.01, 0.1]:
                if lib == "xgboost":
                    if xgb is None:
                        raise RuntimeError("xgboost is not available")
                    model = xgb.XGBRegressor(n_estimators=n_estimators, max_depth=max_depth, learning_rate=learning_rate, random_state=42, n_jobs=-1)
                else:
                    if lgb is None:
                        raise RuntimeError("lightgbm is not available")
                    model = lgb.LGBMRegressor(n_estimators=n_estimators, max_depth=max_depth, learning_rate=learning_rate, random_state=42, n_jobs=-1, verbose=-1)
                model.fit(X_train, y_train)
                pred = model.predict(X_val).astype(np.float64)
                rmse = val_rmse(val, pred)
                row = {"library": lib, "n_estimators": n_estimators, "max_depth": max_depth, "learning_rate": learning_rate, "val_RMSE": rmse}
                rows.append(row)
                if best is None or rmse < best["val_RMSE"]:
                    best = {"val_RMSE": rmse, "model": model, "params": row}
    if best is None:
        raise ValueError("No boosted tree model was fitted")
    return {"type": BOOST_MODEL, "library": lib, "model": best["model"], "best_params": {k: v for k, v in best["params"].items() if k != "val_RMSE"}, "search_results": rows}


def predict_model(bundle: dict, X: np.ndarray) -> np.ndarray:
    if bundle.get("scaler") is not None:
        return predict_scaled(bundle, X)
    return bundle["model"].predict(X).astype(np.float64)


def train_models_for_feature_set(feature_set: str, train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame) -> dict:
    y_train = train[TARGET_COL].to_numpy(dtype=np.float64)
    features = prepare_feature_set(train, val, test, feature_set)
    models = {}
    global_mean = float(np.mean(y_train))
    models[BASE_MODEL] = {"type": BASE_MODEL, "predict_constant": 0.0}
    models[GLOBAL_BIAS_MODEL] = {"type": GLOBAL_BIAS_MODEL, "predict_constant": global_mean}
    if FEATURE_SETS[feature_set]["allow_bin_bias"]:
        models[BIN_BIAS_MODEL] = {"type": BIN_BIAS_MODEL, **fit_bin_bias(train)}
    if HAS_SKLEARN:
        print(f"训练 {feature_set}: linear_regression")
        models[LINEAR_MODEL] = fit_linear(features["X_train"], y_train)
        print(f"训练 {feature_set}: ridge_regression grid")
        models[RIDGE_MODEL] = fit_ridge_grid(features["X_train"], y_train, features["X_val"], val)
        print(f"训练 {feature_set}: random_forest_regressor grid")
        models[RF_MODEL] = fit_rf_grid(features["X_train"], y_train, features["X_val"], val)
    boost = fit_boost_grid(features["X_train"], y_train, features["X_val"], val)
    if boost is not None:
        print(f"训练 {feature_set}: {boost['library']} grid")
        models[BOOST_MODEL] = boost
    return {"features": features, "models": models}


def make_predictions(model_name: str, model: dict, df: pd.DataFrame, X: np.ndarray) -> np.ndarray:
    if model_name in [BASE_MODEL, GLOBAL_BIAS_MODEL]:
        return np.full(len(df), float(model["predict_constant"]), dtype=np.float64)
    if model_name == BIN_BIAS_MODEL:
        return predict_bin_bias(model, df)
    return predict_model(model, X)


def prediction_base(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["cell_id", "lon_center", "lat_center", "ship_elev", "SWOT_T1_elev", "depth_bin", "quality_tier", "SWOT_T1_pred_depth_bin"]
    out = df[cols].copy()
    out["SWOT_T1_pred_depth_bin"] = out["SWOT_T1_pred_depth_bin"].astype(str)
    out["depth_bin"] = out["depth_bin"].astype(str)
    out["quality_tier"] = out["quality_tier"].astype(str)
    return out


def append_prediction_columns(pred_df: pd.DataFrame, source_df: pd.DataFrame, feature_set: str, model_name: str, pred_residual: np.ndarray) -> None:
    prefix = f"{feature_set}_{model_name}"
    corrected = source_df["SWOT_T1_elev"].to_numpy(dtype=np.float64) + pred_residual
    error = corrected - source_df["ship_elev"].to_numpy(dtype=np.float64)
    pred_df[f"pred_residual_{prefix}"] = pred_residual
    pred_df[f"corrected_elev_{prefix}"] = corrected
    pred_df[f"error_{prefix}"] = error


def grouped_metrics(df: pd.DataFrame, pred_residual: np.ndarray, group_col: str) -> list[dict]:
    rows = []
    work = df[[group_col, "ship_elev", "SWOT_T1_elev"]].copy()
    work["predicted_residual"] = pred_residual
    for key, g in work.groupby(group_col, dropna=False, observed=False, sort=False):
        idx = g.index.to_numpy()
        corrected = df.loc[idx, "SWOT_T1_elev"].to_numpy(dtype=np.float64) + pred_residual[idx]
        ship = df.loc[idx, "ship_elev"].to_numpy(dtype=np.float64)
        rows.append({group_col: str(key), **safe_compute_metrics(ship, corrected)})
    return rows


def evaluate_all(train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    metrics_rows = []
    depth_rows = []
    quality_rows = []
    pred_val = prediction_base(val)
    pred_test = prediction_base(test)
    trained = {}

    for feature_set in FEATURE_SETS:
        print(f"\nFeature Set: {feature_set}")
        result = train_models_for_feature_set(feature_set, train, val, test)
        trained[feature_set] = result
        X_val = result["features"]["X_val"]
        X_test = result["features"]["X_test"]
        for model_name, model in result["models"].items():
            pred_res_val = make_predictions(model_name, model, val, X_val)
            pred_res_test = make_predictions(model_name, model, test, X_test)
            append_prediction_columns(pred_val, val, feature_set, model_name, pred_res_val)
            append_prediction_columns(pred_test, test, feature_set, model_name, pred_res_test)
            for eval_set, eval_df, pred_res in [("val", val, pred_res_val), ("test", test, pred_res_test)]:
                metrics_rows.append({"feature_set": feature_set, "model": model_name, "eval_set": eval_set, **evaluate_corrected(eval_df, pred_res)})
            for row in grouped_metrics(test, pred_res_test, "depth_bin"):
                depth_rows.append({"feature_set": feature_set, "model": model_name, **row})
            for row in grouped_metrics(test, pred_res_test, "SWOT_T1_pred_depth_bin"):
                depth_rows.append({"feature_set": feature_set, "model": model_name, **row})
            for row in grouped_metrics(test, pred_res_test, "quality_tier"):
                quality_rows.append({"feature_set": feature_set, "model": model_name, **row})
            save_pickle({"feature_set": feature_set, "model_name": model_name, "feature_names": result["features"]["feature_names"], "categories": result["features"]["categories"], "model": model}, MODELS_DIR / f"{feature_set}_{model_name}.pkl")

    metrics = pd.DataFrame(metrics_rows)
    depth_metrics = pd.DataFrame(depth_rows)
    quality_metrics = pd.DataFrame(quality_rows)
    metric_cols = ["feature_set", "model", "eval_set", "n", "bias", "MAE", "RMSE", "STD", "median_error", "MAD", "p95_abs_error", "correlation"]
    depth_cols = ["feature_set", "model", "depth_bin", "SWOT_T1_pred_depth_bin", "n", "bias", "MAE", "RMSE", "STD", "median_error", "MAD", "p95_abs_error", "correlation"]
    quality_cols = ["feature_set", "model", "quality_tier", "n", "bias", "MAE", "RMSE", "STD", "median_error", "MAD", "p95_abs_error", "correlation"]
    metrics = metrics[metric_cols]
    depth_metrics = depth_metrics[[col for col in depth_cols if col in depth_metrics.columns]]
    quality_metrics = quality_metrics[quality_cols]
    return metrics, depth_metrics, quality_metrics, pred_val, pred_test, trained


def metric_row(metrics: pd.DataFrame, feature_set: str, model: str) -> pd.Series:
    sub = metrics[(metrics["feature_set"] == feature_set) & (metrics["model"] == model) & (metrics["eval_set"] == "test")]
    if sub.empty:
        return pd.Series(dtype=object)
    return sub.iloc[0]


def best_model(metrics: pd.DataFrame, feature_set: str) -> pd.Series:
    sub = metrics[(metrics["feature_set"] == feature_set) & (metrics["eval_set"] == "test")].sort_values("RMSE")
    return sub.iloc[0]


def describe_effect(metrics: pd.DataFrame, feature_set: str, model: str, base_rmse: float) -> str:
    row = metric_row(metrics, feature_set, model)
    if row.empty:
        return "未运行。"
    delta = base_rmse - float(row["RMSE"])
    pct = delta / base_rmse * 100.0 if base_rmse else np.nan
    return f"test RMSE={fmt(row['RMSE'])} m，MAE={fmt(row['MAE'])} m，Bias={fmt(row['bias'])} m；相比 no_correction RMSE {'降低' if delta >= 0 else '升高'} {fmt(abs(delta))} m ({fmt(abs(pct), 1)}%)."


def make_report(metrics: pd.DataFrame, depth_metrics: pd.DataFrame) -> str:
    env = {"sklearn": "available" if HAS_SKLEARN else "not available", "xgboost": "available" if HAS_XGBOOST else "not available", "lightgbm": "available" if HAS_LIGHTGBM else "not available"}
    no_corr = metric_row(metrics, "swot_only_inference", BASE_MODEL)
    best_a = best_model(metrics, "swot_only_inference")
    best_b = best_model(metrics, "global_product_fusion_diagnostic")
    best_c = best_model(metrics, "oracle_ship_quality_diagnostic")
    base_rmse = float(no_corr["RMSE"])
    best_delta = base_rmse - float(best_a["RMSE"])
    best_pct = best_delta / base_rmse * 100.0
    bias_text = describe_effect(metrics, "swot_only_inference", GLOBAL_BIAS_MODEL, base_rmse)
    bin_text = describe_effect(metrics, "swot_only_inference", BIN_BIAS_MODEL, base_rmse)
    a_depth = metric_row(metrics, "swot_only_inference", BIN_BIAS_MODEL)
    a_linear = metric_row(metrics, "swot_only_inference", LINEAR_MODEL)
    a_rf = metric_row(metrics, "swot_only_inference", RF_MODEL)
    a_boost = metric_row(metrics, "swot_only_inference", BOOST_MODEL)
    candidates = pd.DataFrame([r for r in [a_linear, a_rf, a_boost] if not r.empty])
    best_spatial = candidates.sort_values("RMSE").iloc[0] if not candidates.empty else pd.Series(dtype=object)
    if not a_depth.empty and not best_spatial.empty:
        improve_more = "空间/非线性校正" if float(best_spatial["RMSE"]) < float(a_depth["RMSE"]) else "深度依赖校正"
        source_text = f"depth-bin bias 的 RMSE={fmt(a_depth['RMSE'])} m；最佳线性/RF/Boost（{best_spatial['model']}）RMSE={fmt(best_spatial['RMSE'])} m，因此主要改善更接近 {improve_more}。"
    else:
        source_text = "可用模型不足，无法稳定比较。"
    b_delta = float(best_a["RMSE"]) - float(best_b["RMSE"])
    b_text = f"B 最佳模型 {best_b['model']} test RMSE={fmt(best_b['RMSE'])} m；A 最佳模型 {best_a['model']} test RMSE={fmt(best_a['RMSE'])} m。B 相比 A {'降低' if b_delta > 0 else '没有降低'} {fmt(abs(b_delta))} m。"
    c_text = f"C 使用 n_points_total/n_file_cells/n_cruises_guess/quality_tier 等船测质量信息，不能用于真实 SWOT inference，只能作为诊断上限。C 最佳模型 {best_c['model']} test RMSE={fmt(best_c['RMSE'])} m。"

    depth_col = depth_metrics["depth_bin"] if "depth_bin" in depth_metrics.columns else pd.Series(index=depth_metrics.index, dtype=object)
    depth_focus = depth_metrics[(depth_metrics["feature_set"].eq("swot_only_inference")) & (depth_metrics["model"].isin([BASE_MODEL, str(best_a["model"])])) & (depth_col.astype(str).isin(["5000–6000", "6000–7000"]))]
    depth_table = markdown_table(depth_focus[["model", "depth_bin", "n", "bias", "MAE", "RMSE", "correlation"]].sort_values(["depth_bin", "model"]), 2) if not depth_focus.empty else "无可用深水分组结果。"
    recommend = "建议进入 sparse ship input / patch-based residual model。" if best_pct >= 5.0 else "如果目标是显著降低 RMSE，当前简单 baseline 改善有限；建议先做 sparse ship input / patch-based residual model 的小规模原型，而不是直接扩大复杂度。"

    top_table = markdown_table(metrics[metrics["eval_set"].eq("test")].sort_values("RMSE").head(12)[["feature_set", "model", "n", "bias", "MAE", "RMSE", "correlation"]], 2)
    return "\n".join([
        "# T1 Residual Baseline Training 报告",
        "",
        "## 环境信息",
        f"- sklearn: {env['sklearn']}",
        f"- xgboost: {env['xgboost']}",
        f"- lightgbm: {env['lightgbm']}",
        "",
        "## 1. no_correction 的 test RMSE/MAE/Bias/Corr",
        f"SWOT_T1 corrected_elev = SWOT_T1_elev + 0。test RMSE={fmt(no_corr['RMSE'])} m，MAE={fmt(no_corr['MAE'])} m，Bias={fmt(no_corr['bias'])} m，Corr={fmt(no_corr['correlation'], 4)}。",
        "",
        "## 2. swot_only_inference 中哪个模型最好",
        f"按 test RMSE 排序，最佳模型是 **{best_a['model']}**，test RMSE={fmt(best_a['RMSE'])} m，MAE={fmt(best_a['MAE'])} m，Bias={fmt(best_a['bias'])} m。",
        "",
        "## 3. 最好模型相比 no_correction 的 RMSE 降低多少",
        f"no_correction RMSE={fmt(base_rmse)} m；最佳 A 模型 RMSE={fmt(best_a['RMSE'])} m；绝对降低 {fmt(best_delta)} m，相对降低 {fmt(best_pct, 1)}%。",
        "",
        "## 4. global bias correction 是否有效",
        bias_text,
        "",
        "## 5. SWOT_T1_pred_depth_bin bias correction 是否有效",
        bin_text,
        "",
        "## 6. 改善主要来自深度依赖校正还是空间/非线性校正",
        source_text,
        "",
        "## 7. global_product_fusion_diagnostic 是否显著优于 swot_only_inference",
        b_text,
        "",
        "## 8. oracle_ship_quality_diagnostic 是否只是诊断上限",
        c_text,
        "",
        "## 9. 深水 5000–6000m 和 6000–7000m 上是否改善",
        depth_table,
        "",
        "## 10. 是否值得进入 sparse ship input / patch-based residual model",
        recommend,
        "",
        "## Test RMSE 排名前 12",
        top_table,
        "",
    ])


def deep_5000_rmse(test: pd.DataFrame, pred_test: pd.DataFrame, feature_set: str, model: str) -> float:
    mask = test["ship_depth"].to_numpy(dtype=np.float64) >= 5000
    corrected = pred_test.loc[mask, f"corrected_elev_{feature_set}_{model}"].to_numpy(dtype=np.float64)
    ship = test.loc[mask, "ship_elev"].to_numpy(dtype=np.float64)
    return float(safe_compute_metrics(ship, corrected)["RMSE"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Train T1 ship-supervised residual correction baselines.")
    parser.add_argument("--overwrite", action="store_true", help="regenerate outputs even if they exist")
    args = parser.parse_args()

    if check_existing(args.overwrite):
        return 0

    train, val, test = load_splits()
    metrics, depth_metrics, quality_metrics, pred_val, pred_test, _trained = evaluate_all(train, val, test)
    report = make_report(metrics, depth_metrics)

    atomic_write_tsv(metrics, OUTPUT_DIR / "residual_baseline_metrics.tsv")
    atomic_write_tsv(depth_metrics, OUTPUT_DIR / "residual_baseline_metrics_by_depth_bin.tsv")
    atomic_write_tsv(quality_metrics, OUTPUT_DIR / "residual_baseline_metrics_by_quality_tier.tsv")
    atomic_write_parquet(pred_test, OUTPUT_DIR / "residual_baseline_predictions_test.parquet")
    atomic_write_parquet(pred_val, OUTPUT_DIR / "residual_baseline_predictions_val.parquet")
    atomic_write_text(report, OUTPUT_DIR / "residual_baseline_report.md")

    best_a = best_model(metrics, "swot_only_inference")
    no_corr = metric_row(metrics, "swot_only_inference", BASE_MODEL)
    base_rmse = float(no_corr["RMSE"])
    best_rmse = float(best_a["RMSE"])
    pct = (base_rmse - best_rmse) / base_rmse * 100.0
    deep_no = deep_5000_rmse(test, pred_test, "swot_only_inference", BASE_MODEL)
    deep_best = deep_5000_rmse(test, pred_test, "swot_only_inference", str(best_a["model"]))

    print("\nT1 Residual Baseline Training 完成")
    print(f"环境: sklearn={'yes' if HAS_SKLEARN else 'no'}, xgboost={'yes' if HAS_XGBOOST else 'no'}, lightgbm={'yes' if HAS_LIGHTGBM else 'no'}")
    print(f"输出目录: {OUTPUT_DIR}")
    print("Feature Sets: A(swot_only), B(global_fusion), C(oracle_ship)")
    print(f"最佳 swot_only_inference 模型: {best_a['model']} (test RMSE={best_rmse:.2f}m)")
    print(f"no_correction RMSE: {base_rmse:.2f}m → 最佳 RMSE: {best_rmse:.2f}m (降低 {pct:.1f}%)")
    print(f"深水 5000m+ RMSE: no_correction={deep_no:.2f}m → 最佳={deep_best:.2f}m")
    return 0


if __name__ == "__main__":
    sys.exit(main())

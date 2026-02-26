"""
GPU-Accelerated Outpatient Flow Analytics

Computes operational insights from outpatient case event data:
1. Aggregate metrics (p50/p90 durations, volumes, late-start rates) per facility/procedure
2. Predictive models (discharge time, extended recovery probability) via XGBoost
3. Trend detection and insight generation

Supports GPU acceleration via RAPIDS cuDF/cuML + XGBoost GPU, with
automatic CPU fallback when GPU is unavailable.
"""

import argparse
import json
import logging
import os
import sys
import warnings
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Try GPU-accelerated libraries first, fall back to CPU
GPU_AVAILABLE = False
try:
    import cudf
    import cuml
    GPU_AVAILABLE = True
    logger_gpu = "GPU (RAPIDS)"
except ImportError:
    logger_gpu = "CPU (pandas/scikit-learn)"

import pandas as pd

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    xgb = None
    XGB_AVAILABLE = False

try:
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_absolute_error, r2_score, roc_auc_score
    from sklearn.preprocessing import LabelEncoder
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

warnings.filterwarnings("ignore", category=FutureWarning)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_data(input_path: str) -> pd.DataFrame:
    """Load case event data from CSV or PostgreSQL connection string."""
    if input_path.startswith("postgresql://"):
        try:
            import psycopg2
            import io
            conn = psycopg2.connect(input_path)
            df = pd.read_sql("SELECT * FROM outpatient_case_event", conn)
            conn.close()
        except Exception as e:
            logger.error("Failed to load from DB: %s", e)
            raise
    else:
        df = pd.read_csv(input_path, parse_dates=[
            "scheduled_start_time", "checkin_time", "preop_start_time",
            "op_start_time", "postop_start_time", "discharge_time",
        ])
    logger.info("Loaded %d records from %s (backend: %s)", len(df), input_path, logger_gpu)
    return df


def compute_durations(df: pd.DataFrame) -> pd.DataFrame:
    """Compute derived duration columns if not already present."""
    time_cols = ["checkin_time", "preop_start_time", "op_start_time",
                 "postop_start_time", "discharge_time"]
    for col in time_cols:
        if not pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = pd.to_datetime(df[col])

    if "dur_checkin_to_preop" not in df.columns:
        df["dur_checkin_to_preop"] = (df["preop_start_time"] - df["checkin_time"]).dt.total_seconds() / 60.0
        df["dur_preop_to_op"] = (df["op_start_time"] - df["preop_start_time"]).dt.total_seconds() / 60.0
        df["dur_op_to_postop"] = (df["postop_start_time"] - df["op_start_time"]).dt.total_seconds() / 60.0
        df["dur_postop_to_discharge"] = (df["discharge_time"] - df["postop_start_time"]).dt.total_seconds() / 60.0
        df["dur_total"] = (df["discharge_time"] - df["checkin_time"]).dt.total_seconds() / 60.0

    return df


def compute_aggregates(df: pd.DataFrame) -> pd.DataFrame:
    """Compute aggregate metrics per facility and procedure type."""
    completed = df[df["case_status"] == "completed"].copy()

    duration_cols = [
        "dur_checkin_to_preop", "dur_preop_to_op",
        "dur_op_to_postop", "dur_postop_to_discharge", "dur_total",
    ]

    agg_dict = {}
    for col in duration_cols:
        agg_dict[f"{col}_mean"] = (col, "mean")
        agg_dict[f"{col}_median"] = (col, "median")
        agg_dict[f"{col}_p90"] = (col, lambda x: np.percentile(x.dropna(), 90) if len(x.dropna()) > 0 else np.nan)
        agg_dict[f"{col}_std"] = (col, "std")
    agg_dict["case_volume"] = ("event_id", "count")

    aggs = completed.groupby(["facility_id", "procedure_type"]).agg(**agg_dict).reset_index()

    # Late start rate
    if "scheduled_start_time" in completed.columns:
        completed["late_start"] = (
            pd.to_datetime(completed["op_start_time"]) >
            pd.to_datetime(completed["scheduled_start_time"]) + pd.Timedelta(minutes=15)
        ).astype(int)
        late_rate = completed.groupby(["facility_id", "procedure_type"])["late_start"].mean().reset_index()
        late_rate.columns = ["facility_id", "procedure_type", "late_start_rate"]
        aggs = aggs.merge(late_rate, on=["facility_id", "procedure_type"], how="left")

    logger.info("Computed aggregates: %d facility-procedure combinations", len(aggs))
    return aggs


def prepare_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str], Dict[str, Any]]:
    """Prepare feature matrix for ML models."""
    completed = df[df["case_status"] == "completed"].copy()

    # Encode categoricals
    encoders = {}
    for col in ["facility_id", "procedure_type", "anesthesia_type"]:
        if col in completed.columns:
            le = LabelEncoder()
            completed[f"{col}_enc"] = le.fit_transform(completed[col].fillna("unknown"))
            encoders[col] = le

    # Time features
    completed["checkin_hour"] = pd.to_datetime(completed["checkin_time"]).dt.hour
    completed["checkin_dow"] = pd.to_datetime(completed["checkin_time"]).dt.dayofweek

    feature_cols = [
        "facility_id_enc", "procedure_type_enc", "anesthesia_type_enc",
        "asa_class", "checkin_hour", "checkin_dow",
        "dur_checkin_to_preop", "dur_preop_to_op", "dur_op_to_postop",
    ]
    feature_cols = [c for c in feature_cols if c in completed.columns]

    return completed, feature_cols, encoders


def train_discharge_predictor(df: pd.DataFrame, feature_cols: List[str]) -> Optional[Dict]:
    """Train XGBoost model to predict total case duration (discharge time)."""
    if not XGB_AVAILABLE:
        logger.warning("XGBoost not available, skipping discharge predictor")
        return None

    target = "dur_total"
    valid = df.dropna(subset=feature_cols + [target])
    if len(valid) < 100:
        logger.warning("Insufficient data for training: %d rows", len(valid))
        return None

    X = valid[feature_cols].values
    y = valid[target].values

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    params = {
        "objective": "reg:squarederror",
        "max_depth": 6,
        "learning_rate": 0.1,
        "n_estimators": 100,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "random_state": 42,
    }

    if GPU_AVAILABLE:
        params["tree_method"] = "gpu_hist"
        params["device"] = "cuda"
        logger.info("Training discharge predictor with GPU acceleration")
    else:
        params["tree_method"] = "hist"
        logger.info("Training discharge predictor on CPU")

    model = xgb.XGBRegressor(**params)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)

    logger.info("Discharge predictor: MAE=%.2f min, R²=%.4f", mae, r2)

    # Feature importance
    importance = dict(zip(feature_cols, model.feature_importances_.tolist()))

    return {
        "model_type": "XGBRegressor",
        "target": target,
        "mae_minutes": round(mae, 2),
        "r2_score": round(r2, 4),
        "feature_importance": importance,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "gpu_used": GPU_AVAILABLE,
    }


def train_extended_recovery_classifier(df: pd.DataFrame, feature_cols: List[str]) -> Optional[Dict]:
    """Train classifier for extended recovery (postop > p90 duration)."""
    if not XGB_AVAILABLE:
        logger.warning("XGBoost not available, skipping recovery classifier")
        return None

    completed = df[df["case_status"] == "completed"].copy()
    if "dur_postop_to_discharge" not in completed.columns or len(completed) < 100:
        return None

    p90 = completed["dur_postop_to_discharge"].quantile(0.90)
    completed["extended_recovery"] = (completed["dur_postop_to_discharge"] > p90).astype(int)

    # Use only pre-postop features for prediction
    clf_features = [c for c in feature_cols if "postop" not in c]
    valid = completed.dropna(subset=clf_features + ["extended_recovery"])

    X = valid[clf_features].values
    y = valid["extended_recovery"].values

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    params = {
        "objective": "binary:logistic",
        "max_depth": 5,
        "learning_rate": 0.1,
        "n_estimators": 100,
        "scale_pos_weight": (y_train == 0).sum() / max((y_train == 1).sum(), 1),
        "random_state": 42,
    }
    if GPU_AVAILABLE:
        params["tree_method"] = "gpu_hist"
        params["device"] = "cuda"

    model = xgb.XGBClassifier(**params)
    model.fit(X_train, y_train)

    y_prob = model.predict_proba(X_test)[:, 1]
    try:
        auc = roc_auc_score(y_test, y_prob)
    except ValueError:
        auc = 0.0

    logger.info("Extended recovery classifier: AUC=%.4f (p90 threshold=%.1f min)", auc, p90)

    return {
        "model_type": "XGBClassifier",
        "target": "extended_recovery",
        "p90_threshold_minutes": round(p90, 2),
        "auc_score": round(auc, 4),
        "features_used": clf_features,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "gpu_used": GPU_AVAILABLE,
    }


def generate_insights(df: pd.DataFrame, aggs: pd.DataFrame) -> List[Dict]:
    """Generate actionable insights from the analysis."""
    insights = []

    # 1. Highest variance procedures
    if "dur_total_std" in aggs.columns:
        high_var = aggs.nlargest(5, "dur_total_std")
        for _, row in high_var.iterrows():
            insights.append({
                "type": "high_variance",
                "facility": row["facility_id"],
                "procedure": row["procedure_type"],
                "total_duration_std": round(row["dur_total_std"], 1),
                "message": (
                    f"{row['facility_id']}: {row['procedure_type']} shows high duration variance "
                    f"(σ={row['dur_total_std']:.1f} min). Staffing adjustment may help."
                ),
            })

    # 2. Highest late start rates
    if "late_start_rate" in aggs.columns:
        late = aggs[aggs["late_start_rate"] > 0.2].nlargest(5, "late_start_rate")
        for _, row in late.iterrows():
            insights.append({
                "type": "late_starts",
                "facility": row["facility_id"],
                "procedure": row["procedure_type"],
                "late_start_rate": round(row["late_start_rate"], 3),
                "message": (
                    f"{row['facility_id']}: {row['procedure_type']} has {row['late_start_rate']:.0%} "
                    f"late start rate (>15 min past scheduled). Scheduling review recommended."
                ),
            })

    # 3. Facility-level summary
    completed = df[df["case_status"] == "completed"]
    for fac in completed["facility_id"].unique():
        fac_data = completed[completed["facility_id"] == fac]
        avg_total = fac_data["dur_total"].mean()
        vol = len(fac_data)
        insights.append({
            "type": "facility_summary",
            "facility": fac,
            "avg_total_minutes": round(avg_total, 1),
            "total_cases": vol,
            "message": (
                f"{fac}: {vol} completed cases, avg total time {avg_total:.0f} min"
            ),
        })

    # 4. Cancellation rate
    total = len(df)
    canceled = len(df[df["case_status"] == "canceled"])
    if total > 0:
        cancel_rate = canceled / total
        insights.append({
            "type": "cancellation_rate",
            "rate": round(cancel_rate, 4),
            "count": canceled,
            "total": total,
            "message": f"Overall cancellation rate: {cancel_rate:.1%} ({canceled}/{total})",
        })

    logger.info("Generated %d insights", len(insights))
    return insights


def run_analytics(input_path: str, output_dir: str):
    """Run the full analytics pipeline."""
    os.makedirs(output_dir, exist_ok=True)

    # Load and prepare data
    df = load_data(input_path)
    df = compute_durations(df)

    # Aggregates
    aggs = compute_aggregates(df)
    aggs.to_csv(os.path.join(output_dir, "aggregates.csv"), index=False)

    results = {"timestamp": datetime.now(timezone.utc).isoformat(), "gpu_available": GPU_AVAILABLE}

    if SKLEARN_AVAILABLE:
        prepared, feature_cols, encoders = prepare_features(df)

        # Train models
        discharge_result = train_discharge_predictor(prepared, feature_cols)
        if discharge_result:
            results["discharge_predictor"] = discharge_result

        recovery_result = train_extended_recovery_classifier(prepared, feature_cols)
        if recovery_result:
            results["extended_recovery_classifier"] = recovery_result
    else:
        logger.warning("scikit-learn not available, skipping ML models")

    # Generate insights
    insights = generate_insights(df, aggs)
    results["insights"] = insights

    # Write results
    output_path = os.path.join(output_dir, "analytics_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info("Analytics results written to %s", output_path)

    return results


def main():
    parser = argparse.ArgumentParser(description="Outpatient Flow Analytics")
    parser.add_argument(
        "--input", type=str, required=True,
        help="Input CSV path or PostgreSQL connection string",
    )
    parser.add_argument(
        "--output-dir", type=str, default="output/analytics",
        help="Output directory for results",
    )
    args = parser.parse_args()
    run_analytics(args.input, args.output_dir)


if __name__ == "__main__":
    main()

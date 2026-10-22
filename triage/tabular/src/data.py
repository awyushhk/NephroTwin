"""
data.py — Schema, symptom vocabulary, and feature engineering for the
emergency-department symptom triage router (TRIAGE_NHAMCS.csv).
"""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import FunctionTransformer

MODULE_DIR = Path(__file__).resolve().parent.parent
METADATA_PATH = MODULE_DIR / "models" / "metadata.json"

if METADATA_PATH.exists():
    _metadata = json.loads(METADATA_PATH.read_text())
    SYMPTOMS = list(_metadata.get("symptoms", []))
    RAW_INPUT_COLUMNS = list(_metadata.get("raw_input_columns", []))
    CATEGORICAL_FEATURES = list(_metadata.get("categorical_features", []))
    NUMERICAL_FEATURES = list(_metadata.get("numerical_features", []))
    GATE_FEATURES = list(_metadata.get("gate_features", []))
else:
    SYMPTOMS = []
    RAW_INPUT_COLUMNS = [
        "age", "sex", "symptom_1", "symptom_2", "symptom_3", "injury_reason",
        "diabetes", "temperature_f", "heart_rate", "respiratory_rate",
        "systolic_bp", "diastolic_bp", "oxygen_saturation", "pain_score",
    ]
    CATEGORICAL_FEATURES = ["sex", "injury_reason", "diabetes", "symptom_1", "symptom_2", "symptom_3"]
    NUMERICAL_FEATURES = [
        "age", "temperature_f", "heart_rate", "respiratory_rate", "systolic_bp",
        "diastolic_bp", "oxygen_saturation", "pain_score", "symptom_count",
        "pulse_pressure", "shock_index", "fever", "low_oxygen",
        "fast_heart_rate", "fast_breathing",
    ]
    GATE_FEATURES = [
        "age", "temperature_f", "heart_rate", "respiratory_rate", "systolic_bp",
        "diastolic_bp", "oxygen_saturation", "pain_score", "pulse_pressure", "shock_index",
    ]


def clean_symptom_column(symptom_name: str) -> str:
    """Map symptom display name to the pipeline's indicator column name."""
    return "symptom_" + re.sub(r"[^a-z0-9]+", "_", symptom_name.lower()).strip("_")


SYMPTOM_COLUMNS = [clean_symptom_column(s) for s in SYMPTOMS]


def add_custom_features(X_df: pd.DataFrame) -> pd.DataFrame:
    """
    Feature engineering step saved inside the triage models' pipelines:
    - Unpacks `symptoms` list if given as a single input into symptom_1, 2, 3
    - 128 symptom binary indicator columns (symptom_<name>)
    - symptom_count
    - Clinical vitals interactions: pulse_pressure, shock_index, fever,
      low_oxygen, fast_heart_rate, fast_breathing
    """
    X = X_df.copy()

    # If caller gave a list of symptoms (e.g. from multiselect)
    if "symptoms" in X.columns:
        s1, s2, s3 = [], [], []
        for val in X["symptoms"]:
            if isinstance(val, (list, tuple)):
                s1.append(val[0] if len(val) > 0 else None)
                s2.append(val[1] if len(val) > 1 else None)
                s3.append(val[2] if len(val) > 2 else None)
            else:
                s1.append(None)
                s2.append(None)
                s3.append(None)
        if "symptom_1" not in X.columns or X["symptom_1"].isna().all():
            X["symptom_1"] = s1
            X["symptom_2"] = s2
            X["symptom_3"] = s3

    s_cols = [c for c in ["symptom_1", "symptom_2", "symptom_3"] if c in X.columns]

    # Build symptom indicators efficiently in a dict to prevent fragmentation
    indicators = {}
    for sym, col_name in zip(SYMPTOMS, SYMPTOM_COLUMNS):
        if not s_cols:
            indicators[col_name] = np.zeros(len(X), dtype=float)
        else:
            match = np.zeros(len(X), dtype=bool)
            for sc in s_cols:
                match |= (X[sc] == sym).to_numpy(dtype=bool)
            indicators[col_name] = match.astype(float)

    indicator_df = pd.DataFrame(indicators, index=X.index)

    # Symptom count
    if s_cols:
        symptom_count = sum((X[c].notna() & (X[c] != "")).astype(float) for c in s_cols)
    else:
        symptom_count = pd.Series(0.0, index=X.index)

    # Clinical features
    new_cols = {
        "symptom_count": symptom_count,
        "pulse_pressure": (X["systolic_bp"] - X["diastolic_bp"]) if "systolic_bp" in X.columns and "diastolic_bp" in X.columns else np.nan,
        "shock_index": (X["heart_rate"] / X["systolic_bp"]) if "heart_rate" in X.columns and "systolic_bp" in X.columns else np.nan,
        "fever": (X["temperature_f"] >= 100.4).astype(float) if "temperature_f" in X.columns else 0.0,
        "low_oxygen": (X["oxygen_saturation"] < 95.0).astype(float) if "oxygen_saturation" in X.columns else 0.0,
        "fast_heart_rate": (X["heart_rate"] > 100.0).astype(float) if "heart_rate" in X.columns else 0.0,
        "fast_breathing": (X["respiratory_rate"] > 20.0).astype(float) if "respiratory_rate" in X.columns else 0.0,
    }
    clinical_df = pd.DataFrame(new_cols, index=X.index)

    return pd.concat([X, clinical_df, indicator_df], axis=1)


FEATURE_ENGINEERING = FunctionTransformer(add_custom_features)

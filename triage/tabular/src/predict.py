"""
predict.py — Cascade inference for the layer-1 symptom triage router.
Routes a patient's symptoms, demographics, and optional vital signs to the appropriate
organ modules (heart, lung, kidney) or to 'Other' (routine care).
"""

import json
import sys
import threading
from pathlib import Path
from typing import Optional, Union

_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import numpy as np
import pandas as pd

from common import ACCEPTED, REVIEW, Prediction
from common.config import ORGANS
from common.utils.artifacts import load_pipeline

from . import data

MODEL_DIR = data.MODULE_DIR / "models"
GATE_PATH = MODEL_DIR / "triage_anomaly_gate.joblib"
METADATA_PATH = MODEL_DIR / "metadata.json"
REFERENCE_PATH = MODEL_DIR / "reference_profile.json"

ANOMALY_MESSAGE = "Unusual vital signs or symptom profile: withheld by anomaly gate for manual review"
EXPLANATION_METHOD = "what-if: effect = probability for this patient - probability with this input replaced by typical patient"


class TriageRouter:
    """Layer 1 symptom triage router."""

    def __init__(self):
        self.data_module = data
        self.input_columns = list(data.RAW_INPUT_COLUMNS)
        self.metadata = None
        self.reference = None
        self.gate = None
        self.models = {}
        self.thresholds = {}
        self._lock = threading.Lock()
        self._loaded = False

    def load(self):
        with self._lock:
            if not self._loaded:
                if METADATA_PATH.exists():
                    self.metadata = json.loads(METADATA_PATH.read_text())
                else:
                    self.metadata = {}

                if REFERENCE_PATH.exists():
                    self.reference = json.loads(REFERENCE_PATH.read_text()).get("values", {})
                else:
                    self.reference = {}

                if GATE_PATH.exists():
                    self.gate = load_pipeline(GATE_PATH, self.data_module)

                # Load available organ heads
                heads = self.metadata.get("heads", {})
                for organ in ("kidney", "heart", "lung"):
                    model_file = MODEL_DIR / f"triage_{organ}_calibrated_model.joblib"
                    if model_file.exists():
                        self.models[organ] = load_pipeline(model_file, self.data_module)
                        self.thresholds[organ] = float(heads.get(organ, {}).get("optimal_threshold", 0.15))

                self._loaded = True
        return self

    def frame(self, patient: Union[dict, pd.DataFrame]) -> pd.DataFrame:
        if isinstance(patient, pd.DataFrame):
            df = patient.copy()
        elif isinstance(patient, dict):
            df = pd.DataFrame([patient])
        else:
            df = pd.DataFrame(patient)

        # Ensure raw input columns exist
        for col in self.input_columns:
            if col not in df.columns:
                df[col] = None

        return df

    def predict(self, patient: dict, explain: bool = True) -> Prediction:
        self.load()
        df = self.frame(patient)

        # Stage 1: Anomaly Gate
        if self.gate is not None:
            try:
                gate_pred = self.gate.predict(df)[0]
                if gate_pred == -1:
                    return Prediction(
                        organ="triage", modality="tabular", status=REVIEW,
                        label=None, probability=None, positive=False,
                        explanation={}, message=ANOMALY_MESSAGE,
                        details={"route": [], "probabilities": {}, "thresholds": self.thresholds,
                                 "anomaly_flagged": True},
                    )
            except Exception:
                pass

        # Stage 2: Scoring heads
        probabilities = {}
        for organ, model in self.models.items():
            prob = float(model.predict_proba(df)[0, 1])
            probabilities[organ] = prob

        # Determine route based on configured active ORGANS
        # An organ is routed if P(organ) >= threshold AND organ in ORGANS
        routed_organs = []
        for organ in ORGANS:
            if organ in probabilities and probabilities[organ] >= self.thresholds.get(organ, 0.5):
                ratio = probabilities[organ] / max(self.thresholds.get(organ, 0.5), 1e-9)
                routed_organs.append((organ, ratio))

        # Sort routed organs by ratio descending
        routed_organs.sort(key=lambda x: x[1], reverse=True)
        route = [organ for organ, _ in routed_organs]

        highest_prob = max((probabilities[o] for o in ORGANS if o in probabilities), default=0.0)
        positive = len(route) > 0

        if positive:
            label = " + ".join(o.capitalize() for o in route)
            message = f"Routed to {label}"
        else:
            label = "Other"
            message = "No specific organ signal: routine care"

        explanation = self.explain(df, probabilities) if explain else {}

        return Prediction(
            organ="triage", modality="tabular", status=ACCEPTED,
            label=label, probability=highest_prob, positive=positive,
            explanation=explanation, message=message,
            details={
                "route": route,
                "probabilities": probabilities,
                "thresholds": self.thresholds,
                "models": {o: self.metadata.get("heads", {}).get(o, {}).get("best_model", "Calibrated") for o in self.models},
            },
        )

    def explain(self, df: pd.DataFrame, probabilities: dict) -> dict:
        """Compute what-if explanation factors for each scored organ head."""
        if not self.reference:
            return {"method": EXPLANATION_METHOD, "factors": {}}

        factors_by_organ = {}
        patient_row = df.iloc[0]

        # Find inputs that differ from typical training patient
        differing = []
        for col in self.input_columns:
            val = patient_row.get(col)
            typ = self.reference.get(col)
            if pd.notna(val) and val != typ and val != "":
                differing.append(col)

        if not differing:
            return {"method": EXPLANATION_METHOD, "factors": {o: [] for o in ORGANS if o in self.models}}

        # Create counterfactual variants
        variants = pd.concat([df] * len(differing), ignore_index=True)
        for i, col in enumerate(differing):
            variants.at[i, col] = self.reference.get(col)

        for organ in ORGANS:
            if organ not in self.models:
                continue
            model = self.models[organ]
            p_actual = probabilities[organ]
            p_counter = model.predict_proba(variants)[:, 1]
            effects = p_actual - p_counter

            order = np.argsort(-np.abs(effects))[:5]
            factors_by_organ[organ] = [
                {
                    "feature": differing[i],
                    "value": patient_row[differing[i]],
                    "typical": self.reference.get(differing[i]),
                    "effect": float(effects[i]),
                }
                for i in order if abs(effects[i]) > 0.001
            ]

        return {"method": EXPLANATION_METHOD, "factors": factors_by_organ}

    def predict_batch(self, patients: pd.DataFrame) -> pd.DataFrame:
        self.load()
        df = self.frame(patients)
        results = [self.predict(row.to_dict(), explain=False) for _, row in df.iterrows()]
        return pd.DataFrame({
            "status": [r.status for r in results],
            "label": [r.label for r in results],
            "probability": [r.probability for r in results],
            "positive": [r.positive for r in results],
            "route": [r.details.get("route", []) for r in results],
            "message": [r.message for r in results],
        })


MODEL = TriageRouter()


def predict(patient: dict, explain: bool = True) -> Prediction:
    return MODEL.predict(patient, explain=explain)


def predict_batch(patients: pd.DataFrame) -> pd.DataFrame:
    return MODEL.predict_batch(patients)


if __name__ == "__main__":
    from common.tabular import run_cli
    run_cli(MODEL, "Run layer 1 symptom triage router.")

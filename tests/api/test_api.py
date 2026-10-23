"""
tests/api/test_api.py — Integration and endpoint tests for FastAPI backend.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "Renal Risk Prediction System API"
    assert data["organ"] == "kidney"
    assert "timestamp" in data


def test_root_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_metadata_endpoint():
    response = client.get("/api/kidney/metadata")
    assert response.status_code == 200
    data = response.json()
    assert data["organ"] == "kidney"

    # Tabular metadata
    tabular = data["tabular"]
    assert tabular["disease"] == "chronic kidney disease (KDIGO)"
    assert tabular["total_features"] == 19
    assert tabular["min_features_required"] == 10
    assert len(tabular["columns"]) == 19
    assert isinstance(tabular["threshold"], float)
    assert "About you" in tabular["sections"]
    assert "age" in tabular["features"]
    assert tabular["features"]["age"]["type"] == "numeric"
    assert tabular["features"]["gender"]["type"] == "categorical"
    assert "Female" in tabular["features"]["gender"]["options"]

    # Image metadata
    image = data["image"]
    assert image["expected_input"] == "a kidney CT slice"
    assert "Cyst" in image["class_names"]
    assert "Stone" in image["class_names"]
    assert "png" in image["supported_formats"]
    assert image["confidence_threshold"] == 0.75
    assert image["best_model"] == "DenseNet121_FT"


def test_tabular_prediction_valid():
    example_path = ROOT / "models" / "kidney" / "tabular" / "examples" / "patient.json"
    patient = json.loads(example_path.read_text())

    response = client.post("/api/kidney/tabular", json=patient)
    assert response.status_code == 200
    data = response.json()

    assert data["organ"] == "kidney"
    assert data["modality"] == "tabular"
    assert data["status"] in ("accepted", "review", "rejected")
    assert data["scored"] is True
    assert isinstance(data["probability"], float)
    assert 0.0 <= data["probability"] <= 1.0
    assert data["label"] == "Low Risk"
    assert data["positive"] is False
    assert isinstance(data["threshold"], float)
    assert isinstance(data["message"], str)
    assert "factors" in data["explanation"]
    assert len(data["explanation"]["factors"]) > 0


def test_tabular_prediction_nested_inputs():
    example_path = ROOT / "models" / "kidney" / "tabular" / "examples" / "patient.json"
    patient = json.loads(example_path.read_text())

    response = client.post("/api/kidney/tabular", json={"inputs": patient})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert data["scored"] is True


def test_tabular_prediction_insufficient_features_rejected():
    # Only 2 features out of 19 (minimum is 10)
    response = client.post("/api/kidney/tabular", json={"age": 55, "gender": "Male"})
    assert response.status_code == 422
    data = response.json()
    assert "Please provide at least 10" in data["detail"]


def test_tabular_prediction_half_features_with_knn_imputation():
    example_path = ROOT / "models" / "kidney" / "tabular" / "examples" / "patient.json"
    patient = json.loads(example_path.read_text())

    # Provide exactly 10 features (50% of 19 rounded up)
    keys = list(patient.keys())[:10]
    partial = {k: patient[k] for k in keys}

    response = client.post("/api/kidney/tabular", json=partial)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("accepted", "review", "rejected")
    assert data["scored"] is True
    assert isinstance(data["probability"], float)


def test_tabular_prediction_anomaly_flagged_for_review():
    # Extreme/anomalous profile that triggers the Isolation Forest anomaly gate
    anomalous = {
        "age": 99,
        "education_level": 1,
        "poverty_income_ratio": 5.0,
        "bmi": 75.0,
        "height_cm": 120,
        "bp_systolic": 280,
        "bp_diastolic": 180,
        "blood_urea_nitrogen": 140,
        "albumin_serum": 1.2,
        "phosphorus": 9.5,
        "bicarbonate": 8,
        "calcium": 5.2,
        "uric_acid": 14.5,
        "gender": "Male",
        "ethnicity": "Non-Hispanic Black",
        "insulin_use": "Yes",
        "diabetes_pills": "Yes",
        "diabetes": "Yes",
        "smoking_status": "Current",
    }
    response = client.post("/api/kidney/tabular", json=anomalous)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "review"
    assert data["scored"] is False
    assert data["probability"] is None
    assert "anomaly gate" in data["message"].lower() or "review" in data["message"].lower()


def test_image_prediction_valid_ct_with_gradcam():
    sample_ct = ROOT / "frontend" / "assets" / "sample_ct" / "sample_stone.png"
    if not sample_ct.exists():
        pytest.skip("sample_stone.png does not exist")

    with open(sample_ct, "rb") as f:
        response = client.post(
            "/api/kidney/image",
            files={"file": ("sample_stone.png", f, "image/png")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["organ"] == "kidney"
    assert data["modality"] == "image"
    assert data["status"] == "accepted"
    assert data["scored"] is True
    assert data["label"] == "Stone"
    assert data["positive"] is True
    assert isinstance(data["probability"], float)
    assert "Grad-CAM" in data["explanation"]["method"]
    assert data["explanation"]["overlay"] is not None
    assert data["explanation"]["overlay"].startswith("data:image/png;base64,")


def test_image_prediction_ood_rejected():
    sample_ood = ROOT / "sample_test_slice.png"
    if not sample_ood.exists():
        pytest.skip("sample_test_slice.png does not exist")

    with open(sample_ood, "rb") as f:
        response = client.post(
            "/api/kidney/image",
            files={"file": ("sample_test_slice.png", f, "image/png")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["scored"] is False
    assert data["label"] is None
    assert data["probability"] is None
    assert "rejected by the out-of-distribution gate" in data["message"]


def test_image_prediction_unsupported_format():
    response = client.post(
        "/api/kidney/image",
        files={"file": ("patient_history.txt", b"plain text content", "text/plain")},
    )
    assert response.status_code == 400
    assert "Unsupported file format" in response.json()["detail"]


def test_image_prediction_empty_file():
    response = client.post(
        "/api/kidney/image",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_image_prediction_corrupt_image():
    response = client.post(
        "/api/kidney/image",
        files={"file": ("corrupt.png", b"NOT_A_VALID_PNG_DATA", "image/png")},
    )
    assert response.status_code == 400
    assert "not a valid" in response.json()["detail"].lower()


def test_image_prediction_ensemble_missing_checkpoints():
    sample_ct = ROOT / "frontend" / "assets" / "sample_ct" / "sample_stone.png"
    if not sample_ct.exists():
        pytest.skip("sample_stone.png does not exist")

    with open(sample_ct, "rb") as f:
        response = client.post(
            "/api/kidney/image",
            files={"file": ("sample_stone.png", f, "image/png")},
            data={"ensemble": "true"},
        )

    # Since the other 3 ensemble checkpoints are not committed to git, 503 is returned explaining missing weights
    assert response.status_code == 503
    assert "Model checkpoint missing on server" in response.json()["detail"]

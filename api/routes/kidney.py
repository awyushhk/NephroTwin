"""
api/routes/kidney.py — Renal (CKD) risk prediction routes: metadata, clinical tabular questionnaire, and CT slice image.
"""

from typing import Optional
from fastapi import APIRouter, File, Form, Request, UploadFile

from api.schemas import (
    MetadataResponse,
    TabularPredictionRequest,
    TabularPredictionResponse,
    ImagePredictionResponse,
)
from api import services

router = APIRouter(prefix="/kidney", tags=["Kidney Risk Prediction"])


@router.get("/metadata", response_model=MetadataResponse)
async def get_kidney_metadata():
    """
    Get clinical feature specifications, supported CT formats, and model parameters
    for both tabular CKD risk prediction and CT image analysis.
    """
    return services.get_metadata()


@router.post("/tabular", response_model=TabularPredictionResponse)
async def predict_tabular_risk(request: TabularPredictionRequest):
    """
    Predict CKD risk from patient clinical questionnaire inputs.
    Requires at least 50% (10 of 19) of input features. Missing values are imputed with KNN.
    Returns status, risk label, calibrated probability, decision threshold, message, and SHAP-style factors.
    """
    inputs = request.get_input_dict()
    return services.predict_tabular(inputs)


@router.post("/image", response_model=ImagePredictionResponse)
async def predict_ct_image(
    request: Request,
    file: UploadFile = File(...),
    ensemble: Optional[bool] = Form(None),
):
    """
    Predict kidney finding (Cyst, Normal, Stone, Tumor) from a single CT scan slice.
    Supports PNG, JPG, JPEG, BMP, TIF, TIFF. Optional ensemble mode (soft-voting).
    Returns inference status, predicted class, probability, confidence, and Grad-CAM overlay.
    """
    # Check ensemble flag from either Form or Query params
    use_ensemble = False
    if ensemble is not None:
        use_ensemble = bool(ensemble)
    elif "ensemble" in request.query_params:
        use_ensemble = request.query_params.get("ensemble", "").lower() in ("true", "1", "yes")

    content = await file.read()
    return services.predict_image(content, filename=file.filename, ensemble=use_ensemble)

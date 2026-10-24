"""
api/routes/kidney.py — Renal (CKD) risk prediction routes: metadata, clinical tabular questionnaire, and CT slice image.
"""

from typing import Optional
from fastapi import APIRouter, File, Form, Request, UploadFile

from api.schemas import (
    CTStudyPredictionResponse,
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


@router.post("/image/study", response_model=CTStudyPredictionResponse)
async def predict_ct_study(
    request: Request,
    files: list[UploadFile] = File(...),
    ensemble: Optional[bool] = Form(None),
):
    """Analyze submitted CT slices independently and return a conservative descriptive summary."""
    use_ensemble = bool(ensemble) if ensemble is not None else request.query_params.get("ensemble", "").lower() in ("true", "1", "yes")
    submitted = []
    total_bytes = 0
    for index, upload in enumerate(files):
        filename = upload.filename or "unnamed-image"
        if index >= services.MAX_STUDY_FILES:
            submitted.append((filename, None, f"A study can contain at most {services.MAX_STUDY_FILES} images."))
            continue
        remaining = services.MAX_STUDY_SIZE_BYTES - total_bytes
        if remaining <= 0:
            submitted.append((filename, None, "The examination exceeds the 100 MB total upload limit."))
            continue
        read_limit = min(services.MAX_IMAGE_SIZE_BYTES + 1, remaining + 1)
        content = await upload.read(read_limit)
        if len(content) > remaining:
            submitted.append((filename, None, "The examination exceeds the 100 MB total upload limit."))
            total_bytes = services.MAX_STUDY_SIZE_BYTES
        else:
            total_bytes += len(content)
            submitted.append((filename, content, None))
    return services.predict_ct_study(submitted, ensemble=use_ensemble)

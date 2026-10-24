"""
api/services.py — Service layer interfacing with existing kidney models.
Never duplicates preprocessing or retrains models; reuses existing loaders.
"""

import io
import math
import os
import uuid
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image, UnidentifiedImageError
from fastapi import HTTPException

from common import ACCEPTED, REJECTED, REVIEW
from common.registry import module
from frontend.components import fields
from api.schemas import (
    ExplanationFactor,
    FeatureMetadata,
    HealthResponse,
    ImageExplanation,
    ImageMetadata,
    ImagePredictionResponse,
    MetadataResponse,
    TabularExplanation,
    TabularMetadata,
    TabularPredictionResponse,
    CTStudyClassCount,
    CTStudyImageResult,
    CTStudyPredictionResponse,
    CTStudySummary,
)
from api.utils import clean_for_json, is_valid_image_extension, numpy_to_base64_png

ORGAN = "kidney"
SUPPORTED_IMAGE_FORMATS = ["png", "jpg", "jpeg", "bmp", "tif", "tiff"]
MAX_IMAGE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_STUDY_FILES = 12
MAX_STUDY_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
MAX_IMAGE_PIXELS = 40_000_000
CT_CLASS_NAMES = ["Cyst", "Normal", "Stone", "Tumor"]


def _study_minimum_accepted_images() -> int:
    try:
        return max(1, int(os.getenv("CT_STUDY_MIN_ACCEPTED_IMAGES", "2")))
    except ValueError:
        return 2


def get_tabular_module():
    """Retrieve and ensure the kidney tabular module and its models are loaded."""
    m = module(ORGAN, "tabular")
    m.MODEL.load()
    return m


def get_image_module():
    """Retrieve and ensure the kidney image module metadata and gate are loaded."""
    im = module(ORGAN, "image")
    im.MODEL.load()
    return im


def get_metadata() -> MetadataResponse:
    """Extract metadata for tabular questionnaire and image CT prediction."""
    tab_mod = get_tabular_module()
    img_mod = get_image_module()

    columns = list(tab_mod.MODEL.input_columns)
    min_needed = math.ceil(len(columns) * 0.5)

    categorical_answers = fields.answers(ORGAN)
    feature_meta: dict[str, FeatureMetadata] = {}

    for col in columns:
        if col in fields.ORDINAL:
            lbl, opt_dict = fields.ORDINAL[col]
            options = [{"value": k, "label": v} for k, v in opt_dict.items()]
            feature_meta[col] = FeatureMetadata(
                name=col,
                label=lbl,
                type="ordinal",
                options=options,
            )
        elif col in fields.NUMERIC:
            lbl, unit, low, high, step = fields.NUMERIC[col]
            feature_meta[col] = FeatureMetadata(
                name=col,
                label=lbl,
                type="numeric",
                unit=unit,
                min=float(low),
                max=float(high),
                step=float(step),
            )
        elif col in categorical_answers:
            feature_meta[col] = FeatureMetadata(
                name=col,
                label=fields.label(col),
                type="categorical",
                options=categorical_answers[col],
            )
        else:
            feature_meta[col] = FeatureMetadata(
                name=col,
                label=fields.label(col),
                type="categorical",
                options=[],
            )

    tab_meta = TabularMetadata(
        disease=tab_mod.MODEL.disease,
        columns=columns,
        total_features=len(columns),
        min_features_required=min_needed,
        threshold=float(tab_mod.MODEL.threshold),
        sections=fields.sections(columns),
        features=feature_meta,
    )

    img_meta = ImageMetadata(
        expected_input=img_mod.MODEL.expected_input,
        class_names=list(img_mod.MODEL.class_names or []),
        supported_formats=SUPPORTED_IMAGE_FORMATS,
        confidence_threshold=float(img_mod.MODEL.threshold),
        best_model=str(img_mod.MODEL.best_model),
        ensemble_members=list(img_mod.MODEL.ensemble_members or []),
    )

    return MetadataResponse(organ=ORGAN, tabular=tab_meta, image=img_meta)


def predict_tabular(inputs: dict[str, Any]) -> TabularPredictionResponse:
    """
    Validate questionnaire inputs, check the >= 50% feature threshold,
    and run inference using the existing kidney tabular model.
    """
    tab_mod = get_tabular_module()
    columns = list(tab_mod.MODEL.input_columns)
    min_needed = math.ceil(len(columns) * 0.5)

    # Count provided inputs that are not None, not empty string, and not NaN
    provided_values: dict[str, Any] = {}
    for col in columns:
        val = inputs.get(col)
        if val is not None and val != "":
            if isinstance(val, float) and math.isnan(val):
                continue
            # Type cast numeric fields if passed as numeric string
            if col in fields.NUMERIC and isinstance(val, (int, float, str)):
                try:
                    val = float(val)
                except ValueError:
                    pass
            elif col in fields.ORDINAL and isinstance(val, (int, str)):
                try:
                    val = int(val)
                except ValueError:
                    pass
            provided_values[col] = val

    if len(provided_values) < min_needed:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Please provide at least {min_needed} of the {len(columns)} "
                f"clinical questionnaire fields (you provided {len(provided_values)})."
            ),
        )

    # Build row ensuring all 19 columns are present (None for missing)
    row = {col: provided_values.get(col, None) for col in columns}

    try:
        result = tab_mod.predict(row, explain=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Tabular prediction failed: {exc}")

    # Build serializable factors
    factors_list: list[ExplanationFactor] = []
    for f in result.explanation.get("factors", []):
        factors_list.append(
            ExplanationFactor(
                feature=str(f.get("feature")),
                value=clean_for_json(f.get("value")),
                typical=clean_for_json(f.get("typical")),
                effect=float(f.get("effect", 0.0)),
            )
        )

    threshold = float(result.details.get("threshold", tab_mod.MODEL.threshold))
    clean_details = clean_for_json(result.details)

    return TabularPredictionResponse(
        organ=result.organ,
        modality=result.modality,
        status=result.status,
        scored=result.scored,
        probability=float(result.probability) if result.probability is not None else None,
        label=result.label,
        positive=result.positive,
        threshold=threshold,
        message=result.message,
        explanation=TabularExplanation(
            method=result.explanation.get("method", ""),
            factors=factors_list,
        ),
        details=clean_details,
    )


def predict_image(image_bytes: bytes, filename: Optional[str] = None, ensemble: bool = False) -> ImagePredictionResponse:
    """
    Validate uploaded image slice, handle formats safely, and run inference
    using the existing kidney image model (with Grad-CAM overlay).
    """
    if not is_valid_image_extension(filename):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file format '{Path(filename or '').suffix}'. "
                f"Supported formats: {', '.join(fmt.upper() for fmt in SUPPORTED_IMAGE_FORMATS)}."
            ),
        )

    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded image file is empty.")

    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded image exceeds 25 MB size limit.")

    # Validate image bytes can be decoded
    try:
        with Image.open(io.BytesIO(image_bytes)) as pil_img:
            pil_img.verify()
    except (UnidentifiedImageError, Exception):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid, decodable image.")

    img_mod = get_image_module()

    try:
        result = img_mod.predict(image_bytes, explain=True, ensemble=ensemble)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Model checkpoint missing on server: {exc}. "
                "Only the primary deployed model (DenseNet121_FT) is installed. "
                "See models/kidney/image_based/models/README.md to download full ensemble weights."
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Image prediction failed: {exc}")

    overlay_b64: Optional[str] = None
    if "overlay" in result.explanation and isinstance(result.explanation["overlay"], np.ndarray):
        overlay_b64 = numpy_to_base64_png(result.explanation["overlay"])

    clean_details = clean_for_json(result.details)

    return ImagePredictionResponse(
        organ=result.organ,
        modality=result.modality,
        status=result.status,
        scored=result.scored,
        probability=float(result.probability) if result.probability is not None else None,
        label=result.label,
        positive=result.positive,
        message=result.message,
        details=clean_details,
        explanation=ImageExplanation(
            method=result.explanation.get("method"),
            overlay=overlay_b64,
        ),
    )


def predict_ct_study(
    submitted: list[tuple[str, Optional[bytes], Optional[str]]], ensemble: bool = False,
) -> CTStudyPredictionResponse:
    """Run the unchanged single-image pipeline independently for each study file."""
    examination_id = str(uuid.uuid4())
    results: list[CTStudyImageResult] = []
    total_bytes = 0
    for index, (filename, content, validation_error) in enumerate(submitted):
        image_id = str(uuid.uuid4())
        name = Path(filename or "unnamed-image").name
        error = validation_error
        invalid_file = validation_error is not None
        if index >= MAX_STUDY_FILES:
            error = f"A study can contain at most {MAX_STUDY_FILES} images."
            invalid_file = True
        elif error is None and content is not None:
            total_bytes += len(content)
            if len(content) > MAX_IMAGE_SIZE_BYTES:
                error = "Uploaded image exceeds the 25 MB per-image limit."
                invalid_file = True
            elif total_bytes > MAX_STUDY_SIZE_BYTES:
                error = "The examination exceeds the 100 MB total upload limit."
                invalid_file = True
        if error is None and content is not None:
            try:
                with Image.open(io.BytesIO(content)) as image:
                    width, height = image.size
                    if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
                        raise HTTPException(status_code=400, detail="Image dimensions exceed the 40 megapixel limit.")
                    image.verify()
            except HTTPException as exc:
                error = str(exc.detail)
                invalid_file = True
            except Exception:
                error = "Uploaded file is not a valid, decodable image."
                invalid_file = True
        if error is None and content is not None:
            try:
                prediction = predict_image(content, filename=name, ensemble=ensemble)
                status = {
                    ACCEPTED: "accepted",
                    REVIEW: "review_required",
                    REJECTED: "ood_rejected",
                }.get(prediction.status, "processing_error")
                results.append(CTStudyImageResult(
                    image_id=image_id, filename=name, status=status, prediction=prediction,
                ))
                continue
            except HTTPException as exc:
                error = str(exc.detail)
                invalid_file = exc.status_code in (400, 413)
            except Exception as exc:
                error = f"Image processing failed ({type(exc).__name__})."
        results.append(CTStudyImageResult(
            image_id=image_id,
            filename=name,
            status="invalid_file" if invalid_file else "processing_error",
            error=error or "Image content was not available for processing.",
        ))

    accepted = [row for row in results if row.status == "accepted" and row.prediction]
    counts = {name: sum(row.prediction.label == name for row in accepted) for name in CT_CLASS_NAMES}
    accepted_count = len(accepted)
    distribution = {
        name: CTStudyClassCount(
            count=count,
            percentage=round(count * 100 / accepted_count, 2) if accepted_count else 0.0,
        )
        for name, count in counts.items()
    }
    score_values: dict[str, list[float]] = {name: [] for name in CT_CLASS_NAMES}
    for row in accepted:
        probabilities = row.prediction.details.get("probabilities", {})
        if isinstance(probabilities, dict):
            for name in CT_CLASS_NAMES:
                value = probabilities.get(name)
                if isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 1:
                    score_values[name].append(float(value))
    mean_scores = {
        name: round(sum(values) / len(values), 6)
        for name, values in score_values.items() if values
    }
    warnings: list[str] = []
    if accepted_count == 0:
        warnings.append("No images passed the existing OOD and confidence checks; no class summary is available.")
    if accepted_count < _study_minimum_accepted_images():
        warnings.append(f"Fewer than {_study_minimum_accepted_images()} accepted images are available.")
    if len({row.prediction.label for row in accepted}) > 1:
        warnings.append("Accepted images have conflicting predicted classes; expert review is required.")
    if any(row.status == "review_required" for row in results):
        warnings.append("One or more images fell below the existing confidence threshold and need individual review.")
    if any(row.status == "ood_rejected" for row in results):
        warnings.append("One or more images were rejected by the existing out-of-distribution gate.")
    if any(row.status in ("invalid_file", "processing_error") for row in results):
        warnings.append("One or more submitted files could not be analyzed; they were not counted as Normal.")
    must_review = (
        accepted_count < _study_minimum_accepted_images()
        or len({row.prediction.label for row in accepted}) > 1
    )
    summary = CTStudySummary(
        status="study_review_required" if must_review else "descriptive_summary_available",
        accepted_image_count=accepted_count,
        submitted_image_count=len(submitted),
        class_distribution=distribution,
        mean_image_level_scores=mean_scores,
        mean_score_image_counts={name: len(values) for name, values in score_values.items()},
        warnings=warnings,
        minimum_accepted_images=_study_minimum_accepted_images(),
        disagreement_rule="Abstain when accepted images predict more than one class; no majority vote is used.",
    )
    return CTStudyPredictionResponse(examination_id=examination_id, summary=summary, images=results)

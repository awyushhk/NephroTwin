"""
api/schemas.py — Pydantic models for request validation and response serialization.
"""

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str = "Renal Risk Prediction System API"
    organ: str = "kidney"
    timestamp: Optional[str] = None


class FeatureMetadata(BaseModel):
    name: str
    label: str
    type: str  # "numeric", "ordinal", "categorical"
    unit: Optional[str] = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    options: Optional[Any] = None  # list of strings or list of {value, label} dicts


class TabularMetadata(BaseModel):
    disease: str
    columns: list[str]
    total_features: int
    min_features_required: int
    threshold: float
    sections: dict[str, list[str]]
    features: dict[str, FeatureMetadata]


class ImageMetadata(BaseModel):
    expected_input: str
    class_names: list[str]
    supported_formats: list[str]
    confidence_threshold: float
    best_model: str
    ensemble_members: list[str]


class MetadataResponse(BaseModel):
    organ: str = "kidney"
    tabular: TabularMetadata
    image: ImageMetadata


class TabularPredictionRequest(BaseModel):
    """
    Accepts either a nested {"inputs": {...}} payload or flat feature keys:
    {"age": 58, "bp_systolic": 145, ...}
    """
    model_config = ConfigDict(extra="allow")

    inputs: Optional[dict[str, Any]] = None

    def get_input_dict(self) -> dict[str, Any]:
        """Extract questionnaire inputs whether passed under 'inputs' or top-level."""
        if self.inputs is not None and isinstance(self.inputs, dict):
            return self.inputs
        dumped = self.model_dump(exclude_unset=True)
        dumped.pop("inputs", None)
        return dumped


class ExplanationFactor(BaseModel):
    feature: str
    value: Any
    typical: Any
    effect: float


class TabularExplanation(BaseModel):
    method: str = ""
    factors: list[ExplanationFactor] = Field(default_factory=list)


class TabularPredictionResponse(BaseModel):
    organ: str = "kidney"
    modality: str = "tabular"
    status: str
    scored: bool
    probability: Optional[float] = None
    label: Optional[str] = None
    positive: Optional[bool] = None
    threshold: float
    message: str
    explanation: TabularExplanation
    details: dict[str, Any] = Field(default_factory=dict)


class ImageExplanation(BaseModel):
    method: Optional[str] = None
    overlay: Optional[str] = None  # Base64 data URI: data:image/png;base64,...


class ImagePredictionResponse(BaseModel):
    organ: str = "kidney"
    modality: str = "image"
    status: str
    scored: bool
    probability: Optional[float] = None
    label: Optional[str] = None
    positive: Optional[bool] = None
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    explanation: ImageExplanation


class CTStudyImageResult(BaseModel):
    image_id: str
    filename: str
    status: str
    prediction: Optional[ImagePredictionResponse] = None
    error: Optional[str] = None


class CTStudyClassCount(BaseModel):
    count: int
    percentage: float


class CTStudySummary(BaseModel):
    status: str
    accepted_image_count: int
    submitted_image_count: int
    class_distribution: dict[str, CTStudyClassCount]
    mean_image_level_scores: dict[str, float] = Field(default_factory=dict)
    mean_score_image_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    minimum_accepted_images: int
    disagreement_rule: str


class CTStudyPredictionResponse(BaseModel):
    examination_id: str
    summary: CTStudySummary
    images: list[CTStudyImageResult]

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class PatientCreate(BaseModel):
    patient_code: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    profile_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("profile_metadata")
    @classmethod
    def non_identifying_metadata(cls, value):
        if set(value) - {"synthetic", "cohort"}:
            raise ValueError("Profile metadata supports only the non-identifying synthetic and cohort fields.")
        if "synthetic" in value and not isinstance(value["synthetic"], bool):
            raise ValueError("synthetic metadata must be a boolean.")
        if "cohort" in value and (not isinstance(value["cohort"], str) or len(value["cohort"]) > 64):
            raise ValueError("cohort metadata must be a short non-identifying label.")
        return value

class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_code: str | None
    created_at: datetime
    observation_count: int = 0

class ObservationCreate(BaseModel):
    measurement_type: Literal["creatinine", "egfr", "acr", "bun", "potassium", "bicarbonate", "urine_albumin", "urine_creatinine", "systolic_bp", "diastolic_bp"]
    value: float
    unit: str = Field(max_length=32)
    observed_at: datetime
    source: str | None = Field(default=None, max_length=128)
    note: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=128)

class ObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_id: int
    measurement_type: str
    value: float
    unit: str
    observed_at: datetime
    source: str | None
    note: str | None
    created_at: datetime

class ScenarioCreate(BaseModel):
    baseline_observation_id: int
    rate_per_year: float = Field(ge=-30, le=30)
    horizon_months: int = Field(ge=1, le=120)

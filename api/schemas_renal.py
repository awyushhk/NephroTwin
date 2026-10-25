from datetime import date, datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    measurement_type: Literal["creatinine", "egfr", "acr", "bun", "potassium", "bicarbonate", "urine_albumin", "urine_creatinine", "systolic_bp", "diastolic_bp", "hba1c"]
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
    observed_at: datetime | None
    observed_date: date | None = None
    timestamp_precision: Literal["exact_time", "date_only"] = "exact_time"
    source_sequence_number: int | None = None
    source: str | None
    note: str | None
    created_at: datetime

class ScenarioCreate(BaseModel):
    baseline_observation_id: int
    rate_per_year: float = Field(ge=-30, le=30)
    horizon_months: int = Field(ge=1, le=120)
    comparison_group_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    scenario_label: str | None = Field(default=None, max_length=40)
    comparison_index: int | None = Field(default=None, ge=0, le=9)

class ScenarioComparisonItem(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    rate_per_year: float = Field(ge=-30, le=30, allow_inf_nan=False)

class ScenarioComparisonCreate(BaseModel):
    baseline_observation_id: int
    horizon_months: int = Field(ge=1, le=120)
    scenarios: list[ScenarioComparisonItem] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def distinct_scenario_rates_and_labels(self):
        rates = [item.rate_per_year for item in self.scenarios]
        labels = [item.label.strip().casefold() for item in self.scenarios]
        if len(set(rates)) != len(rates):
            raise ValueError("Each comparison scenario must use a different annual rate.")
        if len(set(labels)) != len(labels):
            raise ValueError("Scenario labels must be unique within a comparison.")
        return self

class NephroQSimulationCreate(BaseModel):
    years: float = Field(default=15, gt=0, le=15, allow_inf_nan=False)
    baseline_observation_id: int | None = Field(default=None, gt=0)

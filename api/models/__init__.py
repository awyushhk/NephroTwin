"""Persistent renal twin entities."""
from datetime import date, datetime, timezone
from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column, relationship
from api.database import Base

def now_utc(): return datetime.now(timezone.utc)

class Patient(Base):
    __tablename__ = "renal_patients"
    __table_args__ = (UniqueConstraint("source_system", "source_patient_id", name="uq_patient_source_identity"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_code: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    profile_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    source_system: Mapped[str | None] = mapped_column(String(32))
    source_patient_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    observations = relationship("RenalObservation", back_populates="patient", cascade="all, delete-orphan")

class RenalObservation(Base):
    __tablename__ = "renal_observations"
    __table_args__ = (
        Index("ix_renal_observations_patient_time", "patient_id", "observed_at"),
        Index("ix_renal_observations_patient_event_order", "patient_id", "observed_date", "source_sequence_number", "observed_at", "id"),
        UniqueConstraint("patient_id", "idempotency_key", name="uq_observation_idempotency"),
        UniqueConstraint("source_system", "source_observation_id", name="uq_observation_source_identity"),
        CheckConstraint("value >= 0", name="ck_observation_nonnegative"),
        CheckConstraint("(timestamp_precision = 'exact_time' AND observed_at IS NOT NULL) OR (timestamp_precision = 'date_only' AND observed_at IS NULL AND observed_date IS NOT NULL)", name="ck_observation_timestamp_precision"),
        CheckConstraint("timestamp_precision IN ('exact_time', 'date_only')", name="ck_observation_timestamp_precision_value"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("renal_patients.id", ondelete="CASCADE"), nullable=False)
    measurement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    timestamp_precision: Mapped[str] = mapped_column(String(16), nullable=False, default="exact_time", server_default="exact_time")
    source_sequence_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str | None] = mapped_column(String(128))
    note: Mapped[str | None] = mapped_column(String(500))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    source_system: Mapped[str | None] = mapped_column(String(32))
    source_subject_id: Mapped[str | None] = mapped_column(String(64))
    source_observation_id: Mapped[str | None] = mapped_column(String(64))
    source_item_id: Mapped[str | None] = mapped_column(String(32))
    source_original_label: Mapped[str | None] = mapped_column(String(200))
    source_original_value: Mapped[str | None] = mapped_column(String(200))
    source_original_numeric_value: Mapped[float | None] = mapped_column(Float)
    source_original_unit: Mapped[str | None] = mapped_column(String(32))
    source_charttime_text: Mapped[str | None] = mapped_column(String(40))
    source_timestamp_timezone: Mapped[str | None] = mapped_column(String(80))
    source_encounter_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    patient = relationship("Patient", back_populates="observations")


@event.listens_for(RenalObservation, "before_insert")
def set_observation_precision_defaults(mapper, connection, observation):
    """Keep legacy ORM writers exact-time by default; never anchor date-only events."""
    precision = observation.timestamp_precision or "exact_time"
    observation.timestamp_precision = precision
    if precision == "exact_time":
        if observation.observed_at is None:
            raise ValueError("exact_time observations require observed_at")
        if observation.observed_date is None:
            value = observation.observed_at
            observation.observed_date = value.astimezone(timezone.utc).date() if value.tzinfo else value.date()
        observation.source_sequence_number = None
    elif precision == "date_only":
        if observation.observed_at is not None or observation.observed_date is None:
            raise ValueError("date_only observations require observed_date and must not have observed_at")
    else:
        raise ValueError("timestamp_precision must be exact_time or date_only")

class TwinUpdateHistory(Base):
    __tablename__ = "renal_twin_updates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("renal_patients.id", ondelete="CASCADE"), index=True)
    latest_observation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class TwinState(Base):
    __tablename__ = "renal_twin_states"
    patient_id: Mapped[int] = mapped_column(ForeignKey("renal_patients.id", ondelete="CASCADE"), primary_key=True)
    latest_observation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

class Scenario(Base):
    __tablename__ = "renal_scenarios"
    __table_args__ = (CheckConstraint("horizon_months >= 1 AND horizon_months <= 120", name="ck_scenario_horizon"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("renal_patients.id", ondelete="CASCADE"), index=True)
    baseline_observation_id: Mapped[int] = mapped_column(ForeignKey("renal_observations.id", ondelete="RESTRICT"))
    assumptions: Mapped[dict] = mapped_column(JSON, nullable=False)
    horizon_months: Mapped[int] = mapped_column(Integer, nullable=False)
    output: Mapped[dict] = mapped_column(JSON, nullable=False)
    limitations: Mapped[list] = mapped_column(JSON, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

from datetime import date
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from api.models import Base, Patient, RenalObservation
from api.routes.renal_twin import _ambiguous_same_day_dates, _serialize_observation


def test_date_only_observation_serializes_date_sequence_and_null_timestamp():
    row = SimpleNamespace(
        id=5, patient_id=12, measurement_type="systolic_bp", value=120, unit="mmHg",
        observed_at=None, observed_date=date(2150, 1, 3), timestamp_precision="date_only",
        source_sequence_number=2, source="MIMIC-IV v3.1 OMR", note="date only",
        created_at=None, source_system="MIMIC-IV-v3.1", source_observation_id="omr:2:systolic_bp",
        source_item_id=None, source_original_label="Blood Pressure Sitting",
        source_charttime_text="2150-01-03", source_timestamp_timezone=None,
        source_original_value="120/70",
    )
    payload = _serialize_observation(row)
    assert payload["observed_at"] is None
    assert payload["observed_date"] == "2150-01-03"
    assert payload["timestamp_precision"] == "date_only"
    assert payload["source_sequence_number"] == 2
    assert payload["source_timestamp_timezone"] is None


def test_exact_time_serialization_remains_utc_timestamp():
    from datetime import datetime, timezone

    row = SimpleNamespace(
        id=6, patient_id=12, measurement_type="egfr", value=60, unit="mL/min/1.73m2",
        observed_at=datetime(2150, 1, 3, 9, tzinfo=timezone.utc), observed_date=date(2150, 1, 3),
        timestamp_precision="exact_time", source_sequence_number=None, source=None, note=None,
        created_at=None, source_system=None, source_observation_id=None, source_item_id=None,
        source_original_label=None, source_charttime_text=None, source_timestamp_timezone=None,
        source_original_value=None,
    )
    payload = _serialize_observation(row)
    assert payload["observed_at"] == "2150-01-03T09:00:00Z"
    assert payload["observed_date"] == "2150-01-03"
    assert payload["timestamp_precision"] == "exact_time"


def test_mixed_precision_query_marks_same_day_measurement_ambiguous():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            patient = Patient(patient_code="date-precision-test")
            session.add(patient)
            session.flush()
            session.add_all([
                RenalObservation(patient_id=patient.id, measurement_type="systolic_bp", value=120, unit="mmHg",
                                 observed_at=None, observed_date=date(2150, 1, 3), timestamp_precision="date_only",
                                 source_sequence_number=1),
                RenalObservation(patient_id=patient.id, measurement_type="systolic_bp", value=122, unit="mmHg",
                                 observed_at=__import__("datetime").datetime(2150, 1, 3, 9),
                                 observed_date=date(2150, 1, 3), timestamp_precision="exact_time"),
            ])
            session.flush()
            ambiguous_dates = _ambiguous_same_day_dates(session, patient.id)
            assert (date(2150, 1, 3), "systolic_bp") in ambiguous_dates
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from api.database import Base
from api.models import Patient, RenalObservation, TwinState, TwinUpdateHistory
from api.renal_twin import ALGORITHM_VERSION, compute_state


def _database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_import_transaction_rolls_back_patient_and_observation():
    engine = _database()
    with Session(engine) as session:
        with pytest.raises(RuntimeError):
            with session.begin():
                patient = Patient(patient_code="TEST-ROLLBACK", source_system="MIMIC-IV-v3.1", source_patient_id="test-only")
                session.add(patient)
                session.flush()
                session.add(RenalObservation(patient_id=patient.id, measurement_type="creatinine", value=1.0,
                    unit="mg/dL", observed_at=datetime(2020, 1, 1), source_system="MIMIC-IV-v3.1",
                    source_observation_id="test-only-event"))
                raise RuntimeError("simulate failed import batch")
        assert session.scalar(select(func.count()).select_from(Patient)) == 0
        assert session.scalar(select(func.count()).select_from(RenalObservation)) == 0
    engine.dispose()


def test_persisted_twin_state_recomputes_from_imported_observations():
    engine = _database()
    observed_at = datetime(2020, 1, 1)
    with Session(engine) as session, session.begin():
        patient = Patient(patient_code="TEST-STATE", source_system="MIMIC-IV-v3.1", source_patient_id="test-only")
        session.add(patient)
        session.flush()
        session.add_all([
            RenalObservation(patient_id=patient.id, measurement_type="creatinine", value=1.0, unit="mg/dL",
                observed_at=observed_at, source_system="MIMIC-IV-v3.1", source_observation_id="test-event-1"),
            RenalObservation(patient_id=patient.id, measurement_type="creatinine", value=1.2, unit="mg/dL",
                observed_at=observed_at + timedelta(days=1), source_system="MIMIC-IV-v3.1", source_observation_id="test-event-2"),
        ])
        session.flush()
        state = compute_state(session.scalars(select(RenalObservation).where(RenalObservation.patient_id == patient.id)).all(),
            now=observed_at + timedelta(days=2))
        session.add(TwinState(patient_id=patient.id, latest_observation_at=observed_at + timedelta(days=1),
            state_snapshot=state, algorithm_version=ALGORITHM_VERSION))
        session.add(TwinUpdateHistory(patient_id=patient.id, latest_observation_at=observed_at + timedelta(days=1),
            state_snapshot=state, algorithm_version=ALGORITHM_VERSION, reason="mimic_cohort_import", warnings=state["warnings"]))
    with Session(engine) as session:
        stored = session.get(TwinState, 1)
        assert stored.state_snapshot["measurements"]["creatinine"]["count"] == 2
        assert session.scalar(select(func.count()).select_from(TwinUpdateHistory)) == 1
    engine.dispose()

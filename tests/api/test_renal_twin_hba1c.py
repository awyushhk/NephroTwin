from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.database import Base, get_session
from api.main import app
from api.models import Patient, RenalObservation, TwinState
from api.renal_twin import validate_measurement
from api.schemas_renal import ObservationCreate


def test_hba1c_observation_api_serializes_orders_and_keeps_missing_missing():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_session():
        with test_sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with test_sessions.begin() as session:
            with_data = Patient(patient_code="TEST-HBA1C", source_system="MIMIC-IV-v3.1", source_patient_id="test-hba1c")
            without_data = Patient(patient_code="TEST-NO-HBA1C", source_system="MIMIC-IV-v3.1", source_patient_id="test-no-hba1c")
            session.add_all([with_data, without_data])
            session.flush()
            hba_rows = [
                RenalObservation(patient_id=with_data.id, measurement_type="hba1c", value=6.2, unit="%", observed_at=datetime(2020, 5, 3, 9, 0), source="test source"),
                RenalObservation(patient_id=with_data.id, measurement_type="hba1c", value=6.8, unit="%", observed_at=datetime(2021, 2, 11, 14, 30), source="test source"),
            ]
            old_creatinine = RenalObservation(patient_id=without_data.id, measurement_type="creatinine", value=1.1, unit="mg/dL", observed_at=datetime(2020, 1, 1), source="test source")
            old_snapshot = TwinState(patient_id=without_data.id, latest_observation_at=datetime(2020, 1, 1),
                state_snapshot={"measurements": {"creatinine": {"latest": {"value": 1.1}}}}, algorithm_version="renal-twin-0.9")
            session.add_all([*hba_rows, old_creatinine, old_snapshot])
            patient_id, empty_patient_id = with_data.id, without_data.id
        payload = ObservationCreate(measurement_type="hba1c", value=6.5, unit="%", observed_at="2022-01-01T00:00:00Z")
        assert payload.measurement_type == "hba1c"
        assert validate_measurement(payload.measurement_type, payload.value, payload.unit)[1] is None
        with TestClient(app) as client:
            history = client.get(
                f"/api/renal-twin/patients/{patient_id}/observations?limit=10&recent=true&measurement_type=hba1c"
            )
            assert history.status_code == 200
            rows = history.json()
            assert [row["value"] for row in rows] == [6.2, 6.8]
            assert rows[-1]["observed_at"].startswith("2021-02-11T14:30:00")
            state = client.get(f"/api/renal-twin/patients/{patient_id}/state").json()
            assert state["measurements"]["hba1c"]["latest"]["value"] == 6.8
            assert state["measurements"]["hba1c"]["count"] == 2

            empty_history = client.get(
                f"/api/renal-twin/patients/{empty_patient_id}/observations?measurement_type=hba1c"
            )
            assert empty_history.status_code == 200
            assert empty_history.json() == []
            empty_state = client.get(f"/api/renal-twin/patients/{empty_patient_id}/state").json()
            assert empty_state["measurements"]["hba1c"]["latest"] is None
            assert empty_state["measurements"]["hba1c"]["count"] == 0
            with test_sessions() as session:
                persisted = session.get(TwinState, empty_patient_id)
                assert "hba1c" not in persisted.state_snapshot["measurements"]
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()

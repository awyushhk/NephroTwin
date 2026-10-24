"""Database utility commands: python -m api.db_cli check|seed-synthetic"""
import os
import sys
from datetime import datetime, timezone
from sqlalchemy import select
from api.database import verify_database, make_session_factory
from api.models import Patient, RenalObservation

def seed_synthetic():
    if os.getenv("ENVIRONMENT", "development").lower() in {"production", "prod"}:
        raise RuntimeError("Synthetic seed data is disabled in production.")
    _, factory = make_session_factory()
    with factory.begin() as session:
        profiles = [
            ("SYNTH-IRREGULAR", [("egfr", 78, "2025-01-01T09:00:00+00:00"), ("egfr", 72, "2025-04-20T10:30:00+00:00"), ("acr", 42, "2025-04-20T10:35:00+00:00"), ("egfr", 69, "2025-11-03T08:00:00+00:00"), ("egfr", 70, "2025-08-10T11:00:00+00:00")]),
            ("SYNTH-SINGLE", [("egfr", 54, "2026-02-14T12:00:00+00:00")]),
            ("SYNTH-SPARSE", [("systolic_bp", 128, "2025-06-02T08:00:00+00:00"), ("diastolic_bp", 78, "2025-06-02T08:05:00+00:00")]),
        ]
        for code, observations in profiles:
            patient = session.scalar(select(Patient).where(Patient.patient_code == code))
            if patient is None:
                patient = Patient(patient_code=code, profile_metadata={"synthetic": True})
                session.add(patient); session.flush()
            for kind, value, when in observations:
                dt = datetime.fromisoformat(when)
                duplicate = session.scalar(select(RenalObservation.id).where(RenalObservation.patient_id == patient.id, RenalObservation.measurement_type == kind, RenalObservation.observed_at == dt))
                if duplicate is None:
                    unit = "mL/min/1.73m2" if kind == "egfr" else "mg/g" if kind == "acr" else "mmHg"
                    session.add(RenalObservation(patient_id=patient.id, measurement_type=kind, value=value, unit=unit, observed_at=dt, source="synthetic development example", idempotency_key=f"seed:{code}:{kind}:{when}"))
    print("Synthetic records seeded (repeatable). They are labeled SYNTH-* and are not real patient data.")

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "check"
    if action == "check":
        verify_database(); print("PostgreSQL connection verified.")
    elif action == "seed-synthetic":
        verify_database(); seed_synthetic()
    else:
        raise SystemExit("Usage: python -m api.db_cli check|seed-synthetic")

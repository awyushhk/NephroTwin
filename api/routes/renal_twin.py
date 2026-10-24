"""Persistent patient observations and deterministic renal twin APIs."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from api.database import get_session
from api.models import Patient, RenalObservation, TwinState, TwinUpdateHistory, Scenario
from api.schemas_renal import PatientCreate, ObservationCreate, ScenarioCreate
from api.renal_twin import ALGORITHM_VERSION, MEASUREMENTS, compute_state, simulate_egfr, validate_measurement

router = APIRouter(prefix="/renal-twin", tags=["Renal Digital Twin"])
MIMIC_SOURCE_SYSTEM = "MIMIC-IV-v3.1"

def db_error(exc):
    raise HTTPException(status_code=503, detail="PostgreSQL unavailable. Verify DATABASE_URL, credentials, service status, and migrations.") from exc

def rebuild(session, patient_id, reason):
    patient = session.get(Patient, patient_id)
    rows = list(session.scalars(select(RenalObservation).where(RenalObservation.patient_id == patient_id).order_by(RenalObservation.observed_at, RenalObservation.id)))
    # MIMIC charttimes are shifted/deidentified and can lie after the host date.
    # Use the dataset's latest event as its as-of point without changing source times.
    as_of = max((row.observed_at for row in rows), default=datetime.now(timezone.utc)) if patient and patient.source_system == MIMIC_SOURCE_SYSTEM else datetime.now(timezone.utc)
    rows = [row for row in rows if row.observed_at <= as_of]
    snapshot = compute_state(rows, now=as_of)
    latest = datetime.fromisoformat(snapshot["latest_observation_at"]) if snapshot["latest_observation_at"] else None
    state = session.get(TwinState, patient_id)
    if state is None:
        state = TwinState(patient_id=patient_id, state_snapshot=snapshot, algorithm_version=ALGORITHM_VERSION, latest_observation_at=latest)
        session.add(state)
    else:
        state.state_snapshot, state.algorithm_version, state.latest_observation_at = snapshot, ALGORITHM_VERSION, latest
    session.add(TwinUpdateHistory(patient_id=patient_id, latest_observation_at=latest, state_snapshot=snapshot,
                                  algorithm_version=ALGORITHM_VERSION, reason=reason, warnings=snapshot["warnings"]))
    return snapshot

@router.get("/patients")
def patients(session: Session = Depends(get_session)):
    try:
        patient_rows = session.scalars(select(Patient).order_by(Patient.id)).all()
        counts = dict(session.execute(select(RenalObservation.patient_id, func.count(RenalObservation.id))
                                      .group_by(RenalObservation.patient_id)).all())
        return [{"id": p.id, "patient_code": p.patient_code, "created_at": p.created_at,
                 "observation_count": counts.get(p.id, 0)} for p in patient_rows]
    except SQLAlchemyError as exc: db_error(exc)

@router.post("/patients", status_code=201)
def create_patient(payload: PatientCreate, session: Session = Depends(get_session)):
    try:
        patient = Patient(patient_code=payload.patient_code, profile_metadata=payload.profile_metadata)
        session.add(patient); session.commit(); session.refresh(patient)
        return {"id": patient.id, "patient_code": patient.patient_code, "created_at": patient.created_at, "observation_count": 0}
    except IntegrityError as exc:
        session.rollback(); raise HTTPException(409, "Patient code already exists.") from exc
    except SQLAlchemyError as exc: session.rollback(); db_error(exc)

@router.get("/patients/{patient_id}")
def patient(patient_id: int, session: Session = Depends(get_session)):
    obj = session.get(Patient, patient_id)
    if not obj: raise HTTPException(404, "Patient not found.")
    return {"id": obj.id, "patient_code": obj.patient_code, "created_at": obj.created_at, "observation_count": len(obj.observations)}

@router.get("/patients/{patient_id}/observations")
def observations(patient_id: int, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), recent: bool = Query(False), measurement_type: str | None = Query(None), session: Session = Depends(get_session)):
    if not session.get(Patient, patient_id): raise HTTPException(404, "Patient not found.")
    if measurement_type is not None and measurement_type not in MEASUREMENTS:
        raise HTTPException(422, "Unsupported measurement type.")
    order = (desc(RenalObservation.observed_at), desc(RenalObservation.id)) if recent else (RenalObservation.observed_at, RenalObservation.id)
    statement = select(RenalObservation).where(RenalObservation.patient_id == patient_id)
    if measurement_type is not None:
        statement = statement.where(RenalObservation.measurement_type == measurement_type)
    rows = session.scalars(statement.order_by(*order).offset(offset).limit(limit)).all()
    if recent:
        rows.reverse()
    return [{"id": x.id, "patient_id": x.patient_id, "measurement_type": x.measurement_type, "value": x.value, "unit": x.unit, "observed_at": x.observed_at, "source": x.source, "note": x.note, "created_at": x.created_at} for x in rows]

@router.post("/patients/{patient_id}/observations", status_code=201)
def add_observation(patient_id: int, payload: ObservationCreate, session: Session = Depends(get_session)):
    if not session.get(Patient, patient_id): raise HTTPException(404, "Patient not found.")
    try: warnings, _ = validate_measurement(payload.measurement_type, payload.value, payload.unit)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    observed = payload.observed_at
    if observed.tzinfo is None: raise HTTPException(422, "observed_at must include a timezone offset.")
    if observed.astimezone(timezone.utc) > datetime.now(timezone.utc): raise HTTPException(422, "Observation time cannot be in the future.")
    try:
        row = RenalObservation(patient_id=patient_id, measurement_type=payload.measurement_type, value=payload.value, unit=payload.unit,
                               observed_at=observed.astimezone(timezone.utc), source=payload.source, note=payload.note, idempotency_key=payload.idempotency_key)
        session.add(row); session.flush()
        snapshot = rebuild(session, patient_id, "observation_added")
        session.commit(); session.refresh(row)
        return {"observation": {"id": row.id, "patient_id": row.patient_id, "measurement_type": row.measurement_type,
                "value": row.value, "unit": row.unit, "observed_at": row.observed_at, "source": row.source, "note": row.note, "created_at": row.created_at},
                "state": snapshot, "warnings": warnings}
    except IntegrityError as exc:
        session.rollback(); raise HTTPException(409, "Duplicate idempotency key for this patient.") from exc
    except SQLAlchemyError as exc: session.rollback(); db_error(exc)

@router.get("/patients/{patient_id}/state")
def state(patient_id: int, session: Session = Depends(get_session)):
    obj = session.get(Patient, patient_id)
    if not obj: raise HTTPException(404, "Patient not found.")
    if not obj.observations: return compute_state([])
    item = session.get(TwinState, patient_id)
    if item: return item.state_snapshot
    rows = list(session.scalars(select(RenalObservation).where(RenalObservation.patient_id == patient_id).order_by(RenalObservation.observed_at, RenalObservation.id)))
    as_of = max((row.observed_at for row in rows), default=datetime.now(timezone.utc)) if obj.source_system == MIMIC_SOURCE_SYSTEM else datetime.now(timezone.utc)
    return compute_state(rows, now=as_of)

@router.post("/patients/{patient_id}/update")
def update(patient_id: int, session: Session = Depends(get_session)):
    if not session.get(Patient, patient_id): raise HTTPException(404, "Patient not found.")
    try:
        result = rebuild(session, patient_id, "manual_recompute"); session.commit(); return result
    except SQLAlchemyError as exc: session.rollback(); db_error(exc)

@router.get("/patients/{patient_id}/history")
def history(patient_id: int, session: Session = Depends(get_session)):
    if not session.get(Patient, patient_id): raise HTTPException(404, "Patient not found.")
    rows = session.scalars(select(TwinUpdateHistory).where(TwinUpdateHistory.patient_id == patient_id).order_by(TwinUpdateHistory.created_at.desc()).limit(100)).all()
    return [{"id": r.id, "updated_at": r.created_at, "latest_observation_at": r.latest_observation_at, "algorithm_version": r.algorithm_version, "reason": r.reason, "source_observation_ids": r.state_snapshot["source_observation_ids"], "warnings": r.warnings} for r in rows]

@router.post("/patients/{patient_id}/scenarios", status_code=201)
def create_scenario(patient_id: int, payload: ScenarioCreate, session: Session = Depends(get_session)):
    if not session.get(Patient, patient_id): raise HTTPException(404, "Patient not found.")
    baseline = session.get(RenalObservation, payload.baseline_observation_id)
    if not baseline or baseline.patient_id != patient_id: raise HTTPException(404, "Baseline observation not found for this patient.")
    if baseline.measurement_type != "egfr": raise HTTPException(422, "Scenario baseline must be an observed eGFR result.")
    result = simulate_egfr(baseline.value, payload.rate_per_year, payload.horizon_months)
    scenario = Scenario(patient_id=patient_id, baseline_observation_id=baseline.id,
        assumptions={"rate_per_year": payload.rate_per_year, "unit": "mL/min/1.73m2 per year", "step_months": 1},
        horizon_months=payload.horizon_months, output=result, limitations=result["warnings"], algorithm_version=ALGORITHM_VERSION)
    try:
        session.add(scenario); session.commit(); session.refresh(scenario)
        return {"id": scenario.id, "patient_id": patient_id, "baseline_observation_id": baseline.id, "assumptions": scenario.assumptions,
                "horizon_months": scenario.horizon_months, "output": scenario.output, "limitations": scenario.limitations,
                "algorithm_version": scenario.algorithm_version, "created_at": scenario.created_at}
    except SQLAlchemyError as exc: session.rollback(); db_error(exc)

@router.get("/patients/{patient_id}/scenarios")
def scenarios(patient_id: int, session: Session = Depends(get_session)):
    if not session.get(Patient, patient_id): raise HTTPException(404, "Patient not found.")
    return [{"id": s.id, "baseline_observation_id": s.baseline_observation_id, "assumptions": s.assumptions, "horizon_months": s.horizon_months, "output": s.output, "limitations": s.limitations, "created_at": s.created_at} for s in session.scalars(select(Scenario).where(Scenario.patient_id == patient_id).order_by(Scenario.created_at.desc())).all()]

@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: int, session: Session = Depends(get_session)):
    s = session.get(Scenario, scenario_id)
    if not s: raise HTTPException(404, "Scenario not found.")
    return {"id": s.id, "patient_id": s.patient_id, "baseline_observation_id": s.baseline_observation_id, "assumptions": s.assumptions, "horizon_months": s.horizon_months, "output": s.output, "limitations": s.limitations, "algorithm_version": s.algorithm_version, "created_at": s.created_at}

@router.delete("/patients/{patient_id}/scenarios/{scenario_id}", status_code=204)
def delete_scenario(patient_id: int, scenario_id: int, session: Session = Depends(get_session)):
    scenario = session.get(Scenario, scenario_id)
    if not scenario or scenario.patient_id != patient_id: raise HTTPException(404, "Scenario not found for this patient.")
    session.delete(scenario)
    session.commit()

"""Persistent patient observations and deterministic renal twin APIs."""
from datetime import date, datetime, timezone
from collections import defaultdict
import os
import uuid
from types import SimpleNamespace
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, desc, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from api.database import get_session
from api.models import Patient, RenalObservation, TwinState, TwinUpdateHistory, Scenario
from api.schemas_renal import NephroQSimulationCreate, PatientCreate, ObservationCreate, ScenarioComparisonCreate, ScenarioCreate
from api.renal_twin import ALGORITHM_VERSION, MEASUREMENTS, compute_observability, compute_state, observation_date, observation_order_key, observation_payload, observation_precision, simulate_egfr, utc_datetime, utc_iso, validate_measurement

router = APIRouter(prefix="/renal-twin", tags=["Renal Digital Twin"])
MIMIC_SOURCE_SYSTEM = "MIMIC-IV-v3.1"

def _setting(name, default, minimum, maximum):
    try: value = int(os.getenv(name, str(default)))
    except ValueError: value = default
    return min(maximum, max(minimum, value))

def db_error(exc):
    raise HTTPException(status_code=503, detail="PostgreSQL unavailable. Verify DATABASE_URL, credentials, service status, and migrations.") from exc


def _ordered_rows(session, patient_id, measurement_type=None):
    statement = select(RenalObservation).where(RenalObservation.patient_id == patient_id)
    if measurement_type is not None:
        statement = statement.where(RenalObservation.measurement_type == measurement_type)
    return sorted(session.scalars(statement).all(), key=observation_order_key)


def _as_of_for_patient(patient, rows):
    if patient and patient.source_system == MIMIC_SOURCE_SYSTEM and rows:
        if any(observation_precision(row) == "date_only" for row in rows):
            return max(observation_date(row) for row in rows)
        return max(utc_datetime(row.observed_at) for row in rows)
    return datetime.now(timezone.utc)


def _serialize_observation(row, ambiguous_dates=frozenset()):
    return {
        "id": row.id, "patient_id": row.patient_id,
        "measurement_type": row.measurement_type, "value": row.value, "unit": row.unit,
        **observation_payload(row),
        "same_day_ordering_ambiguous": (observation_date(row), row.measurement_type) in ambiguous_dates,
        "source": row.source, "note": row.note, "created_at": utc_iso(row.created_at),
        "source_system": row.source_system, "source_observation_id": row.source_observation_id,
        "source_item_id": row.source_item_id, "source_original_label": row.source_original_label,
        "source_charttime_text": row.source_charttime_text,
        "source_timestamp_timezone": row.source_timestamp_timezone,
        "source_original_value": row.source_original_value,
    }


def _ambiguous_same_day_dates(session, patient_id, measurement_type=None):
    precision_count = func.count(func.distinct(RenalObservation.timestamp_precision))
    statement = select(RenalObservation.observed_date, RenalObservation.measurement_type).where(RenalObservation.patient_id == patient_id)
    if measurement_type is not None:
        statement = statement.where(RenalObservation.measurement_type == measurement_type)
    statement = statement.group_by(RenalObservation.observed_date, RenalObservation.measurement_type).having(precision_count > 1)
    return set(session.execute(statement).all())

def rebuild(session, patient_id, reason):
    patient = session.get(Patient, patient_id)
    rows = _ordered_rows(session, patient_id)
    # MIMIC charttimes are shifted/deidentified and can lie after the host date.
    # Use the dataset's latest event as its as-of point without changing source times.
    as_of = _as_of_for_patient(patient, rows)
    snapshot = compute_state(rows, now=as_of)
    latest = datetime.fromisoformat(snapshot["latest_observation_at"].replace("Z", "+00:00")) if snapshot["latest_observation_at"] else None
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
                 "source_system": p.source_system, "observation_count": counts.get(p.id, 0)} for p in patient_rows]
    except SQLAlchemyError as exc: db_error(exc)

@router.get("/patients/recommended-examples")
def recommended_example_patients(session: Session = Depends(get_session)):
    """Find rich MIMIC profiles currently eligible for the NephroQ example mode."""
    try:
        from api.nephroq import REQUIRED_INPUTS, rank_example_profiles

        patient_rows = session.scalars(
            select(Patient).where(Patient.source_system == MIMIC_SOURCE_SYSTEM).order_by(Patient.id)
        ).all()
        counts_by_patient = defaultdict(dict)
        for patient_id, kind, count in session.execute(
            select(RenalObservation.patient_id, RenalObservation.measurement_type, func.count(RenalObservation.id))
            .where(RenalObservation.patient_id.in_([patient.id for patient in patient_rows]))
            .group_by(RenalObservation.patient_id, RenalObservation.measurement_type)
        ):
            counts_by_patient[patient_id][kind] = int(count)
        candidate_ids = [
            patient_id for patient_id, counts in counts_by_patient.items()
            if all(counts.get(kind, 0) for kind in REQUIRED_INPUTS)
        ]
        if not candidate_ids:
            return []

        observations_by_patient = defaultdict(list)
        selected = session.execute(
            select(
                RenalObservation.patient_id, RenalObservation.id, RenalObservation.measurement_type,
                RenalObservation.value, RenalObservation.unit, RenalObservation.observed_at,
                RenalObservation.observed_date, RenalObservation.timestamp_precision,
                RenalObservation.source_sequence_number, RenalObservation.source,
                RenalObservation.source_observation_id,
            ).where(
                RenalObservation.patient_id.in_(candidate_ids),
                RenalObservation.measurement_type.in_(tuple(REQUIRED_INPUTS)),
            )
        )
        for row in selected:
            patient_id, ident, kind, value, unit, observed_at, observed_date, precision, sequence, source, source_id = row
            observations_by_patient[patient_id].append(SimpleNamespace(
                id=ident, patient_id=patient_id, measurement_type=kind, value=value, unit=unit,
                observed_at=observed_at, observed_date=observed_date, timestamp_precision=precision,
                source_sequence_number=sequence, source=source, source_observation_id=source_id,
            ))

        return rank_example_profiles(
            patient_rows, counts_by_patient, observations_by_patient,
            _setting("RENAL_OBSERVABILITY_STALE_DAYS", 90, 1, 10000),
        )
    except SQLAlchemyError as exc:
        db_error(exc)

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
    return {"id": obj.id, "patient_code": obj.patient_code, "source_system": obj.source_system, "created_at": obj.created_at, "observation_count": len(obj.observations)}

@router.get("/patients/{patient_id}/observations")
def observations(patient_id: int, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), recent: bool = Query(False), measurement_type: str | None = Query(None), session: Session = Depends(get_session)):
    if not session.get(Patient, patient_id): raise HTTPException(404, "Patient not found.")
    if measurement_type is not None and measurement_type not in MEASUREMENTS:
        raise HTTPException(422, "Unsupported measurement type.")
    statement = select(RenalObservation).where(RenalObservation.patient_id == patient_id)
    if measurement_type is not None:
        statement = statement.where(RenalObservation.measurement_type == measurement_type)
    order = (
        (desc(RenalObservation.observed_date), desc(case((RenalObservation.timestamp_precision == "exact_time", 0), else_=1)), desc(RenalObservation.observed_at), desc(RenalObservation.source_sequence_number), desc(RenalObservation.id))
        if recent else
        (RenalObservation.observed_date, case((RenalObservation.timestamp_precision == "exact_time", 0), else_=1), RenalObservation.observed_at, RenalObservation.source_sequence_number, RenalObservation.id)
    )
    rows = session.scalars(statement.order_by(*order).offset(offset).limit(limit)).all()
    if recent:
        rows.reverse()
    ambiguous_dates = _ambiguous_same_day_dates(session, patient_id, measurement_type)
    return [_serialize_observation(x, ambiguous_dates) for x in rows]

@router.get("/patients/{patient_id}/analysis")
def analysis(patient_id: int, trend_window_days: int = Query(365, ge=0, le=10000), session: Session = Depends(get_session)):
    patient = session.get(Patient, patient_id)
    if not patient: raise HTTPException(404, "Patient not found.")
    rows = _ordered_rows(session, patient_id)
    as_of = _as_of_for_patient(patient, rows)
    return compute_observability(
        rows,
        source_system=patient.source_system,
        as_of=as_of,
        trend_window_days=trend_window_days,
        recent_window_days=_setting("RENAL_OBSERVABILITY_RECENT_DAYS", 30, 1, 3650),
        historical_window_days=_setting("RENAL_OBSERVABILITY_HISTORICAL_DAYS", 365, 1, 10000),
        minimum_trend_observations=_setting("RENAL_TREND_MIN_OBSERVATIONS", 3, 2, 100),
        minimum_trend_span_days=_setting("RENAL_TREND_MIN_SPAN_DAYS", 30, 1, 10000),
        stale_after_days=_setting("RENAL_OBSERVABILITY_STALE_DAYS", 90, 1, 10000),
    )

@router.get("/patients/{patient_id}/trajectory/eligibility")
@router.get("/patients/{patient_id}/nephroq/eligibility", include_in_schema=False)
def nephroq_eligibility(patient_id: int, baseline_observation_id: int | None = Query(None, gt=0), session: Session = Depends(get_session)):
    if not session.get(Patient, patient_id):
        raise HTTPException(404, "Patient not found.")
    rows = _ordered_rows(session, patient_id)
    from api.nephroq import assess_nephroq_inputs
    return assess_nephroq_inputs(rows, baseline_observation_id, _setting("RENAL_OBSERVABILITY_STALE_DAYS", 90, 1, 10000))

@router.post("/patients/{patient_id}/trajectory")
@router.post("/patients/{patient_id}/nephroq", include_in_schema=False)
def nephroq_simulation(patient_id: int, payload: NephroQSimulationCreate, session: Session = Depends(get_session)):
    patient_obj = session.get(Patient, patient_id)
    if not patient_obj:
        raise HTTPException(404, "Patient not found.")
    rows = _ordered_rows(session, patient_id)
    try:
        from api.nephroq import NephroQInputError, simulate_nephroq
        return simulate_nephroq(rows, patient_id, payload.years, payload.baseline_observation_id,
                                _setting("RENAL_OBSERVABILITY_STALE_DAYS", 90, 1, 10000))
    except NephroQInputError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc

@router.post("/patients/{patient_id}/observations", status_code=201)
def add_observation(patient_id: int, payload: ObservationCreate, session: Session = Depends(get_session)):
    if not session.get(Patient, patient_id): raise HTTPException(404, "Patient not found.")
    try: warnings, _ = validate_measurement(payload.measurement_type, payload.value, payload.unit)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    observed = payload.observed_at
    if observed.tzinfo is None: raise HTTPException(422, "observed_at must include a timezone offset.")
    if observed.astimezone(timezone.utc) > datetime.now(timezone.utc): raise HTTPException(422, "Observation time cannot be in the future.")
    try:
        event_time = observed.astimezone(timezone.utc)
        row = RenalObservation(patient_id=patient_id, measurement_type=payload.measurement_type, value=payload.value, unit=payload.unit,
                               observed_at=event_time, observed_date=event_time.date(), timestamp_precision="exact_time",
                               source=payload.source, note=payload.note, idempotency_key=payload.idempotency_key)
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
    # Older persisted snapshots may predate a newly supported measurement (for
    # example hba1c). Rebuild in memory so the API returns a complete shape;
    # do not persist a read-time refresh or alter the stored audit history.
    if item and set(MEASUREMENTS).issubset(item.state_snapshot.get("measurements", {})):
        return item.state_snapshot
    rows = _ordered_rows(session, patient_id)
    as_of = _as_of_for_patient(obj, rows)
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
    rows = list(session.scalars(select(TwinUpdateHistory).where(TwinUpdateHistory.patient_id == patient_id).order_by(TwinUpdateHistory.created_at.desc()).limit(100)).all())
    chronological = list(reversed(rows))
    observation_ids = sorted({ident for row in chronological for ident in row.state_snapshot.get("source_observation_ids", [])})
    observation_lookup = {row.id: row for row in session.scalars(select(RenalObservation).where(RenalObservation.id.in_(observation_ids))).all()} if observation_ids else {}
    result = []
    previous = None
    for row in chronological:
        ids = row.state_snapshot.get("source_observation_ids", [])
        changed = []
        new_ids = None
        late_arrival = None
        if previous is not None:
            previous_ids = set(previous.state_snapshot.get("source_observation_ids", []))
            added_ids = set(ids) - previous_ids
            new_ids = sorted(added_ids)
            previous_latest_day = previous.state_snapshot.get("latest_observation_date")
            if previous_latest_day is None and previous.latest_observation_at:
                previous_latest_day = utc_datetime(previous.latest_observation_at).date().isoformat()
            added_dates = [observation_date(observation_lookup[ident]) for ident in added_ids if ident in observation_lookup]
            if previous_latest_day and any(day and day.isoformat() < previous_latest_day for day in added_dates):
                late_arrival = True
            elif previous_latest_day and any(day and day.isoformat() == previous_latest_day and observation_precision(observation_lookup[ident]) == "date_only" for ident in added_ids if ident in observation_lookup):
                late_arrival = None
            else:
                late_arrival = False if previous_latest_day else None
            before = previous.state_snapshot.get("measurements", {})
            after = row.state_snapshot.get("measurements", {})
            for kind in MEASUREMENTS:
                old, new = before.get(kind, {}), after.get(kind, {})
                for field, old_value, new_value in (
                    ("latest.value", (old.get("latest") or {}).get("value"), (new.get("latest") or {}).get("value")),
                    ("latest.observed_at", (old.get("latest") or {}).get("observed_at"), (new.get("latest") or {}).get("observed_at")),
                    ("count", old.get("count"), new.get("count")),
                    ("category", old.get("category"), new.get("category")),
                    ("change", old.get("change"), new.get("change")),
                ):
                    if old_value != new_value: changed.append(f"{kind}.{field}")
        contributing_sample = [{"observation_id": ident, "source_observation_id": observation_lookup[ident].source_observation_id}
                               for ident in ids[:20] if ident in observation_lookup]
        new_sample = ([{"observation_id": ident, "source_observation_id": observation_lookup[ident].source_observation_id}
                       for ident in new_ids[:20] if ident in observation_lookup] if new_ids is not None else None)
        result.append({"id": row.id, "updated_at": utc_iso(row.created_at), "latest_observation_at": utc_iso(row.latest_observation_at),
            "latest_observation_date": row.state_snapshot.get("latest_observation_date"),
            "algorithm_version": row.algorithm_version, "reason": row.reason, "source_observation_ids": ids,
            "contributing_observation_count": len(ids), "contributing_observations_sample": contributing_sample,
            "comparison_available": previous is not None, "new_observation_count": len(new_ids) if new_ids is not None else None,
            "new_observations_sample": new_sample,
            "late_historical_observation": late_arrival, "changed_summary_values": changed if previous is not None else None,
            "warnings": row.warnings})
        previous = row
    return list(reversed(result))

@router.post("/patients/{patient_id}/scenarios", status_code=201)
def create_scenario(patient_id: int, payload: ScenarioCreate, session: Session = Depends(get_session)):
    if not session.get(Patient, patient_id): raise HTTPException(404, "Patient not found.")
    baseline = session.get(RenalObservation, payload.baseline_observation_id)
    if not baseline or baseline.patient_id != patient_id: raise HTTPException(404, "Baseline observation not found for this patient.")
    if baseline.measurement_type != "egfr": raise HTTPException(422, "Scenario baseline must be an observed eGFR result.")
    result = simulate_egfr(baseline.value, payload.rate_per_year, payload.horizon_months)
    scenario = Scenario(patient_id=patient_id, baseline_observation_id=baseline.id,
        assumptions={"rate_per_year": payload.rate_per_year, "unit": "mL/min/1.73m2 per year", "step_months": 1,
                     "comparison_group_id": payload.comparison_group_id, "scenario_label": payload.scenario_label,
                     "comparison_index": payload.comparison_index},
        horizon_months=payload.horizon_months, output=result, limitations=result["warnings"], algorithm_version=ALGORITHM_VERSION)
    try:
        session.add(scenario); session.commit(); session.refresh(scenario)
        return {"id": scenario.id, "patient_id": patient_id, "baseline_observation_id": baseline.id, "assumptions": scenario.assumptions,
                "horizon_months": scenario.horizon_months, "output": scenario.output, "limitations": scenario.limitations,
                "algorithm_version": scenario.algorithm_version, "created_at": scenario.created_at}
    except SQLAlchemyError as exc: session.rollback(); db_error(exc)

@router.post("/patients/{patient_id}/scenarios/compare", status_code=201)
def create_scenario_comparison(patient_id: int, payload: ScenarioComparisonCreate, session: Session = Depends(get_session)):
    if not session.get(Patient, patient_id): raise HTTPException(404, "Patient not found.")
    baseline = session.get(RenalObservation, payload.baseline_observation_id)
    if not baseline or baseline.patient_id != patient_id: raise HTTPException(404, "Baseline observation not found for this patient.")
    if baseline.measurement_type != "egfr": raise HTTPException(422, "Scenario baseline must be an observed eGFR result.")
    comparison_group_id = str(uuid.uuid4())
    pending = []
    for index, item in enumerate(payload.scenarios):
        output = simulate_egfr(baseline.value, item.rate_per_year, payload.horizon_months)
        scenario = Scenario(
            patient_id=patient_id,
            baseline_observation_id=baseline.id,
            assumptions={"rate_per_year": item.rate_per_year, "unit": "mL/min/1.73m2 per year", "step_months": 1,
                         "comparison_group_id": comparison_group_id, "scenario_label": item.label.strip(), "comparison_index": index},
            horizon_months=payload.horizon_months,
            output=output,
            limitations=output["warnings"],
            algorithm_version=ALGORITHM_VERSION,
        )
        session.add(scenario)
        pending.append(scenario)
    try:
        session.flush()
        result = [{"id": scenario.id, "patient_id": patient_id, "baseline_observation_id": baseline.id,
                   "assumptions": scenario.assumptions, "horizon_months": scenario.horizon_months,
                   "output": scenario.output, "limitations": scenario.limitations,
                   "algorithm_version": scenario.algorithm_version} for scenario in pending]
        session.commit()
        return {"comparison_group_id": comparison_group_id, "scenarios": result}
    except SQLAlchemyError as exc:
        session.rollback()
        db_error(exc)

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

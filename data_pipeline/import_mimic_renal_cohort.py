"""Import validated processed MIMIC cohort CSVs. Writes require --execute."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from data_pipeline.mimic_renal_cohort import DEFAULT_OUTPUT, SOURCE_SYSTEM, STD_UNITS, parse_numeric, parse_timestamp, validate_directory

DB_SOURCE = "MIMIC-IV-v3.1"
BATCH_SIZE = 1000

def _chunks(iterable, size):
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch; batch = []
    if batch: yield batch

def _session_stack():
    try:
        from sqlalchemy import inspect, select, text
        from sqlalchemy.orm import Session
        from api.database import make_session_factory
        from api.models import Patient, RenalObservation, TwinState, TwinUpdateHistory
        from api.renal_twin import ALGORITHM_VERSION, compute_state
    except ImportError as exc:
        raise RuntimeError("Install API dependencies first: python -m pip install -r api/requirements.txt") from exc
    engine, factory = make_session_factory()
    if engine.url.database != "renal_twin_db":
        raise RuntimeError(f"Refusing to inspect/import database {engine.url.database!r}; expected the configured renal_twin_db database.")
    version = None
    with engine.connect() as connection:
        if "alembic_version" in inspect(engine).get_table_names():
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    if version != "0003_timestamp_provenance_length":
        raise RuntimeError(f"Database migration 0003_timestamp_provenance_length is required before import (current revision: {version!r}). Run `alembic upgrade head` after reviewing the additive migrations.")
    return select, factory, Patient, RenalObservation, TwinState, TwinUpdateHistory, ALGORITHM_VERSION, compute_state

def _parse_valid_observation(row):
    measure = row["canonical_measurement"]
    value = parse_numeric(row["standardized_value"])
    chart = parse_timestamp(row["charttime"])
    source_id = row["source_observation_id"].strip()
    unit = row["standardized_unit"]
    if measure not in STD_UNITS or value is None or chart is None or not source_id or unit != STD_UNITS[measure]:
        return None
    # MIMIC charttime has no source timezone. UTC is used only as the database's
    # deterministic storage convention; source_charttime_text and timezone provenance retain the source semantics.
    return value, chart.replace(tzinfo=timezone.utc), source_id

def source_observation_matches(existing, row, value, patient_id):
    """Idempotency comparison is exact over source-identifying and clinical fields."""
    return (
        existing.patient_id == patient_id
        and existing.source_system == DB_SOURCE
        and existing.source_subject_id == row["source_subject_id"]
        and existing.value == value
        and existing.unit == row["standardized_unit"]
        and existing.measurement_type == row["canonical_measurement"]
        and existing.source_item_id == row["mimic_item_id"]
        and existing.source_original_label == row["original_lab_label"]
        and existing.source_original_value == row["original_value"][:200]
        and existing.source_original_numeric_value == parse_numeric(row["original_numeric_value"])
        and existing.source_original_unit == row["original_unit"][:32]
        and existing.source_charttime_text == row["charttime"][:40]
        and existing.source_encounter_id == (row["hadm_id"] or None)
    )

def import_cohort(directory: Path, execute: bool = False) -> dict:
    validation = validate_directory(directory)
    select, factory, Patient, Observation, TwinState, TwinUpdateHistory, algorithm_version, compute_state = _session_stack()
    patients_rows = list(csv.DictReader((directory / "patients.csv").open("r", encoding="utf-8", newline="")))
    if not patients_rows:
        raise RuntimeError("Processed cohort contains no selected patients.")
    by_subject = {row["source_subject_id"]: row for row in patients_rows}
    counts = {"patients_to_insert": 0, "patients_existing": 0, "observations_to_insert": 0, "inserted": 0, "updated": 0, "skipped": 0, "duplicate_observations": 0, "failed": 0, "state_recomputed": 0, "invalid_processed_rows_skipped": 0}
    conflicts = []
    import_patient_ids: dict[str, int] = {}
    patients_with_new_rows: set[int] = set()
    latest_source_time: dict[int, datetime] = {}
    with factory() as session:
        tx = session.begin() if execute else None
        try:
            subjects = list(by_subject)
            for subject_batch in _chunks(subjects, BATCH_SIZE):
                existing_source = {p.source_patient_id: p for p in session.scalars(select(Patient).where(Patient.source_system == DB_SOURCE, Patient.source_patient_id.in_(subject_batch))).all()}
                codes = ["MIMIC31-" + subject for subject in subject_batch]
                existing_codes = {p.patient_code: p for p in session.scalars(select(Patient).where(Patient.patient_code.in_(codes))).all()}
                for subject in subject_batch:
                    found = existing_source.get(subject)
                    code = "MIMIC31-" + subject
                    code_owner = existing_codes.get(code)
                    if found:
                        import_patient_ids[subject] = found.id
                        counts["patients_existing"] += 1
                    elif code_owner:
                        conflicts.append({"subject_id": subject, "reason": "patient_code already belongs to a profile with no matching MIMIC source identity"})
                        counts["failed"] += 1
                    elif execute:
                        obj = Patient(patient_code=code, profile_metadata={"cohort": "MIMIC-IV v3.1 curated research cohort"}, source_system=DB_SOURCE, source_patient_id=subject)
                        session.add(obj); session.flush()
                        import_patient_ids[subject] = obj.id
                        counts["patients_to_insert"] += 1
                    else:
                        # Negative IDs are dry-run placeholders; no objects are added.
                        import_patient_ids[subject] = -int(subject)
                        counts["patients_to_insert"] += 1

            pending = []
            with (directory / "renal_observations.csv").open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    parsed = _parse_valid_observation(row)
                    subject = row["source_subject_id"]
                    if parsed is None:
                        counts["invalid_processed_rows_skipped"] += 1; counts["skipped"] += 1
                        continue
                    value, chart, source_id = parsed
                    if subject not in import_patient_ids:
                        # Existing patient-code conflict, do not attach any observation.
                        if not execute and not any(c["subject_id"] == subject for c in conflicts):
                            counts["failed"] += 1; conflicts.append({"subject_id": subject, "reason": "no source patient identity was resolved"})
                        else:
                            counts["skipped"] += 1
                        continue
                    pending.append((row, value, chart, source_id, subject))
                    if len(pending) >= BATCH_SIZE:
                        _process_observation_batch(session, select, Observation, pending, execute, counts, conflicts, import_patient_ids, patients_with_new_rows, latest_source_time)
                        pending = []
                if pending:
                    _process_observation_batch(session, select, Observation, pending, execute, counts, conflicts, import_patient_ids, patients_with_new_rows, latest_source_time)

            if execute:
                patient_ids = sorted(patients_with_new_rows)
                states = {item.patient_id: item for item in session.scalars(select(TwinState).where(TwinState.patient_id.in_(patient_ids))).all()}
                current_patient_id = None
                current_observations = []

                def persist_state(patient_id, observations):
                    # MIMIC dates are deidentified and may be in the future relative to the host clock.
                    # Recompute at the last imported source event, never against wall-clock dates.
                    as_of = max(item.observed_at for item in observations)
                    snapshot = compute_state(observations, now=as_of)
                    latest_at = datetime.fromisoformat(snapshot["latest_observation_at"]) if snapshot["latest_observation_at"] else None
                    state = states.get(patient_id)
                    if state:
                        state.latest_observation_at = latest_at; state.state_snapshot = snapshot; state.algorithm_version = algorithm_version
                    else:
                        state = TwinState(patient_id=patient_id, latest_observation_at=latest_at, state_snapshot=snapshot, algorithm_version=algorithm_version)
                        session.add(state); states[patient_id] = state
                    session.add(TwinUpdateHistory(patient_id=patient_id, latest_observation_at=latest_at, state_snapshot=snapshot,
                        algorithm_version=algorithm_version, reason="mimic_iv_v3_1_cohort_import", warnings=snapshot["warnings"]))
                    counts["state_recomputed"] += 1

                # One ordered server-side cursor avoids hundreds of separate history queries while
                # retaining only one patient's observations in Python at a time.
                statement = select(Observation).where(Observation.patient_id.in_(patient_ids)).order_by(Observation.patient_id, Observation.observed_at, Observation.id)
                for observation in session.scalars(statement.execution_options(yield_per=10000)):
                    if current_patient_id is not None and observation.patient_id != current_patient_id:
                        persist_state(current_patient_id, current_observations)
                        for previous in current_observations:
                            session.expunge(previous)
                        current_observations = []
                    current_patient_id = observation.patient_id
                    current_observations.append(observation)
                if current_observations:
                    persist_state(current_patient_id, current_observations)
                    for observation in current_observations:
                        session.expunge(observation)
                tx.commit()
        except Exception:
            if tx and tx.is_active: tx.rollback()
            raise
    counts["observations_to_insert"] = counts["inserted"] if execute else counts["observations_to_insert"]
    return {"mode": "execute" if execute else "dry_run_no_writes", "database": "renal_twin_db", "processed_validation": validation, "counts": counts, "conflicts": conflicts[:100], "conflicts_truncated": max(0, len(conflicts)-100), "policy": "Existing matching source identity/content is skipped; any mismatch is reported and never overwritten. Other source rows remain untouched."}

def _process_observation_batch(session, select, Observation, batch, execute, counts, conflicts, patient_ids, patients_with_new_rows, latest_source_time):
    source_ids = [item[3] for item in batch]
    existing = {o.source_observation_id: o for o in session.scalars(select(Observation).where(Observation.source_system == DB_SOURCE, Observation.source_observation_id.in_(source_ids))).all()}
    created = []
    for row, value, chart, source_id, subject in batch:
        patient_id = patient_ids[subject]
        old = existing.get(source_id)
        if old:
            if source_observation_matches(old, row, value, patient_id): counts["skipped"] += 1; counts["duplicate_observations"] += 1
            else:
                counts["failed"] += 1
                conflicts.append({"source_observation_id": source_id, "subject_id": subject, "reason": "source observation ID exists with different patient/value/unit/item/time; existing row was not changed"})
            continue
        if execute:
            obj = Observation(patient_id=patient_id, measurement_type=row["canonical_measurement"], value=value, unit=row["standardized_unit"],
                observed_at=chart, source="MIMIC-IV v3.1 labevents", note=row["validation_flags"][:500] or None,
                idempotency_key=f"mimiciv31:labevent:{source_id}", source_system=DB_SOURCE, source_subject_id=subject, source_observation_id=source_id,
                source_item_id=row["mimic_item_id"], source_original_label=row["original_lab_label"], source_original_value=row["original_value"][:200],
                source_original_numeric_value=parse_numeric(row["original_numeric_value"]), source_original_unit=row["original_unit"][:32],
                source_charttime_text=row["charttime"][:40], source_timestamp_timezone="unspecified; UTC used as storage convention", source_encounter_id=row["hadm_id"] or None)
            session.add(obj); created.append(obj); counts["inserted"] += 1; patients_with_new_rows.add(patient_id)
            latest_source_time[patient_id] = max(latest_source_time.get(patient_id, chart), chart)
        else:
            counts["observations_to_insert"] += 1
    if execute and created:
        # Keep the transaction atomic while bounding pending ORM objects to one input batch.
        session.flush()
        for obj in created:
            session.expunge(obj)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--execute", action="store_true", help="Commit imports. Without this flag, perform a no-write preview.")
    args = parser.parse_args(argv)
    try:
        result = import_cohort(args.processed_dir, execute=args.execute)
        print(json.dumps(result, indent=2, sort_keys=True))
        if not args.execute:
            print("Dry run only: no database records were changed. Add --execute only after reviewing the cohort and this conflict report.")
        return 0 if not result["counts"]["failed"] else 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())

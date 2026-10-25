"""Import validated processed MIMIC cohort CSVs. Writes require --execute."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from data_pipeline.mimic_renal_cohort import DEFAULT_OUTPUT, SOURCE_SYSTEM, STD_UNITS, parse_numeric, parse_timestamp, validate_directory
from api.renal_twin import observation_date, observation_precision
from api.renal_twin import validate_measurement

DB_SOURCE = "MIMIC-IV-v3.1"
BATCH_SIZE = 1000
OMR_BP_LABELS = {"Blood Pressure", "Blood Pressure Lying", "Blood Pressure Sitting", "Blood Pressure Standing", "Blood Pressure Standing (1 min)", "Blood Pressure Standing (3 mins)"}

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
    if version != "0004_date_precision_observations":
        raise RuntimeError(f"Database migration 0004_date_precision_observations is required before import (current revision: {version!r}). Run `alembic upgrade head` after reviewing the additive migrations.")
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
        and getattr(existing, "timestamp_precision", "exact_time") == "exact_time"
        and getattr(existing, "observed_date", parse_timestamp(row["charttime"]).date()) == parse_timestamp(row["charttime"]).date()
    )


def omr_component_records(row: dict) -> list[dict]:
    """Expand one validated source BP reading into two date-only observation payloads."""
    day = date.fromisoformat(row["chartdate"])
    sequence = int(row["seq_num"])
    source_id = row["source_observation_id"]
    record_number = int(row["source_record_number"])
    if sequence < 1 or record_number < 1:
        raise ValueError("OMR seq_num and source record number must be positive integers")
    if not source_id or source_id != f"omr:{record_number}":
        raise ValueError("OMR source observation key does not match its stable source record number")
    if row.get("timestamp_precision") != "date_only; no time recorded":
        raise ValueError("OMR source row lacks the date-only precision marker")
    if row.get("original_result_name") not in OMR_BP_LABELS:
        raise ValueError("OMR result label is not in the supported blood-pressure label set")
    if row.get("systolic_unit") != "mmHg" or row.get("diastolic_unit") != "mmHg":
        raise ValueError("OMR BP components must both be normalized to mmHg")
    systolic, diastolic = float(row["systolic_value"]), float(row["diastolic_value"])
    validate_measurement("systolic_bp", systolic, "mmHg")
    validate_measurement("diastolic_bp", diastolic, "mmHg")
    if systolic <= diastolic:
        raise ValueError("OMR systolic value must exceed diastolic value")
    original_pair = [part.strip() for part in row.get("original_result_value", "").split("/")]
    if len(original_pair) != 2 or float(original_pair[0]) != systolic or float(original_pair[1]) != diastolic:
        raise ValueError("Standardized BP components do not match the original combined source value")
    original_value = row.get("original_result_value", "")
    label = row.get("original_result_name", "")
    return [
        {
            "measurement_type": measurement,
            "value": systolic if value_field == "systolic_value" else diastolic,
            "unit": "mmHg",
            "observed_at": None,
            "observed_date": day,
            "timestamp_precision": "date_only",
            "source_sequence_number": sequence,
            "source_system": DB_SOURCE,
            "source_subject_id": row["source_subject_id"],
            "source_observation_id": f"{source_id}:{measurement}",
            "source_original_label": label,
            "source_original_value": original_value[:200],
            "source_original_numeric_value": None,
            "source_original_unit": None,
            "source_charttime_text": day.isoformat(),
            "source_timestamp_timezone": None,
            "source": "MIMIC-IV v3.1 OMR",
            "note": f"Date-only OMR reading; seq_num={sequence}; no measurement time supplied.",
            "idempotency_key": f"mimiciv31:{source_id}:{measurement}",
            "source_item_id": None,
            "source_encounter_id": None,
            "value_field": value_field,
        }
        for measurement, value_field in (("systolic_bp", "systolic_value"), ("diastolic_bp", "diastolic_value"))
    ]


def omr_source_observation_matches(existing, payload, patient_id):
    return (
        existing.patient_id == patient_id
        and existing.measurement_type == payload["measurement_type"]
        and existing.value == payload["value"]
        and existing.unit == payload["unit"]
        and existing.observed_at is None
        and existing.observed_date == payload["observed_date"]
        and existing.timestamp_precision == "date_only"
        and existing.source_sequence_number == payload["source_sequence_number"]
        and existing.source_system == payload["source_system"]
        and existing.source_subject_id == payload["source_subject_id"]
        and existing.source_observation_id == payload["source_observation_id"]
        and existing.source_original_label == payload["source_original_label"]
        and existing.source_original_value == payload["source_original_value"]
        and existing.source_charttime_text == payload["source_charttime_text"]
        and existing.source_timestamp_timezone is None
        and existing.source == payload["source"]
        and existing.note == payload["note"]
    )


def import_omr_bp_file(observations_file: Path, patients_file: Path = DEFAULT_OUTPUT / "patients.csv", execute: bool = False) -> dict:
    """Import only processed date-aware OMR output; no raw source is opened here."""
    from sqlalchemy import case, select
    from api.models import Patient, RenalObservation, TwinState, TwinUpdateHistory
    from api.renal_twin import ALGORITHM_VERSION, compute_state, observation_date, observation_order_key, observation_precision

    observations_file, patients_file = observations_file.resolve(), patients_file.resolve()
    if not observations_file.is_file() or not patients_file.is_file():
        raise FileNotFoundError("Processed OMR observations.csv and cohort patients.csv are required")
    patient_rows = {row["source_subject_id"]: row for row in csv.DictReader(patients_file.open(encoding="utf-8", newline=""))}
    if not patient_rows:
        raise ValueError("Fixed cohort patient map is empty")
    select_fn, factory, Patient, Observation, TwinState, TwinUpdateHistory, algorithm_version, compute = _session_stack()
    counts = {"source_readings": 0, "component_rows_expected": 0, "inserted": 0, "skipped": 0, "conflicts": 0, "invalid_rows": 0, "patients_existing": 0, "patients_missing": 0, "state_recomputed": 0}
    conflict_samples = []
    touched_patients: set[int] = set()
    patient_ids: dict[str, int] = {}
    seen_source_ids: set[str] = set()
    pending = []

    def process_batch(session, batch):
        ids = [payload["source_observation_id"] for _, _, payload in batch]
        existing = {item.source_observation_id: item for item in session.scalars(select_fn(Observation).where(
            Observation.source_system == DB_SOURCE, Observation.source_observation_id.in_(ids)
        )).all()}
        created = []
        for row, subject, payload in batch:
            patient_id = patient_ids.get(subject)
            if patient_id is None:
                counts["conflicts"] += 1
                if len(conflict_samples) < 20:
                    conflict_samples.append({"source_observation_id": payload["source_observation_id"], "reason": "fixed cohort patient profile is absent"})
                continue
            old = existing.get(payload["source_observation_id"])
            if old:
                if omr_source_observation_matches(old, payload, patient_id):
                    counts["skipped"] += 1
                else:
                    counts["conflicts"] += 1
                    if len(conflict_samples) < 20:
                        conflict_samples.append({"source_observation_id": payload["source_observation_id"], "reason": "existing source identity has different data; preserved without overwrite"})
                continue
            if execute:
                payload = {key: value for key, value in payload.items() if key != "value_field"}
                item = Observation(patient_id=patient_id, **payload)
                session.add(item)
                created.append(item)
                counts["inserted"] += 1
                touched_patients.add(patient_id)
            else:
                counts["component_rows_expected"] += 1
        if execute and created:
            session.flush()
            for item in created:
                session.expunge(item)

    with factory() as session:
        tx = session.begin() if execute else None
        try:
            subjects = list(patient_rows)
            for subject_batch in _chunks(subjects, BATCH_SIZE):
                found = {p.source_patient_id: p.id for p in session.scalars(select_fn(Patient).where(
                    Patient.source_system == DB_SOURCE, Patient.source_patient_id.in_(subject_batch)
                )).all()}
                patient_ids.update(found)
                counts["patients_existing"] += len(found)
                missing_subjects = set(subject_batch) - set(found)
                counts["patients_missing"] += len(missing_subjects)
                counts["conflicts"] += len(missing_subjects)
                for subject in sorted(missing_subjects):
                    if len(conflict_samples) < 20:
                        conflict_samples.append({"source_subject_id": subject, "reason": "fixed cohort patient profile is absent"})
            with observations_file.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    counts["source_readings"] += 1
                    subject = row.get("source_subject_id", "")
                    if subject not in patient_rows:
                        counts["invalid_rows"] += 1
                        continue
                    try:
                        payloads = omr_component_records(row)
                    except (KeyError, TypeError, ValueError):
                        counts["invalid_rows"] += 1
                        continue
                    for payload in payloads:
                        source_id = payload["source_observation_id"]
                        if source_id in seen_source_ids:
                            counts["invalid_rows"] += 1
                            continue
                        seen_source_ids.add(source_id)
                        pending.append((row, subject, payload))
                        if len(pending) >= BATCH_SIZE:
                            process_batch(session, pending)
                            pending = []
                if pending:
                    process_batch(session, pending)
                    pending = []
            if execute and counts["invalid_rows"]:
                raise RuntimeError(f"Refusing OMR insert: {counts['invalid_rows']} processed rows failed validation")
            if execute and touched_patients:
                patient_batch = sorted(touched_patients)
                event_order = (RenalObservation.observed_date, case((RenalObservation.timestamp_precision == "exact_time", 0), else_=1), RenalObservation.observed_at, RenalObservation.source_sequence_number, RenalObservation.id)
                statement = select_fn(Observation).where(Observation.patient_id.in_(patient_batch)).order_by(Observation.patient_id, *event_order)
                current_patient_id = None
                current_rows = []

                def persist_state(patient_id, rows):
                    rows.sort(key=observation_order_key)
                    as_of = max(observation_date(row) for row in rows) if any(observation_precision(row) == "date_only" for row in rows) else max(row.observed_at for row in rows)
                    snapshot = compute(rows, now=as_of)
                    latest_at = datetime.fromisoformat(snapshot["latest_observation_at"].replace("Z", "+00:00")) if snapshot.get("latest_observation_at") else None
                    state = session.get(TwinState, patient_id)
                    if state:
                        state.state_snapshot = snapshot
                        state.algorithm_version = algorithm_version
                        state.latest_observation_at = latest_at
                    else:
                        session.add(TwinState(patient_id=patient_id, state_snapshot=snapshot, algorithm_version=algorithm_version, latest_observation_at=latest_at))
                    session.add(TwinUpdateHistory(patient_id=patient_id, latest_observation_at=latest_at, state_snapshot=snapshot,
                        algorithm_version=algorithm_version, reason="mimic_iv_v3_1_omr_bp_import", warnings=snapshot["warnings"]))
                    counts["state_recomputed"] += 1

                for item in session.scalars(statement.execution_options(yield_per=10000)):
                    if current_patient_id is not None and item.patient_id != current_patient_id:
                        persist_state(current_patient_id, current_rows)
                        for previous in current_rows:
                            session.expunge(previous)
                        current_rows = []
                    current_patient_id = item.patient_id
                    current_rows.append(item)
                if current_rows:
                    persist_state(current_patient_id, current_rows)
                    for item in current_rows:
                        session.expunge(item)
            if execute:
                tx.commit()
        except Exception:
            if tx and tx.is_active:
                tx.rollback()
            raise
    return {"mode": "execute" if execute else "dry_run_no_writes", "database": "renal_twin_db", "source_file": str(observations_file),
            "raw_omr_read": False, "database_writes": execute, "counts": counts, "conflicts_sample": conflict_samples,
            "conflicts_truncated": max(0, counts["conflicts"] - len(conflict_samples)),
            "policy": "Matching source identities are skipped; conflicts are preserved and never overwritten. OMR events remain date-only with seq_num; state recomputation occurs only after successful --execute."}

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
                from sqlalchemy import case

                patient_ids = sorted(patients_with_new_rows)
                states = {item.patient_id: item for item in session.scalars(select(TwinState).where(TwinState.patient_id.in_(patient_ids))).all()}
                current_patient_id = None
                current_observations = []

                def persist_state(patient_id, observations):
                    # MIMIC dates are deidentified and may be in the future relative to the host clock.
                    # Recompute at the last imported source event, never against wall-clock dates.
                    if any(observation_precision(item) == "date_only" for item in observations):
                        as_of = max(observation_date(item) for item in observations)
                    else:
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
                event_order = (
                    Observation.observed_date,
                    case((Observation.timestamp_precision == "exact_time", 0), else_=1),
                    Observation.observed_at,
                    Observation.source_sequence_number,
                    Observation.id,
                )
                statement = select(Observation).where(Observation.patient_id.in_(patient_ids)).order_by(Observation.patient_id, *event_order)
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
                observed_at=chart, observed_date=chart.date(), timestamp_precision="exact_time", source="MIMIC-IV v3.1 labevents", note=row["validation_flags"][:500] or None,
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
    parser.add_argument("--omr-bp-file", type=Path, help="Import only the processed date-aware OMR observations.csv")
    parser.add_argument("--omr-cohort-file", type=Path, default=DEFAULT_OUTPUT / "patients.csv", help="Fixed cohort patients.csv used to validate OMR membership")
    parser.add_argument("--execute", action="store_true", help="Commit imports. Without this flag, perform a no-write preview.")
    args = parser.parse_args(argv)
    try:
        if args.omr_bp_file:
            result = import_omr_bp_file(args.omr_bp_file, args.omr_cohort_file, execute=args.execute)
        else:
            result = import_cohort(args.processed_dir, execute=args.execute)
        print(json.dumps(result, indent=2, sort_keys=True))
        if not args.execute:
            print("Dry run only: no database records were changed. Add --execute only after reviewing the cohort and this conflict report.")
        counts = result["counts"]
        failed = counts.get("failed")
        if failed is None:
            # OMR preview reports these categories separately; it has no
            # aggregate `failed` field like the cohort importer.
            failed = counts.get("conflicts", 0) + counts.get("invalid_rows", 0)
        return 0 if not failed else 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())

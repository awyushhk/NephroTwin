"""Read-only preview of OMR BP insertion identity and current schema compatibility."""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path

from sqlalchemy import select

from data_pipeline.extract_mimic_omr_blood_pressure import DEFAULT_COHORT, DEFAULT_OUTPUT, load_cohort

DB_SOURCE = "MIMIC-IV-v3.1"
BATCH_SIZE = 1000


def preview(processed: Path = DEFAULT_OUTPUT, cohort_file: Path = DEFAULT_COHORT) -> dict:
    processed, cohort_file = processed.resolve(), cohort_file.resolve()
    observation_file = processed / "observations.csv"
    audit_file = processed / "audit.json"
    if not observation_file.is_file() or not audit_file.is_file():
        raise FileNotFoundError("Run the OMR BP extractor before requesting an import preview")
    cohort = load_cohort(cohort_file)
    audit = json.loads(audit_file.read_text(encoding="utf-8"))
    if audit["patient_coverage"]["fixed_cohort_patients"] != len(cohort):
        raise ValueError("Processed audit cohort size differs from the fixed patients.csv")

    try:
        from api.database import make_session_factory
        from api.models import Patient, RenalObservation
    except ImportError as exc:
        raise RuntimeError("Install API requirements before checking the configured database") from exc
    engine, factory = make_session_factory()
    if engine.url.database != "renal_twin_db":
        engine.dispose()
        raise RuntimeError(f"Read-only preview refuses configured database {engine.url.database!r}; expected renal_twin_db")

    from sqlalchemy import inspect

    columns = {column["name"]: column for column in inspect(engine).get_columns("renal_observations")}
    observed_at = columns.get("observed_at")
    precision_supported = {"observed_date", "timestamp_precision", "source_sequence_number"}.issubset(columns)
    migration_revision = None
    if "alembic_version" in inspect(engine).get_table_names():
        from sqlalchemy import text
        with engine.connect() as connection:
            migration_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    timestamp_schema = {
        "observed_at_exists": observed_at is not None,
        "observed_at_nullable": bool(observed_at["nullable"]) if observed_at else None,
        "observed_at_type": str(observed_at["type"]) if observed_at else None,
        "date_precision_columns_exist": precision_supported,
        "supports_date_precision_without_time": bool(observed_at and observed_at["nullable"] and precision_supported),
        "alembic_revision": migration_revision,
    }
    patients_existing = 0
    patients_conflicting = 0
    rows_read = 0
    component_count = 0
    duplicate_source_ids = 0
    colliding_observations = 0
    collision_samples: list[str] = []
    seen_source_ids: set[str] = set()
    patient_conflicts: list[str] = []
    pending_ids: list[str] = []
    matched_subjects: set[str] = set()
    batch_subjects = list(cohort)

    try:
        with factory() as session:
            for start in range(0, len(batch_subjects), BATCH_SIZE):
                subject_batch = batch_subjects[start:start + BATCH_SIZE]
                found = set(session.scalars(select(Patient.source_patient_id).where(
                    Patient.source_system == DB_SOURCE, Patient.source_patient_id.in_(subject_batch)
                )).all())
                matched_subjects.update(found)
                patients_existing += len(found)
                missing = set(subject_batch) - found
                patients_conflicting += len(missing)
                patient_conflicts.extend(sorted(missing)[:10 - len(patient_conflicts)])

            def check_id_batch(ids: list[str]) -> None:
                nonlocal colliding_observations
                if not ids:
                    return
                existing = set(session.scalars(select(RenalObservation.source_observation_id).where(
                    RenalObservation.source_system == DB_SOURCE,
                    RenalObservation.source_observation_id.in_(ids),
                )).all())
                colliding_observations += len(existing)
                collision_samples.extend(sorted(existing)[:max(0, 10 - len(collision_samples))])

            with observation_file.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                required = {"source_subject_id", "source_observation_id", "source_record_number", "chartdate", "timestamp_precision", "seq_num", "systolic_value", "systolic_unit", "diastolic_value", "diastolic_unit"}
                if not reader.fieldnames or not required.issubset(reader.fieldnames):
                    raise ValueError("OMR observations CSV schema is incomplete")
                for row in reader:
                    rows_read += 1
                    subject = row["source_subject_id"]
                    if subject not in cohort:
                        raise ValueError(f"Observation references non-cohort subject {subject}")
                    if row["timestamp_precision"] != "date_only; no time recorded":
                        raise ValueError("An observation is missing its date-only precision marker")
                    date.fromisoformat(row["chartdate"])
                    if not row["seq_num"]:
                        raise ValueError("Source row is missing seq_num")
                    if row["systolic_unit"] != "mmHg" or row["diastolic_unit"] != "mmHg":
                        raise ValueError("Unexpected normalized BP unit")
                    base_id = row["source_observation_id"]
                    if not base_id or base_id in seen_source_ids:
                        duplicate_source_ids += 1
                        continue
                    seen_source_ids.add(base_id)
                    # Existing generic observation storage requires one row per measure.
                    component_ids = [f"{base_id}:sbp", f"{base_id}:dbp"]
                    component_count += 2
                    pending_ids.extend(component_ids)
                    if len(pending_ids) >= BATCH_SIZE:
                        check_id_batch(pending_ids)
                        pending_ids = []
            check_id_batch(pending_ids)
            audit_rows = int(audit["cohort_rows"]["valid_readings"])
            if rows_read != audit_rows:
                raise ValueError(f"Observations CSV has {rows_read} rows but audit reports {audit_rows}")
            target_profiles = session.scalar(select(Patient.id).limit(1)) is not None
    finally:
        engine.dispose()

    return {
        "target_database": "renal_twin_db",
        "database_writes": False,
        "source_file_read": str(observation_file),
        "raw_omr_file_read": False,
        "fixed_cohort_patients": len(cohort),
        "matching_existing_mimic_patient_profiles": patients_existing,
        "patient_id_conflicts_or_missing_profiles": patients_conflicting,
        "patient_conflict_sample": patient_conflicts,
        "valid_source_bp_readings": rows_read,
        "expected_component_observation_rows_if_imported": component_count,
        "expected_measurement_counts": {"systolic_bp": rows_read, "diastolic_bp": rows_read},
        "duplicate_source_reading_ids_in_file": duplicate_source_ids,
        "existing_observation_source_id_collisions": colliding_observations,
        "source_id_collision_sample": collision_samples,
        "timestamp_schema": timestamp_schema,
        "database_has_any_patient": target_profiles,
        "preview_status": "ready_for_review" if observed_at and observed_at["nullable"] and precision_supported and migration_revision == "0004_date_precision_observations" else "blocked_date_precision_migration_not_applied",
        "reason": None if observed_at and observed_at["nullable"] and precision_supported and migration_revision == "0004_date_precision_observations" else "Apply the reviewed date-precision migration first; date-only records must keep observed_at null and retain observed_date plus source seq_num.",
        "database_schema_changed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cohort-file", type=Path, default=DEFAULT_COHORT)
    args = parser.parse_args()
    print(json.dumps(preview(args.processed_dir, args.cohort_file), indent=2))


if __name__ == "__main__":
    main()

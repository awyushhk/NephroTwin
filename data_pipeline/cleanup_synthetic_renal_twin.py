"""Safely remove only records created by api.db_cli.seed_synthetic."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from sqlalchemy import func, select, text

from api.database import make_session_factory
from api.models import Patient, RenalObservation, Scenario, TwinState, TwinUpdateHistory

SEED_OBSERVATIONS = {
    "SYNTH-IRREGULAR": 5,
    "SYNTH-SINGLE": 1,
    "SYNTH-SPARSE": 2,
}
DEFAULT_BACKUP = Path("data/backups/renal_twin_db_pre_mimic_replace_20261024.dump")
EXPECTED_BACKUP_SHA256 = "508faf654d4105e01e16daafa6d1acf2d1ff7951e27582d65d2861d7708c79fc"
PG_RESTORE = Path(r"C:\Program Files\PostgreSQL\18\bin\pg_restore.exe")


def _backup_verified(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError(f"Required database backup is missing: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != EXPECTED_BACKUP_SHA256:
        raise RuntimeError(f"Backup checksum mismatch for {path}; refusing cleanup.")
    env = os.environ.copy()
    listing = subprocess.run([str(PG_RESTORE), "--list", str(path)], capture_output=True, text=True, env=env)
    if listing.returncode or "TABLE DATA" not in listing.stdout or "alembic_version" not in listing.stdout:
        raise RuntimeError("pg_restore could not verify required table data and migration metadata in backup.")
    return {"path": str(path.resolve()), "size_bytes": path.stat().st_size, "sha256": digest, "archive_verified": True}


def _inspect(session) -> tuple[list[Patient], dict, dict]:
    # The seed command creates exactly these identity and provenance markers.
    flagged = session.scalars(select(Patient).where(Patient.profile_metadata["synthetic"].as_boolean().is_(True))).all()
    if {p.patient_code for p in flagged} != set(SEED_OBSERVATIONS):
        raise RuntimeError("Synthetic metadata does not identify exactly the three known seed patients; refusing cleanup.")
    patients = session.scalars(select(Patient).where(Patient.patient_code.in_(list(SEED_OBSERVATIONS))).order_by(Patient.id)).all()
    if len(patients) != len(SEED_OBSERVATIONS):
        raise RuntimeError("Known seed patient codes are missing or duplicated; refusing cleanup.")
    for p in patients:
        if p.source_system is not None or p.source_patient_id is not None:
            raise RuntimeError(f"Seed patient {p.patient_code} has source identity; refusing cleanup.")
        obs = session.scalars(select(RenalObservation).where(RenalObservation.patient_id == p.id)).all()
        expected = SEED_OBSERVATIONS[p.patient_code]
        if len(obs) != expected or any(
            o.source != "synthetic development example"
            or not o.idempotency_key
            or not o.idempotency_key.startswith(f"seed:{p.patient_code}:")
            or o.source_system is not None
            or o.source_observation_id is not None
            for o in obs
        ):
            raise RuntimeError(f"Observations for {p.patient_code} do not exactly match seed provenance; refusing cleanup.")
    ids = [p.id for p in patients]
    counts = {
        "patients": len(patients),
        "observations": session.scalar(select(func.count()).select_from(RenalObservation).where(RenalObservation.patient_id.in_(ids))) or 0,
        "states": session.scalar(select(func.count()).select_from(TwinState).where(TwinState.patient_id.in_(ids))) or 0,
        "update_histories": session.scalar(select(func.count()).select_from(TwinUpdateHistory).where(TwinUpdateHistory.patient_id.in_(ids))) or 0,
        "scenarios": session.scalar(select(func.count()).select_from(Scenario).where(Scenario.patient_id.in_(ids))) or 0,
    }
    records = [{"patient_id": p.id, "patient_code": p.patient_code, "seeded_observations": SEED_OBSERVATIONS[p.patient_code]} for p in patients]
    return patients, records, counts


def cleanup(execute: bool, backup: Path = DEFAULT_BACKUP) -> dict:
    backup_report = _backup_verified(backup)
    engine, factory = make_session_factory()
    if engine.url.database != "renal_twin_db":
        raise RuntimeError(f"Refusing database {engine.url.database!r}; expected renal_twin_db.")
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    if revision not in {"0003_timestamp_provenance_length", "0004_date_precision_observations"}:
        raise RuntimeError(f"Unexpected Alembic revision {revision!r}; refusing cleanup.")
    result = {"mode": "execute" if execute else "dry_run_no_writes", "database": "renal_twin_db", "alembic_revision": revision, "backup": backup_report}
    with factory() as session:
        transaction = session.begin() if execute else None
        try:
            patients, records, counts = _inspect(session)
            result.update({"verified_targets": records, "dependent_rows": counts})
            if execute:
                ids = [p.id for p in patients]
                for model in (Scenario, TwinState, TwinUpdateHistory, RenalObservation):
                    session.execute(model.__table__.delete().where(model.patient_id.in_(ids)))
                session.execute(Patient.__table__.delete().where(Patient.id.in_(ids)))
                transaction.commit()
                result["deleted"] = counts
            else:
                result["deleted"] = {key: 0 for key in counts}
        except Exception:
            if transaction and transaction.is_active:
                transaction.rollback()
            raise
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--execute", action="store_true", help="Commit deletion after verifying exact seed provenance and backup checksum.")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(cleanup(args.execute, args.backup), indent=2, sort_keys=True))
        if not args.execute:
            print("Dry run only: no database records were changed.")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

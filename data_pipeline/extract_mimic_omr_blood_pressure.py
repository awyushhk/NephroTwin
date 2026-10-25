"""Extract date-level MIMIC-IV OMR blood-pressure readings for the fixed renal cohort.

This is an extraction-only stage. It intentionally does not create an ``observed_at``
timestamp because OMR supplies a date and same-day sequence, not a measurement time.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import uuid
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.csv as pacsv

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data/raw/omr.csv"
DEFAULT_COHORT = ROOT / "data/processed/mimic_renal_cohort/patients.csv"
DEFAULT_OUTPUT = ROOT / "data/processed/mimic_renal_omr_bp"
BP_LABELS = (
    "Blood Pressure",
    "Blood Pressure Lying",
    "Blood Pressure Sitting",
    "Blood Pressure Standing",
    "Blood Pressure Standing (1 min)",
    "Blood Pressure Standing (3 mins)",
)
REQUIRED_COLUMNS = ("subject_id", "chartdate", "seq_num", "result_name", "result_value")
PAIR_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*$")
OBSERVATION_FIELDS = (
    "internal_patient_id", "source_subject_id", "source_observation_id", "source_record_number",
    "chartdate", "timestamp_precision", "seq_num", "measurement_context", "original_result_name",
    "original_result_value", "systolic_value", "systolic_unit", "diastolic_value", "diastolic_unit",
    "source_table", "source_file", "validation_flags",
)
QUARANTINE_FIELDS = OBSERVATION_FIELDS + ("rejection_reason",)


def load_cohort(path: Path) -> dict[str, str]:
    """Return source subject -> stable internal ID and reject ambiguous mappings."""
    mapping: dict[str, str] = {}
    internal_ids: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"source_subject_id", "internal_patient_id"}.issubset(reader.fieldnames):
            raise ValueError("patients.csv must contain source_subject_id and internal_patient_id columns")
        for row in reader:
            subject = (row.get("source_subject_id") or "").strip()
            internal = (row.get("internal_patient_id") or "").strip()
            if not subject or not internal:
                raise ValueError("Cohort contains a missing source or internal patient identifier")
            if subject in mapping or internal in internal_ids:
                raise ValueError("Cohort patient mapping is not one-to-one")
            mapping[subject] = internal
            internal_ids.add(internal)
    if not mapping:
        raise ValueError("Cohort patient list is empty")
    return mapping


def parse_blood_pressure(value: str | None) -> tuple[float | None, float | None, str | None]:
    """Parse exactly one numeric SBP/DBP pair; reject missing, ambiguous, or implausible values.

    Broad extraction checks are SBP 30..300 mmHg, DBP 10..200 mmHg, and SBP > DBP.
    They are data-quality bounds, not clinical thresholds or a diagnosis.
    """
    raw = (value or "").strip()
    if not raw:
        return None, None, "missing_value"
    match = PAIR_RE.fullmatch(raw)
    if not match:
        if "/" not in raw or raw.count("/") != 1:
            return None, None, "malformed_or_ambiguous_pair"
        return None, None, "nonnumeric_or_malformed_component"
    systolic, diastolic = float(match.group(1)), float(match.group(2))
    if not (math.isfinite(systolic) and math.isfinite(diastolic)):
        return None, None, "nonfinite_component"
    if not (30 <= systolic <= 300 and 10 <= diastolic <= 200 and systolic > diastolic):
        return None, None, "implausible_component_values"
    return systolic, diastolic, None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _date_only(value: str | None) -> bool:
    try:
        date.fromisoformat((value or "").strip())
        return True
    except ValueError:
        return False


def _row_template(row: dict[str, Any], source: Path, subject_to_internal: dict[str, str], record_number: int) -> dict[str, Any]:
    subject = (row.get("subject_id") or "").strip()
    return {
        "internal_patient_id": subject_to_internal[subject],
        "source_subject_id": subject,
        "source_observation_id": f"omr:{record_number}",
        "source_record_number": record_number,
        "chartdate": (row.get("chartdate") or "").strip(),
        "timestamp_precision": "date_only; no time recorded",
        "seq_num": (row.get("seq_num") or "").strip(),
        "measurement_context": (row.get("result_name") or "").strip(),
        "original_result_name": (row.get("result_name") or "").strip(),
        "original_result_value": row.get("result_value") or "",
        "systolic_value": "",
        "systolic_unit": "mmHg",
        "diastolic_value": "",
        "diastolic_unit": "mmHg",
        "source_table": "omr",
        "source_file": str(source),
        "validation_flags": "",
    }


def extract(source: Path = DEFAULT_SOURCE, cohort: Path = DEFAULT_COHORT, output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    """Chunk-scan OMR and atomically publish validated, quarantined, audit, and report files."""
    source, cohort, output = source.resolve(), cohort.resolve(), output.resolve()
    if not source.is_file() or not cohort.is_file():
        raise FileNotFoundError("OMR source and fixed-cohort patients.csv must both exist")
    mapping = load_cohort(cohort)
    source_sha = _sha256(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    staged = {name: output / f".{name}.{token}.tmp" for name in ("observations.csv", "quarantine.csv", "audit.json", "report.md")}
    observations_path = staged["observations.csv"]
    quarantine_path = staged["quarantine.csv"]
    total_rows = 0
    label_counts: Counter[str] = Counter()
    all_bp_counts: Counter[str] = Counter()
    cohort_bp_counts: Counter[str] = Counter()
    selected_quality: Counter[str] = Counter()
    quality_by_label: dict[str, Counter[str]] = {}
    matched_any: set[str] = set()
    matched_valid: set[str] = set()
    valid_dates: list[str] = []
    duplicate_signatures: Counter[tuple[str, ...]] = Counter()
    invalid_chartdate_rows = 0
    input_headers: list[str] = []
    with observations_path.open("w", encoding="utf-8", newline="") as valid_handle, quarantine_path.open("w", encoding="utf-8", newline="") as quarantine_handle:
        valid_writer = csv.DictWriter(valid_handle, fieldnames=OBSERVATION_FIELDS, extrasaction="ignore")
        quarantine_writer = csv.DictWriter(quarantine_handle, fieldnames=QUARANTINE_FIELDS, extrasaction="ignore")
        valid_writer.writeheader()
        quarantine_writer.writeheader()
        convert = pacsv.ConvertOptions(include_columns=list(REQUIRED_COLUMNS), column_types={name: pa.string() for name in REQUIRED_COLUMNS})
        reader = pacsv.open_csv(source, read_options=pacsv.ReadOptions(block_size=8 * 1024 * 1024, use_threads=False), convert_options=convert)
        input_headers = list(reader.schema.names)
        missing_columns = set(REQUIRED_COLUMNS) - set(reader.schema.names)
        if missing_columns:
            raise ValueError(f"OMR CSV missing required columns: {sorted(missing_columns)}")
        for batch in reader:
            for row in batch.to_pylist():
                total_rows += 1
                label = (row.get("result_name") or "").strip()
                label_counts[label] += 1
                if label not in BP_LABELS:
                    continue
                all_bp_counts[label] += 1
                subject = (row.get("subject_id") or "").strip()
                if subject not in mapping:
                    continue
                cohort_bp_counts[label] += 1
                matched_any.add(subject)
                record = _row_template(row, source, mapping, total_rows)
                label_quality = quality_by_label.setdefault(label, Counter())
                raw = row.get("result_value")
                systolic, diastolic, reason = parse_blood_pressure(raw)
                chartdate = record["chartdate"]
                if not _date_only(chartdate):
                    reason = "invalid_chartdate"
                    invalid_chartdate_rows += 1
                signature = (subject, chartdate, record["seq_num"], label, raw or "")
                duplicate_signatures[signature] += 1
                if reason:
                    selected_quality[reason] += 1
                    label_quality[reason] += 1
                    record["rejection_reason"] = reason
                    quarantine_writer.writerow(record)
                    continue
                record["systolic_value"] = f"{systolic:g}"
                record["diastolic_value"] = f"{diastolic:g}"
                valid_writer.writerow(record)
                selected_quality["valid_pair"] += 1
                label_quality["valid_pair"] += 1
                matched_valid.add(subject)
                valid_dates.append(chartdate)

    duplicate_groups = sum(count > 1 for count in duplicate_signatures.values())
    duplicate_excess_rows = sum(count - 1 for count in duplicate_signatures.values() if count > 1)
    for quality_name in (
        "valid_pair", "missing_value", "malformed_or_ambiguous_pair",
        "nonnumeric_or_malformed_component", "nonfinite_component",
        "implausible_component_values", "invalid_chartdate",
    ):
        selected_quality.setdefault(quality_name, 0)
    quality_by_label_json = {}
    for label in BP_LABELS:
        label_counts_value = quality_by_label.setdefault(label, Counter())
        quality_by_label_json[label] = {
            key: label_counts_value.get(key, 0)
            for key in ("valid_pair", "missing_value", "malformed_or_ambiguous_pair", "nonnumeric_or_malformed_component", "nonfinite_component", "implausible_component_values", "invalid_chartdate")
        }
    patients_rows = len(mapping)
    audit: dict[str, Any] = {
        "processing_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "processing_version": "mimic-omr-bp-extractor-1.0",
        "inputs": {
            "source_file": str(source), "source_sha256": source_sha, "source_bytes": source.stat().st_size,
            "source_header": input_headers, "cohort_patients_file": str(cohort),
            "cohort_sha256": _sha256(cohort), "cohort_size": patients_rows,
        },
        "rows_scanned": total_rows,
        "malformed_csv_rows": 0,
        "result_name_counts_all_source_rows": dict(sorted(label_counts.items())),
        "supported_blood_pressure_labels": list(BP_LABELS),
        "blood_pressure_rows_all_subjects_by_label": dict(sorted(all_bp_counts.items())),
        "blood_pressure_rows_all_subjects": sum(all_bp_counts.values()),
        "cohort_blood_pressure_rows_by_label": dict(sorted(cohort_bp_counts.items())),
        "cohort_quality_counts_by_label": quality_by_label_json,
        "cohort_rows": {
            "blood_pressure_source_readings": sum(cohort_bp_counts.values()),
            "valid_readings": selected_quality["valid_pair"],
            "quarantined_readings": sum(v for k, v in selected_quality.items() if k != "valid_pair"),
            "valid_component_observations_if_split_for_twin": {"systolic_bp": selected_quality["valid_pair"], "diastolic_bp": selected_quality["valid_pair"]},
            "quality_counts": dict(sorted(selected_quality.items())),
        },
        "patient_coverage": {
            "fixed_cohort_patients": patients_rows,
            "with_any_supported_bp_row": len(matched_any),
            "with_valid_sbp_and_dbp": len(matched_valid),
            "with_valid_sbp": len(matched_valid),
            "with_valid_dbp": len(matched_valid),
            "with_both_valid_sbp_and_dbp": len(matched_valid),
            "with_neither_valid_sbp_nor_dbp": patients_rows - len(matched_valid),
            "with_no_supported_bp_row": patients_rows - len(matched_any),
            "with_no_valid_bp_pair": patients_rows - len(matched_valid),
            "sbp_and_dbp_coverage_are_identical": True,
        },
        "timestamp_semantics": {
            "source_column": "chartdate", "precision": "date only", "time_of_day": "not present; not inferred",
            "same_day_order": "seq_num is retained; no exact clock time is inferred",
            "timezone": "not applicable to date-only values", "timestamp_min": min(valid_dates) if valid_dates else None,
            "timestamp_max": max(valid_dates) if valid_dates else None,
            "deidentification": "MIMIC source chartdate preserved unchanged; dates are deidentified and not real-world calendar dates",
            "invalid_chartdate_rows": invalid_chartdate_rows,
            "database_readiness": "not importable into the current required DateTime observed_at field without a schema/API precision design change",
        },
        "unit_assumptions": {
            "source_unit_field": "OMR does not provide a unit column",
            "normalized_unit": "mmHg", "basis": "documented blood-pressure result semantics; no unit inferred from numeric magnitude",
            "no_conversion": True,
        },
        "validation_rules": {
            "accepted_format": "one numeric SBP/DBP pair separated by one slash; surrounding whitespace allowed",
            "sbp_bounds_mmHg": [30, 300], "dbp_bounds_mmHg": [10, 200], "relation": "SBP > DBP",
            "bounds_are_data_quality_filters_not_diagnostic_thresholds": True,
        },
        "duplicate_handling": {
            "identity": "stable source CSV record number; subject/date/seq_num/label/value signature audited",
            "source_observation_id_policy": "OMR has no event ID; assigned deterministic key omr:<source_record_number>, with source file SHA-256 retained in this audit",
            "duplicate_signature_groups": duplicate_groups, "duplicate_rows_beyond_first": duplicate_excess_rows,
            "policy": "never average or discard repeated same-day rows; every source row retains seq_num and source record number",
        },
        "cohort_policy": "Only source_subject_id values in the existing patients.csv are included; no patients selected or replaced.",
        "synthetic_data_generated": False,
        "attribution": "MIMIC-IV v3.1; use and cite under the applicable PhysioNet/MIMIC-IV Data Use Agreement",
        "limitations": [
            "OMR blood pressure is date-level outpatient/medical-record data, not an exact-time ICU bedside measurement.",
            "Posture variants remain distinguished by the original result_name.",
            "OMR has no explicit unit column; mmHg follows the documented blood-pressure semantics, not numeric-value guessing.",
            "Current ORM requires observed_at as timezone-aware DateTime and has no first-class timestamp precision; import is stopped pending design change.",
        ],
    }
    audit["outputs"] = {}
    for name in ("observations.csv", "quarantine.csv"):
        file = staged[name]
        audit["outputs"][name] = {"rows": max(0, sum(1 for _ in file.open(encoding="utf-8")) - 1), "bytes": file.stat().st_size, "sha256": _sha256(file)}
    staged["audit.json"].write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = _make_report(audit)
    staged["report.md"].write_text(report, encoding="utf-8")
    # Validate output row counts and that every selected row maps back to this fixed cohort.
    expected = selected_quality["valid_pair"]
    if audit["outputs"]["observations.csv"]["rows"] != expected:
        raise RuntimeError("Staged observation CSV count does not match audit")
    if audit["outputs"]["quarantine.csv"]["rows"] != audit["cohort_rows"]["quarantined_readings"]:
        raise RuntimeError("Staged quarantine CSV count does not match audit")
    # Each final file is replaced only after the full scan and validation succeed.
    for name in ("observations.csv", "quarantine.csv", "audit.json", "report.md"):
        os.replace(staged[name], output / name)
    return audit


def _make_report(audit: dict[str, Any]) -> str:
    coverage = audit["patient_coverage"]
    rows = audit["cohort_rows"]
    excluded = rows["quality_counts"].get("implausible_component_values", 0)
    return f"""# MIMIC-IV OMR blood-pressure extraction report

- Fixed cohort: **{coverage['fixed_cohort_patients']:,}** patients.
- Patients with any supported OMR BP row: **{coverage['with_any_supported_bp_row']:,}**.
- Patients with at least one valid SBP and DBP pair: **{coverage['with_valid_sbp_and_dbp']:,}**.
- Cohort source readings: **{rows['blood_pressure_source_readings']:,}**; valid: **{rows['valid_readings']:,}**; quarantined: **{rows['quarantined_readings']:,}**.
- Implausible pairs rejected: **{excluded:,}**. Full rejection categories are in `audit.json`.
- Date span of valid readings: **{audit['timestamp_semantics']['timestamp_min']}** to **{audit['timestamp_semantics']['timestamp_max']}**.
- All six distinct OMR BP labels, including posture variants, are retained as context; same-day rows are not averaged.

`chartdate` is a date, not a time. The extracted CSV preserves `chartdate` and `seq_num` and does not fabricate a clock time. The existing database requires a timestamped `observed_at` and lacks a first-class date-precision field, so **no PostgreSQL import is safe yet**. A schema/API design that preserves date precision and keeps UI/state ordering date-aware is required before import. No database writes or migrations were performed.

The broad SBP/DBP ranges are extraction quality checks, not clinical thresholds. Source dates are de-identified MIMIC dates, preserved unchanged; they are not real-world calendar dates. No values were synthesized, and patients without readings remain without BP observations. Follow the applicable MIMIC-IV Data Use Agreement and required attribution.
"""


def validate_outputs(output: Path = DEFAULT_OUTPUT, cohort: Path = DEFAULT_COHORT) -> dict[str, Any]:
    """Validate published CSVs against the cohort mapping and audit without reading raw OMR."""
    output, cohort = output.resolve(), cohort.resolve()
    mapping = load_cohort(cohort)
    audit = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    valid_count = 0
    seen_ids: set[str] = set()
    with (output / "observations.csv").open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(OBSERVATION_FIELDS).issubset(reader.fieldnames):
            raise ValueError("Observations output has an incomplete schema")
        for row in reader:
            valid_count += 1
            subject = row["source_subject_id"]
            if subject not in mapping or row["internal_patient_id"] != mapping[subject]:
                raise ValueError("Observation patient identifier is outside or mismatched with the fixed cohort")
            if row["source_observation_id"] in seen_ids or row["source_observation_id"] != f"omr:{row['source_record_number']}":
                raise ValueError("Observation source identity is duplicated or unstable")
            seen_ids.add(row["source_observation_id"])
            if not _date_only(row["chartdate"]) or row["timestamp_precision"] != "date_only; no time recorded":
                raise ValueError("Observation timestamp precision is missing or invalid")
            if row["systolic_unit"] != "mmHg" or row["diastolic_unit"] != "mmHg":
                raise ValueError("Unexpected BP unit")
            systolic, diastolic, reason = parse_blood_pressure(f"{row['systolic_value']}/{row['diastolic_value']}")
            if reason or systolic is None or diastolic is None:
                raise ValueError("Published observation has invalid SBP/DBP components")
            if row["original_result_name"] not in BP_LABELS:
                raise ValueError("Published observation has an unsupported result_name")
    quarantine_count = 0
    with (output / "quarantine.csv").open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(QUARANTINE_FIELDS).issubset(reader.fieldnames):
            raise ValueError("Quarantine output has an incomplete schema")
        for row in reader:
            quarantine_count += 1
            if row["source_subject_id"] not in mapping or not row["rejection_reason"]:
                raise ValueError("Quarantined row lacks cohort membership or a rejection reason")
    if valid_count != int(audit["cohort_rows"]["valid_readings"]):
        raise ValueError("Valid output row count differs from audit")
    if quarantine_count != int(audit["cohort_rows"]["quarantined_readings"]):
        raise ValueError("Quarantine row count differs from audit")
    for filename, count in (("observations.csv", valid_count), ("quarantine.csv", quarantine_count)):
        expected = audit["outputs"][filename]
        file = output / filename
        if count != int(expected["rows"]) or _sha256(file) != expected["sha256"]:
            raise ValueError(f"{filename} differs from the hashes/counts recorded in audit.json")
    return {"valid_observations": valid_count, "quarantined_observations": quarantine_count,
            "fixed_cohort_size": len(mapping), "all_patient_ids_match": True,
            "date_precision_preserved": True, "database_writes": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--validate-only", action="store_true", help="validate published outputs without reading raw OMR")
    args = parser.parse_args()
    if args.validate_only:
        result = validate_outputs(args.output, args.cohort)
        print(json.dumps(result, indent=2))
        return
    result = extract(args.source, args.cohort, args.output)
    print(json.dumps({
        "output_directory": str(args.output.resolve()),
        "cohort_size": result["patient_coverage"]["fixed_cohort_patients"],
        "valid_observations": result["cohort_rows"]["valid_readings"],
        "quarantined_observations": result["cohort_rows"]["quarantined_readings"],
        "patients_with_valid_bp": result["patient_coverage"]["with_valid_sbp_and_dbp"],
        "database_import": "blocked pending explicit date-precision schema/API support",
    }, indent=2))


if __name__ == "__main__":
    main()

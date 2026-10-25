import csv
import shutil
from pathlib import Path

from data_pipeline.extract_mimic_omr_blood_pressure import (
    extract,
    load_cohort,
    parse_blood_pressure,
)


def test_parse_standard_pair_and_whitespace():
    assert parse_blood_pressure("110/65") == (110.0, 65.0, None)
    assert parse_blood_pressure("  110 / 65  ") == (110.0, 65.0, None)
    assert parse_blood_pressure("120.5/70.5") == (120.5, 70.5, None)


def test_parse_rejects_missing_malformed_and_ambiguous_values():
    assert parse_blood_pressure(None)[2] == "missing_value"
    assert parse_blood_pressure("  ")[2] == "missing_value"
    assert parse_blood_pressure("120/")[2] == "nonnumeric_or_malformed_component"
    assert parse_blood_pressure("x/80")[2] == "nonnumeric_or_malformed_component"
    assert parse_blood_pressure("120/80/60")[2] == "malformed_or_ambiguous_pair"
    assert parse_blood_pressure("120-80")[2] == "malformed_or_ambiguous_pair"
    assert parse_blood_pressure("120/80, 121/81")[2] == "malformed_or_ambiguous_pair"


def test_parse_rejects_implausible_values_and_reversed_components():
    for value in ("29/10", "301/80", "120/9", "120/201", "70/100"):
        assert parse_blood_pressure(value)[2] == "implausible_component_values"


def _write_csv(path: Path, headers, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_fixed_cohort_membership_date_precision_duplicate_retention_and_idempotency():
    tmp_path = Path(__file__).parent / "omr_test_work"
    if tmp_path.exists():
        shutil.rmtree(tmp_path)
    tmp_path.mkdir()
    try:
        _test_fixed_cohort_membership_date_precision_duplicate_retention_and_idempotency(tmp_path)
    finally:
        shutil.rmtree(tmp_path)


def _test_fixed_cohort_membership_date_precision_duplicate_retention_and_idempotency(tmp_path):
    cohort_path = tmp_path / "patients.csv"
    _write_csv(cohort_path, ["internal_patient_id", "source_subject_id"], [
        {"internal_patient_id": "mimiciv31:100", "source_subject_id": "100"},
    ])
    assert load_cohort(cohort_path) == {"100": "mimiciv31:100"}

    source_path = tmp_path / "omr.csv"
    headers = ["subject_id", "chartdate", "seq_num", "result_name", "result_value"]
    rows = [
        {"subject_id": "100", "chartdate": "2150-01-01", "seq_num": "1", "result_name": "Blood Pressure", "result_value": " 120 / 80 "},
        # An exact repeated source row is preserved with its own stable record identifier.
        {"subject_id": "100", "chartdate": "2150-01-01", "seq_num": "1", "result_name": "Blood Pressure", "result_value": " 120 / 80 "},
        {"subject_id": "200", "chartdate": "2150-01-01", "seq_num": "1", "result_name": "Blood Pressure", "result_value": "110/70"},
        {"subject_id": "100", "chartdate": "2150-01-01", "seq_num": "2", "result_name": "Blood Pressure Sitting", "result_value": "130/85"},
        {"subject_id": "100", "chartdate": "2150-01-02", "seq_num": "1", "result_name": "Blood Pressure", "result_value": "150/7"},
    ]
    _write_csv(source_path, headers, rows)
    output_path = tmp_path / "processed"
    first = extract(source_path, cohort_path, output_path)
    first_bytes = {name: (output_path / name).read_bytes() for name in ("observations.csv", "quarantine.csv")}
    second = extract(source_path, cohort_path, output_path)
    second_bytes = {name: (output_path / name).read_bytes() for name in ("observations.csv", "quarantine.csv")}

    assert first["patient_coverage"]["fixed_cohort_patients"] == 1
    assert first["patient_coverage"]["with_valid_sbp_and_dbp"] == 1
    assert first["cohort_rows"]["valid_readings"] == 3
    assert first["cohort_rows"]["quarantined_readings"] == 1
    assert first["duplicate_handling"]["duplicate_signature_groups"] == 1
    assert first["duplicate_handling"]["duplicate_rows_beyond_first"] == 1
    assert first_bytes == second_bytes

    with (output_path / "observations.csv").open(encoding="utf-8", newline="") as handle:
        observations = list(csv.DictReader(handle))
    assert [row["source_record_number"] for row in observations] == ["1", "2", "4"]
    assert {row["internal_patient_id"] for row in observations} == {"mimiciv31:100"}
    assert all(row["chartdate"] == "2150-01-01" for row in observations)
    assert all(row["timestamp_precision"] == "date_only; no time recorded" for row in observations)
    assert all("observed_at" not in row for row in observations)
    assert [(row["systolic_value"], row["diastolic_value"]) for row in observations] == [("120", "80"), ("120", "80"), ("130", "85")]
    assert {row["systolic_unit"] for row in observations} == {"mmHg"}
    assert {row["diastolic_unit"] for row in observations} == {"mmHg"}
    with (output_path / "quarantine.csv").open(encoding="utf-8", newline="") as handle:
        rejected = list(csv.DictReader(handle))
    assert rejected[0]["rejection_reason"] == "implausible_component_values"


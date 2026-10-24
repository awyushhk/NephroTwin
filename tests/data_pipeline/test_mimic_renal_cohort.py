from datetime import datetime, timedelta

from data_pipeline.mimic_renal_cohort import (
    classify_lab_item,
    classify_research_group,
    internal_patient_id,
    parse_timestamp,
    parse_numeric,
    patient_is_eligible,
    select_subjects,
    standardize,
)

def test_exact_dictionary_mapping_and_ambiguous_fluids():
    assert classify_lab_item({"label": "Creatinine", "fluid": "Blood", "category": "Chemistry"})[0] == "creatinine"
    assert classify_lab_item({"label": "Creatinine, Ascites", "fluid": "Ascites", "category": "Chemistry"})[0] is None
    assert classify_lab_item({"label": "Albumin/Creatinine, Urine", "fluid": "Urine", "category": "Chemistry"})[0] == "acr"
    assert classify_lab_item({"label": "Albumin, Urine", "fluid": "Urine", "category": "Chemistry"})[0] == "urine_albumin"

def test_validated_units_and_unknown_units():
    val, unit, rule = standardize("creatinine", 88.4, "umol/L")
    assert val == 1.0 and unit == "mg/dL" and "88.4" in rule
    assert standardize("egfr", 60, "mL/min")[0] is None
    assert standardize("acr", 30, "mg/g")[:2] == (30, "mg/g")
    assert standardize("urine_albumin", 10, "mystery-unit")[0] is None
    assert standardize("creatinine", float("inf"), "mg/dL")[0] is None

def test_missing_numeric_values_remain_missing():
    assert parse_numeric("") is None
    assert parse_numeric("   ") is None
    assert standardize("creatinine", None, "mg/dL")[0] is None

def test_time_policy_and_eligibility_requires_repeated_span():
    timestamp = parse_timestamp("2180-03-23 11:51:00")
    assert timestamp == datetime(2180, 3, 23, 11, 51)
    assert parse_timestamp("2180-03-23T11:51:00+00:00") is None
    assert patient_is_eligible(2, timestamp, timestamp + timedelta(days=1), 1)
    assert not patient_is_eligible(2, timestamp, timestamp + timedelta(hours=23), 1)

def test_selection_is_deterministic_and_coverage_ranked():
    t = datetime(2180, 1, 1)
    stats = {"101": {"creatinine_count": 5, "first": t, "last": t + timedelta(days=10), "span_days": 10},
             "102": {"creatinine_count": 3, "first": t, "last": t + timedelta(days=20), "span_days": 20},
             "103": {"creatinine_count": 1, "first": t, "last": t + timedelta(days=30), "span_days": 30}}
    first, _ = select_subjects(stats, 1, 1)
    second, _ = select_subjects(stats, 1, 1)
    assert first == second == ["102"]
    assert internal_patient_id("102") == "mimiciv31:102"

def test_research_groups_are_candidates_not_diagnoses():
    start = datetime(2180, 1, 1)
    group, evidence = classify_research_group({"creatinine": [(start, 1.0, "50912", ""), (start + timedelta(hours=36), 1.35, "50912", "")]})
    assert group == "acute_creatinine_change_candidate"
    assert "not an AKI diagnosis" in evidence
    group, evidence = classify_research_group({"egfr": [(start, 55, "50920", ""), (start + timedelta(days=100), 54, "50920", "")]})
    assert group == "persistent_renal_measurement_abnormality_review_candidate"
    assert "not a CKD diagnosis" in evidence
    assert classify_research_group({})[0] == "insufficient_evidence_or_data_quality"

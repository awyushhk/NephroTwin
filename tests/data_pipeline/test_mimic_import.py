from types import SimpleNamespace

from data_pipeline.import_mimic_renal_cohort import _parse_valid_observation, omr_component_records, source_observation_matches

def test_exact_source_observation_is_idempotent_but_conflicts_are_not_overwritten():
    row = {"source_subject_id": "10000032", "standardized_unit": "mg/dL", "canonical_measurement": "creatinine",
           "mimic_item_id": "50912", "original_lab_label": "Creatinine", "original_value": "1.20", "original_numeric_value": "1.2",
           "original_unit": "mg/dL", "charttime": "2180-03-23 11:51:00", "hadm_id": "22595853"}
    existing = SimpleNamespace(patient_id=4, source_system="MIMIC-IV-v3.1", source_subject_id="10000032", value=1.2,
        unit="mg/dL", measurement_type="creatinine", source_item_id="50912", source_original_label="Creatinine",
        source_original_value="1.20", source_original_numeric_value=1.2, source_original_unit="mg/dL",
        source_charttime_text="2180-03-23 11:51:00", source_encounter_id="22595853")
    assert source_observation_matches(existing, row, 1.2, 4)
    assert not source_observation_matches(existing, {**row, "original_value": "1.3"}, 1.2, 4)
    assert not source_observation_matches(existing, row, 1.2, 5)


def test_hba1c_import_preserves_percent_value_and_source_time_and_is_idempotent():
    row = {"source_subject_id": "10000032", "standardized_unit": "%", "canonical_measurement": "hba1c",
        "standardized_value": "6.5",
        "mimic_item_id": "50852", "original_lab_label": "% Hemoglobin A1c", "original_value": "6.50",
        "original_numeric_value": "6.5", "original_unit": "%", "charttime": "2180-03-23 11:51:00", "hadm_id": "22595853"}
    value, observed_at, source_id = _parse_valid_observation({**row, "source_observation_id": "a1c-event-1"})
    assert (value, observed_at.isoformat(), source_id) == (6.5, "2180-03-23T11:51:00+00:00", "a1c-event-1")
    existing = SimpleNamespace(patient_id=4, source_system="MIMIC-IV-v3.1", source_subject_id="10000032", value=6.5,
        unit="%", measurement_type="hba1c", source_item_id="50852", source_original_label="% Hemoglobin A1c",
        source_original_value="6.50", source_original_numeric_value=6.5, source_original_unit="%",
        source_charttime_text="2180-03-23 11:51:00", source_encounter_id="22595853")
    assert source_observation_matches(existing, row, 6.5, 4)
    assert not source_observation_matches(existing, {**row, "charttime": "2180-03-23 12:51:00"}, 6.5, 4)
    assert _parse_valid_observation({**row, "source_observation_id": "bad-unit", "standardized_unit": "mmol/mol"}) is None


def test_omr_reading_splits_to_idempotent_date_only_components():
    row = {
        "source_subject_id": "100", "source_observation_id": "omr:15", "source_record_number": "15",
        "chartdate": "2150-01-03", "timestamp_precision": "date_only; no time recorded", "seq_num": "2",
        "original_result_name": "Blood Pressure Sitting", "original_result_value": "120/70",
        "systolic_value": "120", "systolic_unit": "mmHg", "diastolic_value": "70", "diastolic_unit": "mmHg",
    }
    systolic, diastolic = omr_component_records(row)
    assert [item["measurement_type"] for item in (systolic, diastolic)] == ["systolic_bp", "diastolic_bp"]
    assert [item["value"] for item in (systolic, diastolic)] == [120.0, 70.0]
    assert all(item["observed_at"] is None for item in (systolic, diastolic))
    assert all(item["observed_date"].isoformat() == "2150-01-03" for item in (systolic, diastolic))
    assert all(item["timestamp_precision"] == "date_only" for item in (systolic, diastolic))
    assert all(item["source_sequence_number"] == 2 for item in (systolic, diastolic))
    assert systolic["source_observation_id"] != diastolic["source_observation_id"]
    assert systolic["source_original_value"] == diastolic["source_original_value"] == "120/70"

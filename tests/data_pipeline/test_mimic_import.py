from types import SimpleNamespace

from data_pipeline.import_mimic_renal_cohort import source_observation_matches

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

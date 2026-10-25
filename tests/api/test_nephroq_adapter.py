from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.nephroq import NephroQInputError, assess_nephroq_inputs, rank_example_profiles, simulate_nephroq


def _row(ident, kind, value, unit, day, seq=1, precision="date_only", time=None):
    return SimpleNamespace(
        id=ident,
        measurement_type=kind,
        value=value,
        unit=unit,
        observed_at=time,
        observed_date=day,
        timestamp_precision=precision,
        source_sequence_number=seq,
        source="MIMIC-IV v3.1 OMR" if kind == "systolic_bp" else "MIMIC-IV v3.1 lab",
        source_observation_id=f"source-{ident}",
    )


def _complete_rows():
    return [
        _row(1, "egfr", 58, "mL/min/1.73m2", date(2201, 3, 3), precision="exact_time", time=datetime(2201, 3, 3, 20, 40, tzinfo=timezone.utc)),
        _row(2, "acr", 13, "mg/g", date(2201, 3, 1), precision="exact_time", time=datetime(2201, 3, 1, 14, 0, tzinfo=timezone.utc)),
        _row(3, "systolic_bp", 142, "mmHg", date(2201, 3, 31)),
        _row(4, "hba1c", 7.4, "%", date(2201, 3, 2), precision="exact_time", time=datetime(2201, 3, 2, 4, 35, tzinfo=timezone.utc)),
        _row(5, "systolic_bp", 130, "mmHg", date(2201, 3, 2)),
    ]


def test_nephroq_all_fresh_inputs_from_different_dates_are_eligible_and_run():
    from renal_trajectory_module import simulate_trajectory_v2

    rows = _complete_rows()
    result = simulate_nephroq(rows, patient_id=77, years=1)
    expected = simulate_trajectory_v2(egfr0=58, a1c=7.4, uacr0=13, sbp=130, u=0.0, p=None, years=1, n=400)

    assert result["eligibility"]["eligible"] is True
    assert result["index_date"] == "2201-03-03"
    assert result["patient_id"] == 77
    assert result["point_count"] == 400
    assert result["trajectory"][0]["egfr"] == pytest.approx(float(expected[1][0]))
    assert result["trajectory"][-1]["uacr"] == pytest.approx(float(expected[2][-1]))
    assert result["baseline_inputs"]["acr"]["source_observation_id"] == "source-2"
    assert result["baseline_inputs"]["acr"]["stale"] is False
    assert result["baseline_inputs"]["systolic_bp"]["stale"] is False
    assert result["baseline_inputs"]["systolic_bp"]["source_observation_id"] == "source-5"
    assert result["baseline_inputs"]["systolic_bp"]["timestamp_precision"] == "date_only"
    assert result["assumptions"]["u"] == 0.0
    assert result["time_to_egfr_below_15_years"] is None
    assert any("different dates" in warning for warning in result["warnings"])


def test_nephroq_missing_required_input_is_reported_and_blocks_run():
    with pytest.raises(NephroQInputError, match="hba1c is missing"):
        simulate_nephroq([row for row in _complete_rows() if row.measurement_type != "hba1c"], patient_id=77, years=1)

    report = assess_nephroq_inputs([row for row in _complete_rows() if row.measurement_type != "hba1c"])
    assert report["eligible"] is False
    assert report["inputs"]["hba1c"]["freshness_status"] == "missing"


def test_stale_uacr_is_reported_and_blocks_default_simulation():
    rows = _complete_rows()
    rows = [row for row in rows if row.measurement_type != "acr"]
    rows.append(_row(6, "acr", 33.3, "mg/g", date(2169, 2, 3), precision="exact_time", time=datetime(2169, 2, 3, 14, tzinfo=timezone.utc)))
    report = assess_nephroq_inputs(rows)
    assert report["inputs"]["acr"]["freshness_status"] == "stale"
    assert report["inputs"]["acr"]["age_days"] > 90
    with pytest.raises(NephroQInputError, match="acr is stale"):
        simulate_nephroq(rows, patient_id=77, years=1)


def test_future_measurements_are_excluded_and_only_future_value_is_missing():
    rows = _complete_rows()
    report = assess_nephroq_inputs(rows)
    assert report["inputs"]["systolic_bp"]["source_observation_id"] == "source-5"
    without_prior_sbp = [row for row in rows if row.source_observation_id != "source-5"]
    report = assess_nephroq_inputs(without_prior_sbp)
    assert report["inputs"]["systolic_bp"]["freshness_status"] == "missing"
    assert "later" in report["inputs"]["systolic_bp"]["reason"].lower()


def test_same_day_date_only_input_vs_exact_baseline_is_temporally_ambiguous():
    rows = [row for row in _complete_rows() if row.measurement_type != "systolic_bp"]
    rows.extend([
        _row(7, "systolic_bp", 111, "mmHg", date(2201, 3, 3), seq=1),
        _row(8, "systolic_bp", 109, "mmHg", date(2201, 3, 2), seq=1),
    ])
    report = assess_nephroq_inputs(rows)
    assert report["eligible"] is False
    assert report["inputs"]["systolic_bp"]["freshness_status"] == "temporally_ambiguous"
    assert any("temporally ambiguous" in blocker for blocker in report["blockers"])


def test_same_day_exact_time_after_index_is_excluded_without_fabricating_order():
    rows = [row for row in _complete_rows() if row.measurement_type != "systolic_bp"]
    rows.extend([
        _row(9, "systolic_bp", 111, "mmHg", date(2201, 3, 3), precision="exact_time", time=datetime(2201, 3, 3, 21, tzinfo=timezone.utc)),
        _row(10, "systolic_bp", 110, "mmHg", date(2201, 3, 3), precision="exact_time", time=datetime(2201, 3, 3, 19, tzinfo=timezone.utc)),
    ])
    report = assess_nephroq_inputs(rows)
    assert report["inputs"]["systolic_bp"]["source_observation_id"] == "source-10"


def test_nephroq_rejects_out_of_range_horizon():
    with pytest.raises(NephroQInputError, match="horizon"):
        simulate_nephroq(_complete_rows(), patient_id=77, years=16)


def test_recommended_examples_are_eligible_and_cover_distinct_demo_strengths():
    patients = [
        SimpleNamespace(id=101, patient_code="MIMIC-101", source_system="MIMIC-IV-v3.1"),
        SimpleNamespace(id=102, patient_code="MIMIC-102", source_system="MIMIC-IV-v3.1"),
        SimpleNamespace(id=103, patient_code="MIMIC-103", source_system="MIMIC-IV-v3.1"),
        SimpleNamespace(id=104, patient_code="LOCAL-104", source_system="local"),
    ]
    required_rows = {
        patient.id: [
            _row(patient.id * 10 + 1, "egfr", 58, "mL/min/1.73m2", date(2201, 3, 3), precision="exact_time", time=datetime(2201, 3, 3, 20, 40, tzinfo=timezone.utc)),
            _row(patient.id * 10 + 2, "acr", 13, "mg/g", date(2201, 3, 1)),
            _row(patient.id * 10 + 3, "systolic_bp", 120, "mmHg", date(2201, 3, 2)),
            _row(patient.id * 10 + 4, "hba1c", 7, "%", date(2201, 3, 2)),
        ]
        for patient in patients
    }
    counts = {
        101: {"egfr": 3, "creatinine": 20, "acr": 2, "systolic_bp": 2, "hba1c": 2, "bun": 2},
        102: {"egfr": 2, "creatinine": 5, "acr": 15, "systolic_bp": 2, "hba1c": 20},
        103: {"egfr": 8, "creatinine": 25, "acr": 2, "systolic_bp": 2, "hba1c": 2},
        104: {"egfr": 4, "creatinine": 100, "acr": 10, "systolic_bp": 10, "hba1c": 10},
    }

    selected = rank_example_profiles(patients, counts, required_rows)

    assert [item["id"] for item in selected] == [101, 102, 103]
    assert {item["focus"] for item in selected} == {
        "Broadest multi-biomarker history",
        "Most ACR and HbA1c observations",
        "Most recorded eGFR checkpoints",
    }
    assert all(item["nephroq_eligible"] for item in selected)
    assert all(item["measurement_type_count"] >= 5 for item in selected)


def test_api_preflight_reports_stale_input_and_run_returns_actionable_422(monkeypatch):
    from api.routes import renal_twin as routes
    from api.schemas_renal import NephroQSimulationCreate

    rows = [row for row in _complete_rows() if row.measurement_type != "acr"]
    rows.append(_row(6, "acr", 33.3, "mg/g", date(2169, 2, 3), precision="exact_time", time=datetime(2169, 2, 3, 14, tzinfo=timezone.utc)))

    class FakeSession:
        def get(self, model, ident):
            return object()

    session = FakeSession()
    monkeypatch.setattr(routes, "_ordered_rows", lambda _session, _patient_id: rows)
    report = routes.nephroq_eligibility(77, 1, session)
    assert report["eligible"] is False
    assert report["inputs"]["acr"]["freshness_status"] == "stale"

    with pytest.raises(HTTPException) as error:
        routes.nephroq_simulation(77, NephroQSimulationCreate(years=1, baseline_observation_id=1), session)
    assert error.value.status_code == 422
    assert "acr is stale" in error.value.detail


def test_neutral_trajectory_routes_are_available_with_legacy_aliases():
    from api.routes.renal_twin import router

    paths = {route.path for route in router.routes}
    assert "/renal-twin/patients/{patient_id}/trajectory/eligibility" in paths
    assert "/renal-twin/patients/{patient_id}/trajectory" in paths
    assert "/renal-twin/patients/{patient_id}/nephroq/eligibility" in paths
    assert "/renal-twin/patients/{patient_id}/nephroq" in paths


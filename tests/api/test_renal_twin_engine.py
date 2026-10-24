from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from api.renal_twin import compute_observability, compute_state, simulate_egfr, utc_iso, validate_measurement
from api.schemas_renal import ScenarioComparisonCreate

def obs(ident, kind, value, when, unit=None):
    units = {"egfr": "mL/min/1.73m2", "acr": "mg/g", "creatinine": "mg/dL", "systolic_bp": "mmHg", "diastolic_bp": "mmHg"}
    return SimpleNamespace(id=ident, measurement_type=kind, value=value, observed_at=when, unit=unit or units[kind])

def test_one_observation_has_no_unsupported_trend():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    state = compute_state([obs(1, "egfr", 58, now)], now)
    assert state["measurements"]["egfr"]["change"] is None
    assert state["measurements"]["egfr"]["previous"] is None
    assert any("single result" in item for item in state["warnings"])

def test_two_observations_change_uses_irregular_elapsed_time():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=45, hours=12)
    trend = compute_state([obs(1, "egfr", 80, start), obs(2, "egfr", 70, end)], end)["measurements"]["egfr"]
    assert trend["change"] == -10
    assert trend["elapsed_days"] == 45.5
    assert trend["change_per_day"] == pytest.approx(-10 / 45.5)

def test_missing_values_remain_missing_and_future_values_excluded():
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    state = compute_state([obs(1, "egfr", 50, now), obs(2, "egfr", 10, now + timedelta(days=1))], now)
    assert state["measurements"]["egfr"]["latest"]["value"] == 50
    assert state["source_observation_ids"] == [1]
    assert state["measurements"]["acr"]["latest"] is None

def test_stale_and_out_of_order_entries_are_ordered_by_observation_time():
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    rows = [obs(2, "egfr", 60, now - timedelta(days=180)), obs(1, "egfr", 65, now - timedelta(days=181))]
    state = compute_state(rows, now)
    assert state["measurements"]["egfr"]["previous"]["observation_id"] == 1
    assert state["stale"] is True

@pytest.mark.parametrize(("value", "category"), [(90, "G1"), (89.99, "G2"), (60, "G2"), (45, "G3a"), (30, "G3b"), (15, "G4"), (14.99, "G5")])
def test_egfr_category_boundaries(value, category):
    assert validate_measurement("egfr", value, "mL/min/1.73m2")[1] == category

@pytest.mark.parametrize(("value", "category"), [(29.99, "A1"), (30, "A2"), (300, "A2"), (300.01, "A3")])
def test_acr_category_boundaries(value, category):
    assert validate_measurement("acr", value, "mg/g")[1] == category

def test_incompatible_units_and_impossible_values_rejected():
    with pytest.raises(ValueError): validate_measurement("egfr", 55, "ml/min")
    with pytest.raises(ValueError): validate_measurement("egfr", float("nan"), "mL/min/1.73m2")
    with pytest.raises(ValueError): validate_measurement("acr", -1, "mg/g")

def test_deterministic_scenario_and_invalid_horizon():
    assert simulate_egfr(60, -2, 12) == simulate_egfr(60, -2, 12)
    assert simulate_egfr(60, -2, 12)["points"][-1]["value"] == 58
    with pytest.raises(ValueError): simulate_egfr(60, 0, 121)


def test_observability_uses_event_times_and_reports_irregular_gaps():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        obs(1, "egfr", 80, start),
        obs(2, "egfr", 70, start + timedelta(days=19)),
        obs(3, "egfr", 60, start + timedelta(days=40)),
    ]
    result = compute_observability(
        rows,
        source_system="manual",
        as_of=start + timedelta(days=40),
        trend_window_days=365,
        recent_window_days=30,
        historical_window_days=365,
        minimum_trend_observations=3,
        minimum_trend_span_days=30,
    )
    egfr = result["measurements"]["egfr"]
    assert egfr["valid_observation_count"] == 3
    assert egfr["elapsed_days_since_previous"] == 21
    assert egfr["median_interval_days"] == 20
    assert egfr["recent_observation_count"] == 2
    assert egfr["historical_observation_count"] == 1
    assert egfr["trend"]["sufficient"] is True
    assert egfr["trend"]["absolute_change"] == -20
    assert egfr["trend"]["elapsed_days"] == 40
    assert egfr["trend"]["rate_per_year"] == pytest.approx(-20 * 365.25 / 40)
    assert "Variable gaps" in egfr["sampling_description"]


def test_observability_keeps_missingness_unknown_without_a_schedule():
    result = compute_observability([], source_system="manual", as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))
    egfr = result["measurements"]["egfr"]
    assert egfr["availability"] == "missing"
    assert egfr["missingness"]["denominator"] is None
    assert egfr["missingness"]["percent"] is None
    assert egfr["trend"]["sufficient"] is False
    assert egfr["trend"]["rate_per_year"] is None


def test_timestamp_api_normalization_preserves_mimic_source_clock_time():
    # PostgreSQL returns this instant in Asia/Calcutta; the MIMIC source charttime has no zone.
    returned = datetime(2154, 8, 9, 11, 20, tzinfo=ZoneInfo("Asia/Calcutta"))
    assert utc_iso(returned) == "2154-08-09T05:50:00Z"


def test_scenario_comparison_requires_multiple_distinct_user_assumptions():
    comparison = ScenarioComparisonCreate(
        baseline_observation_id=10,
        horizon_months=12,
        scenarios=[{"label": "Scenario A", "rate_per_year": -1}, {"label": "Scenario B", "rate_per_year": 0}],
    )
    assert len(comparison.scenarios) == 2
    with pytest.raises(ValueError):
        ScenarioComparisonCreate(
            baseline_observation_id=10,
            horizon_months=12,
            scenarios=[{"label": "Scenario A", "rate_per_year": -1}, {"label": "Scenario B", "rate_per_year": -1}],
        )

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from api.renal_twin import compute_state, simulate_egfr, validate_measurement

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

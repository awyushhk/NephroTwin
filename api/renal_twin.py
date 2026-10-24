"""Deterministic, descriptive renal twin state and scenario calculations."""
from datetime import datetime, timezone
from math import isfinite

ALGORITHM_VERSION = "renal-twin-1.0"
MEASUREMENTS = {
    "creatinine": {"unit": "mg/dL", "min": 0.05, "max": 100.0},
    "egfr": {"unit": "mL/min/1.73m2", "min": 0.0, "max": 250.0},
    "acr": {"unit": "mg/g", "min": 0.0, "max": 100000.0},
    "bun": {"unit": "mg/dL", "min": 0.0, "max": 1000.0},
    "potassium": {"unit": "mmol/L", "min": 0.0, "max": 30.0},
    "bicarbonate": {"unit": "mmol/L", "min": 0.0, "max": 100.0},
    "urine_albumin": {"unit": "mg/dL", "min": 0.0, "max": 100000.0},
    "urine_creatinine": {"unit": "mg/dL", "min": 0.0, "max": 100000.0},
    "systolic_bp": {"unit": "mmHg", "min": 30.0, "max": 300.0},
    "diastolic_bp": {"unit": "mmHg", "min": 10.0, "max": 200.0},
}

def validate_measurement(kind, value, unit):
    if kind not in MEASUREMENTS:
        raise ValueError("Unsupported measurement type.")
    if not isfinite(value):
        raise ValueError("Measurement value must be finite.")
    spec = MEASUREMENTS[kind]
    if unit != spec["unit"]:
        raise ValueError(f"{kind} requires unit {spec['unit']}.")
    if not spec["min"] <= value <= spec["max"]:
        raise ValueError("Value is outside the supported input range; review the source and units before entry.")
    warnings = []
    if kind == "egfr" and value < 60:
        warnings.append("Low eGFR observation: a single result does not establish chronic kidney disease.")
    if kind == "acr" and value >= 30:
        warnings.append("Elevated ACR observation: repeat testing and clinical context are needed to assess chronicity.")
    if kind == "egfr" and value >= 90:
        category = "G1"
    elif kind == "egfr" and value >= 60:
        category = "G2"
    elif kind == "egfr" and value >= 45:
        category = "G3a"
    elif kind == "egfr" and value >= 30:
        category = "G3b"
    elif kind == "egfr" and value >= 15:
        category = "G4"
    elif kind == "egfr":
        category = "G5"
    elif kind == "acr":
        category = "A1" if value < 30 else "A2" if value <= 300 else "A3"
    else:
        category = None
    return warnings, category

def compute_state(observations, now=None):
    now = now or datetime.now(timezone.utc)
    grouped = {key: [] for key in MEASUREMENTS}
    for obs in observations:
        if obs.observed_at <= now and obs.measurement_type in grouped:
            grouped[obs.measurement_type].append(obs)
    metrics, warnings, source_ids = {}, [], []
    latest_time = None
    for kind, rows in grouped.items():
        rows.sort(key=lambda o: (o.observed_at, o.id))
        source_ids.extend(o.id for o in rows)
        if not rows:
            metrics[kind] = {"latest": None, "previous": None, "count": 0, "trend": None, "category": None, "age_days": None, "stale": False}
            continue
        latest = rows[-1]
        age_days = max(0.0, (now - latest.observed_at).total_seconds() / 86400)
        latest_time = max(latest_time, latest.observed_at) if latest_time else latest.observed_at
        prev = rows[-2] if len(rows) > 1 else None
        elapsed_days = (latest.observed_at - prev.observed_at).total_seconds() / 86400 if prev else None
        delta = latest.value - prev.value if prev and elapsed_days > 0 else None
        metrics[kind] = {
            "latest": {"value": latest.value, "unit": latest.unit, "observed_at": latest.observed_at.isoformat(), "observation_id": latest.id},
            "previous": ({"value": prev.value, "observed_at": prev.observed_at.isoformat(), "observation_id": prev.id} if prev else None),
            "count": len(rows), "elapsed_days": elapsed_days, "change": delta,
            "change_per_day": delta / elapsed_days if delta is not None and elapsed_days else None,
            "category": validate_measurement(kind, latest.value, latest.unit)[1],
            "age_days": round(age_days, 2), "stale": age_days > 90,
        }
        if age_days > 90:
            warnings.append(f"{kind} observation is {int(age_days)} days old; review freshness.")
        warnings.extend(validate_measurement(kind, latest.value, latest.unit)[0])
    observed_types = sum(bool(grouped[k]) for k in grouped)
    return {"algorithm_version": ALGORITHM_VERSION, "as_of": now.isoformat(), "latest_observation_at": latest_time.isoformat() if latest_time else None,
            "measurements": metrics, "source_observation_ids": sorted(set(source_ids)),
            "data_completeness": {"available_measurements": observed_types, "supported_measurements": len(MEASUREMENTS)},
            "stale": any("days old" in w for w in warnings), "warnings": sorted(set(warnings)),
            "clinical_note": "Descriptive observations only. Trends do not diagnose CKD, acute kidney injury, or disease progression."}

def simulate_egfr(baseline, rate_per_year, horizon_months):
    if not isfinite(baseline) or baseline < 0 or baseline > 250:
        raise ValueError("Baseline eGFR must be between 0 and 250 mL/min/1.73m2.")
    if not isfinite(rate_per_year) or not -30 <= rate_per_year <= 30:
        raise ValueError("Assumed rate must be between -30 and 30 mL/min/1.73m2 per year.")
    if not 1 <= horizon_months <= 120:
        raise ValueError("Horizon must be between 1 and 120 months.")
    points = [{"month": month, "value": round(baseline + rate_per_year * month / 12, 4)} for month in range(0, horizon_months + 1)]
    warnings = ["This deterministic mathematical illustration is not a validated clinical forecast or treatment target."]
    if any(p["value"] < 0 or p["value"] > 250 for p in points):
        warnings.append("One or more outputs are outside the supported eGFR range and must not be interpreted clinically.")
    return {"points": points, "warnings": warnings}

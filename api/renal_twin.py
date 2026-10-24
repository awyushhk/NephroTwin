"""Deterministic, descriptive renal twin state and scenario calculations."""
from datetime import datetime, timedelta, timezone
from math import isfinite
from statistics import median
from collections import Counter

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


def utc_datetime(value):
    """Normalize aware timestamps to UTC; treat naive DB values as UTC storage values."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def utc_iso(value):
    return utc_datetime(value).isoformat().replace("+00:00", "Z") if value else None


def compute_observability(
    observations,
    source_system=None,
    as_of=None,
    trend_window_days=365,
    recent_window_days=30,
    historical_window_days=365,
    minimum_trend_observations=3,
    minimum_trend_span_days=30,
    stale_after_days=90,
):
    """Summarize recorded availability and observed-time trends without imputation."""
    rows = sorted(observations, key=lambda row: (utc_datetime(row.observed_at), row.id))
    latest_event = max((utc_datetime(row.observed_at) for row in rows), default=None)
    as_of = utc_datetime(as_of) if as_of else (latest_event if source_system == "MIMIC-IV-v3.1" and latest_event else datetime.now(timezone.utc))
    recent_start = as_of - timedelta(days=recent_window_days)
    historical_start = as_of - timedelta(days=max(historical_window_days, recent_window_days))
    trend_start = as_of - timedelta(days=trend_window_days) if trend_window_days else None
    summary = {}
    trend_series = {}

    for kind, spec in MEASUREMENTS.items():
        raw_rows = [row for row in rows if row.measurement_type == kind]
        valid_rows = []
        invalid_count = 0
        for row in raw_rows:
            try:
                validate_measurement(kind, float(row.value), row.unit)
                valid_rows.append(row)
            except (ValueError, TypeError):
                invalid_count += 1
        valid_rows.sort(key=lambda row: (utc_datetime(row.observed_at), row.id))
        timestamps = [utc_datetime(row.observed_at) for row in valid_rows]
        intervals = [(later - earlier).total_seconds() / 86400 for earlier, later in zip(timestamps, timestamps[1:])]
        latest = valid_rows[-1] if valid_rows else None
        previous = valid_rows[-2] if len(valid_rows) > 1 else None
        latest_interval = ((utc_datetime(latest.observed_at) - utc_datetime(previous.observed_at)).total_seconds() / 86400) if previous else None
        age_days = max(0.0, (as_of - utc_datetime(latest.observed_at)).total_seconds() / 86400) if latest else None
        recent_count = sum(recent_start <= time <= as_of for time in timestamps)
        historical_count = sum(historical_start <= time < recent_start for time in timestamps)
        selected = [row for row in valid_rows if trend_start is None or utc_datetime(row.observed_at) >= trend_start]
        trend_elapsed = ((utc_datetime(selected[-1].observed_at) - utc_datetime(selected[0].observed_at)).total_seconds() / 86400) if len(selected) > 1 else None
        trend_change = (selected[-1].value - selected[0].value) if len(selected) > 1 else None
        trend_rate = trend_change * 365.25 / trend_elapsed if trend_elapsed and trend_elapsed > 0 else None
        sufficient = len(selected) >= minimum_trend_observations and trend_elapsed is not None and trend_elapsed >= minimum_trend_span_days

        warnings = []
        if not valid_rows:
            warnings.append("No valid observations recorded; this is missing data, not a normal result.")
        if invalid_count:
            warnings.append(f"{invalid_count} stored row(s) have unsupported units or values and were excluded from descriptive summaries.")
        if age_days is not None and age_days > stale_after_days:
            warnings.append(f"Latest result is older than the {stale_after_days}-day freshness review window.")
        if len(intervals) >= 2:
            sampling = "Variable gaps between observations" if len({round(value, 6) for value in intervals}) > 1 else "Similar observed gaps; this does not establish continuous monitoring"
        elif intervals:
            sampling = "Only one interval is available; sampling pattern is insufficient to characterize"
        else:
            sampling = "Insufficient observations to characterize sampling intervals"

        missing_source = sum(not getattr(row, "source", None) for row in valid_rows)
        if missing_source:
            warnings.append(f"Source provenance is missing for {missing_source} valid observation(s).")
        quality_flags = sum(bool(getattr(row, "note", None)) for row in valid_rows)
        if quality_flags:
            warnings.append(f"{quality_flags} observation(s) carry source validation or quality notes.")
        timestamp_mismatches = 0
        for row in valid_rows:
            source_time = getattr(row, "source_charttime_text", None)
            if source_time:
                try:
                    parsed_source_time = datetime.fromisoformat(source_time.replace(" ", "T"))
                    if parsed_source_time.tzinfo is None:
                        timestamp_mismatches += parsed_source_time != utc_datetime(row.observed_at).replace(tzinfo=None)
                    else:
                        timestamp_mismatches += utc_datetime(parsed_source_time) != utc_datetime(row.observed_at)
                except ValueError:
                    timestamp_mismatches += 1
        if timestamp_mismatches:
            warnings.append(f"{timestamp_mismatches} source chart timestamp(s) do not match the stored event timestamp.")
        if source_system == "MIMIC-IV-v3.1" and latest:
            warnings.append("MIMIC-IV timestamps are de-identified shifted dates; source chart times have no timezone and are stored using a UTC convention.")
        if not sufficient:
            warnings.append(f"Insufficient observations for this descriptive trend (requires {minimum_trend_observations} valid results spanning at least {minimum_trend_span_days} days).")

        summary[kind] = {
            "valid_observation_count": len(valid_rows),
            "invalid_observation_count": invalid_count,
            "latest": ({"value": latest.value, "unit": latest.unit, "observed_at": utc_iso(latest.observed_at), "source": getattr(latest, "source", None),
                        "source_observation_id": getattr(latest, "source_observation_id", None),
                        "source_charttime_text": getattr(latest, "source_charttime_text", None)} if latest else None),
            "previous_observed_at": utc_iso(previous.observed_at) if previous else None,
            "elapsed_days_since_previous": round(latest_interval, 4) if latest_interval is not None else None,
            "median_interval_days": round(median(intervals), 4) if intervals else None,
            "recent_window_days": recent_window_days,
            "recent_observation_count": recent_count,
            "historical_window_days": max(historical_window_days, recent_window_days),
            "historical_observation_count": historical_count,
            "availability": "available" if valid_rows else "missing",
            "missingness": {"denominator": None, "percent": None, "note": "No expected sampling schedule is defined, so a missingness percentage would be misleading."},
            "sampling_description": sampling,
            "age_days": round(age_days, 2) if age_days is not None else None,
            "stale": bool(age_days is not None and age_days > stale_after_days),
            "trend": {
                "sufficient": sufficient,
                "minimum_observations": minimum_trend_observations,
                "minimum_span_days": minimum_trend_span_days,
                "window_days": trend_window_days or None,
                "observation_count": len(selected),
                "earliest": ({"value": selected[0].value, "observed_at": utc_iso(selected[0].observed_at)} if selected else None),
                "latest": ({"value": selected[-1].value, "observed_at": utc_iso(selected[-1].observed_at)} if selected else None),
                "absolute_change": round(trend_change, 6) if trend_change is not None else None,
                "elapsed_days": round(trend_elapsed, 4) if trend_elapsed is not None else None,
                "rate_per_year": round(trend_rate, 6) if trend_rate is not None else None,
                "unit": f"{spec['unit']} per year",
                "gap_count": max(0, len(selected) - 1),
                "median_gap_days": round(median([(utc_datetime(b.observed_at) - utc_datetime(a.observed_at)).total_seconds() / 86400 for a, b in zip(selected, selected[1:])]), 4) if len(selected) > 1 else None,
                "maximum_gap_days": round(max([(utc_datetime(b.observed_at) - utc_datetime(a.observed_at)).total_seconds() / 86400 for a, b in zip(selected, selected[1:])]), 4) if len(selected) > 1 else None,
                "warning": "Endpoint rates can be affected by sparse sampling or acute changes. This descriptive calculation does not classify AKI or establish disease progression." if kind in ("egfr", "creatinine") else None,
            },
            "provenance": {
                "source_count": sum(bool(getattr(row, "source", None)) for row in valid_rows),
                "source_item_count": sum(bool(getattr(row, "source_item_id", None)) for row in valid_rows),
                "source_timestamp_timezone": (getattr(latest, "source_timestamp_timezone", None) if latest else None),
                "quality_note_count": quality_flags,
                "timestamp_mismatch_count": timestamp_mismatches,
                "original_unit_counts": dict(Counter(getattr(row, "source_original_unit", None) or row.unit for row in valid_rows)),
            },
            "warnings": warnings,
        }

        if kind in ("egfr", "creatinine"):
            points = [{"id": row.id, "measurement_type": kind, "value": row.value, "unit": row.unit, "observed_at": utc_iso(row.observed_at),
                      "source": getattr(row, "source", None), "source_observation_id": getattr(row, "source_observation_id", None)} for row in selected]
            plotted = points
            if len(points) > 500:
                plotted = [points[round(index * (len(points) - 1) / 499)] for index in range(500)]
            trend_series[kind] = {"points": plotted, "total_in_window": len(points), "downsampled": len(points) > len(plotted)}

    return {
        "as_of": utc_iso(as_of),
        "source_system": source_system,
        "configuration": {"recent_window_days": recent_window_days, "historical_window_days": max(historical_window_days, recent_window_days),
                           "trend_window_days": trend_window_days or None, "minimum_trend_observations": minimum_trend_observations,
                           "minimum_trend_span_days": minimum_trend_span_days, "stale_after_days": stale_after_days},
        "measurements": summary,
        "trend_series": trend_series,
        "method_note": "Irregular source observations only. No interpolation, forward fill, diagnosis, or continuous-monitoring assumption is applied.",
    }

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

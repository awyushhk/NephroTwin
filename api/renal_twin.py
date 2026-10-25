"""Deterministic, descriptive renal twin state and scenario calculations."""
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from statistics import median
from collections import Counter

ALGORITHM_VERSION = "renal-twin-1.1"
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
    "hba1c": {"unit": "%", "min": 0.1, "max": 100.0},
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


def observation_precision(row):
    """Treat pre-migration/in-memory observations as exact timestamps."""
    precision = getattr(row, "timestamp_precision", None)
    if precision in ("exact_time", "date_only"):
        return precision
    return "exact_time" if getattr(row, "observed_at", None) is not None else "date_only"


def observation_date(row):
    source_date = getattr(row, "observed_date", None)
    if source_date is not None:
        return source_date if isinstance(source_date, date) and not isinstance(source_date, datetime) else source_date.date()
    observed_at = getattr(row, "observed_at", None)
    return utc_datetime(observed_at).date() if observed_at is not None else None


def observation_order_key(row):
    """Stable ordering; callers must still treat mixed same-day precision as ambiguous."""
    day = observation_date(row) or date.min
    if observation_precision(row) == "date_only":
        sequence = getattr(row, "source_sequence_number", None)
        return (day, 1, sequence if sequence is not None else -1, getattr(row, "id", 0) or 0)
    return (day, 0, utc_datetime(row.observed_at), getattr(row, "id", 0) or 0)


def observation_payload(row):
    precision = observation_precision(row)
    return {
        "observed_at": utc_iso(getattr(row, "observed_at", None)),
        "observed_date": observation_date(row).isoformat() if observation_date(row) else None,
        "timestamp_precision": precision,
        "source_sequence_number": getattr(row, "source_sequence_number", None),
    }


def _latest_day_group(rows):
    if not rows:
        return [], False
    latest_day = max(observation_date(row) for row in rows)
    day_rows = [row for row in rows if observation_date(row) == latest_day]
    precisions = {observation_precision(row) for row in day_rows}
    return sorted(day_rows, key=observation_order_key), len(precisions) > 1


def _select_ordered_latest(rows):
    """Choose latest only when temporal ordering is supported by source precision."""
    group, ambiguous = _latest_day_group(rows)
    if ambiguous:
        return None, group, True
    return (group[-1] if group else None), group, False


def _compute_date_aware_observability(
    observations, source_system, as_of, trend_window_days, recent_window_days,
    historical_window_days, minimum_trend_observations,
    minimum_trend_span_days, stale_after_days,
):
    rows = sorted(observations, key=observation_order_key)
    latest_day = max((observation_date(row) for row in rows), default=None)
    if as_of is None:
        as_of = latest_day if source_system == "MIMIC-IV-v3.1" and latest_day else datetime.now(timezone.utc).date()
    as_of_day = as_of.date() if isinstance(as_of, datetime) else as_of
    recent_start = as_of_day - timedelta(days=recent_window_days)
    historical_start = as_of_day - timedelta(days=max(historical_window_days, recent_window_days))
    trend_start = as_of_day - timedelta(days=trend_window_days) if trend_window_days else None
    summary, trend_series = {}, {}
    for kind, spec in MEASUREMENTS.items():
        raw_rows = [
            row for row in rows
            if row.measurement_type == kind
            and observation_date(row) <= as_of_day
            and not (
                isinstance(as_of, datetime)
                and observation_precision(row) == "exact_time"
                and utc_datetime(row.observed_at) > utc_datetime(as_of)
            )
        ]
        valid_rows, invalid_count = [], 0
        for row in raw_rows:
            try:
                validate_measurement(kind, float(row.value), row.unit)
                valid_rows.append(row)
            except (ValueError, TypeError):
                invalid_count += 1
        valid_rows.sort(key=observation_order_key)
        latest, latest_group, latest_ambiguous = _select_ordered_latest(valid_rows)
        kind_latest_day = max((observation_date(row) for row in valid_rows), default=None)
        previous = None
        if latest and kind_latest_day:
            earlier = [row for row in valid_rows if observation_date(row) < kind_latest_day]
            if earlier:
                previous, _, previous_ambiguous = _select_ordered_latest(earlier)
                if previous_ambiguous:
                    previous = None
            elif len(latest_group) > 1 and not latest_ambiguous:
                previous = latest_group[-2]
        latest_payload = ({"value": latest.value, "unit": latest.unit, **observation_payload(latest)} if latest else None)
        candidates = ([{"value": item.value, "unit": item.unit, **observation_payload(item)} for item in latest_group] if latest_ambiguous else [])
        previous_payload = ({"value": previous.value, **observation_payload(previous)} if previous else None)
        selected = [row for row in valid_rows if trend_start is None or observation_date(row) >= trend_start]
        selected.sort(key=observation_order_key)
        selected_has_date_precision = any(observation_precision(row) == "date_only" for row in selected)
        first_day = min((observation_date(row) for row in selected), default=None)
        first_group = [row for row in selected if observation_date(row) == first_day] if first_day else []
        earliest_ambiguous = len({observation_precision(row) for row in first_group}) > 1
        endpoints_unambiguous = not latest_ambiguous and not earliest_ambiguous and len(selected) > 0
        change = selected[-1].value - selected[0].value if len(selected) > 1 and endpoints_unambiguous else None
        calendar_span = (observation_date(selected[-1]) - observation_date(selected[0])).days if len(selected) > 1 else None
        elapsed_exact = None
        if len(selected) > 1 and not selected_has_date_precision:
            elapsed_exact = (utc_datetime(selected[-1].observed_at) - utc_datetime(selected[0].observed_at)).total_seconds() / 86400
        sufficient = (len(selected) >= minimum_trend_observations and elapsed_exact is not None
                      and elapsed_exact >= minimum_trend_span_days and not latest_ambiguous)
        age_days = (as_of_day - kind_latest_day).days if kind_latest_day else None
        mixed_precision_warning = latest_ambiguous
        warnings = []
        if not valid_rows:
            warnings.append("No valid observations recorded; this is missing data, not a normal result.")
        if invalid_count:
            warnings.append(f"{invalid_count} stored row(s) have unsupported units or values and were excluded from descriptive summaries.")
        if any(observation_precision(row) == "date_only" for row in valid_rows):
            warnings.append("Date-only observations have calendar-day precision; exact within-day intervals and rates are unavailable.")
        if mixed_precision_warning:
            warnings.append(f"{kind} has exact-time and date-only observations on {kind_latest_day}; latest-value ordering is unresolved.")
        if age_days is not None and age_days > stale_after_days:
            warnings.append(f"Latest result is older than the {stale_after_days}-day freshness review window (calendar-day precision).")
        if not sufficient:
            warnings.append(f"Insufficient observations for this descriptive trend (requires {minimum_trend_observations} valid results spanning at least {minimum_trend_span_days} exact-time days).")
        intervals = [
            (utc_datetime(b.observed_at) - utc_datetime(a.observed_at)).total_seconds() / 86400
            for a, b in zip(valid_rows, valid_rows[1:])
            if observation_precision(a) == observation_precision(b) == "exact_time"
        ]
        summary[kind] = {
            "valid_observation_count": len(valid_rows), "invalid_observation_count": invalid_count,
            "latest": latest_payload, "latest_temporal_ambiguity": latest_ambiguous,
            "latest_candidates": candidates,
            "previous": previous_payload,
            "previous_observed_at": previous_payload.get("observed_at") if previous_payload else None,
            "elapsed_days_since_previous": None if latest and (observation_precision(latest) == "date_only" or (previous and observation_precision(previous) == "date_only")) else ((utc_datetime(latest.observed_at) - utc_datetime(previous.observed_at)).total_seconds() / 86400 if latest and previous else None),
            "elapsed_calendar_days_since_previous": ((kind_latest_day - observation_date(previous)).days if previous and kind_latest_day else None),
            "median_interval_days": round(median(intervals), 4) if intervals and not any(observation_precision(row) == "date_only" for row in valid_rows) else None,
            "recent_window_days": recent_window_days,
            "recent_observation_count": sum(recent_start <= observation_date(row) <= as_of_day for row in valid_rows),
            "historical_window_days": max(historical_window_days, recent_window_days),
            "historical_observation_count": sum(historical_start <= observation_date(row) < recent_start for row in valid_rows),
            "availability": "available" if valid_rows else "missing",
            "missingness": {"denominator": None, "percent": None, "note": "No expected sampling schedule is defined, so a missingness percentage would be misleading."},
            "sampling_description": "Date-level observations; exact time gaps cannot be calculated" if selected_has_date_precision else "Exact-time observations",
            "age_days": age_days, "age_precision": "calendar_day" if isinstance(as_of, date) and not isinstance(as_of, datetime) or latest and observation_precision(latest) == "date_only" else "exact_time",
            "stale": bool(age_days is not None and age_days > stale_after_days),
            "trend": {
                "sufficient": sufficient, "minimum_observations": minimum_trend_observations,
                "minimum_span_days": minimum_trend_span_days, "window_days": trend_window_days or None,
                "observation_count": len(selected),
                "earliest": ({"value": selected[0].value, **observation_payload(selected[0])} if selected else None),
                "latest": ({"value": selected[-1].value, **observation_payload(selected[-1])} if selected and not latest_ambiguous else None),
                "absolute_change": round(change, 6) if change is not None else None,
                "elapsed_days": round(elapsed_exact, 4) if elapsed_exact is not None else None,
                "elapsed_calendar_days": calendar_span,
                "rate_per_year": round(change * 365.25 / elapsed_exact, 6) if change is not None and elapsed_exact else None,
                "unit": f"{spec['unit']} per year", "gap_count": max(0, len(selected) - 1),
                "median_gap_days": round(median(intervals), 4) if intervals and not selected_has_date_precision else None,
                "maximum_gap_days": round(max(intervals), 4) if intervals and not selected_has_date_precision else None,
                "warning": "Date-only rows preserve calendar dates and source sequence; no elapsed-time rate is calculated." if selected_has_date_precision else None,
            },
            "provenance": {"source_count": sum(bool(getattr(row, "source", None)) for row in valid_rows),
                           "source_item_count": sum(bool(getattr(row, "source_item_id", None)) for row in valid_rows),
                           "source_timestamp_timezone": None if latest and observation_precision(latest) == "date_only" else getattr(latest, "source_timestamp_timezone", None),
                           "quality_note_count": sum(bool(getattr(row, "note", None)) for row in valid_rows),
                           "timestamp_mismatch_count": 0,
                           "original_unit_counts": dict(Counter(getattr(row, "source_original_unit", None) or row.unit for row in valid_rows))},
            "warnings": warnings,
        }
        if kind in ("egfr", "creatinine"):
            points = [{"id": row.id, "measurement_type": kind, "value": row.value, "unit": row.unit,
                       **observation_payload(row), "source": getattr(row, "source", None),
                       "source_observation_id": getattr(row, "source_observation_id", None)} for row in selected]
            plotted = points if len(points) <= 500 else [points[round(i * (len(points) - 1) / 499)] for i in range(500)]
            trend_series[kind] = {"points": plotted, "total_in_window": len(points), "downsampled": len(points) > len(plotted)}
    as_of_precision = "exact_time" if isinstance(as_of, datetime) else "date_only"
    as_of_text = as_of.isoformat()
    return {"as_of": as_of_text, "as_of_precision": as_of_precision, "source_system": source_system,
            "configuration": {"recent_window_days": recent_window_days, "historical_window_days": max(historical_window_days, recent_window_days),
                              "trend_window_days": trend_window_days or None, "minimum_trend_observations": minimum_trend_observations,
                              "minimum_trend_span_days": minimum_trend_span_days, "stale_after_days": stale_after_days},
            "measurements": summary, "trend_series": trend_series,
            "method_note": "Irregular source observations only. Date-only rows retain calendar-day precision and seq_num order; no interpolation, forward fill, diagnosis, or continuous-monitoring assumption is applied."}


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
    observations = list(observations)
    if any(observation_precision(row) == "date_only" for row in observations):
        return _compute_date_aware_observability(
            observations, source_system, as_of, trend_window_days, recent_window_days,
            historical_window_days, minimum_trend_observations,
            minimum_trend_span_days, stale_after_days,
        )
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
    as_of_day = now.date() if isinstance(now, datetime) else now
    grouped = {key: [] for key in MEASUREMENTS}
    for obs in observations:
        day = observation_date(obs)
        if day is None or day > as_of_day or obs.measurement_type not in grouped:
            continue
        if observation_precision(obs) == "exact_time" and isinstance(now, datetime) and utc_datetime(obs.observed_at) > utc_datetime(now):
            continue
        grouped[obs.measurement_type].append(obs)
    metrics, warnings, source_ids = {}, [], []
    latest_date = None
    for kind, rows in grouped.items():
        rows.sort(key=observation_order_key)
        source_ids.extend(o.id for o in rows if getattr(o, "id", None) is not None)
        if not rows:
            metrics[kind] = {"latest": None, "previous": None, "count": 0, "trend": None, "category": None, "age_days": None, "stale": False}
            continue
        latest_date = max(latest_date, max(observation_date(row) for row in rows)) if latest_date else max(observation_date(row) for row in rows)
        latest, latest_group, latest_ambiguous = _select_ordered_latest(rows)
        latest_day = max(observation_date(row) for row in rows)
        age_days = max(0, (as_of_day - latest_day).days)
        previous = None
        elapsed_days = None
        elapsed_calendar_days = None
        change = None
        change_per_day = None
        if latest is not None:
            earlier = [row for row in rows if observation_date(row) < latest_day]
            if earlier:
                previous, _, previous_ambiguous = _select_ordered_latest(earlier)
                if previous_ambiguous:
                    previous = None
            elif len(latest_group) > 1 and not latest_ambiguous:
                previous = latest_group[-2]
            if previous is not None:
                previous_precision = observation_precision(previous)
                latest_precision = observation_precision(latest)
                elapsed_calendar_days = (latest_day - observation_date(previous)).days
                if previous_precision == latest_precision == "exact_time":
                    elapsed_days = (utc_datetime(latest.observed_at) - utc_datetime(previous.observed_at)).total_seconds() / 86400
                elif previous_precision == latest_precision == "date_only":
                    # A calendar-day difference is known; exact elapsed duration is not.
                    elapsed_days = None
                if elapsed_calendar_days > 0:
                    change = latest.value - previous.value
                    if elapsed_days and elapsed_days > 0:
                        change_per_day = change / elapsed_days
        latest_item = None
        if latest is not None:
            latest_item = {"value": latest.value, "unit": latest.unit, "observation_id": latest.id, **observation_payload(latest)}
        ambiguous_candidates = [
            {"value": row.value, "unit": row.unit, "observation_id": row.id, **observation_payload(row)}
            for row in latest_group
        ] if latest_ambiguous else []
        previous_item = ({"value": previous.value, "observation_id": previous.id, **observation_payload(previous)} if previous else None)
        stale = age_days > 90
        metrics[kind] = {
            "latest": latest_item,
            "latest_temporal_ambiguity": latest_ambiguous,
            "latest_candidates": ambiguous_candidates,
            "previous": previous_item,
            "count": len(rows), "elapsed_days": elapsed_days, "elapsed_calendar_days": elapsed_calendar_days,
            "change": change, "change_per_day": change_per_day,
            "category": validate_measurement(kind, latest.value, latest.unit)[1] if latest else None,
            "age_days": age_days, "age_precision": "calendar_day" if latest_ambiguous or (latest and observation_precision(latest) == "date_only") or not isinstance(now, datetime) else "exact_time",
            "stale": stale,
        }
        if latest_ambiguous:
            warnings.append(f"{kind} has timestamped and date-only observations on {latest_day.isoformat()}; current value ordering is unresolved.")
        if latest and observation_precision(latest) == "date_only":
            warnings.append(f"{kind} latest observation has date-only precision; freshness is measured by calendar date, not time of day.")
        if change is not None and elapsed_days is None:
            warnings.append(f"{kind} endpoint change is descriptive; an exact elapsed-time rate is unavailable because date-only observations are present.")
        if stale:
            warnings.append(f"{kind} observation is {age_days} calendar days old; review freshness.")
        if latest:
            warnings.extend(validate_measurement(kind, latest.value, latest.unit)[0])
    observed_types = sum(bool(grouped[k]) for k in grouped)
    has_date_only = any(observation_precision(row) == "date_only" for rows in grouped.values() for row in rows)
    latest_day_rows = [row for rows in grouped.values() for row in rows if observation_date(row) == latest_date]
    # A timestamp is a defensible overall latest event only if the latest calendar
    # day contains timestamped rows exclusively. Date-only events on that day
    # have no known within-day position relative to exact-time events.
    latest_exact_time = (
        max(utc_datetime(row.observed_at) for row in latest_day_rows)
        if latest_day_rows and all(observation_precision(row) == "exact_time" for row in latest_day_rows)
        else None
    )
    as_of_value = now.isoformat() if isinstance(now, datetime) else now.isoformat()
    return {"algorithm_version": ALGORITHM_VERSION, "as_of": as_of_value,
            "as_of_precision": "exact_time" if isinstance(now, datetime) else "date_only",
            "latest_observation_at": utc_iso(latest_exact_time), "latest_observation_date": latest_date.isoformat() if latest_date else None,
            "measurements": metrics, "source_observation_ids": sorted(set(source_ids)),
            "data_completeness": {"available_measurements": observed_types, "supported_measurements": len(MEASUREMENTS)},
            "stale": any(item.get("stale", False) for item in metrics.values()), "warnings": sorted(set(warnings)),
            "clinical_note": "Descriptive observations only. Trends do not diagnose CKD, acute kidney injury, or disease progression." + (" Date-only measurements are ordered by source date and sequence; same-day mixed precision is unresolved." if has_date_only else "")}

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

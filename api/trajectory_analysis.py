"""Descriptive summaries for returned hypothetical renal trajectories."""
from __future__ import annotations

from math import isfinite
from typing import Any, Iterable

EGFR_THRESHOLDS = (60.0, 45.0, 30.0, 15.0)
PERCENT_DECLINE = 0.20


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if isfinite(parsed) else None


def gfr_category(value: Any) -> str | None:
    """Categories: >=90 G1, >=60 G2, >=45 G3a, >=30 G3b, >=15 G4, else G5."""
    egfr = _number(value)
    if egfr is None or egfr < 0:
        return None
    if egfr >= 90:
        return "G1"
    if egfr >= 60:
        return "G2"
    if egfr >= 45:
        return "G3a"
    if egfr >= 30:
        return "G3b"
    if egfr >= 15:
        return "G4"
    return "G5"


def albuminuria_category(value: Any) -> str | None:
    """Categories: <30 A1, 30 through 300 inclusive A2, >300 A3 (mg/g)."""
    uacr = _number(value)
    if uacr is None or uacr < 0:
        return None
    if uacr < 30:
        return "A1"
    if uacr <= 300:
        return "A2"
    return "A3"


def _series(points: Iterable[dict[str, Any]], key: str) -> list[tuple[float, float]]:
    valid = []
    for point in points:
        year, value = _number(point.get("year")), _number(point.get(key))
        if year is not None and year >= 0 and value is not None and value >= 0:
            valid.append((year, value))
    return valid


def _crossing(series: list[tuple[float, float]], threshold: float) -> dict[str, Any]:
    if not series:
        return {"status": "unavailable", "time_years": None}
    first_year, first_value = series[0]
    if first_value < threshold:
        return {"status": "below_at_baseline", "time_years": None}
    if first_value == threshold:
        return {"status": "at_threshold_at_baseline", "time_years": first_year}
    if len(series) < 2:
        return {"status": "unavailable", "time_years": None}

    for (t0, v0), (t1, v1) in zip(series, series[1:]):
        crossed = v1 <= threshold
        if v0 > threshold and crossed:
            if t1 <= t0:
                return {"status": "unavailable", "time_years": None}
            fraction = (v0 - threshold) / (v0 - v1) if v0 != v1 else 0.0
            return {"status": "crossed", "time_years": t0 + fraction * (t1 - t0)}
    return {"status": "not_crossed", "time_years": None}


def _endpoint_metrics(series: list[tuple[float, float]], unit: str) -> dict[str, Any]:
    if not series:
        return {
            "status": "unavailable", "starting": None, "final": None,
            "absolute_change": None, "percent_change": None,
            "average_annualized_change": None, "elapsed_years": None,
            "unit": unit, "valid_points": 0,
        }
    start_year, start = series[0]
    end_year, end = series[-1]
    elapsed = end_year - start_year
    change = end - start
    return {
        "status": "available" if len(series) >= 2 and elapsed > 0 else "insufficient_points",
        "starting": start,
        "final": end,
        "absolute_change": change,
        "percent_change": (change / start * 100.0) if start > 0 else None,
        "average_annualized_change": (change / elapsed) if elapsed > 0 else None,
        "elapsed_years": elapsed,
        "unit": unit,
        "valid_points": len(series),
    }


def summarize_trajectory(
    points: Iterable[dict[str, Any]],
    thresholds: Iterable[float] = EGFR_THRESHOLDS,
) -> dict[str, Any]:
    """Summarize actual returned points; never extrapolates beyond their time grid."""
    points = list(points)
    egfr = _series(points, "egfr")
    uacr = _series(points, "uacr")
    egfr_metrics = _endpoint_metrics(egfr, "mL/min/1.73m²")
    uacr_metrics = _endpoint_metrics(uacr, "mg/g")

    egfr_milestones = {str(float(threshold)).removesuffix(".0"): _crossing(egfr, float(threshold)) for threshold in thresholds}
    if egfr and egfr[0][1] > 0:
        decline_threshold = egfr[0][1] * (1.0 - PERCENT_DECLINE)
        decline = _crossing(egfr, decline_threshold)
    else:
        decline = {"status": "unavailable", "time_years": None}

    paired = []
    for point in points:
        year, gfr, acr = (_number(point.get(k)) for k in ("year", "egfr", "uacr"))
        if year is not None and year >= 0 and gfr is not None and gfr >= 0 and acr is not None and acr >= 0:
            paired.append({"year": year, "egfr": gfr, "uacr": acr,
                           "g_category": gfr_category(gfr), "a_category": albuminuria_category(acr)})
    transitions = []
    for previous, current in zip(paired, paired[1:]):
        if (previous["g_category"], previous["a_category"]) != (current["g_category"], current["a_category"]):
            transitions.append({
                "year": current["year"],
                "gfr_category": current["g_category"],
                "albuminuria_category": current["a_category"],
                "egfr": current["egfr"],
                "uacr": current["uacr"],
            })
    start_categories = paired[0] if paired else None
    end_categories = paired[-1] if paired else None
    return {
        "label": "Hypothetical model-derived analysis; categories are not diagnoses.",
        "calculation": "Endpoint changes use first and last valid returned points; annualized change = endpoint change / elapsed simulation years.",
        "crossing_method": "Linear interpolation between adjacent returned points; no extrapolation.",
        "egfr": {
            **egfr_metrics,
            "thresholds": egfr_milestones,
            "decline_20_percent": decline,
        },
        "uacr": uacr_metrics,
        "categories": {
            "starting": ({"gfr": start_categories["g_category"], "albuminuria": start_categories["a_category"]} if start_categories else None),
            "final": ({"gfr": end_categories["g_category"], "albuminuria": end_categories["a_category"]} if end_categories else None),
            "transitions": transitions,
            "boundary_rules": {"gfr": "90→G1, 60→G2, 45→G3a, 30→G3b, 15→G4; lower values→G5", "uacr_mg_g": "<30→A1, 30–300 inclusive→A2, >300→A3"},
        },
    }

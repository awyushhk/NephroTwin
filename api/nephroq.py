"""On-demand adapter and eligibility gate for extracted NephroQ."""
from __future__ import annotations

from math import isfinite

from api.renal_twin import (
    _select_ordered_latest,
    observation_date,
    observation_payload,
    observation_precision,
    utc_datetime,
    validate_measurement,
)

REQUIRED_INPUTS = {
    "egfr": ("egfr0", "mL/min/1.73m2"),
    "acr": ("uacr0", "mg/g"),
    "systolic_bp": ("sbp", "mmHg"),
    "hba1c": ("a1c", "%"),
}
DEFAULT_FRESHNESS_DAYS = 90
LIMITATIONS = [
    "Research simulation only; not a validated patient-specific clinical forecast or diagnosis.",
    "Inputs may be from different dates and must not be assumed simultaneous.",
    "The bundled trial-anchored parameter defaults are used; no patient-specific fitting or training is performed.",
    "The default model setting u=0 is used; no treatment effect is represented.",
]


class NephroQInputError(ValueError):
    pass


def _valid_rows(rows, kind):
    valid = []
    for row in rows:
        if row.measurement_type != kind:
            continue
        try:
            validate_measurement(kind, float(row.value), row.unit)
        except (ValueError, TypeError):
            continue
        if observation_date(row) is not None:
            valid.append(row)
    return valid


def _at_or_before_index(row, baseline):
    """Return True/False, or None when source precision cannot order same-day rows."""
    row_day, index_day = observation_date(row), observation_date(baseline)
    if row_day < index_day:
        return True
    if row_day > index_day:
        return False
    if observation_precision(row) == observation_precision(baseline) == "exact_time":
        return utc_datetime(row.observed_at) <= utc_datetime(baseline.observed_at)
    # A source date plus seq_num does not establish a time relative to an exact
    # timestamp or another measurement stream on that same date.
    return None


def _input_metadata(row, index_row, freshness_days):
    row_day, index_day = observation_date(row), observation_date(index_row)
    if observation_precision(row) == observation_precision(index_row) == "exact_time":
        age_days = (utc_datetime(index_row.observed_at) - utc_datetime(row.observed_at)).total_seconds() / 86400
        age_precision = "exact_time"
    else:
        age_days = float((index_day - row_day).days)
        age_precision = "calendar_day"
    stale = age_days > freshness_days
    return {
        "value": float(row.value),
        "unit": row.unit,
        **observation_payload(row),
        "source": getattr(row, "source", None),
        "source_observation_id": getattr(row, "source_observation_id", None),
        "age_days": round(age_days, 4) if age_precision == "exact_time" else int(age_days),
        "age_precision": age_precision,
        "freshness_status": "stale" if stale else "fresh",
        "stale": stale,
    }


def assess_nephroq_inputs(rows, baseline_observation_id=None, freshness_days=DEFAULT_FRESHNESS_DAYS):
    """Resolve the eGFR index and other inputs without calling the model."""
    rows = list(rows)
    blockers, warnings, inputs = [], [], {}
    if freshness_days < 1:
        raise ValueError("Freshness threshold must be at least one day.")

    valid_egfr = _valid_rows(rows, "egfr")
    baseline = None
    baseline_ambiguous = False
    if baseline_observation_id is not None:
        baseline = next((row for row in valid_egfr if row.id == baseline_observation_id), None)
        if baseline is None:
            blockers.append("The selected eGFR baseline is missing, invalid, or does not belong to this profile.")
    else:
        baseline, _, ambiguous = _select_ordered_latest(valid_egfr)
        if ambiguous:
            baseline_ambiguous = True
            blockers.append("The latest eGFR date has mixed exact-time and date-only observations; select an unambiguous eGFR baseline.")
    if baseline is None:
        inputs["egfr"] = {"freshness_status": "temporally_ambiguous" if baseline_ambiguous else "missing", "reason": blockers[0] if blockers else "No valid eGFR observation is available."}
        for kind in REQUIRED_INPUTS:
            if kind != "egfr":
                inputs[kind] = {"freshness_status": "missing", "reason": "An eGFR index date is required before this input can be assessed."}
        return {
            "eligible": False,
            "baseline": None,
            "freshness_threshold_days": freshness_days,
            "freshness_policy": "Configurable review window; not a clinically validated threshold.",
            "inputs": inputs,
            "blockers": blockers or ["A valid eGFR baseline is required."],
            "warnings": warnings,
        }

    baseline_metadata = _input_metadata(baseline, baseline, freshness_days)
    inputs["egfr"] = baseline_metadata
    selected_input_dates = {observation_date(baseline)}
    for kind, (_, expected_unit) in REQUIRED_INPUTS.items():
        if kind == "egfr":
            continue
        candidates, same_day_ambiguous = [], False
        for row in _valid_rows(rows, kind):
            relation = _at_or_before_index(row, baseline)
            if relation is True:
                candidates.append(row)
            elif relation is None:
                same_day_ambiguous = True

        selected, latest_group, mixed_latest = _select_ordered_latest(candidates)
        if mixed_latest or same_day_ambiguous:
            candidate_rows = latest_group if mixed_latest else [row for row in _valid_rows(rows, kind) if observation_date(row) == observation_date(baseline)]
            inputs[kind] = {
                "freshness_status": "temporally_ambiguous",
                "reason": "Same-day date-only and exact-time records cannot be ordered relative to the selected eGFR baseline.",
                "candidates": [
                    {"value": float(row.value), "unit": row.unit, **observation_payload(row), "source": getattr(row, "source", None), "source_observation_id": getattr(row, "source_observation_id", None)}
                    for row in candidate_rows
                ],
            }
            blockers.append(f"{kind} is temporally ambiguous on the eGFR index date; select a baseline with resolvable event ordering.")
            continue
        if selected is None:
            future_rows = [row for row in _valid_rows(rows, kind) if observation_date(row) > observation_date(baseline)]
            reason = (
                f"Only later {kind} readings are available; readings after the selected eGFR baseline are excluded."
                if future_rows else f"A valid {kind} observation ({expected_unit}) at or before the eGFR index date is required."
            )
            inputs[kind] = {"freshness_status": "missing", "reason": reason}
            blockers.append(f"{kind} is missing at or before the selected eGFR baseline.")
            continue

        metadata = _input_metadata(selected, baseline, freshness_days)
        inputs[kind] = metadata
        selected_input_dates.add(observation_date(selected))
        if metadata["stale"]:
            blockers.append(
                f"{kind} is stale ({metadata['age_days']} days) relative to the selected eGFR baseline; update the measurement or review the configured research freshness policy."
            )

    index_date = observation_date(baseline)
    if len(selected_input_dates) > 1:
        warnings.append("Eligible measurements are from different dates; the model treats them as baseline inputs but they are not simultaneous.")

    baseline_result = {
        "observation_id": baseline.id,
        "value": float(baseline.value),
        "unit": baseline.unit,
        **observation_payload(baseline),
        "source": getattr(baseline, "source", None),
        "source_observation_id": getattr(baseline, "source_observation_id", None),
    }
    return {
        "eligible": not blockers,
        "baseline": baseline_result,
        "index_date": index_date.isoformat(),
        "freshness_threshold_days": freshness_days,
        "freshness_policy": "Configurable review window; not a clinically validated threshold.",
        "inputs": inputs,
        "blockers": blockers,
        "warnings": warnings,
    }


def rank_example_profiles(patients, counts_by_patient, observations_by_patient, freshness_days=DEFAULT_FRESHNESS_DAYS):
    """Choose up to three rich MIMIC examples that pass the current NephroQ gate."""
    candidates = []
    for patient in patients:
        if getattr(patient, "source_system", None) != "MIMIC-IV-v3.1":
            continue
        counts = counts_by_patient.get(patient.id, {})
        if not all(counts.get(kind, 0) for kind in REQUIRED_INPUTS):
            continue
        rows = observations_by_patient.get(patient.id, [])
        egfr_rows = _valid_rows(rows, "egfr")
        baseline, _, ambiguous = _select_ordered_latest(egfr_rows)
        if baseline is None or ambiguous:
            continue
        eligibility = assess_nephroq_inputs(rows, baseline.id, freshness_days)
        if not eligibility["eligible"]:
            continue
        candidates.append({
            "id": patient.id,
            "patient_code": patient.patient_code,
            "observation_count": sum(counts.values()),
            "measurement_counts": {kind: int(counts.get(kind, 0)) for kind in (
                "egfr", "creatinine", "acr", "systolic_bp", "diastolic_bp", "hba1c",
                "bun", "potassium", "bicarbonate", "urine_albumin", "urine_creatinine",
            )},
            "measurement_type_count": sum(bool(counts.get(kind, 0)) for kind in REQUIRED_INPUTS) + sum(
                bool(counts.get(kind, 0)) for kind in ("creatinine", "diastolic_bp", "bun", "potassium", "bicarbonate", "urine_albumin", "urine_creatinine")
            ),
            "index_date": eligibility["index_date"],
            "freshness_threshold_days": freshness_days,
        })

    if not candidates:
        return []

    # Pick distinct examples for broad coverage, albumin/glycemic history, and
    # repeated eGFR follow-up, rather than returning three near-identical profiles.
    selections = []
    remaining = list(candidates)
    choices = (
        ("Broadest multi-biomarker history", lambda row: (row["measurement_type_count"], row["observation_count"], row["measurement_counts"]["egfr"])),
        ("Most ACR and HbA1c observations", lambda row: (row["measurement_counts"]["acr"] + row["measurement_counts"]["hba1c"], row["measurement_type_count"], row["observation_count"])),
        ("Most recorded eGFR checkpoints", lambda row: (row["measurement_counts"]["egfr"], row["measurement_counts"]["creatinine"], row["observation_count"])),
    )
    for focus, score in choices:
        if not remaining:
            break
        selected = max(remaining, key=lambda row: (score(row), -row["id"]))
        remaining.remove(selected)
        selections.append({**selected, "focus": focus, "nephroq_eligible": True})
    return selections


def simulate_nephroq(rows, patient_id: int, years: float, baseline_observation_id=None, freshness_days=DEFAULT_FRESHNESS_DAYS):
    """Run the unchanged module only after all required inputs pass eligibility."""
    if not isfinite(years) or years <= 0 or years > 15:
        raise NephroQInputError("Simulation horizon must be greater than 0 and no more than 15 years.")
    eligibility = assess_nephroq_inputs(rows, baseline_observation_id, freshness_days)
    if not eligibility["eligible"]:
        raise NephroQInputError("Trajectory simulation blocked: " + " ".join(eligibility["blockers"]))
    inputs = eligibility["inputs"]
    values = {REQUIRED_INPUTS[kind][0]: item["value"] for kind, item in inputs.items()}
    try:
        from renal_trajectory_module import simulate_trajectory_v2
    except ImportError as exc:
        raise RuntimeError(
            "Trajectory simulation dependencies are unavailable. Install numpy and scipy from renal_trajectory_module/requirements.txt."
        ) from exc

    try:
        times, egfr_values, uacr_values, threshold_time = simulate_trajectory_v2(
            egfr0=values["egfr0"], a1c=values["a1c"], uacr0=values["uacr0"], sbp=values["sbp"],
            u=0.0, p=None, years=float(years), n=400,
        )
        trajectory = [
            {"year": float(t), "egfr": float(g), "uacr": float(a)}
            for t, g, a in zip(times, egfr_values, uacr_values, strict=True)
        ]
    except Exception as exc:
        raise RuntimeError(f"Trajectory simulation failed: {exc}") from exc
    if len(trajectory) != 400 or any(
        not all(isfinite(point[key]) for key in ("year", "egfr", "uacr")) for point in trajectory
    ):
        raise RuntimeError("The trajectory simulator returned an incomplete or non-finite result.")

    threshold_years = float(threshold_time)
    return {
        "method": "nephroq.simulate_trajectory_v2",
        "patient_id": patient_id,
        "horizon_years": float(years),
        "point_count": len(trajectory),
        "index_date": eligibility["index_date"],
        "baseline_inputs": inputs,
        "trajectory": trajectory,
        "time_to_egfr_below_15_years": threshold_years if isfinite(threshold_years) else None,
        "assumptions": {
            "u": 0.0,
            "parameter_set": "bundled TRIAL_CALIBRATION_V2 defaults (p=None)",
            "points": 400,
            "source_model": "NephroQ simulate_trajectory_v2; equations unchanged",
        },
        "eligibility": eligibility,
        "warnings": list(dict.fromkeys(eligibility["warnings"])),
        "limitations": LIMITATIONS,
    }

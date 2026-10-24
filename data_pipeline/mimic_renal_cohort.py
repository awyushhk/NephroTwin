"""Chunked, deterministic MIMIC-IV v3.1 renal cohort curation. No DB writes."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import sys
import uuid
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "mimic-renal-cohort-1.0"
DEFAULT_RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "processed" / "mimic_renal_cohort"
SOURCE_SYSTEM = "MIMIC-IV v3.1"
PATIENT_COLUMNS = ["internal_patient_id", "source_subject_id", "gender", "anchor_age", "anchor_age_interpretation", "anchor_year", "anchor_year_group", "eligibility_status", "research_group", "selected_renal_observation_count", "earliest_observation_timestamp", "latest_observation_timestamp"]
OBSERVATION_COLUMNS = ["internal_patient_id", "source_subject_id", "source_observation_id", "mimic_item_id", "original_lab_label", "canonical_measurement", "original_value", "original_numeric_value", "original_unit", "standardized_value", "standardized_unit", "charttime", "charttime_timezone", "hadm_id", "admission_time", "discharge_time", "source_table", "provenance", "validation_flags"]
MANIFEST_COLUMNS = ["internal_patient_id", "source_subject_id", "selection_status", "eligibility_criteria", "research_group", "research_group_evidence", "creatinine_observation_count", "observation_count_by_measurement", "missing_measurement_types", "earliest_observation_timestamp", "latest_observation_timestamp", "temporal_coverage_days", "data_quality_flags"]
LAB_COLUMNS = ["labevent_id", "subject_id", "hadm_id", "itemid", "charttime", "value", "valuenum", "valueuom", "flag"]
MAX_VALUES = {"creatinine": 100.0, "egfr": 250.0, "acr": 100000.0, "bun": 1000.0, "potassium": 30.0, "bicarbonate": 100.0, "urine_albumin": 100000.0, "urine_creatinine": 100000.0}
MIN_VALUES = {"creatinine": 0.05, "egfr": 0.0, "acr": 0.0, "bun": 0.0, "potassium": 0.0, "bicarbonate": 0.0, "urine_albumin": 0.0, "urine_creatinine": 0.0}
STD_UNITS = {"creatinine": "mg/dL", "egfr": "mL/min/1.73m2", "acr": "mg/g", "bun": "mg/dL", "potassium": "mmol/L", "bicarbonate": "mmol/L", "urine_albumin": "mg/dL", "urine_creatinine": "mg/dL"}


def read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))


def classify_lab_item(row: dict[str, str]) -> tuple[str | None, str]:
    """Select exact blood/urine lab concepts; broad keyword matches are excluded."""
    label = " ".join((row.get("label") or "").lower().split())
    fluid = " ".join((row.get("fluid") or "").lower().split())
    category = " ".join((row.get("category") or "").lower().split())
    if fluid == "blood":
        if label in {"creatinine", "creatinine, serum", "creatinine, blood"}:
            return "creatinine", "Exact serum/blood creatinine label and Blood fluid"
        if label.startswith("estimated gfr"):
            return "egfr", "Explicit Estimated GFR label and Blood fluid"
        if label in {"urea nitrogen", "bun"}:
            return "bun", "Exact blood urea nitrogen label and Blood fluid"
        if label == "potassium" and category == "chemistry":
            return "potassium", "Exact potassium label, Blood fluid, Chemistry category"
        if label == "bicarbonate" and category == "chemistry":
            return "bicarbonate", "Exact bicarbonate label, Blood fluid, Chemistry category"
    if fluid == "urine":
        if label in {"albumin/creatinine, urine", "albumin/creatinine ratio, urine", "albumin creatinine ratio, urine"}:
            return "acr", "Explicit urine albumin/creatinine ratio label and Urine fluid"
        if label == "albumin, urine":
            return "urine_albumin", "Exact urine albumin label and Urine fluid; concentration is not ACR"
        if label in {"creatinine, urine", "urine creatinine"}:
            return "urine_creatinine", "Exact urine creatinine label and Urine fluid; not used to derive ACR"
    return None, "Not selected: non-target, ambiguous, non-blood/non-urine, or different assay definition"


def is_renal_candidate(row: dict[str, str]) -> bool:
    text = " ".join((row.get(k) or "") for k in ("label", "fluid", "category")).lower()
    return any(term in text for term in ("creatin", "gfr", "albumin", "urea nitrogen", "bun", "potassium", "bicarbonate"))


def normalize_unit(unit: str | None) -> str:
    return " ".join((unit or "").strip().lower().replace("μ", "µ").replace("²", "2").replace("^", "").split())


def standardize(measurement: str | None, value: float | None, unit: str | None) -> tuple[float | None, str | None, str]:
    if measurement is None:
        return None, None, "excluded_item"
    if value is None or not math.isfinite(value):
        return None, None, "missing_or_nonfinite_numeric_value"
    u = normalize_unit(unit)
    rules: dict[str, dict[str, tuple[float, str]]] = {
        "creatinine": {"mg/dl": (1.0, "identity mg/dL"), "µmol/l": (1 / 88.4, "µmol/L to mg/dL using 88.4 µmol/L per mg/dL"), "umol/l": (1 / 88.4, "umol/L to mg/dL using 88.4 µmol/L per mg/dL"), "micromol/l": (1 / 88.4, "micromol/L to mg/dL using 88.4 µmol/L per mg/dL")},
        "egfr": {"ml/min/1.73m2": (1.0, "identity; already indexed to 1.73 m2"), "ml/min/1.73 m2": (1.0, "identity; already indexed to 1.73 m2"), "ml/min/1.73 m^2": (1.0, "identity; already indexed to 1.73 m2")},
        "acr": {"mg/g": (1.0, "identity mg/g"), "mg/mmol": (8.84, "mg/mmol to mg/g using 8.84 conversion"), "mg/mmol creatinine": (8.84, "mg/mmol to mg/g using 8.84 conversion")},
        "bun": {"mg/dl": (1.0, "identity mg/dL"), "mmol/l": (2.801, "urea nitrogen mmol/L to BUN mg/dL using 2.801")},
        "potassium": {"mmol/l": (1.0, "identity mmol/L"), "meq/l": (1.0, "potassium monovalent mEq/L numerically equals mmol/L")},
        "bicarbonate": {"mmol/l": (1.0, "identity mmol/L"), "meq/l": (1.0, "bicarbonate mEq/L numerically equals mmol/L")},
        "urine_albumin": {"mg/dl": (1.0, "identity mg/dL"), "mg/l": (0.1, "mg/L to mg/dL"), "mg/24 hr": (None, "unsupported timed excretion unit")},
        "urine_creatinine": {"mg/dl": (1.0, "identity mg/dL"), "mmol/l": (11.312, "creatinine mmol/L to mg/dL using 113.12 mg/mmol")},
    }
    rule = rules.get(measurement, {}).get(u)
    if not rule or rule[0] is None:
        return None, None, "unrecognized_or_unsupported_original_unit"
    converted = value * rule[0]
    if not math.isfinite(converted) or converted < MIN_VALUES[measurement] or converted > MAX_VALUES[measurement]:
        return None, None, "outside_broad_supported_value_range_manual_review"
    return converted, STD_UNITS[measurement], rule[1]


def parse_timestamp(value: str | None) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo is None else None
    except ValueError:
        return None


def parse_numeric(value: str | None) -> float | None:
    try:
        number = float(value) if value and value.strip() else None
        return number if number is not None and math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def internal_patient_id(subject_id: str) -> str:
    return f"mimiciv31:{subject_id}"


def patient_is_eligible(creatinine_count: int, first: datetime | None, last: datetime | None, min_span_days: float = 1.0) -> bool:
    return creatinine_count >= 2 and first is not None and last is not None and (last - first).total_seconds() >= min_span_days * 86400


def select_subjects(stats: dict[str, dict[str, Any]], target: int, min_span_days: float) -> tuple[list[str], dict[str, str]]:
    eligible = []
    reasons = {}
    for subject, item in stats.items():
        if patient_is_eligible(item["creatinine_count"], item["first"], item["last"], min_span_days):
            eligible.append(subject)
        else:
            reasons[subject] = "fewer than two valid standardized blood creatinine observations at distinct times spanning the configured minimum"
    eligible.sort(key=lambda subject: (-stats[subject]["span_days"], -stats[subject]["creatinine_count"], hashlib.sha256(subject.encode()).hexdigest()))
    return eligible[:target], reasons


def read_dict_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        return list(reader.fieldnames), list(reader)


def load_item_mapping(path: Path) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    headers, rows = read_dict_csv(path)
    required = {"itemid", "label", "fluid", "category"}
    if not required.issubset(headers):
        raise ValueError(f"d_labitems.csv missing required columns: {sorted(required - set(headers))}")
    mappings: dict[str, dict[str, str]] = {}
    output = []
    for row in rows:
        canonical, evidence = classify_lab_item(row)
        if canonical or is_renal_candidate(row):
            mappings[row["itemid"]] = {**row, "canonical_measurement": canonical or "", "mapping_evidence": evidence}
    return mappings, output


def input_headers(raw_dir: Path) -> dict[str, list[str]]:
    expected = {
        "patients.csv": {"subject_id", "gender", "anchor_age", "anchor_year", "anchor_year_group"},
        "admissions.csv": {"subject_id", "hadm_id", "admittime", "dischtime"},
        "d_labitems.csv": {"itemid", "label", "fluid", "category"},
        "labevents.csv": set(LAB_COLUMNS),
    }
    result = {}
    for name, required in expected.items():
        path = raw_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"Required MIMIC input is missing: {path}")
        header = read_header(path)
        missing = required - set(header)
        if missing:
            raise ValueError(f"{name} is missing required columns: {sorted(missing)}")
        result[name] = header
    return result


def stream_labs(path: Path, invalid_counter: Counter, item_ids: set[str], subjects: set[str] | None = None):
    try:
        import pyarrow as pa
        import pyarrow.csv as pacsv
        import pyarrow.compute as pc
    except ImportError as exc:
        raise RuntimeError("Efficient MIMIC scanning needs PyArrow. Install it with: python -m pip install pyarrow") from exc
    names = LAB_COLUMNS
    types = {name: pa.string() for name in names}
    def invalid_row(_row):
        invalid_counter["malformed_csv_rows_skipped"] += 1
        return "skip"
    reader = pacsv.open_csv(
        str(path),
        read_options=pacsv.ReadOptions(block_size=8 * 1024 * 1024, use_threads=False),
        parse_options=pacsv.ParseOptions(invalid_row_handler=invalid_row),
        convert_options=pacsv.ConvertOptions(include_columns=names, column_types=types, strings_can_be_null=False),
    )
    item_values = pa.array(sorted(item_ids), type=pa.string())
    subject_values = pa.array(sorted(subjects), type=pa.string()) if subjects is not None else None
    rows_scanned, next_report = 0, 10_000_000
    for batch in reader:
        rows_scanned += batch.num_rows
        mask = pc.is_in(batch.column("itemid"), value_set=item_values)
        if subject_values is not None:
            mask = pc.and_(mask, pc.is_in(batch.column("subject_id"), value_set=subject_values))
        filtered = pc.filter(batch, mask)
        if filtered.num_rows:
            invalid_counter["mapped_rows"] += filtered.num_rows
            yield from filtered.to_pylist()
        if rows_scanned >= next_report:
            print(f"  scanned {rows_scanned:,} labevents rows; mapped rows in current pass {invalid_counter.get('mapped_rows', 0):,}", flush=True)
            next_report = ((rows_scanned // 10_000_000) + 1) * 10_000_000


def load_admissions(path: Path, selected: set[str]) -> dict[tuple[str, str], tuple[str, str]]:
    result = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            subject = row.get("subject_id", "")
            if subject in selected and row.get("hadm_id"):
                result[(subject, row["hadm_id"])] = (row.get("admittime", ""), row.get("dischtime", ""))
    return result


def load_patients(path: Path, selected: set[str]) -> tuple[dict[str, dict[str, str]], int]:
    result = {}
    total = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            total += 1
            if row.get("subject_id") in selected:
                result[row["subject_id"]] = row
    return result, total


def safe_atomic_publish(stage: Path, destination: Path) -> None:
    backup = destination.with_name(destination.name + ".previous-" + datetime.now().strftime("%Y%m%d%H%M%S"))
    moved_old = False
    try:
        if destination.exists():
            os.replace(destination, backup)
            moved_old = True
        os.replace(stage, destination)
    except Exception:
        if moved_old and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise


def _write_csv(path: Path, columns: list[str]):
    handle = path.open("w", encoding="utf-8", newline="")
    writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    return handle, writer


def classify_research_group(events: dict[str, list[tuple[datetime, float, str, str]]]) -> tuple[str, str]:
    creat = sorted(events.get("creatinine", []), key=lambda x: (x[0], x[2]))
    by_time: dict[datetime, tuple[float, str]] = {}
    for when, value, itemid, _flag in creat:
        if when not in by_time or value > by_time[when][0]: by_time[when] = (value, itemid)
    times = sorted(by_time)
    min48, min7 = deque(), deque()
    left48 = left7 = 0
    for i, when in enumerate(times):
        value, itemid = by_time[when]
        while left48 < i and (when - times[left48]).total_seconds() > 2 * 86400:
            left48 += 1
        while min48 and min48[0] < left48: min48.popleft()
        while left7 < i and (when - times[left7]).total_seconds() > 7 * 86400:
            left7 += 1
        while min7 and min7[0] < left7: min7.popleft()
        if min48 and value - by_time[times[min48[0]]][0] >= 0.3:
            return "acute_creatinine_change_candidate", f"Observed serum creatinine rise >=0.3 mg/dL in <=48h (item {by_time[times[min48[0]]][1]} to {itemid}); screening criterion only, not an AKI diagnosis"
        if min7 and by_time[times[min7[0]]][0] > 0 and value >= 1.5 * by_time[times[min7[0]]][0]:
            return "acute_creatinine_change_candidate", f"Observed serum creatinine ratio >=1.5 within <=7d (item {by_time[times[min7[0]]][1]} to {itemid}); screening criterion only, not an AKI diagnosis"
        while min48 and by_time[times[min48[-1]]][0] >= value: min48.pop()
        min48.append(i)
        while min7 and by_time[times[min7[-1]]][0] >= value: min7.pop()
        min7.append(i)
    for measure, threshold, relation in (("egfr", 60.0, "below"), ("acr", 30.0, "at_or_above")):
        vals = sorted(events.get(measure, []), key=lambda x: x[0])
        abnormal = [e for e in vals if (e[1] < threshold if relation == "below" else e[1] >= threshold)]
        if len(abnormal) >= 2 and (abnormal[-1][0] - abnormal[0][0]).total_seconds() >= 90 * 86400:
            return "persistent_renal_measurement_abnormality_review_candidate", f"At least two standardized {measure} observations met the configured category threshold >=90d apart; incomplete source context, not a CKD diagnosis"
    valid_count = len(creat)
    if valid_count >= 3 and creat and (creat[-1][0] - creat[0][0]).total_seconds() >= 90 * 86400:
        return "repeated_observation_comparison_group", "Repeated standardized serum creatinine observations spanning >=90d without the screening rules above; not healthy or CKD-free"
    return "insufficient_evidence_or_data_quality", "Repeated source observations do not provide >=90d chronicity evidence or do not satisfy the specified screening rules"


def build(raw_dir: Path = DEFAULT_RAW, destination: Path = DEFAULT_OUTPUT, target_count: int = 1000, min_span_days: float = 1.0) -> dict[str, Any]:
    headers = input_headers(raw_dir)
    item_rows = read_dict_csv(raw_dir / "d_labitems.csv")[1]
    mapping: dict[str, dict[str, str]] = {}
    for row in item_rows:
        canonical, evidence = classify_lab_item(row)
        if canonical or is_renal_candidate(row):
            mapping[row["itemid"]] = {**row, "canonical_measurement": canonical or "", "mapping_evidence": evidence}
    selected_item_ids = {k for k, v in mapping.items() if v["canonical_measurement"]}
    if not selected_item_ids:
        raise RuntimeError("No supported renal lab concepts were found in d_labitems.csv; refusing to create outputs.")

    invalid = Counter()
    stats: dict[str, dict[str, Any]] = {}
    raw_counts, valid_measure_counts, unit_counts, quality_full = Counter(), Counter(), Counter(), Counter()
    print(f"Scanning {raw_dir / 'labevents.csv'} in Arrow CSV blocks; only mapped renal concepts are retained.", flush=True)
    for row in stream_labs(raw_dir / "labevents.csv", invalid, selected_item_ids):
        item = mapping.get(row["itemid"])
        if not item or not item["canonical_measurement"]:
            continue
        subject, measure = row["subject_id"], item["canonical_measurement"]
        raw_counts[measure] += 1
        unit_counts[(row.get("itemid", ""), row.get("valueuom", ""))] += 1
        val = parse_numeric(row.get("valuenum"))
        stamp = parse_timestamp(row.get("charttime"))
        standardized, _, _ = standardize(measure, val, row.get("valueuom"))
        if val is None: quality_full["missing_or_nonfinite_numeric_value"] += 1
        if stamp is None: quality_full["missing_or_invalid_or_timezone_offset_charttime"] += 1
        if standardized is None:
            _, _, problem = standardize(measure, val, row.get("valueuom"))
            quality_full[problem] += 1
        if measure == "creatinine" and standardized is not None and stamp is not None:
            info = stats.setdefault(subject, {"creatinine_count": 0, "first": stamp, "last": stamp, "measurement_counts": Counter()})
            info["creatinine_count"] += 1
            info["first"] = min(info["first"], stamp)
            info["last"] = max(info["last"], stamp)
            info["measurement_counts"][measure] += 1
            valid_measure_counts[measure] += 1
        elif standardized is not None and stamp is not None:
            valid_measure_counts[measure] += 1
    for info in stats.values():
        info["span_days"] = max(0.0, (info["last"] - info["first"]).total_seconds() / 86400)
    chosen, excluded = select_subjects(stats, target_count, min_span_days)
    selected = set(chosen)
    print(f"Eligible subjects: {len([s for s,v in stats.items() if patient_is_eligible(v['creatinine_count'],v['first'],v['last'],min_span_days)])}; selected: {len(chosen)}.", flush=True)
    if not chosen:
        raise RuntimeError("No subjects meet the configured repeated, timestamped creatinine eligibility criteria; no output published.")

    demographics, subjects_considered = load_patients(raw_dir / "patients.csv", selected)
    admissions = load_admissions(raw_dir / "admissions.csv", selected)
    temp_parent = destination.parent
    temp_parent.mkdir(parents=True, exist_ok=True)
    stage = temp_parent / f"{destination.name}-staging-{uuid.uuid4().hex}"
    stage.mkdir()
    all_stats = {s: {"creatinine_count": stats[s]["creatinine_count"], "counts": Counter(), "valid_counts": Counter(), "first": None, "last": None, "flags": Counter()} for s in chosen}
    group_events: dict[str, dict[str, list[tuple[datetime, float, str, str]]]] = defaultdict(lambda: defaultdict(list))
    seen_source_ids: set[str] = set()
    observation_count = 0
    flag_counts = Counter()
    output_units = Counter()
    try:
        obs_handle, obs_writer = _write_csv(stage / "renal_observations.csv", OBSERVATION_COLUMNS)
        with obs_handle:
            for row in stream_labs(raw_dir / "labevents.csv", invalid, selected_item_ids, selected):
                subject = row["subject_id"]
                if subject not in selected:
                    continue
                item = mapping.get(row["itemid"])
                if not item or not item["canonical_measurement"]:
                    continue
                measure = item["canonical_measurement"]
                value = parse_numeric(row.get("valuenum"))
                stamp = parse_timestamp(row.get("charttime"))
                standardized, std_unit, conversion = standardize(measure, value, row.get("valueuom"))
                flags = []
                if value is None: flags.append("missing_or_nonfinite_numeric_value")
                if stamp is None: flags.append("missing_or_invalid_charttime")
                if standardized is None: flags.append(conversion)
                if not row.get("labevent_id"): flags.append("missing_source_observation_id")
                if row.get("labevent_id") and row["labevent_id"] in seen_source_ids: flags.append("duplicate_source_observation_id")
                elif row.get("labevent_id"): seen_source_ids.add(row["labevent_id"])
                if row.get("flag") and row["flag"].strip(): flags.append("source_abnormal_flag:" + row["flag"].strip())
                admit, discharge = admissions.get((subject, row.get("hadm_id", "")), ("", ""))
                obs_writer.writerow({"internal_patient_id": internal_patient_id(subject), "source_subject_id": subject, "source_observation_id": row.get("labevent_id", ""),
                    "mimic_item_id": row["itemid"], "original_lab_label": item["label"], "canonical_measurement": measure, "original_value": row.get("value", ""),
                    "original_numeric_value": "" if value is None else value, "original_unit": row.get("valueuom", ""), "standardized_value": "" if standardized is None else standardized,
                    "standardized_unit": std_unit or "", "charttime": row.get("charttime", ""), "charttime_timezone": "unspecified (MIMIC source timestamp has no zone)",
                    "hadm_id": row.get("hadm_id", ""), "admission_time": admit, "discharge_time": discharge, "source_table": "labevents",
                    "provenance": f"{SOURCE_SYSTEM}; d_labitems.itemid={row['itemid']}; charttime preserved as supplied", "validation_flags": ";".join(flags)})
                observation_count += 1
                output_units[(measure, row.get("valueuom", ""))] += 1
                flag_counts.update(flags)
                patient_stats = all_stats[subject]
                patient_stats["counts"][measure] += 1
                if standardized is not None and stamp is not None: patient_stats["valid_counts"][measure] += 1
                if flags: patient_stats["flags"].update(flags)
                if stamp:
                    patient_stats["first"] = stamp if patient_stats["first"] is None else min(patient_stats["first"], stamp)
                    patient_stats["last"] = stamp if patient_stats["last"] is None else max(patient_stats["last"], stamp)
                if standardized is not None and stamp is not None and measure in {"creatinine", "egfr", "acr"}:
                    group_events[subject][measure].append((stamp, standardized, row["itemid"], row.get("flag", "")))

        patient_handle, patient_writer = _write_csv(stage / "patients.csv", PATIENT_COLUMNS)
        manifest_handle, manifest_writer = _write_csv(stage / "cohort_manifest.csv", MANIFEST_COLUMNS)
        group_counts = Counter()
        with patient_handle, manifest_handle:
            for subject in sorted(chosen, key=lambda s: int(s)):
                p = demographics.get(subject)
                if not p:
                    raise RuntimeError(f"Selected subject {subject} is missing from patients.csv; no output published.")
                data = all_stats[subject]
                group, evidence = classify_research_group(group_events[subject])
                group_counts[group] += 1
                first = data["first"].isoformat(sep=" ") if data["first"] else ""
                last = data["last"].isoformat(sep=" ") if data["last"] else ""
                count_all = sum(data["counts"].values())
                age = p.get("anchor_age", "")
                interpretation = "MIMIC anchor_age at anchor_year; values >=91 are top-coded/deidentified, not exact age"
                missing = sorted(set(STD_UNITS) - set(data["valid_counts"]))
                counts = json.dumps(dict(sorted(data["counts"].items())), sort_keys=True)
                quality = ";".join(sorted(data["flags"]))
                patient_writer.writerow({"internal_patient_id": internal_patient_id(subject), "source_subject_id": subject, "gender": p.get("gender", ""), "anchor_age": age,
                    "anchor_age_interpretation": interpretation, "anchor_year": p.get("anchor_year", ""), "anchor_year_group": p.get("anchor_year_group", ""),
                    "eligibility_status": "selected_eligible", "research_group": group, "selected_renal_observation_count": count_all,
                    "earliest_observation_timestamp": first, "latest_observation_timestamp": last})
                coverage = (data["last"] - data["first"]).total_seconds() / 86400 if data["first"] and data["last"] else 0
                manifest_writer.writerow({"internal_patient_id": internal_patient_id(subject), "source_subject_id": subject, "selection_status": "selected_eligible",
                    "eligibility_criteria": f">=2 finite in-range blood creatinine observations with validated mg/dL standardization, spanning >={min_span_days:g} days",
                    "research_group": group, "research_group_evidence": evidence, "creatinine_observation_count": data["creatinine_count"],
                    "observation_count_by_measurement": counts, "missing_measurement_types": ";".join(missing), "earliest_observation_timestamp": first,
                    "latest_observation_timestamp": last, "temporal_coverage_days": round(coverage, 4), "data_quality_flags": quality})

        mapping_path = stage / "lab_item_mapping.csv"
        item_unit_seen: dict[str, Counter] = defaultdict(Counter)
        for (itemid, unit), count in unit_counts.items(): item_unit_seen[itemid][unit] += count
        with mapping_path.open("w", encoding="utf-8", newline="") as handle:
            cols = ["mimic_item_id", "original_label", "fluid", "category", "canonical_measurement", "accepted_original_units", "validated_conversion_rule", "included", "exclusion_reason", "dictionary_mapping_evidence", "raw_event_count"]
            writer = csv.DictWriter(handle, fieldnames=cols); writer.writeheader()
            for itemid, item in sorted(mapping.items(), key=lambda pair: int(pair[0])):
                canonical = item["canonical_measurement"]
                observed_units = item_unit_seen[itemid]
                accepted, conversions = [], []
                for unit in sorted(observed_units):
                    _, _, rule = standardize(canonical, 1.0, unit)
                    if canonical and rule not in {"unrecognized_or_unsupported_original_unit", "outside_broad_supported_value_range_manual_review"}:
                        accepted.append(unit or "<blank>"); conversions.append(f"{unit or '<blank>'}: {rule}")
                included = bool(canonical)
                writer.writerow({"mimic_item_id": itemid, "original_label": item["label"], "fluid": item["fluid"], "category": item["category"],
                    "canonical_measurement": canonical, "accepted_original_units": ";".join(accepted), "validated_conversion_rule": ";".join(conversions),
                    "included": str(included).lower(), "exclusion_reason": "" if included else item["mapping_evidence"],
                    "dictionary_mapping_evidence": item["mapping_evidence"], "raw_event_count": sum(observed_units.values())})

        outputs = ["patients.csv", "renal_observations.csv", "cohort_manifest.csv", "lab_item_mapping.csv"]
        audit = {
            "pipeline_version": VERSION, "source_dataset": SOURCE_SYSTEM, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "input_files": {name: {"path": str(raw_dir / name), "header": header, "size_bytes": (raw_dir / name).stat().st_size} for name, header in headers.items()},
            "configuration": {"target_count": target_count, "minimum_span_days": min_span_days, "minimum_standardized_creatinine_observations": 2, "selection_order": "longest creatinine temporal coverage, then highest count, then SHA-256 subject-id order", "timestamp_policy": "preserve source charttime text; source has no timezone", "timezone": "unspecified in source"},
            "selection_rules": {"inclusion": "At least 2 valid blood creatinine observations with supported unit conversion and distinct charttime span meeting minimum; only selected renal lab concepts retained.",
                "research_groups": {"acute_creatinine_change_candidate": "KDIGO creatinine screening thresholds: +0.3 mg/dL within 48h or >=1.5x an earlier observation within 7d; candidate only, no urine output/clinical context and not AKI diagnosis.",
                    "persistent_renal_measurement_abnormality_review_candidate": "Explicit standardized eGFR <60 or ACR >=30 mg/g at observations >=90d apart; review candidate, not diagnosis.",
                    "repeated_observation_comparison_group": ">=3 valid creatinine observations spanning >=90d, no above screening rules; not healthy/CKD-free.",
                    "insufficient_evidence_or_data_quality": "Selected longitudinal cohort members without >=90d evidence or screening-rule match."},
                "selection_precedence": ["acute creatinine change candidate", "persistent measurement abnormality review candidate", "repeated-observation comparison", "insufficient evidence/data quality"]},
            "subject_counts": {"subjects_considered_from_patients_file": subjects_considered, "subjects_with_valid_creatinine": len(stats), "eligible_subjects": sum(patient_is_eligible(v["creatinine_count"], v["first"], v["last"], min_span_days) for v in stats.values()), "selected_subjects": len(chosen), "target_count": target_count, "excluded_from_selection": len(stats) - len(chosen)},
            "observations": {"selected_mapped_source_rows": observation_count, "counts_per_measurement": dict(sorted(Counter({m: sum(s["counts"][m] for s in all_stats.values()) for m in STD_UNITS}).items())),
                "raw_mapped_event_counts_full_dataset": dict(sorted(raw_counts.items())), "valid_standardizable_counts_full_dataset": dict(sorted(valid_measure_counts.items())),
                "validation_flag_counts_full_dataset_mapped_rows": dict(sorted(quality_full.items())), "validation_flag_counts_selected_rows": dict(sorted(flag_counts.items())), "unit_distribution_selected": {f"{m}|{u or '<blank>'}": n for (m, u), n in sorted(output_units.items())},
                "unit_distribution_full_mapped": {f"{item}|{unit or '<blank>'}": n for (item, unit), n in sorted(unit_counts.items())}},
            "research_group_counts": dict(sorted(group_counts.items())), "malformed_csv_rows_skipped": invalid["malformed_csv_rows_skipped"],
            "limitations": ["MIMIC-IV is a deidentified single-center hospital EHR cohort, not representative of the general population.", "Available files lack diagnosis-code tables, ICU chartevents, medication data, urine output, and broader clinical context.", "Anchor ages 91 and above are top-coded; age is not recalculated at lab timestamps.", "MIMIC charttime values are deidentified and timezone-free; the exact source text is retained.", "Creatinine screening does not diagnose AKI; eGFR/ACR repeated abnormality groups are review candidates, not CKD diagnoses.", "No eGFR/ACR is derived from serum/urine creatinine or albumin concentrations.", "The synthetic seed utility is not used by this pipeline; cohort outputs contain source observations only."],
            "attribution": "Johnson AE et al. MIMIC-IV, a freely accessible electronic health record dataset. Scientific Data. 2023;10(1):1. Access subject to MIMIC data use agreement.",
        }
        for name in outputs:
            path = stage / name
            audit.setdefault("output_files", {})[name] = {"rows": _csv_count(path), "size_bytes": path.stat().st_size, "sha256": _sha256(path)}
        audit["output_files"]["cohort_audit.json"] = {"rows": 1, "size_bytes": 0, "sha256": "not_self-hashed"}
        audit_path = stage / "cohort_audit.json"
        for _ in range(3):
            audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")
            size = audit_path.stat().st_size
            if audit["output_files"]["cohort_audit.json"]["size_bytes"] == size: break
            audit["output_files"]["cohort_audit.json"]["size_bytes"] = size
        audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")
        validate_directory(stage)
        safe_atomic_publish(stage, destination)
        return audit
    except Exception:
        if stage.exists(): shutil.rmtree(stage, ignore_errors=True)
        raise


def _csv_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return max(0, sum(1 for _ in handle) - 1)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_directory(directory: Path) -> dict[str, Any]:
    required = {"patients.csv": PATIENT_COLUMNS, "renal_observations.csv": OBSERVATION_COLUMNS, "cohort_manifest.csv": MANIFEST_COLUMNS, "lab_item_mapping.csv": None, "cohort_audit.json": None}
    for filename, columns in required.items():
        path = directory / filename
        if not path.is_file(): raise ValueError(f"Missing processed file: {path}")
        if columns and not set(columns).issubset(read_header(path)): raise ValueError(f"Processed schema invalid: {filename}")
    patients = {}
    with (directory / "patients.csv").open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            subject = row["source_subject_id"]
            if subject in patients: raise ValueError(f"Duplicate selected subject: {subject}")
            patients[subject] = row
    manifest = {}
    with (directory / "cohort_manifest.csv").open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["source_subject_id"] in manifest: raise ValueError("Duplicate subject in manifest")
            manifest[row["source_subject_id"]] = row
    if set(patients) != set(manifest): raise ValueError("patients.csv and cohort_manifest.csv subject sets disagree")
    counts, ids, timestamps, references = Counter(), set(), Counter(), set()
    patient_measure_counts, measure_counts = Counter(), Counter()
    with (directory / "renal_observations.csv").open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            subject = row["source_subject_id"]
            if subject not in patients: raise ValueError(f"Observation references unselected subject {subject}")
            counts[subject] += 1
            patient_measure_counts[(subject, row["canonical_measurement"])] += 1
            measure_counts[row["canonical_measurement"]] += 1
            sid = row["source_observation_id"]
            if sid:
                if sid in ids: raise ValueError(f"Duplicate source observation ID: {sid}")
                ids.add(sid)
            if row["charttime"] and parse_timestamp(row["charttime"]) is None: raise ValueError(f"Unparseable timestamp in source observation {sid}")
            if row["standardized_value"]:
                val = parse_numeric(row["standardized_value"])
                if val is None or row["standardized_unit"] != STD_UNITS.get(row["canonical_measurement"]): raise ValueError(f"Invalid standardized value/unit for observation {sid}")
            timestamps.update([row["charttime"]] if row["charttime"] else [])
    for subject, row in patients.items():
        if counts[subject] != int(row["selected_renal_observation_count"]): raise ValueError(f"Patient observation count mismatch for {subject}")
        declared = json.loads(manifest[subject]["observation_count_by_measurement"] or "{}")
        actual = {measure: patient_measure_counts[(subject, measure)] for measure in sorted(STD_UNITS) if patient_measure_counts[(subject, measure)]}
        if declared != actual: raise ValueError(f"Manifest per-measurement counts mismatch for {subject}")
    with (directory / "lab_item_mapping.csv").open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["included"] == "true" and not row["canonical_measurement"]: raise ValueError("Included item mapping lacks canonical measurement")
    audit = json.loads((directory / "cohort_audit.json").read_text(encoding="utf-8"))
    for filename, details in audit.get("output_files", {}).items():
        if filename == "cohort_audit.json": continue
        file_path = directory / filename
        if file_path.stat().st_size != details["size_bytes"] or _sha256(file_path) != details["sha256"]: raise ValueError(f"Processed output hash/size differs from cohort audit: {filename}")
    item_map = {}
    with (directory / "lab_item_mapping.csv").open("r", encoding="utf-8", newline="") as handle:
        item_map = {row["mimic_item_id"]: row for row in csv.DictReader(handle)}
    with (directory / "renal_observations.csv").open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["internal_patient_id"].startswith("SYNTH-"): raise ValueError("Synthetic patient rows found in MIMIC cohort output")
            mapping = item_map.get(row["mimic_item_id"])
            if not mapping or mapping["included"] != "true" or mapping["canonical_measurement"] != row["canonical_measurement"]: raise ValueError(f"Observation has no matching included item mapping: {row['source_observation_id']}")
            if not row["standardized_value"] and not row["validation_flags"]: raise ValueError(f"Unstandardized observation has no quality flag: {row['source_observation_id']}")
    if len(patients) != audit["subject_counts"]["selected_subjects"]: raise ValueError("Selected patient count differs from audit")
    if counts.total() != audit["output_files"]["renal_observations.csv"]["rows"]: raise ValueError("Observation count differs from audit")
    if dict(measure_counts) != audit["observations"]["counts_per_measurement"]: raise ValueError("Per-measurement observation counts differ from audit")
    return {"selected_patients": len(patients), "observations": counts.total(), "distinct_source_observation_ids": len(ids), "unique_charttime_values": sum(1 for _ in timestamps), "research_group_counts": dict(Counter(row["research_group"] for row in patients.values()))}


def print_report(directory: Path) -> None:
    audit = json.loads((directory / "cohort_audit.json").read_text(encoding="utf-8"))
    manifest = list(csv.DictReader((directory / "cohort_manifest.csv").open("r", encoding="utf-8", newline="")))
    coverage = sorted(float(row["temporal_coverage_days"]) for row in manifest)
    def q(p): return coverage[min(len(coverage)-1, int((len(coverage)-1)*p))] if coverage else 0
    print(f"Dataset: {audit['source_dataset']} | Pipeline: {audit['pipeline_version']}")
    print(f"Selected patients: {audit['subject_counts']['selected_subjects']} of {audit['subject_counts']['eligible_subjects']} eligible; target {audit['subject_counts']['target_count']}")
    print(f"Selected renal observation rows: {audit['observations']['selected_mapped_source_rows']}")
    print(f"Temporal coverage days (min / median / max): {coverage[0] if coverage else 0:.1f} / {q(.5):.1f} / {coverage[-1] if coverage else 0:.1f}")
    print("Groups:", json.dumps(audit["research_group_counts"], sort_keys=True))
    print("Missing mapped data counts:", json.dumps({m: sum(1 for r in manifest if m in r["missing_measurement_types"].split(";")) for m in sorted(STD_UNITS)}, sort_keys=True))
    print("Validation flags:", json.dumps(audit["observations"]["validation_flag_counts_selected_rows"], sort_keys=True))
    print("Limitations:")
    for item in audit["limitations"]: print(" -", item)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inspect", help="Check headers and show dictionary item mapping; does not scan labevents")
    for name in ("dry-run", "build"):
        cmd = sub.add_parser(name, help="Scan raw labs in bounded Arrow blocks and produce processed CSVs (never writes PostgreSQL)")
        cmd.add_argument("--target-count", type=int, default=1000)
        cmd.add_argument("--minimum-creatinine-span-days", type=float, default=1.0)
    sub.add_parser("validate", help="Validate processed CSV consistency without modifying data")
    sub.add_parser("report", help="Print cohort composition, coverage, missingness, and quality review")
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            headers = input_headers(args.raw_dir)
            print(json.dumps({"files": headers}, indent=2))
            mappings, _ = load_item_mapping(args.raw_dir / "d_labitems.csv")
            for itemid, item in sorted(mappings.items(), key=lambda p: int(p[0])):
                print(f"{itemid}\t{item['label']}\t{item['fluid']}\t{item['category']}\t{item['canonical_measurement']}\t{item['mapping_evidence']}")
        elif args.command in {"dry-run", "build"}:
            if args.target_count < 1 or args.minimum_creatinine_span_days < 0: raise ValueError("target count must be positive and minimum span nonnegative")
            audit = build(args.raw_dir, args.output_dir, args.target_count, args.minimum_creatinine_span_days)
            print_report(args.output_dir)
            print(f"Processed outputs atomically published to {args.output_dir}; PostgreSQL was not modified.")
        elif args.command == "validate":
            print(json.dumps(validate_directory(args.output_dir), indent=2))
        elif args.command == "report":
            print_report(args.output_dir)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

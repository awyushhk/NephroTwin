"""Append verified HbA1c observations to the already-selected MIMIC cohort.

The command never reselects patients and never connects to PostgreSQL. Without
--publish it validates a staged result and prints a preview without modifying
the published cohort. --publish atomically replaces the processed directory.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

from data_pipeline.mimic_renal_cohort import (
    DEFAULT_OUTPUT, DEFAULT_RAW, OBSERVATION_COLUMNS, PATIENT_COLUMNS,
    MANIFEST_COLUMNS, input_headers, parse_numeric, parse_timestamp,
    read_dict_csv, safe_atomic_publish, standardize, stream_labs,
    validate_directory, _csv_count, _sha256,
)

VERSION = "mimic-renal-measurement-extension-1.0"
ITEMS_OF_INTEREST = {"50852", "50854", "51631"}
BP_SOURCE_PATHS = ("icu/chartevents.csv.gz", "icu/d_items.csv.gz", "hosp/omr.csv.gz")


def _write_rows(path: Path, fields: list[str], rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _load_selected(processed: Path):
    patients = list(csv.DictReader((processed / "patients.csv").open("r", encoding="utf-8", newline="")))
    manifest = list(csv.DictReader((processed / "cohort_manifest.csv").open("r", encoding="utf-8", newline="")))
    if len(patients) != 1000:
        raise ValueError(f"Expected existing 1,000-patient cohort; found {len(patients)}. Refusing to select or replace patients.")
    subjects = {row["source_subject_id"] for row in patients}
    if len(subjects) != len(patients) or subjects != {row["source_subject_id"] for row in manifest}:
        raise ValueError("Patient/manifest source subject mapping is inconsistent.")
    for row in patients:
        if row["internal_patient_id"] != f"mimiciv31:{row['source_subject_id']}":
            raise ValueError(f"Unexpected established patient mapping for subject {row['source_subject_id']}.")
    return patients, manifest, subjects


def _map_items(raw: Path):
    headers, entries = read_dict_csv(raw / "d_labitems.csv")
    if not {"itemid", "label", "fluid", "category"}.issubset(headers):
        raise ValueError("d_labitems.csv lacks required dictionary columns.")
    by_id = {row["itemid"]: row for row in entries if row.get("itemid") in ITEMS_OF_INTEREST}
    target = by_id.get("50852")
    if not target or " ".join(target["label"].lower().split()) != "% hemoglobin a1c" or target["fluid"].lower() != "blood" or target["category"].lower() != "chemistry":
        raise ValueError("Item 50852 did not match the audited exact Blood/Chemistry % Hemoglobin A1c dictionary definition.")
    return by_id


def extend(raw: Path = DEFAULT_RAW, processed: Path = DEFAULT_OUTPUT, publish: bool = False) -> dict:
    headers = input_headers(raw)
    patients, manifest, subjects = _load_selected(processed)
    dictionary = _map_items(raw)
    missing_bp_paths = [p for p in BP_SOURCE_PATHS if not (raw / p).is_file()]
    if len(missing_bp_paths) != len(BP_SOURCE_PATHS):
        raise RuntimeError("At least one expected SBP source file is present; inspect its schema and item dictionary before continuing this HbA1c-only extractor.")

    # Keep staging under the repository workspace (same volume for atomic publish).
    # Some Windows sync folders deny child-file writes under data/processed.
    stage_parent = Path(__file__).resolve().parents[1]
    stage = stage_parent / f".{processed.name}.hba1c-stage-{uuid.uuid4().hex}"
    stage.mkdir()
    try:
        # Copy processed inputs and retain every existing row byte-for-byte at the CSV level.
        shutil.copytree(processed, stage, dirs_exist_ok=True, copy_function=shutil.copyfile)
        old_rows = _csv_count(processed / "renal_observations.csv")
        old_ids: set[str] = set()
        per_patient = Counter()
        valid_existing_counts = Counter()
        existing_hba_by_id = {}
        existing_hba_counts = Counter()
        with (processed / "renal_observations.csv").open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row["source_observation_id"]:
                    old_ids.add(row["source_observation_id"])
                per_patient[row["source_subject_id"]] += 1
                if row["canonical_measurement"] == "hba1c":
                    existing_hba_by_id[row["source_observation_id"]] = row
                    existing_hba_counts[row["source_subject_id"]] += 1
                if row["standardized_value"] and row["charttime"] and parse_timestamp(row["charttime"]):
                    valid_existing_counts[(row["source_subject_id"], row["canonical_measurement"])] += 1

        audit_scan = Counter()
        units = Counter()
        finite_values = []
        valid_rows = []
        quarantine = []
        source_rows = Counter()
        stamps = []
        seen_ids: set[str] = set()
        full_item_rows = Counter()
        full_finite_values = Counter()
        full_valid_values = Counter()
        full_subjects = {item_id: set() for item_id in ITEMS_OF_INTEREST}
        full_valid_subjects = {item_id: set() for item_id in ITEMS_OF_INTEREST}
        full_units = Counter()
        full_time_min = {}
        full_time_max = {}
        already_present = 0
        for row in stream_labs(raw / "labevents.csv", audit_scan, ITEMS_OF_INTEREST):
            item_id = row.get("itemid", "")
            subject_id = row.get("subject_id", "")
            full_item_rows[item_id] += 1
            full_subjects[item_id].add(subject_id)
            full_units[(item_id, row.get("valueuom", ""))] += 1
            full_value = parse_numeric(row.get("valuenum"))
            full_stamp = parse_timestamp(row.get("charttime"))
            if full_value is not None:
                full_finite_values[item_id] += 1
            if item_id == "50852":
                full_normalized, _, _ = standardize("hba1c", full_value, row.get("valueuom"))
                if full_normalized is not None and full_stamp is not None:
                    full_valid_values[item_id] += 1
                    full_valid_subjects[item_id].add(subject_id)
                    full_time_min[item_id] = min(full_time_min.get(item_id, full_stamp), full_stamp)
                    full_time_max[item_id] = max(full_time_max.get(item_id, full_stamp), full_stamp)
            if subject_id not in subjects:
                continue
            source_rows[item_id] += 1
            units[(item_id, row.get("valueuom", ""))] += 1
            value = parse_numeric(row.get("valuenum"))
            stamp = parse_timestamp(row.get("charttime"))
            source_id = (row.get("labevent_id") or "").strip()
            reason = ""
            if item_id == "50852":
                converted, normalized_unit, rule = standardize("hba1c", value, row.get("valueuom"))
                if not source_id:
                    reason = "missing_source_observation_id"
                elif value is None:
                    reason = "missing_or_nonfinite_numeric_value"
                elif stamp is None:
                    reason = "missing_or_invalid_or_timezone_offset_charttime"
                elif converted is None:
                    reason = rule
                elif source_id in existing_hba_by_id:
                    old = existing_hba_by_id[source_id]
                    same = (old["source_subject_id"] == row["subject_id"] and old["mimic_item_id"] == item_id
                        and old["canonical_measurement"] == "hba1c" and old["original_value"] == row.get("value", "")
                        and parse_numeric(old["original_numeric_value"]) == value and old["original_unit"] == row.get("valueuom", "")
                        and old["charttime"] == row.get("charttime", "") and parse_numeric(old["standardized_value"]) == converted
                        and old["standardized_unit"] == normalized_unit)
                    if same:
                        already_present += 1
                        finite_values.append(value)
                        stamps.append(stamp)
                        continue
                    reason = "conflicting_existing_source_observation_id"
                elif source_id in old_ids or source_id in seen_ids:
                    reason = "duplicate_source_observation_id"
                if reason:
                    quarantine.append({"source_subject_id": row.get("subject_id", ""), "source_observation_id": source_id,
                        "mimic_item_id": item_id, "original_lab_label": dictionary[item_id]["label"], "original_value": row.get("value", ""),
                        "original_numeric_value": row.get("valuenum", ""), "original_unit": row.get("valueuom", ""),
                        "charttime": row.get("charttime", ""), "source_table": "labevents", "reason": reason})
                    continue
                seen_ids.add(source_id)
                finite_values.append(value)
                stamps.append(stamp)
                valid_rows.append({"internal_patient_id": f"mimiciv31:{row['subject_id']}", "source_subject_id": row["subject_id"],
                    "source_observation_id": source_id, "mimic_item_id": item_id, "original_lab_label": dictionary[item_id]["label"],
                    "canonical_measurement": "hba1c", "original_value": row.get("value", ""), "original_numeric_value": value,
                    "original_unit": row.get("valueuom", ""), "standardized_value": converted, "standardized_unit": normalized_unit,
                    "charttime": row.get("charttime", ""), "charttime_timezone": "unspecified (MIMIC source timestamp has no zone)",
                    "hadm_id": row.get("hadm_id", ""), "admission_time": "", "discharge_time": "", "source_table": "labevents",
                    "provenance": f"MIMIC-IV v3.1; d_labitems.itemid={item_id}; HbA1c identity percent; charttime preserved as supplied",
                    "validation_flags": ""})
            else:
                # Unsupported variants are retained in a quarantine report, not silently mapped to HbA1c.
                quarantine.append({"source_subject_id": row.get("subject_id", ""), "source_observation_id": source_id,
                    "mimic_item_id": item_id, "original_lab_label": dictionary[item_id]["label"], "original_value": row.get("value", ""),
                    "original_numeric_value": row.get("valuenum", ""), "original_unit": row.get("valueuom", ""),
                    "charttime": row.get("charttime", ""), "source_table": "labevents",
                    "reason": "unsupported HbA1c assay variant; not equivalent to item 50852"})

        if not valid_rows and not already_present:
            raise RuntimeError("No valid item 50852 observations were extracted; staged cohort will not be published.")
        if old_ids.intersection(seen_ids) or len(seen_ids) != len(valid_rows):
            raise ValueError("New HbA1c source observation IDs are not unique relative to existing source rows.")

        obs_path = stage / "renal_observations.csv"
        with obs_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=OBSERVATION_COLUMNS, extrasaction="ignore")
            writer.writerows(valid_rows)

        new_by_subject = Counter(row["source_subject_id"] for row in valid_rows)
        valid_by_subject = Counter(existing_hba_counts)
        valid_by_subject.update(new_by_subject)
        span_by_subject = {}
        for row in valid_rows:
            span_by_subject.setdefault(row["source_subject_id"], []).append(parse_timestamp(row["charttime"]))
        patient_map = {row["source_subject_id"]: row for row in patients}
        manifest_map = {row["source_subject_id"]: row for row in manifest}
        for subject, count in new_by_subject.items():
            p = patient_map[subject]
            m = manifest_map[subject]
            p["selected_renal_observation_count"] = str(int(p["selected_renal_observation_count"]) + count)
            m["observation_count_by_measurement"] = json.dumps({**json.loads(m["observation_count_by_measurement"] or "{}"), "hba1c": count}, sort_keys=True)
            new_first = min(span_by_subject[subject]).isoformat(sep=" ")
            new_last = max(span_by_subject[subject]).isoformat(sep=" ")
            firsts = [parse_timestamp(p["earliest_observation_timestamp"]), parse_timestamp(new_first)]
            lasts = [parse_timestamp(p["latest_observation_timestamp"]), parse_timestamp(new_last)]
            first = min(t for t in firsts if t is not None)
            last = max(t for t in lasts if t is not None)
            p["earliest_observation_timestamp"] = m["earliest_observation_timestamp"] = first.isoformat(sep=" ")
            p["latest_observation_timestamp"] = m["latest_observation_timestamp"] = last.isoformat(sep=" ")
            m["temporal_coverage_days"] = str(round((last - first).total_seconds() / 86400, 4))
        for subject, p in patient_map.items():
            m = manifest_map[subject]
            counts = json.loads(m["observation_count_by_measurement"] or "{}")
            if subject not in valid_by_subject:
                counts.pop("hba1c", None)
                m["observation_count_by_measurement"] = json.dumps(counts, sort_keys=True)
            m["missing_measurement_types"] = ";".join(sorted((set(m["missing_measurement_types"].split(";")) - {""}) | ({"hba1c"} if not valid_by_subject[subject] else set()) | {"systolic_bp"}))
        _write_rows(stage / "patients.csv", PATIENT_COLUMNS, [patient_map[k] for k in sorted(patient_map, key=int)])
        _write_rows(stage / "cohort_manifest.csv", MANIFEST_COLUMNS, [manifest_map[k] for k in sorted(manifest_map, key=int)])

        # Extend the existing dictionary mapping with the audited variants and source counts.
        map_path = stage / "lab_item_mapping.csv"
        with map_path.open("r", encoding="utf-8", newline="") as handle:
            mappings = list(csv.DictReader(handle))
            mapping_fields = list(mappings[0]) if mappings else ["mimic_item_id", "original_label", "fluid", "category", "canonical_measurement", "accepted_original_units", "validated_conversion_rule", "included", "exclusion_reason", "dictionary_mapping_evidence", "raw_event_count"]
        existing_items = {row["mimic_item_id"] for row in mappings}
        for item_id in sorted(ITEMS_OF_INTEREST, key=int):
            item = dictionary.get(item_id)
            if not item or item_id in existing_items:
                continue
            include = item_id == "50852"
            mappings.append({"mimic_item_id": item_id, "original_label": item["label"], "fluid": item["fluid"], "category": item["category"],
                "canonical_measurement": "hba1c" if include else "", "accepted_original_units": "%" if include and units[(item_id, "%")] else "",
                "validated_conversion_rule": "identity: explicitly percent-labeled HbA1c" if include else "",
                "included": str(include).lower(), "exclusion_reason": "" if include else "Unsupported assay variant; not equivalent to explicit percent HbA1c item 50852",
                "dictionary_mapping_evidence": "Exact Blood/Chemistry % Hemoglobin A1c label" if include else "A1c-related dictionary item; unsupported assay definition",
                "raw_event_count": source_rows[item_id]})
        _write_rows(map_path, mapping_fields, mappings)

        quarantine_fields = ["source_subject_id", "source_observation_id", "mimic_item_id", "original_lab_label", "original_value", "original_numeric_value", "original_unit", "charttime", "source_table", "reason"]
        _write_rows(stage / "hba1c_quarantine.csv", quarantine_fields, quarantine)

        audit_path = stage / "cohort_audit.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        previous_measure_counts = audit["observations"]["counts_per_measurement"]
        previous_measure_counts["hba1c"] = len(valid_rows)
        final_rows = old_rows + len(valid_rows)
        original_observation_count = audit.get("measurement_extension", {}).get("original_observation_count", old_rows)
        total_hba1c_rows = sum(valid_by_subject.values())
        audit["observations"]["selected_mapped_source_rows"] = final_rows
        audit["observations"]["counts_per_measurement"]["hba1c"] = total_hba1c_rows
        audit["observations"]["unit_distribution_selected"]["hba1c|%"] = total_hba1c_rows
        audit["observations"]["validation_flag_counts_selected_rows"]["hba1c_quarantined"] = len(quarantine)
        audit["limitations"] = list(audit["limitations"]) + [
            "This extension used only the exact Blood/Chemistry item 50852 (% Hemoglobin A1c), with identity percent units. Items 50854 (Absolute A1c) and 51631 (Glycated Hemoglobin) were not treated as equivalent.",
            "Systolic blood pressure was not extractable: ICU chartevents.csv.gz, ICU d_items.csv.gz, and hospital omr.csv.gz are absent from the local raw directory. No MAP or diastolic value was substituted.",
        ]
        audit["measurement_extension"] = {
            "version": VERSION, "patient_selection_changed": False, "existing_patient_ids_preserved": True,
            "existing_observation_ids_preserved": True, "synthetic_measurements_generated": 0,
            "original_patient_count": len(patients), "final_patient_count": len(patients),
            "original_observation_count": original_observation_count, "new_hba1c_observation_count": total_hba1c_rows,
            "new_systolic_bp_observation_count": 0, "final_observation_count": final_rows,
            "hba1c_distinct_selected_patients": len(valid_by_subject),
            "systolic_bp_distinct_selected_patients": 0,
            "patients_with_hba1c_only": sum(1 for s in subjects if valid_by_subject[s] and not valid_existing_counts[(s, "systolic_bp")]),
            "patients_with_hba1c_and_sbp": 0, "patients_with_neither": len(subjects) - len(valid_by_subject),
            "hba1c_items": {"50852": {"label": dictionary["50852"]["label"], "unit_distribution": {u or "<blank>": n for (i, u), n in units.items() if i == "50852"}, "accepted_unit": "%", "conversion": "identity"},
                "50854": {"label": dictionary.get("50854", {}).get("label"), "unit_distribution": {u or "<blank>": n for (i, u), n in units.items() if i == "50854"}, "included": False},
                "51631": {"label": dictionary.get("51631", {}).get("label"), "unit_distribution": {u or "<blank>": n for (i, u), n in units.items() if i == "51631"}, "included": False}},
            "valid_hba1c_value_min": min(finite_values), "valid_hba1c_value_max": max(finite_values),
            "hba1c_timestamp_min": min(stamps).isoformat(sep=" "), "hba1c_timestamp_max": max(stamps).isoformat(sep=" "),
            "quarantined_rows": len(quarantine), "quarantine_reason_counts": dict(Counter(r["reason"] for r in quarantine)),
            "duplicate_new_source_ids": 0, "missing_sbp_source_files": missing_bp_paths,
            "raw_files_used": [str(raw / "labevents.csv"), str(raw / "d_labitems.csv")],
            "raw_headers": {"labevents.csv": headers["labevents.csv"], "d_labitems.csv": headers["d_labitems.csv"]},
            "raw_candidate_item_row_counts_selected_subjects": dict(source_rows),
            "full_source_item_audit": {
                item_id: {"dictionary_label": dictionary.get(item_id, {}).get("label"), "raw_rows": full_item_rows[item_id],
                    "finite_numeric_rows": full_finite_values[item_id], "valid_timestamped_standardizable_rows": full_valid_values[item_id],
                    "distinct_subjects": len(full_subjects[item_id]), "distinct_subjects_with_valid_rows": len(full_valid_subjects[item_id]),
                    "unit_distribution": {unit or "<blank>": count for (iid, unit), count in full_units.items() if iid == item_id},
                    "valid_timestamp_min": full_time_min[item_id].isoformat(sep=" ") if item_id in full_time_min else None,
                    "valid_timestamp_max": full_time_max[item_id].isoformat(sep=" ") if item_id in full_time_max else None}
                for item_id in sorted(ITEMS_OF_INTEREST, key=int)
            },
            "idempotency_key": "MIMIC labevent_id; existing IDs are checked and existing rows are never rewritten",
            "timestamp_policy": "source charttime text preserved; timezone unspecified; no timestamp shift",
        }
        audit["subject_counts"]["selected_subjects"] = len(patients)
        outputs = list(audit.get("output_files", {}))
        for name in ["patients.csv", "renal_observations.csv", "cohort_manifest.csv", "lab_item_mapping.csv", "hba1c_quarantine.csv"]:
            path = stage / name
            audit.setdefault("output_files", {})[name] = {"rows": _csv_count(path), "size_bytes": path.stat().st_size, "sha256": _sha256(path)}
        audit["output_files"]["cohort_audit.json"] = {"rows": 1, "size_bytes": 0, "sha256": "not_self-hashed"}
        for _ in range(4):
            audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")
            size = audit_path.stat().st_size
            audit["output_files"]["cohort_audit.json"]["size_bytes"] = size
        audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")
        validate_directory(stage)
        result = {"mode": "publish" if publish else "dry_run_no_publish", "patients": len(patients), "original_observations": original_observation_count,
            "new_hba1c_observations": total_hba1c_rows, "new_hba1c_rows_added_this_run": len(valid_rows), "already_present_hba1c_rows": already_present,
            "new_systolic_bp_observations": 0,
            "final_observations": final_rows, "selected_patients_with_hba1c": len(valid_by_subject),
            "selected_patients_with_sbp": 0, "selected_patients_with_both": 0, "selected_patients_with_neither": len(subjects) - len(valid_by_subject),
            "quarantined_rows": len(quarantine), "quarantine_reason_counts": dict(Counter(r["reason"] for r in quarantine)),
            "hba1c_timestamp_range": [min(stamps).isoformat(sep=" "), max(stamps).isoformat(sep=" ")],
            "hba1c_percent_value_range": [min(finite_values), max(finite_values)], "missing_sbp_source_files": missing_bp_paths,
            "processed_validation": {"valid": True, "patient_ids_preserved": True, "old_source_observation_ids_preserved": True,
                "new_source_ids_unique": True, "outside_cohort_rows": 0, "synthetic_rows": 0}}
        if publish:
            safe_atomic_publish(stage, processed)
        return result
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--publish", action="store_true", help="Publish validated processed CSV extension; never writes PostgreSQL")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(extend(args.raw_dir, args.processed_dir, args.publish), indent=2, sort_keys=True))
        if not args.publish:
            print("Preview only: processed cohort and PostgreSQL were not modified. Use --publish to atomically publish the validated processed extension.")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

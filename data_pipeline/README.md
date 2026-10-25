# Processed MIMIC-IV renal cohort

This pipeline reads the four local MIMIC-IV v3.1 CSVs and creates a reproducible, curated cohort for research use. It does not use synthetic records and does not train or call an ML model. `labevents.csv` is read twice as an Arrow streaming reader with 8 MiB blocks and item/patient projection; the full 17 GB table is never loaded into pandas or memory at once.

The pipeline was run against the supplied `data/raw` files and produced **1,000 selected subjects** from **207,716 eligible** subjects and **457,533 mapped renal observation rows**. The cohort is selected by supported blood creatinine history, then ranked by temporal coverage, observation count, and a stable SHA-256 subject-ID tie-break. This favors long, dense records and is not a representative sample of MIMIC or the general population.

## Inputs, cohort rule, and measurements

The observed input headers are stored in `cohort_audit.json`. The pipeline checks required columns before reading. Item mappings are based on the local `d_labitems.csv`; exact label, fluid, and category rules are implemented in `mimic_renal_cohort.py`. Explicit blood creatinine/GFR/BUN, blood chemistry potassium/bicarbonate, and explicit urine ACR/albumin/creatinine concepts are selected. Similar labels in ascites, pleural, CSF, other body fluids, whole blood gas, or ambiguous assays are excluded with reasons in `lab_item_mapping.csv`.

Eligibility requires at least two finite, in-range blood creatinine observations that can be converted to mg/dL and whose charttimes span at least one day. The default target is 1,000 but selection returns fewer if fewer qualify. No patient is selected by row order. The selected cohort includes irregular dates and carries every matching renal source row for selected subjects, including rows with missing numeric values or units. Such rows remain in the processed data with quality flags and are skipped by the database importer if they cannot populate a valid typed observation.

Standardized values are only populated for explicit recognized unit rules. The pipeline converts serum creatinine µmol/L to mg/dL; ACR mg/mmol to mg/g; BUN mmol/L to mg/dL; potassium/bicarbonate mEq/L to mmol/L; urine albumin mg/L to mg/dL; and urine creatinine mmol/L to mg/dL. Unknown units remain available with their original value and receive no standardized value. It does not derive eGFR or ACR from other labs.

Research labels are cautious candidates, not diagnoses:

- `acute_creatinine_change_candidate`: a source creatinine rise ≥0.3 mg/dL within 48 hours or ≥1.5× a prior observation within 7 days. No urine output or clinical context is available, so this is not an AKI diagnosis.
- `persistent_renal_measurement_abnormality_review_candidate`: explicitly recorded standardized eGFR <60 or ACR ≥30 mg/g at observations ≥90 days apart. This is not a CKD diagnosis and does not account for all clinical evidence or exclusions.
- `repeated_observation_comparison_group`: ≥3 valid creatinine measurements spanning ≥90 days without the prior criteria. This does not mean healthy or CKD-free.
- `insufficient_evidence_or_data_quality`: the selected record lacks the repeated/temporal evidence above. Group sizes are not forced.

MIMIC dates are deidentified and shifted; `charttime` in the provided table has no timezone. The exact source text is retained. The importer uses UTC only as a database storage convention without shifting the wall-clock value and records that the source timezone is unspecified. `anchor_age` is the dataset's anchor-year age; 91 represents top-coded age over 89 and is not an exact age. The pipeline does not calculate age at an observation date.

The provided files omit diagnosis-code tables, ICU `chartevents`, urine output, medications, and wider clinical context. These are hospital records from one center and do not represent the general population. Follow the MIMIC-IV data use agreement and do not redistribute the generated identifiable-by-source-ID cohort outside approved access. Required attribution: Johnson AE, Bulgarelli L, Shen L, et al. *MIMIC-IV, a freely accessible electronic health record dataset*. Scientific Data. 2023;10(1):1.

## Windows PowerShell commands

Run from the repository root. Install the streaming dependency in the same environment used for the commands:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r data_pipeline/requirements.txt
```

1. Inspect required headers and actual local item mappings (no full lab scan):

```powershell
python data_pipeline/mimic_renal_cohort.py --raw-dir data/raw inspect
```

2. Build the cohort locally. `dry-run` means no PostgreSQL changes; it still builds, validates, and publishes processed files:

```powershell
python data_pipeline/mimic_renal_cohort.py --raw-dir data/raw --output-dir data/processed/mimic_renal_cohort dry-run --target-count 1000 --minimum-creatinine-span-days 1
```

The command writes into a staging directory and publishes only after all validations pass. If a prior processed directory exists, it is retained as a timestamped `.previous-*` backup. If scanning or validation fails, the old published directory remains in place.

3. Review cohort composition and audit:

```powershell
python data_pipeline/mimic_renal_cohort.py --output-dir data/processed/mimic_renal_cohort report
Get-Content data/processed/mimic_renal_cohort/cohort_audit.json
Import-Csv data/processed/mimic_renal_cohort/cohort_manifest.csv | Group-Object research_group | Select-Object Name,Count
```

4. Validate processed schema, joins, unit flags, observation counts, unique source IDs, and hashes:

```powershell
python data_pipeline/mimic_renal_cohort.py --output-dir data/processed/mimic_renal_cohort validate
```

5. Rebuild from the original raw files by rerunning the same `dry-run` command in step 2. Selection, ID generation, and ordering are deterministic for the same files and options.

## Separate PostgreSQL import

The existing SQLAlchemy design is reused. Migration `0002_mimic_provenance` adds nullable source identity and observation provenance fields; `0003_timestamp_provenance_length` extends the timezone provenance field to hold its complete description. Both are additive. The importer also requires migration `0004_date_precision_observations` before a current import.

Review the additive schema migration and apply it when ready:

```powershell
alembic upgrade head
```

Import preview reads only processed CSVs and checks source identity conflicts; it performs no database writes:

```powershell
python -m data_pipeline.import_mimic_renal_cohort --processed-dir data/processed/mimic_renal_cohort
```

Only after reviewing the cohort and preview, an operator explicitly approved to import may run:

```powershell
python -m data_pipeline.import_mimic_renal_cohort --processed-dir data/processed/mimic_renal_cohort --execute
```

Existing rows that exactly match their MIMIC source identity and content are skipped. Conflicting patient codes or source observation IDs are reported and never overwritten. New rows are flushed in batches within a single transaction; state snapshots and update-history rows for patients receiving new observations are recomputed in that transaction. `updated` remains zero by policy. Rows with no valid standardized numeric value or timestamp are retained in CSV but skipped by import with counts in the report. Synthetic seeding is not called.

For a database containing only known development seed records, the replacement cleanup has its own preview and explicit execute flag. It requires the verified pre-import backup, checks its checksum/archive, and refuses to delete unless all `SYNTH-*` patient metadata and observation seed keys match the implementation exactly:

```powershell
python -m data_pipeline.cleanup_synthetic_renal_twin
python -m data_pipeline.cleanup_synthetic_renal_twin --execute
```

The cleanup deletes only those patients and their dependent scenarios, states, update histories, and observations in a transaction. It preserves unrelated rows and migration history. A verified custom-format backup should be made before executing cleanup; the cleanup command checks the configured backup path and expected checksum.

Verify database counts in pgAdmin or `psql` connected to the database configured in `api/.env`:

```sql
SELECT source_system, count(*) FROM renal_patients WHERE source_system = 'MIMIC-IV-v3.1' GROUP BY source_system;
SELECT source_system, count(*) FROM renal_observations WHERE source_system = 'MIMIC-IV-v3.1' GROUP BY source_system;
SELECT reason, count(*) FROM renal_twin_updates WHERE reason = 'mimic_iv_v3_1_cohort_import' GROUP BY reason;
```

The import recomputes twin state for patients with newly inserted observations. For a reviewed individual patient later, use the existing API endpoint:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/renal-twin/patients/<internal-database-patient-id>/update"
```

Re-running the cohort builder republishes the same processed source for the same inputs. Re-running the import preview is read-only. Re-running the explicit import skips identical source records and does not replace conflicting or unrelated records.

## HbA1c and systolic blood pressure extension

The targeted extension script uses the existing 1,000-patient manifest and matches only by source `subject_id`. It does not call the cohort selector. It streams `data/raw/labevents.csv` and reads `data/raw/d_labitems.csv`; the accepted HbA1c dictionary entry is item **50852**, `% Hemoglobin A1c` (Blood/Chemistry), with identity `%` normalization. Items 50854 (`Absolute A1c`) and 51631 (`Glycated Hemoglobin`) are retained in the quarantine/mapping audit as unsupported variants, not silently converted. The source chart time and `labevent_id` remain unchanged.

The earlier HbA1c-only audit did not identify an ICU chart-events file or the compressed `hosp/omr.csv.gz` path. A separate read-only audit later found the local root-level `data/raw/omr.csv`; its date-level blood-pressure extraction is documented below. No values are substituted from another pressure type. The NephroQ API requires valid, fresh measurements aligned to the selected eGFR index date before it runs.

The current source audit found 295,978 rows for item 50852 in the full lab file; all report `%`, 295,829 have finite numeric values and valid timestamps, covering 96,116 source subjects. Of the fixed selected cohort, 11,732 valid observations cover 924 patients. Item 50854 has 547 full-file rows with blank units and no finite numeric values (71 rows across 67 selected subjects); item 51631 has no lab-event rows. These alternate items are quarantined as unsupported. The processed cohort has 0/1,000 patients with SBP and 0 with both added inputs; 76 have neither HbA1c nor SBP.

Preview the staged extension without changing the published cohort or PostgreSQL:

```powershell
python -m data_pipeline.extend_mimic_renal_measurements
```

After reviewing its validation output, publish the validated processed CSV extension (this still does not write to PostgreSQL):

```powershell
python -m data_pipeline.extend_mimic_renal_measurements --publish
python data_pipeline/mimic_renal_cohort.py --output-dir data/processed/mimic_renal_cohort validate
```

Then inspect the importer preview. The importer reads only processed CSV files and remains read-only unless `--execute` is explicitly supplied:

```powershell
python -m data_pipeline.import_mimic_renal_cohort --processed-dir data/processed/mimic_renal_cohort
```

Do not add `--execute` until the preview, database backup, and insert/conflict counts have been reviewed. The existing generic observation table already stores the measurement type, unit, event time, source item, and source identifiers, so this extension requires no Alembic migration.

## Date-level OMR blood pressure extraction

`data/raw/omr.csv` is a 320,875,376-byte MIMIC-IV v3.1 source with columns `subject_id,chartdate,seq_num,result_name,result_value`. The extractor streams it in 8 MiB chunks and joins only against the existing `patients.csv` source-subject mapping. It never changes the selected cohort or the original `renal_observations.csv`.

Run the extraction and generate `observations.csv`, `quarantine.csv`, `audit.json`, and `report.md` in a separate ignored directory:

```powershell
python -m data_pipeline.extract_mimic_omr_blood_pressure
```

Inspect the audit and concise report:

```powershell
Get-Content data/processed/mimic_renal_omr_bp/report.md
Get-Content data/processed/mimic_renal_omr_bp/audit.json
python -m data_pipeline.extract_mimic_omr_blood_pressure --validate-only
```

The full source contained 7,753,027 rows and 13 distinct `result_name` values. The six supported BP labels were `Blood Pressure`, `Blood Pressure Lying`, `Blood Pressure Sitting`, `Blood Pressure Standing`, `Blood Pressure Standing (1 min)`, and `Blood Pressure Standing (3 mins)`. In the fixed 1,000-patient cohort, 96,518 source readings matched; 96,450 valid pairs cover 987 patients and 68 implausible pairs were quarantined. The other 13 cohort patients had no supported OMR BP row. No selected rows had missing, malformed, nonnumeric, ambiguous, or invalid-date values; the audit reports those zero counts explicitly. There were no duplicate `(subject_id, chartdate, seq_num, result_name, result_value)` signatures. All source rows are retained separately, including repeated same-day readings.

MIMIC-IV documents `chartdate` as the observation date and `seq_num` as the order for same-day results; neither provides a measurement clock time. The output keeps `chartdate` and `seq_num` and deliberately omits a fabricated `observed_at`. OMR has no unit column; `mmHg` is assigned from the documented blood-pressure result semantics, not guessed from numeric magnitude. Broad validation bounds are SBP 30–300 mmHg and DBP 10–200 mmHg, with SBP > DBP; these are data-quality checks, not diagnostic criteria. See the [MIMIC OMR table documentation](https://mimic.mit.edu/docs/iv/modules/hosp/omr.html).

The code now supports a first-class date-precision representation, but **database import remains blocked until migration `0004_date_precision_observations` is separately approved and applied**. `observed_at` is nullable for `date_only` rows; `observed_date` and `source_sequence_number` hold OMR's date and sequence. Existing timestamped rows keep their original `observed_at` and receive a UTC calendar-date field. API ordering groups by date, with exact-time order within timestamped rows and source sequence within OMR rows. Mixed exact-time and date-only rows on one date are explicitly marked ambiguous; current-state selection does not choose between them. Date-only intervals do not produce elapsed-time rates. No migration, PostgreSQL write, OMR import, or state recomputation was performed.

```powershell
python -m data_pipeline.preview_mimic_omr_bp_import
```

The extraction-specific preview checks the current schema and source identity collisions. After migration `0004`, use the OMR-only importer dry run documented at the end of this README; it reads processed files only and performs no writes.

Focused extractor tests:

```powershell
python -m pytest -q tests/data_pipeline/test_mimic_omr_blood_pressure.py
```

## Tests

```powershell
python -m pytest -q tests/data_pipeline
```

The tests cover exact item mapping, units, timestamp rules, cohort eligibility/ranking, candidate labels, stable internal identifiers, exact-repeat versus conflict import policy, transaction rollback, and persisted state recomputation. Unit tests use in-memory SQLite and do not modify the configured production database.

## Date-aware observation migration and OMR import

Migration `0004_date_precision_observations` adds `timestamp_precision`, `observed_date`, and `source_sequence_number`; backfills the UTC calendar date for existing timestamped observations; and makes `observed_at` nullable while enforcing the exact-time/date-only relationship. Its downgrade refuses to proceed while date-only rows exist. The migration has not been applied.

After separately approving the migration, run:

```powershell
alembic upgrade head
alembic current
```

Then preview the processed OMR import:

```powershell
python -m data_pipeline.import_mimic_renal_cohort `
  --omr-bp-file data/processed/mimic_renal_omr_bp/observations.csv `
  --omr-cohort-file data/processed/mimic_renal_cohort/patients.csv
```

Review patient identities, expected component row counts, duplicates/conflicts, and a database backup before separately approving writes with:

```powershell
python -m data_pipeline.import_mimic_renal_cohort `
  --omr-bp-file data/processed/mimic_renal_omr_bp/observations.csv `
  --omr-cohort-file data/processed/mimic_renal_cohort/patients.csv `
  --execute
```

The importer reads processed files only. No migration or OMR import was run in this task.

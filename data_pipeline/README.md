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

The existing SQLAlchemy design is reused. Migration `0002_mimic_provenance` adds nullable source identity and observation provenance fields; `0003_timestamp_provenance_length` extends the timezone provenance field to hold its complete description. Both are additive. The importer checks that the configured DB is exactly `renal_twin_db` and that migration `0003_timestamp_provenance_length` is current.

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

## Tests

```powershell
python -m pytest -q tests/data_pipeline
```

The tests cover exact item mapping, units, timestamp rules, cohort eligibility/ranking, candidate labels, stable internal identifiers, exact-repeat versus conflict import policy, transaction rollback, and persisted state recomputation. Unit tests use in-memory SQLite and do not modify the configured production database.

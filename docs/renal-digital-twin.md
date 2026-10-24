# Renal Digital Twin local setup

## Architecture and data flow

The Next.js `/renal-digital-twin` page calls the FastAPI `/api/renal-twin` routes through the existing `web/src/lib/api.ts` client. API code stores patient profiles, timestamped observations, current state snapshots, update history, and hypothetical scenarios in PostgreSQL using SQLAlchemy. Existing tabular screening and CT model services remain unchanged and are not inputs to the twin.

The database tables are `renal_patients`, `renal_observations`, `renal_twin_states`, `renal_twin_updates`, and `renal_scenarios`. Observation event time (`observed_at`) is distinct from insertion time (`created_at`). An out-of-order observation is retained and triggers a deterministic recomputation. Snapshot source IDs, warnings, and `renal-twin-1.0` are recorded. Observations are ordered by event time; no interpolation or forward filling is used. Trend changes are descriptive differences between the two most recent observations of that same measurement.

## Requirements and Windows PowerShell setup

Install PostgreSQL 15 or later and ensure its Windows service is running. Create a database and a least-privilege local application user in `psql` or pgAdmin. For example, in `psql` as a database administrator:

```sql
CREATE ROLE renal_app LOGIN PASSWORD 'replace-with-a-local-password';
CREATE DATABASE renal_twin OWNER renal_app;
```

From the repository root in PowerShell:

```powershell
Copy-Item api/.env.example api/.env
notepad api/.env
```

Set `DATABASE_URL` in `api/.env` to `postgresql+psycopg://renal_app:<URL-encoded-password>@localhost:5432/renal_twin`. Keep this file private; `.gitignore` excludes it. Activate the existing virtual environment and install API dependencies:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r api/requirements.txt
python -m api.db_cli check
alembic upgrade head
```

The connectivity command checks PostgreSQL and does not create or reset a database. The migration only creates missing tables and indexes. It does not drop patient data. On an existing database, back it up and inspect the schema before migration.

Start the API and web app in separate PowerShell terminals:

```powershell
uvicorn api.main:app --reload
```

```powershell
Set-Location web
npm run dev
```

The web app uses `http://localhost:8000` by default. To change it, set `NEXT_PUBLIC_API_BASE_URL` in the frontend environment before starting Next.js.

## Synthetic development data

Only run in a local development database:

```powershell
python -m api.db_cli seed-synthetic
```

The seeder is idempotent and creates only `SYNTH-*` patient codes, marked with synthetic metadata and provenance. It includes irregular eGFR observations, an ACR value, a single abnormal eGFR without history, sparse blood pressure data, a span longer than three months, and a historical result inserted after a newer event time. Seeding is disabled when `ENVIRONMENT=production` or `prod`.

Inspect records through the UI or the read-only API (`GET /api/renal-twin/patients` and `GET /api/renal-twin/patients/{id}/observations`). To remove only local seed records, use a local-only SQL transaction. First inspect the exact matching patients and observation counts; then delete only these synthetic profiles (foreign keys cascade to their observations, state, history, and scenarios):

```sql
BEGIN;
SELECT p.id, p.patient_code, count(o.id) AS observations
FROM renal_patients p LEFT JOIN renal_observations o ON o.patient_id = p.id
WHERE p.patient_code LIKE 'SYNTH-%'
GROUP BY p.id, p.patient_code;
DELETE FROM renal_scenarios WHERE patient_id IN (SELECT id FROM renal_patients WHERE patient_code LIKE 'SYNTH-%');
DELETE FROM renal_patients WHERE patient_code LIKE 'SYNTH-%';
SELECT patient_code FROM renal_patients WHERE patient_code LIKE 'SYNTH-%';
-- Verify only intended synthetic records were removed, then:
COMMIT;
-- Use ROLLBACK instead of COMMIT if the inspected rows were not the intended seed profiles.
```

Do not run a broad table reset or delete non-synthetic patients. The application does not expose a patient delete endpoint.

## API endpoints

- `GET/POST /api/renal-twin/patients`
- `GET /api/renal-twin/patients/{patient_id}`
- `GET/POST /api/renal-twin/patients/{patient_id}/observations`
- `GET /api/renal-twin/patients/{patient_id}/state`
- `POST /api/renal-twin/patients/{patient_id}/update`
- `GET /api/renal-twin/patients/{patient_id}/history`
- `GET /api/renal-twin/patients/{patient_id}/analysis?trend_window_days=365` (`0` means all history)
- `GET/POST /api/renal-twin/patients/{patient_id}/scenarios`
- `POST /api/renal-twin/patients/{patient_id}/scenarios/compare`
- `GET /api/renal-twin/scenarios/{scenario_id}`

OpenAPI is available at `http://localhost:8000/docs`. Observation input accepts only documented units: creatinine `mg/dL`, eGFR `mL/min/1.73m2`, ACR `mg/g`, and blood pressure `mmHg`. Timestamps must include a timezone. The optional idempotency key is unique within a patient.

## Observability, trend windows, and timestamps

The observability endpoint validates stored value/unit pairs with the same existing measurement rules, reports valid and invalid counts, latest and prior event times, median elapsed interval, recent and historical window counts, staleness, source provenance, and source timestamp checks. Recent and historical windows are anchored to the latest event time for MIMIC-IV profiles (their event dates are de-identified and can be future-shifted); other profiles use the current UTC time. The default recent window is 30 days and the historical window is the preceding 365 days excluding that recent window. No sampling schedule exists, so the API returns an unknown missingness denominator and does not calculate a missingness percentage.

Descriptive eGFR and creatinine endpoint rates use the first and last valid observation in the selected time window: `(last value - first value) / elapsed days × 365.25`. The default minimum is three observations spanning at least 30 days. These settings are configurable in `api/.env`: `RENAL_OBSERVABILITY_RECENT_DAYS`, `RENAL_OBSERVABILITY_HISTORICAL_DAYS`, `RENAL_OBSERVABILITY_STALE_DAYS`, `RENAL_TREND_MIN_OBSERVATIONS`, and `RENAL_TREND_MIN_SPAN_DAYS`. The UI offers 30/90/365/1825 days or all history. Trend output is descriptive and can be misleading with sparse samples or acute changes. It is not a validated progression rate or diagnosis.

The timeline chart defaults to all history and shows the selected biomarker using its recorded timestamps. A solid line connects observation dots as a visual guide only; it does not indicate measurements between those timestamps. The chart uses the most recent 500 observations loaded by the existing page request; the paginated history table remains unchanged and reports source timestamps, measurement labels, item IDs, and source observation IDs when present. Endpoint-rate cards, aligned eGFR/creatinine panels, the observability panel, and the state evolution/provenance section were removed from the page. The analysis and history endpoints remain available to API clients.

Timestamp inspection confirmed that the MIMIC chart-time text is timezone-unspecified, while the importer stores that wall time using UTC as a deterministic database convention and retains both the source text and timezone provenance. PostgreSQL in this environment returns the stored instant in `Asia/Calcutta`; for example, source `2154-08-09 05:50:00` was returned as `11:20+05:30`. API event timestamps are now normalized to UTC and the page formats dates in UTC, so the displayed time matches the retained source chart clock instead of applying the host/browser timezone. The year remains shifted because MIMIC dates are de-identified; no timestamp was rewritten. This is covered by a UTC-normalization regression test.

Snapshot history is derived from the existing `renal_twin_updates` records. It compares each stored source observation-ID set and descriptive measurement summaries with the preceding stored snapshot, and marks an added observation as late historical data when its `observed_at` precedes the preceding snapshot's latest event time. The first retained snapshot has no comparison. The state evolution/provenance section is hidden in the current UI; snapshots and API records remain stored. No new database table or migration was needed.

Multiple scenario comparisons use the existing scenario table. The comparison endpoint validates two to five distinct user-entered annual rates and stores each scenario separately, with a shared comparison group, label, baseline reference, assumptions, output, and algorithm version. The full group is inserted transactionally. Values use the existing deterministic monthly calculation and are warned when outside the supported eGFR range; outputs are never clamped. Differences are absolute endpoint differences from Scenario A at the same baseline and horizon. Scenario rates are user assumptions, not estimates learned from the patient record.

## Clinical assumptions and limitations

KDIGO adult categories are displayed only for supplied eGFR and ACR values: G1 ≥90, G2 60–89, G3a 45–59, G3b 30–44, G4 15–29, G5 <15 mL/min/1.73 m²; A1 <30, A2 30–300, A3 >300 mg/g. The ACR boundary of 300 is included in A2. Categories describe the entered result and are not CKD diagnoses. G1/G2 alone does not establish CKD. A single abnormal observation cannot establish chronicity. KDIGO defines CKD by abnormalities present for at least three months unless other evidence establishes chronicity; a time span alone is not sufficient proof. The implementation does not calculate eGFR, infer AKI, diagnose CKD, or make treatment suggestions.

The scenario simulator applies `baseline eGFR + assumed annual rate × months / 12`, with a monthly step. The user supplies the assumption; it is not selected as a medically expected trajectory. Out-of-range values are visibly warned. Scenarios are stored separately and never enter the observation table. This is a mathematical illustration, not a validated prediction.

Clinical reference: [KDIGO 2024 CKD guideline](https://kdigo.org/guidelines/ckd-evaluation-and-management/kdigo-2024-ckd-guideline/) and [full guideline PDF](https://kdigo.org/wp-content/uploads/2024/03/KDIGO-2024-CKD-Guideline.pdf).

## Security and troubleshooting

This repository has no authentication or patient-level authorization. CORS is restricted to local development origins, but this does not provide patient access control. Do not use for real patient data or clinical deployment. Database credentials are server-side only. The project logs API exceptions; avoid adding clinical values or credentials to logs.

- **`DATABASE_URL is required`**: copy `api/.env.example` to `api/.env` and set the URL. Run commands from the repository root.
- **Connection refused / port**: start the PostgreSQL Windows service; verify host and port (`5432` by default) and check with `python -m api.db_cli check`.
- **Password authentication failed**: verify role, password, URL-encode reserved password characters, and confirm the role can connect to `renal_twin`.
- **Database does not exist**: create it explicitly; startup and migration do not create a database or reset one.
- **Migration command not found**: activate `.venv` and install `api/requirements.txt`.
- **Missing psycopg / SQLAlchemy**: reinstall API dependencies using the same active Python environment used by Uvicorn.
- **API returns 503 for twin calls**: verify PostgreSQL connectivity and run `alembic upgrade head`.

## Tests

Run the existing and new tests with `python -m pytest -q`. Database integration tests should use a dedicated disposable PostgreSQL database, never a developer's populated database. The pure deterministic state engine tests do not require PostgreSQL. The original image tests may be skipped unless `RUN_IMAGE_TESTS=1`; some repository tests also require writable temporary directories.

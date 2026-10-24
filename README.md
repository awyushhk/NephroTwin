# Renal Risk Assessment

An AI-powered **Kidney Risk Assessment System** that integrates clinical data and CT imaging to deliver a unified, data-driven evaluation of renal health and potential disease risk.

Two complementary prediction modes — a **tabular model** (routine clinical data → CKD
risk probability) and an **image model** (kidney CT slice → imaging diagnosis):

```
Clinical Data ──► models/kidney/tabular   ──► CKD risk (KDIGO) + explanation
CT Slice      ──► models/kidney/image_based ──► Cyst / Normal / Stone / Tumor + Grad-CAM
```

| Module                                                   | Description                                                                                                                                                                                    |
| -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`models/kidney/tabular`](models/kidney/tabular)         | CKD (KDIGO criteria) from 19 clinical features — demographics, blood pressure, basic metabolic panel, diabetes and smoking history — **without** the tests that define CKD. Trained on NHANES. |
| [`models/kidney/image_based`](models/kidney/image_based) | Kidney CT slice classification: **Cyst, Normal, Stone, Tumor**. Grad-CAM overlay shows where the model focused.                                                                                |

Each module has its own README (data, method, results) and the same layout:
`data/`, `notebooks/` (the full analysis), `src/` (importable code), `models/`, `results/`, `images/`,
and for the tabular module `examples/` (a sample patient).

## Repository layout

```
common/        shared code: registry.py (one entry point), prediction.py,
               tabular.py / image.py (the per-module cascades), and
               config/ (where the models live), preprocessing/, utils/, evaluation/
frontend/      app/ (the Streamlit page), components/ (form fields), assets/ (example patient)
models/kidney/ the kidney models: tabular/ and image_based/
triage/        tabular/: the layer-1 symptom router (retained for compatibility)
tests/         pytest smoke tests: common/, kidney/, triage/
```

## Running the models

Every module's `src/predict.py` exposes two functions:

- `predict(x)` → a `Prediction`, for one patient (a dict of the module's raw input
  columns) or one image (a path, bytes, a file-like upload, a PIL image or an array)
- `predict_batch(xs)` → a DataFrame with one row per patient or image

```python
from common.registry import module   # from the repo root

# Tabular: CKD risk from clinical data
result = module("kidney", "tabular").predict(patient)   # patient: dict of raw inputs
result.status, result.label, result.probability, result.positive, result.explanation
result.to_dict(arrays=False)                            # JSON-ready (drops the heatmap arrays)

# Image: CT slice classification
result = module("kidney", "image").predict("ct_slice.png")
result.status, result.label, result.positive
result.explanation["overlay"]                           # Grad-CAM heatmap (bytes)
```

| Field         | Tabular model                                                              | Image model                                                                                  |
| ------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `status`      | `accepted`, or `review` when the anomaly gate withholds an unusual profile | `accepted`; `review` below 75 % confidence; `rejected` when the image is out-of-distribution |
| `label`       | risk band: **Low / Medium / High Risk**                                    | predicted class: **Cyst / Normal / Stone / Tumor**                                           |
| `probability` | calibrated P(CKD)                                                          | 1 − P(Normal)                                                                                |
| `positive`    | probability ≥ the cost-optimal threshold → refer for eGFR + ACR            | predicted class is not Normal                                                                |
| `explanation` | the 5 inputs that moved the probability most vs. a typical patient         | Grad-CAM heatmap and overlay                                                                 |
| `message`     | risk band + next step: _"order kidney tests (eGFR and urine ACR)"_         | finding and confidence, or why rejected                                                      |
| `details`     | threshold, risk bands, model name                                          | confidence, class probabilities, top-3, model name                                           |

When `status` is `rejected` (image OOD gate) or `review` (tabular anomaly gate), no
`label` or `probability` is returned — a clinician is asked to review.

Each module also runs standalone from its folder:

```bash
# Tabular (from models/kidney/tabular/)
python -m src.predict --input examples/patient.json

# Image (from models/kidney/image_based/)
python -m src.predict --image ct_slice.png --heatmap-dir out
```

## Front end

The Next.js interface also includes the `/renal-digital-twin` longitudinal observation and simulation page. See [`docs/renal-digital-twin.md`](docs/renal-digital-twin.md) for PostgreSQL setup, migrations, synthetic data, API routes, and research-use limitations.

[`frontend/app/streamlit_app.py`](frontend/app/streamlit_app.py) provides a unified UI for
both models:

```bash
streamlit run frontend/app/streamlit_app.py      # from the repo root
```

Two tabs:

1. **Clinical Questionnaire (Tabular)** — fill in what you know from the 19-feature
   form (grouped into _About you_, _Measurements_, _Lab results_, _History and lifestyle_).
   The model handles missing values with KNN imputation. Results show CKD risk %, decision
   band, progress bar, and what moved the risk most.
2. **CT Scan Analysis (Image)** — upload one or more kidney CT slice images. Each image
   gets an independent Cyst / Normal / Stone / Tumor result and Grad-CAM overlay; a study
   summary describes accepted-image counts and abstains when results disagree or evidence is sparse.

_Load example patient_ pre-fills the tabular form from
[`frontend/assets/cascade_patient.json`](frontend/assets/cascade_patient.json).
The first image of a session loads the network (~1.5 GB with PyTorch).

### Multi-image CT examination

`POST /api/kidney/image/study` accepts multipart `files` fields (up to 12 images) and the
optional `ensemble=true` field. It returns an `examination_id`, one entry per submitted
file (`image_id`, filename, status, and the existing single-image prediction when produced),
and a descriptive summary. Per-image statuses are `accepted`, `review_required`,
`ood_rejected`, `invalid_file`, or `processing_error`.

The summary counts classes only among `accepted` images. It reports available mean
image-level class scores separately from class counts; neither is a calibrated examination
probability. By default at least two accepted images are required, and any disagreement
between accepted predicted classes sets `study_review_required`; no majority vote is used.
Set `CT_STUDY_MIN_ACCEPTED_IMAGES` in the API environment to change the minimum (default
`2`). Each image is limited to 25 MB, each image is limited to 40 megapixels, and an
examination is limited to 12 images and 100 MB total. The existing `POST /api/kidney/image`
single-image endpoint and model pipeline remain available unchanged. The summary policy is
descriptive, not clinically validated, and is not a study-level diagnosis.

Run the backend and frontend from the repository root in separate terminals:

```powershell
# Terminal 1: activate the project environment and start FastAPI
.\.venv\Scripts\Activate.ps1
uvicorn api.main:app --reload --port 8000

# Terminal 2: start Next.js
cd web
npm run dev
```

The backend still requires the existing image-model dependencies and checkpoint described
above. No new package is required for multi-image analysis.

## Setup

```bash
# Install tabular model dependencies
pip install -r models/kidney/tabular/requirements.txt

# Install image model dependencies
pip install -r models/kidney/image_based/requirements.txt

# Install Streamlit
pip install streamlit
```

- **Python 3.10+** recommended; tested on 3.13.
- The image model runs **Keras 3** on the **PyTorch** backend (default on Windows, since
  TensorFlow has no GPU support on native Windows). Set `KERAS_BACKEND=tensorflow` to use
  TensorFlow instead; Grad-CAM works on both backends.
- The `.keras` checkpoint and the CT image dataset are **not in git** (size). The image
  module's [`README`](models/kidney/image_based/README.md) says where to get them.

## Tests

```bash
python -m pytest tests                         # from the repo root: layout, imports, tabular model, triage
RUN_IMAGE_TESTS=1 python -m pytest tests       # also loads the image network (~1.5 GB)
```

The image tests need the `.keras` checkpoint and `data/test/` images; they skip when those are missing.

## Caveats

- The tabular and image datasets come from **different patients**. There is no dataset where
  the same person has both clinical labs and a CT scan, so each model is evaluated independently.
  Their results are shown **side by side** in the UI and never combined into a single probability.
- Trained on public datasets (NHANES clinical survey, public kidney CT image sets).
  **Research only — not a medical device.** Always consult a licensed physician.

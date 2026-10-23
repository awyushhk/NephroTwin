"""
streamlit_app.py - Kidney Disease (CKD) Risk Prediction System

A kidney-exclusive UI with two prediction modes:
  1. Tabular Risk   - clinical questionnaire -> CKD risk probability
  2. CT Image       - kidney CT slice upload -> image-based finding

Run from the repo root:
    streamlit run frontend/app/streamlit_app.py
"""

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from common import REJECTED, REVIEW
from common.registry import module
from frontend.components import fields

IMAGE_TYPES = ["png", "jpg", "jpeg", "bmp", "tif", "tiff"]
ORGAN = "kidney"

st.set_page_config(
    page_title="Renal Risk Prediction System",
    page_icon="\U0001fad8",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- CSS --------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: linear-gradient(135deg, #0f0c29 0%, #1a1a3e 50%, #0f2027 100%); color: #e8e8f0; }
section[data-testid="stSidebar"] { background: linear-gradient(180deg, #1a1040 0%, #0d1b2a 100%); border-right: 1px solid rgba(139,92,246,0.3); }
section[data-testid="stSidebar"] .stMarkdown, section[data-testid="stSidebar"] p { color: #c4b5fd !important; }
[data-testid="stMetric"] { background: rgba(139,92,246,0.12); border: 1px solid rgba(139,92,246,0.3); border-radius: 12px; padding: 12px 16px; }
[data-testid="stMetricValue"] { color: #a78bfa !important; font-size: 2rem !important; font-weight: 700 !important; }
[data-testid="stMetricLabel"] { color: #c4b5fd !important; }
.stButton > button { background: linear-gradient(135deg, #7c3aed, #4f46e5); color: white; border: none; border-radius: 8px; font-weight: 600; transition: all 0.3s ease; box-shadow: 0 4px 15px rgba(124,58,237,0.4); }
.stButton > button:hover { background: linear-gradient(135deg, #6d28d9, #4338ca); box-shadow: 0 6px 20px rgba(124,58,237,0.6); transform: translateY(-2px); }
[data-testid="stFormSubmitButton"] > button { background: linear-gradient(135deg, #7c3aed, #06b6d4) !important; color: white !important; border: none !important; border-radius: 8px !important; font-weight: 600 !important; font-size: 1rem !important; box-shadow: 0 4px 15px rgba(6,182,212,0.4) !important; }
.stTabs [data-baseweb="tab-list"] { gap: 8px; background: rgba(255,255,255,0.04); border-radius: 12px; padding: 6px; border: 1px solid rgba(139,92,246,0.25); }
.stTabs [data-baseweb="tab"] { background: transparent; border-radius: 8px; color: #a78bfa; font-weight: 500; padding: 8px 20px; }
.stTabs [aria-selected="true"] { background: linear-gradient(135deg, #7c3aed, #4f46e5) !important; color: white !important; }
h1 { color: #e2d9f3 !important; font-weight: 700 !important; }
h2 { color: #c4b5fd !important; font-weight: 600 !important; }
h3 { color: #a78bfa !important; font-weight: 600 !important; }
.stProgress > div > div { background: linear-gradient(90deg, #7c3aed, #06b6d4); border-radius: 4px; }
[data-testid="stDataFrame"] { border: 1px solid rgba(139,92,246,0.25); border-radius: 8px; }
hr { border-color: rgba(139,92,246,0.2) !important; }
.stCaption { color: #9ca3af !important; }
[data-testid="stExpander"] { background: rgba(255,255,255,0.04); border: 1px solid rgba(139,92,246,0.25); border-radius: 12px; }
[data-testid="stFileUploader"] { border: 2px dashed rgba(139,92,246,0.4) !important; border-radius: 12px !important; background: rgba(139,92,246,0.05) !important; }
</style>
""", unsafe_allow_html=True)


# ---- Cached model loaders ---------------------------------------------------

@st.cache_resource
def kidney_info() -> dict:
    """Metadata from both kidney models without loading heavy weights."""
    m = module(ORGAN, "tabular")
    im = module(ORGAN, "image")
    return {
        "disease": m.MODEL.disease,
        "columns": m.MODEL.input_columns,
        "image_desc": im.MODEL.expected_input,
    }


# ---- Form helpers -----------------------------------------------------------

def wkey(key: str) -> str:
    """Widget key bumped with form_version so 'start over' clears values."""
    return f"{st.session_state.get('form_version', 0)}|{key}"


def _default(key: str):
    return st.session_state.get("defaults", {}).get(key)


def _index(key: str, options: list):
    value = _default(key)
    return options.index(value) if value in options else None


def number_input(column: str, key: str):
    name, unit, low, high, step = fields.NUMERIC[column]
    cast = float if isinstance(step, float) else int
    value = _default(key)
    decimals = len(str(step).split(".")[1]) if cast is float else 0
    return st.number_input(
        f"{name} ({unit})", min_value=cast(low), max_value=cast(high),
        step=cast(step), value=None if value is None else cast(value),
        format=f"%.{decimals}f" if decimals else None,
        placeholder="unknown", key=wkey(key),
    )


def choice_input(column: str, key: str, options: list, format_func=str):
    return st.selectbox(
        fields.label(column), options, index=_index(key, options),
        format_func=format_func, placeholder="unknown", key=wkey(key),
    )


def ask(column: str):
    """Render one questionnaire field for the kidney model."""
    key = f"k:{column}"
    if column in fields.ORDINAL:
        labels = fields.ORDINAL[column][1]
        return choice_input(column, key, list(labels), format_func=lambda v: labels[v])
    if column in fields.NUMERIC:
        return number_input(column, key)
    return choice_input(column, key, fields.answers(ORGAN)[column])


# ---- Example patient --------------------------------------------------------

EXAMPLE_PATH = ROOT / "frontend" / "assets" / "cascade_patient.json"


def reset_results():
    for k in ("tabular_result", "image_result", "uploaded_image_bytes"):
        st.session_state.pop(k, None)


def new_form(defaults: dict):
    version = st.session_state.get("form_version", 0) + 1
    for k in [k for k in st.session_state if "|" in k]:
        del st.session_state[k]
    st.session_state.form_version = version
    st.session_state.defaults = defaults


def load_example():
    """Pre-fill from the bundled cascade_patient.json."""
    try:
        payload = json.loads(EXAMPLE_PATH.read_text())
        kidney_answers = payload.get("tabular", {}).get("kidney", {})
        defaults = {f"k:{col}": val for col, val in kidney_answers.items()}
        new_form(defaults)
        reset_results()
    except Exception as e:
        st.error(f"Could not load example: {e}")


def start_over():
    new_form({})
    reset_results()


# ---- Tabular section --------------------------------------------------------

def show_factors(factors: list, value_header: str = "This patient"):
    if not factors:
        st.caption("No single input strongly moved the probability for this patient.")
        return
    table = pd.DataFrame({
        "Input": [fields.label(f["feature"]) for f in factors],
        value_header: [f["value"] for f in factors],
        "Typical": ["n/a" if f["typical"] is None else str(f["typical"]) for f in factors],
        "Effect": [f"{f['effect'] * 100:+.1f} pts" for f in factors],
    })
    st.dataframe(table.astype(str), hide_index=True, use_container_width=True)


def tabular_section():
    st.markdown("### \U0001f9ea Clinical Risk Questionnaire")
    st.markdown(
        "Fill in what you know - the model needs at least **half** the inputs and "
        "handles missing values with KNN imputation."
    )

    info = kidney_info()
    columns = info["columns"]

    with st.form("kidney_tabular_form"):
        for section_name, group in fields.sections(columns).items():
            if not group:
                continue
            with st.expander(f"\U0001f4cb {section_name}", expanded=(section_name == "About you")):
                grid = st.columns(3)
                for i, col in enumerate(group):
                    with grid[i % 3]:
                        ask(col)
        submitted = st.form_submit_button(
            "\U0001f52c Predict CKD Risk", type="primary", use_container_width=True
        )

    if not submitted:
        return

    answers_dict = {}
    for col in columns:
        val = st.session_state.get(wkey(f"k:{col}"))
        if val is not None:
            answers_dict[col] = val

    min_needed = math.ceil(len(columns) * 0.5)
    if len(answers_dict) < min_needed:
        st.error(
            f"Please fill in at least **{min_needed}** of the {len(columns)} fields "
            f"(you provided {len(answers_dict)})."
        )
        return

    with st.spinner("Running CKD risk cascade..."):
        try:
            result = module(ORGAN, "tabular").predict(answers_dict)
            st.session_state.tabular_result = result
        except Exception as e:
            st.error(f"Prediction failed: {e}")


def tabular_result_card():
    result = st.session_state.tabular_result
    st.markdown("---")
    st.markdown("### \U0001f4ca Tabular Model Result")

    if result.status == REVIEW:
        st.warning(f"Needs clinician review. {result.message}")
        return
    if not result.scored:
        st.warning(result.message)
        return

    prob = result.probability
    threshold = result.details.get("threshold", 0.5)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("CKD Risk", f"{prob:.0%}")
    with col2:
        st.metric("Decision", result.label)
    with col3:
        st.metric("Threshold", f"{threshold:.0%}", delta_color="off")

    bar_val = min(prob / max(threshold, 1e-9) / 2, 1.0)
    st.progress(bar_val)
    st.caption(
        f"Bar is half-full at the routing threshold ({threshold:.0%}). "
        "Past half = positive screen."
    )

    if result.positive:
        st.warning(f"**{result.message}**")
    else:
        st.success(f"**{result.message}**")

    with st.expander("\U0001f50d What moved this risk?"):
        show_factors(result.explanation.get("factors", []))
        st.caption(result.explanation.get("method", ""))

    st.download_button(
        "Download full result (JSON)", mime="application/json",
        file_name="ckd_tabular_result.json",
        data=json.dumps(result.to_dict(arrays=False), indent=2, default=str),
    )


# ---- Image section ----------------------------------------------------------

def image_section():
    info = kidney_info()
    st.markdown("### \U0001f52c CT Scan Analysis")
    st.markdown(
        f"Upload **{info['image_desc']}** for AI-powered image-based analysis. "
        "Supported formats: PNG, JPG, BMP, TIFF."
    )

    col_up, col_preview = st.columns([1, 1])
    with col_up:
        uploaded = st.file_uploader(
            "Upload kidney CT slice", type=IMAGE_TYPES, key=wkey("kidney_image")
        )
        ensemble = st.toggle(
            "Ensemble mode (soft-vote, slower but more robust)", key="ensemble_toggle"
        )
    with col_preview:
        if uploaded:
            st.image(uploaded, caption="Uploaded CT slice", use_container_width=True)

    if uploaded:
        if st.button("\U0001f9e0 Analyse Image", type="primary", use_container_width=True):
            with st.spinner("Running image model... (first run loads the network: ~30 s)"):
                try:
                    result = module(ORGAN, "image").predict(
                        uploaded.getvalue(), ensemble=ensemble
                    )
                    st.session_state.image_result = result
                    st.session_state.uploaded_image_bytes = uploaded.getvalue()
                except Exception as e:
                    st.error(f"Image prediction failed: {e}")


def image_result_card():
    result = st.session_state.image_result
    img_bytes = st.session_state.get("uploaded_image_bytes")
    st.markdown("---")
    st.markdown("### \U0001f5bc Image Model Result")

    if result.status == REJECTED:
        st.error(result.message)
        if img_bytes:
            st.image(img_bytes, caption="Uploaded image", width=240)
        return

    if result.status == REVIEW or result.positive:
        st.warning(f"**{result.message}**")
    else:
        st.success(f"**{result.message}**")

    col_orig, col_overlay = st.columns(2)
    with col_orig:
        if img_bytes:
            st.image(img_bytes, caption="Uploaded CT slice", use_container_width=True)
    with col_overlay:
        if "overlay" in result.explanation:
            st.image(
                result.explanation["overlay"],
                caption="Grad-CAM: where the model focused",
                use_container_width=True,
            )

    if "probabilities" in result.details:
        probs = pd.Series(
            result.details["probabilities"], name="Probability"
        ).sort_values(ascending=False)
        st.markdown("**Class probabilities**")
        st.bar_chart(probs, height=40 + 28 * len(probs))

    st.download_button(
        "Download image result (JSON)", mime="application/json",
        file_name="ckd_image_result.json",
        data=json.dumps(result.to_dict(arrays=False), indent=2, default=str),
    )


# ---- Sidebar ----------------------------------------------------------------

with st.sidebar:
    st.markdown("""
<div style="text-align:center; padding:1rem 0 0.5rem 0;">
  <div style="font-size:3rem;">\U0001fad8</div>
  <div style="color:#a78bfa;font-size:1.4rem;font-weight:700;margin:0.3rem 0;">KidneyCare AI</div>
</div>
""", unsafe_allow_html=True)
    st.divider()
    st.markdown("**\U0001f527 Quick Actions**")
    st.button("Load example patient", on_click=load_example, use_container_width=True)
    st.button("Start over", on_click=start_over, use_container_width=True)
    st.divider()
    st.markdown("**\U00002139 About the models**")
    st.caption(
        "Two complementary AI models:\n\n"
        "- **Tabular**: trained on NHANES clinical data (19 features, XGBoost + calibration)\n\n"
        "- **Image**: deep CNN trained on kidney CT scans\n\n"
        "Results are shown side by side and never combined into a single score."
    )
    st.divider()
    st.caption(
        "\u2695 Research only - not a medical device. "
        "Always consult a licensed physician for medical advice."
    )


# ---- Main page --------------------------------------------------------------

st.markdown("""
<div style="text-align:center; padding:1.5rem 0 0.5rem 0;">
  <h1 style="font-size:2.4rem; background:linear-gradient(135deg,#a78bfa,#06b6d4);
             -webkit-background-clip:text; -webkit-text-fill-color:transparent;
             background-clip:text; font-weight:800; letter-spacing:-0.5px; margin:0;">
    Renal Risk Prediction System
  </h1>
  <p style="color:#9ca3af; font-size:1.05rem; max-width:600px; margin:0.4rem auto 0;">
    An AI-driven system that analyzes clinical data and CT scans to assess kidney health and detect potential risks.
  </p>
</div>
""", unsafe_allow_html=True)

st.divider()

tab_tabular, tab_image = st.tabs([
    "\U0001f9ea Clinical Questionnaire (Tabular)",
    "\U0001f52c CT Scan Analysis (Image)"
])

with tab_tabular:
    tabular_section()
    if "tabular_result" in st.session_state:
        tabular_result_card()

with tab_image:
    image_section()
    if "image_result" in st.session_state:
        image_result_card()

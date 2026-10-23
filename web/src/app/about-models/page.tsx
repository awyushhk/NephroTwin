import {
  FileText,
  ScanLine,
  ShieldAlert,
  Cpu,
  Layers,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  BarChart3,
  ExternalLink,
} from "lucide-react";

export default function AboutModelsPage() {
  return (
    <div className="space-y-8 max-w-4xl">
      {/* Page Title */}
      <div>
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-teal-700">
          <Cpu className="w-4 h-4" />
          <span>System Governance & Documentation</span>
        </div>
        <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight mt-1">
          About the AI Prediction Models
        </h1>
        <p className="text-xs md:text-sm text-slate-500 mt-1">
          Detailed technical specifications, clinical feature definitions, and safety mechanisms for the
          Renal Risk Prediction System.
        </p>
      </div>

      {/* Prominent Research Disclaimer */}
      <div className="p-5 rounded-2xl bg-amber-50 border border-amber-200 text-amber-950 space-y-2">
        <div className="flex items-center gap-2 font-bold text-sm text-amber-900">
          <ShieldAlert className="w-4 h-4 text-amber-700 shrink-0" />
          <span>Mandatory Investigational Notice</span>
        </div>
        <p className="text-xs md:text-sm leading-relaxed text-amber-900/90">
          <strong>Research prototype only — not a medical device and not a substitute for professional medical advice.</strong>{" "}
          This software was developed for investigational clinical decision-support research. It is not cleared or
          approved by the FDA or other regulatory authorities. Always consult a licensed healthcare professional for
          clinical diagnosis and management decisions.
        </p>
      </div>

      {/* Model 1: Clinical Tabular Model */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 md:p-8 shadow-xs space-y-5">
        <div className="flex items-center gap-3 pb-4 border-b border-slate-100">
          <div className="w-10 h-10 rounded-xl bg-teal-50 text-teal-700 flex items-center justify-center shrink-0">
            <FileText className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900">1. Tabular CKD Risk Model</h2>
            <p className="text-xs text-slate-500">Epidemiological Screening (NHANES Cohort)</p>
          </div>
        </div>

        <div className="space-y-4 text-xs md:text-sm text-slate-600 leading-relaxed">
          <p>
            The tabular model screens for Chronic Kidney Disease (CKD) according to the{" "}
            <strong>KDIGO criteria</strong> (defined as an eGFR &lt; 60 mL/min/1.73m² or urine albumin-to-creatinine
            ratio &ge; 30 mg/g). To prevent target leakage and simulate real-world screening before laboratory confirmation,
            the label-defining values (eGFR, serum creatinine, urine albumin) are strictly removed from the feature set.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
            <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-1.5">
              <span className="font-semibold text-slate-800 text-xs uppercase tracking-wide block">
                Model Pipeline
              </span>
              <p className="text-xs text-slate-600">
                Gradient-boosted decision trees (XGBoost) combined with isotonic probability calibration.
                Missing values are imputed using K-Nearest Neighbors (KNN) fitted on similar training patients.
              </p>
            </div>

            <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-1.5">
              <span className="font-semibold text-slate-800 text-xs uppercase tracking-wide block">
                Decision Threshold & Gating
              </span>
              <p className="text-xs text-slate-600">
                A cost-optimal operating threshold (43%) partitions patients into Low, Medium, and High Risk.
                An initial <strong>Isolation Forest anomaly gate</strong> withholds anomalous or extreme biomarker
                combinations for manual clinical review.
              </p>
            </div>
          </div>

          <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-1.5">
            <span className="font-semibold text-slate-800 text-xs uppercase tracking-wide block">
              Explainability via Reference Profile Swapping
            </span>
            <p className="text-xs text-slate-600">
              The model explains predictions by comparing each patient feature against a typical reference patient
              (training median or mode) one at a time. The resulting difference in probability measures that specific
              feature&apos;s contribution to the score without depending on missingness artifacts.
            </p>
          </div>
        </div>
      </div>

      {/* Model 2: CT Scan Deep Learning Model */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 md:p-8 shadow-xs space-y-5">
        <div className="flex items-center gap-3 pb-4 border-b border-slate-100">
          <div className="w-10 h-10 rounded-xl bg-teal-50 text-teal-700 flex items-center justify-center shrink-0">
            <ScanLine className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900">2. CT Image Classification Model</h2>
            <p className="text-xs text-slate-500">Deep Convolutional Neural Network (DenseNet-121)</p>
          </div>
        </div>

        <div className="space-y-4 text-xs md:text-sm text-slate-600 leading-relaxed">
          <p>
            The imaging pipeline processes single-slice axial kidney CT scans to distinguish between four diagnostic classes:
            <strong> Cyst, Normal, Stone, and Tumor</strong>. Images are preprocessed by padding to square, resizing to
            224&times;224, and replicating grayscale channels to three dimensions.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
            <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-1.5">
              <span className="font-semibold text-slate-800 text-xs uppercase tracking-wide block">
                Out-of-Distribution (OOD) Gate
              </span>
              <p className="text-xs text-slate-600">
                An Isolation Forest fitted on pooled feature embeddings rejects non-CT inputs (e.g. chest X-rays,
                photographs, noise). Inputs outside the CT distribution are flagged as <code>rejected</code> and never classified.
              </p>
            </div>

            <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-1.5">
              <span className="font-semibold text-slate-800 text-xs uppercase tracking-wide block">
                Grad-CAM Visual Heatmaps
              </span>
              <p className="text-xs text-slate-600">
                Gradient-weighted Class Activation Mapping (Grad-CAM) computes the gradient of the predicted class score
                with respect to the final convolutional feature maps, highlighting regions that informed the classification.
              </p>
            </div>
          </div>

          <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-1.5">
            <span className="font-semibold text-slate-800 text-xs uppercase tracking-wide block">
              Confidence & Ensemble Checkpoints
            </span>
            <p className="text-xs text-slate-600">
              Predictions with top-class probability below 75% are routed to <code>review</code> for manual clinician inspection.
              The system supports optional soft-voting ensemble across four fine-tuned CNN architectures when all checkpoint
              files are installed locally.
            </p>
          </div>
        </div>
      </div>

      {/* Workflow Independence Principle */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 md:p-8 shadow-xs space-y-4">
        <div className="flex items-center gap-2">
          <HelpCircle className="w-5 h-5 text-teal-700" />
          <h2 className="text-base font-bold text-slate-900">Workflow Independence & Clinical Governance</h2>
        </div>

        <div className="space-y-3 text-xs md:text-sm text-slate-600 leading-relaxed">
          <p>
            A core architectural principle of this system is that <strong>tabular risk and CT scan findings are never combined</strong>.
          </p>
          <ul className="list-disc pl-5 space-y-1.5 text-xs">
            <li>
              The models address distinct clinical questions: tabular screening detects systemic chronic functional decline,
              while CT imaging detects focal anatomical lesions.
            </li>
            <li>
              The models were trained on completely separate cohorts (NHANES epidemiological data vs. public radiological datasets);
              no unified clinical trial data exists to validate a composite score.
            </li>
            <li>
              A low tabular risk does not rule out structural findings like kidney stones or tumors, nor does a benign CT scan
              rule out impaired renal clearance.
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  FileText,
  ScanLine,
  ArrowRight,
  ShieldCheck,
  Cpu,
  Layers,
  Server,
  AlertCircle,
  HelpCircle,
  Activity,
  CheckCircle2,
} from "lucide-react";
import { checkHealth, getKidneyMetadata } from "@/lib/api";
import { HealthResponse, MetadataResponse } from "@/lib/types";

export default function OverviewPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [metadata, setMetadata] = useState<MetadataResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    Promise.all([
      checkHealth().catch(() => null),
      getKidneyMetadata().catch(() => null),
    ]).then(([h, m]) => {
      if (active) {
        setHealth(h);
        setMetadata(m);
        setLoading(false);
      }
    });

    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="space-y-8">
      {/* Hero Welcome Header */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 md:p-8 shadow-xs">
        <div className="max-w-3xl space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-teal-50 text-teal-800 border border-teal-200">
            <Activity className="w-3.5 h-3.5" />
            <span>Clinical Decision Support Research Platform</span>
          </div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-slate-900 tracking-tight">
            Renal Risk Prediction System
          </h1>
          <p className="text-sm md:text-base text-slate-600 leading-relaxed">
            An artificial intelligence platform for non-invasive renal health assessment. Integrates
            calibrated clinical machine learning on patient demographics and routine lab values with
            deep convolutional neural networks on kidney CT imaging.
          </p>
        </div>

        {/* Live Backend Connection Indicator Card */}
        <div className="mt-6 pt-5 border-t border-slate-100 flex flex-wrap items-center justify-between gap-4 text-xs">
          <div className="flex items-center gap-3">
            <span className="font-semibold text-slate-500 uppercase tracking-wider">API Status:</span>
            {loading ? (
              <span className="inline-flex items-center gap-1.5 text-slate-500">
                <Server className="w-3.5 h-3.5 animate-pulse" /> Connecting to backend...
              </span>
            ) : health ? (
              <span className="inline-flex items-center gap-1.5 text-emerald-700 font-semibold bg-emerald-50 px-2.5 py-1 rounded-md border border-emerald-200">
                <CheckCircle2 className="w-3.5 h-3.5" /> Connected &bull; {health.service}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 text-rose-700 font-semibold bg-rose-50 px-2.5 py-1 rounded-md border border-rose-200">
                <AlertCircle className="w-3.5 h-3.5" /> Backend Offline (Check localhost:8000)
              </span>
            )}
          </div>

          {metadata && (
            <div className="text-slate-400 font-mono">
              Tabular: {metadata.tabular.columns.length} features &bull; Image: {metadata.image.best_model}
            </div>
          )}
        </div>
      </div>

      {/* Two Primary Workflow Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Workflow 1: Tabular Clinical Risk */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs flex flex-col justify-between hover:border-teal-400 transition-colors group">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="w-12 h-12 rounded-xl bg-teal-50 text-teal-700 flex items-center justify-center">
                <FileText className="w-6 h-6" />
              </div>
              <span className="text-xs font-semibold text-teal-800 bg-teal-50 px-2.5 py-1 rounded-full border border-teal-200">
                KDIGO CKD Criteria
              </span>
            </div>

            <div>
              <h2 className="text-xl font-bold text-slate-900 group-hover:text-teal-900 transition-colors">
                Clinical CKD Risk Assessment
              </h2>
              <p className="text-xs md:text-sm text-slate-600 mt-2 leading-relaxed">
                Screens chronic kidney disease probability using 19 non-invasive clinical biomarkers
                (demographics, vitals, routine serum chemistry, and urinalysis proxies).
              </p>
            </div>

            <div className="space-y-2 pt-2 border-t border-slate-100 text-xs text-slate-600">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-teal-600" />
                <span>Calibrated XGBoost pipeline with KNN imputation for missing values</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-teal-600" />
                <span>Isolation Forest anomaly gate flags rare or extreme clinical profiles</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-teal-600" />
                <span>What-if factor analysis explains top variables moving patient probability</span>
              </div>
            </div>
          </div>

          <div className="pt-6 mt-6 border-t border-slate-100">
            <Link
              href="/clinical-risk"
              className="inline-flex items-center justify-center gap-2 w-full px-5 py-2.5 rounded-xl font-semibold text-sm bg-teal-700 hover:bg-teal-800 text-white shadow-xs transition-all active:scale-[0.99]"
            >
              <span>Open Questionnaire</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>

        {/* Workflow 2: CT Scan Analysis */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs flex flex-col justify-between hover:border-teal-400 transition-colors group">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="w-12 h-12 rounded-xl bg-teal-50 text-teal-700 flex items-center justify-center">
                <ScanLine className="w-6 h-6" />
              </div>
              <span className="text-xs font-semibold text-teal-800 bg-teal-50 px-2.5 py-1 rounded-full border border-teal-200">
                DenseNet-121 CNN
              </span>
            </div>

            <div>
              <h2 className="text-xl font-bold text-slate-900 group-hover:text-teal-900 transition-colors">
                Kidney CT Scan Analysis
              </h2>
              <p className="text-xs md:text-sm text-slate-600 mt-2 leading-relaxed">
                Processes single-slice axial kidney CT scans to identify structural lesions:
                <strong> Cyst, Normal, Stone, or Tumor</strong> with visual Grad-CAM interpretability.
              </p>
            </div>

            <div className="space-y-2 pt-2 border-t border-slate-100 text-xs text-slate-600">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-teal-600" />
                <span>4-class differential diagnostic categorization</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-teal-600" />
                <span>OOD Gate (Isolation Forest) rejects non-CT images for patient safety</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-teal-600" />
                <span>Grad-CAM heatmaps highlight relevant anatomical feature regions</span>
              </div>
            </div>
          </div>

          <div className="pt-6 mt-6 border-t border-slate-100">
            <Link
              href="/ct-analysis"
              className="inline-flex items-center justify-center gap-2 w-full px-5 py-2.5 rounded-xl font-semibold text-sm bg-teal-700 hover:bg-teal-800 text-white shadow-xs transition-all active:scale-[0.99]"
            >
              <span>Upload CT Scan</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </div>

      {/* Critical Note: Workflow Independence */}
      <div className="bg-slate-100/70 border border-slate-200 rounded-2xl p-6 space-y-3">
        <div className="flex items-center gap-2 text-slate-900 font-bold text-sm">
          <HelpCircle className="w-4 h-4 text-teal-700" />
          <span>Independent Prediction Workflows</span>
        </div>
        <p className="text-xs md:text-sm text-slate-600 leading-relaxed">
          The <strong>Clinical Tabular Model</strong> and the <strong>CT Image Model</strong> assess completely distinct
          pathological mechanisms. Tabular screening estimates systemic chronic kidney dysfunction (KDIGO criteria), whereas
          the CT model identifies focal morphological findings (cysts, calculi, neoplasms).
        </p>
        <p className="text-xs text-slate-500">
          In accordance with medical AI safety guidelines, outputs are reported independently side-by-side. They are never
          averaged, multiplied, or aggregated into a single composite score.
        </p>
      </div>

      {/* Architecture & Model Specifications Card */}
      {metadata && (
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-4">
          <div className="flex items-center gap-2">
            <Cpu className="w-5 h-5 text-teal-700" />
            <h3 className="font-bold text-slate-900 text-base">Loaded Model Specifications</h3>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
            <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200/80">
              <span className="text-slate-400 font-medium block">Tabular Disease Target</span>
              <span className="text-slate-800 font-bold text-sm mt-0.5 block capitalize">
                {metadata.tabular.disease}
              </span>
            </div>

            <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200/80">
              <span className="text-slate-400 font-medium block">Routing Threshold</span>
              <span className="text-slate-800 font-bold text-sm mt-0.5 block">
                {(metadata.tabular.threshold * 100).toFixed(0)}% (Cost-optimal)
              </span>
            </div>

            <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200/80">
              <span className="text-slate-400 font-medium block">CT Classifier Architecture</span>
              <span className="text-slate-800 font-bold text-sm mt-0.5 block">
                {metadata.image.best_model}
              </span>
            </div>

            <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200/80">
              <span className="text-slate-400 font-medium block">CT Diagnostic Classes</span>
              <span className="text-slate-800 font-bold text-sm mt-0.5 block">
                {metadata.image.class_names.join(", ")}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

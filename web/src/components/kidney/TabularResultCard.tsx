"use client";

import {
  Download,
  CheckCircle2,
  AlertTriangle,
  AlertOctagon,
  ArrowRight,
  Info,
  TrendingUp,
  TrendingDown,
} from "lucide-react";
import { TabularPredictionResponse } from "@/lib/types";
import { formatProbability, formatPercent, formatPts, cn } from "@/lib/utils";

interface TabularResultCardProps {
  result: TabularPredictionResponse;
}

export default function TabularResultCard({ result }: TabularResultCardProps) {
  const isReview = result.status === "review";
  const isRejected = result.status === "rejected";
  const isAccepted = result.status === "accepted";
  const prob = result.probability ?? 0;
  const threshold = result.threshold ?? 0.43;
  const factors = result.explanation?.factors || [];

  const handleDownloadJson = () => {
    const dataStr =
      "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(result, null, 2));
    const downloadAnchor = document.createElement("a");
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", "ckd_tabular_result.json");
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  // Bar progress: normalized so that 50% bar width corresponds exactly to the decision threshold
  const normalizedProgress = Math.min(Math.max((prob / Math.max(threshold, 0.01)) * 50, 2), 100);

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden space-y-6 p-6">
      {/* Header with Status Badge */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-200">
        <div>
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block">
            Screening Output
          </span>
          <h3 className="text-xl font-bold text-slate-900 mt-0.5">Tabular Model Result</h3>
        </div>

        <div className="flex items-center gap-2">
          {isAccepted && (
            <span
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border",
                result.positive
                  ? "bg-amber-50 text-amber-800 border-amber-300"
                  : "bg-emerald-50 text-emerald-800 border-emerald-300"
              )}
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Status: Screen {result.positive ? "Positive" : "Negative"}</span>
            </span>
          )}

          {isReview && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-300">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
              <span>Status: Review Required</span>
            </span>
          )}

          {isRejected && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-800 border border-rose-300">
              <AlertOctagon className="w-3.5 h-3.5 text-rose-600" />
              <span>Status: Rejected</span>
            </span>
          )}

          <button
            onClick={handleDownloadJson}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors"
            title="Download JSON result payload"
          >
            <Download className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Download JSON</span>
          </button>
        </div>
      </div>

      {/* When Withheld for Clinical Review (Anomaly Gate) */}
      {isReview && (
        <div className="p-5 bg-amber-50/90 border border-amber-200 rounded-xl text-amber-950 space-y-2">
          <div className="flex items-center gap-2 font-bold text-base text-amber-900">
            <AlertTriangle className="w-5 h-5 text-amber-700" />
            <span>Patient Profile Withheld by Anomaly Gate</span>
          </div>
          <p className="text-sm text-amber-900/90 leading-relaxed">
            {result.message ||
              "Unusual profile: Withheld by the Isolation Forest anomaly gate for manual clinical review."}
          </p>
          <div className="text-xs text-amber-800/80 bg-amber-100/60 p-3 rounded-lg mt-3">
            <strong>Clinical Safety Protocol:</strong> The model withholding gate prevents scoring extreme or
            implausible biomarker combinations (such as severe laboratory compounding conditions or entry errors)
            that lie outside the validated NHANES training distribution. Direct clinician assessment is required.
          </div>
        </div>
      )}

      {/* When Scored Normally */}
      {result.scored && (
        <>
          {/* 3 Metric Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80">
              <span className="text-xs font-semibold text-slate-500 uppercase">Estimated CKD Risk</span>
              <div
                className={cn(
                  "text-3xl font-extrabold tracking-tight mt-1",
                  result.positive ? "text-amber-700" : "text-emerald-700"
                )}
              >
                {formatProbability(result.probability)}
              </div>
              <span className="text-xs text-slate-500 mt-1 block">
                Calibrated P(Disease)
              </span>
            </div>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80">
              <span className="text-xs font-semibold text-slate-500 uppercase">Decision Band</span>
              <div className="text-2xl font-bold text-slate-900 mt-1">
                {result.label || "Indeterminate"}
              </div>
              <span className="text-xs text-slate-500 mt-1 block">
                Threshold: {formatPercent(result.threshold)}
              </span>
            </div>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80">
              <span className="text-xs font-semibold text-slate-500 uppercase">Routing Action</span>
              <div className="text-sm font-semibold text-slate-800 mt-1 flex items-center gap-1.5">
                <ArrowRight className="w-4 h-4 text-teal-700 shrink-0" />
                <span>{result.positive ? "Refer for Kidney Labs" : "Continue Routine Care"}</span>
              </div>
              <span className="text-xs text-slate-500 mt-1 block">
                {result.positive ? "eGFR + ACR tests advised" : "Annual clinical check"}
              </span>
            </div>
          </div>

          {/* Progress Bar with Routing Threshold Marker */}
          <div className="space-y-2 pt-2">
            <div className="flex items-center justify-between text-xs text-slate-600">
              <span>Risk Continuum</span>
              <span className="font-semibold">
                Routing Threshold: {formatPercent(result.threshold)}
              </span>
            </div>

            <div className="relative h-4 w-full bg-slate-100 rounded-full overflow-hidden border border-slate-200">
              {/* Threshold line marker at 50% width */}
              <div className="absolute top-0 bottom-0 left-1/2 w-0.5 bg-slate-400 z-10" />

              <div
                className={cn(
                  "h-full transition-all duration-500 rounded-full",
                  prob >= 0.5
                    ? "bg-rose-600"
                    : prob >= threshold
                    ? "bg-amber-500"
                    : "bg-emerald-600"
                )}
                style={{ width: `${normalizedProgress}%` }}
              />
            </div>

            <div className="flex items-center justify-between text-[11px] text-slate-400">
              <span>0% (Lowest Risk)</span>
              <span className="text-slate-600 font-medium">▲ Halfway = Routing Threshold</span>
              <span>100% (High Risk)</span>
            </div>
          </div>

          {/* Clinical Message Banner */}
          <div
            className={cn(
              "p-4 rounded-xl border text-sm leading-relaxed",
              result.positive
                ? "bg-amber-50 border-amber-200 text-amber-900"
                : "bg-emerald-50 border-emerald-200 text-emerald-900"
            )}
          >
            <div className="font-semibold text-xs uppercase tracking-wide mb-1">
              {result.positive ? "Action Recommended" : "Routine Observation"}
            </div>
            {result.message}
          </div>

          {/* Explanation Factor Analysis */}
          <div className="space-y-3 pt-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Info className="w-4 h-4 text-teal-700" />
                <h4 className="text-sm font-bold text-slate-900">What moved this patient&apos;s risk?</h4>
              </div>
              <span className="text-xs text-slate-400">Top 5 influence factors</span>
            </div>

            {factors.length === 0 ? (
              <p className="text-xs text-slate-500 italic bg-slate-50 p-4 rounded-lg">
                No single input significantly moved the probability away from the reference baseline for this profile.
              </p>
            ) : (
              <div className="overflow-x-auto border border-slate-200 rounded-lg">
                <table className="w-full text-xs text-left text-slate-700">
                  <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                    <tr>
                      <th className="px-4 py-2.5">Biomarker / Feature</th>
                      <th className="px-4 py-2.5">This Patient</th>
                      <th className="px-4 py-2.5">Population Reference</th>
                      <th className="px-4 py-2.5 text-right">Risk Impact</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {factors.map((f, i) => {
                      const isRiskIncrease = f.effect > 0;
                      return (
                        <tr key={i} className="hover:bg-slate-50/80 transition-colors">
                          <td className="px-4 py-2.5 font-medium text-slate-900 capitalize">
                            {f.feature.replace(/_/g, " ")}
                          </td>
                          <td className="px-4 py-2.5 font-semibold text-slate-800">
                            {f.value !== null && f.value !== undefined ? String(f.value) : "—"}
                          </td>
                          <td className="px-4 py-2.5 text-slate-500">
                            {f.typical !== null && f.typical !== undefined ? String(f.typical) : "N/A"}
                          </td>
                          <td className="px-4 py-2.5 text-right font-medium">
                            <span
                              className={cn(
                                "inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px]",
                                isRiskIncrease
                                  ? "bg-rose-50 text-rose-700 font-bold"
                                  : "bg-emerald-50 text-emerald-700 font-bold"
                              )}
                            >
                              {isRiskIncrease ? (
                                <TrendingUp className="w-3 h-3" />
                              ) : (
                                <TrendingDown className="w-3 h-3" />
                              )}
                              {formatPts(f.effect)}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {result.explanation?.method && (
              <p className="text-[11px] text-slate-400 italic">
                Methodology: {result.explanation.method}
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

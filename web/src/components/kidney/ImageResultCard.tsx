"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import {
  Download,
  CheckCircle2,
  AlertTriangle,
  AlertOctagon,
  ScanLine,
  Eye,
  Info,
} from "lucide-react";
import { ImagePredictionResponse } from "@/lib/types";
import { formatPercent, cn } from "@/lib/utils";

interface ImageResultCardProps {
  result: ImagePredictionResponse;
  originalFile?: File | null;
}

export default function ImageResultCard({ result, originalFile }: ImageResultCardProps) {
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);

  useEffect(() => {
    if (originalFile) {
      const url = URL.createObjectURL(originalFile);
      setOriginalUrl(url);
      return () => {
        URL.revokeObjectURL(url);
      };
    }
  }, [originalFile]);

  const isRejected = result.status === "rejected";
  const isReview = result.status === "review";
  const isAccepted = result.status === "accepted";
  const label = result.label;
  const probabilities = result.details?.probabilities || {};
  const overlaySrc = result.explanation?.overlay;

  const handleDownloadJson = () => {
    const dataStr =
      "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(result, null, 2));
    const downloadAnchor = document.createElement("a");
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", "ckd_image_result.json");
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden space-y-6 p-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-200">
        <div>
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block">
            Deep CNN Output
          </span>
          <h3 className="text-xl font-bold text-slate-900 mt-0.5">CT Image Model Result</h3>
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
              <span>Status: {result.positive ? "Finding Detected" : "Normal"}</span>
            </span>
          )}

          {isReview && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-300">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
              <span>Status: Low Confidence Review</span>
            </span>
          )}

          {isRejected && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-800 border border-rose-300">
              <AlertOctagon className="w-3.5 h-3.5 text-rose-600" />
              <span>Status: OOD Rejected</span>
            </span>
          )}

          <button
            onClick={handleDownloadJson}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Download JSON</span>
          </button>
        </div>
      </div>

      {/* Case 1: Out of Distribution (OOD) Rejection */}
      {isRejected && (
        <div className="p-5 bg-rose-50/80 border border-rose-200 rounded-xl text-rose-950 space-y-4">
          <div className="flex items-center gap-2 font-bold text-base text-rose-900">
            <AlertOctagon className="w-5 h-5 text-rose-600 shrink-0" />
            <span>Image Rejected by Out-of-Distribution (OOD) Gate</span>
          </div>

          <p className="text-sm text-rose-900 leading-relaxed font-medium">
            {result.message}
          </p>

          <div className="p-3 bg-white/70 border border-rose-200/60 rounded-lg text-xs text-rose-800 space-y-1">
            <strong>Safety Mechanism:</strong> An Isolation Forest trained on the pooled feature embeddings
            of genuine kidney CT scans detected that this image does not match the expected CT scan distribution.
            To avoid dangerous false classifications, the model refuses to score non-CT inputs (e.g. chest X-rays,
            ECG tracings, photographic images, or artifacts).
          </div>

          {originalUrl && (
            <div className="pt-2">
              <span className="text-xs font-semibold text-slate-600 block mb-2">Uploaded Image:</span>
              <div className="relative w-48 h-48 rounded-lg overflow-hidden border border-slate-300 bg-black">
                <Image
                  src={originalUrl}
                  alt="Rejected upload"
                  fill
                  className="object-contain"
                  unoptimized
                />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Case 2: Accepted or Low Confidence Review */}
      {(isAccepted || isReview) && (
        <div className="space-y-6">
          {/* Key Metrics Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80">
              <span className="text-xs font-semibold text-slate-500 uppercase">Predicted Finding</span>
              <div
                className={cn(
                  "text-2xl font-bold mt-1",
                  label === "Normal"
                    ? "text-emerald-700"
                    : label === "Tumor"
                    ? "text-rose-700"
                    : "text-amber-700"
                )}
              >
                {label || "Unclassified"}
              </div>
              <span className="text-xs text-slate-500 mt-1 block">
                Model: {result.details?.model || "DenseNet121_FT"}
              </span>
            </div>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80">
              <span className="text-xs font-semibold text-slate-500 uppercase">Class Confidence</span>
              <div className="text-2xl font-bold text-slate-900 mt-1">
                {formatPercent(result.details?.confidence)}
              </div>
              <span className="text-xs text-slate-500 mt-1 block">
                Threshold: {formatPercent(result.details?.threshold)}
              </span>
            </div>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80">
              <span className="text-xs font-semibold text-slate-500 uppercase">P(Abnormal)</span>
              <div
                className={cn(
                  "text-2xl font-bold mt-1",
                  result.positive ? "text-amber-700" : "text-emerald-700"
                )}
              >
                {formatPercent(result.probability)}
              </div>
              <span className="text-xs text-slate-500 mt-1 block">
                1 - P(Normal)
              </span>
            </div>
          </div>

          {/* Finding Message Banner */}
          <div
            className={cn(
              "p-4 rounded-xl border text-sm leading-relaxed",
              isReview
                ? "bg-amber-50 border-amber-200 text-amber-900"
                : result.positive
                ? "bg-amber-50 border-amber-200 text-amber-900"
                : "bg-emerald-50 border-emerald-200 text-emerald-900"
            )}
          >
            <div className="font-semibold text-xs uppercase tracking-wide mb-1">
              {isReview
                ? "Manual Clinician Review Recommended"
                : result.positive
                ? "Image Finding Noted"
                : "Normal CT Scan Screen"}
            </div>
            {result.message}
          </div>

          {/* Side-by-Side Visual Comparison: Original vs Grad-CAM Overlay */}
          <div className="space-y-3 pt-2">
            <div className="flex items-center gap-2">
              <Eye className="w-4 h-4 text-teal-700" />
              <h4 className="text-sm font-bold text-slate-900">
                Visual Explainability: CT Slice & Grad-CAM Attention Map
              </h4>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Original Image */}
              <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/70 text-center space-y-2">
                <span className="text-xs font-semibold text-slate-700 block">
                  Original Uploaded CT Slice
                </span>
                <div className="relative w-full aspect-square max-w-[280px] mx-auto rounded-lg overflow-hidden border border-slate-300 bg-black">
                  {originalUrl ? (
                    <Image
                      src={originalUrl}
                      alt="Original CT Slice"
                      fill
                      className="object-contain"
                      unoptimized
                    />
                  ) : (
                    <div className="h-full flex items-center justify-center text-xs text-slate-400">
                      CT Slice Processed
                    </div>
                  )}
                </div>
                <span className="text-[11px] text-slate-400 block">Preprocessed axial view</span>
              </div>

              {/* Grad-CAM Heatmap Overlay */}
              <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/70 text-center space-y-2">
                <span className="text-xs font-semibold text-slate-700 block">
                  Grad-CAM Feature Activation Overlay
                </span>
                <div className="relative w-full aspect-square max-w-[280px] mx-auto rounded-lg overflow-hidden border border-slate-300 bg-black">
                  {overlaySrc ? (
                    <Image
                      src={overlaySrc}
                      alt="Grad-CAM Overlay"
                      fill
                      className="object-contain"
                      unoptimized
                    />
                  ) : (
                    <div className="h-full flex items-center justify-center text-xs text-slate-400 p-4">
                      Overlay not available for this prediction
                    </div>
                  )}
                </div>
                <span className="text-[11px] text-slate-500 block">
                  {result.explanation?.method || "Where the neural network focused"}
                </span>
              </div>
            </div>
          </div>

          {/* Class Probabilities Distribution */}
          {Object.keys(probabilities).length > 0 && (
            <div className="space-y-3 pt-3 border-t border-slate-100">
              <div className="flex items-center gap-2">
                <Info className="w-4 h-4 text-teal-700" />
                <h4 className="text-sm font-bold text-slate-900">Class Probabilities Breakdown</h4>
              </div>

              <div className="space-y-2.5">
                {Object.entries(probabilities)
                  .sort(([, a], [, b]) => b - a)
                  .map(([className, prob]) => {
                    const isTop = className === label;
                    return (
                      <div key={className} className="space-y-1">
                        <div className="flex items-center justify-between text-xs font-medium">
                          <span
                            className={cn(
                              "capitalize",
                              isTop ? "text-slate-900 font-bold" : "text-slate-600"
                            )}
                          >
                            {className} {isTop && " (Predicted Class)"}
                          </span>
                          <span className={cn(isTop ? "text-teal-800 font-bold" : "text-slate-500")}>
                            {formatPercent(prob)}
                          </span>
                        </div>
                        <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                          <div
                            className={cn(
                              "h-full rounded-full transition-all duration-300",
                              isTop
                                ? className === "Normal"
                                  ? "bg-emerald-600"
                                  : "bg-teal-700"
                                : "bg-slate-300"
                            )}
                            style={{ width: `${Math.min(prob * 100, 100)}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

"use client";

import { useRef, useState } from "react";
import { AlertTriangle, ArrowDown, ScanLine } from "lucide-react";
import ImageUploader from "@/components/kidney/ImageUploader";
import ImageResultCard from "@/components/kidney/ImageResultCard";
import { CTStudyPredictionResponse } from "@/lib/types";

const statusLabels: Record<string, string> = {
  accepted: "Accepted by image checks",
  review_required: "Image review required",
  ood_rejected: "Rejected by OOD gate",
  invalid_file: "File not analyzed",
  processing_error: "Processing failed",
};

export default function CTAnalysisPage() {
  const [study, setStudy] = useState<CTStudyPredictionResponse | null>(null);
  const [studyFiles, setStudyFiles] = useState<File[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const resultsRef = useRef<HTMLDivElement | null>(null);

  const handlePredictionSuccess = (result: CTStudyPredictionResponse, files: File[]) => {
    setStudy(result);
    setStudyFiles(files);
    window.setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
  };

  const handleReset = () => {
    setStudy(null);
    setStudyFiles([]);
  };

  return (
    <div className="space-y-8">
      <div>
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-teal-700"><ScanLine className="h-4 w-4" /><span>Workflow 2</span></div>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 md:text-3xl">CT Scan Image Analysis</h1>
        <p className="mt-1 max-w-3xl text-xs text-slate-500 md:text-sm">Analyze multiple kidney CT slice images independently with the existing OOD gate, DenseNet121 classifier, confidence check, and Grad-CAM. The examination summary is descriptive and may require expert review.</p>
      </div>

      <ImageUploader onPredictionSuccess={handlePredictionSuccess} onReset={handleReset} isLoading={isLoading} setIsLoading={setIsLoading} />

      {study && <section ref={resultsRef} className="space-y-5 pt-2" aria-labelledby="study-summary-heading">
        <div className="flex items-center gap-2 text-xs font-medium text-slate-500"><ArrowDown className="h-3.5 w-3.5 text-teal-600" /><span>Examination summary · ID {study.examination_id}</span></div>
        <div className={`rounded-2xl border p-5 sm:p-6 ${study.summary.status === "study_review_required" ? "border-amber-300 bg-amber-50/70" : "border-teal-200 bg-teal-50/50"}`}>
          <div className="flex items-start gap-3">
            {study.summary.status === "study_review_required" && <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" />}
            <div className="min-w-0 flex-1">
              <h2 id="study-summary-heading" className="text-lg font-bold text-slate-900">{study.summary.status === "study_review_required" ? "Examination review required" : "Descriptive examination summary"}</h2>
              <p className="mt-1 text-sm text-slate-600">{study.summary.accepted_image_count} of {study.summary.submitted_image_count} images passed the existing image checks. This describes image-level model outputs; it is not a confirmed diagnosis or a calibrated whole-examination probability.</p>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Object.entries(study.summary.class_distribution).map(([name, item]) => <div key={name} className="rounded-xl border border-white bg-white/80 p-3"><p className="text-xs font-medium text-slate-500">{name}</p><p className="mt-1 text-lg font-bold text-slate-900">{item.count} <span className="text-xs font-medium text-slate-500">({item.percentage}%)</span></p></div>)}
          </div>
          {Object.keys(study.summary.mean_image_level_scores).length > 0 && <div className="mt-4 rounded-xl border border-slate-200 bg-white/80 p-4">
            <h3 className="text-sm font-semibold text-slate-800">Mean image-level class scores</h3>
            <p className="mt-0.5 text-xs text-slate-500">Averages of available per-image model scores for accepted images. These are not examination-level probabilities.</p>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">{Object.entries(study.summary.mean_image_level_scores).map(([name, score]) => <div key={name} className="text-xs text-slate-600"><span className="font-semibold text-slate-800">{name}:</span> {(score * 100).toFixed(1)}% <span className="text-slate-400">({study.summary.mean_score_image_counts[name] ?? 0} images)</span></div>)}</div>
          </div>}
          {study.summary.warnings.length > 0 && <ul className="mt-4 space-y-1 text-sm text-amber-900">{study.summary.warnings.map((warning) => <li key={warning} className="flex gap-2"><span aria-hidden="true">•</span><span>{warning}</span></li>)}</ul>}
          <p className="mt-4 border-t border-slate-200/70 pt-3 text-xs leading-5 text-slate-500">Summary rule: at least {study.summary.minimum_accepted_images} accepted images are needed, and any disagreement between accepted predicted classes requires review. No majority vote is used. This rule is not clinically validated.</p>
        </div>

        <div className="space-y-4">
          <div><h2 className="text-lg font-bold text-slate-900">Individual image results</h2><p className="mt-1 text-xs text-slate-500">Each result below is for one uploaded image. Failed or rejected images are not counted as Normal.</p></div>
          {study.images.map((image, index) => <article key={image.image_id} className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 sm:p-5">
            <div className="flex flex-wrap items-center justify-between gap-2"><div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-900" title={image.filename}>{image.filename}</p><p className="mt-0.5 font-mono text-[10px] text-slate-400">Image ID {image.image_id}</p></div><span className={`rounded-full px-3 py-1 text-xs font-semibold ${image.status === "accepted" ? "bg-emerald-50 text-emerald-800" : image.status === "review_required" ? "bg-amber-50 text-amber-800" : "bg-rose-50 text-rose-800"}`}>{statusLabels[image.status] ?? image.status.replaceAll("_", " ")}</span></div>
            {image.prediction ? <ImageResultCard result={image.prediction} originalFile={studyFiles[index] ?? null} /> : <div role="status" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">{image.error ?? "This image could not be analyzed."}</div>}
          </article>)}
        </div>
      </section>}
    </div>
  );
}

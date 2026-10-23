"use client";

import { useState, useRef } from "react";
import { ScanLine, ArrowDown } from "lucide-react";
import ImageUploader from "@/components/kidney/ImageUploader";
import ImageResultCard from "@/components/kidney/ImageResultCard";
import { ImagePredictionResponse } from "@/lib/types";

export default function CTAnalysisPage() {
  const [result, setResult] = useState<ImagePredictionResponse | null>(null);
  const [originalFile, setOriginalFile] = useState<File | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const resultsRef = useRef<HTMLDivElement | null>(null);

  const handlePredictionSuccess = (res: ImagePredictionResponse, file: File) => {
    setResult(res);
    setOriginalFile(file);
    setTimeout(() => {
      resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 100);
  };

  const handleReset = () => {
    setResult(null);
    setOriginalFile(null);
  };

  return (
    <div className="space-y-8">
      {/* Page Title */}
      <div>
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-teal-700">
          <ScanLine className="w-4 h-4" />
          <span>Workflow 2</span>
        </div>
        <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight mt-1">
          CT Scan Image Analysis
        </h1>
        <p className="text-xs md:text-sm text-slate-500 mt-1 max-w-3xl">
          Automated kidney CT slice classification with Out-of-Distribution safety gating and Grad-CAM attention
          localization. Categorizes slices into Cyst, Normal, Stone, or Tumor.
        </p>
      </div>

      {/* Upload Interface */}
      <ImageUploader
        onPredictionSuccess={handlePredictionSuccess}
        onReset={handleReset}
        isLoading={isLoading}
        setIsLoading={setIsLoading}
      />

      {/* Results Section */}
      {result && (
        <div ref={resultsRef} className="pt-4 space-y-4">
          <div className="flex items-center gap-2 text-slate-500 text-xs font-medium">
            <ArrowDown className="w-3.5 h-3.5 text-teal-600" />
            <span>Generated Deep Learning Assessment</span>
          </div>
          <ImageResultCard result={result} originalFile={originalFile} />
        </div>
      )}
    </div>
  );
}

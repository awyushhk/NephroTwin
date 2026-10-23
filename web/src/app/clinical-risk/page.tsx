"use client";

import { useState, useRef } from "react";
import { FileText, ArrowDown } from "lucide-react";
import TabularQuestionnaire from "@/components/kidney/TabularQuestionnaire";
import TabularResultCard from "@/components/kidney/TabularResultCard";
import { TabularPredictionResponse } from "@/lib/types";

export default function ClinicalRiskPage() {
  const [result, setResult] = useState<TabularPredictionResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const resultsRef = useRef<HTMLDivElement | null>(null);

  const handlePredictionSuccess = (res: TabularPredictionResponse) => {
    setResult(res);
    setTimeout(() => {
      resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 100);
  };

  const handleReset = () => {
    setResult(null);
  };

  return (
    <div className="space-y-8">
      {/* Page Title */}
      <div>
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-teal-700">
          <FileText className="w-4 h-4" />
          <span>Workflow 1</span>
        </div>
        <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight mt-1">
          Clinical CKD Risk Assessment
        </h1>
        <p className="text-xs md:text-sm text-slate-500 mt-1 max-w-3xl">
          Evaluate chronic kidney disease risk using patient demographics, clinical measurements, and routine lab
          proxies. Based on calibrated machine learning trained on NHANES epidemiological data.
        </p>
      </div>

      {/* Questionnaire Form */}
      <TabularQuestionnaire
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
            <span>Generated Prediction Assessment</span>
          </div>
          <TabularResultCard result={result} />
        </div>
      )}
    </div>
  );
}

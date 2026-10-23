"use client";

import { useEffect, useState } from "react";
import {
  FileText,
  User,
  Activity,
  FlaskConical,
  HeartPulse,
  Sparkles,
  RotateCcw,
  AlertCircle,
  CheckCircle2,
  HelpCircle,
} from "lucide-react";
import { getKidneyMetadata, predictTabular, ApiError } from "@/lib/api";
import { MetadataResponse, TabularPredictionResponse, FeatureMetadata } from "@/lib/types";
import { CASCADE_EXAMPLE_PATIENT, LOW_RISK_EXAMPLE_PATIENT } from "@/lib/sample-data";
import { cn } from "@/lib/utils";

interface TabularQuestionnaireProps {
  onPredictionSuccess: (result: TabularPredictionResponse) => void;
  onReset: () => void;
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
}

const SECTION_ICONS: Record<string, any> = {
  "About you": User,
  Measurements: Activity,
  "Lab results": FlaskConical,
  "History and lifestyle": HeartPulse,
};

export default function TabularQuestionnaire({
  onPredictionSuccess,
  onReset,
  isLoading,
  setIsLoading,
}: TabularQuestionnaireProps) {
  const [metadata, setMetadata] = useState<MetadataResponse | null>(null);
  const [metaLoading, setMetaLoading] = useState(true);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [formData, setFormData] = useState<Record<string, any>>({});
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    getKidneyMetadata()
      .then((data) => {
        if (mounted) {
          setMetadata(data);
          setMetaLoading(false);
        }
      })
      .catch((err) => {
        if (mounted) {
          setMetaError(
            err instanceof ApiError ? err.detail : "Could not load clinical metadata from backend."
          );
          setMetaLoading(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  const columns = metadata?.tabular.columns || [];
  const minRequired = metadata?.tabular.min_features_required || 10;
  const totalFeatures = metadata?.tabular.total_features || 19;

  // Count features with non-null, non-empty values
  const filledCount = columns.filter((col) => {
    const v = formData[col];
    return v !== undefined && v !== null && v !== "" && !(typeof v === "number" && isNaN(v));
  }).length;

  const isFormValid = filledCount >= minRequired;

  const handleInputChange = (column: string, value: any) => {
    setFormData((prev) => {
      const next = { ...prev };
      if (value === "" || value === "unknown" || value === undefined || value === null) {
        delete next[column];
      } else {
        next[column] = value;
      }
      return next;
    });
    if (errorMessage) setErrorMessage(null);
  };

  const handleLoadExample = (example: Record<string, any>) => {
    setFormData({ ...example });
    setErrorMessage(null);
  };

  const handleStartOver = () => {
    setFormData({});
    setErrorMessage(null);
    onReset();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isFormValid) {
      setErrorMessage(
        `Please provide at least ${minRequired} of the ${totalFeatures} clinical questionnaire fields (you provided ${filledCount}).`
      );
      return;
    }

    setErrorMessage(null);
    setIsLoading(true);

    try {
      const result = await predictTabular(formData);
      onPredictionSuccess(result);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else {
        setErrorMessage("Tabular prediction failed. Please verify that the API server is running.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  if (metaLoading) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-8 shadow-xs animate-pulse">
        <div className="h-6 bg-slate-200 rounded w-1/3 mb-4" />
        <div className="h-4 bg-slate-100 rounded w-2/3 mb-8" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-20 bg-slate-100 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (metaError || !metadata) {
    return (
      <div className="p-6 bg-rose-50 border border-rose-200 rounded-xl text-rose-900">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-rose-600 mt-0.5 shrink-0" />
          <div>
            <h3 className="font-semibold text-rose-950">Backend Connection Error</h3>
            <p className="text-sm mt-1 text-rose-800">
              {metaError || "Unable to reach the FastAPI backend to retrieve clinical feature metadata."}
            </p>
            <p className="text-xs text-rose-600 mt-2 font-mono">
              Target: {process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"}
            </p>
          </div>
        </div>
      </div>
    );
  }

  const sections = metadata.tabular.sections;
  const features = metadata.tabular.features;

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Questionnaire Header & Actions */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2">
              <span className="p-1.5 bg-teal-50 text-teal-700 rounded-md">
                <FileText className="w-4 h-4" />
              </span>
              <h2 className="text-lg font-bold text-slate-900">Clinical Risk Questionnaire</h2>
            </div>
            <p className="text-xs md:text-sm text-slate-500 mt-1">
              Enter available patient markers. Missing values are imputed using KNN trained on NHANES clinical cohorts.
            </p>
          </div>

          {/* Quick Action Buttons */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => handleLoadExample(CASCADE_EXAMPLE_PATIENT)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors"
              title="58-year-old male with clinical CKD risk indicators"
            >
              <Sparkles className="w-3.5 h-3.5 text-teal-600" />
              <span>Example Patient (Elevated)</span>
            </button>
            <button
              type="button"
              onClick={() => handleLoadExample(LOW_RISK_EXAMPLE_PATIENT)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors"
              title="28-year-old female with baseline healthy markers"
            >
              <Sparkles className="w-3.5 h-3.5 text-emerald-600" />
              <span>Example (Low Risk)</span>
            </button>
            <button
              type="button"
              onClick={handleStartOver}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white hover:bg-slate-100 text-slate-600 border border-slate-200 transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Clear</span>
            </button>
          </div>
        </div>

        {/* Feature Completion Tracker */}
        <div className="pt-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-3">
            <span className="font-semibold text-slate-700">
              Completion: {filledCount} of {totalFeatures} features
            </span>
            {isFormValid ? (
              <span className="inline-flex items-center gap-1 text-emerald-700 font-medium bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200">
                <CheckCircle2 className="w-3 h-3" /> Minimum met ({filledCount}/{minRequired})
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-amber-700 font-medium bg-amber-50 px-2 py-0.5 rounded-md border border-amber-200">
                <AlertCircle className="w-3 h-3" /> Need at least {minRequired - filledCount} more
              </span>
            )}
          </div>

          <div className="w-full sm:w-48 bg-slate-100 h-2 rounded-full overflow-hidden">
            <div
              className={cn(
                "h-full transition-all duration-300",
                isFormValid ? "bg-teal-600" : "bg-amber-500"
              )}
              style={{ width: `${Math.min((filledCount / totalFeatures) * 100, 100)}%` }}
            />
          </div>
        </div>
      </div>

      {/* Field Sections */}
      <div className="space-y-6">
        {Object.entries(sections).map(([sectionName, cols]) => {
          if (!cols || cols.length === 0) return null;
          const SectionIcon = SECTION_ICONS[sectionName] || FileText;

          return (
            <div
              key={sectionName}
              className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden"
            >
              <div className="flex items-center gap-2.5 px-6 py-3.5 bg-slate-50/70 border-b border-slate-200 text-slate-800 font-semibold text-sm">
                <SectionIcon className="w-4 h-4 text-teal-700" />
                <span>{sectionName}</span>
                <span className="text-xs text-slate-400 font-normal ml-auto">
                  {cols.filter((c) => formData[c] !== undefined && formData[c] !== "").length} of {cols.length} answered
                </span>
              </div>

              <div className="p-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                {cols.map((colName) => {
                  const meta: FeatureMetadata = features[colName] || {
                    name: colName,
                    label: colName,
                    type: "numeric",
                  };
                  const currentValue = formData[colName];

                  return (
                    <div key={colName} className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <label
                          htmlFor={`field-${colName}`}
                          className="text-xs font-semibold text-slate-700 block truncate"
                          title={meta.label}
                        >
                          {meta.label}
                        </label>
                        {meta.unit && (
                          <span className="text-[10px] text-slate-400 font-medium shrink-0 ml-1">
                            ({meta.unit})
                          </span>
                        )}
                      </div>

                      {meta.type === "numeric" ? (
                        <div className="relative">
                          <input
                            id={`field-${colName}`}
                            type="number"
                            step={meta.step ?? "any"}
                            min={meta.min ?? undefined}
                            max={meta.max ?? undefined}
                            value={currentValue ?? ""}
                            onChange={(e) => {
                              const val = e.target.value;
                              handleInputChange(colName, val === "" ? null : Number(val));
                            }}
                            placeholder="Unknown"
                            className="w-full px-3 py-2 text-xs md:text-sm bg-white border border-slate-300 rounded-lg text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-600 focus:border-transparent transition-all"
                          />
                        </div>
                      ) : meta.type === "ordinal" ? (
                        <select
                          id={`field-${colName}`}
                          value={currentValue ?? ""}
                          onChange={(e) => {
                            const val = e.target.value;
                            handleInputChange(colName, val === "" ? null : Number(val));
                          }}
                          className="w-full px-3 py-2 text-xs md:text-sm bg-white border border-slate-300 rounded-lg text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-600 focus:border-transparent transition-all"
                        >
                          <option value="">Unknown</option>
                          {Array.isArray(meta.options) &&
                            meta.options.map((opt: any) => (
                              <option key={opt.value} value={opt.value}>
                                {opt.label || opt.value}
                              </option>
                            ))}
                        </select>
                      ) : (
                        <select
                          id={`field-${colName}`}
                          value={currentValue ?? ""}
                          onChange={(e) => {
                            const val = e.target.value;
                            handleInputChange(colName, val === "" ? null : val);
                          }}
                          className="w-full px-3 py-2 text-xs md:text-sm bg-white border border-slate-300 rounded-lg text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-600 focus:border-transparent transition-all"
                        >
                          <option value="">Unknown</option>
                          {Array.isArray(meta.options) &&
                            meta.options.map((opt: any) => {
                              const valStr = typeof opt === "string" ? opt : opt.value;
                              const labelStr = typeof opt === "string" ? opt : opt.label;
                              return (
                                <option key={valStr} value={valStr}>
                                  {labelStr}
                                </option>
                              );
                            })}
                        </select>
                      )}

                      {/* Hint for numeric range */}
                      {meta.type === "numeric" && meta.min !== null && meta.max !== null && (
                        <div className="flex items-center justify-between text-[10px] text-slate-400">
                          <span>Range: {meta.min}–{meta.max}</span>
                          {currentValue !== undefined && currentValue !== null && (
                            <span className="text-teal-700 font-medium">Entered</span>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {/* Validation / API Error Banner */}
      {errorMessage && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-900 text-sm flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold block">Submission Error</span>
            <span>{errorMessage}</span>
          </div>
        </div>
      )}

      {/* Submit Action Bar */}
      <div className="sticky bottom-4 z-10 p-4 bg-white/95 backdrop-blur-sm border border-slate-200 rounded-xl shadow-lg flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="text-xs text-slate-500 flex items-center gap-2">
          <HelpCircle className="w-4 h-4 text-slate-400 shrink-0" />
          <span>
            {isFormValid
              ? "Ready to score with calibrated XGBoost pipeline."
              : `Fill in at least ${minRequired} fields (${filledCount}/${minRequired} completed).`}
          </span>
        </div>

        <div className="flex items-center gap-3 w-full sm:w-auto">
          <button
            type="submit"
            disabled={!isFormValid || isLoading}
            className={cn(
              "w-full sm:w-auto px-6 py-2.5 rounded-lg text-sm font-semibold text-white shadow-xs transition-all flex items-center justify-center gap-2",
              isFormValid && !isLoading
                ? "bg-teal-700 hover:bg-teal-800 active:scale-[0.99] cursor-pointer"
                : "bg-slate-300 text-slate-500 cursor-not-allowed"
            )}
          >
            {isLoading ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>Running CKD Cascade...</span>
              </>
            ) : (
              <>
                <Activity className="w-4 h-4" />
                <span>Predict CKD Risk</span>
              </>
            )}
          </button>
        </div>
      </div>
    </form>
  );
}

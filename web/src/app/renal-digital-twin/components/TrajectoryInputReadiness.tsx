"use client";

import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Database,
  Info,
  LoaderCircle,
} from "lucide-react";
import type {
  TrajectoryEligibility,
  Observation,
  ObservationDateFields,
  MeasurementType,
} from "../types";

export function TrajectoryInputReadiness({
  trajectoryEligibility,
  trajectoryEligibilityLoading,
  trajectoryInputsAvailable,
  scenarioBase,
  eGfrObservations,
  formatObservationDate,
}: {
  trajectoryEligibility: TrajectoryEligibility | null;
  trajectoryEligibilityLoading: boolean;
  trajectoryInputsAvailable: boolean;
  scenarioBase: string;
  eGfrObservations: Observation[];
  formatObservationDate: (row: ObservationDateFields, withTime?: boolean) => string;
}) {
  const trajectoryInputRows: { key: MeasurementType; label: string }[] = [
    { key: "egfr", label: "eGFR baseline" },
    { key: "acr", label: "Urine ACR / UACR" },
    { key: "systolic_bp", label: "Systolic blood pressure" },
    { key: "hba1c", label: "HbA1c" },
  ];

  return (
    <section
      aria-labelledby="input-readiness-heading"
      className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-xs sm:p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3.5">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-md bg-violet-100 text-violet-700">
              <Database className="h-3.5 w-3.5" />
            </span>
            <h3 id="input-readiness-heading" className="text-sm font-bold text-slate-900 tracking-tight">
              Clinical Input Readiness &amp; Temporal Alignment
            </h3>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Supporting biomarkers must be recorded at or prior to the selected eGFR baseline index date within the review window.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-medium text-slate-600">
            <Clock3 className="h-3 w-3 text-slate-400" />
            Lookback: {trajectoryEligibility?.freshness_threshold_days ?? 90} days default
          </span>
          <span
            className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-semibold ${
              trajectoryEligibilityLoading
                ? "bg-slate-100 text-slate-700 border border-slate-200"
                : trajectoryInputsAvailable
                ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                : "bg-amber-50 text-amber-800 border border-amber-200"
            }`}
          >
            {trajectoryEligibilityLoading ? (
              <>
                <LoaderCircle className="h-3.5 w-3.5 animate-spin text-slate-500" />
                Checking inputs…
              </>
            ) : trajectoryInputsAvailable ? (
              <>
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                Eligible for simulation
              </>
            ) : (
              <>
                <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
                Review required
              </>
            )}
          </span>
        </div>
      </div>

      {/* 4-Column Clinical Data Grid */}
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {/* 1. eGFR Baseline (Index Date Anchor) */}
        <div className="flex flex-col justify-between rounded-xl border border-violet-200/80 bg-violet-50/30 p-3.5 text-xs transition hover:border-violet-300">
          <div>
            <div className="flex items-center justify-between gap-1.5">
              <span className="font-semibold text-slate-700">eGFR Baseline</span>
              <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-semibold text-violet-800">
                Index Anchor
              </span>
            </div>
            {scenarioBase && trajectoryEligibility?.baseline ? (
              <div className="mt-2.5">
                <p className="font-mono text-base font-bold text-slate-900">
                  {trajectoryEligibility.baseline.value}{" "}
                  <span className="text-xs font-normal text-slate-500">
                    {trajectoryEligibility.baseline.unit}
                  </span>
                </p>
                <p className="mt-1 text-[11px] text-slate-600">
                  Observed: {formatObservationDate(trajectoryEligibility.baseline, true)}
                </p>
                <p className="mt-0.5 text-[11px] font-medium text-violet-700">
                  Baseline anchor (Index T = 0)
                </p>
              </div>
            ) : (
              <div className="mt-2.5">
                <p className="font-mono text-base font-semibold text-slate-400">—</p>
                <p className="mt-1 text-[11px] text-rose-700 font-medium">
                  No eGFR baseline selected
                </p>
              </div>
            )}
          </div>
          <div className="mt-3 border-t border-violet-100 pt-2 text-[10px] text-slate-500">
            Defines timeline start and index reference
          </div>
        </div>

        {/* Supporting Measurements (Urine ACR, Systolic BP, HbA1c) */}
        {trajectoryInputRows
          .filter(({ key }) => key !== "egfr")
          .map(({ key, label }) => {
            const inputStatus = trajectoryEligibility?.inputs[key];
            const isFresh = inputStatus?.freshness_status === "fresh";
            const isStale = inputStatus?.freshness_status === "stale";
            const isMissing = inputStatus?.freshness_status === "missing";
            const isAmbiguous = inputStatus?.freshness_status === "temporally_ambiguous";

            return (
              <div
                key={key}
                className={`flex flex-col justify-between rounded-xl border p-3.5 text-xs transition ${
                  isFresh
                    ? "border-slate-200 bg-white hover:border-slate-300"
                    : isStale || isAmbiguous
                    ? "border-amber-200 bg-amber-50/20 hover:border-amber-300"
                    : "border-rose-200 bg-rose-50/20 hover:border-rose-300"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between gap-1.5">
                    <span className="font-semibold text-slate-800">{label}</span>
                    {trajectoryEligibilityLoading ? (
                      <span className="text-[10px] text-slate-400">Checking…</span>
                    ) : inputStatus ? (
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                          isFresh
                            ? "bg-emerald-100 text-emerald-800"
                            : isStale
                            ? "bg-amber-100 text-amber-800"
                            : isAmbiguous
                            ? "bg-amber-100 text-amber-800"
                            : "bg-rose-100 text-rose-800"
                        }`}
                      >
                        {inputStatus.freshness_status.replaceAll("_", " ")}
                      </span>
                    ) : (
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500">
                        Pending
                      </span>
                    )}
                  </div>

                  {trajectoryEligibilityLoading ? (
                    <div className="mt-3 space-y-1.5 animate-pulse">
                      <div className="h-4 w-16 rounded bg-slate-200" />
                      <div className="h-3 w-28 rounded bg-slate-100" />
                    </div>
                  ) : inputStatus?.value != null ? (
                    <div className="mt-2.5">
                      <p className="font-mono text-base font-bold text-slate-900">
                        {inputStatus.value}{" "}
                        <span className="text-xs font-normal text-slate-500">
                          {inputStatus.unit}
                        </span>
                      </p>
                      <p className="mt-1 text-[11px] text-slate-600">
                        Date: {formatObservationDate(inputStatus, true)}
                      </p>
                      {inputStatus.age_days != null && (
                        <p className="mt-0.5 text-[11px] text-slate-500">
                          {inputStatus.age_days}{" "}
                          {inputStatus.age_precision === "exact_time" ? "days" : "calendar days"} before index
                          {inputStatus.source_sequence_number != null ? ` · seq ${inputStatus.source_sequence_number}` : ""}
                        </p>
                      )}
                    </div>
                  ) : (
                    <div className="mt-2.5">
                      <p className="font-mono text-base font-semibold text-slate-400">—</p>
                      <p className="mt-1 text-[11px] font-medium text-rose-700">
                        {inputStatus?.reason ?? "Observation not available in history."}
                      </p>
                    </div>
                  )}
                </div>

                {/* Status reasons if not fresh */}
                {inputStatus && !isFresh && inputStatus.reason && (
                  <div className="mt-3 rounded-lg border border-amber-200/80 bg-amber-50/70 p-2 text-[11px] leading-4 text-amber-900 font-medium">
                    {inputStatus.reason}
                  </div>
                )}
              </div>
            );
          })}
      </div>

      {/* Warnings and Blockers Bar */}
      <div className="mt-4 space-y-2 border-t border-slate-100 pt-3">
        <div className="flex items-start gap-2 rounded-xl bg-amber-50/70 p-3 text-xs leading-5 text-amber-900 border border-amber-200/60">
          <Info className="h-4 w-4 shrink-0 text-amber-600 mt-0.5" />
          <div>
            <p>
              Inputs must be no later than the selected eGFR date and within the {trajectoryEligibility?.freshness_threshold_days ?? 90}-day review window. Dates are not assumed simultaneous. Research use only; not a clinical forecast.
            </p>
          </div>
        </div>

        {trajectoryEligibility?.blockers && trajectoryEligibility.blockers.length > 0 && (
          <div className="rounded-xl border border-rose-200 bg-rose-50/60 p-3 space-y-1.5">
            <p className="text-xs font-bold text-rose-900 flex items-center gap-1.5">
              <AlertCircle className="h-4 w-4 text-rose-600 shrink-0" />
              Simulation Blockers ({trajectoryEligibility.blockers.length})
            </p>
            {trajectoryEligibility.blockers.map((blocker) => (
              <p key={blocker} className="text-xs font-medium text-rose-800 pl-5">
                • {blocker}
              </p>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

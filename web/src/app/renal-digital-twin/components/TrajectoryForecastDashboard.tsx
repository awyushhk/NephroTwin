"use client";

import { AlertTriangle, ChevronDown } from "lucide-react";
import type { ObservationDateFields, TrajectorySimulationResult } from "../types";
import { MechanisticTrajectoryPlot } from "./MechanisticTrajectoryPlot";
import { TrajectoryCategoryChanges } from "./TrajectoryCategoryChanges";
import { TrajectoryMilestones } from "./TrajectoryMilestones";

export function TrajectoryForecastDashboard({
  trajectoryResultForPatient,
  formatObservationDate,
  trajectoryNumber,
}: {
  trajectoryResultForPatient: TrajectorySimulationResult;
  formatObservationDate: (row: ObservationDateFields, withTime?: boolean) => string;
  trajectoryNumber: (value: number | null, digits?: number) => string;
}) {
  return (
    <div className="space-y-6">
      {/* Overview Banner */}
      <div className="rounded-2xl border border-violet-200/80 bg-gradient-to-r from-violet-50/60 via-slate-50/40 to-white p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-violet-700 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">
                Forecast Result
              </span>
              <span className="text-xs font-semibold text-violet-900">
                {trajectoryResultForPatient.method || "Mechanistic ODE"}
              </span>
            </div>
            <h3 className="mt-1 text-lg font-bold text-slate-900">
              Hypothetical trajectory · {trajectoryResultForPatient.horizon_years} years
            </h3>
            <p className="mt-0.5 text-xs text-slate-500">
              {trajectoryResultForPatient.point_count} simulated points · baseline date shown above
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-slate-600 font-medium">
              Index Date: {formatObservationDate(trajectoryResultForPatient.eligibility.baseline ?? { observed_date: trajectoryResultForPatient.index_date }, true)}
            </span>
            <span className="rounded-lg border border-violet-200 bg-violet-50 px-2.5 py-1 text-violet-800 font-semibold">
              Assumes u=0 (No treatment effect)
            </span>
          </div>
        </div>

        {/* Prominent Simulated Forecast Summary */}
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 border-t border-violet-100 pt-3">
          <div className="rounded-xl bg-white p-3 border border-slate-200/70">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Starting eGFR</p>
            <p className="mt-1 text-lg font-bold font-mono text-slate-900">
              {trajectoryNumber(trajectoryResultForPatient.analysis.egfr.starting)}{" "}
              <span className="text-xs font-normal text-slate-500">{trajectoryResultForPatient.analysis.egfr.unit}</span>
            </p>
          </div>
          <div className="rounded-xl bg-white p-3 border border-slate-200/70">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Final eGFR (Yr {trajectoryResultForPatient.horizon_years})</p>
            <p className="mt-1 text-lg font-bold font-mono text-violet-700">
              {trajectoryNumber(trajectoryResultForPatient.analysis.egfr.final)}{" "}
              <span className="text-xs font-normal text-slate-500">{trajectoryResultForPatient.analysis.egfr.unit}</span>
            </p>
          </div>
          <div className="rounded-xl bg-white p-3 border border-slate-200/70">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Starting UACR</p>
            <p className="mt-1 text-lg font-bold font-mono text-slate-900">
              {trajectoryNumber(trajectoryResultForPatient.analysis.uacr.starting)}{" "}
              <span className="text-xs font-normal text-slate-500">{trajectoryResultForPatient.analysis.uacr.unit}</span>
            </p>
          </div>
          <div className="rounded-xl bg-white p-3 border border-slate-200/70">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Final UACR (Yr {trajectoryResultForPatient.horizon_years})</p>
            <p className="mt-1 text-lg font-bold font-mono text-teal-700">
              {trajectoryNumber(trajectoryResultForPatient.analysis.uacr.final)}{" "}
              <span className="text-xs font-normal text-slate-500">{trajectoryResultForPatient.analysis.uacr.unit}</span>
            </p>
          </div>
        </div>
      </div>

      {/* eGFR and UACR Detailed Metric Summaries */}
      <div className="grid gap-4 sm:grid-cols-2">
        {([ ["eGFR", trajectoryResultForPatient.analysis.egfr], ["UACR", trajectoryResultForPatient.analysis.uacr] ] as const).map(([label, metric]) => {
          const isEgfr = label === "eGFR";
          return (
            <article
              key={label}
              className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-2xs transition hover:border-slate-300"
            >
              <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
                <div className="flex items-center gap-2">
                  <span
                    className="h-3 w-3 rounded-full"
                    style={{ backgroundColor: isEgfr ? "#6366f1" : "#0d9488" }}
                  />
                  <h3 className="font-bold text-slate-900 text-sm">Simulated {label}</h3>
                </div>
                <span className="font-mono text-xs font-semibold text-slate-600 bg-slate-50 rounded-lg px-2 py-0.5 border border-slate-200/80">
                  {metric.unit}
                </span>
              </div>

              <div className="mt-3 flex items-baseline justify-between">
                <p className="text-xs font-medium text-slate-500">Progression Trajectory</p>
                <p className="font-mono text-sm font-bold text-slate-900">
                  {trajectoryNumber(metric.starting)} → {trajectoryNumber(metric.final)} {metric.unit}
                </p>
              </div>

              <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                <div className="rounded-xl bg-slate-50/80 p-2.5 border border-slate-100">
                  <p className="text-[10px] uppercase font-semibold text-slate-500">Absolute Change</p>
                  <p className="mt-1 font-mono text-sm font-bold text-slate-800">
                    {metric.absolute_change == null ? "Unavailable" : `${metric.absolute_change >= 0 ? "+" : ""}${trajectoryNumber(metric.absolute_change)} ${metric.unit}`}
                    {metric.percent_change != null && (
                      <span className="ml-1 text-[11px] font-medium text-slate-500">
                        ({metric.percent_change >= 0 ? "+" : ""}{trajectoryNumber(metric.percent_change, 1)}%)
                      </span>
                    )}
                  </p>
                </div>

                <div className="rounded-xl bg-slate-50/80 p-2.5 border border-slate-100">
                  <p className="text-[10px] uppercase font-semibold text-slate-500">Avg Annualized</p>
                  <p className="mt-1 font-mono text-sm font-bold text-slate-800">
                    {metric.average_annualized_change == null ? "Unavailable" : `${metric.average_annualized_change >= 0 ? "+" : ""}${trajectoryNumber(metric.average_annualized_change)} ${metric.unit}/year`}
                  </p>
                </div>
              </div>

              <div className="mt-3 flex items-center justify-between text-[11px] text-slate-500 border-t border-slate-100 pt-2.5">
                <span>{metric.valid_points} points over {trajectoryNumber(metric.elapsed_years)} years</span>
                <span className="font-mono font-medium text-slate-600">dt = {(Number(trajectoryResultForPatient.horizon_years) / Math.max(1, metric.valid_points - 1)).toFixed(3)}y</span>
              </div>
            </article>
          );
        })}
      </div>

      {/* Visualizations and Categorization Grid */}
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(300px,0.9fr)]">
        {/* Charts Column */}
        <div className="space-y-6">
          <MechanisticTrajectoryPlot points={trajectoryResultForPatient.trajectory} metric="egfr" horizon={trajectoryResultForPatient.horizon_years} analysis={trajectoryResultForPatient.analysis} />
          <MechanisticTrajectoryPlot points={trajectoryResultForPatient.trajectory} metric="uacr" horizon={trajectoryResultForPatient.horizon_years} analysis={trajectoryResultForPatient.analysis} />
        </div>

        {/* Analytics Sidebar */}
        <div className="space-y-6">
          <TrajectoryCategoryChanges trajectoryResult={trajectoryResultForPatient} />
          <TrajectoryMilestones trajectoryResult={trajectoryResultForPatient} />
        </div>
      </div>

      {/* Technical Details, Limitations and Warnings */}
      <div className="space-y-3 pt-2">
        <details className="group rounded-2xl border border-slate-200 bg-slate-50/60 p-4 text-xs text-slate-600 transition">
          <summary className="cursor-pointer font-bold text-slate-800 flex items-center justify-between select-none">
            <span>Calculation and model limitations</span>
            <ChevronDown className="h-4 w-4 text-slate-500 transition group-open:rotate-180" />
          </summary>
          <div className="mt-3 space-y-2 border-t border-slate-200/80 pt-3 text-xs leading-5">
            <p className="font-semibold text-slate-800">
              {trajectoryResultForPatient.analysis.calculation} {trajectoryResultForPatient.analysis.crossing_method}
            </p>
            {trajectoryResultForPatient.limitations.map((limitation) => (
              <p key={limitation} className="text-slate-600">
                • {limitation}
              </p>
            ))}
            <div className="rounded-xl border border-violet-100 bg-violet-50/50 p-3 text-violet-900 text-[11px] leading-4">
              Bundled defaults are used. Parameters are not fitted to the individual patient. Assumes no active treatment effect (u=0). Research simulation only; results are not saved as patient observations.
            </div>
          </div>
        </details>

        {trajectoryResultForPatient.warnings.map((warning) => (
          <div
            key={warning}
            className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900 flex items-start gap-2"
          >
            <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
            <span>{warning}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

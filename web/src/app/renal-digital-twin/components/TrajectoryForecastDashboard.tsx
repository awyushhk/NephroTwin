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
      {/* Overview Banner with Unified Forecast Summary */}
      <div className="rounded-2xl border border-violet-200/80 bg-gradient-to-r from-violet-50/50 via-slate-50/30 to-white p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-violet-100/80 pb-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-violet-700 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">
                Forecast Result
              </span>
              <h3 className="text-base font-bold text-slate-900">
                Hypothetical Trajectory · {trajectoryResultForPatient.horizon_years} Years
              </h3>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              Index baseline: {formatObservationDate(trajectoryResultForPatient.eligibility.baseline ?? { observed_date: trajectoryResultForPatient.index_date }, true)}
            </p>
          </div>

          <span className="rounded-lg border border-violet-200 bg-violet-50 px-2.5 py-1 text-xs font-semibold text-violet-800">
            No treatment intervention
          </span>
        </div>

        {/* Consolidated Metric Cards (No repetition!) */}
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          {/* Simulated eGFR */}
          <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-2xs">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-indigo-600" />
                <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wide">Simulated eGFR</h4>
              </div>
              <span className="font-mono text-xs font-semibold text-slate-500">
                {trajectoryResultForPatient.analysis.egfr.unit}
              </span>
            </div>

            <div className="mt-3 grid grid-cols-3 gap-2">
              <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-100">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  Baseline → Yr {trajectoryResultForPatient.horizon_years}
                </p>
                <p className="mt-1 font-mono text-sm font-bold text-slate-900">
                  {trajectoryNumber(trajectoryResultForPatient.analysis.egfr.starting)} →{" "}
                  <span className="text-violet-700 font-extrabold">
                    {trajectoryNumber(trajectoryResultForPatient.analysis.egfr.final)}
                  </span>
                </p>
              </div>

              <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-100">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Total Change</p>
                <p className="mt-1 font-mono text-sm font-bold text-slate-900">
                  {trajectoryResultForPatient.analysis.egfr.absolute_change == null
                    ? "—"
                    : `${trajectoryResultForPatient.analysis.egfr.absolute_change >= 0 ? "+" : ""}${trajectoryNumber(trajectoryResultForPatient.analysis.egfr.absolute_change)}`}
                  {trajectoryResultForPatient.analysis.egfr.percent_change != null && (
                    <span className="ml-1 text-[11px] font-normal text-slate-500">
                      ({trajectoryResultForPatient.analysis.egfr.percent_change >= 0 ? "+" : ""}{trajectoryNumber(trajectoryResultForPatient.analysis.egfr.percent_change, 1)}%)
                    </span>
                  )}
                </p>
              </div>

              <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-100">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Annual Rate</p>
                <p className="mt-1 font-mono text-sm font-bold text-slate-900">
                  {trajectoryResultForPatient.analysis.egfr.average_annualized_change == null
                    ? "—"
                    : `${trajectoryResultForPatient.analysis.egfr.average_annualized_change >= 0 ? "+" : ""}${trajectoryNumber(trajectoryResultForPatient.analysis.egfr.average_annualized_change)}/yr`}
                </p>
              </div>
            </div>
          </div>

          {/* Simulated UACR */}
          <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-2xs">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-teal-600" />
                <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wide">Simulated UACR</h4>
              </div>
              <span className="font-mono text-xs font-semibold text-slate-500">
                {trajectoryResultForPatient.analysis.uacr.unit}
              </span>
            </div>

            <div className="mt-3 grid grid-cols-3 gap-2">
              <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-100">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  Baseline → Yr {trajectoryResultForPatient.horizon_years}
                </p>
                <p className="mt-1 font-mono text-sm font-bold text-slate-900">
                  {trajectoryNumber(trajectoryResultForPatient.analysis.uacr.starting)} →{" "}
                  <span className="text-teal-700 font-extrabold">
                    {trajectoryNumber(trajectoryResultForPatient.analysis.uacr.final)}
                  </span>
                </p>
              </div>

              <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-100">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Total Change</p>
                <p className="mt-1 font-mono text-sm font-bold text-slate-900">
                  {trajectoryResultForPatient.analysis.uacr.absolute_change == null
                    ? "—"
                    : `${trajectoryResultForPatient.analysis.uacr.absolute_change >= 0 ? "+" : ""}${trajectoryNumber(trajectoryResultForPatient.analysis.uacr.absolute_change)}`}
                  {trajectoryResultForPatient.analysis.uacr.percent_change != null && (
                    <span className="ml-1 text-[11px] font-normal text-slate-500">
                      ({trajectoryResultForPatient.analysis.uacr.percent_change >= 0 ? "+" : ""}{trajectoryNumber(trajectoryResultForPatient.analysis.uacr.percent_change, 1)}%)
                    </span>
                  )}
                </p>
              </div>

              <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-100">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Annual Rate</p>
                <p className="mt-1 font-mono text-sm font-bold text-slate-900">
                  {trajectoryResultForPatient.analysis.uacr.average_annualized_change == null
                    ? "—"
                    : `${trajectoryResultForPatient.analysis.uacr.average_annualized_change >= 0 ? "+" : ""}${trajectoryNumber(trajectoryResultForPatient.analysis.uacr.average_annualized_change)}/yr`}
                </p>
              </div>
            </div>
          </div>
        </div>
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

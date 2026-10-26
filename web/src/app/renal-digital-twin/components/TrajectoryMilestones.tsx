"use client";

import type { TrajectoryMilestone, TrajectorySimulationResult } from "../types";

export function milestoneDescription(milestone: TrajectoryMilestone | undefined) {
  if (!milestone) return "Unavailable";
  if (milestone.status === "crossed") {
    return milestone.time_years != null ? `Reached at year ${milestone.time_years.toFixed(2)}` : "Reached";
  }
  if (milestone.status === "below_at_baseline") return "Below at baseline";
  if (milestone.status === "at_threshold_at_baseline") return "At threshold at baseline";
  return "Not crossed in horizon";
}

export function TrajectoryMilestones({
  trajectoryResult,
}: {
  trajectoryResult: TrajectorySimulationResult;
}) {
  const { analysis } = trajectoryResult;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-2xs sm:p-5">
      <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
        <h3 className="text-sm font-bold text-slate-900 tracking-tight">eGFR milestones</h3>
        <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">
          Interpolated Thresholds
        </span>
      </div>

      <ul className="mt-3 space-y-2.5 text-xs">
        {["60", "45", "30", "15"].map((threshold) => {
          const milestone = analysis.egfr.thresholds?.[threshold];
          const isCrossed = milestone?.status === "crossed";
          return (
            <li
              key={threshold}
              className="flex items-center justify-between gap-2 rounded-xl border border-slate-200/80 bg-slate-50/50 p-2.5 transition hover:border-slate-300"
            >
              <div>
                <span className="font-bold text-slate-900">eGFR {threshold}</span>
                <span className="ml-1 text-[11px] text-slate-500">mL/min/1.73m²</span>
              </div>
              <span
                className={`rounded-lg px-2.5 py-1 font-mono text-[11px] font-semibold text-right ${
                  isCrossed
                    ? "bg-violet-100 text-violet-800 border border-violet-200"
                    : milestone?.status === "below_at_baseline" || milestone?.status === "at_threshold_at_baseline"
                    ? "bg-amber-100 text-amber-800 border border-amber-200"
                    : "bg-slate-100 text-slate-600 border border-slate-200"
                }`}
              >
                {milestoneDescription(milestone)}
              </span>
            </li>
          );
        })}

        <li className="flex items-center justify-between gap-2 rounded-xl border border-slate-200/80 bg-slate-50/50 p-2.5 transition hover:border-slate-300 border-t border-slate-200">
          <div>
            <span className="font-bold text-slate-900">20% decline</span>
            <span className="ml-1 text-[11px] text-slate-500">from baseline</span>
          </div>
          <span
            className={`rounded-lg px-2.5 py-1 font-mono text-[11px] font-semibold text-right ${
              analysis.egfr.decline_20_percent?.status === "crossed"
                ? "bg-violet-100 text-violet-800 border border-violet-200"
                : "bg-slate-100 text-slate-600 border border-slate-200"
            }`}
          >
            {milestoneDescription(analysis.egfr.decline_20_percent)}
          </span>
        </li>
      </ul>

      <p className="mt-3.5 text-[11px] leading-4 text-slate-500">
        Threshold times between points are linearly interpolated; nothing is extrapolated. eGFR &lt;15 is a modeled filtration threshold, not a treatment or dialysis prediction.
      </p>
    </section>
  );
}

"use client";

import type { TrajectoryMilestone, TrajectorySimulationResult } from "../types";

export function milestoneDescription(milestone: TrajectoryMilestone | undefined) {
  if (!milestone) return "Unavailable";
  if (milestone.status === "crossed") return milestone.time_years != null ? `Year ${milestone.time_years.toFixed(2)}` : "Crossed";
  if (milestone.status === "below_at_baseline") return "Below at baseline";
  if (milestone.status === "at_threshold_at_baseline") return "At baseline";
  if (milestone.status === "unavailable") return "Unavailable";
  return "Not crossed in horizon";
}

export function TrajectoryMilestones({ trajectoryResult }: { trajectoryResult: TrajectorySimulationResult }) {
  const scenarios = [trajectoryResult.scenarios.no_treatment, trajectoryResult.scenarios.hypothetical_treatment];
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-2xs sm:p-5">
      <div className="border-b border-slate-100 pb-2.5">
        <h3 className="text-sm font-bold text-slate-900 tracking-tight">eGFR milestones</h3>
        <p className="text-[11px] text-slate-500">Calculated independently from each returned trajectory</p>
      </div>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[320px] text-xs">
          <thead><tr className="border-b border-slate-100 text-left text-[10px] uppercase tracking-wide text-slate-500"><th className="py-2 pr-2">Threshold</th><th className="px-2 py-2">No treatment</th><th className="px-2 py-2">SGLT2i-informed scenario</th></tr></thead>
          <tbody>
            {["60", "45", "30", "15", "decline_20_percent"].map((key) => {
              const title = key === "decline_20_percent" ? "20% decline" : `eGFR ${key}`;
              const noTreatmentMilestone = key === "decline_20_percent" ? scenarios[0].analysis.egfr.decline_20_percent : scenarios[0].analysis.egfr.thresholds?.[key];
              const treatmentMilestone = key === "decline_20_percent" ? scenarios[1].analysis.egfr.decline_20_percent : scenarios[1].analysis.egfr.thresholds?.[key];
              return <tr key={key} className="border-b border-slate-50 last:border-0">
                <th className="py-2 pr-2 text-left font-semibold text-slate-800">{title}</th>
                {[noTreatmentMilestone, treatmentMilestone].map((milestone, index) => <td key={index} className="px-2 py-2 font-mono text-[11px] text-slate-700">{milestoneDescription(milestone)}</td>)}
              </tr>;
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-[11px] leading-4 text-slate-500">Crossings between points use linear interpolation; none are extrapolated. eGFR below 15 is a modeled filtration threshold, not a dialysis or treatment prediction.</p>
    </section>
  );
}

"use client";

import { Info } from "lucide-react";
import type { TrajectorySimulationResult } from "../types";

export function TrajectoryCategoryChanges({
  trajectoryResult,
}: {
  trajectoryResult: TrajectorySimulationResult;
}) {
  const { analysis, horizon_years } = trajectoryResult;
  const { categories } = analysis;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-2xs sm:p-5">
      <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
        <div>
          <h3 className="text-sm font-bold text-slate-900 tracking-tight">Simulated category changes</h3>
          <p className="text-[11px] text-slate-500">KDIGO classification progression</p>
        </div>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600">
          KDIGO 2024
        </span>
      </div>
      <p className="mt-2 text-xs text-slate-500">Not a diagnosis or confirmed disease progression.</p>

      <div className="mt-3.5 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3">
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Start (Year 0)</p>
          <p className="mt-1 font-mono text-sm font-bold text-slate-900">
            {categories.starting ? `${categories.starting.gfr} · ${categories.starting.albuminuria}` : "Unavailable"}
          </p>
        </div>
        <div className="rounded-xl border border-violet-200/80 bg-violet-50/40 p-3">
          <p className="text-[10px] font-bold uppercase tracking-wider text-violet-800">End (Year {horizon_years})</p>
          <p className="mt-1 font-mono text-sm font-bold text-violet-950">
            {categories.final ? `${categories.final.gfr} · ${categories.final.albuminuria}` : "Unavailable"}
          </p>
        </div>
      </div>

      {categories.transitions.length ? (
        <div className="mt-3.5 border-t border-slate-100 pt-3">
          <p className="text-[11px] font-bold text-slate-700 uppercase tracking-wide mb-2">
            Transition Milestones ({categories.transitions.length})
          </p>
          <ol className="max-h-48 space-y-2 overflow-y-auto pr-1 text-xs">
            {categories.transitions.map((item, index) => (
              <li
                key={`${item.year}-${index}`}
                className="flex items-center justify-between gap-2 rounded-lg border border-slate-200/70 bg-slate-50/60 p-2"
              >
                <span className="font-mono font-bold text-violet-900">Year {item.year.toFixed(2)}</span>
                <span className="font-medium text-slate-800">
                  {item.gfr_category} · {item.albuminuria_category}
                </span>
                <span className="font-mono text-[11px] text-slate-500 hidden sm:inline">
                  ({item.egfr.toFixed(0)} mL/min)
                </span>
              </li>
            ))}
          </ol>
        </div>
      ) : (
        <p className="mt-3.5 border-t border-slate-100 pt-3 text-xs text-slate-500">
          No category transitions in this horizon.
        </p>
      )}

      {/* Category Matrix Disclosure */}
      <details className="group relative mt-3.5 border-t border-slate-100 pt-3">
        <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-violet-800 hover:bg-violet-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-600">
          <Info className="h-4 w-4" />
          View category matrix
        </summary>
        <div className="absolute right-0 z-30 mt-2 w-[min(44rem,calc(100vw-3rem))] rounded-2xl border border-slate-200 bg-white p-4 shadow-xl">
          <div className="mb-2.5 flex items-center justify-between border-b border-slate-100 pb-2">
            <h4 className="text-xs font-bold text-slate-900">KDIGO 2024 Reference Matrix</h4>
            <span className="text-[10px] text-slate-500">Reference categories applied to simulated values. This matrix is not a diagnosis or risk score.</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[440px] border-collapse text-center text-[11px]">
              <caption className="sr-only">Combined GFR and albuminuria reference categories</caption>
              <thead>
                <tr className="text-slate-700 bg-slate-50/80 border-b border-slate-200">
                  <th scope="col" className="p-2 text-left font-bold">GFR / UACR</th>
                  <th scope="col" className="p-2 font-bold">A1<br /><span className="font-normal text-slate-500">&lt;30 mg/g</span></th>
                  <th scope="col" className="p-2 font-bold">A2<br /><span className="font-normal text-slate-500">30–300 mg/g, inclusive</span></th>
                  <th scope="col" className="p-2 font-bold">A3<br /><span className="font-normal text-slate-500">&gt;300 mg/g</span></th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["G1", "≥90"],
                  ["G2", "60–<90"],
                  ["G3a", "45–<60"],
                  ["G3b", "30–<45"],
                  ["G4", "15–<30"],
                  ["G5", "<15"],
                ].map(([g, range]) => {
                  return (
                    <tr key={g} className="border-t border-slate-200">
                      <th scope="row" className="p-2 text-left font-semibold text-slate-700 bg-slate-50/40">
                        {g}<span className="ml-1 font-normal text-slate-500">{range}</span>
                      </th>
                      {["A1", "A2", "A3"].map((a) => {
                        const isStart = categories.starting?.gfr === g && categories.starting?.albuminuria === a;
                        const isEnd = categories.final?.gfr === g && categories.final?.albuminuria === a;
                        return (
                          <td key={a} className="p-1.5">
                            <span
                              className={`inline-block w-full rounded-md px-2 py-1 font-mono font-medium text-[11px] border transition ${
                                isStart && isEnd
                                  ? "bg-violet-700 text-white border-violet-800 font-bold shadow-xs"
                                  : isStart
                                  ? "bg-emerald-100 text-emerald-900 border-emerald-300 font-bold"
                                  : isEnd
                                  ? "bg-violet-100 text-violet-900 border-violet-300 font-bold"
                                  : "bg-white text-slate-700 border-slate-200"
                              }`}
                            >
                              {g} · {a}
                              {isStart && !isEnd && " (Start)"}
                              {isEnd && !isStart && " (End)"}
                              {isStart && isEnd && " (Start/End)"}
                            </span>
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </details>
    </section>
  );
}

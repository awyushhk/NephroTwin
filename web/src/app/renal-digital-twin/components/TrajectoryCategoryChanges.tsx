"use client";

import { Info, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { TrajectorySimulationResult } from "../types";

type CellData = { risk: 0 | 1 | 2 | 3 | 4; action: string; freq: number };

const MATRIX: Record<string, [CellData, CellData, CellData]> = {
  G1:  [{ risk: 0, action: "Screen",        freq: 1 }, { risk: 1, action: "Treat",        freq: 1 }, { risk: 2, action: "Treat & Refer", freq: 3 }],
  G2:  [{ risk: 0, action: "Screen",        freq: 1 }, { risk: 1, action: "Treat",        freq: 1 }, { risk: 2, action: "Treat & Refer", freq: 3 }],
  G3a: [{ risk: 1, action: "Treat",         freq: 1 }, { risk: 2, action: "Treat",        freq: 2 }, { risk: 3, action: "Treat & Refer", freq: 3 }],
  G3b: [{ risk: 2, action: "Treat",         freq: 2 }, { risk: 3, action: "Treat & Refer",freq: 3 }, { risk: 3, action: "Treat & Refer", freq: 3 }],
  G4:  [{ risk: 3, action: "Treat & Refer", freq: 3 }, { risk: 3, action: "Treat & Refer",freq: 3 }, { risk: 4, action: "Treat & Refer", freq: 4 }],
  G5:  [{ risk: 4, action: "Treat & Refer", freq: 4 }, { risk: 4, action: "Treat & Refer",freq: 4 }, { risk: 4, action: "Treat & Refer", freq: 4 }],
};

const RISK_BG: Record<number, string> = {
  0: "bg-emerald-500 text-white",
  1: "bg-amber-300 text-amber-950",
  2: "bg-amber-500 text-white",
  3: "bg-[#f05a68] text-white",
  4: "bg-rose-600 text-white",
};
const RISK_SWATCH: Record<number, string> = {
  0: "bg-emerald-500",
  1: "bg-amber-300",
  2: "bg-amber-500",
  3: "bg-[#f05a68]",
  4: "bg-rose-600",
};

const GFR_ROWS = [
  { g: "G1",  range: "≥90",   desc: "Normal or high" },
  { g: "G2",  range: "60-89", desc: "Mildly decreased" },
  { g: "G3a", range: "45-59", desc: "Mildly-mod. decreased" },
  { g: "G3b", range: "30-44", desc: "Mod.-severely decreased" },
  { g: "G4",  range: "15-29", desc: "Severely decreased" },
  { g: "G5",  range: "<15",   desc: "Kidney failure" },
];

const ALB_COLS = [
  { a: "A1", desc: "Normal to mildly incr.", range: "<30 mg/g" },
  { a: "A2", desc: "Moderately incr.",       range: "30–299 mg/g" },
  { a: "A3", desc: "Severely incr.",         range: "≥300 mg/g" },
];

export function TrajectoryCategoryChanges({
  trajectoryResult,
}: {
  trajectoryResult: TrajectorySimulationResult;
}) {
  const { analysis, horizon_years } = trajectoryResult;
  const { categories } = analysis;
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };

    document.addEventListener("mousedown", handleClickOutside);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

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

      {/* Trigger & Popover Anchor */}
      <div className="relative mt-3.5 border-t border-slate-100 pt-3" ref={containerRef}>
        <button
          type="button"
          onClick={() => setOpen((prev) => !prev)}
          className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-600 ${
            open
              ? "bg-violet-100 text-violet-900 shadow-2xs"
              : "text-violet-800 hover:bg-violet-50"
          }`}
          aria-expanded={open}
        >
          <Info className="h-3.5 w-3.5" />
          View category matrix
        </button>

        {/* Popover anchored right below the button */}
        {open && (
          <div
            className="absolute left-0 sm:left-auto sm:right-0 top-full z-40 mt-1.5 w-[530px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-slate-200/95 bg-white shadow-2xl animate-in fade-in slide-in-from-top-1 duration-150"
            role="region"
            aria-label="KDIGO 2024 Risk Matrix"
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/80 px-3.5 py-2">
              <div className="flex items-center gap-2">
                <h4 className="text-xs font-bold text-slate-900">KDIGO 2024 Risk Matrix</h4>
                <span className="text-[10.5px] text-slate-500 hidden sm:inline">
                  · Monitoring &amp; Referral Guide
                </span>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-md p-1 text-slate-400 hover:bg-slate-200/70 hover:text-slate-700 transition"
                aria-label="Close matrix"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Table */}
            <div className="overflow-x-auto p-2.5">
              <table className="w-full min-w-[490px] border-collapse">
                <caption className="sr-only">KDIGO 2024 combined GFR and albuminuria risk matrix</caption>
                <thead>
                  {/* Albuminuria super-header */}
                  <tr>
                    <th colSpan={2} className="border-b border-r border-slate-200 bg-slate-100/70 px-2 py-1.5 text-left align-bottom">
                      <span className="text-[9.5px] font-bold uppercase tracking-wider text-slate-600">GFR (mL/min)</span>
                    </th>
                    <th colSpan={3} className="border-b border-slate-200 bg-slate-100/70 px-2 py-1.5 text-center">
                      <span className="text-[10.5px] font-bold uppercase tracking-wide text-slate-700">Persistent albuminuria categories</span>
                    </th>
                  </tr>
                  {/* Column sub-headers */}
                  <tr className="border-b-2 border-slate-200">
                    <th colSpan={2} className="border-r border-slate-200 bg-slate-50/50 p-1" />
                    {ALB_COLS.map((col) => (
                      <th key={col.a} scope="col" className="border-l border-slate-200 bg-sky-50/50 px-2 py-1.5 text-center">
                        <p className="text-[12px] font-bold text-slate-900">{col.a}</p>
                        <p className="text-[9.5px] font-semibold text-slate-700 leading-tight">{col.desc}</p>
                        <p className="text-[9px] font-mono text-slate-500 font-medium">{col.range}</p>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {GFR_ROWS.map(({ g, range, desc }) => {
                    const rowCells = MATRIX[g];
                    return (
                      <tr key={g} className="border-b border-slate-100 last:border-b-0">
                        {/* Stage & Range */}
                        <th scope="row" className="border-r border-slate-200 bg-slate-50/80 px-2 py-1 text-left align-middle whitespace-nowrap">
                          <span className="font-bold text-slate-900 text-[11px]">{g}</span>
                          <span className="ml-1.5 text-[9.5px] font-mono font-medium text-slate-600">{range}</span>
                        </th>
                        {/* Description */}
                        <td className="border-r border-slate-200 bg-slate-50/40 px-2 py-1 text-left align-middle text-[9px] font-medium text-slate-600 max-w-[95px] leading-snug">
                          {desc}
                        </td>
                        {/* Risk cells */}
                        {rowCells?.map((cell, colIdx) => {
                          const colA = ALB_COLS[colIdx]!.a;
                          const isStart = categories.starting?.gfr === g && categories.starting?.albuminuria === colA;
                          const isEnd   = categories.final?.gfr   === g && categories.final?.albuminuria   === colA;
                          const freq    = cell.freq >= 4 ? "4+" : String(cell.freq);
                          return (
                            <td key={colA} className="border-l border-white/70 p-0.5">
                              <div
                                className={`relative flex flex-col items-center justify-center rounded min-h-[35px] py-1 px-1 text-center ${RISK_BG[cell.risk]} ${
                                  (isStart || isEnd)
                                    ? `ring-2 ring-offset-1 z-10 ${isStart && isEnd ? "ring-violet-700 shadow-sm" : isStart ? "ring-emerald-800 shadow-sm" : "ring-violet-700 shadow-sm"}`
                                    : ""
                                }`}
                              >
                                {isStart && !isEnd && (
                                  <span className="absolute top-0.5 right-0.5 rounded bg-white px-1 py-0 text-[7px] font-black uppercase text-emerald-900 shadow-2xs border border-emerald-300 whitespace-nowrap">
                                    Start
                                  </span>
                                )}
                                {isEnd && !isStart && (
                                  <span className="absolute top-0.5 right-0.5 rounded bg-white px-1 py-0 text-[7px] font-black uppercase text-violet-900 shadow-2xs border border-violet-300 whitespace-nowrap">
                                    End
                                  </span>
                                )}
                                {isStart && isEnd && (
                                  <span className="absolute top-0.5 right-0.5 rounded bg-white px-1 py-0 text-[7px] font-black uppercase text-violet-900 shadow-2xs border border-violet-400 whitespace-nowrap">
                                    Start/End
                                  </span>
                                )}
                                <span className="text-[10px] font-bold leading-tight">{cell.action}</span>
                                <span className="text-[8.5px] font-semibold opacity-95 leading-none mt-0.5">{freq}× / yr</span>
                              </div>
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Compact Legend & footnote */}
            <div className="border-t border-slate-200 bg-slate-50/70 px-3.5 py-1.5">
              <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  {[
                    { risk: 0, label: "Low risk" },
                    { risk: 1, label: "Moderate" },
                    { risk: 2, label: "High" },
                    { risk: 3, label: "Very high" },
                    { risk: 4, label: "Very high (4+ checks)" },
                  ].map(({ risk, label }) => (
                    <div key={risk} className="flex items-center gap-1.5">
                      <span className={`h-2.5 w-2.5 shrink-0 rounded-xs ${RISK_SWATCH[risk]}`} />
                      <span className="text-[9.5px] font-semibold text-slate-700">{label}</span>
                    </div>
                  ))}
                </div>
                <span className="text-[8.5px] font-medium text-slate-500">Freq = visits/yr</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

"use client";

import { useState } from "react";
import type { TrajectoryScenarioResult } from "../types";

type PlotSeries = Pick<TrajectoryScenarioResult, "label" | "trajectory" | "analysis"> & {
  color: string;
  dash?: string;
};

export function MechanisticTrajectoryPlot({
  series,
  metric,
  horizon,
}: {
  series: PlotSeries[];
  metric: "egfr" | "uacr";
  horizon: number;
}) {
  const [hoveredPoint, setHoveredPoint] = useState<{
    label: string; year: number; value: number; x: number; y: number; color: string;
  } | null>(null);
  const label = metric === "egfr" ? "eGFR" : "UACR";
  const fullName = metric === "egfr" ? "Glomerular Filtration Rate" : "Urine Albumin-to-Creatinine Ratio";
  const unit = metric === "egfr" ? "mL/min/1.73m²" : "mg/g";
  const allValues = series.flatMap((scenario) => scenario.trajectory.map((point) => point[metric]));
  const rawMin = Math.min(...allValues, ...(metric === "egfr" ? [15] : []));
  const rawMax = Math.max(...allValues);
  const padding = Math.max((rawMax - rawMin) * 0.08, Math.abs(rawMax) * 0.03, 1);
  const low = Math.max(0, rawMin - padding);
  const high = rawMax + padding;
  const left = 84;
  const right = 820;
  const top = 32;
  const bottom = 296;
  const x = (year: number) => left + (year / horizon) * (right - left);
  const y = (value: number) => bottom - ((value - low) / (high - low)) * (bottom - top);
  const yTicks = Array.from({ length: 5 }, (_, index) => low + ((high - low) * index) / 4);
  const xTicks = Array.from({ length: 6 }, (_, index) => (horizon * index) / 5);
  const showsThreshold = metric === "egfr" && low <= 15 && high >= 15;
  const tooltipX = hoveredPoint ? Math.max(left, Math.min(right - 190, hoveredPoint.x - 95)) : 0;
  const tooltipY = hoveredPoint ? Math.max(top, Math.min(bottom - 64, hoveredPoint.y - 74)) : 0;

  return (
    <figure className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-xs sm:p-5">
      <figcaption className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
        <div>
          <h4 className="text-sm font-bold text-slate-900 tracking-tight">
            Simulated {label} <span className="text-xs font-normal text-slate-500 hidden sm:inline">({fullName})</span>
          </h4>
          <p className="text-[11px] text-slate-500">{horizon}-year hypothetical comparison · {series[0]?.trajectory.length ?? 0} model time points</p>
        </div>
        <span className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-[11px] font-medium text-slate-700">{unit}</span>
      </figcaption>

      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-[11px] text-slate-700" aria-label={`${label} scenario legend`}>
        {series.map((scenario) => (
          <span key={scenario.label} className="inline-flex items-center gap-2 font-medium">
            <svg width="28" height="10" aria-hidden="true"><line x1="1" x2="27" y1="5" y2="5" stroke={scenario.color} strokeWidth="2.5" strokeDasharray={scenario.dash} /></svg>
            {scenario.label}
          </span>
        ))}
        {showsThreshold && <span className="inline-flex items-center gap-1.5 text-amber-900"><span className="inline-block w-4 border-b-2 border-dashed border-amber-600" />eGFR 15 reference</span>}
      </div>

      <div className="w-full overflow-x-auto rounded-xl border border-slate-100 bg-slate-50/40 p-1">
        <svg viewBox="0 0 860 370" className="h-[300px] min-w-[680px] w-full sm:h-[360px]" role="img" aria-label={`${series.map((scenario) => scenario.label).join(" and ")} ${label} trajectories over ${horizon} years`}>
          {yTicks.map((tick, index) => (
            <g key={`y-${index}`}>
              <line x1={left} x2={right} y1={y(tick)} y2={y(tick)} stroke="#e2e8f0" strokeDasharray="3 4" />
              <text x={left - 12} y={y(tick) + 4} textAnchor="end" fill="#64748b" fontSize="11" fontFamily="monospace">{tick.toFixed(tick >= 100 ? 0 : 1)}</text>
            </g>
          ))}
          {xTicks.map((tick, index) => (
            <g key={`x-${index}`}>
              <line x1={x(tick)} x2={x(tick)} y1={top} y2={bottom} stroke="#f1f5f9" />
              <text x={x(tick)} y={bottom + 20} textAnchor="middle" fill="#64748b" fontSize="11" fontFamily="monospace">Yr {tick.toFixed(tick % 1 ? 1 : 0)}</text>
            </g>
          ))}

          {showsThreshold && <g>
            <line x1={left} x2={right} y1={y(15)} y2={y(15)} stroke="#d97706" strokeDasharray="6 4" strokeWidth="1.5" />
            <text x={right - 4} y={y(15) - 7} textAnchor="end" fill="#92400e" fontSize="10" fontWeight="600">eGFR 15 reference threshold</text>
          </g>}

          <line x1={left} x2={right} y1={bottom} y2={bottom} stroke="#94a3b8" strokeWidth="1.5" />
          <line x1={left} x2={left} y1={top} y2={bottom} stroke="#94a3b8" strokeWidth="1.5" />

          {series.map((scenario) => {
            const points = scenario.trajectory;
            const path = points.map((point) => `${x(point.year)},${y(point[metric])}`).join(" ");
            const thresholds = metric === "egfr"
              ? Object.entries(scenario.analysis.egfr.thresholds ?? {}).flatMap(([threshold, milestone]) => milestone.status === "crossed" && milestone.time_years != null
                ? [{ threshold: Number(threshold), year: milestone.time_years }]
                : [])
              : [];
            const transitions = scenario.analysis.categories.transitions;
            return <g key={scenario.label}>
              <polyline points={path} fill="none" stroke={scenario.color} strokeWidth="3" strokeDasharray={scenario.dash} strokeLinejoin="round" strokeLinecap="round" />
              {points.map((point, index) => {
                const cx = x(point.year);
                const cy = y(point[metric]);
                const keyboardTarget = index === 0 || index === points.length - 1 || index % 20 === 0;
                const showTooltip = () => setHoveredPoint({ label: scenario.label, year: point.year, value: point[metric], x: cx, y: cy, color: scenario.color });
                return <g key={`${scenario.label}-point-${index}`}>
                  <circle cx={cx} cy={cy} r="2.2" fill={scenario.color} pointerEvents="none" />
                  <circle cx={cx} cy={cy} r="7" fill="transparent" className="cursor-crosshair" onPointerEnter={showTooltip} onPointerMove={showTooltip} onPointerLeave={() => setHoveredPoint(null)} onFocus={showTooltip} onBlur={() => setHoveredPoint(null)} tabIndex={keyboardTarget ? 0 : -1} role={keyboardTarget ? "img" : undefined} aria-hidden={!keyboardTarget} aria-label={keyboardTarget ? `${scenario.label}, year ${point.year.toFixed(2)}, ${point[metric].toFixed(2)} ${unit}` : undefined}>
                    <title>{scenario.label} · Year {point.year.toFixed(2)} · {point[metric].toFixed(2)} {unit}</title>
                  </circle>
                </g>;
              })}
              {thresholds.map(({ threshold, year }) => <g key={`${scenario.label}-threshold-${threshold}`}>
                <line x1={x(year)} x2={x(year)} y1={top} y2={bottom} stroke={scenario.color} strokeDasharray="2 3" strokeWidth="1" opacity="0.7" pointerEvents="none" />
                <circle cx={x(year)} cy={y(threshold)} r="5" fill={scenario.color} stroke="white" strokeWidth="2" pointerEvents="none"><title>{scenario.label}: eGFR {threshold} crossing at year {year.toFixed(2)}</title></circle>
              </g>)}
              {transitions.map((transition, index) => <circle key={`${scenario.label}-category-${index}`} cx={x(transition.year)} cy={y(metric === "egfr" ? transition.egfr : transition.uacr)} r="4.5" fill={scenario.color} stroke="white" strokeWidth="2" pointerEvents="none">
                <title>{scenario.label}: Year {transition.year.toFixed(2)} category {transition.gfr_category} / {transition.albuminuria_category}</title>
              </circle>)}
              {points.length > 0 && <>
                <circle cx={x(points[0].year)} cy={y(points[0][metric])} r="5.5" fill={scenario.color} stroke="white" strokeWidth="2.5" pointerEvents="none" />
                <circle cx={x(points.at(-1)!.year)} cy={y(points.at(-1)![metric])} r="5.5" fill={scenario.color} stroke="white" strokeWidth="2.5" pointerEvents="none" />
              </>}
            </g>;
          })}

          {hoveredPoint && <g pointerEvents="none">
            <line x1={hoveredPoint.x} x2={hoveredPoint.x} y1={top} y2={bottom} stroke="#94a3b8" strokeDasharray="3 3" />
            <circle cx={hoveredPoint.x} cy={hoveredPoint.y} r="6.5" fill={hoveredPoint.color} stroke="white" strokeWidth="2.5" />
            <rect x={tooltipX} y={tooltipY} width="190" height="60" rx="8" fill="#0f172a" stroke="#334155" />
            <text x={tooltipX + 11} y={tooltipY + 18} fill="#cbd5e1" fontSize="10" fontWeight="700">{hoveredPoint.label}</text>
            <text x={tooltipX + 11} y={tooltipY + 42} fill="white" fontSize="12" fontWeight="600" fontFamily="monospace">Year {hoveredPoint.year.toFixed(2)} · {hoveredPoint.value.toFixed(2)} {unit}</text>
          </g>}

          <text x={(left + right) / 2} y="356" textAnchor="middle" fill="#475569" fontSize="11" fontWeight="600">Simulation timeline (elapsed years)</text>
          <text transform={`translate(18 ${(top + bottom) / 2}) rotate(-90)`} textAnchor="middle" fill="#475569" fontSize="11" fontWeight="600">{label} ({unit})</text>
        </svg>
      </div>
      <p className="mt-2.5 text-[11px] leading-5 text-slate-500">Both lines are hypothetical model outputs, separate from recorded measurements. Threshold and category markers use each scenario&apos;s own returned trajectory.</p>
    </figure>
  );
}

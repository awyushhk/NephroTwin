"use client";

import { useState } from "react";
import type { TrajectorySimulationResult, TrajectoryAnalysis } from "../types";

export function MechanisticTrajectoryPlot({
  points,
  metric,
  horizon,
  analysis,
}: {
  points: TrajectorySimulationResult["trajectory"];
  metric: "egfr" | "uacr";
  horizon: number;
  analysis: TrajectoryAnalysis;
}) {
  const [hoveredPoint, setHoveredPoint] = useState<{ year: number; value: number; x: number; y: number } | null>(null);
  const label = metric === "egfr" ? "eGFR" : "UACR";
  const fullName = metric === "egfr" ? "Glomerular Filtration Rate" : "Urine Albumin-to-Creatinine Ratio";
  const unit = metric === "egfr" ? "mL/min/1.73m²" : "mg/g";
  const color = metric === "egfr" ? "#6366f1" : "#0d9488";
  const startVal = points[0]?.[metric];
  const endVal = points.at(-1)?.[metric];
  const delta = startVal != null && endVal != null ? endVal - startVal : null;
  const values = points.map((point) => point[metric]);
  const rawMin = Math.min(...values, ...(metric === "egfr" ? [15] : []));
  const rawMax = Math.max(...values);
  const padding = Math.max((rawMax - rawMin) * 0.08, Math.abs(rawMax) * 0.03, 1);
  const low = Math.max(0, rawMin - padding);
  const high = rawMax + padding;
  const left = 84;
  const right = 820;
  const top = 32;
  const bottom = 296;
  const x = (year: number) => left + (year / horizon) * (right - left);
  const y = (value: number) => bottom - ((value - low) / (high - low)) * (bottom - top);
  const path = points.map((point) => `${x(point.year)},${y(point[metric])}`).join(" ");
  const areaPath = points.length > 0 ? `${x(points[0].year)},${bottom} ${path} ${x(points.at(-1)!.year)},${bottom}` : "";
  const yTicks = Array.from({ length: 5 }, (_, index) => low + ((high - low) * index) / 4);
  const xTicks = Array.from({ length: 6 }, (_, index) => (horizon * index) / 5);
  const showsThreshold = metric === "egfr" && low <= 15 && high >= 15;
  const thresholdMarkers = metric === "egfr"
    ? Object.entries(analysis.egfr.thresholds ?? {}).flatMap(([threshold, milestone]) => milestone.status === "crossed" && milestone.time_years != null
      ? [{ threshold: Number(threshold), year: milestone.time_years }]
      : [])
    : [];
  const categoryTransitions = analysis.categories.transitions;
  const tooltipX = hoveredPoint ? Math.max(left, Math.min(right - 180, hoveredPoint.x - 90)) : 0;
  const tooltipY = hoveredPoint ? Math.max(top, Math.min(bottom - 56, hoveredPoint.y - 66)) : 0;

  return (
    <figure className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-xs sm:p-5">
      <figcaption className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
        <div className="flex items-center gap-2.5">
          <span className="h-3 w-3 rounded-full shadow-xs" style={{ backgroundColor: color }} />
          <div>
            <h4 className="text-sm font-bold text-slate-900 tracking-tight">
              Simulated {label}{" "}
              <span className="text-xs font-normal text-slate-500 hidden sm:inline">({fullName})</span>
            </h4>
            <p className="text-[11px] text-slate-500">
              Hypothetical {horizon}-year trajectory · {points.length} calculated ODE timepoints
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-[11px] font-medium text-slate-700">
            {unit}
          </span>
          {startVal != null && endVal != null && (
            <span className={`rounded-lg px-2 py-0.5 font-mono text-[11px] font-semibold ${
              delta != null && delta < 0
                ? metric === "egfr" ? "bg-rose-50 text-rose-700 border border-rose-200/60" : "bg-emerald-50 text-emerald-700 border border-emerald-200/60"
                : delta != null && delta > 0
                ? metric === "egfr" ? "bg-emerald-50 text-emerald-700 border border-emerald-200/60" : "bg-rose-50 text-rose-700 border border-rose-200/60"
                : "bg-slate-50 text-slate-700 border border-slate-200"
            }`}>
              {startVal.toFixed(1)} → {endVal.toFixed(1)} ({delta != null && delta >= 0 ? "+" : ""}{delta?.toFixed(1)})
            </span>
          )}
        </div>
      </figcaption>

      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-slate-600" aria-label="Chart legend">
        <span className="inline-flex items-center gap-1.5 font-medium">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-600 ring-2 ring-emerald-200" /> Start (Baseline)
        </span>
        <span className="inline-flex items-center gap-1.5 font-medium">
          <span className="h-2.5 w-2.5 rounded-full ring-2" style={{ backgroundColor: color, outlineColor: color }} /> End (Year {horizon})
        </span>
        {categoryTransitions.length > 0 && (
          <span className="inline-flex items-center gap-1.5 font-medium">
            <span className="h-2.5 w-2.5 rounded-full bg-rose-600 ring-2 ring-rose-200" /> Category shift ({categoryTransitions.length})
          </span>
        )}
        {thresholdMarkers.length > 0 && (
          <span className="inline-flex items-center gap-1.5 font-medium">
            <span className="h-2.5 w-2.5 rounded-full bg-amber-600 ring-2 ring-amber-200" /> Threshold crossed ({thresholdMarkers.length})
          </span>
        )}
        {showsThreshold && (
          <span className="inline-flex items-center gap-1.5 font-medium text-amber-900">
            <span className="inline-block w-3.5 border-b-2 border-dashed border-amber-600" /> eGFR 15 threshold
          </span>
        )}
      </div>

      <div className="w-full overflow-x-auto rounded-xl border border-slate-100 bg-slate-50/40 p-1">
        <svg viewBox="0 0 860 370" className="h-[300px] min-w-[680px] w-full sm:h-[360px]" role="img" aria-label={`Simulated ${label} over ${horizon} years`}>
          <defs>
            <linearGradient id={`gradient-${metric}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity="0.14" />
              <stop offset="100%" stopColor={color} stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Area fill under curve */}
          {areaPath && <polygon points={areaPath} fill={`url(#gradient-${metric})`} pointerEvents="none" />}

          {/* Grid lines and tick labels */}
          {yTicks.map((tick, index) => (
            <g key={`y-${index}`}>
              <line x1={left} x2={right} y1={y(tick)} y2={y(tick)} stroke="#e2e8f0" strokeDasharray="3 4" strokeWidth="1" />
              <text x={left - 12} y={y(tick) + 4} textAnchor="end" fill="#64748b" fontSize="11" fontFamily="monospace" fontWeight="500">
                {tick.toFixed(tick >= 100 ? 0 : 1)}
              </text>
            </g>
          ))}
          {xTicks.map((tick, index) => (
            <g key={`x-${index}`}>
              <line x1={x(tick)} x2={x(tick)} y1={top} y2={bottom} stroke="#f1f5f9" strokeWidth="1" />
              <text x={x(tick)} y={bottom + 20} textAnchor="middle" fill="#64748b" fontSize="11" fontFamily="monospace" fontWeight="500">
                Yr {tick.toFixed(tick % 1 ? 1 : 0)}
              </text>
            </g>
          ))}

          {/* Reference threshold 15 line */}
          {showsThreshold && (
            <g>
              <line x1={left} x2={right} y1={y(15)} y2={y(15)} stroke="#d97706" strokeDasharray="6 4" strokeWidth="1.5" />
              <rect x={right - 170} y={y(15) - 18} width="166" height="17" rx="4" fill="#fef3c7" stroke="#fcd34d" strokeWidth="0.5" />
              <text x={right - 87} y={y(15) - 6} textAnchor="middle" fill="#92400e" fontSize="10" fontWeight="600">
                eGFR 15 reference threshold
              </text>
            </g>
          )}

          {/* Coordinate axes */}
          <line x1={left} x2={right} y1={bottom} y2={bottom} stroke="#94a3b8" strokeWidth="1.5" />
          <line x1={left} x2={left} y1={top} y2={bottom} stroke="#94a3b8" strokeWidth="1.5" />

          {/* Main Trajectory Line */}
          <polyline points={path} fill="none" stroke={color} strokeWidth="2.75" strokeLinejoin="round" strokeLinecap="round" />

          {/* Interactive point targets */}
          {points.map((point, index) => {
            const cx = x(point.year);
            const cy = y(point[metric]);
            const keyboardTarget = index === 0 || index === points.length - 1 || index % 20 === 0;
            const showTooltip = () => setHoveredPoint({ year: point.year, value: point[metric], x: cx, y: cy });
            return (
              <g key={`point-${index}`}>
                <circle cx={cx} cy={cy} r="2" fill={color} opacity="0.65" pointerEvents="none" />
                <circle
                  cx={cx}
                  cy={cy}
                  r="7"
                  fill="transparent"
                  className="cursor-crosshair"
                  onPointerEnter={showTooltip}
                  onPointerMove={showTooltip}
                  onPointerLeave={() => setHoveredPoint(null)}
                  onFocus={showTooltip}
                  onBlur={() => setHoveredPoint(null)}
                  tabIndex={keyboardTarget ? 0 : -1}
                  role={keyboardTarget ? "img" : undefined}
                  aria-hidden={!keyboardTarget}
                  aria-label={keyboardTarget ? `Simulated ${label}, year ${point.year.toFixed(2)}, ${point[metric].toFixed(2)} ${unit}` : undefined}
                >
                  <title>Year {point.year.toFixed(2)} · {point[metric].toFixed(2)} {unit}</title>
                </circle>
              </g>
            );
          })}

          {/* Threshold markers */}
          {thresholdMarkers.map(({ threshold, year }) => (
            <g key={`threshold-${threshold}`}>
              <line x1={x(year)} x2={x(year)} y1={top} y2={bottom} stroke="#f59e0b" strokeDasharray="2 3" strokeWidth="1" opacity="0.75" pointerEvents="none" />
              <circle cx={x(year)} cy={y(threshold)} r="5" fill="#d97706" stroke="white" strokeWidth="2" pointerEvents="none">
                <title>eGFR {threshold} crossing at year {year.toFixed(2)} (interpolated)</title>
              </circle>
            </g>
          ))}

          {/* Category transition markers */}
          {categoryTransitions.map((transition, index) => (
            <circle
              key={`category-${index}`}
              cx={x(transition.year)}
              cy={y(metric === "egfr" ? transition.egfr : transition.uacr)}
              r="4.5"
              fill="#e11d48"
              stroke="white"
              strokeWidth="2"
              pointerEvents="none"
            >
              <title>Year {transition.year.toFixed(2)}: {transition.gfr_category} / {transition.albuminuria_category}</title>
            </circle>
          ))}

          {/* Start and End Key Markers */}
          <circle cx={x(points[0].year)} cy={y(points[0][metric])} r="5.5" fill="#059669" stroke="white" strokeWidth="2.5" pointerEvents="none" />
          <circle cx={x(points.at(-1)!.year)} cy={y(points.at(-1)![metric])} r="5.5" fill={color} stroke="white" strokeWidth="2.5" pointerEvents="none" />

          {/* Hover Crosshair & Tooltip */}
          {hoveredPoint && (
            <g pointerEvents="none">
              <line x1={hoveredPoint.x} x2={hoveredPoint.x} y1={top} y2={bottom} stroke="#94a3b8" strokeDasharray="3 3" strokeWidth="1.25" />
              <line x1={left} x2={hoveredPoint.x} y1={hoveredPoint.y} y2={hoveredPoint.y} stroke="#cbd5e1" strokeDasharray="3 3" strokeWidth="1" />
              <circle cx={hoveredPoint.x} cy={hoveredPoint.y} r="6.5" fill={color} stroke="white" strokeWidth="2.5" />
            </g>
          )}

          {hoveredPoint && (
            <g pointerEvents="none" aria-hidden="true">
              <rect x={tooltipX} y={tooltipY} width="180" height="52" rx="8" fill="#0f172a" stroke="#334155" strokeWidth="1" />
              <text x={tooltipX + 12} y={tooltipY + 18} fill="#94a3b8" fontSize="9" fontWeight="700" letterSpacing="0.05em">
                SIMULATED POINT
              </text>
              <text x={tooltipX + 12} y={tooltipY + 38} fill="white" fontSize="12" fontWeight="600" fontFamily="monospace">
                Yr {hoveredPoint.year.toFixed(2)} · {hoveredPoint.value.toFixed(2)} {unit}
              </text>
            </g>
          )}

          {/* Axis Labels */}
          <text x={(left + right) / 2} y="356" textAnchor="middle" fill="#475569" fontSize="11" fontWeight="600">
            Simulation timeline (elapsed years)
          </text>
          <text transform={`translate(18 ${(top + bottom) / 2}) rotate(-90)`} textAnchor="middle" fill="#475569" fontSize="11" fontWeight="600">
            {label} ({unit})
          </text>
        </svg>
      </div>

      <p className="mt-2.5 text-[11px] leading-5 text-slate-500">
        Hypothetical model output, separate from recorded measurements. Markers show threshold crossings or category changes.
      </p>
    </figure>
  );
}

"use client";

import { useMemo } from "react";
import { Activity } from "lucide-react";
import type {
  ChartObservation,
  MeasurementType,
  ObservationDateFields,
  Scenario,
} from "../types";

export type MeasurementSpec = {
  label: string;
  short: string;
  unit: string;
  color: string;
  decimals?: number;
};

// Matches the palette used in LinearScenarioSimulator so timeline lines
// align visually with scenario cards and the comparison chart.
const SCENARIO_STROKE_COLORS = [
  "#6366f1", // indigo  — Scenario A
  "#0d9488", // teal    — Scenario B
  "#f59e0b", // amber   — Scenario C
  "#e11d48", // rose    — Scenario D
  "#8b5cf6", // violet  — Scenario E
];

export function TrendChart({
  observations,
  scenarios = [],
  measure,
  title,
  timeBounds,
  specs,
  formatObservationDate,
  observationCoordinate,
  observationSortValue,
  formatUtcMonth,
  observationX,
  valueY,
}: {
  observations: ChartObservation[];
  scenarios?: Scenario[];
  measure: MeasurementType;
  title?: string;
  timeBounds?: { start: number; end: number };
  specs: Record<MeasurementType, MeasurementSpec>;
  formatObservationDate: (row: ObservationDateFields, withTime?: boolean) => string;
  observationCoordinate: (row: ObservationDateFields, calendarDateAxis?: boolean) => number;
  observationSortValue: (row: ObservationDateFields) => number;
  formatUtcMonth: (value: number) => string;
  observationX: (value: string, start: number, span: number) => number;
  valueY: (value: number, low: number, high: number) => number;
}) {
  const rows = useMemo(
    () =>
      observations
        .filter((row) => row.measurement_type === measure)
        .slice()
        .sort(
          (a, b) =>
            observationSortValue(a) - observationSortValue(b) ||
            (a.source_sequence_number ?? 0) - (b.source_sequence_number ?? 0) ||
            a.id - b.id
        ),
    [measure, observations, observationSortValue]
  );
  const calendarDateAxis = rows.some(
    (row) => row.timestamp_precision === "date_only"
  );
  const hasUnresolvedOrdering = rows.some(
    (row) => row.same_day_ordering_ambiguous
  );
  const actualScenarios = useMemo(
    () => (measure === "egfr" ? scenarios : []),
    [measure, scenarios]
  );
  const chart = useMemo(() => {
    const points = rows.map((row) => ({
      time: observationCoordinate(row, calendarDateAxis),
      value: row.value,
    }));
    const baselineTimes = actualScenarios
      .map((scenario) => {
        const baseline = rows.find(
          (row) => row.id === scenario.baseline_observation_id
        );
        return baseline
          ? observationCoordinate(baseline, calendarDateAxis) +
              scenario.horizon_months * 30.4375 * 86400000
          : null;
      })
      .filter((time): time is number => time !== null);
    const times = points.map((point) => point.time).concat(baselineTimes);
    const values = points
      .map((point) => point.value)
      .concat(
        actualScenarios.flatMap((scenario) =>
          scenario.output.points.map((point) => point.value)
        )
      );
    if (!times.length || !values.length) return null;
    const start = timeBounds?.start ?? Math.min(...times);
    const rawEnd = Math.max(...times);
    const end = Math.max(timeBounds?.end ?? rawEnd, start + 86400000);
    const rawLow = Math.min(...values);
    const rawHigh = Math.max(...values);
    const padding = Math.max(
      (rawHigh - rawLow) * 0.12,
      Math.abs(rawHigh) * 0.035,
      1
    );
    const low = rawLow - padding;
    const high = rawHigh + padding;
    return { start, span: end - start, low, high, points };
  }, [actualScenarios, calendarDateAxis, observationCoordinate, rows, timeBounds]);

  if (!chart || !rows.length) {
    return (
      <div className="flex min-h-72 flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-50 px-6 text-center">
        <Activity className="mb-3 h-8 w-8 text-slate-300" />
        <p className="text-sm font-semibold text-slate-700">
          No {specs[measure]?.short ?? measure} observations in this history window
        </p>
        <p className="mt-1 max-w-md text-xs leading-5 text-slate-500">
          Choose another measurement. The timeline shows recorded results only,
          with the original gaps between measurements.
        </p>
      </div>
    );
  }

  const yTicks = Array.from(
    { length: 5 },
    (_, index) => chart.low + ((chart.high - chart.low) * index) / 4
  ).reverse();
  const timeTicks = Array.from(
    { length: 5 },
    (_, index) => chart.start + (chart.span * index) / 4
  );

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-gradient-to-b from-slate-50 to-white p-3 sm:p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-slate-800">
            {title ??
              (measure === "egfr" && actualScenarios.length > 0
                ? "Recorded eGFR and linear scenario paths"
                : measure === "egfr"
                ? "eGFR over recorded time"
                : `${specs[measure]?.label ?? measure} over recorded time`)}
          </p>
          <p className="mt-0.5 text-xs text-slate-500">
            {rows.length} visible result{rows.length === 1 ? "" : "s"} ·{" "}
            {specs[measure]?.unit}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-600">
          <span className="inline-flex items-center gap-1.5">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: specs[measure]?.color ?? "#0f766e" }}
            />
            Observed values
          </span>
          {actualScenarios.length > 0 && actualScenarios.map((s, i) => (
            <span key={s.id} className="inline-flex items-center gap-1.5">
              <span
                className="h-0 w-5 border-t-2 border-dashed"
                style={{ borderColor: SCENARIO_STROKE_COLORS[i % SCENARIO_STROKE_COLORS.length] }}
              />
              {s.assumptions.scenario_label ?? `Scenario ${String.fromCharCode(65 + i)}`}
            </span>
          ))}
        </div>
      </div>
      <div className="w-full overflow-x-auto">
        <svg
          viewBox="0 0 760 290"
          role="img"
          aria-label={`${specs[measure]?.label ?? measure} observations over actual chart times`}
          className="h-auto min-w-[620px] w-full"
        >
          {yTicks.map((tick, index) => {
            const y = 42 + (index * 196) / 4;
            return (
              <g key={`y-${index}`}>
                <line
                  x1="58"
                  x2="724"
                  y1={y}
                  y2={y}
                  stroke="#e2e8f0"
                  strokeDasharray={index === 4 ? undefined : "3 5"}
                />
                <text
                  x="49"
                  y={y + 3}
                  textAnchor="end"
                  fill="#64748b"
                  fontSize="10"
                >
                  {tick.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                </text>
              </g>
            );
          })}
          {timeTicks.map((tick, index) => (
            <g key={`x-${index}`}>
              <line
                x1={observationX(
                  new Date(tick).toISOString(),
                  chart.start,
                  chart.span
                )}
                x2={observationX(
                  new Date(tick).toISOString(),
                  chart.start,
                  chart.span
                )}
                y1="42"
                y2="238"
                stroke="#f1f5f9"
              />
              <text
                x={observationX(
                  new Date(tick).toISOString(),
                  chart.start,
                  chart.span
                )}
                y="260"
                textAnchor={
                  index === 0 ? "start" : index === 4 ? "end" : "middle"
                }
                fill="#64748b"
                fontSize="10"
              >
                {formatUtcMonth(tick)}
              </text>
            </g>
          ))}
          {actualScenarios.map((scenario, scenarioIdx) => {
            const baseline = rows.find(
              (row) => row.id === scenario.baseline_observation_id
            );
            if (!baseline) return null;
            const startTime = observationCoordinate(baseline, calendarDateAxis);
            const points = scenario.output.points
              .map((point) => {
                const time = startTime + point.month * 30.4375 * 86400000;
                return `${observationX(new Date(time).toISOString(), chart.start, chart.span)},${valueY(point.value, chart.low, chart.high)}`;
              })
              .join(" ");
            const strokeColor = SCENARIO_STROKE_COLORS[scenarioIdx % SCENARIO_STROKE_COLORS.length];
            return (
              <polyline
                key={`scenario-${scenario.id}`}
                points={points}
                fill="none"
                stroke={strokeColor}
                strokeWidth="2"
                strokeDasharray="7 5"
              >
                <title>
                  {scenario.assumptions.scenario_label ?? `Hypothetical scenario ${scenario.id}`}
                  {" · "}
                  {scenario.assumptions.rate_per_year >= 0 ? "+" : ""}
                  {scenario.assumptions.rate_per_year} mL/min/yr
                </title>
              </polyline>
            );
          })}
          {chart.points.length > 1 && !hasUnresolvedOrdering && (
            <polyline
              points={chart.points
                .map(
                  (point) =>
                    `${58 + ((point.time - chart.start) / chart.span) * 666},${valueY(point.value, chart.low, chart.high)}`
                )
                .join(" ")}
              fill="none"
              stroke={specs[measure]?.color ?? "#0f766e"}
              strokeWidth="1.75"
              strokeOpacity="0.65"
            >
              <title>Visual guide connecting the recorded observations</title>
            </polyline>
          )}
          {rows.map((row) => (
            <circle
              key={row.id}
              cx={
                58 +
                ((observationCoordinate(row, calendarDateAxis) - chart.start) /
                  chart.span) *
                  666
              }
              cy={valueY(row.value, chart.low, chart.high)}
              r="4.5"
              fill={specs[measure]?.color ?? "#0f766e"}
              stroke="white"
              strokeWidth="2"
            >
              <title>
                {formatObservationDate(row, true)}
                {row.source_sequence_number != null
                  ? ` · sequence ${row.source_sequence_number}`
                  : ""}{" "}
                · {row.value} {row.unit} · observation #{row.id}
              </title>
            </circle>
          ))}
          <line x1="58" x2="724" y1="238" y2="238" stroke="#94a3b8" />
          <line x1="58" x2="58" y1="42" y2="238" stroke="#94a3b8" />
          <text x="58" y="281" fill="#64748b" fontSize="10">
            Earlier
          </text>
          <text x="724" y="281" textAnchor="end" fill="#64748b" fontSize="10">
            Later
          </text>
        </svg>
      </div>
      <p className="mt-1 text-[11px] leading-5 text-slate-500">
        Dots mark recorded observations. Date-only points use calendar-date positions without a time of day; same-day date-only readings follow source sequence order.{" "}
        {hasUnresolvedOrdering
          ? "No line is shown because same-day mixed-precision ordering is unresolved."
          : "The solid line connects observations as a visual guide; it does not mean measurements were recorded between points."}{" "}
        {actualScenarios.length > 0 && "Dashed lines, when shown, are hypothetical scenarios."}
      </p>
    </div>
  );
}

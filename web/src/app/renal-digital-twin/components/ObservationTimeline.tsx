"use client";

import { ChevronLeft, ChevronRight, LoaderCircle } from "lucide-react";
import { useMemo } from "react";
import type {
  ChartObservation,
  MeasurementFilter,
  MeasurementType,
  Observation,
  ObservationDateFields,
  Scenario,
  TwinState,
} from "../types";
import { TrendChart, type MeasurementSpec } from "./TrendChart";

export const TIMELINE_PAGE_SIZE = 10;

function AllBiomarkerTimelineChart({
  observations,
  specs,
  timeBounds,
  observationCoordinate,
  formatObservationDate,
}: {
  observations: ChartObservation[];
  specs: Record<MeasurementType, MeasurementSpec>;
  timeBounds?: { start: number; end: number };
  observationCoordinate: (row: ObservationDateFields, calendarDateAxis?: boolean) => number;
  formatObservationDate: (row: ObservationDateFields, withTime?: boolean) => string;
}) {
  const lanes = useMemo(() => (Object.keys(specs) as MeasurementType[])
    .map((kind) => ({ kind, rows: observations.filter((row) => row.measurement_type === kind) }))
    .filter((lane) => lane.rows.length > 0), [observations, specs]);
  const calendarDateAxis = observations.some((row) => row.timestamp_precision === "date_only");
  if (!observations.length || !lanes.length) {
    return <div className="flex min-h-64 items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-50 text-sm text-slate-500">No observations in this time window.</div>;
  }

  const width = 1000;
  const left = 250;
  const right = 980;
  const top = 30;
  const laneHeight = 54;
  const bottom = top + lanes.length * laneHeight;
  const height = bottom + 58;
  const times = observations.map((row) => observationCoordinate(row, calendarDateAxis)).filter(Number.isFinite);
  const rawStart = timeBounds?.start ?? Math.min(...times);
  const rawEnd = timeBounds?.end ?? Math.max(...times);
  const singleDay = rawEnd <= rawStart;
  const start = singleDay ? rawStart - 43200000 : rawStart;
  const end = singleDay ? rawEnd + 43200000 : rawEnd;
  const span = end - start;
  const x = (time: number) => left + ((time - start) / span) * (right - left);
  const dateFormatter = new Intl.DateTimeFormat(undefined, span < 180 * 86400000
    ? { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }
    : { month: "short", year: "numeric", timeZone: "UTC" });
  const points = lanes.flatMap((lane, laneIndex) => {
    const byDate = new Map<number, ChartObservation[]>();
    lane.rows.forEach((row) => {
      const time = observationCoordinate(row, calendarDateAxis);
      const group = byDate.get(time) ?? [];
      group.push(row);
      byDate.set(time, group);
    });
    return [...byDate.entries()].flatMap(([time, sameDateRows]) => sameDateRows.map((row, index) => {
      const offset = sameDateRows.length > 1 ? (index / (sameDateRows.length - 1) - 0.5) * 30 : 0;
      return { row, time, cx: x(time), cy: top + laneIndex * laneHeight + laneHeight / 2 + offset };
    }));
  });

  return (
    <figure className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4 sm:p-5">
      <figcaption className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm font-semibold text-slate-900">All biomarkers over recorded time</span>
        <span className="text-xs text-slate-500">{observations.length.toLocaleString()} points · separate measurement lanes</span>
      </figcaption>
      <div className="w-full overflow-x-auto">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-auto max-h-[760px] min-h-[360px] min-w-[760px] w-full" role="img" aria-label={`Timeline of ${observations.length} observations across ${lanes.length} biomarker types`}>
          {lanes.map((lane, index) => {
            const center = top + index * laneHeight + laneHeight / 2;
            return <g key={lane.kind}>
              <line x1={left} x2={right} y1={top + (index + 1) * laneHeight} y2={top + (index + 1) * laneHeight} stroke="#e2e8f0" />
              <circle cx="12" cy={center - 4} r="4" fill={specs[lane.kind].color} />
              <text x="24" y={center - 3} fill="#334155" fontSize="12" fontWeight="600">{specs[lane.kind].label}</text>
              <text x="24" y={center + 13} fill="#64748b" fontSize="10">{specs[lane.kind].unit} · {lane.rows.length.toLocaleString()} results</text>
            </g>;
          })}
          {[0, 1, 2, 3, 4].map((fraction) => {
            const time = start + span * fraction / 4;
            const cx = x(time);
            return <g key={fraction}>
              <line x1={cx} x2={cx} y1={top} y2={bottom} stroke="#cbd5e1" strokeDasharray="3 5" />
              <text x={cx} y={bottom + 22} textAnchor={fraction === 0 ? "start" : fraction === 4 ? "end" : "middle"} fill="#64748b" fontSize="11">{dateFormatter.format(time)}</text>
            </g>;
          })}
          <line x1={left} x2={right} y1={bottom} y2={bottom} stroke="#94a3b8" />
          {points.map(({ row, time, cx, cy }) => <circle key={`${row.measurement_type}-${row.id}`} cx={cx} cy={cy} r="4" fill={specs[row.measurement_type].color} stroke="white" strokeWidth="1.5">
            <title>{`${specs[row.measurement_type].label}: ${row.value} ${row.unit} · ${formatObservationDate(row, true)}${row.source_sequence_number != null ? ` · source sequence ${row.source_sequence_number}` : ""}${row.source ? ` · ${row.source}` : ""}${row.source_observation_id ? ` · record ${row.source_observation_id}` : ""}`}</title>
          </circle>)}
          <text x={(left + right) / 2} y={height - 8} textAnchor="middle" fill="#475569" fontSize="11">Recorded date</text>
        </svg>
      </div>
      <p className="mt-2 text-[11px] leading-5 text-slate-500">Each lane has its own unit; vertical placement only separates same-date points and does not represent value. Points are not connected. When date-only observations are present, the shared axis uses calendar dates; hover shows exact times only when recorded and preserves date-only precision.</p>
    </figure>
  );
}

export function ObservationTimeline({
  loadingPatient,
  timelineChartObservations,
  scenarios,
  measurementFilter,
  setMeasurementFilter,
  analysisWindowDays,
  setAnalysisWindowDays,
  analysisBounds,
  specs,
  timelineLoading,
  timelineRows,
  timelinePage,
  setTimelinePage,
  twin,
  totalObservationCount,
  formatObservationDate,
  observationCoordinate,
  observationSortValue,
  formatUtcMonth,
  observationX,
  valueY,
}: {
  loadingPatient: boolean;
  timelineChartObservations: ChartObservation[];
  scenarios?: Scenario[];
  measurementFilter: MeasurementFilter;
  setMeasurementFilter: (m: MeasurementFilter) => void;
  analysisWindowDays: string;
  setAnalysisWindowDays: (d: string) => void;
  analysisBounds?: { start: number; end: number };
  specs: Record<MeasurementType, MeasurementSpec>;
  timelineLoading: boolean;
  timelineRows: Observation[];
  timelinePage: number;
  setTimelinePage: React.Dispatch<React.SetStateAction<number>>;
  twin: TwinState | null;
  totalObservationCount: number;
  formatObservationDate: (row: ObservationDateFields, withTime?: boolean) => string;
  observationCoordinate: (row: ObservationDateFields, calendarDateAxis?: boolean) => number;
  observationSortValue: (row: ObservationDateFields) => number;
  formatUtcMonth: (value: number) => string;
  observationX: (value: string, start: number, span: number) => number;
  valueY: (value: number, low: number, high: number) => number;
}) {
  const selectedMeasurement = measurementFilter === "all"
    ? { label: "All biomarkers", short: "All", unit: "mixed units", color: "#0f766e" }
    : specs[measurementFilter];
  return (
    <section
      aria-labelledby="timeline-heading"
      className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-xs sm:p-6"
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-teal-700">
            02 · Recorded history
          </p>
          <h2
            id="timeline-heading"
            className="mt-1 text-xl font-bold text-slate-900"
          >
            Renal measurement timeline
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            {measurementFilter === "all"
              ? "The chart includes all recorded biomarkers in separate lanes."
              : "The chart shows up to 500 recent observations for the selected measure."} Page through the full history below.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label htmlFor="measurement-filter" className="text-xs font-semibold text-slate-600">
            Measure
            <select
              id="measurement-filter"
              value={measurementFilter}
              onChange={(event) => {
                setMeasurementFilter(event.target.value as MeasurementFilter);
                setTimelinePage(0);
              }}
              className="ml-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800"
            >
              <option value="all">All</option>
              {Object.entries(specs).map(([key, spec]) => (
                <option key={key} value={key}>
                  {spec.label}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor="trend-window" className="text-xs font-semibold text-slate-600">
            Trend window
            <select
              id="trend-window"
              value={analysisWindowDays}
              onChange={(event) => setAnalysisWindowDays(event.target.value)}
              className="ml-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800"
            >
              <option value="30">30 days</option>
              <option value="90">90 days</option>
              <option value="365">1 year</option>
              <option value="1825">5 years</option>
              <option value="all">All history</option>
            </select>
          </label>
        </div>
      </div>

      {loadingPatient ? (
        <div className="flex min-h-64 items-center justify-center text-sm text-slate-500">
          <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
          Loading recorded timeline…
        </div>
      ) : (
        measurementFilter === "all" ? <AllBiomarkerTimelineChart
          observations={timelineChartObservations}
          specs={specs}
          timeBounds={analysisBounds}
          observationCoordinate={observationCoordinate}
          formatObservationDate={formatObservationDate}
        /> : <TrendChart
          observations={timelineChartObservations}
          scenarios={[]}
          measure={measurementFilter}
          timeBounds={analysisBounds}
          specs={specs}
          formatObservationDate={formatObservationDate}
          observationCoordinate={observationCoordinate}
          observationSortValue={observationSortValue}
          formatUtcMonth={formatUtcMonth}
          observationX={observationX}
          valueY={valueY}
        />
      )}

      <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full min-w-[620px] text-left text-sm">
          <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3 font-semibold">Observed at</th>
              <th className="px-4 py-3 font-semibold">Measurement</th>
              <th className="px-4 py-3 font-semibold">Result</th>
              <th className="px-4 py-3 font-semibold">Source</th>
              <th className="px-4 py-3 font-semibold">Record ID</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {timelineLoading ? (
              <tr>
                <td
                  colSpan={5}
                  className="px-4 py-8 text-center text-sm text-slate-500"
                >
                  <LoaderCircle className="mr-2 inline h-4 w-4 animate-spin" />
                  Loading results…
                </td>
              </tr>
            ) : (
              timelineRows
                .slice()
                .reverse()
                .map((row) => (
                  <tr key={row.id} className="hover:bg-slate-50">
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-600">
                      {formatObservationDate(row, true)}
                      {row.source_sequence_number != null ? (
                        <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-[10px]">
                          Date only · seq {row.source_sequence_number}
                        </span>
                      ) : null}
                      {row.same_day_ordering_ambiguous ? (
                        <span className="ml-2 text-amber-700">Same-day order unresolved</span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 text-xs font-medium text-slate-800">
                      {specs[row.measurement_type]?.label ?? row.measurement_type}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-sm font-semibold text-slate-900">
                      {row.value}{" "}
                      <span className="text-xs font-normal text-slate-500">
                        {row.unit}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {row.source_original_label ? `${row.source_original_label} · ` : ""}
                      {row.source ?? "Source record"}
                      {row.source_item_id ? ` · item ${row.source_item_id}` : ""}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500">
                      #{row.source_observation_id ?? row.id}
                      {row.source_observation_id ? " source" : ""}
                    </td>
                  </tr>
                ))
            )}
          </tbody>
        </table>
        {!timelineLoading && timelineRows.length === 0 && (
          <p className="px-4 py-4 text-sm text-slate-500">
            {measurementFilter === "all" ? "No observations are recorded for this patient." : `No ${selectedMeasurement.label.toLowerCase()} observations are recorded for this patient.`}
          </p>
        )}
      </div>

      {(() => {
        const total = measurementFilter === "all" ? totalObservationCount : twin?.measurements?.[measurementFilter]?.count ?? 0;
        const totalPages = Math.max(1, Math.ceil(total / TIMELINE_PAGE_SIZE));
        const first = total ? timelinePage * TIMELINE_PAGE_SIZE + 1 : 0;
        const last = Math.min((timelinePage + 1) * TIMELINE_PAGE_SIZE, total);
        return (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-slate-50 px-3.5 py-3">
            <p
              aria-live="polite"
              className="text-xs font-medium text-slate-600"
            >
              Showing{" "}
              <span className="font-semibold text-slate-900">
                {first}–{last}
              </span>{" "}
              of{" "}
              <span className="font-semibold text-slate-900">
                {total.toLocaleString()}
              </span>{" "}
              {selectedMeasurement.short} results · Page{" "}
              {Math.min(timelinePage + 1, totalPages)} of {totalPages}
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                aria-label="Previous timeline page"
                onClick={() =>
                  setTimelinePage((page) => Math.max(0, page - 1))
                }
                disabled={timelinePage === 0 || timelineLoading}
                className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <ChevronLeft className="h-4 w-4" />
                Previous
              </button>
              <button
                type="button"
                aria-label="Next timeline page"
                onClick={() =>
                  setTimelinePage((page) =>
                    Math.min(totalPages - 1, page + 1)
                  )
                }
                disabled={timelinePage >= totalPages - 1 || timelineLoading}
                className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        );
      })()}
    </section>
  );
}

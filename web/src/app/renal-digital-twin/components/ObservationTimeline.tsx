"use client";

import { ChevronLeft, ChevronRight, LoaderCircle } from "lucide-react";
import type {
  ChartObservation,
  MeasurementType,
  Observation,
  ObservationDateFields,
  Scenario,
  TwinState,
} from "../types";
import { TrendChart, type MeasurementSpec } from "./TrendChart";

export const TIMELINE_PAGE_SIZE = 10;

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
  selectedMeasurement,
  timelineLoading,
  timelineRows,
  timelinePage,
  setTimelinePage,
  twin,
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
  measurementFilter: MeasurementType;
  setMeasurementFilter: (m: MeasurementType) => void;
  analysisWindowDays: string;
  setAnalysisWindowDays: (d: string) => void;
  analysisBounds?: { start: number; end: number };
  specs: Record<MeasurementType, MeasurementSpec>;
  selectedMeasurement: MeasurementSpec;
  timelineLoading: boolean;
  timelineRows: Observation[];
  timelinePage: number;
  setTimelinePage: React.Dispatch<React.SetStateAction<number>>;
  twin: TwinState | null;
  formatObservationDate: (row: ObservationDateFields, withTime?: boolean) => string;
  observationCoordinate: (row: ObservationDateFields, calendarDateAxis?: boolean) => number;
  observationSortValue: (row: ObservationDateFields) => number;
  formatUtcMonth: (value: number) => string;
  observationX: (value: string, start: number, span: number) => number;
  valueY: (value: number, low: number, high: number) => number;
}) {
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
            The chart shows up to 500 recent observations for the selected
            measurement; missing intervals remain gaps. Page through the full history below.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label htmlFor="measurement-filter" className="text-xs font-semibold text-slate-600">
            Measure
            <select
              id="measurement-filter"
              value={measurementFilter}
              onChange={(event) => {
                setMeasurementFilter(event.target.value as MeasurementType);
                setTimelinePage(0);
              }}
              className="ml-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800"
            >
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
        <TrendChart
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
            No {selectedMeasurement.label.toLowerCase()} observations are
            recorded for this patient.
          </p>
        )}
      </div>

      {(() => {
        const total = twin?.measurements?.[measurementFilter]?.count ?? 0;
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

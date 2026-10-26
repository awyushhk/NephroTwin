"use client";

import { Activity, ArrowDownRight, ArrowUpRight, Clock3, LoaderCircle, Minus, RefreshCw, Sparkles } from "lucide-react";
import type {
  Measurement,
  MeasurementType,
  ObservationDateFields,
  Patient,
  TwinState,
} from "../types";
import type { MeasurementSpec } from "./TrendChart";

function displayValue(value: number, digits = 2) {
  if (!Number.isFinite(value)) return "\u2014";
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(value);
}

export function metricTrend(measurement: Measurement, digits = 2) {
  if (
    measurement.change == null ||
    !Number.isFinite(measurement.change) ||
    !measurement.previous
  ) return null;
  const direction = measurement.change > 0 ? "increase" : measurement.change < 0 ? "decrease" : "unchanged";
  const change = displayValue(Math.abs(measurement.change), digits);
  if (direction === "unchanged") return { direction, text: "No change since the previous result" };
  const elapsed = measurement.elapsed_days;
  const rate = measurement.change_per_day;
  if (elapsed == null || !Number.isFinite(elapsed) || elapsed <= 0) {
    return { direction, text: `${direction === "increase" ? "Increased" : "Decreased"} by ${change} since the previous result \u00b7 elapsed time unavailable` };
  }
  const interval = elapsed < 1 ? "less than 1 day" : `over ${displayValue(elapsed, 1)} days`;
  if (rate == null || !Number.isFinite(rate)) {
    return { direction, text: `${direction === "increase" ? "Increased" : "Decreased"} by ${change} ${interval}` };
  }
  const signedRate = `${rate > 0 ? "+" : ""}${displayValue(rate, 3)}`;
  return { direction, text: `${direction === "increase" ? "Increased" : "Decreased"} by ${change} ${interval} \u00b7 average ${signedRate}/day` };
}

// ---- Group definitions -------------------------------------------------------
// Keys that belong to each named group. Card order follows array order.

const GROUPS = [
  {
    id: "blood",
    label: "Blood Tests",
    subtitle: "Biomarkers derived from blood samples",
    keys: ["egfr", "creatinine", "bun", "potassium", "bicarbonate", "hba1c"] as MeasurementType[],
  },
  {
    id: "urine",
    label: "Urine Tests",
    subtitle: "Biomarkers derived from urine samples",
    keys: ["acr", "urine_albumin", "urine_creatinine"] as MeasurementType[],
  },
  {
    id: "clinical",
    label: "Clinical Measurements",
    subtitle: "Measured vitals and physical assessments",
    keys: ["systolic_bp", "diastolic_bp"] as MeasurementType[],
  },
] as const;

const CLASSIFIED_KEYS = new Set<string>(GROUPS.flatMap((g) => g.keys as string[]));

// ---- Shared card renderer ----------------------------------------------------

function MeasurementCard({
  measureKey,
  spec,
  item,
  formatObservationDate,
}: {
  measureKey: MeasurementType;
  spec: MeasurementSpec;
  item: Measurement | undefined;
  formatObservationDate: (row: ObservationDateFields, withTime?: boolean) => string;
}) {
  const trend = item ? metricTrend(item, spec.decimals ?? 2) : null;
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm shadow-slate-950/[0.02]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-slate-800">{spec.label}</p>
          <p className="mt-0.5 text-xs text-slate-500">{item?.count ?? 0} recorded results</p>
        </div>
        {item?.stale && (
          <span className="rounded-full bg-amber-50 px-2.5 py-1 text-[10px] font-semibold text-amber-800">
            Older result
          </span>
        )}
      </div>
      <div className="mt-3 flex items-end justify-between gap-3">
        <p className="text-xl font-bold text-slate-950">
          {item?.latest ? `${item.latest.value}` : "\u2014"}
          <span className="ml-1 text-xs font-medium text-slate-500">
            {item?.latest?.unit ?? spec.unit}
          </span>
        </p>
        {item?.category && (
          <span className="rounded-lg bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700">
            {item.category} observed
          </span>
        )}
      </div>
      <p className="mt-1.5 text-xs text-slate-500">
        {item?.latest
          ? formatObservationDate(item.latest, true)
          : item?.latest_temporal_ambiguity
          ? `Same-day ordering unresolved across ${item.latest_candidates?.length ?? 0} observations`
          : "No observation in this profile"}
      </p>
      {trend && (
        <p className="mt-2 flex items-start gap-1.5 text-xs font-medium leading-5 text-slate-700">
          {trend.direction === "increase" ? (
            <ArrowUpRight aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-teal-700" />
          ) : trend.direction === "decrease" ? (
            <ArrowDownRight aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-teal-700" />
          ) : (
            <Minus aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
          )}
          <span>{trend.text}</span>
        </p>
      )}
    </article>
  );
}

// ---- Main component ----------------------------------------------------------

export function CurrentRenalState({
  patientId,
  selectedPatient,
  twin,
  specs,
  formatObservationDate,
  recomputeState,
  updating,
  loadingPatient,
  primaryButtonClassName,
}: {
  patientId: number | "";
  selectedPatient?: Patient;
  twin: TwinState | null;
  specs: Record<MeasurementType, MeasurementSpec>;
  formatObservationDate: (row: ObservationDateFields, withTime?: boolean) => string;
  recomputeState: () => Promise<void>;
  updating: boolean;
  loadingPatient: boolean;
  primaryButtonClassName: string;
}) {
  const ungroupedKeys = (Object.keys(specs) as MeasurementType[]).filter(
    (k) => !CLASSIFIED_KEYS.has(k),
  );

  return (
    <section aria-labelledby="state-heading" className="space-y-5">

      {/* ---- Section header ---- */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-teal-700">
            01 · Patient summary
          </p>
          <h2 id="state-heading" className="mt-1 text-xl font-bold text-slate-900">
            Current Renal State
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Latest available values from recorded data, with the time and trend kept visible.
          </p>
        </div>
        <button
          onClick={() => void recomputeState()}
          disabled={!patientId || updating || loadingPatient}
          className={primaryButtonClassName}
        >
          {updating ? (
            <LoaderCircle className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          {updating ? "Recomputing\u2026" : "Recompute twin state"}
        </button>
      </div>

      {/* ---- Top summary cards (unchanged) ---- */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl border border-teal-200 bg-teal-50/70 p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-teal-800">eGFR latest</span>
            <Activity className="h-4 w-4 text-teal-700" />
          </div>
          <p className="mt-3 text-2xl font-bold tracking-tight text-slate-900">
            {twin?.measurements?.egfr?.latest ? `${displayValue(twin.measurements.egfr.latest.value, specs.egfr.decimals)} ${twin.measurements.egfr.latest.unit}` : "No result"}
          </p>
          <p className="mt-1 text-xs text-slate-600">
            {twin?.measurements?.egfr?.latest ? formatObservationDate(twin.measurements.egfr.latest, true) : twin?.measurements?.egfr?.latest_temporal_ambiguity ? "Same-day ordering unresolved" : "\u2014"}
          </p>
        </div>
        <div className="rounded-2xl border border-blue-200 bg-blue-50/70 p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-blue-800">Creatinine latest</span>
            <Activity className="h-4 w-4 text-blue-700" />
          </div>
          <p className="mt-3 text-2xl font-bold tracking-tight text-slate-900">
            {twin?.measurements?.creatinine?.latest ? `${displayValue(twin.measurements.creatinine.latest.value, specs.creatinine.decimals)} ${twin.measurements.creatinine.latest.unit}` : "No result"}
          </p>
          <p className="mt-1 text-xs text-slate-600">
            {twin?.measurements?.creatinine?.latest ? formatObservationDate(twin.measurements.creatinine.latest, true) : twin?.measurements?.creatinine?.latest_temporal_ambiguity ? "Same-day ordering unresolved" : "\u2014"}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Measurement types</span>
            <Sparkles className="h-4 w-4 text-violet-600" />
          </div>
          <p className="mt-3 text-2xl font-bold tracking-tight text-slate-900">
            {twin?.data_completeness?.available_measurements ?? 0}
            <span className="ml-1 text-sm font-medium text-slate-400">/ {twin?.data_completeness?.supported_measurements ?? Object.keys(specs).length}</span>
          </p>
          <p className="mt-1 text-xs text-slate-500">with at least one recorded result</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">History coverage</span>
            <Clock3 className="h-4 w-4 text-slate-500" />
          </div>
          <p className="mt-3 text-2xl font-bold tracking-tight text-slate-900">{selectedPatient?.observation_count.toLocaleString() ?? "\u2014"}</p>
          <p className="mt-1 text-xs text-slate-500">source observations · irregular timestamps</p>
        </div>
      </div>

      {/* ---- Grouped measurement cards ---- */}
      <div className="space-y-5">
        {GROUPS.map((group) => {
          const keys = group.keys.filter((k) => k in specs);
          if (keys.length === 0) return null;
          const withData = keys.filter((k) => (twin?.measurements?.[k]?.count ?? 0) > 0).length;
          return (
            <div key={group.id}>
              {/* Group heading */}
              <div className="mb-2 flex items-center justify-between border-b border-slate-100 pb-1.5">
                <div>
                  <p className="text-xs font-bold uppercase tracking-wider text-slate-700">{group.label}</p>
                </div>
                <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[10px] font-semibold text-slate-500">
                  {withData} / {keys.length} with data
                </span>
              </div>
              {/* Cards */}
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {keys.map((k) => (
                  <MeasurementCard
                    key={k}
                    measureKey={k}
                    spec={specs[k]}
                    item={twin?.measurements?.[k]}
                    formatObservationDate={formatObservationDate}
                  />
                ))}
              </div>
            </div>
          );
        })}

        {/* Fallback: future / unclassified measurement types are never hidden */}
        {ungroupedKeys.length > 0 && (
          <div>
            <div className="mb-2 border-b border-slate-100 pb-1.5">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-500">Other Measurements</p>
              <p className="mt-0.5 text-[11px] text-slate-400">
                {ungroupedKeys.length} type{ungroupedKeys.length !== 1 ? "s" : ""} not assigned to a specific group
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {ungroupedKeys.map((k) => (
                <MeasurementCard
                  key={k}
                  measureKey={k}
                  spec={specs[k]}
                  item={twin?.measurements?.[k]}
                  formatObservationDate={formatObservationDate}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ---- Review warnings ---- */}
      {twin?.warnings?.length ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
          <p className="text-xs font-semibold text-amber-950">Review notes</p>
          <ul className="mt-1 list-inside list-disc space-y-1 text-xs leading-5 text-amber-900">
            {twin.warnings.map((warning, index) => (
              <li key={`${index}-${warning}`}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="text-xs leading-5 text-slate-500">
        {twin?.clinical_note ??
          "The twin summarizes observations and trends; it does not establish a CKD or AKI diagnosis."}
      </p>
    </section>
  );
}

"use client";

import { FormEvent, useMemo } from "react";
import {
  AlertCircle,
  ArrowRight,
  BarChart3,
  LoaderCircle,
  Minus,
  Plus,
  Trash2,
} from "lucide-react";
import type {
  MeasurementType,
  Observation,
  ObservationDateFields,
  Scenario,
  ScenarioDraft,
} from "../types";
import { TrendChart, type MeasurementSpec } from "./TrendChart";

// Per-scenario colour palette — distinct, restrained, colourblind-safe
const SCENARIO_COLORS = [
  { stroke: "#6366f1", bg: "bg-indigo-100", text: "text-indigo-800", border: "border-indigo-200", dot: "#6366f1" },
  { stroke: "#0d9488", bg: "bg-teal-100",   text: "text-teal-800",   border: "border-teal-200",   dot: "#0d9488" },
  { stroke: "#f59e0b", bg: "bg-amber-100",  text: "text-amber-800",  border: "border-amber-200",  dot: "#f59e0b" },
  { stroke: "#e11d48", bg: "bg-rose-100",   text: "text-rose-800",   border: "border-rose-200",   dot: "#e11d48" },
  { stroke: "#8b5cf6", bg: "bg-violet-100", text: "text-violet-800", border: "border-violet-200", dot: "#8b5cf6" },
] as const;

// ─── Main Component ───────────────────────────────────────────────────────────

export function LinearScenarioSimulator({
  patientId,
  scenarioBase,
  setScenarioBase,
  eGfrObservations,
  formatObservationDate,
  scenarioDrafts,
  setScenarioDrafts,
  horizon,
  setHorizon,
  saveScenario,
  savingScenario,
  scenarios,
  observations,
  deleteScenario,
  deletingScenarioId,
  inputClassName,
  primaryButtonClassName,
  specs,
  observationCoordinate,
  observationSortValue,
  formatUtcMonth,
  observationX,
  valueY,
}: {
  patientId: number | "";
  scenarioBase: string;
  setScenarioBase: (val: string) => void;
  eGfrObservations: Observation[];
  formatObservationDate: (row: ObservationDateFields, withTime?: boolean) => string;
  scenarioDrafts: ScenarioDraft[];
  setScenarioDrafts: React.Dispatch<React.SetStateAction<ScenarioDraft[]>>;
  horizon: string;
  setHorizon: (val: string) => void;
  saveScenario: (event: FormEvent<HTMLFormElement>) => void;
  savingScenario: boolean;
  scenarios: Scenario[];
  observations: Observation[];
  deleteScenario: (id: number) => Promise<void>;
  deletingScenarioId: number | null;
  inputClassName: string;
  primaryButtonClassName: string;
  specs: Record<MeasurementType, MeasurementSpec>;
  observationCoordinate: (row: ObservationDateFields, calendarDateAxis?: boolean) => number;
  observationSortValue: (row: ObservationDateFields) => number;
  formatUtcMonth: (value: number) => string;
  observationX: (value: string, start: number, span: number) => number;
  valueY: (value: number, low: number, high: number) => number;
}) {
  const horizonNum = Number(horizon) || 12;
  const horizonYears = (horizonNum / 12).toFixed(horizonNum % 12 === 0 ? 0 : 1);

  const selectedBaselineRow = eGfrObservations.find((r) => String(r.id) === scenarioBase);

  // Group saved scenarios by comparison_group_id, newest group first
  const scenarioGroups = useMemo(() => {
    const groups = new Map<string, Scenario[]>();
    const ungrouped: Scenario[] = [];
    for (const s of scenarios) {
      const gid = s.assumptions.comparison_group_id;
      if (gid) {
        const arr = groups.get(gid) ?? [];
        arr.push(s);
        groups.set(gid, arr);
      } else {
        ungrouped.push(s);
      }
    }
    // Sort each group internally by comparison_index
    for (const [gid, arr] of groups) {
      groups.set(gid, arr.slice().sort((a, b) => (a.assumptions.comparison_index ?? 0) - (b.assumptions.comparison_index ?? 0)));
    }
    // Return groups ordered newest first (by max scenario id in group)
    const sortedGroups = [...groups.values()].sort((a, b) => {
      const maxA = Math.max(...a.map((s) => s.id));
      const maxB = Math.max(...b.map((s) => s.id));
      return maxB - maxA;
    });
    const ungroupedSorted = ungrouped.slice().sort((a, b) => b.id - a.id);
    return [...sortedGroups, ...ungroupedSorted.map((s) => [s])];
  }, [scenarios]);

  return (
    <div className="divide-y divide-slate-100">
      {/* ── Scenario Builder Form ── */}
      <form
        onSubmit={(event) => void saveScenario(event)}
        className="p-5 sm:p-6"
      >
        <div className="grid gap-6 lg:grid-cols-[minmax(320px,1fr)_minmax(0,1fr)]">
          {/* Left column — controls */}
          <div className="space-y-5">

            {/* Baseline selection */}
            <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-4">
              <p className="mb-2.5 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Baseline — starting point
              </p>
              {eGfrObservations.length === 0 ? (
                <div className="flex items-start gap-2.5 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                  <span>No recorded eGFR results found for this patient. Load a patient profile with eGFR observations to use the scenario builder.</span>
                </div>
              ) : (
                <>
                  <label htmlFor="scenario-baseline" className="sr-only">
                    Select starting eGFR observation
                  </label>
                  <select
                    id="scenario-baseline"
                    className={inputClassName}
                    required
                    value={scenarioBase}
                    onChange={(event) => setScenarioBase(event.target.value)}
                  >
                    <option value="">Choose a recorded result…</option>
                    {eGfrObservations.map((row) => (
                      <option key={row.id} value={row.id}>
                        {row.value} mL/min/1.73m² · {formatObservationDate(row)}
                      </option>
                    ))}
                  </select>
                  {selectedBaselineRow && (
                    <div className="mt-2.5 flex items-baseline gap-3 text-xs">
                      <span className="font-mono text-base font-bold text-slate-900">
                        {selectedBaselineRow.value}
                      </span>
                      <span className="text-slate-500">mL/min/1.73m²</span>
                      <span className="text-slate-400">·</span>
                      <span className="text-slate-600">{formatObservationDate(selectedBaselineRow)}</span>
                    </div>
                  )}
                  <p className="mt-2 text-[11px] text-slate-500">
                    All hypothetical paths start from this recorded observation. The baseline is not calculated or inferred.
                  </p>
                </>
              )}
            </div>

            {/* Horizon */}
            <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-4">
              <div className="mb-2.5 flex items-center justify-between">
                <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Comparison horizon
                </p>
                <span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[11px] font-semibold text-slate-700">
                  {horizonNum} mo · {horizonYears} yr
                </span>
              </div>
              <input
                id="scenario-horizon"
                type="range"
                min="1"
                max="120"
                step="1"
                value={horizon}
                onChange={(event) => setHorizon(event.target.value)}
                className="w-full accent-indigo-600"
                aria-label={`Comparison horizon: ${horizonNum} months`}
              />
              <div className="mt-1 flex items-center justify-between">
                <span className="text-[10px] text-slate-400">1 month</span>
                <label htmlFor="scenario-horizon-input" className="sr-only">Horizon in months</label>
                <input
                  id="scenario-horizon-input"
                  type="number"
                  min="1"
                  max="120"
                  step="1"
                  required
                  value={horizon}
                  onChange={(event) => setHorizon(event.target.value)}
                  className="w-16 rounded-lg border border-slate-300 bg-white px-2 py-1 text-center font-mono text-xs text-slate-800 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
                />
                <span className="text-[10px] text-slate-400">120 months</span>
              </div>
            </div>

            {/* Submit */}
            <button
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-800 focus:outline-none focus:ring-4 focus:ring-indigo-200 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={
                !patientId ||
                !scenarioBase ||
                savingScenario ||
                eGfrObservations.length === 0
              }
            >
              {savingScenario ? (
                <LoaderCircle className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowRight className="h-4 w-4" />
              )}
              {savingScenario ? "Saving…" : "Compare scenarios"}
            </button>
            <p className="text-[11px] leading-5 text-slate-500">
              eGFR at month m = baseline + assumed rate × (m ÷ 12). Results are saved for the selected patient session and visible in the timeline chart above.
            </p>
          </div>

          {/* Right column — scenario rates */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Hypothetical annual rates
                </p>
                <p className="mt-0.5 text-[11px] text-slate-500">
                  Enter assumed rates (−30 to +30 mL/min/1.73m² per year). Not inferred from clinical history.
                </p>
              </div>
              <button
                type="button"
                onClick={() =>
                  setScenarioDrafts((current) =>
                    current.length >= 5
                      ? current
                      : [...current, { key: crypto.randomUUID(), rate: "" }]
                  )
                }
                disabled={scenarioDrafts.length >= 5}
                className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Plus className="h-3.5 w-3.5" />
                Add
              </button>
            </div>

            <div className="space-y-2">
              {scenarioDrafts.map((draft, index) => {
                const col = SCENARIO_COLORS[index % SCENARIO_COLORS.length];
                const rateNum = Number(draft.rate);
                const isPositive = draft.rate !== "" && rateNum > 0;
                const isNegative = draft.rate !== "" && rateNum < 0;
                return (
                  <div
                    key={draft.key}
                    className={`flex items-center gap-3 rounded-xl border ${col.border} bg-white px-3 py-2.5`}
                  >
                    {/* Color swatch + label */}
                    <span
                      className={`shrink-0 rounded-md px-2 py-1 text-[10px] font-bold uppercase tracking-wider ${col.bg} ${col.text}`}
                      style={{ minWidth: "2.5rem", textAlign: "center" }}
                    >
                      {String.fromCharCode(65 + index)}
                    </span>

                    {/* Rate input */}
                    <label
                      htmlFor={`scenario-rate-${index}`}
                      className="sr-only"
                    >
                      Scenario {String.fromCharCode(65 + index)} annual eGFR change in mL/min/1.73m² per year
                    </label>
                    <div className="flex min-w-0 flex-1 items-center gap-2">
                      <input
                        id={`scenario-rate-${index}`}
                        type="number"
                        min="-30"
                        max="30"
                        step="0.1"
                        required
                        value={draft.rate}
                        onChange={(event) =>
                          setScenarioDrafts((current) =>
                            current.map((item) =>
                              item.key === draft.key
                                ? { ...item, rate: event.target.value }
                                : item
                            )
                          )
                        }
                        placeholder="e.g. −1.0"
                        className="w-24 rounded-lg border border-slate-300 bg-slate-50 px-2.5 py-1.5 font-mono text-sm font-semibold text-slate-900 outline-none focus:border-indigo-500 focus:bg-white focus:ring-2 focus:ring-indigo-100"
                      />
                      <span className="text-[11px] text-slate-500">mL/min/1.73m² / yr</span>
                      {draft.rate !== "" && (
                        <span
                          className={`ml-auto shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${
                            isPositive
                              ? "bg-emerald-50 text-emerald-700"
                              : isNegative
                              ? "bg-rose-50 text-rose-700"
                              : "bg-slate-100 text-slate-500"
                          }`}
                        >
                          {isPositive ? "+" : ""}{rateNum.toFixed(1)}
                        </span>
                      )}
                    </div>

                    {/* Remove */}
                    {scenarioDrafts.length > 2 && (
                      <button
                        type="button"
                        aria-label={`Remove scenario ${String.fromCharCode(65 + index)}`}
                        onClick={() =>
                          setScenarioDrafts((current) =>
                            current.filter((item) => item.key !== draft.key)
                          )
                        }
                        className="shrink-0 rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600 transition"
                      >
                        <Minus className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Pre-submission summary */}
            {selectedBaselineRow && scenarioDrafts.some((d) => d.rate !== "") && (
              <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3 text-[11px] text-slate-600">
                <p className="font-semibold text-slate-700">Ready to compare</p>
                <p className="mt-0.5">
                  Baseline: <span className="font-mono font-semibold text-slate-900">{selectedBaselineRow.value} mL/min/1.73m²</span>
                  {" · "}Horizon: <span className="font-mono font-semibold text-slate-900">{horizonNum} months</span>
                  {" · "}{scenarioDrafts.filter((d) => d.rate !== "").length} scenario{scenarioDrafts.filter((d) => d.rate !== "").length !== 1 ? "s" : ""} configured
                </p>
              </div>
            )}
          </div>
        </div>
      </form>

      {/* ── Saved Scenario Results ── */}
      {scenarioGroups.length === 0 ? (
        <div className="flex min-h-56 flex-col items-center justify-center gap-3 p-8 text-center">
          <div className="rounded-full border border-slate-200 bg-slate-50 p-3">
            <BarChart3 className="h-5 w-5 text-slate-400" />
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-700">No comparison results yet</p>
            <p className="mt-1 max-w-sm text-xs leading-5 text-slate-500">
              Select a recorded baseline, enter assumed annual rates for each hypothetical path, set a horizon, and click <strong>Compare scenarios</strong>.
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-8 p-5 sm:p-6">
          {scenarioGroups.map((group, groupIdx) => {
            const refScenario = group[0];
            if (!refScenario) return null;
            const baseline = observations.find((r) => r.id === refScenario.baseline_observation_id);
            const baselineValue = refScenario.output.points[0]?.value ?? baseline?.value;
            const baselineLabel = baseline ? formatObservationDate(baseline) : "—";
            const horizonMo = refScenario.horizon_months;
            const isNewGroup = groupIdx === 0;

            return (
              <section key={refScenario.assumptions.comparison_group_id ?? refScenario.id} aria-label={`Comparison group ${groupIdx + 1}`}>
                {/* Group header */}
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
                  <div>
                    <div className="flex items-center gap-2">
                      {isNewGroup && (
                        <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-indigo-700">
                          Latest
                        </span>
                      )}
                      <p className="text-xs font-semibold text-slate-800">
                        {group.length} hypothetical path{group.length !== 1 ? "s" : ""} · {horizonMo}-month horizon
                      </p>
                    </div>
                    <p className="mt-0.5 text-[11px] text-slate-500">
                      Baseline: {baselineValue ?? "—"} mL/min/1.73m² · {baselineLabel}
                    </p>
                  </div>
                  <span className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[10px] font-semibold text-slate-600 uppercase tracking-wide">
                    Linear model
                  </span>
                </div>

                {/* Recorded eGFR and linear scenario paths chart */}
                {baselineValue != null && group.length > 0 && (
                  <div className="mb-4">
                    <TrendChart
                      observations={observations}
                      scenarios={group}
                      measure="egfr"
                      specs={specs}
                      formatObservationDate={formatObservationDate}
                      observationCoordinate={observationCoordinate}
                      observationSortValue={observationSortValue}
                      formatUtcMonth={formatUtcMonth}
                      observationX={observationX}
                      valueY={valueY}
                    />
                  </div>
                )}

                {/* Scenario cards — compact table-like rows */}
                <div className="overflow-hidden rounded-xl border border-slate-200">
                  {/* Header row */}
                  <div className="grid grid-cols-[auto_1fr_1fr_1fr_auto] items-center gap-px bg-slate-200 text-[10px] font-bold uppercase tracking-wider text-slate-500 sm:gap-0">
                    <div className="bg-slate-50 px-3 py-2">Path</div>
                    <div className="bg-slate-50 px-3 py-2">Assumed rate</div>
                    <div className="bg-slate-50 px-3 py-2">eGFR at month {horizonMo}</div>
                    <div className="bg-slate-50 px-3 py-2">vs Scenario A</div>
                    <div className="bg-slate-50 px-3 py-2" />
                  </div>

                  {group.map((scenario, i) => {
                    const col = SCENARIO_COLORS[i % SCENARIO_COLORS.length];
                    const endPt = scenario.output.points.at(-1);
                    const refEnd = group[0]?.output.points.at(-1)?.value;
                    const diff =
                      i > 0 && endPt?.value != null && refEnd != null
                        ? endPt.value - refEnd
                        : null;
                    const isRef = i === 0;

                    return (
                      <div
                        key={scenario.id}
                        className="grid grid-cols-[auto_1fr_1fr_1fr_auto] items-center border-t border-slate-100 bg-white text-xs transition hover:bg-slate-50"
                      >
                        {/* Label swatch */}
                        <div className="px-3 py-3">
                          <span className={`rounded-md px-2 py-1 text-[10px] font-bold uppercase tracking-wider ${col.bg} ${col.text}`}>
                            {String.fromCharCode(65 + i)}
                          </span>
                        </div>

                        {/* Rate */}
                        <div className="px-3 py-3">
                          <span className="font-mono font-semibold text-slate-900">
                            {scenario.assumptions.rate_per_year >= 0 ? "+" : ""}
                            {scenario.assumptions.rate_per_year}
                          </span>
                          <span className="ml-1 text-[10px] text-slate-500">mL/min/yr</span>
                          {isRef && (
                            <span className="ml-2 text-[10px] text-slate-400">(reference)</span>
                          )}
                        </div>

                        {/* Endpoint */}
                        <div className="px-3 py-3">
                          <span className="font-mono font-semibold text-slate-900">
                            {endPt?.value?.toFixed(1) ?? "—"}
                          </span>
                          <span className="ml-1 text-[10px] text-slate-500">mL/min/1.73m²</span>
                        </div>

                        {/* Difference from A */}
                        <div className="px-3 py-3">
                          {diff != null ? (
                            <span
                              className={`font-mono font-semibold ${
                                diff < 0 ? "text-rose-700" : diff > 0 ? "text-emerald-700" : "text-slate-500"
                              }`}
                            >
                              {diff >= 0 ? "+" : ""}
                              {diff.toFixed(1)}
                            </span>
                          ) : isRef ? (
                            <span className="text-[10px] text-slate-400">—</span>
                          ) : (
                            <span className="text-[10px] text-slate-400">—</span>
                          )}
                        </div>

                        {/* Remove */}
                        <div className="px-2 py-3">
                          <button
                            type="button"
                            onClick={() => void deleteScenario(scenario.id)}
                            disabled={deletingScenarioId !== null}
                            aria-label={`Remove scenario ${String.fromCharCode(65 + i)}`}
                            className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600 disabled:cursor-wait disabled:opacity-50 transition"
                          >
                            {deletingScenarioId === scenario.id ? (
                              <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Trash2 className="h-3.5 w-3.5" />
                            )}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Warnings */}
                {(() => {
                  const uniqueWarnings = Array.from(
                    new Set(group.flatMap((s) => s.output.warnings))
                  );
                  if (uniqueWarnings.length === 0) return null;
                  return (
                    <div className="mt-2 space-y-1">
                      {uniqueWarnings.map((w, idx) => (
                        <p
                          key={`warning-${refScenario.id}-${idx}`}
                          className="flex items-start gap-1.5 text-[11px] text-amber-800"
                        >
                          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
                          {w}
                        </p>
                      ))}
                    </div>
                  );
                })()}

                {/* Disclaimer */}
                <p className="mt-2.5 text-[11px] leading-4 text-slate-500">
                  Mathematical illustration only. Not a validated clinical forecast, diagnosis, or treatment recommendation.
                  Rates are user-supplied assumptions, not inferred from the patient's observed progression.
                </p>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

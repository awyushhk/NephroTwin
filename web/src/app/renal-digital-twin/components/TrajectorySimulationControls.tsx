"use client";

import { FormEvent } from "react";
import { Activity, ArrowRight, LoaderCircle } from "lucide-react";
import type {
  TrajectoryEligibility,
  Observation,
  ObservationDateFields,
} from "../types";

export function TrajectorySimulationControls({
  patientId,
  scenarioBase,
  setScenarioBase,
  trajectoryYears,
  setTrajectoryYears,
  setTrajectoryResult,
  trajectoryInputsAvailable,
  trajectoryEligibilityLoading,
  trajectoryLoading,
  eGfrObservations,
  trajectoryEligibility,
  formatObservationDate,
  runTrajectorySimulation,
  inputClassName,
  primaryButtonClassName,
}: {
  patientId: number | "";
  scenarioBase: string;
  setScenarioBase: (id: string) => void;
  trajectoryYears: string;
  setTrajectoryYears: (years: string) => void;
  setTrajectoryResult: (val: null) => void;
  trajectoryInputsAvailable: boolean;
  trajectoryEligibilityLoading: boolean;
  trajectoryLoading: boolean;
  eGfrObservations: Observation[];
  trajectoryEligibility: TrajectoryEligibility | null;
  formatObservationDate: (row: ObservationDateFields, withTime?: boolean) => string;
  runTrajectorySimulation: (event: FormEvent<HTMLFormElement>) => void;
  inputClassName: string;
  primaryButtonClassName: string;
}) {
  return (
    <section
      aria-labelledby="simulation-controls-heading"
      className="rounded-2xl border border-violet-200/80 bg-gradient-to-br from-violet-50/40 via-white to-slate-50/50 p-4 shadow-xs sm:p-5"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-violet-100 pb-3">
        <div>
          <h3 id="simulation-controls-heading" className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <Activity className="h-4 w-4 text-violet-700" />
            Simulation Parameters
          </h3>
          <p className="text-xs text-slate-500">
            Configure the index baseline observation and simulation forecasting horizon.
          </p>
        </div>
        <span className="text-[11px] font-medium text-violet-800 bg-violet-100/70 rounded-full px-2.5 py-1">
          Horizon: {trajectoryYears} {Number(trajectoryYears) === 1 ? "year" : "years"}
        </span>
      </div>

      <form onSubmit={(event) => void runTrajectorySimulation(event)} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {/* Baseline Observation Picker */}
          <div className="lg:col-span-1">
            <label htmlFor="trajectory-baseline" className="block text-xs font-bold text-slate-700">
              Selected eGFR baseline / index date
            </label>
            <select
              id="trajectory-baseline"
              className={inputClassName}
              required
              value={scenarioBase}
              onChange={(event) => {
                setScenarioBase(event.target.value);
                setTrajectoryResult(null);
              }}
              disabled={eGfrObservations.length === 0 || trajectoryLoading}
            >
              <option value="">Choose an eGFR observation</option>
              {eGfrObservations.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.value} {row.unit} · {formatObservationDate(row, true)}
                </option>
              ))}
            </select>
            {trajectoryEligibility?.baseline && (
              <p className="mt-1.5 text-[11px] font-medium text-slate-500">
                Index date: {formatObservationDate(trajectoryEligibility.baseline, true)}
              </p>
            )}
          </div>

          {/* Horizon Picker */}
          <div className="lg:col-span-1">
            <label htmlFor="trajectory-horizon" className="block text-xs font-bold text-slate-700">
              Simulation horizon
            </label>
            <select
              id="trajectory-horizon"
              className={inputClassName}
              value={trajectoryYears}
              onChange={(event) => setTrajectoryYears(event.target.value)}
            >
              {[1, 5, 10, 15].map((years) => (
                <option key={years} value={years}>
                  {years} {years === 1 ? "year" : "years"}
                </option>
              ))}
            </select>
            <div className="mt-1.5 flex items-center gap-1.5">
              {[1, 5, 10, 15].map((years) => (
                <button
                  key={years}
                  type="button"
                  onClick={() => setTrajectoryYears(String(years))}
                  className={`rounded-lg px-2.5 py-1 text-[11px] font-medium transition ${
                    Number(trajectoryYears) === years
                      ? "border border-violet-600 bg-violet-600 text-white font-semibold shadow-2xs"
                      : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {years}y
                </button>
              ))}
            </div>
          </div>

          {/* Primary Run Action */}
          <div className="flex flex-col justify-end sm:col-span-2 lg:col-span-1">
            <button
              type="submit"
              className={`${primaryButtonClassName} w-full bg-violet-700 hover:bg-violet-800 shadow-sm`}
              disabled={!patientId || !scenarioBase || !trajectoryInputsAvailable || trajectoryEligibilityLoading || trajectoryLoading}
            >
              {trajectoryLoading ? (
                <LoaderCircle className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowRight className="h-4 w-4" />
              )}
              {trajectoryLoading ? "Running simulation…" : "Run trajectory simulation"}
            </button>
            <p className="mt-1.5 text-[11px] text-slate-500">
              Uses recorded inputs at or before this eGFR date. Stale or ambiguous inputs block the run.
            </p>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200/70 bg-slate-50/80 px-3 py-2 text-[11px] text-slate-500">
          Research simulation using bundled defaults; no patient-specific fitting or treatment effect.
        </div>
      </form>
    </section>
  );
}

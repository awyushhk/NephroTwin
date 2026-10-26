"use client";

import { AlertTriangle, ChevronDown, Info, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ObservationDateFields, TrajectorySimulationResult } from "../types";
import { MechanisticTrajectoryPlot } from "./MechanisticTrajectoryPlot";
import { TrajectoryCategoryChanges } from "./TrajectoryCategoryChanges";
import { TrajectoryMilestones } from "./TrajectoryMilestones";

function ScenarioSummaryCard({
  metric,
  unit,
  scenario,
  summary,
  horizon,
  endpointDifference,
  endpointPercentDifference,
  trajectoryNumber,
}: {
  metric: "eGFR" | "UACR";
  unit: string;
  scenario: "No treatment" | "SGLT2i-informed scenario";
  summary: TrajectorySimulationResult["analysis"]["egfr"];
  horizon: number;
  endpointDifference?: number;
  endpointPercentDifference?: number | null;
  trajectoryNumber: (value: number | null, digits?: number) => string;
}) {
  const treatment = scenario === "SGLT2i-informed scenario";
  const accent = treatment ? "text-emerald-700" : "text-rose-700";
  const dot = treatment ? "bg-emerald-600" : "bg-rose-600";
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-2xs">
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2">
        <div className="flex items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-full ${dot}`} />
          <h4 className="text-xs font-bold uppercase tracking-wide text-slate-900">Simulated {metric} · {scenario}</h4>
        </div>
        <span className="font-mono text-xs font-semibold text-slate-500">{unit}</span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
        <div className="rounded-lg border border-slate-100 bg-slate-50 p-2.5">
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Start → Year {horizon}</p>
          <p className="mt-1 font-mono text-sm font-bold text-slate-900">{trajectoryNumber(summary.starting)} → <span className={accent}>{trajectoryNumber(summary.final)}</span></p>
        </div>
        <div className="rounded-lg border border-slate-100 bg-slate-50 p-2.5">
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Total change</p>
          <p className="mt-1 font-mono text-sm font-bold text-slate-900">{summary.absolute_change == null ? "—" : `${summary.absolute_change >= 0 ? "+" : ""}${trajectoryNumber(summary.absolute_change)}`}{summary.percent_change == null ? "" : <span className="ml-1 text-[11px] font-normal text-slate-500">({summary.percent_change >= 0 ? "+" : ""}{trajectoryNumber(summary.percent_change, 1)}%)</span>}</p>
        </div>
        <div className="rounded-lg border border-slate-100 bg-slate-50 p-2.5">
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Average / year</p>
          <p className="mt-1 font-mono text-sm font-bold text-slate-900">{summary.average_annualized_change == null ? "—" : `${summary.average_annualized_change >= 0 ? "+" : ""}${trajectoryNumber(summary.average_annualized_change)}/yr`}</p>
        </div>
      </div>
      {endpointDifference != null && <p className="mt-2 text-xs font-semibold text-emerald-800">Endpoint difference vs no treatment: {endpointDifference >= 0 ? "+" : ""}{trajectoryNumber(endpointDifference)}{endpointPercentDifference == null ? "" : ` (${endpointPercentDifference >= 0 ? "+" : ""}${trajectoryNumber(endpointPercentDifference, 1)}%)`}</p>}
    </article>
  );
}

export function TrajectoryForecastDashboard({
  trajectoryResultForPatient,
  formatObservationDate,
  trajectoryNumber,
}: {
  trajectoryResultForPatient: TrajectorySimulationResult;
  formatObservationDate: (row: ObservationDateFields, withTime?: boolean) => string;
  trajectoryNumber: (value: number | null, digits?: number) => string;
}) {
  const noTreatment = trajectoryResultForPatient.scenarios.no_treatment;
  const treatment = trajectoryResultForPatient.scenarios.hypothetical_treatment;
  const [showTreatmentInfo, setShowTreatmentInfo] = useState(false);
  const infoTriggerRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const dialogCloseRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!showTreatmentInfo) return;
    const trigger = infoTriggerRef.current;
    dialogCloseRef.current?.focus();
    const handleOutsidePointerDown = (event: PointerEvent) => {
      if (dialogRef.current && !dialogRef.current.contains(event.target as Node)) {
        setShowTreatmentInfo(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setShowTreatmentInfo(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), a[href], input:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("pointerdown", handleOutsidePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handleOutsidePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
      trigger?.focus();
    };
  }, [showTreatmentInfo]);
  return (
    <div className="space-y-6">
      {/* Overview Banner with Unified Forecast Summary */}
      <div className="rounded-2xl border border-violet-200/80 bg-gradient-to-r from-violet-50/50 via-slate-50/30 to-white p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-violet-100/80 pb-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-violet-700 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">
                Forecast Result
              </span>
              <h3 className="text-base font-bold text-slate-900">
                Treatment Scenario Comparison · {trajectoryResultForPatient.horizon_years} Years
              </h3>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              Index baseline: {formatObservationDate(trajectoryResultForPatient.eligibility.baseline ?? { observed_date: trajectoryResultForPatient.index_date }, true)}
            </p>
          </div>

          <div className="flex flex-wrap gap-2 text-xs font-semibold">
            <span className="rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1 text-rose-800">No treatment</span>
            <span className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-emerald-900">
              SGLT2i-informed scenario
              <button
                ref={infoTriggerRef}
                type="button"
                onClick={() => setShowTreatmentInfo(true)}
                aria-haspopup="dialog"
                aria-expanded={showTreatmentInfo}
                aria-label="About the SGLT2i-informed scenario"
                title="About the SGLT2i-informed scenario"
                className="rounded-full text-emerald-800 hover:bg-emerald-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
              >
                <Info className="h-4 w-4" aria-hidden="true" />
              </button>
            </span>
          </div>
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <ScenarioSummaryCard metric="eGFR" unit={noTreatment.analysis.egfr.unit} scenario="No treatment" summary={noTreatment.analysis.egfr} horizon={trajectoryResultForPatient.horizon_years} trajectoryNumber={trajectoryNumber} />
          <ScenarioSummaryCard metric="eGFR" unit={treatment.analysis.egfr.unit} scenario="SGLT2i-informed scenario" summary={treatment.analysis.egfr} horizon={trajectoryResultForPatient.horizon_years} endpointDifference={trajectoryResultForPatient.comparison.egfr_endpoint_difference} trajectoryNumber={trajectoryNumber} />
          <ScenarioSummaryCard metric="UACR" unit={noTreatment.analysis.uacr.unit} scenario="No treatment" summary={noTreatment.analysis.uacr} horizon={trajectoryResultForPatient.horizon_years} trajectoryNumber={trajectoryNumber} />
          <ScenarioSummaryCard metric="UACR" unit={treatment.analysis.uacr.unit} scenario="SGLT2i-informed scenario" summary={treatment.analysis.uacr} horizon={trajectoryResultForPatient.horizon_years} endpointDifference={trajectoryResultForPatient.comparison.uacr_endpoint_difference} endpointPercentDifference={trajectoryResultForPatient.comparison.uacr_endpoint_percent_difference} trajectoryNumber={trajectoryNumber} />
        </div>
      </div>

      {/* Visualizations and Categorization Grid */}
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(300px,0.9fr)]">
        {/* Charts Column */}
        <div className="space-y-6">
          <MechanisticTrajectoryPlot series={[
            { ...noTreatment, color: "#dc2626" },
            { ...treatment, label: "SGLT2i-informed scenario", color: "#16a34a" },
          ]} metric="egfr" horizon={trajectoryResultForPatient.horizon_years} />
          <MechanisticTrajectoryPlot series={[
            { ...noTreatment, color: "#dc2626" },
            { ...treatment, label: "SGLT2i-informed scenario", color: "#16a34a" },
          ]} metric="uacr" horizon={trajectoryResultForPatient.horizon_years} />
        </div>

        {/* Analytics Sidebar */}
        <div className="space-y-6">
          <TrajectoryCategoryChanges trajectoryResult={trajectoryResultForPatient} />
          <TrajectoryMilestones trajectoryResult={trajectoryResultForPatient} />
        </div>
      </div>

      {/* Technical Details, Limitations and Warnings */}
      <div className="space-y-3 pt-2">
        <details className="group rounded-2xl border border-slate-200 bg-slate-50/60 p-4 text-xs text-slate-600 transition">
          <summary className="cursor-pointer font-bold text-slate-800 flex items-center justify-between select-none">
            <span>Calculation and model limitations</span>
            <ChevronDown className="h-4 w-4 text-slate-500 transition group-open:rotate-180" />
          </summary>
          <div className="mt-3 space-y-2 border-t border-slate-200/80 pt-3 text-xs leading-5">
            <p className="font-semibold text-slate-800">
              {trajectoryResultForPatient.analysis.calculation} {trajectoryResultForPatient.analysis.crossing_method}
            </p>
            {trajectoryResultForPatient.limitations.map((limitation) => (
              <p key={limitation} className="text-slate-600">
                • {limitation}
              </p>
            ))}
            <div className="rounded-xl border border-violet-100 bg-violet-50/50 p-3 text-violet-900 text-[11px] leading-4">
              The no-treatment series uses u=0; the SGLT2i-informed scenario uses u=1 with bundled treatment-effect parameters. The model does not represent a prescription, acute eGFR dip, or individual treatment response. Results are research simulations and are not saved as patient observations.
            </div>
          </div>
        </details>

        {trajectoryResultForPatient.warnings.map((warning) => (
          <div
            key={warning}
            className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900 flex items-start gap-2"
          >
            <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
            <span>{warning}</span>
          </div>
        ))}
      </div>

      {showTreatmentInfo && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/50 p-4">
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="treatment-info-title"
            aria-describedby="treatment-info-description"
            className="max-h-[min(90dvh,48rem)] w-full max-w-2xl overflow-y-auto rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl sm:p-6"
          >
            <div className="flex items-start justify-between gap-4 border-b border-slate-100 pb-3">
              <h2 id="treatment-info-title" className="text-lg font-bold text-slate-900">About the SGLT2i-Informed Scenario</h2>
              <button
                ref={dialogCloseRef}
                type="button"
                onClick={() => setShowTreatmentInfo(false)}
                aria-label="Close scenario information"
                className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-700"
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>
            <div id="treatment-info-description" className="mt-4 space-y-4 text-sm leading-6 text-slate-700">
              <section>
                <h3 className="font-semibold text-slate-900">What is SGLT2i?</h3>
                <p>SGLT2 inhibitors are a class of medicines used to treat type 2 diabetes that can also help protect kidney function in eligible patients.</p>
              </section>
              <section>
                <h3 className="font-semibold text-slate-900">What does this comparison show?</h3>
                <p>The graphs compare two simulated kidney-function trajectories from the same baseline:</p>
                <ul className="mt-1 list-disc space-y-1 pl-5">
                  <li><strong>No treatment:</strong> The model&apos;s baseline projection.</li>
                  <li><strong>SGLT2i-informed scenario:</strong> The model projection with treatment-effect assumptions enabled.</li>
                </ul>
              </section>
              <section>
                <h3 className="font-semibold text-slate-900">How is the treatment modeled?</h3>
                <p>The model applies configured treatment effects to eGFR progression and UACR. The UACR treatment effect begins at the start of the simulation. Acute eGFR changes associated with treatment initiation are not included.</p>
              </section>
              <section>
                <h3 className="font-semibold text-slate-900">Important note</h3>
                <p>This is an illustrative model scenario, not a personalized treatment prediction. The results depend on the model&apos;s assumptions and do not guarantee an individual treatment benefit. Treatment decisions should be made with a healthcare professional.</p>
              </section>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

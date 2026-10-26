"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  HeartPulse,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { ApiError, renalTwinRequest } from "@/lib/api";
import type {
  ChartObservation,
  ExamplePatient,
  Measurement,
  MeasurementType,
  Observation,
  ObservationDateFields,
  Patient,
  Scenario,
  ScenarioComparisonMetadata,
  ScenarioDraft,
  TrajectoryEligibility,
  TrajectoryEligibilityState,
  TrajectorySimulationResult,
  TwinState,
} from "./types";
import { CurrentRenalState } from "./components/CurrentRenalState";
import { LinearScenarioSimulator } from "./components/LinearScenarioSimulator";
import { ObservationTimeline, TIMELINE_PAGE_SIZE } from "./components/ObservationTimeline";
import { PatientSelector } from "./components/PatientSelector";
import { TrajectoryForecastDashboard } from "./components/TrajectoryForecastDashboard";
import { TrajectoryInputReadiness } from "./components/TrajectoryInputReadiness";
import { TrajectorySimulationControls } from "./components/TrajectorySimulationControls";
import type { MeasurementSpec } from "./components/TrendChart";

function readScenarioComparisonMetadata(patientId: number): Record<number, ScenarioComparisonMetadata> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(`renal_digital_twin_scenario_comparison_metadata_${patientId}`);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    return Object.fromEntries(
      Object.entries(parsed)
        .map(([id, meta]) => {
          if (!meta || typeof meta !== "object") return null;
          const candidate = meta as Record<string, unknown>;
          if (
            typeof candidate.comparison_group_id !== "string" ||
            typeof candidate.scenario_label !== "string" ||
            typeof candidate.comparison_index !== "number"
          ) {
            return null;
          }
          return [Number(id), candidate as ScenarioComparisonMetadata];
        })
        .filter((entry): entry is [number, ScenarioComparisonMetadata] => entry !== null),
    );
  } catch {
    return {};
  }
}

function persistScenarioComparisonMetadata(
  patientId: number,
  metadataByScenarioId: Record<number, ScenarioComparisonMetadata>,
) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      `renal_digital_twin_scenario_comparison_metadata_${patientId}`,
      JSON.stringify(metadataByScenarioId),
    );
  } catch {
    // Ignore localStorage write failures in degraded storage contexts.
  }
}

function deleteScenarioComparisonMetadata(patientId: number, scenarioId: number) {
  const current = readScenarioComparisonMetadata(patientId);
  if (!(scenarioId in current)) return;
  const updated = { ...current };
  delete updated[scenarioId];
  persistScenarioComparisonMetadata(patientId, updated);
}

function formatDate(value?: string | null, withTime = false) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  if (!withTime) {
    return `${year}-${month}-${day}`;
  }
  const hours = String(date.getUTCHours()).padStart(2, "0");
  const minutes = String(date.getUTCMinutes()).padStart(2, "0");
  return `${year}-${month}-${day} ${hours}:${minutes} UTC`;
}

function formatObservationDate(row: ObservationDateFields, withTime = false) {
  if (row.timestamp_precision === "date_only") return formatDate(row.observed_date, false);
  return formatDate(row.observed_at ?? row.observed_date, withTime);
}

function observationCoordinate(row: ObservationDateFields, calendarDateAxis = false) {
  if (calendarDateAxis && row.observed_date) {
    const [y, m, d] = row.observed_date.split("-").map(Number);
    return Date.UTC(y, m - 1, d, 12, 0, 0);
  }
  return new Date(row.observed_at ?? row.observed_date ?? 0).getTime();
}

function observationSortValue(row: ObservationDateFields) {
  return observationCoordinate(row, row.timestamp_precision === "date_only");
}

function formatUtcMonth(value: number) {
  const date = new Date(value);
  return date.toLocaleDateString(undefined, {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

function observationX(value: string, start: number, span: number) {
  const time = new Date(value).getTime();
  return 58 + ((time - start) / span) * 666;
}

function valueY(value: number, low: number, high: number) {
  return 238 - ((value - low) / (high - low)) * 196;
}

function trajectoryNumber(value: number | null, digits = 2) {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

const specs: Record<MeasurementType, MeasurementSpec> = {
  egfr: { label: "eGFR", short: "eGFR", unit: "mL/min/1.73m²", color: "#0f766e", decimals: 1 },
  creatinine: { label: "Serum creatinine", short: "Creatinine", unit: "mg/dL", color: "#2563eb", decimals: 2 },
  acr: { label: "Urine ACR", short: "ACR", unit: "mg/g", color: "#7c3aed", decimals: 1 },
  bun: { label: "Blood urea nitrogen", short: "BUN", unit: "mg/dL", color: "#d97706", decimals: 1 },
  potassium: { label: "Serum potassium", short: "Potassium", unit: "mEq/L", color: "#dc2626", decimals: 2 },
  bicarbonate: { label: "Serum bicarbonate", short: "Bicarbonate", unit: "mEq/L", color: "#059669", decimals: 1 },
  urine_albumin: { label: "Urine albumin", short: "UAlb", unit: "mg/L", color: "#9333ea", decimals: 1 },
  urine_creatinine: { label: "Urine creatinine", short: "UCreat", unit: "mg/dL", color: "#4f46e5", decimals: 1 },
  systolic_bp: { label: "Systolic blood pressure", short: "Systolic BP", unit: "mmHg", color: "#b91c1c", decimals: 0 },
  diastolic_bp: { label: "Diastolic blood pressure", short: "Diastolic BP", unit: "mmHg", color: "#c2410c", decimals: 0 },
  hba1c: { label: "HbA1c (%)", short: "HbA1c", unit: "%", color: "#be123c", decimals: 1 },
};

const input =
  "mt-1.5 w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-800 outline-none transition focus:border-teal-600 focus:ring-4 focus:ring-teal-100 disabled:bg-slate-100 disabled:text-slate-400";
const primaryButton =
  "inline-flex items-center justify-center gap-2 rounded-xl bg-teal-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-teal-800 focus:outline-none focus:ring-4 focus:ring-teal-100 disabled:cursor-not-allowed disabled:opacity-50";
const panel = "rounded-3xl border border-slate-200/80 bg-white shadow-xs";

export default function RenalDigitalTwinPage() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [examplePatients, setExamplePatients] = useState<ExamplePatient[]>([]);
  const [examplePatientsLoading, setExamplePatientsLoading] = useState(true);
  const [examplePatientsError, setExamplePatientsError] = useState("");
  const [patientId, setPatientId] = useState<number | "">("");
  const [observations, setObservations] = useState<Observation[]>([]);
  const [chartObservations, setChartObservations] = useState<Observation[]>([]);
  const [timelineRows, setTimelineRows] = useState<Observation[]>([]);
  const [timelinePage, setTimelinePage] = useState(0);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [twin, setTwin] = useState<TwinState | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [simulatorMode, setSimulatorMode] = useState<"linear" | "mechanistic">("linear");
  const [trajectoryYears, setTrajectoryYears] = useState("10");
  const [trajectoryLoading, setTrajectoryLoading] = useState(false);
  const [trajectoryResult, setTrajectoryResult] = useState<TrajectorySimulationResult | null>(null);
  const [trajectoryEligibilityState, setTrajectoryEligibilityState] = useState<TrajectoryEligibilityState | null>(null);
  const [trajectoryEligibilityLoading, setTrajectoryEligibilityLoading] = useState(false);
  const [analysisWindowDays, setAnalysisWindowDays] = useState("all");
  const [measurementFilter, setMeasurementFilter] = useState<MeasurementType>("egfr");
  const [kind, setKind] = useState<MeasurementType>("egfr");
  const [value, setValue] = useState("");
  const [observedAt, setObservedAt] = useState("");
  const [source, setSource] = useState("");
  const [patientCode, setPatientCode] = useState("");
  const [savingObservation, setSavingObservation] = useState(false);
  const [creatingPatient, setCreatingPatient] = useState(false);
  const [deletingScenarioId, setDeletingScenarioId] = useState<number | null>(null);
  const [scenarioBase, setScenarioBase] = useState("");
  const [scenarioDrafts, setScenarioDrafts] = useState<ScenarioDraft[]>([
    { key: "default-a", rate: "-1.0" },
    { key: "default-b", rate: "-3.5" },
  ]);
  const [horizon, setHorizon] = useState("12");
  const [loadingPatients, setLoadingPatients] = useState(true);
  const [loadingPatient, setLoadingPatient] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [savingScenario, setSavingScenario] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const selectedPatient = useMemo(
    () => patients.find((item) => item.id === patientId),
    [patientId, patients],
  );

  const refreshPatients = useCallback(async () => {
    setLoadingPatients(true);
    try {
      const data = await renalTwinRequest<Patient[]>("/patients?limit=50");
      setPatients(data);
      if (data.length && patientId === "") {
        setPatientId(data[0].id);
      }
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Failed to load patient profiles.",
      );
    } finally {
      setLoadingPatients(false);
    }
  }, [patientId]);

  const refreshExamplePatients = useCallback(async () => {
    setExamplePatientsLoading(true);
    setExamplePatientsError("");
    try {
      const data = await renalTwinRequest<ExamplePatient[]>("/patients/recommended-examples");
      setExamplePatients(data);
    } catch (err) {
      setExamplePatientsError(
        err instanceof ApiError ? err.message : "Failed to load example profiles.",
      );
    } finally {
      setExamplePatientsLoading(false);
    }
  }, []);

  const refreshPatient = useCallback(async () => {
    if (!patientId) return;
    setLoadingPatient(true);
    setError("");
    try {
      const [rows, state, savedScenarios] = await Promise.all([
        renalTwinRequest<Observation[]>(
          `/patients/${patientId}/observations?limit=500&recent=true`,
        ),
        renalTwinRequest<TwinState>(`/patients/${patientId}/state`),
        renalTwinRequest<Scenario[]>(`/patients/${patientId}/scenarios`),
      ]);
      const storedMetadata = readScenarioComparisonMetadata(patientId);
      const scenariosWithMetadata = savedScenarios.map((scenario) => {
        const metadata = storedMetadata[scenario.id];
        return {
          ...scenario,
          assumptions: {
            ...scenario.assumptions,
            comparison_group_id: scenario.assumptions.comparison_group_id ?? metadata?.comparison_group_id,
            scenario_label: scenario.assumptions.scenario_label ?? metadata?.scenario_label,
            comparison_index: scenario.assumptions.comparison_index ?? metadata?.comparison_index,
          },
        };
      });
      setObservations(rows);
      setTwin(state);
      setScenarios(scenariosWithMetadata);
      setScenarioBase((current) =>
        current && rows.some((row) => String(row.id) === current)
          ? current
          : String(
              rows.filter((row) => row.measurement_type === "egfr").at(-1)?.id ?? "",
            ),
      );
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Failed to load patient twin.",
      );
    } finally {
      setLoadingPatient(false);
    }
  }, [patientId]);

  useEffect(() => {
    void refreshPatients();
    void refreshExamplePatients();
  }, [refreshExamplePatients, refreshPatients]);

  useEffect(() => {
    void refreshPatient();
  }, [refreshPatient]);

  useEffect(() => {
    if (!patientId) return;
    let active = true;
    const fetchChart = async () => {
      try {
        const data = await renalTwinRequest<Observation[]>(
          `/patients/${patientId}/observations?measurement_type=${encodeURIComponent(measurementFilter)}&limit=500&offset=0&recent=true`,
        );
        if (active) setChartObservations(data);
      } catch (err) {
        if (active) {
          setError(
            err instanceof ApiError
              ? err.message
              : "Failed to load chart observations.",
          );
        }
      }
    };
    void fetchChart();
    return () => {
      active = false;
    };
  }, [measurementFilter, patientId]);

  useEffect(() => {
    if (!patientId) return;
    let active = true;
    setTimelineLoading(true);
    const fetchTimeline = async () => {
      try {
        const data = await renalTwinRequest<Observation[]>(
          `/patients/${patientId}/observations?measurement_type=${encodeURIComponent(measurementFilter)}&limit=${TIMELINE_PAGE_SIZE}&offset=${timelinePage * TIMELINE_PAGE_SIZE}&recent=true`,
        );
        if (active) setTimelineRows(data);
      } catch (err) {
        if (active) {
          setError(
            err instanceof ApiError
              ? err.message
              : "Failed to load timeline records.",
          );
        }
      } finally {
        if (active) setTimelineLoading(false);
      }
    };
    void fetchTimeline();
    return () => {
      active = false;
    };
  }, [measurementFilter, patientId, timelinePage]);

  useEffect(() => {
    if (!patientId || !scenarioBase || simulatorMode !== "mechanistic") {
      setTrajectoryEligibilityState(null);
      return;
    }
    let active = true;
    setTrajectoryEligibilityLoading(true);
    const fetchTrajectoryEligibility = async () => {
      try {
        const eligibility = await renalTwinRequest<TrajectoryEligibility>(
          `/patients/${patientId}/trajectory/eligibility?baseline_observation_id=${scenarioBase}`,
        );
        if (active) setTrajectoryEligibilityState({ patientId, baselineId: scenarioBase, report: eligibility });
      } catch {
        if (active) {
          setTrajectoryEligibilityState(null);
        }
      } finally {
        if (active) setTrajectoryEligibilityLoading(false);
      }
    };
    void fetchTrajectoryEligibility();
    return () => {
      active = false;
    };
  }, [patientId, scenarioBase, simulatorMode]);

  useEffect(() => {
    setTrajectoryResult(null);
  }, [patientId, scenarioBase]);

  const eGfrObservations = useMemo(
    () =>
      observations
        .filter((row) => row.measurement_type === "egfr")
        .slice()
        .sort((a, b) => observationSortValue(b) - observationSortValue(a)),
    [observations],
  );

  const trajectoryEligibility =
    trajectoryEligibilityState &&
    trajectoryEligibilityState.patientId === patientId &&
    trajectoryEligibilityState.baselineId === scenarioBase
      ? trajectoryEligibilityState.report
      : null;

  const trajectoryInputsAvailable = Boolean(trajectoryEligibility?.eligible);

  const trajectoryResultForPatient =
    trajectoryResult && trajectoryResult.patient_id === patientId
      ? trajectoryResult
      : null;

  async function runTrajectorySimulation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!patientId || !scenarioBase || !trajectoryInputsAvailable) return;
    setTrajectoryLoading(true);
    setTrajectoryResult(null);
    setError("");
    try {
      const result = await renalTwinRequest<TrajectorySimulationResult>(
        `/patients/${patientId}/trajectory`,
        {
          method: "POST",
          body: JSON.stringify({
            baseline_observation_id: Number(scenarioBase),
            horizon_years: Number(trajectoryYears),
          }),
        },
      );
      setTrajectoryResult(result);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Failed to run trajectory simulation.",
      );
    } finally {
      setTrajectoryLoading(false);
    }
  }

  async function recomputeState() {
    if (!patientId) return;
    setUpdating(true);
    setError("");
    setNotice("");
    try {
      const state = await renalTwinRequest<TwinState>(
        `/patients/${patientId}/state`,
        { method: "POST" },
      );
      setTwin(state);
      setNotice(
        "Current renal state recomputed from recent observations.",
      );
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Failed to update digital twin state.",
      );
    } finally {
      setUpdating(false);
    }
  }

  async function addObservation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!patientId || !observedAt) return;
    setSavingObservation(true);
    setError("");
    setNotice("");
    try {
      const numeric = Number(value);
      const row = await renalTwinRequest<Observation>(
        `/patients/${patientId}/observations`,
        {
          method: "POST",
          body: JSON.stringify({
            measurement_type: kind,
            value: numeric,
            unit: specs[kind].unit,
            observed_at: new Date(observedAt).toISOString(),
            source: source.trim() || undefined,
          }),
        },
      );
      setValue("");
      setObservedAt("");
      setSource("");
      setNotice(
        `Observation #${row.id} recorded. Recomputing current state…`,
      );
      await Promise.all([refreshPatient(), recomputeState()]);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Failed to record observation.",
      );
    } finally {
      setSavingObservation(false);
    }
  }

  async function createPatient(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreatingPatient(true);
    setError("");
    setNotice("");
    try {
      const patient = await renalTwinRequest<Patient>("/patients", {
        method: "POST",
        body: JSON.stringify({
          patient_code: patientCode.trim() || undefined,
        }),
      });
      setPatientCode("");
      setNotice(
        `Created patient ${patient.patient_code ?? patient.id}. Switch to it in the profile selector.`,
      );
      await refreshPatients();
      setPatientId(patient.id);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Failed to create patient profile.",
      );
    } finally {
      setCreatingPatient(false);
    }
  }

  async function saveScenario(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!patientId || !scenarioBase) return;
    const rates = scenarioDrafts.map((draft) => Number(draft.rate));
    if (
      scenarioDrafts.length < 2 ||
      scenarioDrafts.some((draft) => draft.rate.trim() === "") ||
      rates.some((value) => !Number.isFinite(value) || value < -30 || value > 30) ||
      new Set(rates).size !== rates.length
    ) {
      setError(
        "Enter a different valid yearly rate for each scenario (−30 to 30 mL/min/1.73m² per year). At least two scenarios are required.",
      );
      return;
    }
    setSavingScenario(true);
    setError("");
    setNotice("");
    const requestScenarios = scenarioDrafts.map((draft, index) => ({
      label: `Scenario ${String.fromCharCode(65 + index)}`,
      rate_per_year: Number(draft.rate),
    }));
    try {
      try {
        await renalTwinRequest(`/patients/${patientId}/scenarios/compare`, {
          method: "POST",
          body: JSON.stringify({
            baseline_observation_id: Number(scenarioBase),
            horizon_months: Number(horizon),
            scenarios: requestScenarios,
          }),
        });
        await refreshPatient();
        setNotice(
          "Comparison saved. Each hypothetical path remains separate from observed measurements.",
        );
      } catch (reason) {
        const comparisonRouteUnavailable =
          reason instanceof ApiError &&
          (reason.status === 404 || reason.status === 405) &&
          (reason.detail === "Not Found" || reason.detail === "Method Not Allowed");
        if (!comparisonRouteUnavailable) throw reason;

        const comparisonGroupId = crypto.randomUUID();
        const created: Scenario[] = [];
        try {
          for (const [index, item] of requestScenarios.entries()) {
            const scenario = await renalTwinRequest<Scenario>(
              `/patients/${patientId}/scenarios`,
              {
                method: "POST",
                body: JSON.stringify({
                  baseline_observation_id: Number(scenarioBase),
                  rate_per_year: item.rate_per_year,
                  horizon_months: Number(horizon),
                }),
              },
            );
            created.push({
              ...scenario,
              assumptions: {
                ...scenario.assumptions,
                comparison_group_id: comparisonGroupId,
                scenario_label: item.label,
                comparison_index: index,
              },
            });
          }
          await refreshPatient();
          setNotice(
            "Comparison saved. Each hypothetical path remains separate from observed measurements.",
          );
        } catch (saveError) {
          await Promise.allSettled(
            created.map((scenario) =>
              renalTwinRequest<void>(
                `/patients/${patientId}/scenarios/${scenario.id}`,
                { method: "DELETE" },
              ),
            ),
          );
          throw saveError;
        }
      }
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Failed to save scenario.",
      );
    } finally {
      setSavingScenario(false);
    }
  }

  async function deleteScenario(id: number) {
    if (!patientId) return;
    setDeletingScenarioId(id);
    setError("");
    try {
      await renalTwinRequest(`/patients/${patientId}/scenarios/${id}`, {
        method: "DELETE",
      });
      deleteScenarioComparisonMetadata(patientId, id);
      setScenarios((current) => current.filter((item) => item.id !== id));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        deleteScenarioComparisonMetadata(patientId, id);
        setScenarios((current) => current.filter((item) => item.id !== id));
        return;
      }
      setError(
        err instanceof ApiError ? err.message : "Failed to delete scenario.",
      );
    } finally {
      setDeletingScenarioId(null);
    }
  }

  async function deleteScenarioGroup(ids: number[]) {
    if (!patientId) return;
    setError("");
    // Delete all scenarios in the group sequentially; ignore 404s (already deleted)
    for (const id of ids) {
      try {
        await renalTwinRequest(`/patients/${patientId}/scenarios/${id}`, { method: "DELETE" });
        deleteScenarioComparisonMetadata(patientId, id);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          deleteScenarioComparisonMetadata(patientId, id);
        } else {
          setError(err instanceof ApiError ? err.message : "Failed to delete scenario group.");
          // Remove whatever was successfully deleted so far from state
          setScenarios((current) => current.filter((item) => !ids.includes(item.id)));
          return;
        }
      }
    }
    setScenarios((current) => current.filter((item) => !ids.includes(item.id)));
  }

  function loadExamplePatient(example: ExamplePatient) {
    setPatientId(example.id);
    setTimelinePage(0);
    setNotice("");
    setSimulatorMode("mechanistic");
    setTrajectoryResult(null);
  }

  const analysisBounds = useMemo(() => {
    const selectedRows = chartObservations.filter((row) => row.measurement_type === measurementFilter);
    if (!selectedRows.length) return undefined;
    const calendarDateAxis = selectedRows.some((row) => row.timestamp_precision === "date_only");
    const times = selectedRows.map((row) => observationCoordinate(row, calendarDateAxis));
    const max = Math.max(...times);
    if (analysisWindowDays === "all") {
      const min = Math.min(...times);
      return { start: min, end: max };
    }
    const days = Number(analysisWindowDays);
    const span = days * 86400000;
    return { start: max - span, end: max };
  }, [analysisWindowDays, chartObservations, measurementFilter]);

  const timelineChartObservations = useMemo(() => {
    if (!analysisBounds) return [];
    const selectedRows = chartObservations.filter((row) => row.measurement_type === measurementFilter);
    const calendarDateAxis = selectedRows.some((row) => row.timestamp_precision === "date_only");
    return selectedRows.filter((row) => {
      const time = observationCoordinate(row, calendarDateAxis);
      return Number.isFinite(time) && time >= analysisBounds.start && time <= analysisBounds.end;
    });
  }, [analysisBounds, chartObservations, measurementFilter]);

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6 pb-10">
      <header className="overflow-hidden rounded-3xl border border-teal-900/10 bg-gradient-to-br from-teal-950 via-teal-900 to-slate-900 p-6 text-white shadow-sm sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="max-w-3xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-semibold text-teal-50">
              <HeartPulse className="h-3.5 w-3.5" />
              Longitudinal renal record
            </div>
            <h1 className="mt-4 text-2xl font-bold tracking-tight sm:text-3xl">
              Renal Digital Twin
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-teal-50/80">
              Explore recorded kidney-related measurements over time, review the
              current descriptive state, and model an explicit what-if eGFR
              assumption.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-2 rounded-xl border border-emerald-200/20 bg-emerald-300/10 px-3 py-2 text-xs font-semibold text-emerald-100">
              <ShieldCheck className="h-4 w-4" />
              Research data
            </span>
            <button
              onClick={() => {
                void refreshPatients();
                void refreshPatient();
                void refreshExamplePatients();
              }}
              disabled={loadingPatients || loadingPatient}
              className="inline-flex items-center gap-2 rounded-xl border border-white/20 bg-white/10 px-3.5 py-2.5 text-sm font-semibold text-white transition hover:bg-white/15 disabled:opacity-50"
            >
              <RefreshCw
                className={`h-4 w-4 ${loadingPatients || loadingPatient ? "animate-spin" : ""}`}
              />
              Refresh data
            </button>
          </div>
        </div>
        <div className="mt-6 grid gap-3 border-t border-white/10 pt-5 sm:grid-cols-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-teal-100/60">
              Selected profile
            </p>
            <p className="mt-1 truncate text-sm font-semibold">
              {selectedPatient?.patient_code ??
                (loadingPatients
                  ? "Loading profiles…"
                  : "Choose a profile below")}
            </p>
          </div>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-teal-100/60">
              Visible observations
            </p>
            <p className="mt-1 text-sm font-semibold">
              {selectedPatient?.observation_count.toLocaleString() ?? "—"} total
              · latest {observations.length} loaded
            </p>
          </div>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-teal-100/60">
              Latest recorded time
            </p>
            <p className="mt-1 text-sm font-semibold">
              {formatDate(
                twin?.latest_observation_at ??
                  twin?.measurements?.egfr?.latest?.observed_at,
                true,
              )}
            </p>
          </div>
        </div>
      </header>

      {selectedPatient?.source_system === "MIMIC-IV-v3.1" && (
        <div role="note" className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-950">
          MIMIC-IV dates are de-identified and shifted; they are not real-world calendar dates. Source chart times have no timezone. Dates here are shown in UTC to preserve the stored source clock time.
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-semibold">Could not complete the request</p>
            <p className="mt-1 text-rose-800">{error}</p>
          </div>
          <button
            onClick={() => {
              void refreshPatients();
              void refreshPatient();
            }}
            className="ml-auto text-xs font-semibold underline"
          >
            Retry
          </button>
        </div>
      )}
      {notice && (
        <div
          role="status"
          className="rounded-xl border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-900"
        >
          {notice}
        </div>
      )}

      <PatientSelector
        patients={patients}
        patientId={patientId}
        setPatientId={setPatientId}
        loadingPatients={loadingPatients}
        examplePatients={examplePatients}
        examplePatientsLoading={examplePatientsLoading}
        examplePatientsError={examplePatientsError}
        loadExamplePatient={loadExamplePatient}
        patientCode={patientCode}
        setPatientCode={setPatientCode}
        createPatient={createPatient}
        creatingPatient={creatingPatient}
        kind={kind}
        setKind={setKind}
        value={value}
        setValue={setValue}
        observedAt={observedAt}
        setObservedAt={setObservedAt}
        source={source}
        setSource={setSource}
        addObservation={addObservation}
        savingObservation={savingObservation}
        specs={specs}
        setTimelinePage={setTimelinePage}
        setNotice={setNotice}
        inputClassName={input}
        primaryButtonClassName={primaryButton}
        panelClassName={panel}
      />

      <CurrentRenalState
        patientId={patientId}
        selectedPatient={selectedPatient}
        twin={twin}
        specs={specs}
        formatObservationDate={formatObservationDate}
        recomputeState={recomputeState}
        updating={updating}
        loadingPatient={loadingPatient}
        primaryButtonClassName={primaryButton}
      />

      <ObservationTimeline
        loadingPatient={loadingPatient}
        timelineChartObservations={timelineChartObservations}
        scenarios={[]}
        measurementFilter={measurementFilter}
        setMeasurementFilter={setMeasurementFilter}
        analysisWindowDays={analysisWindowDays}
        setAnalysisWindowDays={setAnalysisWindowDays}
        analysisBounds={analysisBounds}
        specs={specs}
        selectedMeasurement={specs[measurementFilter]}
        timelineLoading={timelineLoading}
        timelineRows={timelineRows}
        timelinePage={timelinePage}
        setTimelinePage={setTimelinePage}
        twin={twin}
        formatObservationDate={formatObservationDate}
        observationCoordinate={observationCoordinate}
        observationSortValue={observationSortValue}
        formatUtcMonth={formatUtcMonth}
        observationX={observationX}
        valueY={valueY}
      />

      {/* 03 · WHAT-IF SCENARIO SIMULATOR */}
      <section
        className={`${panel} overflow-hidden`}
        aria-labelledby="scenario-heading"
      >
        <div className="border-b border-violet-100 bg-gradient-to-r from-violet-50 via-white to-white p-5 sm:p-6">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-violet-100 p-2.5 text-violet-800">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-violet-800">
                03 · What-if
              </p>
              <h2
                id="scenario-heading"
                className="mt-1 text-xl font-bold text-slate-900"
              >
                What-if scenario simulator
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Model hypothetical paths starting from an actual baseline observation.
              </p>
            </div>
          </div>

          {/* Mode Switcher Segmented Control */}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-violet-100 pt-4">
            <div className="inline-flex rounded-xl bg-slate-100/90 p-1 border border-slate-200/80">
              <button
                type="button"
                aria-pressed={simulatorMode === "linear"}
                onClick={() => setSimulatorMode("linear")}
                className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition ${
                  simulatorMode === "linear"
                    ? "bg-white text-slate-900 shadow-xs border border-slate-200"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <span>Linear</span>
                <span className="text-[10px] text-slate-400 font-normal">Annual decline</span>
              </button>
              <button
                type="button"
                aria-pressed={simulatorMode === "mechanistic"}
                onClick={() => setSimulatorMode("mechanistic")}
                className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition ${
                  simulatorMode === "mechanistic"
                    ? "bg-violet-700 text-white shadow-xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <span>Trajectory Model</span>
                <span
                  className={`text-[10px] font-medium ${
                    simulatorMode === "mechanistic"
                      ? "text-violet-200"
                      : "text-slate-400"
                  }`}
                >
                  {trajectoryEligibilityLoading ? "· checking inputs" : trajectoryInputsAvailable ? "· eligible" : "· review required"}
                </span>
              </button>
            </div>

            <p className="text-xs text-slate-500">
              {simulatorMode === "linear"
                ? "Simulate explicit linear slope paths with custom annual rates."
                : "Simulate non-linear multi-biomarker progression using the Mechanistic ODE trajectory model."}
            </p>
          </div>
        </div>

        {simulatorMode === "linear" ? (
          <LinearScenarioSimulator
            patientId={patientId}
            scenarioBase={scenarioBase}
            setScenarioBase={setScenarioBase}
            eGfrObservations={eGfrObservations}
            formatObservationDate={formatObservationDate}
            scenarioDrafts={scenarioDrafts}
            setScenarioDrafts={setScenarioDrafts}
            horizon={horizon}
            setHorizon={setHorizon}
            saveScenario={saveScenario}
            savingScenario={savingScenario}
            scenarios={scenarios}
            observations={observations}
            deleteScenario={deleteScenario}
            deleteScenarioGroup={deleteScenarioGroup}
            deletingScenarioId={deletingScenarioId}
            inputClassName={input}
            primaryButtonClassName={primaryButton}
            specs={specs}
            observationCoordinate={observationCoordinate}
            observationSortValue={observationSortValue}
            formatUtcMonth={formatUtcMonth}
            observationX={observationX}
            valueY={valueY}
          />
        ) : (
          <div className="space-y-6 p-5 sm:p-6">
            <TrajectoryInputReadiness
              trajectoryEligibility={trajectoryEligibility}
              trajectoryEligibilityLoading={trajectoryEligibilityLoading}
              trajectoryInputsAvailable={trajectoryInputsAvailable}
              scenarioBase={scenarioBase}
              eGfrObservations={eGfrObservations}
              formatObservationDate={formatObservationDate}
            />

            <TrajectorySimulationControls
              patientId={patientId}
              scenarioBase={scenarioBase}
              setScenarioBase={setScenarioBase}
              trajectoryYears={trajectoryYears}
              setTrajectoryYears={setTrajectoryYears}
              setTrajectoryResult={setTrajectoryResult}
              trajectoryInputsAvailable={trajectoryInputsAvailable}
              trajectoryEligibilityLoading={trajectoryEligibilityLoading}
              trajectoryLoading={trajectoryLoading}
              eGfrObservations={eGfrObservations}
              trajectoryEligibility={trajectoryEligibility}
              formatObservationDate={formatObservationDate}
              runTrajectorySimulation={runTrajectorySimulation}
              inputClassName={input}
              primaryButtonClassName={primaryButton}
            />

            {trajectoryResultForPatient && (
              <TrajectoryForecastDashboard
                trajectoryResultForPatient={trajectoryResultForPatient}
                formatObservationDate={formatObservationDate}
                trajectoryNumber={trajectoryNumber}
              />
            )}
          </div>
        )}

        {simulatorMode === "linear" && eGfrObservations.length > 0 && (
          <div className="border-t border-slate-100 bg-slate-50/50 p-4 sm:p-5">
            <p className="text-xs font-semibold text-slate-700">
              Observed Timeline &amp; Scenarios
            </p>
            <p className="text-[11px] text-slate-500">
              Compare your saved hypothetical scenarios against actual recorded eGFR observations above.
            </p>
          </div>
        )}
      </section>
    </main>
  );
}

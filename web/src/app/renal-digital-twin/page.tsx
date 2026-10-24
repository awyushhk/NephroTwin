"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Clock3,
  ChevronLeft,
  ChevronRight,
  Database,
  HeartPulse,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { renalTwinRequest } from "@/lib/api";

type Patient = {
  id: number;
  patient_code: string | null;
  observation_count: number;
};
type Observation = {
  id: number;
  patient_id: number;
  measurement_type: string;
  value: number;
  unit: string;
  observed_at: string;
  source?: string | null;
};
type Measurement = {
  latest: {
    value: number;
    unit: string;
    observed_at: string;
    observation_id: number;
  } | null;
  previous: {
    value: number;
    observed_at: string;
    observation_id: number;
  } | null;
  count: number;
  elapsed_days?: number | null;
  change?: number | null;
  change_per_day?: number | null;
  age_days?: number | null;
  stale?: boolean;
  category: string | null;
};
type TwinState = {
  measurements: Record<string, Measurement>;
  warnings: string[];
  source_observation_ids: number[];
  data_completeness: {
    available_measurements: number;
    supported_measurements: number;
  };
  stale: boolean;
  clinical_note: string;
  latest_observation_at?: string | null;
};
type Scenario = {
  id: number;
  assumptions: { rate_per_year: number; step_months: number };
  horizon_months: number;
  output: { points: { month: number; value: number }[]; warnings: string[] };
  baseline_observation_id: number;
};
const specs: Record<
  string,
  { label: string; short: string; unit: string; color: string }
> = {
  egfr: {
    label: "Estimated GFR",
    short: "eGFR",
    unit: "mL/min/1.73m²",
    color: "#0f766e",
  },
  creatinine: {
    label: "Serum creatinine",
    short: "Creatinine",
    unit: "mg/dL",
    color: "#2563eb",
  },
  acr: { label: "Urine ACR", short: "ACR", unit: "mg/g", color: "#7c3aed" },
  bun: {
    label: "Blood urea nitrogen",
    short: "BUN",
    unit: "mg/dL",
    color: "#c2410c",
  },
  potassium: {
    label: "Potassium",
    short: "Potassium",
    unit: "mmol/L",
    color: "#db2777",
  },
  bicarbonate: {
    label: "Bicarbonate",
    short: "Bicarbonate",
    unit: "mmol/L",
    color: "#0891b2",
  },
  urine_albumin: {
    label: "Urine albumin",
    short: "Urine albumin",
    unit: "mg/dL",
    color: "#9333ea",
  },
  urine_creatinine: {
    label: "Urine creatinine",
    short: "Urine creatinine",
    unit: "mg/dL",
    color: "#4f46e5",
  },
  systolic_bp: {
    label: "Systolic blood pressure",
    short: "Systolic BP",
    unit: "mmHg",
    color: "#ea580c",
  },
  diastolic_bp: {
    label: "Diastolic blood pressure",
    short: "Diastolic BP",
    unit: "mmHg",
    color: "#65a30d",
  },
};

const panel = "rounded-2xl border border-slate-200 bg-white shadow-sm";
const input =
  "mt-1.5 w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 outline-none transition focus:border-teal-600 focus:ring-4 focus:ring-teal-100 disabled:bg-slate-100";
const primaryButton =
  "inline-flex items-center justify-center gap-2 rounded-xl bg-teal-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-50";
const TIMELINE_PAGE_SIZE = 10;

function formatDate(value?: string | null, withTime = false) {
  if (!value) return "—";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  return new Intl.DateTimeFormat(
    undefined,
    withTime
      ? { dateStyle: "medium", timeStyle: "short" }
      : { dateStyle: "medium" },
  ).format(date);
}

function observationX(value: string, start: number, span: number) {
  return 58 + ((new Date(value).getTime() - start) / span) * 666;
}

function valueY(value: number, low: number, high: number) {
  return 238 - ((value - low) / (high - low)) * 196;
}

function TrendChart({
  observations,
  scenarios,
  measure,
}: {
  observations: Observation[];
  scenarios: Scenario[];
  measure: string;
}) {
  const rows = useMemo(
    () =>
      observations
        .filter((row) => row.measurement_type === measure)
        .slice()
        .sort(
          (a, b) =>
            new Date(a.observed_at).getTime() -
            new Date(b.observed_at).getTime(),
        ),
    [measure, observations],
  );
  const actualScenarios = useMemo(
    () => (measure === "egfr" ? scenarios : []),
    [measure, scenarios],
  );
  const chart = useMemo(() => {
    const points = rows.map((row) => ({
      time: new Date(row.observed_at).getTime(),
      value: row.value,
    }));
    const baselineTimes = actualScenarios
      .map((scenario) => {
        const baseline = rows.find(
          (row) => row.id === scenario.baseline_observation_id,
        );
        return baseline
          ? new Date(baseline.observed_at).getTime() +
              scenario.horizon_months * 30.4375 * 86400000
          : null;
      })
      .filter((time): time is number => time !== null);
    const times = points.map((point) => point.time).concat(baselineTimes);
    const values = points
      .map((point) => point.value)
      .concat(
        actualScenarios.flatMap((scenario) =>
          scenario.output.points.map((point) => point.value),
        ),
      );
    if (!times.length || !values.length) return null;
    const start = Math.min(...times);
    const rawEnd = Math.max(...times);
    const end = rawEnd === start ? start + 86400000 : rawEnd;
    const rawLow = Math.min(...values);
    const rawHigh = Math.max(...values);
    const padding = Math.max(
      (rawHigh - rawLow) * 0.12,
      Math.abs(rawHigh) * 0.035,
      1,
    );
    const low = rawLow - padding;
    const high = rawHigh + padding;
    return { start, span: end - start, low, high, points };
  }, [actualScenarios, rows]);

  if (!chart || !rows.length) {
    return (
      <div className="flex min-h-72 flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-50 px-6 text-center">
        <Activity className="mb-3 h-8 w-8 text-slate-300" />
        <p className="text-sm font-semibold text-slate-700">
          No {specs[measure]?.short ?? measure} observations in this history
          window
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
    (_, index) => chart.low + ((chart.high - chart.low) * index) / 4,
  ).reverse();
  const timeTicks = Array.from(
    { length: 5 },
    (_, index) => chart.start + (chart.span * index) / 4,
  );
  const observedLine = chart.points
    .map(
      (point) =>
        `${observationX(new Date(point.time).toISOString(), chart.start, chart.span)},${valueY(point.value, chart.low, chart.high)}`,
    )
    .join(" ");

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-gradient-to-b from-slate-50 to-white p-3 sm:p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-slate-800">
            {specs[measure]?.label ?? measure} over recorded time
          </p>
          <p className="mt-0.5 text-xs text-slate-500">
            {rows.length} visible result{rows.length === 1 ? "" : "s"} ·{" "}
            {specs[measure]?.unit}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-600">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-teal-700" />
            Observed values
          </span>
          {actualScenarios.length > 0 && (
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0 w-5 border-t-2 border-dashed border-violet-600" />
              Hypothetical scenarios
            </span>
          )}
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
                  chart.span,
                )}
                x2={observationX(
                  new Date(tick).toISOString(),
                  chart.start,
                  chart.span,
                )}
                y1="42"
                y2="238"
                stroke="#f1f5f9"
              />
              <text
                x={observationX(
                  new Date(tick).toISOString(),
                  chart.start,
                  chart.span,
                )}
                y="260"
                textAnchor={
                  index === 0 ? "start" : index === 4 ? "end" : "middle"
                }
                fill="#64748b"
                fontSize="10"
              >
                {new Intl.DateTimeFormat(undefined, {
                  year: "numeric",
                  month: "short",
                }).format(new Date(tick))}
              </text>
            </g>
          ))}
          {rows.length > 1 && (
            <polyline
              points={observedLine}
              fill="none"
              stroke={specs[measure]?.color ?? "#0f766e"}
              strokeOpacity="0.2"
              strokeWidth="1.5"
            />
          )}
          {actualScenarios.map((scenario) => {
            const baseline = rows.find(
              (row) => row.id === scenario.baseline_observation_id,
            );
            if (!baseline) return null;
            const startTime = new Date(baseline.observed_at).getTime();
            const points = scenario.output.points
              .map((point) => {
                const time = startTime + point.month * 30.4375 * 86400000;
                return `${observationX(new Date(time).toISOString(), chart.start, chart.span)},${valueY(point.value, chart.low, chart.high)}`;
              })
              .join(" ");
            return (
              <polyline
                key={`scenario-${scenario.id}`}
                points={points}
                fill="none"
                stroke="#7c3aed"
                strokeWidth="2.5"
                strokeDasharray="7 5"
              >
                <title>Hypothetical scenario {scenario.id}</title>
              </polyline>
            );
          })}
          {rows.map((row) => (
            <circle
              key={row.id}
              cx={observationX(row.observed_at, chart.start, chart.span)}
              cy={valueY(row.value, chart.low, chart.high)}
              r="4.5"
              fill={specs[measure]?.color ?? "#0f766e"}
              stroke="white"
              strokeWidth="2"
            >
              <title>
                {formatDate(row.observed_at, true)} · {row.value} {row.unit} ·
                observation #{row.id}
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
        Markers represent source observations at their recorded timestamps. The
        faint guide between observed points does not imply daily measurements;
        dashed lines are mathematical scenarios, not observed results.
      </p>
    </div>
  );
}

function metricTrend(measurement: Measurement) {
  if (measurement.change == null) return null;
  if (measurement.change > 0)
    return (
      <span className="inline-flex items-center gap-1 text-amber-700">
        <ArrowUpRight className="h-3.5 w-3.5" />+
        {Number(measurement.change).toPrecision(3)} since prior
      </span>
    );
  if (measurement.change < 0)
    return (
      <span className="inline-flex items-center gap-1 text-teal-700">
        <ArrowDownRight className="h-3.5 w-3.5" />
        {Number(measurement.change).toPrecision(3)} since prior
      </span>
    );
  return <span className="text-slate-500">No change from prior result</span>;
}

export default function RenalDigitalTwinPage() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [patientId, setPatientId] = useState<number | "">("");
  const [observations, setObservations] = useState<Observation[]>([]);
  const [timelineRows, setTimelineRows] = useState<Observation[]>([]);
  const [timelinePage, setTimelinePage] = useState(0);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [twin, setTwin] = useState<TwinState | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [measurementFilter, setMeasurementFilter] = useState("egfr");
  const [kind, setKind] = useState("egfr");
  const [value, setValue] = useState("");
  const [observedAt, setObservedAt] = useState("");
  const [source, setSource] = useState("");
  const [patientCode, setPatientCode] = useState("");
  const [savingObservation, setSavingObservation] = useState(false);
  const [creatingPatient, setCreatingPatient] = useState(false);
  const [deletingScenarioId, setDeletingScenarioId] = useState<number | null>(
    null,
  );
  const [scenarioBase, setScenarioBase] = useState("");
  const [rate, setRate] = useState("-1");
  const [horizon, setHorizon] = useState("12");
  const [loadingPatients, setLoadingPatients] = useState(true);
  const [loadingPatient, setLoadingPatient] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [savingScenario, setSavingScenario] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const timelineMeasurementCount =
    twin?.measurements?.[measurementFilter]?.count;

  const refreshPatients = useCallback(async () => {
    setLoadingPatients(true);
    try {
      const rows = await renalTwinRequest<Patient[]>("/patients");
      setPatients(rows);
      setPatientId((current) => current || rows[0]?.id || "");
      setError("");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not load patient profiles.",
      );
    } finally {
      setLoadingPatients(false);
    }
  }, []);

  const refreshPatient = useCallback(async () => {
    if (!patientId) {
      setObservations([]);
      setTwin(null);
      setScenarios([]);
      return;
    }
    setLoadingPatient(true);
    try {
      const id = Number(patientId);
      const [rows, state, savedScenarios] = await Promise.all([
        renalTwinRequest<Observation[]>(
          `/patients/${id}/observations?limit=500&recent=true`,
        ),
        renalTwinRequest<TwinState>(`/patients/${id}/state`),
        renalTwinRequest<Scenario[]>(`/patients/${id}/scenarios`),
      ]);
      setObservations(rows);
      setTwin(state);
      setScenarios(savedScenarios);
      setScenarioBase((current) =>
        current && rows.some((row) => String(row.id) === current)
          ? current
          : String(
              rows.find((row) => row.measurement_type === "egfr")?.id ?? "",
            ),
      );
      setError("");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not load this patient’s renal history.",
      );
    } finally {
      setLoadingPatient(false);
    }
  }, [patientId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refreshPatients();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refreshPatients]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refreshPatient();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refreshPatient]);
  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(async () => {
      if (!patientId) {
        setTimelineRows([]);
        setTimelineLoading(false);
        return;
      }
      if (loadingPatient || loadingPatients) {
        setTimelineLoading(true);
        return;
      }
      setTimelineLoading(true);
      try {
        const rows = await renalTwinRequest<Observation[]>(
          `/patients/${patientId}/observations?limit=${TIMELINE_PAGE_SIZE}&offset=${timelinePage * TIMELINE_PAGE_SIZE}&recent=true&measurement_type=${encodeURIComponent(measurementFilter)}`,
        );
        const expectedRows =
          timelineMeasurementCount === undefined
            ? null
            : Math.max(
                0,
                Math.min(
                  TIMELINE_PAGE_SIZE,
                  timelineMeasurementCount - timelinePage * TIMELINE_PAGE_SIZE,
                ),
              );
        const filteredPageIsValid =
          rows.every((row) => row.measurement_type === measurementFilter) &&
          (expectedRows === null || rows.length === expectedRows);
        if (filteredPageIsValid) {
          if (active) setTimelineRows(rows);
          return;
        }

        // Older API processes may ignore the optional measurement_type query. Fall back to
        // scanning recent source pages and filter locally until this page is filled.
        if (timelineMeasurementCount === 0) {
          if (active) setTimelineRows([]);
          return;
        }
        const observationCount =
          patients.find((patient) => patient.id === patientId)
            ?.observation_count ?? 0;
        const matchingRows: Observation[] = [];
        const pageEnd = (timelinePage + 1) * TIMELINE_PAGE_SIZE;
        for (
          let offset = 0;
          offset < observationCount && matchingRows.length < pageEnd;
          offset += 500
        ) {
          const batch = await renalTwinRequest<Observation[]>(
            `/patients/${patientId}/observations?limit=500&offset=${offset}&recent=true`,
          );
          for (const row of batch.slice().reverse()) {
            if (row.measurement_type === measurementFilter)
              matchingRows.push(row);
          }
        }
        if (active)
          setTimelineRows(
            matchingRows
              .slice(timelinePage * TIMELINE_PAGE_SIZE, pageEnd)
              .reverse(),
          );
      } catch (reason) {
        if (active) {
          setTimelineRows([]);
          setError(
            reason instanceof Error
              ? reason.message
              : "Could not load this timeline page.",
          );
        }
      } finally {
        if (active) setTimelineLoading(false);
      }
    }, 0);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [
    loadingPatient,
    loadingPatients,
    measurementFilter,
    patientId,
    patients,
    timelineMeasurementCount,
    timelinePage,
  ]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const localNow = new Date();
      localNow.setMinutes(localNow.getMinutes() - localNow.getTimezoneOffset());
      setObservedAt(localNow.toISOString().slice(0, 16));
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const eGfrObservations = useMemo(
    () => observations.filter((row) => row.measurement_type === "egfr"),
    [observations],
  );
  const selectedPatient = patients.find((patient) => patient.id === patientId);
  const selectedMeasurement = specs[measurementFilter] ?? specs.egfr;

  async function recomputeState() {
    if (!patientId) return;
    setUpdating(true);
    setNotice("");
    setError("");
    try {
      await renalTwinRequest<TwinState>(`/patients/${patientId}/update`, {
        method: "POST",
      });
      await Promise.all([refreshPatient(), refreshPatients()]);
      setNotice(
        "Twin state recomputed from the patient’s recorded observations.",
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The twin state could not be recomputed.",
      );
    } finally {
      setUpdating(false);
    }
  }

  async function addObservation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!patientId) return;
    setSavingObservation(true);
    setError("");
    setNotice("");
    try {
      await renalTwinRequest(`/patients/${patientId}/observations`, {
        method: "POST",
        body: JSON.stringify({
          measurement_type: kind,
          value: Number(value),
          unit: specs[kind].unit,
          observed_at: new Date(observedAt).toISOString(),
          source: source.trim() || null,
        }),
      });
      setValue("");
      setSource("");
      setTimelinePage(0);
      await Promise.all([refreshPatient(), refreshPatients()]);
      setNotice("Observation saved and the twin state was updated.");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The observation could not be saved.",
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
          patient_code: patientCode.trim() || null,
          profile_metadata: {},
        }),
      });
      setPatientCode("");
      const rows = await renalTwinRequest<Patient[]>("/patients");
      setPatients(rows);
      setPatientId(patient.id);
      setNotice("Patient profile created.");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The patient profile could not be created.",
      );
    } finally {
      setCreatingPatient(false);
    }
  }

  async function saveScenario(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!patientId || !scenarioBase) return;
    setSavingScenario(true);
    setError("");
    setNotice("");
    try {
      await renalTwinRequest(`/patients/${patientId}/scenarios`, {
        method: "POST",
        body: JSON.stringify({
          baseline_observation_id: Number(scenarioBase),
          rate_per_year: Number(rate),
          horizon_months: Number(horizon),
        }),
      });
      await refreshPatient();
      setNotice("Scenario saved separately from observed measurements.");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The scenario could not be saved.",
      );
    } finally {
      setSavingScenario(false);
    }
  }

  async function deleteScenario(id: number) {
    setDeletingScenarioId(id);
    setError("");
    setNotice("");
    try {
      await renalTwinRequest<void>(`/patients/${patientId}/scenarios/${id}`, {
        method: "DELETE",
      });
      setScenarios((current) =>
        current.filter((scenario) => scenario.id !== id),
      );
      await refreshPatient();
      setNotice("Scenario removed. Observed measurements were not changed.");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The scenario could not be removed.",
      );
    } finally {
      setDeletingScenarioId(null);
    }
  }

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

      <section
        className={`${panel} p-5 sm:p-6`}
        aria-labelledby="profile-heading"
      >
        <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_minmax(260px,0.65fr)] md:items-end">
          <div>
            <label
              id="profile-heading"
              htmlFor="patient-select"
              className="text-sm font-semibold text-slate-900"
            >
              Patient profile
            </label>
            <p className="mt-1 text-xs text-slate-500">
              Select a pseudonymous cohort profile to inspect its recorded
              history.
            </p>
            <select
              id="patient-select"
              className={`${input} max-w-2xl`}
              value={patientId}
              disabled={loadingPatients || patients.length === 0}
              onChange={(event) => {
                setPatientId(
                  event.target.value ? Number(event.target.value) : "",
                );
                setTimelinePage(0);
                setNotice("");
              }}
            >
              <option value="">
                {loadingPatients
                  ? "Loading patient profiles…"
                  : "Choose a patient"}
              </option>
              {patients.map((patient) => (
                <option key={patient.id} value={patient.id}>
                  {patient.patient_code ?? `Patient ${patient.id}`} ·{" "}
                  {patient.observation_count.toLocaleString()} observations
                </option>
              ))}
            </select>
          </div>
          <form
            onSubmit={(event) => void createPatient(event)}
            className="flex items-end gap-2 rounded-xl bg-slate-50 p-3"
          >
            <div className="min-w-0 flex-1">
              <label
                htmlFor="new-patient-code"
                className="text-xs font-semibold text-slate-700"
              >
                Create a profile
              </label>
              <input
                id="new-patient-code"
                className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-600 focus:ring-4 focus:ring-teal-100"
                value={patientCode}
                onChange={(event) => setPatientCode(event.target.value)}
                maxLength={64}
                pattern="[A-Za-z0-9_-]*"
                placeholder="Optional local code"
              />
            </div>
            <button
              className="rounded-lg bg-slate-800 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
              disabled={creatingPatient}
            >
              {creatingPatient ? "Creating…" : "Create"}
            </button>
          </form>
        </div>
        <form
          onSubmit={(event) => void addObservation(event)}
          className="mt-5 grid gap-3 border-t border-slate-100 pt-5 sm:grid-cols-2 lg:grid-cols-[1.2fr_1fr_1fr_1.2fr_auto] lg:items-end"
        >
          <div>
            <label
              htmlFor="measurement-kind"
              className="text-xs font-semibold text-slate-700"
            >
              Record measurement
            </label>
            <select
              id="measurement-kind"
              value={kind}
              onChange={(event) => setKind(event.target.value)}
              className={input}
            >
              {Object.entries(specs).map(([key, spec]) => (
                <option key={key} value={key}>
                  {spec.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              htmlFor="measurement-value"
              className="text-xs font-semibold text-slate-700"
            >
              Value · {specs[kind].unit}
            </label>
            <input
              id="measurement-value"
              className={input}
              type="number"
              min="0"
              step="any"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              required
            />
          </div>
          <div>
            <label
              htmlFor="measurement-time"
              className="text-xs font-semibold text-slate-700"
            >
              Observed at
            </label>
            <input
              id="measurement-time"
              className={input}
              type="datetime-local"
              value={observedAt}
              onChange={(event) => setObservedAt(event.target.value)}
              required
            />
          </div>
          <div>
            <label
              htmlFor="measurement-source"
              className="text-xs font-semibold text-slate-700"
            >
              Source (optional)
            </label>
            <input
              id="measurement-source"
              className={input}
              value={source}
              onChange={(event) => setSource(event.target.value)}
              maxLength={128}
              placeholder="e.g. local laboratory"
            />
          </div>
          <button
            className={primaryButton}
            disabled={!patientId || savingObservation || !observedAt}
          >
            {savingObservation ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : (
              <ArrowRight className="h-4 w-4" />
            )}
            {savingObservation ? "Saving…" : "Save result"}
          </button>
        </form>
        <p className="mt-3 text-[11px] leading-5 text-slate-500">
          <Database className="mr-1 inline h-3.5 w-3.5" />
          New manual results are stored as observations for the selected
          profile; hypothetical scenario values remain separate.
        </p>
      </section>

      <section className="space-y-4" aria-labelledby="state-heading">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-teal-700">
              01 · Patient summary
            </p>
            <h2
              id="state-heading"
              className="mt-1 text-xl font-bold text-slate-900"
            >
              Current twin state
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Latest available values from recorded data, with the time and
              trend kept visible.
            </p>
          </div>
          <button
            onClick={() => void recomputeState()}
            disabled={!patientId || updating || loadingPatient}
            className={primaryButton}
          >
            {updating ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            {updating ? "Recomputing…" : "Recompute twin state"}
          </button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-2xl border border-teal-200 bg-teal-50/70 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-teal-800">
                eGFR latest
              </span>
              <Activity className="h-4 w-4 text-teal-700" />
            </div>
            <p className="mt-3 text-2xl font-bold tracking-tight text-slate-900">
              {twin?.measurements?.egfr?.latest
                ? `${twin.measurements.egfr.latest.value} ${twin.measurements.egfr.latest.unit}`
                : "No result"}
            </p>
            <p className="mt-1 text-xs text-slate-600">
              {formatDate(twin?.measurements?.egfr?.latest?.observed_at, true)}
            </p>
          </div>
          <div className="rounded-2xl border border-blue-200 bg-blue-50/70 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-blue-800">
                Creatinine latest
              </span>
              <Activity className="h-4 w-4 text-blue-700" />
            </div>
            <p className="mt-3 text-2xl font-bold tracking-tight text-slate-900">
              {twin?.measurements?.creatinine?.latest
                ? `${twin.measurements.creatinine.latest.value} ${twin.measurements.creatinine.latest.unit}`
                : "No result"}
            </p>
            <p className="mt-1 text-xs text-slate-600">
              {formatDate(
                twin?.measurements?.creatinine?.latest?.observed_at,
                true,
              )}
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Measurement types
              </span>
              <Sparkles className="h-4 w-4 text-violet-600" />
            </div>
            <p className="mt-3 text-2xl font-bold tracking-tight text-slate-900">
              {twin?.data_completeness?.available_measurements ?? 0}
              <span className="ml-1 text-sm font-medium text-slate-400">
                /{" "}
                {twin?.data_completeness?.supported_measurements ??
                  Object.keys(specs).length}
              </span>
            </p>
            <p className="mt-1 text-xs text-slate-500">
              with at least one recorded result
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                History coverage
              </span>
              <Clock3 className="h-4 w-4 text-slate-500" />
            </div>
            <p className="mt-3 text-2xl font-bold tracking-tight text-slate-900">
              {selectedPatient?.observation_count.toLocaleString() ?? "—"}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              source observations · irregular timestamps
            </p>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Object.entries(specs).map(([key, spec]) => {
            const item = twin?.measurements?.[key];
            return (
              <article
                key={key}
                className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm shadow-slate-950/[0.02]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-slate-800">
                      {spec.label}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      {item?.count ?? 0} recorded results
                    </p>
                  </div>
                  {item?.stale && (
                    <span className="rounded-full bg-amber-50 px-2.5 py-1 text-[10px] font-semibold text-amber-800">
                      Older result
                    </span>
                  )}
                </div>
                <div className="mt-3 flex items-end justify-between gap-3">
                  <p className="text-xl font-bold text-slate-950">
                    {item?.latest ? `${item.latest.value}` : "—"}
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
                    ? formatDate(item.latest.observed_at, true)
                    : "No observation in this profile"}
                </p>
                {item && metricTrend(item) && (
                  <p className="mt-2 text-xs font-medium">
                    {metricTrend(item)}
                  </p>
                )}
              </article>
            );
          })}
        </div>
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

      <section
        className={`${panel} p-5 sm:p-6`}
        aria-labelledby="timeline-heading"
      >
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
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
              Page through every recorded result. The chart uses the latest 500
              observations; missing intervals remain gaps.
            </p>
          </div>
          <label
            htmlFor="measurement-filter"
            className="text-xs font-semibold text-slate-600"
          >
            Measure
            <select
              id="measurement-filter"
              value={measurementFilter}
              onChange={(event) => {
                setMeasurementFilter(event.target.value);
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
        </div>
        {loadingPatient ? (
          <div className="flex min-h-64 items-center justify-center text-sm text-slate-500">
            <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
            Loading recorded timeline…
          </div>
        ) : (
          <TrendChart
            observations={observations}
            scenarios={scenarios}
            measure={measurementFilter}
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
                <th className="px-4 py-3 font-semibold">Record</th>
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
                        {formatDate(row.observed_at, true)}
                      </td>
                      <td className="px-4 py-3 text-xs font-medium text-slate-800">
                        {specs[row.measurement_type]?.label ??
                          row.measurement_type}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-sm font-semibold text-slate-900">
                        {row.value}{" "}
                        <span className="text-xs font-normal text-slate-500">
                          {row.unit}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500">
                        {row.source ?? "Source record"}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-500">
                        #{row.id}
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
                      Math.min(totalPages - 1, page + 1),
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
                03 · Hypothetical
              </p>
              <h2
                id="scenario-heading"
                className="mt-1 text-xl font-bold text-slate-900"
              >
                What-if scenario simulator
              </h2>
              <p className="mt-1 max-w-3xl text-sm leading-5 text-slate-600">
                Choose a recorded eGFR, enter an assumed yearly change, and pick
                a time period. We’ll show the simple calculated result.
              </p>
            </div>
          </div>
        </div>
        <div className="grid gap-6 p-5 sm:p-6 lg:grid-cols-[minmax(280px,0.8fr)_minmax(0,1.2fr)]">
          <form
            onSubmit={(event) => void saveScenario(event)}
            className="space-y-4 rounded-2xl border border-slate-200 bg-slate-50/70 p-4 sm:p-5"
          >
            <div>
              <label
                htmlFor="scenario-baseline"
                className="text-xs font-semibold text-slate-700"
              >
                1. Starting eGFR (recorded result)
              </label>
              <select
                id="scenario-baseline"
                className={input}
                required
                value={scenarioBase}
                disabled={eGfrObservations.length === 0}
                onChange={(event) => setScenarioBase(event.target.value)}
              >
                <option value="">
                  {eGfrObservations.length
                    ? "Choose a result"
                    : "No eGFR results available"}
                </option>
                {eGfrObservations.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.value} · {formatDate(row.observed_at)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label
                htmlFor="scenario-rate"
                className="text-xs font-semibold text-slate-700"
              >
                2. Assumed eGFR change each year
              </label>
              <div className="relative">
                <input
                  id="scenario-rate"
                  className={`${input} pr-20`}
                  type="number"
                  min="-30"
                  max="30"
                  step="0.1"
                  required
                  value={rate}
                  onChange={(event) => setRate(event.target.value)}
                />
                <span className="pointer-events-none absolute right-3 top-4 text-[10px] text-slate-500">
                  mL/min/year
                </span>
              </div>
              <p className="mt-1 text-[11px] text-slate-500">
                Use a negative number for a decrease, or positive for an
                increase.
              </p>
            </div>
            <div>
              <label
                htmlFor="scenario-horizon"
                className="text-xs font-semibold text-slate-700"
              >
                3. Show result after
              </label>
              <select
                id="scenario-horizon"
                className={input}
                value={horizon}
                onChange={(event) => setHorizon(event.target.value)}
              >
                {[6, 12, 24, 36, 60, 120].map((months) => (
                  <option key={months} value={months}>
                    {months} months
                  </option>
                ))}
              </select>
            </div>
            <button
              className={`${primaryButton} w-full bg-violet-700 hover:bg-violet-800`}
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
              {savingScenario ? "Calculating…" : "Show this example"}
            </button>
            <p className="text-[11px] leading-5 text-slate-500">
              This is a simple illustration based on your assumption. It is not
              a medical prediction.
            </p>
          </form>
          <div className="min-w-0">
            {scenarios.length ? (
              <div
                className="max-h-[26rem] space-y-3 overflow-y-auto overscroll-contain pr-2"
                tabIndex={0}
                aria-label="Saved example results. Scroll to see more."
              >
                {scenarios.map((scenario) => {
                  const baseline = observations.find(
                    (row) => row.id === scenario.baseline_observation_id,
                  );
                  const end = scenario.output.points.at(-1);
                  return (
                    <article
                      key={scenario.id}
                      className="min-h-44 rounded-2xl border border-violet-200 bg-violet-50/50 p-4"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-violet-950">
                            Example result
                          </p>
                          <p className="mt-1 text-xs text-violet-900">
                            Starting from a recorded eGFR of{" "}
                            {baseline?.value ?? "—"} on{" "}
                            {formatDate(baseline?.observed_at)}, assuming{" "}
                            {scenario.assumptions.rate_per_year} mL/min/year for{" "}
                            {scenario.horizon_months} months.
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => void deleteScenario(scenario.id)}
                          disabled={deletingScenarioId !== null}
                          aria-label={`Remove scenario ${scenario.id}`}
                          className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-100 disabled:cursor-wait disabled:opacity-60"
                        >
                          {deletingScenarioId === scenario.id && (
                            <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                          )}
                          {deletingScenarioId === scenario.id
                            ? "Removing…"
                            : "Remove"}
                        </button>
                      </div>
                      <div className="mt-3 grid grid-cols-2 gap-2">
                        <div className="rounded-xl bg-white p-3">
                          <p className="text-[10px] uppercase tracking-wide text-slate-500">
                            Starting value
                          </p>
                          <p className="mt-1 text-lg font-bold text-slate-900">
                            {scenario.output.points[0]?.value ?? "—"} mL/min
                          </p>
                        </div>
                        <div className="rounded-xl bg-white p-3">
                          <p className="text-[10px] uppercase tracking-wide text-slate-500">
                            Example after {scenario.horizon_months} months
                          </p>
                          <p className="mt-1 text-lg font-bold text-violet-800">
                            {end?.value ?? "—"} mL/min
                          </p>
                        </div>
                      </div>
                      <p className="mt-3 text-[11px] leading-5 text-violet-900">
                        {scenario.output.warnings.join(" ")}
                      </p>
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="flex h-full min-h-56 flex-col items-center justify-center rounded-2xl border border-dashed border-violet-200 bg-violet-50/30 px-6 text-center">
                <div className="rounded-full bg-white p-3 text-violet-700 shadow-sm">
                  <Activity className="h-5 w-5" />
                </div>
                <p className="mt-3 text-sm font-semibold text-slate-800">
                  No hypothetical paths yet
                </p>
                <p className="mt-1 max-w-sm text-xs leading-5 text-slate-500">
                  Choose one of the patient’s recorded eGFR results, set an
                  assumption, and save a scenario to compare it with the
                  observed timeline.
                </p>
              </div>
            )}
          </div>
        </div>
        {eGfrObservations.length > 0 && (
          <div className="px-5 pb-5 sm:px-6 sm:pb-6">
            <TrendChart
              observations={observations}
              scenarios={scenarios}
              measure="egfr"
            />
          </div>
        )}
      </section>
    </main>
  );
}

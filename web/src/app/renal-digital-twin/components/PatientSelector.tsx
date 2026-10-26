"use client";

import { FormEvent, useState } from "react";
import { ArrowRight, ChevronDown, Database, LoaderCircle, Search, Sparkles } from "lucide-react";
import type {
  ExamplePatient,
  MeasurementType,
  Patient,
} from "../types";
import { OBSERVATION_INPUT_UNITS } from "../types";
import type { MeasurementSpec } from "./TrendChart";

export function PatientSelector({
  patients,
  patientId,
  setPatientId,
  loadingPatients,
  examplePatients,
  examplePatientsLoading,
  examplePatientsError,
  loadExamplePatient,
  patientCode,
  setPatientCode,
  createPatient,
  creatingPatient,
  kind,
  setKind,
  value,
  setValue,
  observedAt,
  setObservedAt,
  source,
  setSource,
  addObservation,
  savingObservation,
  specs,
  setTimelinePage,
  setNotice,
  inputClassName,
  primaryButtonClassName,
  panelClassName,
}: {
  patients: Patient[];
  patientId: number | "";
  setPatientId: (id: number | "") => void;
  loadingPatients: boolean;
  examplePatients: ExamplePatient[];
  examplePatientsLoading: boolean;
  examplePatientsError: string;
  loadExamplePatient: (example: ExamplePatient) => void;
  patientCode: string;
  setPatientCode: (code: string) => void;
  createPatient: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  creatingPatient: boolean;
  kind: MeasurementType;
  setKind: (kind: MeasurementType) => void;
  value: string;
  setValue: (value: string) => void;
  observedAt: string;
  setObservedAt: (time: string) => void;
  source: string;
  setSource: (source: string) => void;
  addObservation: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  savingObservation: boolean;
  specs: Record<MeasurementType, MeasurementSpec>;
  setTimelinePage: (page: number) => void;
  setNotice: (notice: string) => void;
  inputClassName: string;
  primaryButtonClassName: string;
  panelClassName: string;
}) {
  const [patientSearch, setPatientSearch] = useState("");
  const [patientSearchOpen, setPatientSearchOpen] = useState(false);
  const selectedPatient = patients.find((patient) => patient.id === patientId);
  const normalizedSearch = patientSearch.trim().toLocaleLowerCase();
  const matchingPatients = normalizedSearch
    ? patients.filter((patient) => {
        const searchableId = `${patient.patient_code ?? ""} ${patient.id}`.toLocaleLowerCase();
        return searchableId.includes(normalizedSearch);
      })
    : patients;

  function selectPatient(id: number) {
    setPatientId(id);
    setTimelinePage(0);
    setNotice("");
    setPatientSearch("");
    setPatientSearchOpen(false);
  }

  return (
    <>
      <div
        id="recommended-examples"
        className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm"
      >
        <span className="mr-1 text-xs font-semibold text-slate-700">Example patients</span>
        {examplePatientsLoading ? (
          <span className="text-xs text-slate-500">Finding simulation-eligible profiles…</span>
        ) : examplePatientsError ? (
          <span role="status" className="text-xs text-amber-800">
            Examples unavailable; use the patient selector.
          </span>
        ) : !examplePatients.length ? (
          <span className="text-xs text-slate-500">
            No profiles currently meet the simulation input rules.
          </span>
        ) : (
          examplePatients.map((example, index) => (
            <button
              key={example.id}
              type="button"
              aria-pressed={patientId === example.id}
              onClick={() => loadExamplePatient(example)}
              aria-label={`Load ${example.patient_code ?? `profile ${example.id}`}: ${example.focus}`}
              title={`${example.patient_code ?? `Profile ${example.id}`} · ${example.focus} · eligible for simulation`}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2 ${
                patientId === example.id
                  ? "bg-teal-700 text-white"
                  : "bg-slate-100 text-slate-800 hover:bg-teal-50 hover:text-teal-900"
              }`}
            >
              <Sparkles
                className={`h-3.5 w-3.5 ${
                  patientId === example.id ? "text-white" : "text-teal-700"
                }`}
              />
              {["Broad history", "ACR + HbA1c", "eGFR history"][index] ?? `Example ${index + 1}`}
            </button>
          ))
        )}
      </div>

      <section
        className={`${panelClassName} p-5 sm:p-6`}
        aria-labelledby="profile-heading"
      >
        <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_minmax(260px,0.65fr)] md:items-end">
          <div>
            <label id="profile-heading" className="text-sm font-semibold text-slate-900">
              Patient profile
            </label>
            <p className="mt-1 text-xs text-slate-500">
              Select a pseudonymous cohort profile to inspect its recorded
              history.
            </p>
            <div
              className="relative max-w-2xl"
              onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                  setPatientSearchOpen(false);
                }
              }}
            >
              <button
                id="patient-picker"
                type="button"
                aria-haspopup="listbox"
                aria-expanded={patientSearchOpen}
                aria-controls="patient-picker-options"
                className={`${inputClassName} flex max-w-2xl items-center justify-between gap-3 text-left`}
                disabled={loadingPatients || patients.length === 0}
                onClick={() => {
                  setPatientSearch("");
                  setPatientSearchOpen((open) => !open);
                }}
              >
                <span className={selectedPatient ? "truncate text-slate-800" : "text-slate-500"}>
                  {selectedPatient
                    ? `${selectedPatient.patient_code ?? `Patient ${selectedPatient.id}`} · ${selectedPatient.observation_count.toLocaleString()} observations`
                    : loadingPatients ? "Loading patient profiles…" : "Choose a patient"}
                </span>
                <ChevronDown className={`h-4 w-4 shrink-0 text-slate-500 transition-transform ${patientSearchOpen ? "rotate-180" : ""}`} />
              </button>
              {patientSearchOpen && (
                <div
                  id="patient-picker-options"
                  className="mt-2 rounded-xl border border-slate-200 bg-white p-2 shadow-lg"
                >
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <input
                      autoFocus
                      type="search"
                      aria-label="Search patient ID"
                      placeholder="Search MIMIC31 ID or numeric ID"
                      value={patientSearch}
                      onChange={(event) => setPatientSearch(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Escape") setPatientSearchOpen(false);
                        if (event.key === "Enter" && matchingPatients[0]) {
                          event.preventDefault();
                          selectPatient(matchingPatients[0].id);
                        }
                      }}
                      className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm text-slate-800 outline-none focus:border-teal-600 focus:ring-4 focus:ring-teal-100"
                    />
                  </div>
                  <div role="listbox" aria-label="Patient profiles" className="mt-2 max-h-52 overflow-y-auto">
                    {matchingPatients.length ? matchingPatients.map((patient) => (
                      <button
                        key={patient.id}
                        type="button"
                        role="option"
                        aria-selected={patient.id === patientId}
                        onClick={() => selectPatient(patient.id)}
                        className={`flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-teal-50 focus:bg-teal-50 focus:outline-none ${patient.id === patientId ? "bg-teal-50 text-teal-900" : "text-slate-800"}`}
                      >
                        <span>{patient.patient_code ?? `Patient ${patient.id}`}</span>
                        <span className="shrink-0 text-xs text-slate-500">{patient.observation_count.toLocaleString()} observations</span>
                      </button>
                    )) : (
                      <p className="px-3 py-2 text-sm text-slate-500">No matching patient profile.</p>
                    )}
                  </div>
                </div>
              )}
            </div>
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
              onChange={(event) => setKind(event.target.value as MeasurementType)}
              className={inputClassName}
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
              Value · {OBSERVATION_INPUT_UNITS[kind]}
            </label>
            <input
              id="measurement-value"
              className={inputClassName}
              type="number"
              min={kind === "hba1c" ? "0.1" : "0"}
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
              className={inputClassName}
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
              className={inputClassName}
              value={source}
              onChange={(event) => setSource(event.target.value)}
              maxLength={128}
              placeholder="e.g. local laboratory"
            />
          </div>
          <button
            className={primaryButtonClassName}
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
    </>
  );
}

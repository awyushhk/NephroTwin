export type Patient = {
  id: number;
  patient_code: string | null;
  observation_count: number;
  source_system?: string | null;
};

export type ExamplePatient = {
  id: number;
  patient_code: string | null;
  observation_count: number;
  measurement_type_count: number;
  measurement_counts: Partial<Record<MeasurementType, number>>;
  index_date: string;
  freshness_threshold_days: number;
  focus: string;
  trajectory_eligible: boolean;
};

export type MeasurementType =
  | "egfr"
  | "creatinine"
  | "acr"
  | "bun"
  | "potassium"
  | "bicarbonate"
  | "urine_albumin"
  | "urine_creatinine"
  | "systolic_bp"
  | "diastolic_bp"
  | "hba1c";

export type ObservationDateFields = {
  observed_at?: string | null;
  observed_date?: string | null;
  timestamp_precision?: "exact_time" | "date_only";
};

export type Observation = {
  id: number;
  patient_id: number;
  measurement_type: MeasurementType;
  value: number;
  unit: string;
  observed_at: string | null;
  observed_date?: string | null;
  timestamp_precision?: "exact_time" | "date_only";
  source_sequence_number?: number | null;
  same_day_ordering_ambiguous?: boolean;
  source?: string | null;
  source_observation_id?: string | null;
  source_item_id?: string | null;
  source_original_label?: string | null;
  source_charttime_text?: string | null;
  source_timestamp_timezone?: string | null;
  note?: string | null;
};

export type ChartObservation = {
  id: number;
  measurement_type: MeasurementType;
  value: number;
  unit: string;
  observed_at: string | null;
  observed_date?: string | null;
  timestamp_precision?: "exact_time" | "date_only";
  source_sequence_number?: number | null;
  same_day_ordering_ambiguous?: boolean;
  source?: string | null;
  source_observation_id?: string | null;
};

export type Measurement = {
  latest: {
    value: number;
    unit: string;
    observed_at: string | null;
    observed_date?: string | null;
    timestamp_precision?: "exact_time" | "date_only";
    source_sequence_number?: number | null;
    observation_id: number;
  } | null;
  latest_temporal_ambiguity?: boolean;
  latest_candidates?: { value: number; observed_at: string | null; observed_date?: string | null; timestamp_precision?: "exact_time" | "date_only" }[];
  previous: {
    value: number;
    observed_at: string | null;
    observed_date?: string | null;
    timestamp_precision?: "exact_time" | "date_only";
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

export type TwinState = {
  measurements: Partial<Record<MeasurementType, Measurement>>;
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

export type Scenario = {
  id: number;
  assumptions: { rate_per_year: number; step_months: number; comparison_group_id?: string | null; scenario_label?: string | null; comparison_index?: number | null };
  horizon_months: number;
  output: { points: { month: number; value: number }[]; warnings: string[] };
  baseline_observation_id: number;
};

export type ScenarioDraft = { key: string; rate: string };

export type TrajectorySimulationResult = {
  method: string;
  patient_id: number;
  index_date: string;
  horizon_years: number;
  point_count: number;
  baseline_inputs: Record<string, TrajectoryInputStatus>;
  trajectory: { year: number; egfr: number; uacr: number }[];
  analysis: TrajectoryAnalysis;
  time_to_egfr_below_15_years: number | null;
  assumptions: { u: number; parameter_set: string; points: number; source_model: string };
  eligibility: TrajectoryEligibility;
  warnings: string[];
  limitations: string[];
};

export type TrajectoryMilestone = {
  status: "crossed" | "not_crossed" | "unavailable" | "below_at_baseline" | "at_threshold_at_baseline";
  time_years: number | null;
};

export type TrajectoryMetricSummary = {
  status: "available" | "insufficient_points" | "unavailable";
  starting: number | null;
  final: number | null;
  absolute_change: number | null;
  percent_change: number | null;
  average_annualized_change: number | null;
  elapsed_years: number | null;
  unit: string;
  valid_points: number;
  thresholds?: Record<string, TrajectoryMilestone>;
  decline_20_percent?: TrajectoryMilestone;
};

export type TrajectoryAnalysis = {
  label: string;
  calculation: string;
  crossing_method: string;
  egfr: TrajectoryMetricSummary;
  uacr: TrajectoryMetricSummary;
  categories: {
    starting: { gfr: string; albuminuria: string } | null;
    final: { gfr: string; albuminuria: string } | null;
    transitions: { year: number; gfr_category: string; albuminuria_category: string; egfr: number; uacr: number }[];
    boundary_rules: { gfr: string; uacr_mg_g: string };
  };
};

export type TrajectoryInputStatus = {
  value?: number;
  unit?: string;
  observed_date?: string | null;
  observed_at?: string | null;
  timestamp_precision?: "exact_time" | "date_only";
  source_sequence_number?: number | null;
  source?: string | null;
  source_observation_id?: string | null;
  age_days?: number | null;
  age_precision?: "exact_time" | "calendar_day";
  freshness_status: "fresh" | "stale" | "missing" | "temporally_ambiguous";
  stale?: boolean;
  reason?: string;
};

export type TrajectoryEligibility = {
  eligible: boolean;
  baseline: { observation_id: number; value: number; unit: string; observed_date: string | null; observed_at: string | null; timestamp_precision: "exact_time" | "date_only" } | null;
  index_date?: string;
  freshness_threshold_days: number;
  freshness_policy: string;
  inputs: Record<string, TrajectoryInputStatus>;
  blockers: string[];
  warnings: string[];
};

export type TrajectoryEligibilityState = { patientId: number; baselineId: string; report: TrajectoryEligibility };

export type ScenarioComparisonMetadata = {
  comparison_group_id: string;
  scenario_label: string;
  comparison_index: number;
};

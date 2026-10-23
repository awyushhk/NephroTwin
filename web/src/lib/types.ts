/**
 * web/src/lib/types.ts — TypeScript definitions matching FastAPI backend schemas.
 */

export interface HealthResponse {
  status: string;
  service: string;
  organ: string;
  timestamp?: string;
}

export interface FeatureOption {
  value: number | string;
  label: string;
}

export interface FeatureMetadata {
  name: string;
  label: string;
  type: "numeric" | "ordinal" | "categorical";
  unit?: string | null;
  min?: number | null;
  max?: number | null;
  step?: number | null;
  options?: FeatureOption[] | string[] | null;
}

export interface TabularMetadata {
  disease: string;
  columns: string[];
  total_features: number;
  min_features_required: number;
  threshold: number;
  sections: Record<string, string[]>;
  features: Record<string, FeatureMetadata>;
}

export interface ImageMetadata {
  expected_input: string;
  class_names: string[];
  supported_formats: string[];
  confidence_threshold: number;
  best_model: string;
  ensemble_members: string[];
}

export interface MetadataResponse {
  organ: string;
  tabular: TabularMetadata;
  image: ImageMetadata;
}

export interface ExplanationFactor {
  feature: string;
  value: any;
  typical: any;
  effect: number;
}

export interface TabularExplanation {
  method: string;
  factors: ExplanationFactor[];
}

export interface TabularPredictionResponse {
  organ: string;
  modality: "tabular";
  status: "accepted" | "review" | "rejected" | string;
  scored: boolean;
  probability: number | null;
  label: string | null;
  positive: boolean | null;
  threshold: number;
  message: string;
  explanation: TabularExplanation;
  details: {
    disease?: string;
    model?: string;
    threshold?: number;
    risk_bands?: Record<string, string>;
    anomaly_flagged?: boolean;
    [key: string]: any;
  };
}

export interface ImageExplanation {
  method?: string | null;
  overlay?: string | null; // data:image/png;base64,...
}

export interface ImagePredictionResponse {
  organ: string;
  modality: "image";
  status: "accepted" | "review" | "rejected" | string;
  scored: boolean;
  probability: number | null;
  label: string | null;
  positive: boolean | null;
  message: string;
  details: {
    model?: string;
    threshold?: number;
    confidence?: number;
    probabilities?: Record<string, number>;
    top_3?: [string, number][];
    [key: string]: any;
  };
  explanation: ImageExplanation;
}

export interface ApiError {
  detail: string;
  status?: number;
}

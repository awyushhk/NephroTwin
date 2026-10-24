/**
 * web/src/lib/api.ts — Typed API client interfacing with FastAPI backend.
 */

import {
  HealthResponse,
  MetadataResponse,
  TabularPredictionResponse,
  ImagePredictionResponse,
  CTStudyPredictionResponse,
} from "./types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`;
    try {
      const errorJson = await res.json();
      if (typeof errorJson?.detail === "string") {
        detail = errorJson.detail;
      } else if (Array.isArray(errorJson?.detail)) {
        detail = errorJson.detail
          .map((item: unknown) => typeof item === "object" && item !== null && "msg" in item ? String(item.msg) : JSON.stringify(item))
          .join("; ");
      } else if (errorJson?.message) {
        detail = errorJson.message;
      }
    } catch {
      // Non-JSON error body
      const text = await res.text().catch(() => "");
      if (text) detail = text;
    }
    throw new ApiError(res.status, detail);
  }
  // DELETE endpoints may correctly return 204 with no response body.
  if (res.status === 204 || res.status === 205) {
    return undefined as T;
  }
  return res.json();
}

export async function renalTwinRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}/api/renal-twin${path}`, {
    ...init,
    headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
    cache: "no-store",
  });
  return handleResponse<T>(res);
}

/** Check health status of the backend API. */
export async function checkHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE_URL}/api/health`, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
    cache: "no-store",
  });
  return handleResponse<HealthResponse>(res);
}

/** Fetch metadata for kidney tabular features and image specifications. */
export async function getKidneyMetadata(signal?: AbortSignal): Promise<MetadataResponse> {
  const res = await fetch(`${API_BASE_URL}/api/kidney/metadata`, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });
  return handleResponse<MetadataResponse>(res);
}

/** Submit clinical questionnaire inputs for tabular CKD risk prediction. */
export async function predictTabular(
  inputs: Record<string, unknown>,
  signal?: AbortSignal
): Promise<TabularPredictionResponse> {
  const res = await fetch(`${API_BASE_URL}/api/kidney/tabular`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(inputs),
    signal,
  });
  return handleResponse<TabularPredictionResponse>(res);
}

/** Upload a CT scan image for kidney finding classification and Grad-CAM generation. */
export async function predictImage(
  file: File,
  ensemble = false,
  signal?: AbortSignal
): Promise<ImagePredictionResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (ensemble) {
    formData.append("ensemble", "true");
  }

  const res = await fetch(`${API_BASE_URL}/api/kidney/image`, {
    method: "POST",
    body: formData,
    signal,
  });
  return handleResponse<ImagePredictionResponse>(res);
}

/** Upload slices for one examination; each image runs through the existing image endpoint pipeline. */
export async function predictImageStudy(
  files: File[],
  ensemble = false,
  signal?: AbortSignal,
): Promise<CTStudyPredictionResponse> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file, file.name));
  if (ensemble) formData.append("ensemble", "true");
  const res = await fetch(`${API_BASE_URL}/api/kidney/image/study`, {
    method: "POST",
    body: formData,
    signal,
  });
  try {
    return await handleResponse<CTStudyPredictionResponse>(res);
  } catch (error) {
    // Older local API processes may still be running without the study route.
    // Keep the feature usable through the unchanged single-image endpoint.
    if (error instanceof ApiError && error.status === 404) {
      return predictImageStudyWithLegacyEndpoint(files, ensemble, signal);
    }
    throw error;
  }
}

async function predictImageStudyWithLegacyEndpoint(
  files: File[],
  ensemble: boolean,
  signal?: AbortSignal,
): Promise<CTStudyPredictionResponse> {
  const classes = ["Cyst", "Normal", "Stone", "Tumor"];
  const images: CTStudyPredictionResponse["images"] = [];
  let totalBytes = 0;
  for (const [index, file] of files.entries()) {
    const imageId = crypto.randomUUID();
    const extension = `.${file.name.split(".").pop()?.toLowerCase()}`;
    let status: string | null = null;
    let errorMessage: string | null = null;
    let prediction: ImagePredictionResponse | null = null;
    if (index >= 12) errorMessage = "A study can contain at most 12 images.";
    else if (![".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"].includes(extension)) errorMessage = "Unsupported image format.";
    else if (!file.size) errorMessage = "The selected file is empty.";
    else if (file.size > 25 * 1024 * 1024) errorMessage = "Image exceeds the 25 MB per-image limit.";
    else if (totalBytes + file.size > 100 * 1024 * 1024) errorMessage = "The examination exceeds the 100 MB total upload limit.";

    if (!errorMessage) {
      totalBytes += file.size;
      try {
        prediction = await predictImage(file, ensemble, signal);
        status = prediction.status === "accepted"
          ? "accepted"
          : prediction.status === "review" ? "review_required"
            : prediction.status === "rejected" ? "ood_rejected" : "processing_error";
      } catch (error) {
        status = error instanceof ApiError && [400, 413, 415, 422].includes(error.status)
          ? "invalid_file"
          : "processing_error";
        errorMessage = error instanceof Error ? error.message : "Image processing failed.";
      }
    } else {
      status = "invalid_file";
    }
    images.push({
      image_id: imageId,
      filename: file.name,
      status: status ?? "processing_error",
      prediction,
      error: errorMessage,
    });
  }

  const accepted = images.filter((image) => image.status === "accepted" && image.prediction);
  const classCounts = Object.fromEntries(classes.map((name) => [name, accepted.filter((image) => image.prediction?.label === name).length]));
  const acceptedCount = accepted.length;
  const classDistribution = Object.fromEntries(classes.map((name) => [name, {
    count: classCounts[name],
    percentage: acceptedCount ? Math.round(classCounts[name] * 10000 / acceptedCount) / 100 : 0,
  }]));
  const scoresByClass = Object.fromEntries(classes.map((name) => [name, accepted
    .map((image) => image.prediction?.details.probabilities?.[name])
    .filter((score): score is number => typeof score === "number" && Number.isFinite(score) && score >= 0 && score <= 1)]));
  const means = Object.fromEntries(classes.flatMap((name) => scoresByClass[name].length
    ? [[name, Math.round(scoresByClass[name].reduce((sum, value) => sum + value, 0) / scoresByClass[name].length * 1e6) / 1e6]]
    : []));
  const warnings: string[] = [];
  if (!acceptedCount) warnings.push("No images passed the existing OOD and confidence checks; no class summary is available.");
  if (acceptedCount < 2) warnings.push("Fewer than 2 accepted images are available.");
  if (new Set(accepted.map((image) => image.prediction?.label)).size > 1) warnings.push("Accepted images have conflicting predicted classes; expert review is required.");
  if (images.some((image) => image.status === "review_required")) warnings.push("One or more images fell below the existing confidence threshold and need individual review.");
  if (images.some((image) => image.status === "ood_rejected")) warnings.push("One or more images were rejected by the existing out-of-distribution gate.");
  if (images.some((image) => image.status === "invalid_file" || image.status === "processing_error")) warnings.push("One or more submitted files could not be analyzed; they were not counted as Normal.");
  const disagreement = new Set(accepted.map((image) => image.prediction?.label)).size > 1;
  return {
    examination_id: crypto.randomUUID(),
    summary: {
      status: acceptedCount < 2 || disagreement ? "study_review_required" : "descriptive_summary_available",
      accepted_image_count: acceptedCount,
      submitted_image_count: files.length,
      class_distribution: classDistribution,
      mean_image_level_scores: means,
      mean_score_image_counts: Object.fromEntries(classes.map((name) => [name, scoresByClass[name].length])),
      warnings,
      minimum_accepted_images: 2,
      disagreement_rule: "Abstain when accepted images predict more than one class; no majority vote is used.",
    },
    images,
  };
}

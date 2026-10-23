/**
 * web/src/lib/api.ts — Typed API client interfacing with FastAPI backend.
 */

import {
  HealthResponse,
  MetadataResponse,
  TabularPredictionResponse,
  ImagePredictionResponse,
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
          .map((item: any) => item.msg || JSON.stringify(item))
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
  return res.json();
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
  inputs: Record<string, any>,
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

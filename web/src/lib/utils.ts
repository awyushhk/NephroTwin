import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatProbability(prob: number | null | undefined): string {
  if (prob === null || prob === undefined || isNaN(prob)) return "N/A";
  return `${Math.round(prob * 100)}%`;
}

export function formatPercent(val: number | null | undefined, decimals = 1): string {
  if (val === null || val === undefined || isNaN(val)) return "N/A";
  return `${(val * 100).toFixed(decimals)}%`;
}

export function formatPts(val: number | null | undefined): string {
  if (val === null || val === undefined || isNaN(val)) return "0.0 pts";
  const pts = val * 100;
  return `${pts > 0 ? "+" : ""}${pts.toFixed(1)} pts`;
}

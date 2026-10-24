"use client";

import { useRef, useState } from "react";
import { AlertCircle, FileImage, Layers, ScanLine, Sparkles, UploadCloud, X } from "lucide-react";
import { ApiError, predictImageStudy } from "@/lib/api";
import { CTStudyPredictionResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ImageUploaderProps {
  onPredictionSuccess: (result: CTStudyPredictionResponse, files: File[]) => void;
  onReset: () => void;
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
}

const ACCEPTED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"];
const MAX_FILE_SIZE = 25 * 1024 * 1024;
const MAX_TOTAL_SIZE = 100 * 1024 * 1024;
const MAX_FILES = 12;

export default function ImageUploader({ onPredictionSuccess, onReset, isLoading, setIsLoading }: ImageUploaderProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [statuses, setStatuses] = useState<string[]>([]);
  const [ensembleMode, setEnsembleMode] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const addFiles = (incoming: FileList | File[]) => {
    const next = [...files, ...Array.from(incoming)];
    setFiles(next);
    setStatuses(next.map((file) => {
      const extension = `.${file.name.split(".").pop()?.toLowerCase()}`;
      if (!ACCEPTED_EXTENSIONS.includes(extension)) return "Invalid format";
      if (!file.size) return "Empty file";
      if (file.size > MAX_FILE_SIZE) return "Over 25 MB limit";
      return "Ready";
    }));
    const bytes = next.reduce((sum, file) => sum + file.size, 0);
    setErrorMessage(next.length > MAX_FILES
      ? `Up to ${MAX_FILES} images are allowed per examination. Extra files will be reported as not analyzed.`
      : bytes > MAX_TOTAL_SIZE
        ? "The total upload is over 100 MB. Files beyond the limit will be reported as not analyzed."
        : null);
  };

  const removeFile = (index: number) => {
    setFiles((current) => current.filter((_, i) => i !== index));
    setStatuses((current) => current.filter((_, i) => i !== index));
    setErrorMessage(null);
    onReset();
  };

  const reset = () => {
    setFiles([]);
    setStatuses([]);
    setErrorMessage(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    onReset();
  };

  const handleLoadSample = async () => {
    try {
      const response = await fetch("/sample_stone.png");
      if (!response.ok) throw new Error("Could not load sample CT image");
      const blob = await response.blob();
      addFiles([new File([blob], "sample_stone.png", { type: "image/png" })]);
    } catch {
      setErrorMessage("Could not load the sample image. You can choose image files directly.");
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!files.length) {
      setErrorMessage("Choose one or more CT slice images to analyze.");
      return;
    }
    setErrorMessage(null);
    setIsLoading(true);
    setStatuses(files.map(() => "Analyzing"));
    try {
      const result = await predictImageStudy(files, ensembleMode);
      setStatuses(result.images.map((image) => image.status.replaceAll("_", " ")));
      onPredictionSuccess(result, files);
    } catch (error) {
      setStatuses(files.map(() => "Request failed"));
      setErrorMessage(error instanceof ApiError
        ? error.detail
        : "Examination analysis failed. Please verify that the API server is online.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="space-y-5 rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
        <div className="flex flex-col justify-between gap-4 border-b border-slate-100 pb-5 sm:flex-row sm:items-center">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-md bg-teal-50 p-1.5 text-teal-700"><ScanLine className="h-4 w-4" /></span>
              <h2 className="text-lg font-bold text-slate-900">Kidney CT Examination</h2>
            </div>
            <p className="mt-1 max-w-3xl text-xs text-slate-500 md:text-sm">
              Upload up to 12 CT slice images. Each slice is analyzed separately; the examination summary describes agreement and available results only.
            </p>
          </div>
          <button type="button" onClick={handleLoadSample} disabled={isLoading} className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-200 disabled:opacity-50">
            <Sparkles className="h-3.5 w-3.5 text-teal-600" /> Add sample slice
          </button>
        </div>

        <div
          onDrop={(event) => { event.preventDefault(); setIsDragOver(false); if (event.dataTransfer.files.length) addFiles(event.dataTransfer.files); }}
          onDragOver={(event) => { event.preventDefault(); setIsDragOver(true); }}
          onDragLeave={() => setIsDragOver(false)}
          onClick={() => fileInputRef.current?.click()}
          className={cn("cursor-pointer rounded-xl border-2 border-dashed p-7 text-center transition", isDragOver ? "border-teal-500 bg-teal-50/50" : "border-slate-300 hover:border-teal-500 hover:bg-slate-50/60")}
        >
          <input ref={fileInputRef} type="file" multiple accept=".png,.jpg,.jpeg,.bmp,.tif,.tiff" onChange={(event) => { if (event.target.files?.length) addFiles(event.target.files); event.target.value = ""; }} className="hidden" />
          <UploadCloud className="mx-auto mb-3 h-7 w-7 text-teal-700" />
          <p className="text-sm font-semibold text-slate-800">Drop CT images here, or <span className="text-teal-700">browse files</span></p>
          <p className="mt-1 text-xs text-slate-500">PNG, JPG, JPEG, BMP, TIF or TIFF · 25 MB per image · 100 MB total · up to 12 images</p>
        </div>

        {files.length > 0 && <div className="space-y-2" aria-live="polite">
          <div className="flex items-center justify-between"><h3 className="text-sm font-semibold text-slate-800">Examination files ({files.length})</h3><button type="button" onClick={reset} disabled={isLoading} className="text-xs font-medium text-rose-700 hover:underline disabled:opacity-50">Clear all</button></div>
          <ul className="max-h-64 divide-y divide-slate-100 overflow-y-auto rounded-xl border border-slate-200">
            {files.map((file, index) => <li key={`${file.name}-${file.size}-${index}`} className="flex items-center gap-3 px-3 py-2.5">
              <FileImage className="h-4 w-4 shrink-0 text-teal-700" />
              <span className="min-w-0 flex-1 truncate text-xs font-medium text-slate-800" title={file.name}>{file.name}</span>
              <span className="whitespace-nowrap text-[11px] text-slate-500">{(file.size / 1024).toFixed(0)} KB</span>
              <span className="min-w-24 text-right text-[11px] capitalize text-slate-600">{statuses[index] ?? "Ready"}</span>
              <button type="button" onClick={(event) => { event.stopPropagation(); removeFile(index); }} disabled={isLoading} aria-label={`Remove ${file.name}`} className="rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-700 disabled:opacity-50"><X className="h-4 w-4" /></button>
            </li>)}
          </ul>
        </div>}

        <div className="flex flex-col justify-between gap-4 border-t border-slate-100 pt-4 sm:flex-row sm:items-center">
          <label htmlFor="ensemble-toggle" className="flex cursor-pointer items-start gap-3">
            <input id="ensemble-toggle" type="checkbox" checked={ensembleMode} onChange={(event) => setEnsembleMode(event.target.checked)} className="mt-1 h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500" />
            <span><span className="flex items-center gap-2 text-sm font-semibold text-slate-800"><Layers className="h-4 w-4 text-slate-600" /> Ensemble mode</span><span className="mt-0.5 block text-xs text-slate-500">Optional soft-voting; requires all ensemble checkpoints.</span></span>
          </label>
          <button type="submit" disabled={!files.length || isLoading} className={cn("inline-flex w-full items-center justify-center gap-2 rounded-lg px-6 py-2.5 text-sm font-semibold text-white transition sm:w-auto", files.length && !isLoading ? "bg-teal-700 hover:bg-teal-800" : "cursor-not-allowed bg-slate-300 text-slate-500")}>
            {isLoading ? <><span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />Analyzing examination…</> : <><ScanLine className="h-4 w-4" />Analyze {files.length || "CT"} image{files.length === 1 ? "" : "s"}</>}
          </button>
        </div>
      </div>
      {errorMessage && <div role="alert" className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" /><span>{errorMessage}</span></div>}
    </form>
  );
}

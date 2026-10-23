"use client";

import { useState, useRef } from "react";
import Image from "next/image";
import {
  UploadCloud,
  FileImage,
  X,
  ScanLine,
  Layers,
  AlertCircle,
  Sparkles,
} from "lucide-react";
import { predictImage, ApiError } from "@/lib/api";
import { ImagePredictionResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ImageUploaderProps {
  onPredictionSuccess: (result: ImagePredictionResponse, originalFile: File) => void;
  onReset: () => void;
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
}

const ACCEPTED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"];
const MAX_FILE_SIZE = 25 * 1024 * 1024; // 25 MB

export default function ImageUploader({
  onPredictionSuccess,
  onReset,
  isLoading,
  setIsLoading,
}: ImageUploaderProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [ensembleMode, setEnsembleMode] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const validateAndSetFile = (file: File) => {
    setErrorMessage(null);

    // Validate extension
    const extension = "." + file.name.split(".").pop()?.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.includes(extension)) {
      setErrorMessage(
        `Unsupported file format '${extension}'. Please upload a PNG, JPG, JPEG, BMP, TIF, or TIFF image.`
      );
      return;
    }

    // Validate size
    if (file.size > MAX_FILE_SIZE) {
      setErrorMessage("File exceeds 25 MB limit. Please select a smaller CT image slice.");
      return;
    }

    if (file.size === 0) {
      setErrorMessage("The selected file is empty.");
      return;
    }

    // Free previous preview URL if any
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }

    setSelectedFile(file);
    setPreviewUrl(URL.createObjectURL(file));
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleRemoveFile = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    setSelectedFile(null);
    setPreviewUrl(null);
    setErrorMessage(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    onReset();
  };

  const handleLoadSample = async () => {
    try {
      setErrorMessage(null);
      const res = await fetch("/sample_stone.png");
      if (!res.ok) throw new Error("Could not load sample CT image");
      const blob = await res.blob();
      const file = new File([blob], "sample_stone.png", { type: "image/png" });
      validateAndSetFile(file);
    } catch {
      setErrorMessage("Could not load sample image asset. You can upload any CT slice directly.");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setErrorMessage("Please select or drop a kidney CT slice image to analyze.");
      return;
    }

    setErrorMessage(null);
    setIsLoading(true);

    try {
      const result = await predictImage(selectedFile, ensembleMode);
      onPredictionSuccess(result, selectedFile);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else {
        setErrorMessage("Image prediction failed. Please verify that the API server is online.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Upload Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2">
              <span className="p-1.5 bg-teal-50 text-teal-700 rounded-md">
                <ScanLine className="w-4 h-4" />
              </span>
              <h2 className="text-lg font-bold text-slate-900">Kidney CT Scan Analysis</h2>
            </div>
            <p className="text-xs md:text-sm text-slate-500 mt-1">
              Upload a single axial CT slice. DenseNet-121 screens for <strong>Cyst, Normal, Stone, or Tumor</strong> with Grad-CAM localization.
            </p>
          </div>

          <button
            type="button"
            onClick={handleLoadSample}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors shrink-0"
          >
            <Sparkles className="w-3.5 h-3.5 text-teal-600" />
            <span>Load Sample CT Slice (Stone)</span>
          </button>
        </div>

        {/* Drag & Drop Zone */}
        {!selectedFile ? (
          <div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => fileInputRef.current?.click()}
            className={cn(
              "border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all",
              isDragOver
                ? "border-teal-500 bg-teal-50/50"
                : "border-slate-300 hover:border-teal-500 hover:bg-slate-50/60"
            )}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".png,.jpg,.jpeg,.bmp,.tif,.tiff"
              onChange={handleFileChange}
              className="hidden"
            />
            <div className="w-12 h-12 mx-auto rounded-full bg-teal-50 text-teal-700 flex items-center justify-center mb-3">
              <UploadCloud className="w-6 h-6" />
            </div>
            <p className="text-sm font-semibold text-slate-800">
              Drop kidney CT slice here, or <span className="text-teal-700">browse files</span>
            </p>
            <p className="text-xs text-slate-500 mt-1">
              Supports PNG, JPG, JPEG, BMP, TIF, TIFF (up to 25 MB)
            </p>
          </div>
        ) : (
          <div className="flex flex-col sm:flex-row items-center gap-5 p-4 rounded-xl border border-slate-200 bg-slate-50/50">
            {previewUrl && (
              <div className="relative w-36 h-36 rounded-lg overflow-hidden border border-slate-300 bg-black shrink-0 flex items-center justify-center">
                <Image
                  src={previewUrl}
                  alt="CT slice preview"
                  fill
                  className="object-contain"
                  unoptimized
                />
              </div>
            )}

            <div className="flex-1 min-w-0 space-y-2 text-center sm:text-left">
              <div className="flex items-center justify-center sm:justify-start gap-2">
                <FileImage className="w-4 h-4 text-teal-700 shrink-0" />
                <span className="font-semibold text-sm text-slate-800 truncate" title={selectedFile.name}>
                  {selectedFile.name}
                </span>
              </div>
              <p className="text-xs text-slate-500">
                {(selectedFile.size / 1024).toFixed(1)} KB &bull; CT Image Ready
              </p>

              <div className="flex items-center justify-center sm:justify-start gap-2 pt-1">
                <button
                  type="button"
                  onClick={handleRemoveFile}
                  className="inline-flex items-center gap-1 text-xs text-rose-600 hover:text-rose-800 hover:underline font-medium"
                >
                  <X className="w-3.5 h-3.5" />
                  <span>Remove / Replace</span>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Inference Options (Ensemble Toggle) */}
        <div className="pt-2 border-t border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="pt-0.5">
              <input
                id="ensemble-toggle"
                type="checkbox"
                checked={ensembleMode}
                onChange={(e) => setEnsembleMode(e.target.checked)}
                className="w-4 h-4 text-teal-600 rounded border-slate-300 focus:ring-teal-500"
              />
            </div>
            <label htmlFor="ensemble-toggle" className="cursor-pointer">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-slate-600" />
                <span className="text-sm font-semibold text-slate-800">
                  Ensemble Mode (Soft-voting)
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Votes across 4 architectures. Requires all checkpoints installed on the server.
              </p>
            </label>
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {errorMessage && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-900 text-sm flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold block">Inference Error</span>
            <span>{errorMessage}</span>
          </div>
        </div>
      )}

      {/* Submit Action Bar */}
      <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-xs flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="text-xs text-slate-500">
          {isLoading
            ? "Executing neural inference and Grad-CAM backpropagation..."
            : selectedFile
            ? "Ready to run OOD gate and classification."
            : "Select a CT slice to begin."}
        </div>

        <button
          type="submit"
          disabled={!selectedFile || isLoading}
          className={cn(
            "w-full sm:w-auto px-6 py-2.5 rounded-lg text-sm font-semibold text-white shadow-xs transition-all flex items-center justify-center gap-2",
            selectedFile && !isLoading
              ? "bg-teal-700 hover:bg-teal-800 active:scale-[0.99] cursor-pointer"
              : "bg-slate-300 text-slate-500 cursor-not-allowed"
          )}
        >
          {isLoading ? (
            <>
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              <span>Analyzing CT Slice...</span>
            </>
          ) : (
            <>
              <ScanLine className="w-4 h-4" />
              <span>Analyse CT Image</span>
            </>
          )}
        </button>
      </div>
    </form>
  );
}

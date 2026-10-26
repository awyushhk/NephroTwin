"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Menu, RefreshCw, Server, CheckCircle2, AlertCircle } from "lucide-react";
import { checkHealth, API_BASE_URL } from "@/lib/api";
import { cn } from "@/lib/utils";

interface HeaderProps {
  onOpenMobile: () => void;
}

export default function Header({ onOpenMobile }: HeaderProps) {
  const pathname = usePathname();
  const [healthStatus, setHealthStatus] = useState<"checking" | "online" | "offline">("checking");
  const [latencyMs, setLatencyMs] = useState<number | null>(null);

  const testConnection = async () => {
    setHealthStatus("checking");
    const start = performance.now();
    try {
      await checkHealth();
      setLatencyMs(Math.round(performance.now() - start));
      setHealthStatus("online");
    } catch {
      setLatencyMs(null);
      setHealthStatus("offline");
    }
  };

  useEffect(() => {
    testConnection();
    // Poll health check every 45 seconds
    const interval = setInterval(testConnection, 45000);
    return () => clearInterval(interval);
  }, []);

  const getBreadcrumb = () => {
    if (pathname === "/") return "Overview Dashboard";
    if (pathname.startsWith("/clinical-risk")) return "Clinical Risk Assessment (Tabular)";
    if (pathname.startsWith("/ct-analysis")) return "CT Scan Analysis (Image Deep Learning)";
    if (pathname.startsWith("/renal-digital-twin")) return "Renal Digital Twin";
    if (pathname.startsWith("/about-models")) return "Model Specifications & Governance";
    return "KidneyCare AI";
  };

  return (
    <header className="sticky top-0 z-20 flex items-center justify-between h-16 px-4 md:px-8 bg-white/95 backdrop-blur-sm border-b border-slate-200">
      <div className="flex items-center gap-3">
        <button
          onClick={onOpenMobile}
          className="md:hidden p-2 text-slate-600 hover:text-slate-900 rounded-lg hover:bg-slate-100 focus:outline-none"
          aria-label="Open sidebar"
        >
          <Menu className="w-5 h-5" />
        </button>
        <div className="flex items-center gap-2 text-sm">
          <span className="hidden sm:inline text-slate-400 font-medium">KidneyCare AI</span>
          <span className="hidden sm:inline text-slate-300">/</span>
          <h1 className="font-semibold text-slate-800 text-sm md:text-base tracking-tight">
            {getBreadcrumb()}
          </h1>
        </div>
      </div>

      {/* Backend Status Indicator */}
      <div className="flex items-center gap-3">
        <div
          className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border transition-colors",
            healthStatus === "online"
              ? "bg-emerald-50 text-emerald-800 border-emerald-200"
              : healthStatus === "checking"
              ? "bg-amber-50 text-amber-800 border-amber-200"
              : "bg-rose-50 text-rose-800 border-rose-200"
          )}
          title={`Backend target: ${API_BASE_URL}`}
        >
          {healthStatus === "online" ? (
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
          ) : healthStatus === "checking" ? (
            <Server className="w-3.5 h-3.5 text-amber-600 animate-pulse" />
          ) : (
            <AlertCircle className="w-3.5 h-3.5 text-rose-600" />
          )}

          <span className="hidden sm:inline">
            {healthStatus === "online"
              ? `API Online (${latencyMs ?? 0}ms)`
              : healthStatus === "checking"
              ? "Connecting..."
              : "API Offline"}
          </span>
          <span className="sm:hidden">
            {healthStatus === "online" ? "Online" : healthStatus === "checking" ? "..." : "Offline"}
          </span>

          <button
            onClick={testConnection}
            className="hover:opacity-75 focus:outline-none ml-0.5 p-0.5 rounded"
            aria-label="Refresh API connection"
            title="Re-check API status"
          >
            <RefreshCw
              className={cn("w-3 h-3", healthStatus === "checking" && "animate-spin")}
            />
          </button>
        </div>
      </div>
    </header>
  );
}

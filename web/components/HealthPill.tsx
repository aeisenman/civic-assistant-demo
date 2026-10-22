"use client";

/**
 * The green/red dot in the top nav: reads GET /health once on mount.
 * Rendered by ResidentNav and StaffNav. Depends on lib/health (the one-shot
 * fetch it also seeds for TracePanel and the traces page).
 */

import { modelLabel, useHealth } from "@/lib/health";

export default function HealthPill() {
  const { health, failed } = useHealth();

  // db and s3 only: since M14 GET /health makes no model call (an anonymous
  // caller polling it was unbounded Bedrock spend), so llm/embed are not in the
  // body. The model probe moved to the staff-only GET /health/deep.
  const green =
    !failed &&
    health !== null &&
    ["db", "s3"].every((k) => (health as unknown as Record<string, string>)[k] === "ok");
  const state = failed ? "down" : health ? (green ? "ok" : "degraded") : "checking";
  const label =
    state === "down"
      ? "API unreachable"
      : state === "ok"
        ? "API healthy"
        : state === "degraded"
          ? "API degraded"
          : "checking…";
  // The smart tier is the alias we send; provider_models says what answers it.
  const alias = health?.models?.smart;
  const model = alias ? modelLabel(alias, health?.provider_models ?? {}) : "";
  const title = health
    ? `db=${health.db} s3=${health.s3}` +
      (model ? ` — smart tier: ${model}` : "") +
      (health.kb_chunks != null ? ` — ${health.kb_chunks} kb chunks` : "")
    : label;

  return (
    <span
      title={title}
      data-testid="health-pill"
      data-health={state}
      className="inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/10 px-2.5 py-1 text-[12px] font-medium text-white/90"
    >
      <span
        data-testid="health-dot"
        className={`h-2 w-2 rounded-full ${
          state === "checking"
            ? "bg-slate-300"
            : state === "ok"
              ? "bg-emerald-400"
              : "bg-red-400"
        }`}
      />
      {label}
    </span>
  );
}

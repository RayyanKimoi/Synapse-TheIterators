"use client";

import { ShieldAlert, ShieldCheck } from "lucide-react";

import { formatPct, formatStopwatch, useCountUp } from "@/hooks/useCountUp";
import { formatBudget } from "@/lib/budget";
import type { CompilePlan, WorkflowIR } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useTelemetryStore } from "@/store/useTelemetryStore";

type ScoreboardProps = {
  workflow: WorkflowIR;
  plan: CompilePlan | null;
};

/**
 * The arena's bottom rail, cut back to the three numbers the race is actually
 * about plus the two guarantees behind them.
 *
 * Tokens, spend, cost avoided and the budget-burn sparkline all moved out:
 * every one of them is plotted over time in the analytics charts below, and
 * showing the same figure twice was what made this bar read as clutter.
 */
export function Scoreboard({ workflow, plan }: ScoreboardProps) {
  const runs = useTelemetryStore((state) => state.runs);

  const baselineMs = runs.baseline.frame?.elapsed_pipeline_ms ?? 0;
  const compiledMs = runs.compiled.frame?.elapsed_pipeline_ms ?? 0;
  const metrics = runs.compiled.frame?.aggregate_metrics;

  // Live reduction once both clocks are moving, else the compiler's projection.
  const speedup =
    baselineMs > 0 && compiledMs > 0
      ? 1 - compiledMs / baselineMs
      : (plan?.latency_reduction_pct ?? 0) / 100;

  const baselineRef = useCountUp(baselineMs, formatStopwatch, 0.12);
  const compiledRef = useCountUp(compiledMs, formatStopwatch, 0.12);
  const speedupRef = useCountUp(speedup, formatPct, 0.3);

  const breakerTripped = metrics?.circuit_breaker_status === "CIRCUIT_BREAKER_TRIGGERED";
  const correctness = metrics?.correctness_score ?? 0;
  const invarianceOk = correctness >= workflow.test_assertions.min_semantic_similarity;

  return (
    <footer className="void-card flex shrink-0 flex-wrap items-center gap-x-7 gap-y-3 rounded-2xl px-5 py-3">
      <Clock label="Baseline" tone="text-white/70" refObject={baselineRef} />
      <Clock label="Compiled" tone="text-stream text-glow" refObject={compiledRef} />

      <div aria-hidden className="h-8 w-px bg-white/[0.09]" />

      <div>
        <Label>Latency saved</Label>
        <div className="tabular mt-1 font-head text-[22px] font-semibold leading-none text-stream">
          <span ref={speedupRef}>0.0%</span>
        </div>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <TrustBadge
          ok={!breakerTripped}
          label={`Budget ${formatBudget(metrics?.budget_limit_usd || workflow.budget_limit_usd)}`}
          value={breakerTripped ? "Tripped" : "Pass"}
        />
        <TrustBadge
          ok={invarianceOk}
          label="Invariance"
          value={correctness > 0 ? `${(correctness * 100).toFixed(1)}%` : "—"}
        />
      </div>
    </footer>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <p className="font-sans text-[9.5px] uppercase tracking-[0.18em] text-white/40">{children}</p>
  );
}

/** Instrument-panel stopwatch — the number the whole demo hangs on. */
function Clock({
  label,
  tone,
  refObject,
}: {
  label: string;
  tone: string;
  refObject: React.RefObject<HTMLSpanElement>;
}) {
  return (
    <div className="shrink-0">
      <Label>{label}</Label>
      <div className={cn("ticker mt-1 text-[26px] font-semibold leading-none", tone)}>
        <span ref={refObject}>00:00.000</span>
      </div>
    </div>
  );
}

function TrustBadge({ ok, label, value }: { ok: boolean; label: string; value: string }) {
  const Icon = ok ? ShieldCheck : ShieldAlert;
  return (
    <div
      className={cn(
        "flex shrink-0 items-center gap-2 rounded-xl border px-2.5 py-1.5",
        ok
          ? "border-stream/30 bg-stream/[0.06] text-stream"
          : "border-state-failed/60 bg-state-failed/10 text-state-failed",
      )}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" />
      <div className="leading-tight">
        <div className="font-sans text-[9px] uppercase tracking-[0.14em] opacity-70">{label}</div>
        <div className="tabular font-head text-[11.5px] font-semibold">{value}</div>
      </div>
    </div>
  );
}

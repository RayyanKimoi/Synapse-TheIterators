"use client";

import { Coins, Gauge, ShieldAlert, ShieldCheck, Timer } from "lucide-react";

import {
  formatPct,
  formatStopwatch,
  formatTokens,
  formatUsd,
  useCountUp,
} from "@/hooks/useCountUp";
import type { CompilePlan, WorkflowIR } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useTelemetryStore } from "@/store/useTelemetryStore";

type ScoreboardProps = {
  workflow: WorkflowIR;
  plan: CompilePlan | null;
};

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
  const tokensRef = useCountUp(metrics?.total_tokens ?? 0, formatTokens, 0.3);
  const costRef = useCountUp(metrics?.total_cost_usd ?? 0, formatUsd, 0.3);
  const savedRef = useCountUp(metrics?.projected_cost_saved_usd ?? 0, formatUsd, 0.3);

  const breakerTripped = metrics?.circuit_breaker_status === "CIRCUIT_BREAKER_TRIGGERED";
  const correctness = metrics?.correctness_score ?? 0;
  const invarianceOk = correctness >= workflow.test_assertions.min_semantic_similarity;

  return (
    <footer className="relative flex items-stretch gap-4 overflow-x-auto overflow-y-hidden rounded-2xl border border-white/[0.08] liquid-chrome px-4 py-3">
      <Clock label="Baseline" tone="text-state-blocking" refObject={baselineRef} />
      <Clock label="Compiled" tone="text-state-running" refObject={compiledRef} />

      <Stat icon={<Gauge className="h-3 w-3" />} label="Latency saved">
        <span ref={speedupRef} className="text-state-cached text-glow">
          0.0%
        </span>
      </Stat>

      <Divider />

      <Stat icon={<Coins className="h-3 w-3" />} label="Tokens">
        <span ref={tokensRef}>0</span>
      </Stat>

      <Stat icon={<Coins className="h-3 w-3" />} label="Spend">
        <span ref={costRef}>$0.00000</span>
      </Stat>

      <Stat icon={<Coins className="h-3 w-3" />} label="Cost avoided">
        <span ref={savedRef} className="text-state-cached">
          $0.00000
        </span>
      </Stat>

      <Divider />

      <div className="flex shrink-0 items-center gap-2">
        <TrustBadge
          ok={!breakerTripped}
          label={`Budget cap $${workflow.budget_limit_usd.toFixed(2)}`}
          value={breakerTripped ? "TRIPPED" : "PASS"}
        />
        <TrustBadge
          ok={invarianceOk}
          label="Invariance check"
          value={correctness > 0 ? `${(correctness * 100).toFixed(1)}%` : "—"}
        />
      </div>
    </footer>
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
      <div className="flex items-center gap-1 text-[9px] uppercase tracking-[0.18em] text-muted-foreground">
        <Timer className="h-3 w-3" />
        {label}
      </div>
      <div
        className={cn(
          "ticker mt-0.5 rounded-lg border border-white/[0.07] bg-background/70 px-2.5 py-1 text-[26px] font-semibold leading-none",
          tone,
        )}
      >
        <span ref={refObject}>00:00.000</span>
      </div>
    </div>
  );
}

function Stat({
  icon,
  label,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex shrink-0 flex-col justify-center">
      <div className="flex items-center gap-1 text-[9px] uppercase tracking-[0.18em] text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="tabular mt-1 text-[17px] font-semibold leading-tight text-foreground">
        {children}
      </div>
    </div>
  );
}

function Divider() {
  return <div className="my-1 w-px shrink-0 bg-white/[0.08]" />;
}

function TrustBadge({ ok, label, value }: { ok: boolean; label: string; value: string }) {
  const Icon = ok ? ShieldCheck : ShieldAlert;
  return (
    <div
      className={cn(
        "flex shrink-0 items-center gap-1.5 rounded-xl border px-2.5 py-1.5",
        ok
          ? "border-state-cached/45 bg-state-cached/10 text-state-cached"
          : "border-state-failed/60 bg-state-failed/10 text-state-failed",
      )}
    >
      <Icon className="h-4 w-4" />
      <div className="leading-tight">
        <div className="text-[9px] uppercase tracking-wider opacity-80">{label}</div>
        <div className="tabular text-[11px] font-semibold">{value}</div>
      </div>
    </div>
  );
}

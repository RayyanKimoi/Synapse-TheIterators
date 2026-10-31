"use client";

import { ShieldCheck, ShieldAlert, Timer, Coins, Gauge } from "lucide-react";

import {
  formatPct,
  formatSeconds,
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

  const baselineRef = useCountUp(baselineMs, formatSeconds, 0.12);
  const compiledRef = useCountUp(compiledMs, formatSeconds, 0.12);
  const speedupRef = useCountUp(speedup, formatPct, 0.3);
  const tokensRef = useCountUp(metrics?.total_tokens ?? 0, formatTokens, 0.3);
  const costRef = useCountUp(metrics?.total_cost_usd ?? 0, formatUsd, 0.3);
  const savedRef = useCountUp(metrics?.projected_cost_saved_usd ?? 0, formatUsd, 0.3);

  const breakerTripped = metrics?.circuit_breaker_status === "CIRCUIT_BREAKER_TRIGGERED";
  const correctness = metrics?.correctness_score ?? 0;
  const invarianceOk = correctness >= workflow.test_assertions.min_semantic_similarity;

  return (
    <footer className="flex items-stretch gap-3 overflow-x-auto rounded-xl border border-border liquid-chrome px-4 py-2.5">
      <Stat icon={<Timer className="h-3 w-3" />} label="Baseline">
        <span ref={baselineRef} className="text-orange-400">
          0.00s
        </span>
      </Stat>

      <Stat icon={<Timer className="h-3 w-3" />} label="Compiled">
        <span ref={compiledRef} className="text-state-running">
          0.00s
        </span>
      </Stat>

      <Stat icon={<Gauge className="h-3 w-3" />} label="Latency saved">
        <span ref={speedupRef} className="text-state-cached">
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

      <div className="flex items-center gap-2">
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
    <div className="shrink-0">
      <div className="flex items-center gap-1 text-[9px] uppercase tracking-wider text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="tabular text-base font-semibold leading-tight text-foreground">{children}</div>
    </div>
  );
}

function Divider() {
  return <div className="w-px shrink-0 bg-border" />;
}

function TrustBadge({ ok, label, value }: { ok: boolean; label: string; value: string }) {
  const Icon = ok ? ShieldCheck : ShieldAlert;
  return (
    <div
      className={cn(
        "flex shrink-0 items-center gap-1.5 rounded-lg border px-2 py-1",
        ok ? "border-state-cached/50 text-state-cached" : "border-state-failed/60 text-state-failed",
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      <div className="leading-tight">
        <div className="text-[9px] uppercase tracking-wider opacity-80">{label}</div>
        <div className="tabular text-[11px] font-semibold">{value}</div>
      </div>
    </div>
  );
}

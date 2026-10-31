"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ShieldAlert, X } from "lucide-react";

import {
  BREAKER_PCT,
  WARN_PCT,
  type BudgetLevel,
  type BudgetSample,
  budgetCeiling,
  formatBudget,
  formatPctTight,
  levelsToAnnounce,
  usagePct,
} from "@/lib/budget";
import type { PipelineType } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useTelemetryStore } from "@/store/useTelemetryStore";

const LANES: { pipeline: PipelineType; label: string; stroke: string; text: string }[] = [
  { pipeline: "baseline", label: "Baseline", stroke: "hsl(var(--state-blocking))", text: "text-state-blocking" },
  { pipeline: "compiled", label: "Compiled", stroke: "hsl(var(--state-running))", text: "text-state-running" },
];

const W = 280;
const H = 36;
const WARN_DISMISS_MS = 9000;

type BudgetAlert = {
  id: string;
  lane: string;
  level: BudgetLevel;
  pct: number;
  costUsd: number;
  budgetUsd: number;
  atMs: number;
};

/**
 * Budget burn: each pipeline's spend as a percentage of the budget the circuit
 * breaker enforces, over the run, plus an alert at 80% and when the breaker
 * trips. The percentage uses the budget carried on every frame, so the graph
 * and the breaker can never disagree about where 100% is.
 */
export function BudgetBurn({ declaredBudget }: { declaredBudget: number }) {
  const runs = useTelemetryStore((state) => state.runs);
  const budget =
    runs.compiled.frame?.aggregate_metrics.budget_limit_usd ||
    runs.baseline.frame?.aggregate_metrics.budget_limit_usd ||
    declaredBudget;

  const { alerts, dismiss } = useBudgetAlerts(declaredBudget);

  const lanes = LANES.map((lane) => {
    const samples = runs[lane.pipeline].samples;
    const last = samples[samples.length - 1];
    return { ...lane, samples, pct: last ? usagePct(last.costUsd, budget) : 0, costUsd: last?.costUsd ?? 0 };
  });

  const xMax = Math.max(1000, ...lanes.flatMap((lane) => lane.samples.map((s) => s.t)));
  const peak = Math.max(0, ...lanes.map((lane) => lane.pct));
  const yTop = budgetCeiling(peak);
  const x = (t: number) => (t / xMax) * W;
  const y = (pct: number) => H - 1 - (Math.min(pct, yTop) / yTop) * (H - 2);

  const critical = alerts.some((alert) => alert.level === "breaker");
  const warned = alerts.length > 0;
  const idle = lanes.every((lane) => lane.samples.length === 0);

  return (
    <div
      className={cn(
        "flex w-[300px] shrink-0 flex-col justify-center rounded-xl border px-2.5 py-1.5 transition-colors",
        critical
          ? "border-state-failed/60 bg-state-failed/[0.06]"
          : warned
            ? "border-state-blocking/55 bg-state-blocking/[0.05]"
            : "border-white/[0.07] bg-background/40",
      )}
    >
      <div className="flex items-baseline justify-between gap-2 text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
        <span>
          Budget used · of <span className="tabular normal-case">{formatBudget(budget)}</span>
        </span>
        <span className="tabular flex gap-2 normal-case tracking-normal">
          {lanes.map((lane) => (
            <span key={lane.pipeline} className={lane.text} title={`${lane.label}: $${lane.costUsd.toFixed(6)}`}>
              {lane.label[0]} {formatPctTight(lane.pct)}
            </span>
          ))}
        </span>
      </div>

      <div className="relative mt-1">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          className="block h-9 w-full overflow-visible"
          role="img"
          aria-label={`Budget used: ${lanes
            .map((lane) => `${lane.label} ${formatPctTight(lane.pct)}`)
            .join(", ")} of ${formatBudget(budget)}. Alerts at ${WARN_PCT}% and when the breaker trips.`}
        >
          <line x1={0} x2={W} y1={H - 1} y2={H - 1} stroke="hsl(0 0% 100% / 0.1)" vectorEffect="non-scaling-stroke" />
          {yTop >= WARN_PCT && <Threshold y={y(WARN_PCT)} tone="hsl(var(--state-blocking) / 0.75)" />}
          {yTop >= BREAKER_PCT && <Threshold y={y(BREAKER_PCT)} tone="hsl(var(--state-failed) / 0.85)" />}
          {lanes.map((lane) =>
            lane.samples.length ? (
              <g key={lane.pipeline}>
                <path d={stepPath(lane.samples, x, y, budget, true)} fill={lane.stroke} fillOpacity={0.12} />
                <path
                  d={stepPath(lane.samples, x, y, budget, false)}
                  fill="none"
                  stroke={lane.stroke}
                  strokeWidth={1.5}
                  vectorEffect="non-scaling-stroke"
                />
              </g>
            ) : null,
          )}
        </svg>
        <span className="tabular pointer-events-none absolute -top-0.5 right-0 text-[8px] text-muted-foreground/70">
          {yTop >= WARN_PCT ? `${WARN_PCT}% / ${BREAKER_PCT}% lines` : `axis 0–${formatPctTight(yTop)}`}
        </span>
        {idle && (
          <span className="pointer-events-none absolute inset-0 flex items-center justify-center text-[9px] text-muted-foreground/60">
            run a pipeline to see its spend
          </span>
        )}
      </div>

      <AlertStack alerts={alerts} onDismiss={dismiss} />
    </div>
  );
}

function Threshold({ y, tone }: { y: number; tone: string }) {
  return (
    <line x1={0} x2={W} y1={y} y2={y} stroke={tone} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
  );
}

/** Spend is booked when a node completes, so the honest shape is a step, not a slope. */
function stepPath(
  samples: BudgetSample[],
  x: (t: number) => number,
  y: (pct: number) => number,
  budget: number,
  area: boolean,
): string {
  let d = `M0 ${y(0)}`;
  for (const sample of samples) {
    d += ` H${x(sample.t).toFixed(1)} V${y(usagePct(sample.costUsd, budget)).toFixed(1)}`;
  }
  if (!area) return d;
  const end = x(samples[samples.length - 1].t).toFixed(1);
  return `${d} L${end} ${H} L0 ${H} Z`;
}

/** One alert per level per run, announced the first frame it is reached. */
function useBudgetAlerts(declaredBudget: number) {
  const runs = useTelemetryStore((state) => state.runs);
  const announced = useRef(new Map<string, Set<BudgetLevel>>());
  const [alerts, setAlerts] = useState<BudgetAlert[]>([]);

  useEffect(() => {
    const fresh: BudgetAlert[] = [];
    for (const lane of LANES) {
      const frame = runs[lane.pipeline].frame;
      if (!frame) continue;
      const metrics = frame.aggregate_metrics;
      const budgetUsd = metrics.budget_limit_usd || declaredBudget;
      const pct = usagePct(metrics.total_cost_usd, budgetUsd);
      const tripped = metrics.circuit_breaker_status === "CIRCUIT_BREAKER_TRIGGERED";
      const seen = announced.current.get(frame.run_id) ?? new Set<BudgetLevel>();
      const levels = levelsToAnnounce(pct, tripped, seen);
      if (!levels.length) continue;
      levels.forEach((level) => seen.add(level));
      announced.current.set(frame.run_id, seen);
      for (const level of levels) {
        fresh.push({
          id: `${frame.run_id}:${level}`,
          lane: lane.label,
          level,
          pct,
          costUsd: metrics.total_cost_usd,
          budgetUsd,
          atMs: frame.elapsed_pipeline_ms,
        });
      }
    }
    if (fresh.length) setAlerts((list) => [...list, ...fresh]);
  }, [runs, declaredBudget]);

  const dismiss = useCallback((id: string) => {
    setAlerts((list) => list.filter((alert) => alert.id !== id));
  }, []);

  // Warnings clear themselves; a tripped breaker stays until acknowledged.
  useEffect(() => {
    const timers = alerts
      .filter((alert) => alert.level === "warn")
      .map((alert) => window.setTimeout(() => dismiss(alert.id), WARN_DISMISS_MS));
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [alerts, dismiss]);

  return { alerts, dismiss };
}

function AlertStack({ alerts, onDismiss }: { alerts: BudgetAlert[]; onDismiss: (id: string) => void }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;

  return createPortal(
    <div className="pointer-events-none fixed right-3 top-[76px] z-50 flex w-[330px] flex-col gap-2">
      {alerts.map((alert) => {
        const breaker = alert.level === "breaker";
        return (
          <div
            key={alert.id}
            role={breaker ? "alert" : "status"}
            className={cn(
              "pointer-events-auto flex items-start gap-2.5 rounded-xl border bg-card/95 p-3 shadow-[0_18px_40px_-20px_hsl(225_60%_2%/0.95)] backdrop-blur-md",
              breaker ? "border-state-failed/70" : "border-state-blocking/60",
            )}
          >
            <ShieldAlert
              className={cn("mt-0.5 h-4 w-4 shrink-0", breaker ? "text-state-failed" : "text-state-blocking")}
              aria-hidden="true"
            />
            <div className="min-w-0 flex-1">
              <p className={cn("text-[12px] font-semibold", breaker ? "text-state-failed" : "text-state-blocking")}>
                {breaker
                  ? `${alert.lane} hit its budget: circuit breaker tripped`
                  : `${alert.lane} at ${formatPctTight(alert.pct)} of its budget`}
              </p>
              <p className="tabular mt-0.5 text-[11px] leading-relaxed text-muted-foreground">
                ${alert.costUsd.toFixed(5)} of {formatBudget(alert.budgetUsd)} spent ·{" "}
                {(alert.atMs / 1000).toFixed(1)}s into the run
                {breaker ? " · further model calls refused" : ""}
              </p>
            </div>
            <button
              type="button"
              onClick={() => onDismiss(alert.id)}
              aria-label="Dismiss budget alert"
              className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-white/[0.06] hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        );
      })}
    </div>,
    document.body,
  );
}

"use client";

import { FlowCanvas } from "@/components/FlowCanvas";
import { formatStopwatch, useCountUp } from "@/hooks/useCountUp";
import type { CompilePlan, PipelineType, WorkflowIR } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useTelemetryStore, type RunState } from "@/store/useTelemetryStore";

type RaceArenaProps = {
  workflow: WorkflowIR;
  plan: CompilePlan | null;
};

export function RaceArena({ workflow, plan }: RaceArenaProps) {
  const runs = useTelemetryStore((state) => state.runs);

  // Widest point of the graph: how many nodes can actually be in flight at once.
  const concurrency =
    plan?.execution_tiers?.length
      ? Math.max(...plan.execution_tiers.map((group) => group.length))
      : 1;

  return (
    <div className="grid min-h-0 flex-1 grid-cols-2 gap-3">
      <Lane
        pipeline="baseline"
        title="Unoptimized Baseline"
        subtitle="Sequential imperative chain · one node at a time"
        run={runs.baseline}
        accent="text-state-blocking"
        rail="from-state-blocking/70"
      >
        <FlowCanvas
          workflow={workflow}
          run={runs.baseline}
          variant="baseline"
          sequence={plan?.baseline_sequence}
        />
      </Lane>

      <Lane
        pipeline="compiled"
        title="SYNAPSE Compiled"
        subtitle={
          plan
            ? `Ready-Node scheduler · dependency graph of ${plan.node_count} nodes, ${plan.edge_count} edges · up to ${concurrency} concurrent`
            : "Ready-Node scheduler · dependency-aware dispatch"
        }
        run={runs.compiled}
        accent="text-state-running"
        rail="from-state-running/70"
      >
        <FlowCanvas
          workflow={workflow}
          run={runs.compiled}
          variant="compiled"
          tiers={plan?.execution_tiers}
        />
      </Lane>
    </div>
  );
}

function Lane({
  title,
  subtitle,
  run,
  accent,
  rail,
  children,
}: {
  pipeline: PipelineType;
  title: string;
  subtitle: string;
  run: RunState;
  accent: string;
  rail: string;
  children: React.ReactNode;
}) {
  const elapsed = run.frame?.elapsed_pipeline_ms ?? 0;
  const clockRef = useCountUp(elapsed, formatStopwatch, 0.12);

  return (
    <section className="surface grain relative flex min-h-0 flex-col overflow-hidden rounded-2xl border border-white/[0.07]">
      {/* Lane identity rail along the top edge. */}
      <div
        aria-hidden
        className={cn("h-[2px] w-full bg-gradient-to-r to-transparent", rail)}
      />

      <header className="relative flex items-center gap-3 border-b border-white/[0.07] px-4 py-2.5">
        <div className="min-w-0">
          <h2 className="truncate text-[11px] font-semibold uppercase tracking-[0.16em] text-foreground">
            {title}
          </h2>
          <p className="truncate text-[10.5px] text-muted-foreground">{subtitle}</p>
        </div>

        <div className="ml-auto flex items-center gap-2.5">
          <RunBadge run={run} />
          <span ref={clockRef} className={cn("ticker text-[22px] font-semibold", accent)}>
            00:00.000
          </span>
        </div>
      </header>

      <div className="pixel-canvas relative min-h-0 flex-1">{children}</div>
    </section>
  );
}

function RunBadge({ run }: { run: RunState }) {
  const map = {
    streaming: { label: "LIVE", tone: "border-state-running/60 text-state-running", pulse: true },
    done: { label: "DONE", tone: "border-state-completed/60 text-state-completed", pulse: false },
    error: { label: "ERROR", tone: "border-state-failed/60 text-state-failed", pulse: false },
    idle: { label: "IDLE", tone: "border-white/10 text-muted-foreground", pulse: false },
  } as const;

  const { label, tone, pulse } = map[run.status];

  return (
    <span
      className={cn(
        "flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-semibold tracking-[0.14em]",
        tone,
      )}
    >
      {pulse && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current motion-reduce:animate-none" />
      )}
      {label}
    </span>
  );
}

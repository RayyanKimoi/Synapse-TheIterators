"use client";

import { Badge } from "@/components/ui/badge";
import { FlowCanvas } from "@/components/FlowCanvas";
import { formatSeconds, useCountUp } from "@/hooks/useCountUp";
import type { CompilePlan, PipelineType, WorkflowIR } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useTelemetryStore, type RunState } from "@/store/useTelemetryStore";

type RaceArenaProps = {
  workflow: WorkflowIR;
  plan: CompilePlan | null;
};

export function RaceArena({ workflow, plan }: RaceArenaProps) {
  const runs = useTelemetryStore((state) => state.runs);

  return (
    <div className="grid min-h-0 flex-1 grid-cols-2 gap-3">
      <Lane
        pipeline="baseline"
        title="Unoptimized Baseline"
        subtitle="Sequential imperative execution"
        run={runs.baseline}
        accent="text-orange-400"
      >
        <FlowCanvas workflow={workflow} run={runs.baseline} sequence={plan?.baseline_sequence} />
      </Lane>

      <Lane
        pipeline="compiled"
        title="SYNAPSE Compiled"
        subtitle={
          plan
            ? `${plan.execution_tiers.length} topological tiers · depth ${plan.max_depth}`
            : "Dependency-aware parallel dispatch"
        }
        run={runs.compiled}
        accent="text-state-running"
      >
        <FlowCanvas workflow={workflow} run={runs.compiled} tiers={plan?.execution_tiers} />
      </Lane>
    </div>
  );
}

function Lane({
  title,
  subtitle,
  run,
  accent,
  children,
}: {
  pipeline: PipelineType;
  title: string;
  subtitle: string;
  run: RunState;
  accent: string;
  children: React.ReactNode;
}) {
  const elapsed = run.frame?.elapsed_pipeline_ms ?? 0;
  const clockRef = useCountUp(elapsed, formatSeconds, 0.12);

  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-card/40">
      <header className="flex items-center gap-3 border-b border-border px-4 py-2.5">
        <div className="min-w-0">
          <h2 className="truncate text-xs font-semibold uppercase tracking-wider text-foreground">
            {title}
          </h2>
          <p className="truncate text-[11px] text-muted-foreground">{subtitle}</p>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <RunBadge run={run} />
          <span ref={clockRef} className={cn("tabular text-xl font-semibold", accent)}>
            0.00s
          </span>
        </div>
      </header>

      <div className="pixel-canvas min-h-0 flex-1">{children}</div>
    </section>
  );
}

function RunBadge({ run }: { run: RunState }) {
  if (run.status === "streaming") {
    return (
      <Badge variant="outline" className="border-state-running/60 text-[10px] text-state-running">
        LIVE
      </Badge>
    );
  }
  if (run.status === "done") {
    return (
      <Badge variant="outline" className="border-state-completed/60 text-[10px] text-state-completed">
        DONE
      </Badge>
    );
  }
  if (run.status === "error") {
    return (
      <Badge variant="outline" className="border-state-failed/60 text-[10px] text-state-failed">
        ERROR
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="text-[10px] text-muted-foreground">
      IDLE
    </Badge>
  );
}

"use client";

import { AgentProfileCard } from "@/components/AgentProfileCard";
import type { CompilePlan, WorkflowIR } from "@/lib/types";
import { nodeTelemetry, useTelemetryStore } from "@/store/useTelemetryStore";

type AgentRosterProps = {
  workflow: WorkflowIR;
  plan: CompilePlan | null;
};

/** Roster tracks the compiled pipeline — the side the compiler is optimizing. */
export function AgentRoster({ workflow, plan }: AgentRosterProps) {
  const compiled = useTelemetryStore((state) => state.runs.compiled);
  const cacheHits = compiled.frame
    ? Object.values(compiled.frame.node_states).filter((state) => state.is_cache_hit).length
    : 0;

  return (
    <aside className="flex w-[268px] shrink-0 flex-col overflow-hidden rounded-xl border border-border bg-card/40">
      <header className="flex items-baseline justify-between border-b border-border px-3 py-2.5">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-foreground">
          Agent Roster
        </h2>
        <span className="text-[10px] text-muted-foreground">
          {cacheHits}/{workflow.nodes.length} cached
        </span>
      </header>

      <div className="flex-1 space-y-2 overflow-y-auto p-2.5">
        {workflow.nodes.map((node) => (
          <AgentProfileCard
            key={node.id}
            node={node}
            telemetry={nodeTelemetry(compiled, node.id)}
            depth={plan?.node_depths[node.id]}
          />
        ))}
      </div>
    </aside>
  );
}

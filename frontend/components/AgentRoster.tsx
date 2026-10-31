"use client";

import { Users } from "lucide-react";

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
  const recall = workflow.nodes.length
    ? Math.round((cacheHits / workflow.nodes.length) * 100)
    : 0;

  return (
    <aside className="surface grain relative flex w-[284px] shrink-0 flex-col overflow-hidden rounded-2xl border border-white/[0.07]">
      <header className="relative border-b border-white/[0.07] px-3.5 py-3">
        <div className="flex items-center gap-1.5">
          <Users className="h-3.5 w-3.5 text-state-completed" />
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-foreground">
            Agent Roster
          </h2>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-white/[0.07]">
            <div
              className="h-full rounded-full bg-state-cached transition-[width] duration-500"
              style={{ width: `${recall}%` }}
            />
          </div>
          <span className="tabular shrink-0 text-[10px] text-muted-foreground">
            {cacheHits}/{workflow.nodes.length} cache recall
          </span>
        </div>
      </header>

      <div className="relative flex-1 space-y-2.5 overflow-y-auto p-2.5">
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

"use client";

import { CloudOff, Cpu, Flag, Play, Rocket, Zap } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { CompilePlan, HealthStatus, WorkflowSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

type TopNavProps = {
  workflows: WorkflowSummary[];
  selectedId: string | null;
  onSelect: (workflowId: string) => void;
  health: HealthStatus | null;
  plan: CompilePlan | null;
  cacheWarm: boolean;
  onToggleCacheWarm: () => void;
  onRunBaseline: () => void;
  onRunCompiled: () => void;
  onRunRace: () => void;
  busy: boolean;
};

export function TopNav({
  workflows,
  selectedId,
  onSelect,
  health,
  plan,
  cacheWarm,
  onToggleCacheWarm,
  onRunBaseline,
  onRunCompiled,
  onRunRace,
  busy,
}: TopNavProps) {
  return (
    <header className="flex flex-wrap items-center gap-3 rounded-xl border border-border liquid-chrome px-4 py-2.5">
      <div className="flex items-center gap-2">
        <Cpu className="h-4 w-4 text-state-running" />
        <span className="text-sm font-semibold tracking-tight text-foreground">SYNAPSE</span>
        <span className="hidden text-[10px] uppercase tracking-wider text-muted-foreground sm:inline">
          Workflow Compiler
        </span>
      </div>

      <Select value={selectedId ?? undefined} onValueChange={onSelect}>
        <SelectTrigger className="h-8 w-[260px] border-border bg-background/70 text-xs">
          <SelectValue placeholder="Select a workflow" />
        </SelectTrigger>
        <SelectContent>
          {workflows.map((workflow) => (
            <SelectItem key={workflow.workflow_id} value={workflow.workflow_id} className="text-xs">
              {workflow.name} · {workflow.node_count} nodes
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {plan && (
        <Badge variant="outline" className="border-state-completed/50 text-[10px] text-state-completed">
          {plan.execution_tiers.length} tiers · −{plan.latency_reduction_pct}% projected
        </Badge>
      )}

      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          onClick={onToggleCacheWarm}
          aria-pressed={cacheWarm}
          className={cn(
            "flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[10px] font-medium uppercase tracking-wider transition-colors",
            cacheWarm
              ? "border-state-cached/60 bg-state-cached/10 text-state-cached"
              : "border-border text-muted-foreground hover:text-foreground",
          )}
        >
          <Zap className="h-3 w-3" />
          Warm cache
        </button>

        <HealthBadge health={health} />

        <Button size="sm" variant="outline" className="h-8 text-xs" onClick={onRunBaseline} disabled={busy}>
          <Play className="mr-1 h-3 w-3" />
          Baseline
        </Button>
        <Button size="sm" variant="outline" className="h-8 text-xs" onClick={onRunCompiled} disabled={busy}>
          <Rocket className="mr-1 h-3 w-3" />
          Compiled
        </Button>
        <Button size="sm" className="h-8 text-xs" onClick={onRunRace} disabled={busy}>
          <Flag className="mr-1 h-3 w-3" />
          Run Arena Race
        </Button>
      </div>
    </header>
  );
}

function HealthBadge({ health }: { health: HealthStatus | null }) {
  if (!health) {
    return (
      <Badge variant="outline" className="border-state-failed/60 text-[10px] text-state-failed">
        <CloudOff className="mr-1 h-3 w-3" />
        Backend unreachable
      </Badge>
    );
  }

  const offline = health.llm.offline_mode;
  return (
    <Badge
      variant="outline"
      className={cn(
        "text-[10px]",
        offline
          ? "border-state-completed/50 text-state-completed"
          : "border-state-cached/50 text-state-cached",
      )}
    >
      {offline ? "Offline mode · deterministic" : health.llm.ollama ? "Ollama live" : "Proxy live"}
    </Badge>
  );
}

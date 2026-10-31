"use client";

import {
  CloudOff,
  Flag,
  Play,
  Rocket,
  Terminal,
  Workflow,
  Zap,
} from "lucide-react";

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
  /** Omit to hide the Terminal button. */
  onOpenTerminal?: () => void;
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
  onOpenTerminal,
}: TopNavProps) {
  return (
    <header className="void-card relative flex flex-wrap items-center gap-3 overflow-hidden rounded-2xl px-4 py-2.5">
      <div className="relative flex items-center gap-2.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-xl border border-stream/35 bg-stream/10 text-stream">
          <Workflow className="h-4 w-4" />
        </span>
        <div className="leading-none">
          <span className="font-head text-[14px] font-semibold tracking-tight text-white">
            Execution arena
          </span>
          <p className="mt-0.5 font-sans text-[9px] uppercase tracking-[0.2em] text-white/45">
            Baseline vs compiled
          </p>
        </div>
      </div>

      <div className="relative h-7 w-px bg-white/[0.08]" />

      <Select value={selectedId ?? undefined} onValueChange={onSelect}>
        <SelectTrigger className="relative h-9 w-[250px] rounded-xl border-white/[0.09] bg-background/60 text-xs">
          <SelectValue placeholder="Select a workflow" />
        </SelectTrigger>
        <SelectContent>
          {workflows.map((workflow) => (
            <SelectItem
              key={workflow.workflow_id}
              value={workflow.workflow_id}
              className="text-xs"
            >
              {workflow.name} · {workflow.node_count} nodes
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {plan && (
        <div className="relative flex items-center gap-1.5">
          <span className="rounded-full border border-state-running/40 bg-state-running/10 px-2 py-1 text-[9.5px] font-semibold uppercase tracking-wider text-state-running">
            Ready-Node · {plan.node_count} nodes
          </span>
          <span className="tabular rounded-full border border-state-cached/40 bg-state-cached/10 px-2 py-1 text-[9.5px] font-semibold text-state-cached">
            −{plan.latency_reduction_pct}% projected
          </span>
        </div>
      )}

      <div className="relative ml-auto flex items-center gap-2">
        <button
          type="button"
          onClick={onToggleCacheWarm}
          aria-pressed={cacheWarm}
          className={cn(
            "flex min-h-[36px] items-center gap-1.5 rounded-xl border px-2.5 text-[10px] font-semibold uppercase tracking-wider transition-colors",
            cacheWarm
              ? "border-state-cached/60 bg-state-cached/15 text-state-cached shadow-[0_0_20px_-8px_hsl(var(--state-cached)/0.9)]"
              : "border-white/[0.09] text-muted-foreground hover:text-foreground",
          )}
        >
          <Zap className={cn("h-3 w-3", cacheWarm && "fill-current")} />
          Warm cache
        </button>

        <HealthBadge health={health} />

        <Button
          size="sm"
          variant="outline"
          className="h-9 rounded-xl border-white/[0.09] text-xs"
          onClick={onRunBaseline}
          disabled={busy}
        >
          <Play className="mr-1 h-3 w-3" />
          Baseline
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="h-9 rounded-xl border-white/[0.09] text-xs"
          onClick={onRunCompiled}
          disabled={busy}
        >
          <Rocket className="mr-1 h-3 w-3" />
          Compiled
        </Button>
        <Button
          size="sm"
          className="h-9 rounded-xl bg-stream text-xs font-semibold text-black shadow-[0_0_26px_-8px_hsl(var(--stream)/0.95)] hover:opacity-90"
          onClick={onRunRace}
          disabled={busy}
        >
          <Flag className="mr-1 h-3 w-3" />
          Run Arena Race
        </Button>
        {onOpenTerminal && (
          <Button
            size="sm"
            variant="outline"
            className="h-9 rounded-xl border-white/[0.09] font-mono text-xs"
            onClick={onOpenTerminal}
            aria-keyshortcuts="`"
            title="Agent terminal (`)"
          >
            <Terminal className="mr-1 h-3 w-3" />
            Terminal
          </Button>
        )}
      </div>
    </header>
  );
}

function HealthBadge({ health }: { health: HealthStatus | null }) {
  if (!health) {
    return (
      <span className="flex items-center gap-1 rounded-xl border border-state-failed/60 bg-state-failed/10 px-2 py-1.5 text-[9.5px] font-semibold uppercase tracking-wider text-state-failed">
        <CloudOff className="h-3 w-3" />
        Backend down
      </span>
    );
  }

  const offline = health.llm.offline_mode;
  return (
    <span
      className={cn(
        "flex items-center gap-1.5 rounded-xl border px-2 py-1.5 text-[9.5px] font-semibold uppercase tracking-wider",
        offline
          ? "border-state-completed/45 bg-state-completed/10 text-state-completed"
          : "border-state-cached/45 bg-state-cached/10 text-state-cached",
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {offline
        ? "Offline · deterministic"
        : health.llm.ollama
          ? "Ollama live"
          : "Proxy live"}
    </span>
  );
}

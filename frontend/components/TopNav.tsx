"use client";

import { useRef } from "react";
import {
  CloudOff,
  Flag,
  Play,
  RefreshCw,
  Rocket,
  Terminal,
  Upload,
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

const CUSTOM_VALUE = "__custom__";

type TopNavProps = {
  workflows: WorkflowSummary[];
  selectedId: string | null;
  onSelect: (workflowId: string) => void;
  /** Name of the uploaded IR in play, or null when a predefined one is selected. */
  customLabel?: string | null;
  onUploadIr?: (file: File) => void;
  health: HealthStatus | null;
  plan: CompilePlan | null;
  cacheWarm: boolean;
  onToggleCacheWarm: () => void;
  noCache: boolean;
  onToggleNoCache: () => void;
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
  customLabel,
  onUploadIr,
  health,
  plan,
  cacheWarm,
  onToggleCacheWarm,
  noCache,
  onToggleNoCache,
  onRunBaseline,
  onRunCompiled,
  onRunRace,
  busy,
  onOpenTerminal,
}: TopNavProps) {
  const fileInput = useRef<HTMLInputElement>(null);
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

      <Select
        value={customLabel ? CUSTOM_VALUE : (selectedId ?? undefined)}
        onValueChange={(value) => {
          if (value !== CUSTOM_VALUE) onSelect(value);
        }}
      >
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
          {customLabel && (
            <SelectItem value={CUSTOM_VALUE} className="text-xs text-stream">
              {customLabel} · custom
            </SelectItem>
          )}
        </SelectContent>
      </Select>

      {onUploadIr && (
        <>
          <input
            ref={fileInput}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onUploadIr(file);
              event.target.value = "";
            }}
          />
          <Button
            size="sm"
            variant="outline"
            className="h-9 rounded-xl border-white/[0.09] text-xs"
            onClick={() => fileInput.current?.click()}
            title="Upload a custom workflow IR (.json)"
          >
            <Upload className="mr-1 h-3 w-3 text-stream" />
            Upload IR
          </Button>
        </>
      )}

      {plan && (
        <div className="relative flex items-center gap-1.5">
          <span className="rounded-full border border-stream/35 bg-stream/[0.08] px-2 py-1 font-sans text-[9.5px] font-semibold uppercase tracking-wider text-stream">
            Ready-Node · {plan.node_count} nodes
          </span>
          <span className="tabular rounded-full border border-white/15 bg-white/[0.04] px-2 py-1 font-sans text-[9.5px] font-semibold text-white/70">
            −{plan.latency_reduction_pct}% projected
          </span>
        </div>
      )}

      <div className="relative ml-auto flex items-center gap-2">
        <button
          type="button"
          onClick={onToggleNoCache}
          aria-pressed={noCache}
          title="Dry run: bypass the semantic cache so a re-run re-executes"
          className={cn(
            "flex min-h-[36px] items-center gap-1.5 rounded-xl border px-2.5 text-[10px] font-semibold uppercase tracking-wider transition-colors",
            noCache
              ? "border-amber-400/60 bg-amber-400/15 text-amber-300 shadow-[0_0_20px_-8px_rgba(251,191,36,0.9)]"
              : "border-white/[0.09] text-muted-foreground hover:text-foreground",
          )}
        >
          <RefreshCw className="h-3 w-3" />
          Dry run
        </button>
        <button
          type="button"
          onClick={onToggleCacheWarm}
          aria-pressed={cacheWarm}
          disabled={noCache}
          title={noCache ? "Disabled during a dry run" : "Pre-warm the semantic cache before the race"}
          className={cn(
            "flex min-h-[36px] items-center gap-1.5 rounded-xl border px-2.5 text-[10px] font-semibold uppercase tracking-wider transition-colors disabled:opacity-40",
            cacheWarm && !noCache
              ? "border-stream/60 bg-stream/15 text-stream shadow-[0_0_20px_-8px_hsl(var(--stream)/0.9)]"
              : "border-white/[0.09] text-muted-foreground hover:text-foreground",
          )}
        >
          <Zap className={cn("h-3 w-3", cacheWarm && !noCache && "fill-current")} />
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
            <Terminal className="mr-1 h-3 w-3 text-stream" />
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

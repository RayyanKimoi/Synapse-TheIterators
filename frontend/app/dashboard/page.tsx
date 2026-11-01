"use client";

import { useCallback, useEffect, useState } from "react";
import { Maximize2, Minimize2, PanelsTopLeft } from "lucide-react";

import { AgentRoster } from "@/components/AgentRoster";
import { AgentTerminal } from "@/components/AgentTerminal";
import { AnalyticsCharts } from "@/components/dashboard/AnalyticsCharts";
import { TelemetryMeters } from "@/components/dashboard/TelemetryMeters";
import { MatchmakerDeck } from "@/components/MatchmakerDeck";
import { RaceArena } from "@/components/RaceArena";
import { Scoreboard } from "@/components/Scoreboard";
import { TopNav } from "@/components/TopNav";
import { useWorkflowExecution } from "@/hooks/useWorkflowExecution";
import { compileWorkflow, fetchHealth, fetchWorkflow, fetchWorkflows } from "@/lib/api";
import type {
  HealthStatus,
  OptimizationCandidate,
  WorkflowSummary,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { useTelemetryStore } from "@/store/useTelemetryStore";

export default function DashboardPage() {
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [cacheWarm, setCacheWarm] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const workflow = useTelemetryStore((state) => state.workflow);
  const plan = useTelemetryStore((state) => state.plan);
  const runs = useTelemetryStore((state) => state.runs);
  const setWorkflow = useTelemetryStore((state) => state.setWorkflow);

  const { start, startRace } = useWorkflowExecution(selectedId);
  const busy = runs.baseline.status === "streaming" || runs.compiled.status === "streaming";

  // Discover the backend once on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [listed, status] = await Promise.all([fetchWorkflows(), fetchHealth()]);
        if (cancelled) return;
        setWorkflows(listed);
        setHealth(status);
        setSelectedId((current) => current ?? listed[0]?.workflow_id ?? null);
        setLoadError(null);
      } catch (error) {
        if (!cancelled) setLoadError(error instanceof Error ? error.message : String(error));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Compiling on selection gives us the dependency graph the compiled canvas needs.
  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    (async () => {
      try {
        const ir = await fetchWorkflow(selectedId);
        const compiled = await compileWorkflow(ir);
        if (!cancelled) setWorkflow(ir, compiled);
      } catch (error) {
        if (!cancelled) setLoadError(error instanceof Error ? error.message : String(error));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId, setWorkflow]);

  // Passes the developer swiped left on. The backend skips them, so a verdict
  // changes what actually runs rather than only what the deck shows.
  const [rejected, setRejected] = useState<string[]>([]);

  const runOptions = useCallback(
    () => ({ cacheWarm, disabled: rejected }),
    [cacheWarm, rejected],
  );

  const onApprove = useCallback(
    (candidate: OptimizationCandidate) => {
      // Re-approving a pass puts it back in play, then shows the difference.
      const next = rejected.filter((id) => id !== candidate.id);
      setRejected(next);
      start("compiled", { cacheWarm, disabled: next });
    },
    [start, cacheWarm, rejected],
  );

  const onReject = useCallback(
    (candidate: OptimizationCandidate) => {
      setRejected((ids) => (ids.includes(candidate.id) ? ids : [...ids, candidate.id]));
    },
    [],
  );

  const [terminalOpen, setTerminalOpen] = useState(false);

  // `arena …` in the terminal drives the same runs as the TopNav buttons,
  // honouring the cache toggle and every pass rejected in the Matchmaker.
  const onArena = useCallback(
    (action: "race" | "baseline" | "compiled") => {
      if (action === "race") startRace(runOptions());
      else start(action, runOptions());
    },
    [start, startRace, runOptions],
  );

  // Full screen is state rather than the Fullscreen API: the arena has to stay
  // inside React so the matchmaker deck and the scoreboard come with it, and a
  // state flag survives the browser refusing a fullscreen request.
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!expanded) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setExpanded(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [expanded]);

  return (
    <div className="flex min-h-full flex-col gap-3 p-4">
      <TopNav
        workflows={workflows}
        selectedId={selectedId}
        onSelect={setSelectedId}
        health={health}
        plan={plan}
        cacheWarm={cacheWarm}
        onToggleCacheWarm={() => setCacheWarm((value) => !value)}
        onRunBaseline={() => start("baseline", runOptions())}
        onRunCompiled={() => start("compiled", runOptions())}
        onRunRace={() => startRace(runOptions())}
        busy={busy}
        onOpenTerminal={() => setTerminalOpen(true)}
      />

      {loadError && (
        <div className="rounded-xl border border-state-failed/60 bg-state-failed/10 px-4 py-2 text-xs text-state-failed">
          Cannot reach the SYNAPSE backend ({loadError}). Start it with{" "}
          <code className="font-mono">uvicorn app.main:app --reload --port 8000</code> in{" "}
          <code className="font-mono">backend/</code>.
        </div>
      )}

      {workflow ? (
        <>
          {/* The arena is the page. Expanded, it takes the whole viewport —
              including the rail and the top bar — and keeps its own scoreboard. */}
          <section
            aria-label="Execution arena"
            className={cn(
              "flex flex-col gap-3",
              expanded
                ? "fixed inset-0 z-50 bg-void/95 p-4 backdrop-blur-xl"
                : "h-[min(74vh,820px)] min-h-[520px]",
            )}
          >
            <div className="relative flex min-h-0 flex-1 gap-3">
              <AgentRoster workflow={workflow} plan={plan} />
              <RaceArena workflow={workflow} plan={plan} />

              {/* Wrapped, because an absolutely-positioned flex child gets
                  stretched by the row's alignment — the wrapper takes the
                  position and the button stays a 28px square. */}
              <div className="absolute right-2.5 top-2.5 z-30">
                <button
                  type="button"
                  onClick={() => setExpanded((value) => !value)}
                  aria-pressed={expanded}
                  aria-label={expanded ? "Exit full screen" : "Expand the arena to full screen"}
                  title={expanded ? "Exit full screen (Esc)" : "Full screen"}
                  className="void-card void-card-hover grid h-7 w-7 place-items-center rounded-lg text-white/60 transition-colors hover:text-white"
                >
                  {expanded ? (
                    <Minimize2 className="h-3.5 w-3.5" />
                  ) : (
                    <Maximize2 className="h-3.5 w-3.5" />
                  )}
                </button>
              </div>

              {/* Floating matchmaker deck over the arena's right edge. */}
              <div className="pointer-events-none absolute bottom-3 right-3 z-20">
                <MatchmakerDeck
                  candidates={plan?.optimization_candidates ?? []}
                  onApprove={onApprove}
                  onReject={onReject}
                  busy={busy}
                />
              </div>
            </div>

            <Scoreboard workflow={workflow} plan={plan} />
          </section>

          {/* Analytics sit beneath the arena rather than above it, so the
              graph is what you land on and the numbers are what you scroll to. */}
          <div className="flex items-center gap-2.5 pt-3">
            <PanelsTopLeft className="h-3.5 w-3.5 text-stream" />
            <h2 className="font-head text-[12px] font-semibold uppercase tracking-[0.18em] text-white/70">
              Run analytics
            </h2>
            <span className="h-px flex-1 void-rule" />
          </div>

          <TelemetryMeters workflow={workflow} plan={plan} />
          <AnalyticsCharts workflow={workflow} />
        </>
      ) : (
        !loadError && (
          <div className="flex flex-1 items-center justify-center text-xs text-muted-foreground">
            Loading workflow…
          </div>
        )
      )}

      <AgentTerminal
        open={terminalOpen}
        onOpenChange={setTerminalOpen}
        workflowId={selectedId}
        workflows={workflows}
        busy={busy}
        onSelectWorkflow={setSelectedId}
        onArena={onArena}
      />
    </div>
  );
}

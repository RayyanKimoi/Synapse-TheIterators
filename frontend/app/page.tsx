"use client";

import { useCallback, useEffect, useState } from "react";

import { AgentRoster } from "@/components/AgentRoster";
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

  return (
    <main className="flex h-screen flex-col gap-3 bg-background p-3">
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
          <div className="relative flex min-h-0 flex-1 gap-3">
            <AgentRoster workflow={workflow} plan={plan} />
            <RaceArena workflow={workflow} plan={plan} />

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
        </>
      ) : (
        !loadError && (
          <div className="flex flex-1 items-center justify-center text-xs text-muted-foreground">
            Loading workflow…
          </div>
        )
      )}
    </main>
  );
}

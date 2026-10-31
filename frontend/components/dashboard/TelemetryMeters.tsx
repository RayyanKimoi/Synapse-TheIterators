"use client";

import type { CompilePlan, WorkflowIR } from "@/lib/types";
import { useTelemetryStore } from "@/store/useTelemetryStore";

/**
 * The arena's live telemetry strip: a ratio against a limit is a meter, so
 * each one is an accent fill on a lighter step of the same ramp rather than
 * a chart. Values come from the plan until a run produces measured ones, and
 * every meter says which of the two it is showing.
 */

type MeterProps = {
  label: string;
  /** 0..1 */
  share: number;
  value: string;
  caption: string;
};

function Meter({ label, share, value, caption }: MeterProps) {
  const clamped = Math.max(0, Math.min(1, share));
  return (
    <div className="void-card void-card-hover min-w-0 rounded-xl px-4 py-3">
      <div className="flex items-baseline justify-between gap-3">
        <p className="truncate font-sans text-[11.5px] text-white/55">{label}</p>
        <p className="shrink-0 font-head text-[14px] font-semibold leading-none text-white">
          {value}
        </p>
      </div>
      <div
        className="mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-stream/15"
        role="meter"
        aria-label={label}
        aria-valuenow={Math.round(clamped * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuetext={`${value} — ${caption}`}
      >
        <div
          className="h-full rounded-full bg-stream transition-[width] duration-700 ease-out"
          style={{ width: `${clamped * 100}%` }}
        />
      </div>
      <p className="mt-2 truncate font-sans text-[10.5px] text-white/40">{caption}</p>
    </div>
  );
}

export function TelemetryMeters({
  workflow,
  plan,
}: {
  workflow: WorkflowIR | null;
  plan: CompilePlan | null;
}) {
  const runs = useTelemetryStore((state) => state.runs);

  const nodeCount = plan?.node_count ?? workflow?.nodes.length ?? 0;
  const baseline = runs.baseline.summary;
  const compiled = runs.compiled.summary;

  // Measured once both lanes have finished; projected until then.
  const measured = baseline && compiled && baseline.total_elapsed_ms > 0;
  const savedPct = measured
    ? ((baseline.total_elapsed_ms - compiled.total_elapsed_ms) / baseline.total_elapsed_ms) * 100
    : (plan?.latency_reduction_pct ?? 0);

  const fusedNodes = new Set(
    (plan?.optimization_candidates ?? [])
      .filter((candidate) => candidate.kind === "prompt_fusion")
      .flatMap((candidate) => candidate.node_ids),
  ).size;

  const cacheHits = compiled?.cache_hits ?? 0;

  // `max_concurrency` exists on the backend plan but is not in the frontend's
  // CompilePlan type yet, and lib/types.ts belongs to another contributor —
  // so width comes from the nodes the planner actually marked parallel.
  const parallelNodes = new Set(
    (plan?.optimization_candidates ?? [])
      .filter((candidate) => candidate.kind === "parallelize")
      .flatMap((candidate) => candidate.node_ids),
  ).size;

  return (
    <div className="grid shrink-0 grid-cols-2 gap-2 lg:grid-cols-4">
      <Meter
        label="Latency saved"
        share={savedPct / 100}
        value={`${savedPct.toFixed(1)}%`}
        caption={measured ? "Measured, both lanes finished" : "Planner projection"}
      />
      <Meter
        label="Nodes fused"
        share={nodeCount ? fusedNodes / nodeCount : 0}
        value={`${fusedNodes} / ${nodeCount}`}
        caption={fusedNodes ? "Adjacent private LLM pair merged" : "No fusable pair in this graph"}
      />
      <Meter
        label="Cache hits"
        share={nodeCount ? cacheHits / nodeCount : 0}
        value={`${cacheHits} / ${nodeCount}`}
        caption={compiled ? "Served from the semantic cache" : "Awaiting a compiled run"}
      />
      <Meter
        label="Parallelised"
        share={nodeCount ? parallelNodes / nodeCount : 0}
        value={`${parallelNodes} / ${nodeCount}`}
        caption={parallelNodes ? "Dispatched off the critical path" : "Awaiting a compile"}
      />
    </div>
  );
}

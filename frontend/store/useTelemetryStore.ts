import { create } from "zustand";

import type {
  CompilePlan,
  NodeTelemetry,
  PipelineType,
  RunSummary,
  TelemetryFrame,
  WorkflowIR,
} from "@/lib/types";
import { IDLE_TELEMETRY } from "@/lib/types";

export type RunStatus = "idle" | "streaming" | "done" | "error";

export type RunState = {
  status: RunStatus;
  frame: TelemetryFrame | null;
  summary: RunSummary | null;
  error: string | null;
};

const EMPTY_RUN: RunState = { status: "idle", frame: null, summary: null, error: null };

type TelemetryStore = {
  workflow: WorkflowIR | null;
  plan: CompilePlan | null;
  runs: Record<PipelineType, RunState>;
  setWorkflow: (workflow: WorkflowIR | null, plan: CompilePlan | null) => void;
  resetRun: (pipeline: PipelineType) => void;
  resetAllRuns: () => void;
  setRunStatus: (pipeline: PipelineType, status: RunStatus, error?: string | null) => void;
  applyFrame: (frame: TelemetryFrame) => void;
  applySummary: (summary: RunSummary) => void;
};

export const useTelemetryStore = create<TelemetryStore>((set) => ({
  workflow: null,
  plan: null,
  runs: { baseline: EMPTY_RUN, compiled: EMPTY_RUN },

  setWorkflow: (workflow, plan) =>
    set({
      workflow,
      plan,
      runs: { baseline: EMPTY_RUN, compiled: EMPTY_RUN },
    }),

  resetRun: (pipeline) =>
    set((state) => ({ runs: { ...state.runs, [pipeline]: EMPTY_RUN } })),

  resetAllRuns: () => set({ runs: { baseline: EMPTY_RUN, compiled: EMPTY_RUN } }),

  setRunStatus: (pipeline, status, error = null) =>
    set((state) => ({
      runs: { ...state.runs, [pipeline]: { ...state.runs[pipeline], status, error } },
    })),

  // The frame carries its own pipeline_type, so a single handler serves both
  // sides of the race.
  applyFrame: (frame) =>
    set((state) => ({
      runs: {
        ...state.runs,
        [frame.pipeline_type]: { ...state.runs[frame.pipeline_type], frame },
      },
    })),

  applySummary: (summary) =>
    set((state) => ({
      runs: {
        ...state.runs,
        [summary.pipeline_type]: { ...state.runs[summary.pipeline_type], summary },
      },
    })),
}));

/** Telemetry for one node on one side of the race, defaulting to IDLE. */
export function nodeTelemetry(run: RunState, nodeId: string): NodeTelemetry {
  return run.frame?.node_states[nodeId] ?? IDLE_TELEMETRY;
}

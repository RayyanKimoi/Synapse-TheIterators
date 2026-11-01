"use client";

import { useCallback, useEffect, useRef } from "react";

import { streamExecute, streamUrl } from "@/lib/api";
import type {
  PipelineType,
  RunSummary,
  TelemetryFrame,
  WorkflowIR,
} from "@/lib/types";
import { useTelemetryStore } from "@/store/useTelemetryStore";

export type RunOptions = {
  cacheWarm?: boolean;
  /** Dry run: bypass the semantic cache so a re-run re-executes. */
  noCache?: boolean;
  timeScale?: number;
  /** Optimization candidate ids the developer rejected in the Matchmaker. */
  disabled?: string[];
};

/**
 * Binds the backend SSE stream to the Zustand store.
 *
 * Two transports, one lifecycle: a registered `workflowId` streams over GET
 * EventSource, while an `inlineWorkflow` (an uploaded IR the registry has never
 * seen) is POSTed and read with fetch. Each pipeline keeps a single `cancel`
 * so a new run, or unmount, tears the old one down; EventSource would otherwise
 * reconnect on close and re-run the whole workflow.
 */
export function useWorkflowExecution(
  workflowId: string | null,
  inlineWorkflow?: WorkflowIR | null,
) {
  const cancels = useRef<Partial<Record<PipelineType, () => void>>>({});

  const applyFrame = useTelemetryStore((state) => state.applyFrame);
  const applySummary = useTelemetryStore((state) => state.applySummary);
  const setRunStatus = useTelemetryStore((state) => state.setRunStatus);
  const resetRun = useTelemetryStore((state) => state.resetRun);

  const close = useCallback((pipeline: PipelineType) => {
    cancels.current[pipeline]?.();
    delete cancels.current[pipeline];
  }, []);

  const start = useCallback(
    (pipeline: PipelineType, options: RunOptions = {}) => {
      if (!inlineWorkflow && !workflowId) return;

      close(pipeline);
      resetRun(pipeline);
      setRunStatus(pipeline, "streaming");

      const onFrame = (frame: TelemetryFrame) => applyFrame(frame);
      const onComplete = (summary: RunSummary) => {
        applySummary(summary);
        setRunStatus(pipeline, "done");
        close(pipeline);
      };
      const onFail = () => {
        close(pipeline);
        const current = useTelemetryStore.getState().runs[pipeline];
        if (current.status === "streaming") {
          setRunStatus(pipeline, "error", `stream to ${pipeline} pipeline failed`);
        }
      };

      if (inlineWorkflow) {
        const controller = new AbortController();
        cancels.current[pipeline] = () => controller.abort();
        streamExecute(inlineWorkflow, pipeline, options, controller.signal, (event) => {
          if (event.event === "telemetry_update") onFrame(event.data);
          else onComplete(event.data);
        }).catch((error) => {
          if (!controller.signal.aborted) onFail();
        });
        return;
      }

      const source = new EventSource(
        streamUrl({
          workflowId: workflowId as string,
          mode: pipeline,
          cacheWarm: options.cacheWarm,
          noCache: options.noCache,
          timeScale: options.timeScale,
          disabled: options.disabled,
        }),
      );
      cancels.current[pipeline] = () => source.close();

      source.addEventListener("telemetry_update", (event) => {
        onFrame(JSON.parse((event as MessageEvent<string>).data) as TelemetryFrame);
      });
      source.addEventListener("run_complete", (event) => {
        onComplete(JSON.parse((event as MessageEvent<string>).data) as RunSummary);
      });
      // Also fires when the server closes the stream, so only a run that has
      // not reported run_complete is a real failure.
      source.onerror = onFail;
    },
    [workflowId, inlineWorkflow, applyFrame, applySummary, setRunStatus, resetRun, close],
  );

  const startRace = useCallback(
    (options: RunOptions = {}) => {
      start("baseline", options);
      start("compiled", options);
    },
    [start],
  );

  const stopAll = useCallback(() => {
    (Object.keys(cancels.current) as PipelineType[]).forEach(close);
  }, [close]);

  useEffect(() => stopAll, [stopAll]);

  return { start, startRace, stopAll };
}

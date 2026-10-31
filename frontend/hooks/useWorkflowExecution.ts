"use client";

import { useCallback, useEffect, useRef } from "react";

import { streamUrl } from "@/lib/api";
import type { PipelineType, RunSummary, TelemetryFrame } from "@/lib/types";
import { useTelemetryStore } from "@/store/useTelemetryStore";

export type RunOptions = {
  cacheWarm?: boolean;
  timeScale?: number;
  /** Optimization candidate ids the developer rejected in the Matchmaker. */
  disabled?: string[];
};

/**
 * Binds the backend SSE stream to the Zustand store.
 *
 * EventSource reconnects automatically on a closed stream, which would re-run
 * the whole workflow, so every terminal path closes the connection explicitly.
 */
export function useWorkflowExecution(workflowId: string | null) {
  const sources = useRef<Partial<Record<PipelineType, EventSource>>>({});

  const applyFrame = useTelemetryStore((state) => state.applyFrame);
  const applySummary = useTelemetryStore((state) => state.applySummary);
  const setRunStatus = useTelemetryStore((state) => state.setRunStatus);
  const resetRun = useTelemetryStore((state) => state.resetRun);

  const close = useCallback((pipeline: PipelineType) => {
    sources.current[pipeline]?.close();
    delete sources.current[pipeline];
  }, []);

  const start = useCallback(
    (pipeline: PipelineType, options: RunOptions = {}) => {
      if (!workflowId) return;

      close(pipeline);
      resetRun(pipeline);
      setRunStatus(pipeline, "streaming");

      const source = new EventSource(
        streamUrl({
          workflowId,
          mode: pipeline,
          cacheWarm: options.cacheWarm,
          timeScale: options.timeScale,
          disabled: options.disabled,
        }),
      );

      source.addEventListener("telemetry_update", (event) => {
        applyFrame(JSON.parse((event as MessageEvent<string>).data) as TelemetryFrame);
      });

      source.addEventListener("run_complete", (event) => {
        applySummary(JSON.parse((event as MessageEvent<string>).data) as RunSummary);
        setRunStatus(pipeline, "done");
        close(pipeline);
      });

      source.onerror = () => {
        // Also fires when the server closes the stream, so only a run that has
        // not reported run_complete is a real failure.
        close(pipeline);
        const current = useTelemetryStore.getState().runs[pipeline];
        if (current.status === "streaming") {
          setRunStatus(pipeline, "error", `stream to ${pipeline} pipeline failed`);
        }
      };

      sources.current[pipeline] = source;
    },
    [workflowId, applyFrame, applySummary, setRunStatus, resetRun, close],
  );

  const startRace = useCallback(
    (options: RunOptions = {}) => {
      start("baseline", options);
      start("compiled", options);
    },
    [start],
  );

  const stopAll = useCallback(() => {
    (Object.keys(sources.current) as PipelineType[]).forEach(close);
  }, [close]);

  useEffect(() => stopAll, [stopAll]);

  return { start, startRace, stopAll };
}

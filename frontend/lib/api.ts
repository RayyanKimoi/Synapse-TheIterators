import type {
  CompilePlan,
  HealthStatus,
  PipelineType,
  WorkflowIR,
  WorkflowSummary,
} from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    throw new Error(`${path} responded ${response.status}`);
  }
  return (await response.json()) as T;
}

export const fetchHealth = () => getJson<HealthStatus>("/api/v1/health");

export const fetchWorkflows = () => getJson<WorkflowSummary[]>("/api/v1/workflows");

export const fetchWorkflow = (workflowId: string) =>
  getJson<WorkflowIR>(`/api/v1/workflows/${workflowId}`);

export const compileWorkflow = (workflow: WorkflowIR) =>
  getJson<CompilePlan>("/api/v1/compile", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(workflow),
  });

export type StreamOptions = {
  workflowId: string;
  mode: PipelineType;
  cacheWarm?: boolean;
  timeScale?: number;
  disabled?: string[];
};

/** GET variant of the stream, so the browser's native EventSource can subscribe. */
export function streamUrl({
  workflowId,
  mode,
  cacheWarm,
  timeScale,
  disabled,
}: StreamOptions): string {
  const query = new URLSearchParams({
    workflow_id: workflowId,
    mode,
    cache_warm: String(Boolean(cacheWarm)),
    time_scale: String(timeScale ?? 1),
  });
  // EventSource cannot send a body, so rejected passes ride the query string.
  if (disabled?.length) query.set("disabled", disabled.join(","));
  return `${API_BASE}/api/v1/execute/stream?${query.toString()}`;
}

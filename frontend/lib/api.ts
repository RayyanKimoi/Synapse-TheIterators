import type {
  AgentEvent,
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

/**
 * Sends one terminal line to the agent and hands each event to `onEvent` as the
 * backend streams it. POST + fetch rather than EventSource: EventSource cannot
 * send a body, and a terminal line carries quotes and arbitrary length.
 */
export async function streamAgent(
  input: string,
  workflowId: string | null,
  signal: AbortSignal,
  onEvent: (event: AgentEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1/agent/run`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ input, workflow_id: workflowId }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`/api/v1/agent/run responded ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // Events end with a blank line; sse-starlette writes \r\n. Keepalive pings
    // are comment lines with no `data:`, so they fall out here.
    const events = buffer.split(/\r?\n\r?\n/);
    buffer = events.pop() ?? "";
    for (const block of events) {
      const data = block
        .split(/\r?\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (data) onEvent(JSON.parse(data) as AgentEvent);
    }
  }
}

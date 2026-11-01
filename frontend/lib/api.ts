import type {
  AgentEvent,
  CompilePlan,
  HealthStatus,
  PipelineType,
  RunSummary,
  TelemetryFrame,
  WorkflowIR,
  WorkflowSummary,
} from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

/** Pulls a human-readable reason out of a failed response body (esp. FastAPI 422). */
async function describeError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    const detail = body?.detail;
    if (Array.isArray(detail)) {
      // 422: [{loc: ["body","nodes",0,"model"], msg: "Field required"}, ...]
      return detail
        .map((item) => {
          const loc = Array.isArray(item?.loc) ? item.loc.slice(1).join(".") : "body";
          return `${loc || "body"}: ${item?.msg ?? "invalid"}`;
        })
        .join("; ");
    }
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      return String((detail as { message: unknown }).message);
    }
    return response.statusText || `HTTP ${response.status}`;
  } catch {
    return response.statusText || `HTTP ${response.status}`;
  }
}

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    throw new Error(`${path} responded ${response.status}: ${await describeError(response)}`);
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
  noCache?: boolean;
  timeScale?: number;
  disabled?: string[];
};

/** GET variant of the stream, so the browser's native EventSource can subscribe. */
export function streamUrl({
  workflowId,
  mode,
  cacheWarm,
  noCache,
  timeScale,
  disabled,
}: StreamOptions): string {
  const query = new URLSearchParams({
    workflow_id: workflowId,
    mode,
    cache_warm: String(Boolean(cacheWarm)),
    no_cache: String(Boolean(noCache)),
    time_scale: String(timeScale ?? 1),
  });
  // EventSource cannot send a body, so rejected passes ride the query string.
  if (disabled?.length) query.set("disabled", disabled.join(","));
  return `${API_BASE}/api/v1/execute/stream?${query.toString()}`;
}

export type ExecuteEvent =
  | { event: "telemetry_update"; data: TelemetryFrame }
  | { event: "run_complete"; data: RunSummary };

/**
 * Runs a raw IR the registry has never seen (an uploaded custom workflow) by
 * POSTing it in the request body and reading the SSE reply with fetch. The GET
 * `streamUrl` path cannot do this: EventSource sends no body, so it can only
 * name a registered `workflow_id`.
 */
export async function streamExecute(
  workflow: WorkflowIR,
  mode: PipelineType,
  options: { cacheWarm?: boolean; noCache?: boolean; timeScale?: number; disabled?: string[] },
  signal: AbortSignal,
  onEvent: (event: ExecuteEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1/execute/stream`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      workflow,
      mode,
      cache_warm: Boolean(options.cacheWarm),
      no_cache: Boolean(options.noCache),
      time_scale: options.timeScale ?? 1,
      disabled_optimizations: options.disabled ?? [],
    }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`/api/v1/execute/stream responded ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const lines = block.split(/\r?\n/);
      const name = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
      const data = lines
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (!name || !data) continue;
      if (name === "telemetry_update" || name === "run_complete") {
        onEvent({ event: name, data: JSON.parse(data) } as ExecuteEvent);
      }
    }
  }
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

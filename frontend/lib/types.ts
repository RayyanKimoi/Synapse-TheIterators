/** Mirrors backend/app/models/*.py. Keep field names in sync with the SSE contract. */

export type NodeStatus = "IDLE" | "RUNNING" | "CACHED" | "COMPLETED" | "FAILED";
export type PipelineType = "baseline" | "compiled";
export type CircuitBreakerStatus = "NORMAL" | "CIRCUIT_BREAKER_TRIGGERED";

export type NodeTelemetry = {
  status: NodeStatus;
  latency_ms: number;
  tokens_consumed: number;
  cost_usd: number;
  is_cache_hit: boolean;
};

export type AggregateMetrics = {
  total_tokens: number;
  total_cost_usd: number;
  projected_cost_saved_usd: number;
  circuit_breaker_status: CircuitBreakerStatus;
  correctness_score: number;
  /** The budget the breaker enforces (declared, clamped to the deployment ceiling). */
  budget_limit_usd: number;
};

export type TelemetryFrame = {
  run_id: string;
  pipeline_type: PipelineType;
  timestamp_ms: number;
  elapsed_pipeline_ms: number;
  active_nodes: string[];
  node_states: Record<string, NodeTelemetry>;
  aggregate_metrics: AggregateMetrics;
};

export type RunSummary = {
  run_id: string;
  pipeline_type: PipelineType;
  total_elapsed_ms: number;
  wall_clock_ms: number;
  node_count: number;
  cache_hits: number;
  aggregate_metrics: AggregateMetrics;
  /** Merged JSON object emitted by the workflow's terminal nodes. */
  final_output: Record<string, unknown>;
  /** Completed LLM calls by where they were served: mock, ollama, litellm_proxy. */
  llm_calls: Record<string, number>;
};

export type WorkflowNodeType = "llm_agent" | "tool_io";

export type WorkflowNode = {
  id: string;
  type: WorkflowNodeType;
  persona: string;
  system_prompt: string;
  model: string | null;
  tool_name: string | null;
  dependencies: string[];
  params: Record<string, unknown>;
  /** Node changes state elsewhere: excluded from prompt fusion and prefetching. */
  side_effect: boolean;
};

export type WorkflowIR = {
  workflow_id: string;
  name: string;
  budget_limit_usd: number;
  nodes: WorkflowNode[];
  test_assertions: {
    required_output_keys: string[];
    min_semantic_similarity: number;
    max_acceptable_latency_ms: number;
  };
};

export type WorkflowSummary = {
  workflow_id: string;
  name: string;
  node_count: number;
  source_file: string;
};

export type PipelineEstimate = {
  latency_ms: number;
  tokens: number;
  cost_usd: number;
};

export type OptimizationCandidate = {
  id: string;
  kind: "parallelize" | "prompt_fusion" | "speculative_prefetch";
  title: string;
  rationale: string;
  node_ids: string[];
  projected_latency_saved_ms: number;
  projected_tokens_saved: number;
  projected_cost_saved_usd: number;
};

export type CompilePlan = {
  workflow_id: string;
  name: string;
  node_count: number;
  edge_count: number;
  max_depth: number;
  node_depths: Record<string, number>;
  execution_tiers: string[][];
  baseline_sequence: string[];
  baseline_estimate: PipelineEstimate;
  compiled_estimate: PipelineEstimate;
  latency_reduction_pct: number;
  optimization_candidates: OptimizationCandidate[];
  warnings: string[];
};

export type HealthStatus = {
  status: string;
  environment: string;
  llm: { offline_mode: boolean; ollama: boolean; litellm_proxy: boolean };
  workflows_loaded: number;
};

export const IDLE_TELEMETRY: NodeTelemetry = {
  status: "IDLE",
  latency_ms: 0,
  tokens_consumed: 0,
  cost_usd: 0,
  is_cache_hit: false,
};

/** Mirrors backend/app/agent/terminal.py: the agent terminal's event stream. */
export type AgentTone = "text" | "muted" | "info" | "ok" | "warn" | "error" | "accent";

export type AgentEvent =
  | { type: "plan"; steps: { tool: string; title: string }[] }
  | { type: "step"; index: number; title: string }
  | { type: "line"; text: string; tone: AgentTone }
  | { type: "ui"; action: "select"; workflow_id: string }
  | { type: "done"; ok: boolean; elapsed_ms: number };

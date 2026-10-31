"""SSE telemetry contract (PRD sections 8.1 and 8.2).

Existing field names and the status vocabulary are frozen: the Zustand store and
the GSAP counters bind straight to this payload. New fields are optional and
additive, so older consumers simply ignore them.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NodeStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    CACHED = "CACHED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PipelineType(str, Enum):
    BASELINE = "baseline"
    COMPILED = "compiled"


class CircuitBreakerStatus(str, Enum):
    NORMAL = "NORMAL"
    TRIGGERED = "CIRCUIT_BREAKER_TRIGGERED"


class NodeTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: NodeStatus = NodeStatus.IDLE
    latency_ms: int = 0
    tokens_consumed: int = 0
    cost_usd: float = 0.0
    is_cache_hit: bool = False
    # Why a FAILED node failed: a tripped breaker, or a halted upstream branch.
    error: str | None = None


class AggregateMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_tokens: int = 0
    total_cost_usd: float = 0.0
    projected_cost_saved_usd: float = 0.0
    circuit_breaker_status: CircuitBreakerStatus = CircuitBreakerStatus.NORMAL
    correctness_score: float = 0.0
    # The budget the breaker enforces: the IR's budget_limit_usd clamped to the
    # deployment ceiling. Sent so a client's "% of budget" matches the breaker.
    budget_limit_usd: float = 0.0


class ContractReport(BaseModel):
    """Post-execution verdict against the IR's `test_assertions`."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    required_output_keys: list[str]
    missing_output_keys: list[str]
    latency_ms: int
    max_acceptable_latency_ms: int
    latency_ok: bool
    # None when the run cannot be certified: it halted, or a cache served an
    # output whose similarity was never measured.
    semantic_invariance: float | None
    min_semantic_similarity: float
    cache_similarity_threshold: float
    # Nodes a cache served below the admission threshold.
    cache_admission_violations: list[str] = Field(default_factory=list)
    halted: bool = False


class TelemetryFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    pipeline_type: PipelineType
    timestamp_ms: int
    elapsed_pipeline_ms: int
    active_nodes: list[str] = Field(default_factory=list)
    node_states: dict[str, NodeTelemetry] = Field(default_factory=dict)
    aggregate_metrics: AggregateMetrics = Field(default_factory=AggregateMetrics)
    # Present on the final frame only, once every node has terminated.
    contract: ContractReport | None = None


class RunSummary(BaseModel):
    """Terminal `run_complete` event; closes out the arena scoreboard."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    pipeline_type: PipelineType
    total_elapsed_ms: int
    wall_clock_ms: int
    node_count: int
    cache_hits: int
    aggregate_metrics: AggregateMetrics
    contract: ContractReport
    # Merged JSON object emitted by the workflow's terminal nodes.
    final_output: dict[str, Any] = Field(default_factory=dict)
    # Completed LLM calls by where they were actually served: mock, ollama, litellm_proxy.
    llm_calls: dict[str, int] = Field(default_factory=dict)

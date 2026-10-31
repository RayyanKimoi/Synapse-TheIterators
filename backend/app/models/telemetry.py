"""SSE telemetry contract (PRD sections 8.1 and 8.2).

Field names and the status vocabulary are frozen: the Zustand store and the
GSAP counters in Phase 2 bind straight to this payload.
"""

from enum import Enum

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


class AggregateMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_tokens: int = 0
    total_cost_usd: float = 0.0
    projected_cost_saved_usd: float = 0.0
    circuit_breaker_status: CircuitBreakerStatus = CircuitBreakerStatus.NORMAL
    correctness_score: float = 0.0


class TelemetryFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    pipeline_type: PipelineType
    timestamp_ms: int
    elapsed_pipeline_ms: int
    active_nodes: list[str] = Field(default_factory=list)
    node_states: dict[str, NodeTelemetry] = Field(default_factory=dict)
    aggregate_metrics: AggregateMetrics = Field(default_factory=AggregateMetrics)


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

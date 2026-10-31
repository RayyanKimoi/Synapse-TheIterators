"""Declarative JSON Intermediate Representation (PRD section 5.2).

Validation here is the compiler's front end: anything that survives these models
is structurally sound, so the graph passes only have to reason about topology.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NodeType(str, Enum):
    LLM_AGENT = "llm_agent"
    TOOL_IO = "tool_io"


class WorkflowNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    type: NodeType
    persona: str
    system_prompt: str
    model: str | None = None
    tool_name: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    # Declares that running this node changes state somewhere else: a write, a
    # purchase, a notification. Prompt fusion refuses to merge across one, and
    # speculative pre-fetching refuses to fire one early, because both would
    # execute it more often than the workflow asked for.
    side_effect: bool = False

    @model_validator(mode="after")
    def _check_type_contract(self) -> "WorkflowNode":
        if self.type is NodeType.LLM_AGENT and not self.model:
            raise ValueError(f"node '{self.id}': llm_agent requires 'model'")
        if self.type is NodeType.TOOL_IO and not self.tool_name:
            raise ValueError(f"node '{self.id}': tool_io requires 'tool_name'")
        if self.id in self.dependencies:
            raise ValueError(f"node '{self.id}': self-dependency is not allowed")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError(f"node '{self.id}': duplicate dependencies")
        return self


class TestAssertions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_output_keys: list[str] = Field(default_factory=list)
    min_semantic_similarity: float = Field(default=0.95, ge=0.0, le=1.0)
    max_acceptable_latency_ms: int = Field(default=15_000, gt=0)


class WorkflowIR(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_url: str | None = Field(default=None, alias="$schema")
    workflow_id: str = Field(min_length=1)
    name: str
    budget_limit_usd: float = Field(default=0.50, gt=0)
    nodes: list[WorkflowNode] = Field(min_length=1)
    test_assertions: TestAssertions = Field(default_factory=TestAssertions)

    @model_validator(mode="after")
    def _check_references(self) -> "WorkflowIR":
        ids = [node.id for node in self.nodes]
        duplicates = sorted({node_id for node_id in ids if ids.count(node_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate node ids: {', '.join(duplicates)}")

        known = set(ids)
        for node in self.nodes:
            unknown = [dep for dep in node.dependencies if dep not in known]
            if unknown:
                raise ValueError(
                    f"node '{node.id}' depends on unknown node(s): {', '.join(unknown)}"
                )
        return self

    def node_map(self) -> dict[str, WorkflowNode]:
        return {node.id: node for node in self.nodes}

    def declaration_index(self) -> dict[str, int]:
        """Stable tie-breaker so every ordering the compiler emits is deterministic."""
        return {node.id: index for index, node in enumerate(self.nodes)}

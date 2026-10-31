"""DSPy-assisted prompt fusion: adjacent read-only LLM nodes, one call.

Two LLM nodes in a chain normally cost two round trips, and the second one
re-sends the context the first already read -- the model prefills the same
tokens twice and holds two KV caches. When the pair is genuinely private to
each other, the compiler merges them into a single DSPy signature with one
output field per node, issues one request, and splits the response.

A chain is fusable only when every link is private and read-only:

  * both nodes are LLM agents on the *same* model -- one call cannot be served
    by two models;
  * the consumer depends on nothing but its producer, so no other input is
    missing at the time of the merged call;
  * the producer feeds nothing but that consumer, so no other node is deprived
    of a separately addressable output;
  * neither declares `side_effect`, because a merged call collapses two
    executions into one and that must not change what the workflow does.

Execution deliberately stays on `llm.gateway` rather than going through DSPy's
own LM. The gateway owns the budget circuit breaker, the offline mock fallback
and the cost accounting; routing around it to let DSPy make the call would
silently drop all three. DSPy's job here is what it is good at -- declaring and
validating the merged input/output contract.
"""

import logging
from dataclasses import dataclass
from typing import Any

import networkx as nx

from ..models.ir import NodeType, WorkflowIR, WorkflowNode

logger = logging.getLogger(__name__)

_dspy: Any = None
_dspy_ready = False


@dataclass(frozen=True, slots=True)
class FusionGroup:
    """A chain of LLM nodes served by one request.

    `members` is in execution order; the first is the leader that actually
    calls the model. `fields` maps each member id to its output field name in
    the merged response.
    """

    leader: str
    members: tuple[str, ...]
    model: str
    instructions: str
    fields: dict[str, str]

    @property
    def followers(self) -> tuple[str, ...]:
        return self.members[1:]


def _load_dspy() -> Any:
    """Import DSPy once; absence degrades to rendering the signature directly."""
    global _dspy, _dspy_ready
    if not _dspy_ready:
        _dspy_ready = True
        try:
            import dspy
        except ImportError as exc:
            logger.info("dspy unavailable (%s); rendering signatures directly", exc)
        else:
            _dspy = dspy
    return _dspy


def _field_name(node_id: str) -> str:
    """A node id as a signature field name: identifier-safe, still readable."""
    cleaned = "".join(char if char.isalnum() else "_" for char in node_id).strip("_")
    return cleaned or "output"


def _fusable_pair(
    producer: WorkflowNode, consumer: WorkflowNode, graph: nx.DiGraph
) -> bool:
    return (
        producer.type is NodeType.LLM_AGENT
        and consumer.type is NodeType.LLM_AGENT
        and not producer.side_effect
        and not consumer.side_effect
        and producer.model == consumer.model
        and consumer.dependencies == [producer.id]
        and list(graph.successors(producer.id)) == [consumer.id]
    )


def plan_fusion(workflow: WorkflowIR, graph: nx.DiGraph) -> dict[str, FusionGroup]:
    """Maximal fusable chains, keyed by *every* member id.

    Keying each member lets the executor ask one question -- "am I in a group,
    and am I its leader?" -- without searching.
    """
    nodes = workflow.node_map()
    chains: list[list[str]] = []
    consumed: set[str] = set()

    # Declaration order keeps the grouping deterministic, like every other pass.
    for node in workflow.nodes:
        if node.id in consumed:
            continue
        chain = [node.id]
        while True:
            successors = list(graph.successors(chain[-1]))
            if len(successors) != 1:
                break
            nxt = successors[0]
            if nxt in consumed or not _fusable_pair(nodes[chain[-1]], nodes[nxt], graph):
                break
            chain.append(nxt)
        if len(chain) > 1:
            chains.append(chain)
            consumed.update(chain)

    groups: dict[str, FusionGroup] = {}
    for chain in chains:
        members = tuple(chain)
        fields = {member: _field_name(member) for member in members}
        group = FusionGroup(
            leader=members[0],
            members=members,
            model=nodes[members[0]].model or "",
            instructions=_instructions([nodes[member] for member in members], fields),
            fields=fields,
        )
        for member in members:
            groups[member] = group
    return groups


def _instructions(members: list[WorkflowNode], fields: dict[str, str]) -> str:
    """The merged system prompt: every persona and step, in order, once."""
    steps = "\n".join(
        f"{index}. Acting as the {node.persona}, produce `{fields[node.id]}`: "
        f"{node.system_prompt}"
        for index, node in enumerate(members, start=1)
    )
    return (
        "Perform the following reasoning steps in order, in a single pass. "
        "Each step may rely on the result of the step before it.\n"
        f"{steps}"
    )


def signature_spec(group: FusionGroup) -> str:
    """`query, context -> field_a, field_b`, validated by DSPy when present."""
    spec = f"query, context -> {', '.join(group.fields[m] for m in group.members)}"
    dspy = _load_dspy()
    if dspy is None:
        return spec
    # DSPy parses and validates the field declaration, and is the component the
    # merged contract is defined by even though the gateway makes the call.
    return dspy.Signature(spec, group.instructions).signature


def fused_system_prompt(group: FusionGroup) -> str:
    return (
        f"{group.instructions}\n\n"
        f"DSPy signature: {signature_spec(group)}\n"
        "Respond with only a single JSON object whose keys are exactly: "
        f"{', '.join(group.fields[m] for m in group.members)}. "
        "Every value must be a string."
    )

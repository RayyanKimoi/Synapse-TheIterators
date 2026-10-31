"""Post-execution contract checks against the IR's `test_assertions`.

Runs once the final node has terminated. The verdict rides on the last SSE frame
and on `run_complete`.
"""

import json
from collections.abc import Mapping
from typing import Any

from ..llm.gateway import Guardrails
from ..models.ir import WorkflowIR
from ..models.telemetry import ContractReport


def extract_json_object(text: str) -> dict[str, Any] | None:
    """First JSON object in `text`, tolerating prose or code fences around it."""
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            value, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(value, dict):
                return value
        start = text.find("{", start + 1)
    return None


def final_payload(sink_outputs: Mapping[str, str]) -> dict[str, Any]:
    """Merge the JSON objects emitted by the workflow's terminal nodes."""
    payload: dict[str, Any] = {}
    for node_id in sorted(sink_outputs):
        payload.update(extract_json_object(sink_outputs[node_id]) or {})
    return payload


def evaluate_contract(
    workflow: WorkflowIR,
    guardrails: Guardrails,
    *,
    payload: Mapping[str, Any],
    latency_ms: int,
    cache_hits: Mapping[str, float],
    halted: bool,
) -> ContractReport:
    """`cache_hits` maps each node a cache served to its measured cosine
    similarity against the prompt that was actually asked."""
    assertions = workflow.test_assertions
    missing = [key for key in assertions.required_output_keys if key not in payload]
    latency_ok = latency_ms <= assertions.max_acceptable_latency_ms

    # The run is only as output-invariant as its weakest cached substitution:
    # every node that executed answered its own declared prompt exactly, so a
    # run with no cache hits is 1.0. A halted run cannot be certified at all.
    invariance = None if halted else min(cache_hits.values(), default=1.0)

    # Admission guardrail: a cache may only serve outputs whose match cleared
    # the configured threshold. `lookup` already enforces this, so a violation
    # here means an entry was admitted by something other than the live path.
    violations = sorted(
        node
        for node, similarity in cache_hits.items()
        if similarity < guardrails.cache_similarity_threshold
    )

    passed = (
        not missing
        and latency_ok
        and not halted
        and not violations
        and invariance is not None
        and invariance >= assertions.min_semantic_similarity
    )

    return ContractReport(
        passed=passed,
        required_output_keys=list(assertions.required_output_keys),
        missing_output_keys=missing,
        latency_ms=latency_ms,
        max_acceptable_latency_ms=assertions.max_acceptable_latency_ms,
        latency_ok=latency_ok,
        semantic_invariance=invariance,
        min_semantic_similarity=assertions.min_semantic_similarity,
        cache_similarity_threshold=guardrails.cache_similarity_threshold,
        cache_admission_violations=violations,
        halted=halted,
    )

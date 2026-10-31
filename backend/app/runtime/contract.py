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
    cache_hits: Mapping[str, float | None],
    halted: bool,
) -> ContractReport:
    """`cache_hits` maps each node a cache served to its match similarity
    (None when the hit was scheduled rather than measured)."""
    assertions = workflow.test_assertions
    missing = [key for key in assertions.required_output_keys if key not in payload]
    latency_ok = latency_ms <= assertions.max_acceptable_latency_ms

    # Placeholder until embedding cosine replaces it: a run is structurally
    # invariant when every node executed its own declared prompt. A halted run,
    # or one where a cache substituted an output, cannot be certified this way.
    invariance = None if halted or cache_hits else 1.0

    # Admission guardrail: a cache may only serve outputs whose match cleared the
    # configured threshold. Unmeasured hits are excluded here; they already
    # block certification above.
    violations = sorted(
        node
        for node, similarity in cache_hits.items()
        if similarity is not None and similarity < guardrails.cache_similarity_threshold
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

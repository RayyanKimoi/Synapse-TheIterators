"""V3 Phase 2: the semantic cache -- vector math, admission threshold, dynamic
TTL, and the in-memory fallback when Redis is unavailable."""

import asyncio
import json
import time

import pytest

from app import registry
from app.config import Settings
from app.llm.cache import (
    REASONING_TTL_S,
    TOOL_TTL_S,
    SemanticCache,
    embed,
    ttl_for,
)
from app.models.ir import NodeType, WorkflowIR
from app.models.telemetry import NodeStatus, PipelineType
from app.runtime.runner import stream_telemetry


@pytest.fixture
def workflow() -> WorkflowIR:
    found = registry.get("wf_deep_research_v1")
    assert found is not None
    return found


@pytest.fixture
def cache() -> SemanticCache:
    # No Redis configured in tests, so this exercises the in-memory fallback.
    return SemanticCache(Settings())


def _run(workflow: WorkflowIR, **kwargs) -> list[tuple[str, dict]]:
    async def collect() -> list[tuple[str, dict]]:
        return [
            (event["event"], json.loads(event["data"]))
            async for event in stream_telemetry(workflow, time_scale=150.0, **kwargs)
        ]

    return asyncio.run(collect())


# --- vector math -----------------------------------------------------------


def test_embeddings_are_unit_length_and_deterministic() -> None:
    async def scenario():
        # Concurrently, so the one-time encoder load is exercised under a race.
        return await asyncio.gather(
            embed("interest rate outlook"), embed("interest rate outlook")
        )

    first, second = asyncio.run(scenario())
    assert first == second
    assert sum(value * value for value in first) == pytest.approx(1.0)


def test_an_exact_repeat_scores_one_and_is_served(cache: SemanticCache) -> None:
    async def scenario():
        vectors, miss = await cache.probe("n", query="q", context="c")
        assert miss is None  # nothing stored yet
        await cache.store(
            "n", query="q", context="c", text="answer", vectors=vectors, ttl_s=60
        )
        return await cache.probe("n", query="q", context="c")

    _, hit = asyncio.run(scenario())
    assert hit is not None
    assert hit.text == "answer"
    assert hit.similarity == 1.0
    assert hit.backend == "memory"


def test_an_unrelated_question_is_not_served(cache: SemanticCache) -> None:
    async def scenario():
        vectors, _ = await cache.probe("n", query="CPI and rate projections", context="")
        await cache.store(
            "n",
            query="CPI and rate projections",
            context="",
            text="macro brief",
            vectors=vectors,
            ttl_s=60,
        )
        return await cache.probe("n", query="semiconductor export controls", context="")

    _, hit = asyncio.run(scenario())
    assert hit is None


def test_a_shared_context_cannot_outvote_a_different_question(
    cache: SemanticCache,
) -> None:
    """The failure mode a single combined vector has: the context dwarfs the
    query, so two different questions over the same context look identical."""
    bulk = " ".join(f"finding_{index} regulatory filing detail" for index in range(200))

    async def scenario():
        vectors, _ = await cache.probe("sink", query="NVIDIA supply chain", context=bulk)
        await cache.store(
            "sink",
            query="NVIDIA supply chain",
            context=bulk,
            text="nvidia brief",
            vectors=vectors,
            ttl_s=60,
        )
        return await cache.probe("sink", query="Tesla regulatory exposure", context=bulk)

    _, hit = asyncio.run(scenario())
    assert hit is None


def test_namespaces_are_isolated(cache: SemanticCache) -> None:
    async def scenario():
        vectors, _ = await cache.probe("node_a", query="q", context="c")
        await cache.store(
            "node_a", query="q", context="c", text="a", vectors=vectors, ttl_s=60
        )
        return await cache.probe("node_b", query="q", context="c")

    _, hit = asyncio.run(scenario())
    assert hit is None


def test_the_threshold_comes_from_settings() -> None:
    strict = SemanticCache(Settings(semantic_cache_similarity_threshold=0.99))
    assert strict.threshold == 0.99
    assert SemanticCache(Settings()).threshold == 0.88


def test_a_near_match_is_refused_above_its_score() -> None:
    """One shared token out of three scores well under 0.88, and a cache that is
    configured to accept anything will serve it. The threshold is the only thing
    standing between the two outcomes."""
    loose = SemanticCache(Settings(semantic_cache_similarity_threshold=0.1))
    strict = SemanticCache(Settings())

    async def scenario(target: SemanticCache):
        vectors, _ = await target.probe("n", query="alpha beta gamma", context="")
        await target.store(
            "n",
            query="alpha beta gamma",
            context="",
            text="stored",
            vectors=vectors,
            ttl_s=60,
        )
        return await target.probe("n", query="alpha delta epsilon", context="")

    _, loose_hit = asyncio.run(scenario(loose))
    _, strict_hit = asyncio.run(scenario(strict))
    assert loose_hit is not None and loose_hit.similarity < strict.threshold
    assert strict_hit is None


# --- TTL -------------------------------------------------------------------


def test_dynamic_ttl_is_short_for_tools_and_long_for_reasoning() -> None:
    assert ttl_for(NodeType.TOOL_IO) == TOOL_TTL_S == 300
    assert ttl_for(NodeType.LLM_AGENT) == REASONING_TTL_S == 86_400


def test_an_expired_entry_is_not_served_and_is_evicted(cache: SemanticCache) -> None:
    async def scenario():
        vectors, _ = await cache.probe("n", query="q", context="c")
        await cache.store(
            "n", query="q", context="c", text="stale", vectors=vectors, ttl_s=0
        )
        time.sleep(0.01)
        return await cache.probe("n", query="q", context="c")

    _, hit = asyncio.run(scenario())
    assert hit is None
    assert cache._memory["n"] == {}  # evicted on read, not left to grow


# --- Redis fallback --------------------------------------------------------


def test_an_unreachable_redis_degrades_to_memory(cache: SemanticCache) -> None:
    """Port 1 refuses connections, so the ping fails and the cache still works."""
    offline = SemanticCache(Settings(redis_port=1))

    async def scenario():
        vectors, _ = await offline.probe("n", query="q", context="c")
        await offline.store(
            "n", query="q", context="c", text="served", vectors=vectors, ttl_s=60
        )
        return await offline.probe("n", query="q", context="c")

    _, hit = asyncio.run(scenario())
    assert offline.backend == "memory"
    assert hit is not None and hit.text == "served"


def test_redis_failing_mid_run_falls_back_instead_of_raising(
    cache: SemanticCache,
) -> None:
    class Exploding:
        def scan_iter(self, match):  # noqa: ANN001 - test double
            raise ConnectionError("redis went away")

        async def set(self, *args, **kwargs):
            raise ConnectionError("redis went away")

    cache._probed = True
    cache._redis = Exploding()
    assert cache.backend == "redis"

    async def scenario():
        vectors, hit = await cache.probe("n", query="q", context="c")
        # The write fails too; neither call may propagate the error.
        await cache.store(
            "n", query="q", context="c", text="x", vectors=vectors, ttl_s=60
        )
        return hit

    assert asyncio.run(scenario()) is None
    assert cache.backend == "memory"


# --- end to end ------------------------------------------------------------


def test_a_repeat_run_is_served_entirely_from_cache(workflow: WorkflowIR) -> None:
    first = _run(workflow)[-1][1]
    second = _run(workflow)[-1][1]
    assert first["cache_hits"] == 0
    assert second["cache_hits"] == len(workflow.nodes)
    assert second["aggregate_metrics"]["total_cost_usd"] == 0
    assert second["total_elapsed_ms"] < first["total_elapsed_ms"] / 10


def test_cached_nodes_report_measured_similarity_and_no_spend(
    workflow: WorkflowIR,
) -> None:
    frame = _run(workflow, cache_warm=True)[-2][1]
    states = frame["node_states"]
    assert all(state["status"] == NodeStatus.CACHED.value for state in states.values())
    assert all(
        state["is_cache_hit"] and state["tokens_consumed"] == 0 and state["cost_usd"] == 0
        for state in states.values()
    )
    assert frame["contract"]["semantic_invariance"] == 1.0


def test_the_two_pipelines_do_not_share_cache_state(workflow: WorkflowIR) -> None:
    """The arena races them on one query; a shared cache would hand the second
    competitor the first one's work and make the comparison meaningless."""
    compiled = _run(workflow, mode=PipelineType.COMPILED)[-1][1]
    baseline = _run(workflow, mode=PipelineType.BASELINE)[-1][1]
    assert compiled["cache_hits"] == 0
    assert baseline["cache_hits"] == 0
    assert compiled["total_elapsed_ms"] < baseline["total_elapsed_ms"]

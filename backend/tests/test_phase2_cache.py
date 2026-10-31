"""V3 Phase 2: the semantic cache -- vector math, admission threshold, dynamic
TTL, and the in-memory fallback when Redis is unavailable."""

import asyncio
import json
import time

import pytest

from pydantic import ValidationError

from app import registry
from app.config import Settings
from app.llm.cache import (
    REASONING_TTL_S,
    TOOL_TTL_S,
    SemanticCache,
    embed,
    node_namespace,
    ttl_for,
)
from app.models.ir import NodeType, WorkflowIR, WorkflowNode
from app.models.telemetry import NodeStatus, PipelineType
from app.runtime.runner import stream_telemetry


@pytest.fixture
def workflow() -> WorkflowIR:
    found = registry.get("wf_deep_research_v1")
    assert found is not None
    return found


@pytest.fixture
def cache() -> SemanticCache:
    return SemanticCache(Settings(), use_redis=False)


def _run(workflow: WorkflowIR, **kwargs) -> list[tuple[str, dict]]:
    async def collect() -> list[tuple[str, dict]]:
        return [
            (event["event"], json.loads(event["data"]))
            async for event in stream_telemetry(workflow, time_scale=150.0, **kwargs)
        ]

    return asyncio.run(collect())


# --- vector math -----------------------------------------------------------


def test_the_real_encoder_is_in_use_not_the_hashed_fallback() -> None:
    """all-MiniLM-L6-v2 is 384-dimensional; the fallback is 256. Shipping on the
    fallback would silently disable paraphrase matching, so assert the real one."""
    assert len(asyncio.run(embed("probe"))) == 384


def test_a_paraphrased_question_is_served_from_cache(cache: SemanticCache) -> None:
    """The point of a semantic cache over an exact-match one. Only the real
    encoder can do this; hashed bag-of-words shares no tokens here."""

    async def scenario():
        vectors, _ = await cache.probe(
            "n", query="NVIDIA supply chain risk", context="shared context"
        )
        await cache.store(
            "n",
            query="NVIDIA supply chain risk",
            context="shared context",
            text="nvidia brief",
            vectors=vectors,
            ttl_s=60,
        )
        return await cache.probe(
            "n", query="supply chain risks for NVIDIA", context="shared context"
        )

    _, hit = asyncio.run(scenario())
    assert hit is not None
    assert hit.text == "nvidia brief"
    # Close, but not the identical prompt: a measured value, not a constant.
    assert cache.threshold <= hit.similarity < 1.0


# --- pre-flight validation -------------------------------------------------


def _node(**overrides) -> WorkflowNode:
    base = {
        "id": "n",
        "type": NodeType.TOOL_IO,
        "persona": "Crawler",
        "system_prompt": "Fetch filings.",
        "tool_name": "tavily_search",
        "params": {"index": 0},
    }
    return WorkflowNode.model_validate(base | overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"system_prompt": "Fetch something else."},
        {"params": {"index": 1}},
        {"tool_name": "other_search"},
        {"side_effect": True},
        {"id": "other_node"},
    ],
    ids=["system_prompt", "params", "tool", "side_effect", "node_id"],
)
def test_changing_any_validated_dimension_makes_an_entry_unreachable(
    overrides: dict,
) -> None:
    """Vector similarity decides whether the question is close enough. These
    dimensions are not negotiable: a different prompt or parameter means the
    stored answer is no longer this node's answer."""
    assert node_namespace("compiled", _node()) != node_namespace(
        "compiled", _node(**overrides)
    )


def test_the_same_node_keeps_one_namespace_across_runs() -> None:
    assert node_namespace("compiled", _node()) == node_namespace("compiled", _node())
    # ...but the two racing pipelines never share it.
    assert node_namespace("compiled", _node()) != node_namespace("baseline", _node())


def test_a_model_version_bump_invalidates_cached_reasoning() -> None:
    old = _node(type=NodeType.LLM_AGENT, model="ollama/qwen2.5-7b", tool_name=None)
    new = _node(type=NodeType.LLM_AGENT, model="ollama/qwen3-8b", tool_name=None)
    assert node_namespace("compiled", old) != node_namespace("compiled", new)


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
    strict = Settings(semantic_cache_similarity_threshold=0.90)
    assert SemanticCache(strict, use_redis=False).threshold == 0.90
    assert SemanticCache(Settings(), use_redis=False).threshold == 0.88


def test_the_threshold_is_held_inside_the_prd_cosine_band() -> None:
    for outside in (0.5, 0.84, 0.91, 1.0):
        with pytest.raises(ValidationError):
            Settings(semantic_cache_similarity_threshold=outside)


def test_a_near_match_is_refused_above_its_score() -> None:
    """One shared token out of three scores well under 0.88, and a cache that is
    configured to accept anything will serve it. The threshold is the only thing
    standing between the two outcomes."""
    loose = SemanticCache(Settings(), use_redis=False)
    loose.threshold = 0.1  # below the configurable band, to prove the gate acts
    strict = SemanticCache(Settings(), use_redis=False)

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
    offline = SemanticCache(Settings(redis_port=1))  # nothing listens on port 1

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
    cached = [s for s in frame["node_states"].values() if s["is_cache_hit"]]
    assert len(cached) == len(workflow.nodes) - 1  # the sink is left cold
    assert all(
        state["status"] == NodeStatus.CACHED.value
        and state["tokens_consumed"] == 0
        and state["cost_usd"] == 0
        for state in cached
    )
    # Every hit repeated its primed prompt exactly, so the weakest is still 1.0.
    assert frame["contract"]["semantic_invariance"] == 1.0


def test_the_two_pipelines_do_not_share_cache_state(workflow: WorkflowIR) -> None:
    """The arena races them on one query; a shared cache would hand the second
    competitor the first one's work and make the comparison meaningless."""
    compiled = _run(workflow, mode=PipelineType.COMPILED)[-1][1]
    baseline = _run(workflow, mode=PipelineType.BASELINE)[-1][1]
    assert compiled["cache_hits"] == 0
    assert baseline["cache_hits"] == 0
    assert compiled["total_elapsed_ms"] < baseline["total_elapsed_ms"]

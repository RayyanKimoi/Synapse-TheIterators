"""The semantic cache is deliberately process-wide: vectors are worthless if
they do not outlive a single run. That makes it shared state between tests, so
every test starts from an empty one, pinned to the in-memory backend.

Probing for a Redis that is not running costs a connection timeout per test,
and the Redis paths have their own tests in test_phase2_cache.py.
"""

from collections.abc import Iterator

import pytest

from app import registry
from app.compiler.dag import build_graph
from app.config import get_settings
from app.llm import cache as cache_module
from app.llm.cache import SemanticCache, get_cache
from app.runtime import runner
from app.runtime.paste import MIN_OBSERVATIONS, TransitionMatrix, observed_edges


@pytest.fixture(autouse=True, scope="session")
def _offline_llm() -> None:
    """The suite never calls a real model.

    A developer .env pointing at a live proxy would otherwise turn every test
    into a paid network round trip, and the deterministic latency these tests
    assert only holds for the offline profile. Live wiring is verified by hand
    against a real endpoint, not here.
    """
    settings = get_settings()
    object.__setattr__(settings, "llm_offline_mode", True)
    # The .env may hold a real Gemini key for the judge; the suite drives the
    # judge through a fake transport instead (test_judge.py).
    object.__setattr__(settings, "gemini_api_key", None)


@pytest.fixture(autouse=True)
def _empty_semantic_cache(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every test starts from an empty, memory-only process cache.

    Patching the class rather than poking the instance matters: tests call
    `get_cache.cache_clear()` mid-test to force a cold run, and a fresh instance
    would otherwise probe the developer's real Redis and be served last run's
    entries -- which is exactly the bug this guards, not a hypothetical.

    `test_phase2_cache.py` imported SemanticCache directly, so its live-Redis
    tests still get the unpatched class.
    """
    monkeypatch.setattr(
        cache_module,
        "SemanticCache",
        lambda *args, **kwargs: SemanticCache(*args, **(kwargs | {"use_redis": False})),
    )
    get_cache.cache_clear()
    yield
    get_cache.cache_clear()


@pytest.fixture(autouse=True)
def _isolated_transition_matrix(monkeypatch: pytest.MonkeyPatch) -> TransitionMatrix:
    """One in-memory matrix per test, pre-seeded with history.

    Isolation first: the real matrix is a file under the repo and PASTE learns
    from every run, so without this the suite would both pollute it and inherit
    whatever the previous test taught it.

    Seeded because the default subject of these tests is a *deployed* pipeline,
    which has run before and therefore speculates. Cold start is a real and
    different behaviour -- the first runs miss the SLA because there is no
    history to speculate from -- and it has its own tests in
    test_phase3_paste.py, which build their own empty matrices.
    """
    matrix = TransitionMatrix(":memory:")
    workflow = registry.get("wf_deep_research_v1")
    if workflow is not None:
        graph = build_graph(workflow)
        nodes = [node.id for node in workflow.nodes]
        for _ in range(MIN_OBSERVATIONS):
            matrix._record_run(nodes, observed_edges(graph, nodes))
    monkeypatch.setattr(runner, "get_matrix", lambda: matrix)
    return matrix

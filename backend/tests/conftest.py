"""The semantic cache is deliberately process-wide: vectors are worthless if
they do not outlive a single run. That makes it shared state between tests, so
every test starts from an empty one, pinned to the in-memory backend.

Probing for a Redis that is not running costs a connection timeout per test,
and the Redis paths have their own tests in test_phase2_cache.py.
"""

from collections.abc import Iterator

import pytest

from app.llm.cache import get_cache


@pytest.fixture(autouse=True)
def _empty_semantic_cache() -> Iterator[None]:
    get_cache.cache_clear()
    get_cache()._probed = True  # memory-only: skip the Redis connection probe
    yield
    get_cache.cache_clear()

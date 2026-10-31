"""The semantic cache is deliberately process-wide: vectors are worthless if
they do not outlive a single run. That makes it shared state between tests, so
every test starts from an empty one."""

import pytest

from app.llm.cache import get_cache


@pytest.fixture(autouse=True)
def _empty_semantic_cache() -> None:
    get_cache.cache_clear()

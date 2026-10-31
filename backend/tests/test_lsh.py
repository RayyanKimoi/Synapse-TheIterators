"""SimHash prefilter: the signature math, and that it never changes a verdict."""

import asyncio
import fnmatch
import math
import random

import pytest

from app.config import Settings
from app.llm import lsh
from app.llm.cache import SemanticCache, _pair_similarity

DIMS = 384  # fastembed's all-MiniLM-L6-v2


def _unit(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values]


def _random_unit(rng: random.Random, dims: int = DIMS) -> list[float]:
    return _unit([rng.gauss(0.0, 1.0) for _ in range(dims)])


def _pair_at(rng: random.Random, cosine: float, dims: int = DIMS) -> tuple[list[float], list[float]]:
    """Two unit vectors whose cosine is exactly `cosine`."""
    u = _random_unit(rng, dims)
    w = [rng.gauss(0.0, 1.0) for _ in range(dims)]
    along = sum(a * b for a, b in zip(w, u))
    w = _unit([b - along * a for a, b in zip(u, w)])  # orthogonal to u
    sine = math.sqrt(max(0.0, 1.0 - cosine * cosine))
    return u, [cosine * a + sine * b for a, b in zip(u, w)]


# --- signature math --------------------------------------------------------


def test_signatures_are_deterministic_across_rebuilds() -> None:
    """Workers sharing Redis must derive the same hyperplanes."""
    v = _random_unit(random.Random(1))
    first = lsh.signature(v)
    lsh._planes.cache_clear()
    lsh._matrix.cache_clear()
    lsh._columns.cache_clear()
    assert lsh.signature(v) == first
    assert 0 < first < 1 << lsh.BITS


def test_numpy_and_pure_python_paths_agree(monkeypatch: pytest.MonkeyPatch) -> None:
    rng = random.Random(2)
    vectors = [_random_unit(rng) for _ in range(8)]
    fast = [lsh.signature(v) for v in vectors]
    monkeypatch.setattr(lsh, "_np", None)
    slow = [lsh.signature(v) for v in vectors]
    # Only a projection within an ulp of zero could differ.
    assert all(lsh.hamming(a, b) <= lsh.ULP_SLACK for a, b in zip(fast, slow))


def test_identical_vectors_agree_and_opposite_vectors_disagree_everywhere() -> None:
    v = _random_unit(random.Random(3))
    assert lsh.hamming(lsh.signature(v), lsh.signature(v)) == 0
    assert lsh.hamming(lsh.signature(v), lsh.signature([-x for x in v])) == lsh.BITS


def test_hamming_distance_estimates_the_angle() -> None:
    rng = random.Random(4)
    for cosine in (0.95, 0.85, 0.5, 0.0):
        estimates = []
        for _ in range(40):
            a, b = _pair_at(rng, cosine)
            estimates.append(lsh.estimated_cosine(lsh.hamming(lsh.signature(a), lsh.signature(b))))
        assert abs(sum(estimates) / len(estimates) - cosine) < 0.05, cosine


# --- the prefilter's guarantees -------------------------------------------


@pytest.mark.parametrize("threshold", [0.85, 0.90])
def test_no_pair_at_the_threshold_is_pruned(threshold: float) -> None:
    """The safety property: a pair that would be admitted is never skipped.

    Pairs sit exactly *on* the threshold -- the hardest admissible case, since
    anything more similar has a smaller expected Hamming distance."""
    rng = random.Random(5)
    cutoff = lsh.max_hamming(threshold)
    for _ in range(1500):
        q = _pair_at(rng, threshold)
        c = _pair_at(rng, threshold)
        stored = (lsh.signature(q[0]), lsh.signature(c[0]))
        probed = (lsh.signature(q[1]), lsh.signature(c[1]))
        assert lsh.may_match(stored, probed, cutoff)


def test_unrelated_pairs_are_pruned() -> None:
    rng = random.Random(6)
    cutoff = lsh.max_hamming(0.85)
    pruned = sum(
        not lsh.may_match(
            (lsh.signature(_random_unit(rng)), lsh.signature(_random_unit(rng))),
            (lsh.signature(_random_unit(rng)), lsh.signature(_random_unit(rng))),
            cutoff,
        )
        for _ in range(300)
    )
    assert pruned == 300


def test_cutoff_tightens_as_the_threshold_rises() -> None:
    cutoffs = [lsh.max_hamming(t) for t in (-1.0, 0.0, 0.5, 0.85, 0.9, 0.99, 1.0)]
    assert cutoffs == sorted(cutoffs, reverse=True)
    assert cutoffs[0] == lsh.BITS  # threshold -1 admits everything
    assert cutoffs[-1] == lsh.ULP_SLACK  # threshold 1 admits exact repeats only


def test_encoding_round_trips_and_garbage_falls_through_to_the_exact_check() -> None:
    sigs = (lsh.signature(_random_unit(random.Random(7))), 1)
    assert lsh.decode(lsh.encode(sigs)) == sigs
    assert lsh.decode("not-a-signature") is None
    assert lsh.may_match(None, sigs, 0)  # unreadable index entries are kept


# --- in the cache ----------------------------------------------------------

UNRELATED = [
    f"topic{n} alpha{n} bravo{n} charlie{n} delta{n} echo{n}" for n in range(60)
]


def _memory_cache() -> SemanticCache:
    return SemanticCache(Settings(), use_redis=False)


async def _fill(cache: SemanticCache, namespace: str, queries: list[str]) -> None:
    for query in queries:
        vectors, _ = await cache.probe(namespace, query=query, context="shared context")
        await cache.store(
            namespace, query=query, context="shared context", text=query, vectors=vectors, ttl_s=60
        )


def test_the_prefilter_skips_unrelated_entries_and_still_serves_the_repeat() -> None:
    cache = _memory_cache()

    async def scenario():
        await _fill(cache, "n", [*UNRELATED, "NVIDIA supply chain risk"])
        probe = await cache._embed_pair("NVIDIA supply chain risk", "shared context")
        candidates, pruned = await cache._candidates("n", lsh.pair_signatures(probe))
        _, hit = await cache.probe("n", query="NVIDIA supply chain risk", context="shared context")
        return candidates, pruned, hit

    candidates, pruned, hit = asyncio.run(scenario())
    assert pruned >= len(UNRELATED) - 2  # lexical hash collisions may let one or two through
    assert any(text == "NVIDIA supply chain risk" for _, text in candidates)
    assert hit is not None and hit.text == "NVIDIA supply chain risk" and hit.similarity == 1.0


def test_the_prefilter_never_changes_the_answer() -> None:
    """Best match through the prefilter == best match over every entry, exactly."""
    cache = _memory_cache()
    probes = ["topic3 alpha3 bravo3", "delta7 echo7 topic7 alpha7", "nothing in common here"]

    async def scenario():
        await _fill(cache, "n", UNRELATED)
        results = []
        for query in probes:
            vectors = await cache._embed_pair(query, "shared context")
            everything = await cache._entries("n")
            filtered, _ = await cache._candidates("n", lsh.pair_signatures(vectors))
            results.append((vectors, everything, filtered))
        return results

    for vectors, everything, filtered in asyncio.run(scenario()):
        best_all = max(everything, key=lambda e: _pair_similarity(e[0], vectors))
        admitted_all = _pair_similarity(best_all[0], vectors) >= cache.threshold
        admitted_filtered = any(
            _pair_similarity(e[0], vectors) >= cache.threshold for e in filtered
        )
        assert admitted_all == admitted_filtered
        if admitted_all:
            assert best_all in filtered


# --- Redis index, against an in-process double -------------------------------


class FakeRedis:
    """Just enough of redis.asyncio for the cache, with call accounting."""

    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.fetched: list[int] = []

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.strings[key] = value

    async def hset(self, name: str, key: str, value: str) -> None:
        self.hashes.setdefault(name, {})[key] = value

    async def expire(self, name: str, ttl: int) -> None:
        pass

    async def hgetall(self, name: str) -> dict[str, str]:
        return dict(self.hashes.get(name, {}))

    async def hdel(self, name: str, *keys: str) -> None:
        for key in keys:
            self.hashes.get(name, {}).pop(key, None)

    async def mget(self, keys: list[str]) -> list[str | None]:
        self.fetched.append(len(keys))
        return [self.strings.get(key) for key in keys]

    async def scan_iter(self, match: str):
        for key in list(self.strings):
            if fnmatch.fnmatchcase(key, match):
                yield key


def _redis_cache() -> tuple[SemanticCache, FakeRedis]:
    cache = SemanticCache(Settings(), use_redis=False)
    fake = FakeRedis()
    cache._probed, cache._redis = True, fake
    return cache, fake


def test_redis_fetches_only_the_survivors() -> None:
    cache, fake = _redis_cache()

    async def scenario():
        await _fill(cache, "n", [*UNRELATED, "rate outlook"])
        fake.fetched.clear()
        return await cache.probe("n", query="rate outlook", context="shared context")

    _, hit = asyncio.run(scenario())
    assert cache.backend == "redis"
    assert hit is not None and hit.text == "rate outlook" and hit.backend == "redis"
    assert fake.fetched and fake.fetched[-1] < len(UNRELATED) // 10  # not a full read


def test_redis_drops_index_fields_whose_entry_expired() -> None:
    cache, fake = _redis_cache()

    async def scenario():
        await _fill(cache, "n", ["rate outlook"])
        fake.strings.clear()  # the entry's TTL ran out; its index field did not
        hit = (await cache.probe("n", query="rate outlook", context="shared context"))[1]
        return hit

    assert asyncio.run(scenario()) is None
    assert all(not fields for fields in fake.hashes.values())


def test_redis_still_serves_entries_written_before_the_index() -> None:
    cache, fake = _redis_cache()

    async def scenario():
        await _fill(cache, "n", ["rate outlook"])
        fake.hashes.clear()  # as if an older build wrote it: entry, no index
        return await cache.probe("n", query="rate outlook", context="shared context")

    _, hit = asyncio.run(scenario())
    assert hit is not None and hit.text == "rate outlook"

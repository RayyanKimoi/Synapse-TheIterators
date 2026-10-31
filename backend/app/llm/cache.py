"""Context-aware semantic cache for node outputs.

A node's prompt is embedded as *two* vectors -- the user query and the upstream
context -- and both must clear `semantic_cache_similarity_threshold` against an
entry stored for that same node before it is served. One combined vector does
not work: a node deep in the graph carries far more context text than query
text, so a long shared context swamps the cosine and two genuinely different
questions score as a match. Scoring the halves separately is what makes this
cache context-aware rather than merely similar-looking.

A hit is served for no model call, no tokens and no spend. A miss is stored
after the node executes, under a TTL chosen from the node's type.

Backing store is Redis when it is reachable and an in-memory dictionary
otherwise. The choice is made on first use and never retried, so a Redis that
is down -- or that drops mid-run -- degrades the cache instead of failing the
pipeline.

Embeddings come from fastembed (`all-MiniLM-L6-v2`) when it is installed. The
pure-Python hashed bag-of-words fallback keeps the cache working on a machine
with no model downloaded: it scores exact repeats at 1.0, but it is lexical, so
it is far weaker on paraphrases than the real encoder.

Every stored vector also carries a 256-bit SimHash signature (`lsh.py`). A probe
compares signatures first -- one XOR and popcount per half -- and computes the
exact cosine only for entries whose Hamming distance is consistent with the
threshold. On Redis the signatures live in a small per-namespace hash, so a
pruned entry's vectors are never fetched at all. Admission is still decided by
the exact cosine; the signatures only decide what is worth checking.
"""

import asyncio
import hashlib
import importlib
import json
import logging
import math
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from . import lsh
from ..config import Settings, get_settings
from ..observability import record, span
from ..models.ir import NodeType, WorkflowNode

logger = logging.getLogger(__name__)

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
KEY_PREFIX = "synapse:sc"
FALLBACK_DIMS = 256
# Hard ceiling on any single Redis operation, connect included. Socket timeouts
# alone are not enough: redis-py retries with backoff underneath them, so a
# server that disappears mid-run took ~15s to be declared dead -- long enough to
# freeze a live run. wait_for bounds the whole call, retries and all, whatever
# the client does internally.
REDIS_TIMEOUT_S = 1.5
# A root node has no upstream context. Embedding a constant rather than "" keeps
# two empty contexts scoring 1.0 against each other instead of 0.0.
EMPTY_CONTEXT = "[no upstream context]"

# Dynamic TTL: a real-time tool read goes stale within minutes, while
# deterministic reasoning over fixed context stays valid for a day.
TOOL_TTL_S = 300
REASONING_TTL_S = 86_400


def ttl_for(node_type: NodeType) -> int:
    return TOOL_TTL_S if node_type is NodeType.TOOL_IO else REASONING_TTL_S


@dataclass(frozen=True, slots=True)
class CacheHit:
    text: str
    similarity: float
    latency_ms: int
    backend: str  # redis | memory


Vector = list[float]
# (query, context)
Vectors = tuple[Vector, Vector]

_embedder: Any = None
_embedder_ready = False
_embedder_lock = asyncio.Lock()


def _normalize(values: Vector) -> Vector:
    """Unit-length, so cosine similarity is a plain dot product."""
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values] if norm else values


def _hash_vector(text: str) -> Vector:
    """shortcut: lexical hashed bag-of-words, no paraphrase sensitivity.
    Install fastembed for real sentence embeddings."""
    counts = [0.0] * FALLBACK_DIMS
    for token in text.lower().split():
        digest = hashlib.blake2b(token.encode(), digest_size=4).digest()
        counts[int.from_bytes(digest, "big") % FALLBACK_DIMS] += 1.0
    return _normalize(counts)


async def _load_embedder() -> None:
    """Import and construct the encoder once per process, under a lock.

    Without the lock, nodes dispatched concurrently would race and some would
    embed with the fallback while others used fastembed -- two different vector
    spaces, so every similarity between them would be meaningless.
    """
    global _embedder, _embedder_ready
    async with _embedder_lock:
        if _embedder_ready:
            return
        try:
            module = await asyncio.to_thread(importlib.import_module, "fastembed")
            _embedder = await asyncio.to_thread(module.TextEmbedding, EMBED_MODEL)
        except Exception as exc:  # not installed, or no model cached locally
            logger.info("fastembed unavailable (%s); using hashed embeddings", exc)
        finally:
            _embedder_ready = True


async def embed_many(texts: list[str]) -> list[Vector]:
    """One encoder invocation for the whole batch.

    Batching matters: a probe needs the query and the context vector, and two
    separate calls cost twice the model overhead -- enough to push a cache hit
    past the latency it exists to avoid.
    """
    if not _embedder_ready:
        await _load_embedder()
    if _embedder is None:
        return [_hash_vector(text) for text in texts]
    # fastembed is synchronous CPU work: off the event loop it goes.
    vectors = await asyncio.to_thread(lambda: list(_embedder.embed(texts)))
    return [_normalize([float(value) for value in vector]) for vector in vectors]


async def embed(text: str) -> Vector:
    return (await embed_many([text]))[0]


def _cosine(left: Vector, right: Vector) -> float:
    # A length mismatch means a different embedder wrote one of them, so the two
    # vectors live in different spaces and are not comparable at all.
    if len(left) != len(right):
        return 0.0
    return sum(x * y for x, y in zip(left, right))


def _pair_similarity(stored: Vectors, probed: Vectors) -> float:
    """A hit has to match on the question *and* on the context, so a pair is
    only as similar as its weaker half."""
    return min(_cosine(stored[0], probed[0]), _cosine(stored[1], probed[1]))


def _parse(blobs: list[str | None]) -> list[tuple[Vectors, str]]:
    entries: list[tuple[Vectors, str]] = []
    for blob in blobs:
        if not blob:
            continue
        try:
            entry = json.loads(blob)
            entries.append(((entry["q"], entry["c"]), entry["t"]))
        except (ValueError, KeyError, TypeError):
            continue  # a foreign key landed under our prefix
    return entries


def _digest(text: str) -> str:
    return hashlib.blake2b(text.encode(), digest_size=8).hexdigest()


def node_namespace(scope: str, node: WorkflowNode) -> str:
    """Pre-flight validation, enforced as key separation.

    An entry is only reachable when the model, the system prompt and the tool
    parameters are byte-identical to the ones that produced it. Vector
    similarity decides whether the *question* is close enough; these are the
    dimensions where close enough is simply wrong -- a new model version or an
    edited system prompt means the stored answer is no longer that node's
    answer. `scope` separates the two racing pipelines.
    """
    fingerprint = _digest(
        json.dumps(
            {
                "model": node.model,
                "tool": node.tool_name,
                "system_prompt": node.system_prompt,
                "params": node.params,
                "side_effect": node.side_effect,
            },
            sort_keys=True,
            default=str,
        )
    )
    return f"{scope}|{node.id}|{fingerprint}"


class SemanticCache:
    """Per-namespace vector store. One namespace per node, so a cached answer
    can never be served for a different node's question."""

    def __init__(self, settings: Settings | None = None, *, use_redis: bool = True) -> None:
        self.settings = settings or get_settings()
        self.threshold = self.settings.semantic_cache_similarity_threshold
        # namespace -> digest -> (expires_at, vectors, text, signatures)
        self._memory: dict[str, dict[str, tuple[float, Vectors, str, lsh.Signatures]]] = {}
        self._redis: Any = None
        # `use_redis=False` skips the connection probe for a caller that already
        # knows there is no server, rather than paying its timeout to find out.
        self._probed = not use_redis

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    @property
    def _cutoff(self) -> int:
        """Widest Hamming distance a pair at the threshold plausibly shows.

        Read per probe rather than fixed at construction: `threshold` is a plain
        attribute, and a cutoff left tighter than a lowered threshold would prune
        entries the threshold admits. `max_hamming` is memoized, so this is a
        dictionary lookup.
        """
        return lsh.max_hamming(self.threshold)

    async def stats(self) -> dict[str, object]:
        """Backend, gate settings and live entry counts, for the agent terminal.

        Counting on Redis reads the signature index (HLEN per namespace), never
        the vectors; a field whose entry has expired but not yet been pruned is
        still counted, so the figure is an upper bound there.
        """
        client = await self._client()
        namespaces = entries = 0
        if client is None:
            now = time.time()
            for bucket in self._memory.values():
                live = sum(1 for expires, *_ in bucket.values() if expires > now)
                namespaces += bool(live)
                entries += live
        else:

            async def count() -> tuple[int, int]:
                found = total = 0
                async for key in client.scan_iter(match=f"{KEY_PREFIX}:idx:*"):
                    found += 1
                    total += await client.hlen(key)
                return found, total

            try:
                namespaces, entries = await asyncio.wait_for(count(), REDIS_TIMEOUT_S)
            except Exception as exc:
                self._degrade(exc)
                return await self.stats()
        return {
            "backend": self.backend,
            "threshold": self.threshold,
            "signature_bits": lsh.BITS,
            "hamming_cutoff": self._cutoff,
            "namespaces": namespaces,
            "entries": entries,
        }

    async def probe(
        self, namespace: str, *, query: str, context: str
    ) -> tuple[Vectors, CacheHit | None]:
        """Embed the prompt and return its vectors plus the best admissible hit.

        The vectors are handed back so a miss can be stored without paying for a
        second round of embedding.
        """
        started = time.perf_counter()
        with span("cache.probe", **{"synapse.cache.threshold": self.threshold}) as active:
            vectors = await self._embed_pair(query, context)
            candidates, pruned = await self._candidates(
                namespace, lsh.pair_signatures(vectors)
            )

            best_score = 0.0
            best_text: str | None = None
            for stored, text in candidates:
                score = _pair_similarity(stored, vectors)
                if score > best_score:
                    best_score, best_text = score, text

            latency_ms = int((time.perf_counter() - started) * 1000)
            admitted = best_text is not None and best_score >= self.threshold
            record(
                active,
                **{
                    "synapse.cache.backend": self.backend,
                    "synapse.cache.hit": admitted,
                    "synapse.cache.best_similarity": round(best_score, 4),
                    "synapse.cache.latency_ms": latency_ms,
                    "synapse.cache.candidates": len(candidates),
                    "synapse.cache.pruned": pruned,
                },
            )
            if not admitted:
                return vectors, None
            return vectors, CacheHit(
                text=best_text or "",
                similarity=round(min(best_score, 1.0), 4),
                latency_ms=latency_ms,
                backend=self.backend,
            )

    async def store(
        self,
        namespace: str,
        *,
        query: str,
        context: str,
        text: str,
        vectors: Vectors,
        ttl_s: int,
    ) -> None:
        digest = _digest(f"{query}\x00{context}")
        signatures = lsh.pair_signatures(vectors)
        client = await self._client()
        if client is None:
            self._remember(namespace, digest, ttl_s, vectors, text, signatures)
            return
        try:
            await asyncio.wait_for(
                self._redis_write(client, namespace, digest, vectors, text, signatures, ttl_s),
                REDIS_TIMEOUT_S,
            )
        except Exception as exc:
            self._degrade(exc)
            # Keep the entry rather than lose it with the backend.
            self._remember(namespace, digest, ttl_s, vectors, text, signatures)

    def _remember(
        self,
        namespace: str,
        digest: str,
        ttl_s: int,
        vectors: Vectors,
        text: str,
        signatures: lsh.Signatures,
    ) -> None:
        bucket = self._memory.setdefault(namespace, {})
        bucket[digest] = (time.time() + ttl_s, vectors, text, signatures)

    async def _redis_write(
        self,
        client: Any,
        namespace: str,
        digest: str,
        vectors: Vectors,
        text: str,
        signatures: lsh.Signatures,
        ttl_s: int,
    ) -> None:
        await client.set(
            self._key(namespace, digest),
            json.dumps({"q": vectors[0], "c": vectors[1], "t": text}),
            ex=ttl_s,
        )
        index = self._index_key(namespace)
        await client.hset(index, digest, lsh.encode(signatures))
        # Entries expire on their own TTLs; hash fields cannot. Pushing the
        # index out to the longest TTL on every write means it always outlives
        # what it points at, and a field left behind by an expired entry is
        # dropped the first time a probe finds its entry gone.
        await client.expire(index, REASONING_TTL_S)

    async def _embed_pair(self, query: str, context: str) -> Vectors:
        query_vector, context_vector = await embed_many([query, context or EMPTY_CONTEXT])
        return query_vector, context_vector

    async def _entries(self, namespace: str) -> list[tuple[Vectors, str]]:
        """Every live entry in the namespace, unfiltered."""
        entries, _ = await self._candidates(namespace, None)
        return entries

    async def _candidates(
        self, namespace: str, signatures: lsh.Signatures | None
    ) -> tuple[list[tuple[Vectors, str]], int]:
        """Entries whose signatures could clear the threshold, and how many were
        pruned without an exact check. `signatures=None` prunes nothing."""
        client = await self._client()
        if client is None:
            return self._memory_candidates(namespace, signatures)
        try:
            return await asyncio.wait_for(
                self._redis_candidates(client, namespace, signatures), REDIS_TIMEOUT_S
            )
        except Exception as exc:
            self._degrade(exc)
            return self._memory_candidates(namespace, signatures)

    async def _redis_candidates(
        self, client: Any, namespace: str, signatures: lsh.Signatures | None
    ) -> tuple[list[tuple[Vectors, str]], int]:
        index_key = self._index_key(namespace)
        index = await client.hgetall(index_key)
        if not index:
            # Nothing indexed: entries written before signatures existed, or an
            # empty namespace. Read it the old way, unfiltered.
            return _parse(await self._redis_read(client, namespace)), 0

        survivors = [
            digest
            for digest, encoded in index.items()
            if lsh.may_match(lsh.decode(encoded), signatures, self._cutoff)
        ]
        pruned = len(index) - len(survivors)
        if not survivors:
            return [], pruned
        blobs = await client.mget([self._key(namespace, digest) for digest in survivors])
        expired = [digest for digest, blob in zip(survivors, blobs) if not blob]
        if expired:
            await client.hdel(index_key, *expired)
        return _parse(blobs), pruned

    async def _redis_read(self, client: Any, namespace: str) -> list[str | None]:
        # Unindexed namespaces only. SCAN is O(keyspace), which is why the
        # signature index above is the normal read path.
        keys = [key async for key in client.scan_iter(match=self._key(namespace, "*"))]
        return await client.mget(keys) if keys else []

    def _memory_candidates(
        self, namespace: str, signatures: lsh.Signatures | None
    ) -> tuple[list[tuple[Vectors, str]], int]:
        bucket = self._memory.get(namespace)
        if not bucket:
            return [], 0
        now = time.time()
        for digest in [key for key, (expires, *_) in bucket.items() if expires <= now]:
            del bucket[digest]
        kept = [
            (vectors, text)
            for _, vectors, text, stored in bucket.values()
            if lsh.may_match(stored, signatures, self._cutoff)
        ]
        return kept, len(bucket) - len(kept)

    def _key(self, namespace: str, digest: str) -> str:
        # Namespaces carry '/' and ':' from model names; hash them so they are
        # always safe inside a SCAN glob pattern.
        return f"{KEY_PREFIX}:{_digest(namespace)}:{digest}"

    def _index_key(self, namespace: str) -> str:
        # Under KEY_PREFIX so a prefix purge clears it, but outside the
        # `<prefix>:<namespace>:*` glob so a legacy SCAN never reads it as an entry.
        return f"{KEY_PREFIX}:idx:{_digest(namespace)}"

    async def _client(self) -> Any:
        if self._probed:
            return self._redis
        self._probed = True
        try:
            module = await asyncio.to_thread(importlib.import_module, "redis.asyncio")
            client = module.Redis(
                host=self.settings.redis_host,
                port=self.settings.redis_port,
                decode_responses=True,
                socket_connect_timeout=REDIS_TIMEOUT_S,
                socket_timeout=REDIS_TIMEOUT_S,
            )
            await asyncio.wait_for(client.ping(), REDIS_TIMEOUT_S)
        except Exception as exc:
            logger.info("redis unavailable (%s); semantic cache is in-memory", exc)
            return None
        self._redis = client
        return client

    def _degrade(self, exc: Exception) -> None:
        """Redis dropped mid-run: fall back to memory for the rest of the process."""
        # A bare TimeoutError stringifies to nothing, so name the type too.
        logger.warning(
            "redis semantic cache failed (%s: %s); falling back to memory",
            type(exc).__name__,
            exc,
        )
        self._redis = None


@lru_cache
def get_cache() -> SemanticCache:
    """Process-wide cache. Vectors have to outlive a single run to be of any use."""
    return SemanticCache()

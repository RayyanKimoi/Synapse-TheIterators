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

from ..config import Settings, get_settings
from ..models.ir import NodeType

logger = logging.getLogger(__name__)

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
KEY_PREFIX = "synapse:sc"
FALLBACK_DIMS = 256
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


async def embed(text: str) -> Vector:
    if not _embedder_ready:
        await _load_embedder()
    if _embedder is None:
        return _hash_vector(text)
    # fastembed is synchronous CPU work: off the event loop it goes.
    vectors = await asyncio.to_thread(lambda: list(_embedder.embed([text])))
    return _normalize([float(value) for value in vectors[0]])


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


def _digest(text: str) -> str:
    return hashlib.blake2b(text.encode(), digest_size=8).hexdigest()


class SemanticCache:
    """Per-namespace vector store. One namespace per node, so a cached answer
    can never be served for a different node's question."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.threshold = self.settings.semantic_cache_similarity_threshold
        # namespace -> digest -> (expires_at, vectors, text)
        self._memory: dict[str, dict[str, tuple[float, Vectors, str]]] = {}
        self._redis: Any = None
        self._probed = False

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    async def probe(
        self, namespace: str, *, query: str, context: str
    ) -> tuple[Vectors, CacheHit | None]:
        """Embed the prompt and return its vectors plus the best admissible hit.

        The vectors are handed back so a miss can be stored without paying for a
        second round of embedding.
        """
        started = time.perf_counter()
        vectors = await self._embed_pair(query, context)

        best_score = 0.0
        best_text: str | None = None
        for stored, text in await self._entries(namespace):
            score = _pair_similarity(stored, vectors)
            if score > best_score:
                best_score, best_text = score, text

        if best_text is None or best_score < self.threshold:
            return vectors, None
        return vectors, CacheHit(
            text=best_text,
            similarity=round(min(best_score, 1.0), 4),
            latency_ms=int((time.perf_counter() - started) * 1000),
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
        client = await self._client()
        if client is None:
            bucket = self._memory.setdefault(namespace, {})
            bucket[digest] = (time.time() + ttl_s, vectors, text)
            return
        try:
            await client.set(
                self._key(namespace, digest),
                json.dumps({"q": vectors[0], "c": vectors[1], "t": text}),
                ex=ttl_s,
            )
        except Exception as exc:
            self._degrade(exc)

    async def _embed_pair(self, query: str, context: str) -> Vectors:
        return (await embed(query), await embed(context or EMPTY_CONTEXT))

    async def _entries(self, namespace: str) -> list[tuple[Vectors, str]]:
        client = await self._client()
        if client is None:
            return self._live_memory_entries(namespace)
        try:
            # shortcut: SCAN is O(keyspace); fine for demo-sized runs, swap for
            # a per-namespace index or Redis vector search before real volume.
            keys = [key async for key in client.scan_iter(match=self._key(namespace, "*"))]
            raw = await client.mget(keys) if keys else []
        except Exception as exc:
            self._degrade(exc)
            return self._live_memory_entries(namespace)

        entries: list[tuple[Vectors, str]] = []
        for blob in raw:
            if not blob:
                continue
            try:
                entry = json.loads(blob)
                entries.append(((entry["q"], entry["c"]), entry["t"]))
            except (ValueError, KeyError, TypeError):
                continue  # a foreign key landed under our prefix
        return entries

    def _live_memory_entries(self, namespace: str) -> list[tuple[Vectors, str]]:
        bucket = self._memory.get(namespace)
        if not bucket:
            return []
        now = time.time()
        for digest in [key for key, (expires, _, _) in bucket.items() if expires <= now]:
            del bucket[digest]
        return [(vectors, text) for _, vectors, text in bucket.values()]

    def _key(self, namespace: str, digest: str) -> str:
        # Namespaces carry '/' and ':' from model names; hash them so they are
        # always safe inside a SCAN glob pattern.
        return f"{KEY_PREFIX}:{_digest(namespace)}:{digest}"

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
            )
            await client.ping()
        except Exception as exc:
            logger.info("redis unavailable (%s); semantic cache is in-memory", exc)
            return None
        self._redis = client
        return client

    def _degrade(self, exc: Exception) -> None:
        """Redis dropped mid-run: fall back to memory for the rest of the process."""
        logger.warning("redis semantic cache failed (%s); falling back to memory", exc)
        self._redis = None


@lru_cache
def get_cache() -> SemanticCache:
    """Process-wide cache. Vectors have to outlive a single run to be of any use."""
    return SemanticCache()

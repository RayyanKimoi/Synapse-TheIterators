"""Random-hyperplane LSH (SimHash) signatures for the semantic cache.

Each embedding is reduced to a 256-bit signature: bit b is set when the vector
lies on the positive side of hyperplane b. For hyperplanes drawn from an
isotropic Gaussian, two vectors at angle theta disagree on any one bit with
probability exactly theta / pi (Charikar, 2002), so the Hamming distance between
two signatures is a Binomial(BITS, theta / pi) estimate of the angle between the
vectors -- and comparing two signatures is one XOR and one popcount.

The cache uses this as a *prefilter*, never as the verdict. An entry whose
Hamming distance is too large to be consistent with the admission threshold is
skipped without computing its exact cosine (and, on Redis, without fetching its
vectors at all). Every entry that survives is still admitted on the exact cosine,
so a hit is exactly as trustworthy as it was without the prefilter.

The cut-off is a Z_MARGIN-sigma upper bound on the Hamming distance of a pair
sitting *at* the threshold, so a genuine match is pruned with probability on
the order of 1e-6 per half. A non-match that slips through costs only the exact
check it would have had anyway.
"""

import hashlib
import math
import struct
from collections.abc import Sequence
from functools import lru_cache

try:
    import numpy as _np
except ImportError:  # pragma: no cover - numpy ships with fastembed
    _np = None

BITS = 256
Z_MARGIN = 5.0
# The hyperplanes are floating point, so two platforms can disagree in the last
# ulp and flip a bit whose projection sits within ~1e-16 of zero. Two bits of
# slack absorb that; against a 5-sigma margin of ~30 bits it changes nothing.
ULP_SLACK = 2
SEED = b"synapse/semantic-cache/lsh/v1"

Signature = int
# (query, context), mirroring the cache's vector pair
Signatures = tuple[Signature, Signature]


@lru_cache(maxsize=4)
def _planes(dims: int) -> tuple[float, ...]:
    """BITS x dims Gaussian components, row-major.

    Drawn from SHAKE-256 rather than `random` so every process and every Python
    version derives the same hyperplanes: a signature one worker writes to Redis
    has to be comparable with a probe another worker computes.
    """
    count = BITS * dims  # BITS is even, so Box-Muller pairs come out exact
    stream = hashlib.shake_256(SEED + dims.to_bytes(4, "big")).digest(8 * count)
    words = struct.unpack(f"<{count}Q", stream)
    values: list[float] = []
    for index in range(0, count, 2):
        u1 = 1.0 - (words[index] >> 11) * 2.0**-53  # (0, 1], safe for log
        u2 = (words[index + 1] >> 11) * 2.0**-53
        radius = math.sqrt(-2.0 * math.log(u1))
        values.append(radius * math.cos(2.0 * math.pi * u2))
        values.append(radius * math.sin(2.0 * math.pi * u2))
    return tuple(values)


@lru_cache(maxsize=4)
def _matrix(dims: int):  # noqa: ANN202 - numpy is optional
    return _np.asarray(_planes(dims), dtype=_np.float64).reshape(BITS, dims)


@lru_cache(maxsize=4)
def _columns(dims: int) -> tuple[tuple[float, ...], ...]:
    """Component d of every hyperplane, for the pure-Python path."""
    values = _planes(dims)
    return tuple(values[d::dims] for d in range(dims))


def signature(vector: Sequence[float]) -> Signature:
    """Bit b set when `vector` projects positively onto hyperplane b."""
    dims = len(vector)
    if not dims:
        return 0
    if _np is not None:
        projections = _matrix(dims) @ _np.asarray(vector, dtype=_np.float64)
        packed = _np.packbits(projections > 0.0, bitorder="little")
        return int.from_bytes(packed.tobytes(), "little")
    # Accumulate per non-zero component: the hashed bag-of-words fallback is
    # sparse, so this touches a few dozen columns rather than all of them.
    totals = [0.0] * BITS
    for value, column in zip(vector, _columns(dims)):
        if value:
            totals = [total + value * component for total, component in zip(totals, column)]
    return sum(1 << bit for bit, total in enumerate(totals) if total > 0.0)


def hamming(left: Signature, right: Signature) -> int:
    return (left ^ right).bit_count()


def estimated_cosine(distance: int) -> float:
    """The cosine a Hamming distance implies: theta = pi * distance / BITS."""
    return math.cos(math.pi * distance / BITS)


@lru_cache(maxsize=64)
def max_hamming(threshold: float) -> int:
    """Largest Hamming distance a pair at cosine `threshold` plausibly shows.

    Anything further apart is, to Z_MARGIN sigma, below the threshold.
    """
    cosine = max(-1.0, min(1.0, threshold))
    p = math.acos(cosine) / math.pi
    bound = BITS * p + Z_MARGIN * math.sqrt(BITS * p * (1.0 - p))
    return min(BITS, math.ceil(bound) + ULP_SLACK)


def may_match(stored: Signatures | None, probed: Signatures | None, cutoff: int) -> bool:
    """False only when the pair certainly cannot clear the threshold.

    A missing signature (an entry written before signatures existed) is never
    pruned: it falls through to the exact check.
    """
    if stored is None or probed is None:
        return True
    return hamming(stored[0], probed[0]) <= cutoff and hamming(stored[1], probed[1]) <= cutoff


def pair_signatures(vectors: tuple[Sequence[float], Sequence[float]]) -> Signatures:
    return signature(vectors[0]), signature(vectors[1])


def encode(signatures: Signatures) -> str:
    """`<query hex>:<context hex>`, fixed width, for the Redis index."""
    width = BITS // 4
    return f"{signatures[0]:0{width}x}:{signatures[1]:0{width}x}"


def decode(encoded: str) -> Signatures | None:
    try:
        query, context = encoded.split(":")
        return int(query, 16), int(context, 16)
    except (ValueError, AttributeError):
        return None  # unreadable: keep the entry, let the exact check decide

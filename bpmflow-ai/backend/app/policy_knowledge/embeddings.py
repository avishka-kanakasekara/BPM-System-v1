"""Deterministic text embeddings for policy chunk vector search.

Uses a lightweight bag-of-words hash embedding suitable for offline tests and
pgvector-compatible cosine similarity in production retrieval.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence

_DIM = 128
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def embed_text(text: str, *, dimensions: int = _DIM) -> list[float]:
    """Hash-trick embedding — deterministic, no external model required."""
    vector = [0.0] * dimensions
    tokens = _tokenize(text)
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[idx] += sign
    norm = math.sqrt(sum(v * v for v in vector))
    if norm <= 0:
        return vector
    return [v / norm for v in vector]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))

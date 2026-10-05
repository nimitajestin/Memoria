"""Deterministic bag-of-words embedder for tests and the vector-search gate."""

from __future__ import annotations

import hashlib
import re

import numpy as np

TOKEN = re.compile(r"[a-z0-9_]+")


class HashEmbedder:
    model = "hash-bow-32"

    def __init__(self, dimension: int = 32) -> None:
        if dimension < 8:
            raise ValueError("dimension must be at least 8")
        self.dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_vector(text, self.dimension) for text in texts]


def _vector(text: str, dimension: int) -> list[float]:
    counts = np.zeros(dimension, dtype=np.float32)
    for token in TOKEN.findall(text.casefold()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "little") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        counts[index] += sign
    norm = float(np.linalg.norm(counts))
    if norm == 0.0:
        counts[0] = 1.0
        return counts.tolist()
    return (counts / norm).tolist()

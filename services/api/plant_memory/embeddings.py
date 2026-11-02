"""Embeddings: BAAI/bge-small-en-v1.5 via fastembed (CPU), or a deterministic hash embedder
for tests and CI. Both produce 384-dimensional unit vectors so the schema is identical."""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

from .config import get_settings

MAX_INPUT_TOKENS = 512  # bge-small input limit; chunker stays well under it.


class Embedder:
    name: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class HashEmbedder(Embedder):
    """Deterministic bag-of-ngrams projection. Not semantic; used so the pipeline and SQL run
    without model downloads. Marked in evidence_chunks.embedding_model."""

    name = "hash-384"
    dim = 384

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            vec = [0.0] * self.dim
            tokens = re.findall(r"[a-z0-9][a-z0-9\-]*", t.lower())
            grams = tokens + [a + "_" + b for a, b in zip(tokens, tokens[1:])]
            for g in grams:
                h = int(hashlib.blake2b(g.encode(), digest_size=8).hexdigest(), 16)
                vec[h % self.dim] += 1.0 if (h >> 1) % 2 else -1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class FastEmbedEmbedder(Embedder):
    dim = 384

    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding

        self.name = model_name
        self.model = TextEmbedding(model_name=model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self.model.embed(texts, batch_size=32)]


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    if s.embedding_backend == "hash":
        return HashEmbedder()
    try:
        return FastEmbedEmbedder(s.embedding_model)
    except Exception:  # model unavailable offline — degrade visibly, never silently
        emb = HashEmbedder()
        emb.name = "hash-384 (fastembed unavailable)"
        return emb

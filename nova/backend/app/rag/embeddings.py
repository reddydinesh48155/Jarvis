"""Local embedding providers used by the RAG pipeline.

Ollama is the production provider. The deterministic hashing provider is a
small, dependency-free fallback for offline development and tests; it is
lexical rather than semantic and should not replace a real embedding model
for production deployments.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("nova.rag.embeddings")

TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_'-]{1,}", re.IGNORECASE)
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "i",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "was", "what",
    "when", "where", "which", "who", "with", "you", "your",
}


class EmbeddingProvider(ABC):
    """Async interface implemented by local/free embedding providers."""

    dimension: int

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one fixed-dimension vector for every input text."""

    async def embed_one(self, text: str) -> list[float]:
        vectors = await self.embed([text])
        if len(vectors) != 1:
            raise RuntimeError("embedding provider returned an unexpected number of vectors")
        return vectors[0]

    def _validate(self, vectors: list[list[float]], expected_count: int) -> list[list[float]]:
        if len(vectors) != expected_count:
            raise RuntimeError(
                f"embedding provider returned {len(vectors)} vectors for {expected_count} texts"
            )
        for vector in vectors:
            if len(vector) != self.dimension:
                raise RuntimeError(
                    f"embedding dimension mismatch: expected {self.dimension}, got {len(vector)}"
                )
        return vectors


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Call a local Ollama embedding model over its HTTP API."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.rag_embedding_model
        self.dimension = dimension or settings.rag_embedding_dimension
        self.timeout = timeout or settings.rag_embedding_timeout_seconds

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": self.model, "input": texts},
                )
                response.raise_for_status()
                payload = response.json()
                raw_vectors = payload.get("embeddings")
                if raw_vectors is None and isinstance(payload.get("embedding"), list):
                    raw_vectors = [payload["embedding"]]
                if not isinstance(raw_vectors, list):
                    raise RuntimeError("Ollama /api/embed response did not contain embeddings")
                vectors = [[float(value) for value in vector] for vector in raw_vectors]
                return self._validate(vectors, len(texts))
            except httpx.HTTPStatusError as first_error:
                # Older Ollama versions expose only the single-input endpoint.
                if first_error.response.status_code not in {400, 404, 405}:
                    raise
                vectors = []
                for text in texts:
                    response = await client.post(
                        f"{self.base_url}/api/embeddings",
                        json={"model": self.model, "prompt": text},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    vector = payload.get("embedding")
                    if not isinstance(vector, list):
                        raise RuntimeError("Ollama /api/embeddings response did not contain an embedding")
                    vectors.append([float(value) for value in vector])
                return self._validate(vectors, len(texts))
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                raise RuntimeError(
                    f"Cannot reach local Ollama embeddings at {self.base_url} ({self.model})"
                ) from exc


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic lexical vectors for offline operation and test isolation."""

    def __init__(self, dimension: int | None = None) -> None:
        self.dimension = dimension or settings.rag_embedding_dimension

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return [token.lower() for token in TOKEN_PATTERN.findall(text) if token.lower() not in STOP_WORDS]

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in set(self._tokens(text)):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimension
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return self._validate([self._vector(text) for text in texts], len(texts))


class FallbackEmbeddingProvider(EmbeddingProvider):
    """Use Ollama when available and keep local development usable when it is not."""

    def __init__(self, primary: EmbeddingProvider, fallback: EmbeddingProvider) -> None:
        if primary.dimension != fallback.dimension:
            raise ValueError("primary and fallback embedding dimensions must match")
        self.primary = primary
        self.fallback = fallback
        self.dimension = primary.dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            return await self.primary.embed(texts)
        except Exception as exc:
            logger.warning("local embedding provider unavailable; using lexical fallback: %s", exc)
            return await self.fallback.embed(texts)


@lru_cache(maxsize=1)
def get_default_embedding_provider() -> EmbeddingProvider:
    """Build the configured local provider once per process."""
    fallback = HashEmbeddingProvider()
    if settings.rag_embedding_provider.lower() == "hash":
        return fallback
    return FallbackEmbeddingProvider(OllamaEmbeddingProvider(), fallback)

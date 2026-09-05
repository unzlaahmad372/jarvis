"""Embedding provider abstraction.

The rest of JARVIS depends on EmbeddingProvider, never on Ollama directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    dimension: int


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def dimension(self) -> int | None:
        """Embedding dimension, or None if not yet known."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> EmbeddingResult: ...

    @abstractmethod
    async def health_check(self) -> bool: ...


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Embeddings via Ollama /api/embed endpoint."""

    def __init__(self, base_url: str, model: str) -> None:
        import httpx

        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=60.0)
        self._dimension: int | None = None

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int | None:
        return self._dimension

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=[], model=self._model, dimension=self._dimension or 0)
        response = await self._client.post(
            "/api/embed",
            json={"model": self._model, "input": texts},
        )
        response.raise_for_status()
        data = response.json()
        vectors: list[list[float]] = data["embeddings"]
        dim = len(vectors[0]) if vectors else 0
        self._dimension = dim
        return EmbeddingResult(vectors=vectors, model=self._model, dimension=dim)

    async def health_check(self) -> bool:
        try:
            result = await self.embed(["health check"])
            return len(result.vectors) > 0
        except Exception:
            return False

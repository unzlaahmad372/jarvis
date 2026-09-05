"""Fake embedding provider and vector store for deterministic unit tests.

Never requires Ollama or Chroma.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.knowledge.embeddings import EmbeddingProvider, EmbeddingResult
from app.knowledge.vector_store import IndexHealth, VectorSearchResult, VectorStore


class FakeEmbeddingProvider(EmbeddingProvider):
    """Returns deterministic unit vectors based on text hash."""

    def __init__(self, dim: int = 4, fail: bool = False) -> None:
        self._dim = dim
        self._fail = fail
        self.call_count = 0

    @property
    def model_name(self) -> str:
        return "fake-embed"

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if self._fail:
            raise ConnectionError("Fake embedding failure")
        self.call_count += 1
        vectors = [self._text_to_vector(t) for t in texts]
        return EmbeddingResult(vectors=vectors, model=self.model_name, dimension=self._dim)

    def _text_to_vector(self, text: str) -> list[float]:
        """Deterministic unit vector derived from text hash."""
        seed = hash(text) % (2**31)
        raw = [(seed * (i + 1) * 6364136223846793005) % (2**31) for i in range(self._dim)]
        magnitude = math.sqrt(sum(x**2 for x in raw)) or 1.0
        return [x / magnitude for x in raw]

    async def health_check(self) -> bool:
        return not self._fail


@dataclass
class _StoredChunk:
    vector_id: str
    vector: list[float]
    document_id: int
    chunk_index: int
    content: str
    filename: str
    page: int | None
    section: str | None


class FakeVectorStore(VectorStore):
    """In-memory vector store for tests."""

    def __init__(self, fail: bool = False) -> None:
        self._chunks: list[_StoredChunk] = []
        self._fail = fail

    async def upsert(
        self,
        vector_id: str,
        vector: list[float],
        document_id: int,
        chunk_index: int,
        content: str,
        filename: str,
        page: int | None = None,
        section: str | None = None,
    ) -> None:
        if self._fail:
            raise RuntimeError("Fake vector store failure")
        # Remove existing entry with same vector_id
        self._chunks = [c for c in self._chunks if c.vector_id != vector_id]
        self._chunks.append(
            _StoredChunk(
                vector_id=vector_id,
                vector=vector,
                document_id=document_id,
                chunk_index=chunk_index,
                content=content,
                filename=filename,
                page=page,
                section=section,
            )
        )

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 6,
        score_threshold: float = 0.0,
    ) -> list[VectorSearchResult]:
        if self._fail:
            raise RuntimeError("Fake vector store failure")
        if not self._chunks:
            return []

        def _dot(a: list[float], b: list[float]) -> float:
            return sum(x * y for x, y in zip(a, b, strict=True))

        scored = [
            (c, _dot(query_vector, c.vector))
            for c in self._chunks
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        return [
            VectorSearchResult(
                vector_id=c.vector_id,
                document_id=c.document_id,
                chunk_index=c.chunk_index,
                content=c.content,
                score=score,
                filename=c.filename,
                page=c.page,
                section=c.section,
            )
            for c, score in scored[:top_k]
            if score >= score_threshold
        ]

    async def delete_document(self, document_id: int) -> int:
        before = len(self._chunks)
        self._chunks = [c for c in self._chunks if c.document_id != document_id]
        return before - len(self._chunks)

    async def health(self) -> IndexHealth:
        return IndexHealth(
            status="HEALTHY" if not self._fail else "UNAVAILABLE",
            collection="fake",
            document_count=len(self._chunks),
            embedding_model="fake-embed",
            index_version="1",
        )

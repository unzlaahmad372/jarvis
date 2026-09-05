"""Vector store abstraction and Chroma implementation.

The rest of JARVIS depends on VectorStore, never on Chroma directly.
Chroma types never leak outside this module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VectorSearchResult:
    vector_id: str
    document_id: int
    chunk_index: int
    content: str
    score: float
    filename: str
    page: int | None = None
    section: str | None = None


@dataclass
class IndexHealth:
    status: str          # HEALTHY | EMPTY | REINDEX_REQUIRED | UNAVAILABLE
    collection: str
    document_count: int
    embedding_model: str
    index_version: str
    detail: str | None = None


class VectorStore(ABC):
    @abstractmethod
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
    ) -> None: ...

    @abstractmethod
    async def search(
        self,
        query_vector: list[float],
        top_k: int = 6,
        score_threshold: float = 0.0,
    ) -> list[VectorSearchResult]: ...

    @abstractmethod
    async def delete_document(self, document_id: int) -> int:
        """Delete all chunks for a document. Returns count deleted."""

    @abstractmethod
    async def health(self) -> IndexHealth: ...


COLLECTION_NAME = "jarvis_knowledge"


class ChromaVectorStore(VectorStore):
    """Persistent local Chroma vector store.

    Chroma types are confined to this class — nothing outside imports chromadb.
    """

    def __init__(
        self,
        persist_dir: Path,
        embedding_model: str,
        index_version: str,
    ) -> None:
        import chromadb

        self._embedding_model = embedding_model
        self._index_version = index_version
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={
                "embedding_model": embedding_model,
                "index_version": index_version,
            },
        )

    def _check_compatibility(self) -> bool:
        """Return True if the stored collection matches current config."""
        meta = self._collection.metadata or {}
        return (
            meta.get("embedding_model") == self._embedding_model
            and meta.get("index_version") == self._index_version
        )

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
        metadata: dict[str, str | int] = {
            "document_id": document_id,
            "chunk_index": chunk_index,
            "filename": filename,
        }
        if page is not None:
            metadata["page"] = page
        if section is not None:
            metadata["section"] = section

        self._collection.upsert(
            ids=[vector_id],
            embeddings=[vector],  # type: ignore[arg-type]
            documents=[content],
            metadatas=[metadata],
        )

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 6,
        score_threshold: float = 0.0,
    ) -> list[VectorSearchResult]:
        if self._collection.count() == 0:
            return []

        results = self._collection.query(
            query_embeddings=[query_vector],  # type: ignore[arg-type]
            n_results=min(top_k, self._collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        out: list[VectorSearchResult] = []
        ids = (results.get("ids") or [[]])[0]
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]

        for vid, doc, meta, dist in zip(ids, docs, metas, distances, strict=True):
            # Chroma returns L2 distance; convert to a 0-1 similarity score
            score = 1.0 / (1.0 + dist)
            if score < score_threshold:
                continue
            out.append(
                VectorSearchResult(
                    vector_id=str(vid),
                    document_id=int(meta.get("document_id") or 0),  # type: ignore[arg-type]
                    chunk_index=int(meta.get("chunk_index") or 0),  # type: ignore[arg-type]
                    content=str(doc),
                    score=score,
                    filename=str(meta.get("filename", "")),
                    page=int(meta["page"]) if "page" in meta else None,  # type: ignore[arg-type]
                    section=str(meta["section"]) if "section" in meta else None,
                )
            )

        return sorted(out, key=lambda r: r.score, reverse=True)

    async def delete_document(self, document_id: int) -> int:
        results = self._collection.get(
            where={"document_id": document_id},
            include=[],
        )
        ids: list[str] = results.get("ids", [])
        if ids:
            self._collection.delete(ids=ids)
        return len(ids)

    async def health(self) -> IndexHealth:
        try:
            count = self._collection.count()
            compatible = self._check_compatibility()
            status = "HEALTHY" if compatible else "REINDEX_REQUIRED"
            if count == 0 and compatible:
                status = "EMPTY"
            return IndexHealth(
                status=status,
                collection=COLLECTION_NAME,
                document_count=count,
                embedding_model=self._embedding_model,
                index_version=self._index_version,
                detail=None if compatible else "Embedding model or index version mismatch",
            )
        except Exception as exc:
            return IndexHealth(
                status="UNAVAILABLE",
                collection=COLLECTION_NAME,
                document_count=0,
                embedding_model=self._embedding_model,
                index_version=self._index_version,
                detail=str(exc),
            )

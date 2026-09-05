"""Document ingestion pipeline.

State machine: DISCOVERED → PARSING → CHUNKING → EMBEDDING → INDEXING → INDEXED
                                                                        → FAILED

This is the single canonical ingestion path used by both the API endpoint
and the future inbox watcher.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Document, DocumentChunk, Workspace
from app.knowledge.chunker import chunk_pages
from app.knowledge.embeddings import EmbeddingProvider
from app.knowledge.parser import SUPPORTED_EXTENSIONS, parse_document
from app.knowledge.vector_store import VectorStore

logger = get_logger(__name__)

INDEX_VERSION = "1"


def compute_file_hash(path: Path) -> str:
    """SHA-256 hash of file contents."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


async def _get_default_workspace_id(session: AsyncSession) -> int:
    result = await session.execute(
        select(Workspace.id).where(Workspace.is_default == True)  # noqa: E712
    )
    ws_id = result.scalar_one_or_none()
    if ws_id is None:
        raise RuntimeError("No default workspace found")
    return ws_id


async def ingest_document(
    path: Path,
    session: AsyncSession,
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStore,
    chunk_size_tokens: int = 512,
    overlap_tokens: int = 64,
    workspace_id: int | None = None,
) -> Document:
    """Ingest a single document into the knowledge base.

    Returns the Document ORM object (status=INDEXED on success, FAILED on error).
    Idempotent: if the file hash already exists and is INDEXED, returns existing record.
    """
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {suffix!r}")

    file_hash = compute_file_hash(path)
    ws_id = workspace_id or await _get_default_workspace_id(session)

    # ── Duplicate detection ───────────────────────────────────────────────────
    existing = await session.execute(
        select(Document).where(
            Document.file_hash == file_hash,
            Document.workspace_id == ws_id,
            Document.status == "INDEXED",
        )
    )
    doc = existing.scalar_one_or_none()
    if doc is not None:
        logger.info("document_already_indexed", filename=path.name, doc_id=doc.id)
        return doc

    # ── Create document record ────────────────────────────────────────────────
    doc = Document(
        workspace_id=ws_id,
        filename=path.name,
        file_path=str(path.resolve()),
        file_type=suffix.lstrip("."),
        file_hash=file_hash,
        file_size_bytes=path.stat().st_size,
        status="DISCOVERED",
        embedding_model=embedding_provider.model_name,
        index_version=INDEX_VERSION,
    )
    session.add(doc)
    await session.flush()

    try:
        # ── Parse ─────────────────────────────────────────────────────────────
        doc.status = "PARSING"
        await session.flush()
        pages = parse_document(path)

        # ── Chunk ─────────────────────────────────────────────────────────────
        doc.status = "CHUNKING"
        await session.flush()
        chunks = chunk_pages(
            pages, chunk_size_tokens=chunk_size_tokens, overlap_tokens=overlap_tokens
        )

        if not chunks:
            doc.status = "FAILED"
            doc.error_message = "No text content extracted"
            await session.commit()
            return doc

        # ── Embed ─────────────────────────────────────────────────────────────
        doc.status = "EMBEDDING"
        await session.flush()
        texts = [c.content for c in chunks]
        embedding_result = await embedding_provider.embed(texts)

        doc.embedding_dimension = embedding_result.dimension

        # ── Index + persist chunks ────────────────────────────────────────────
        doc.status = "INDEXING"
        await session.flush()

        for chunk, vector in zip(chunks, embedding_result.vectors, strict=True):
            vector_id = str(uuid.uuid4())
            await vector_store.upsert(
                vector_id=vector_id,
                vector=vector,
                document_id=doc.id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                filename=path.name,
                page=chunk.page,
                section=chunk.section if hasattr(chunk, "section") else None,
            )
            db_chunk = DocumentChunk(
                document_id=doc.id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                page=chunk.page,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                token_count=chunk.token_count,
                vector_id=vector_id,
                embedding_model=embedding_provider.model_name,
            )
            session.add(db_chunk)

        doc.chunk_count = len(chunks)
        doc.status = "INDEXED"
        await session.commit()

        logger.info(
            "document_indexed",
            doc_id=doc.id,
            filename=path.name,
            chunks=len(chunks),
            embedding_model=embedding_provider.model_name,
        )

    except Exception as exc:
        doc.status = "FAILED"
        doc.error_message = str(exc)[:500]
        await session.commit()
        logger.exception("document_ingestion_failed", filename=path.name, error=str(exc))

    return doc

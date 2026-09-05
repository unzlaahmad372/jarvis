"""Documents API — ingest, list, delete knowledge base documents."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import DbSession, SettingsDep
from app.api.schemas.chat import DocumentOut
from app.core.config import Settings
from app.db.models import Document
from app.knowledge.embeddings import OllamaEmbeddingProvider
from app.knowledge.ingestion import ingest_document
from app.knowledge.vector_store import ChromaVectorStore

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


def _get_rag_components(s: Settings) -> tuple[OllamaEmbeddingProvider, ChromaVectorStore]:
    embedding = OllamaEmbeddingProvider(base_url=s.ollama_url, model=s.embedding_model)
    vector_store = ChromaVectorStore(
        persist_dir=s.indexes_dir,
        embedding_model=s.embedding_model,
        index_version=s.index_version,
    )
    return embedding, vector_store


@router.post("/ingest", summary="Ingest a document into the knowledge base")
async def ingest(
    file: UploadFile,
    session: DbSession,
    settings: SettingsDep,
) -> DocumentOut:
    """Upload and ingest a document (TXT, Markdown, PDF, DOCX)."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No filename provided"
        )

    suffix = Path(file.filename).suffix.lower()
    allowed = {".txt", ".md", ".pdf", ".docx"}
    if suffix not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type {suffix!r}. Allowed: {sorted(allowed)}",
        )

    embedding, vector_store = _get_rag_components(settings)

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        doc = await ingest_document(
            path=tmp_path,
            session=session,
            embedding_provider=embedding,
            vector_store=vector_store,
            chunk_size_tokens=settings.chunk_size,
            overlap_tokens=settings.chunk_overlap,
        )
        doc.filename = file.filename
        await session.commit()
    finally:
        tmp_path.unlink(missing_ok=True)

    return DocumentOut.model_validate(doc)


@router.get("", summary="List all documents")
async def list_documents(session: DbSession) -> list[DocumentOut]:
    result = await session.execute(
        select(Document).order_by(Document.created_at.desc())
    )
    return [DocumentOut.model_validate(d) for d in result.scalars().all()]


@router.delete("/{document_id}", summary="Delete a document and its index entries")
async def delete_document(
    document_id: int,
    session: DbSession,
    settings: SettingsDep,
) -> dict[str, object]:
    result = await session.execute(
        select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    _, vector_store = _get_rag_components(settings)
    deleted_vectors = await vector_store.delete_document(document_id)

    await session.delete(doc)
    await session.commit()

    return {"deleted": True, "document_id": document_id, "vectors_removed": deleted_vectors}

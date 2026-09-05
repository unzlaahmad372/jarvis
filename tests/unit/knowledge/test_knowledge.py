"""Unit tests for Phase 2 knowledge components."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.knowledge.chunker import chunk_pages
from app.knowledge.ingestion import compute_file_hash, ingest_document
from app.knowledge.parser import ParsedPage, parse_document
from app.knowledge.retrieval import retrieve
from tests.fakes.knowledge import FakeEmbeddingProvider, FakeVectorStore

# ── Parser ────────────────────────────────────────────────────────────────────


class TestParser:
    def test_parse_txt(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("Hello world\nSecond line", encoding="utf-8")
        pages = parse_document(f)
        assert len(pages) == 1
        assert "Hello world" in pages[0].text

    def test_parse_md(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("# Title\n\nSome content here.", encoding="utf-8")
        pages = parse_document(f)
        assert len(pages) == 1
        assert "Title" in pages[0].text

    def test_unsupported_extension_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "test.xyz"
        f.write_text("data")
        with pytest.raises(ValueError, match="Unsupported file type"):
            parse_document(f)

    def test_empty_txt_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.txt"
        f.write_text("   ", encoding="utf-8")
        pages = parse_document(f)
        assert pages == []

    def test_page_is_none_for_txt(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("content", encoding="utf-8")
        pages = parse_document(f)
        assert pages[0].page is None


# ── Chunker ───────────────────────────────────────────────────────────────────


class TestChunker:
    def test_short_text_single_chunk(self) -> None:
        pages = [ParsedPage(text="Short text.", page=None)]
        chunks = chunk_pages(pages, chunk_size_tokens=512, overlap_tokens=64)
        assert len(chunks) == 1
        assert chunks[0].content == "Short text."

    def test_long_text_multiple_chunks(self) -> None:
        long_text = "word " * 1000
        pages = [ParsedPage(text=long_text, page=None)]
        chunks = chunk_pages(pages, chunk_size_tokens=50, overlap_tokens=10)
        assert len(chunks) > 1

    def test_chunk_indices_sequential(self) -> None:
        pages = [ParsedPage(text="word " * 500, page=None)]
        chunks = chunk_pages(pages, chunk_size_tokens=50, overlap_tokens=10)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_page_metadata_preserved(self) -> None:
        pages = [ParsedPage(text="content here", page=3)]
        chunks = chunk_pages(pages, chunk_size_tokens=512)
        assert chunks[0].page == 3

    def test_empty_pages_returns_empty(self) -> None:
        assert chunk_pages([], chunk_size_tokens=512) == []

    def test_token_count_populated(self) -> None:
        pages = [ParsedPage(text="hello world", page=None)]
        chunks = chunk_pages(pages)
        assert chunks[0].token_count > 0

    def test_overlap_creates_shared_content(self) -> None:
        # With overlap, adjacent chunks should share some characters
        text = "a" * 2000
        pages = [ParsedPage(text=text, page=None)]
        chunks = chunk_pages(pages, chunk_size_tokens=100, overlap_tokens=50)
        if len(chunks) > 1:
            # End of chunk 0 should overlap with start of chunk 1
            assert chunks[0].char_end > chunks[1].char_start


# ── File hash ─────────────────────────────────────────────────────────────────


class TestComputeFileHash:
    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"hello")
        f2.write_bytes(b"hello")
        assert compute_file_hash(f1) == compute_file_hash(f2)

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"hello")
        f2.write_bytes(b"world")
        assert compute_file_hash(f1) != compute_file_hash(f2)

    def test_hash_is_64_chars(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_bytes(b"data")
        assert len(compute_file_hash(f)) == 64


# ── Fake embedding provider ───────────────────────────────────────────────────


class TestFakeEmbeddingProvider:
    async def test_returns_vectors(self) -> None:
        provider = FakeEmbeddingProvider(dim=4)
        result = await provider.embed(["hello", "world"])
        assert len(result.vectors) == 2
        assert all(len(v) == 4 for v in result.vectors)

    async def test_deterministic(self) -> None:
        provider = FakeEmbeddingProvider(dim=4)
        r1 = await provider.embed(["test"])
        r2 = await provider.embed(["test"])
        assert r1.vectors == r2.vectors

    async def test_empty_input(self) -> None:
        provider = FakeEmbeddingProvider(dim=4)
        result = await provider.embed([])
        assert result.vectors == []

    async def test_fail_mode(self) -> None:
        provider = FakeEmbeddingProvider(fail=True)
        with pytest.raises(ConnectionError):
            await provider.embed(["text"])

    async def test_health_check_ok(self) -> None:
        assert await FakeEmbeddingProvider().health_check() is True

    async def test_health_check_fail(self) -> None:
        assert await FakeEmbeddingProvider(fail=True).health_check() is False


# ── Fake vector store ─────────────────────────────────────────────────────────


class TestFakeVectorStore:
    async def test_upsert_and_search(self) -> None:
        store = FakeVectorStore()
        await store.upsert("v1", [1.0, 0.0], 1, 0, "hello", "doc.txt")
        results = await store.search([1.0, 0.0], top_k=5)
        assert len(results) == 1
        assert results[0].content == "hello"

    async def test_search_empty_store(self) -> None:
        store = FakeVectorStore()
        results = await store.search([1.0, 0.0])
        assert results == []

    async def test_delete_document(self) -> None:
        store = FakeVectorStore()
        await store.upsert("v1", [1.0, 0.0], 1, 0, "chunk1", "doc.txt")
        await store.upsert("v2", [0.0, 1.0], 1, 1, "chunk2", "doc.txt")
        await store.upsert("v3", [0.5, 0.5], 2, 0, "other", "other.txt")
        deleted = await store.delete_document(1)
        assert deleted == 2
        results = await store.search([1.0, 0.0], top_k=10)
        assert all(r.document_id == 2 for r in results)

    async def test_fail_mode_search(self) -> None:
        store = FakeVectorStore(fail=True)
        with pytest.raises(RuntimeError):
            await store.search([1.0, 0.0])

    async def test_health_healthy(self) -> None:
        h = await FakeVectorStore().health()
        assert h.status == "HEALTHY"

    async def test_health_unavailable(self) -> None:
        h = await FakeVectorStore(fail=True).health()
        assert h.status == "UNAVAILABLE"


# ── Ingestion pipeline ────────────────────────────────────────────────────────


class TestIngestionPipeline:
    async def test_ingest_txt_success(
        self, db_session: object, tmp_path: Path
    ) -> None:
        from sqlalchemy.ext.asyncio import AsyncSession

        session: AsyncSession = db_session  # type: ignore[assignment]

        # Seed workspace
        from app.db.models import Workspace
        ws = Workspace(name="default", is_default=True)
        session.add(ws)
        await session.commit()

        f = tmp_path / "test.txt"
        f.write_text("This is a test document with enough content to be useful.", encoding="utf-8")

        embedding = FakeEmbeddingProvider(dim=4)
        vector_store = FakeVectorStore()

        doc = await ingest_document(
            path=f,
            session=session,
            embedding_provider=embedding,
            vector_store=vector_store,
        )

        assert doc.status == "INDEXED"
        assert doc.chunk_count >= 1
        assert doc.file_hash is not None
        assert embedding.call_count == 1

    async def test_ingest_duplicate_returns_existing(
        self, db_session: object, tmp_path: Path
    ) -> None:
        from sqlalchemy.ext.asyncio import AsyncSession

        session: AsyncSession = db_session  # type: ignore[assignment]

        from app.db.models import Workspace
        ws = Workspace(name="default", is_default=True)
        session.add(ws)
        await session.commit()

        f = tmp_path / "dup.txt"
        f.write_text("Duplicate content", encoding="utf-8")

        embedding = FakeEmbeddingProvider(dim=4)
        vector_store = FakeVectorStore()

        doc1 = await ingest_document(f, session, embedding, vector_store)
        doc2 = await ingest_document(f, session, embedding, vector_store)

        assert doc1.id == doc2.id
        assert embedding.call_count == 1  # only embedded once

    async def test_ingest_unsupported_type_raises(
        self, db_session: object, tmp_path: Path
    ) -> None:
        from sqlalchemy.ext.asyncio import AsyncSession

        session: AsyncSession = db_session  # type: ignore[assignment]

        f = tmp_path / "bad.xyz"
        f.write_text("data")

        with pytest.raises(ValueError, match="Unsupported"):
            await ingest_document(f, session, FakeEmbeddingProvider(), FakeVectorStore())

    async def test_embedding_failure_marks_failed(
        self, db_session: object, tmp_path: Path
    ) -> None:
        from sqlalchemy.ext.asyncio import AsyncSession

        session: AsyncSession = db_session  # type: ignore[assignment]

        from app.db.models import Workspace
        ws = Workspace(name="default", is_default=True)
        session.add(ws)
        await session.commit()

        f = tmp_path / "fail.txt"
        f.write_text("Some content here.", encoding="utf-8")

        doc = await ingest_document(
            f, session, FakeEmbeddingProvider(fail=True), FakeVectorStore()
        )
        assert doc.status == "FAILED"


# ── Retrieval ─────────────────────────────────────────────────────────────────


class TestRetrieval:
    async def test_retrieval_returns_results(self) -> None:
        embedding = FakeEmbeddingProvider(dim=4)
        store = FakeVectorStore()
        await store.upsert("v1", [1.0, 0.0, 0.0, 0.0], 1, 0, "JARVIS knowledge", "doc.txt")

        result = await retrieve(
            query="JARVIS",
            embedding_provider=embedding,
            vector_store=store,
            top_k=5,
        )
        assert len(result.chunks) >= 1
        assert result.context_slot is not None
        assert len(result.citations) >= 1

    async def test_retrieval_empty_store(self) -> None:
        result = await retrieve(
            query="anything",
            embedding_provider=FakeEmbeddingProvider(dim=4),
            vector_store=FakeVectorStore(),
        )
        assert result.chunks == []
        assert result.context_slot is None

    async def test_retrieval_embed_failure_returns_empty(self) -> None:
        result = await retrieve(
            query="test",
            embedding_provider=FakeEmbeddingProvider(fail=True),
            vector_store=FakeVectorStore(),
        )
        assert result.chunks == []
        assert result.context_slot is None

    async def test_rag_context_slot_priority(self) -> None:
        embedding = FakeEmbeddingProvider(dim=4)
        store = FakeVectorStore()
        await store.upsert("v1", [1.0, 0.0, 0.0, 0.0], 1, 0, "content", "f.txt")
        result = await retrieve("query", embedding, store)
        assert result.context_slot is not None
        assert result.context_slot.priority == 4  # spec §35

    async def test_rag_context_contains_untrusted_label(self) -> None:
        embedding = FakeEmbeddingProvider(dim=4)
        store = FakeVectorStore()
        await store.upsert("v1", [1.0, 0.0, 0.0, 0.0], 1, 0, "secret content", "f.txt")
        result = await retrieve("query", embedding, store)
        assert result.context_slot is not None
        assert "treat as data" in result.context_slot.content.lower()

    async def test_token_budget_limits_chunks(self) -> None:
        embedding = FakeEmbeddingProvider(dim=4)
        store = FakeVectorStore()
        # Add many chunks
        for i in range(20):
            await store.upsert(f"v{i}", [1.0, 0.0, 0.0, 0.0], 1, i, "word " * 100, "f.txt")
        result = await retrieve("query", embedding, store, rag_token_budget=200)
        # Should be limited by budget
        assert len(result.chunks) < 20

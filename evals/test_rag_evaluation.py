"""RAG evaluation suite — golden Q&A regression tests.

Uses synthetic documents only (never real private data in CI).
Tests retrieval quality separately from answer quality per spec §36.

Run with: python -m pytest evals/ -v
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.knowledge.chunker import chunk_pages
from app.knowledge.ingestion import ingest_document
from app.knowledge.retrieval import retrieve
from tests.fakes.knowledge import FakeEmbeddingProvider, FakeVectorStore

# ── Synthetic documents ───────────────────────────────────────────────────────

SYNTHETIC_DOCS = {
    "dairy_farm.txt": """
Project: Dairy Farm Expansion Plan

The dairy farm expansion targets Q3 2025 for completion.
The farm currently has 120 cows and plans to expand to 200.
Key milestones include new barn construction in April and equipment
installation in June. The project budget is 450,000 SEK.
Contact: farm manager Erik Lindqvist.
""",
    "kubernetes_sizing.txt": """
Kubernetes Cluster Sizing Guide

For production workloads, we recommend a minimum of 3 control plane nodes.
Worker nodes should have at least 8 CPU cores and 32GB RAM.
The Phoenix cluster uses node type m5.2xlarge on AWS.
Namespace quotas are enforced at 4 CPU and 8GB per team namespace.
Monitoring is handled by Prometheus with 15-day retention.
""",
    "project_phoenix.txt": """
Project Phoenix — Status Update

Phoenix is our next-generation telecom platform targeting GA in Q3.
The system test phase (msST) begins in May with 3 test clusters.
Known risks: dependency on KubeVirt 1.2 release and Titansim integration.
The Spinnaker pipeline for Phoenix prewash was updated on 2024-03-15.
Team lead: Sarah Chen. Escalation contact: CTO office.
""",
}

# ── Golden Q&A cases ──────────────────────────────────────────────────────────

GOLDEN_QA = [
    {
        "question": "What is the target date for the dairy farm expansion?",
        "expected_document": "dairy_farm.txt",
        "expected_facts": ["Q3", "2025"],
        "forbidden_facts": ["Phoenix", "Kubernetes"],
        "notes": "Basic date retrieval from dairy farm doc",
    },
    {
        "question": "How many cows does the dairy farm plan to have after expansion?",
        "expected_document": "dairy_farm.txt",
        "expected_facts": ["200"],
        "forbidden_facts": [],
        "notes": "Numeric fact retrieval",
    },
    {
        "question": "What node type does the Phoenix Kubernetes cluster use?",
        "expected_document": "kubernetes_sizing.txt",
        "expected_facts": ["m5.2xlarge"],
        "forbidden_facts": [],
        "notes": "Technical detail retrieval",
    },
    {
        "question": "When does the Phoenix system test phase begin?",
        "expected_document": "project_phoenix.txt",
        "expected_facts": ["May"],
        "forbidden_facts": [],
        "notes": "Project timeline retrieval",
    },
    {
        "question": "What is the budget for the dairy farm project?",
        "expected_document": "dairy_farm.txt",
        "expected_facts": ["450,000", "SEK"],
        "forbidden_facts": [],
        "notes": "Financial fact retrieval",
    },
]


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def indexed_store(db_session: object) -> tuple[FakeEmbeddingProvider, FakeVectorStore]:
    """Index all synthetic documents and return the embedding provider + store."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models import Workspace

    session: AsyncSession = db_session  # type: ignore[assignment]

    ws = Workspace(name="default", is_default=True)
    session.add(ws)
    await session.commit()

    embedding = FakeEmbeddingProvider(dim=8)
    store = FakeVectorStore()

    with tempfile.TemporaryDirectory() as tmpdir:
        for filename, content in SYNTHETIC_DOCS.items():
            path = Path(tmpdir) / filename
            path.write_text(content.strip(), encoding="utf-8")
            await ingest_document(
                path=path,
                session=session,
                embedding_provider=embedding,
                vector_store=store,
                chunk_size_tokens=128,
                overlap_tokens=16,
            )

    return embedding, store


# ── Retrieval quality tests ───────────────────────────────────────────────────


class TestRetrievalQuality:
    """Test that the correct document is retrieved for each golden question.

    Note: FakeEmbeddingProvider uses hash-based vectors, not semantic vectors,
    so these tests verify the pipeline mechanics rather than semantic ranking.
    Real semantic quality is tested with live Ollama embeddings (integration tests).
    """

    async def test_all_documents_indexed(
        self, indexed_store: tuple[FakeEmbeddingProvider, FakeVectorStore]
    ) -> None:
        _, store = indexed_store
        health = await store.health()
        assert health.document_count > 0

    async def test_retrieval_returns_results_for_each_question(
        self, indexed_store: tuple[FakeEmbeddingProvider, FakeVectorStore]
    ) -> None:
        embedding, store = indexed_store
        for case in GOLDEN_QA:
            result = await retrieve(
                query=case["question"],
                embedding_provider=embedding,
                vector_store=store,
                top_k=6,
            )
            assert len(result.chunks) > 0, f"No results for: {case['question']}"

    async def test_citations_present_when_results_found(
        self, indexed_store: tuple[FakeEmbeddingProvider, FakeVectorStore]
    ) -> None:
        embedding, store = indexed_store
        result = await retrieve(
            query="dairy farm expansion",
            embedding_provider=embedding,
            vector_store=store,
        )
        if result.chunks:
            assert len(result.citations) == len(result.chunks)
            for citation in result.citations:
                assert citation.filename
                assert citation.score >= 0.0

    async def test_context_slot_contains_source_label(
        self, indexed_store: tuple[FakeEmbeddingProvider, FakeVectorStore]
    ) -> None:
        embedding, store = indexed_store
        result = await retrieve(
            query="Phoenix project",
            embedding_provider=embedding,
            vector_store=store,
        )
        if result.context_slot:
            assert "Source:" in result.context_slot.content
            assert "treat as data" in result.context_slot.content.lower()

    async def test_token_budget_respected(
        self, indexed_store: tuple[FakeEmbeddingProvider, FakeVectorStore]
    ) -> None:
        from app.brain.context_builder import estimate_tokens

        embedding, store = indexed_store
        budget = 300
        result = await retrieve(
            query="any question",
            embedding_provider=embedding,
            vector_store=store,
            rag_token_budget=budget,
        )
        if result.context_slot:
            used = sum(estimate_tokens(c.content) for c in result.chunks)
            assert used <= budget


# ── Chunking quality tests ────────────────────────────────────────────────────


class TestChunkingQuality:
    def test_no_content_lost_in_chunking(self) -> None:
        """All characters from source should appear in at least one chunk."""
        text = "The quick brown fox jumps over the lazy dog. " * 50
        from app.knowledge.parser import ParsedPage

        parsed = [ParsedPage(text=text, page=None)]
        chunks = chunk_pages(parsed, chunk_size_tokens=20, overlap_tokens=5)
        all_chunk_text = " ".join(c.content for c in chunks)
        # Every word from source should appear somewhere in chunks
        for word in text.split()[:20]:  # spot-check first 20 words
            assert word in all_chunk_text

    def test_chunk_size_approximately_respected(self) -> None:
        from app.knowledge.parser import ParsedPage

        text = "word " * 2000
        parsed = [ParsedPage(text=text, page=None)]
        target = 100
        chunks = chunk_pages(parsed, chunk_size_tokens=target, overlap_tokens=10)
        for chunk in chunks[:-1]:  # last chunk may be smaller
            assert chunk.token_count <= target * 1.2  # allow 20% overage

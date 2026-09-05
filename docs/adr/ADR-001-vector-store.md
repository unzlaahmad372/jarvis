# ADR-001 — Vector Store: Chroma (Phase 2)

**Date:** 2025  
**Status:** Accepted

## Context

JARVIS needs a local vector store for document embeddings in Phase 2 (RAG).
Candidates: Chroma, Qdrant.

## Decision

Use **persistent Chroma** (local embedded mode) for Phase 2.

## Reasons

- No separate server process required — runs embedded in the Python process
- File-based persistence — survives restarts without a daemon
- Simple Python API — easy to wrap behind the `VectorStore` interface
- Adequate performance for personal-scale document collections
- Qdrant server mode adds operational complexity not justified for v0.1

## Consequences

- Chroma types must not leak outside the `VectorStore` adapter
- If Qdrant or another backend is needed later, only the adapter changes
- Chroma is not suitable for very large multi-user deployments — acceptable for v0.1

## Alternatives considered

- **Qdrant**: Better scalability, but requires a server process
- **FAISS**: No built-in persistence or metadata filtering

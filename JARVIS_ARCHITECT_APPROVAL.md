# JARVIS — Chief Architect Approval & Build Baseline

**Status:** APPROVED TO START  
**Baseline:** Architecture v1.0  
**Build authorization:** Phase 0 only

## Executive decision

The JARVIS architecture is technically sound enough to start implementation. The project has strong boundaries around local-first data, deterministic tool permissions, RAG provenance, testing, observability, future voice/DevOps integrations and remote-security concerns.

The primary architecture risk is now **scope creep**, not a missing framework. Therefore this review freezes v0.1 scope until Phases 0–2 are complete.

## Authoritative v0.1 definition

**v0.1 = Phase 0 + Phase 1 + Phase 2.**

It delivers one complete vertical slice:

```text
Browser GUI
    |
FastAPI
    |
Orchestrator + ContextBuilder
    |
Ollama
    |
SQLite + local document store + Chroma
    |
Grounded answer with source citations
```

It must run locally without Docker and without any cloud account.

## Approved baseline stack

Backend: Python 3.12, `.venv`, FastAPI/Uvicorn, Pydantic Settings, SQLAlchemy 2, Alembic, SQLite WAL, httpx, Ollama provider abstraction.

RAG (Phase 2): Ollama/local embeddings, persistent Chroma behind `VectorStore`, pypdf, python-docx, versioned index and golden Q&A regression suite.

Frontend: React + TypeScript + Vite, Zustand for HUD/client event state, TanStack Query for server-owned state, OpenAPI-derived types, Vitest/RTL/MSW, Playwright for selected E2E/visual checks.

Streaming: SSE for Phase 1 server-to-browser streaming. WebSockets are deferred until a real bidirectional requirement exists.

Quality: pytest, pytest-asyncio, Ruff, mypy, coverage, pip-audit, pre-commit/secret scan, npm lockfile.

## Architecture decisions

### ACCEPT
- Local-first native runtime
- Ollama abstraction
- FastAPI/React separation
- SQLite + migrations
- Chroma as initial vector adapter
- ContextBuilder
- deterministic PolicyEngine/ToolExecutor
- mock/fake testing for each module
- RAG evaluation/regression testing
- source provenance/citations
- future FileAccessRegistry
- future read-only DevOps adapters

### ACCEPT WITH MODIFICATION
- HUD GUI: design tokens and usable shell now; cinematic animation later
- OpenTelemetry: request IDs/bootstrap now; collector/exporter later
- Docker Compose: secondary target only after native v0.1 works
- file watcher: add after manual ingestion path is stable
- voice: push-to-talk before wake word; speaker verification later
- Kiro: ACP specialist-agent integration later, read-only first, terms gate required
- MCP: only for genuine MCP providers when there is a concrete need
- location: provider abstraction only; no Google consumer-session scraping

### DEFER until after v0.1
Kubernetes, Jenkins, Spinnaker, Grafana operations, memory, automation, advanced agent planning, voice implementation, location, remote/mobile, Tauri, Kiro/ACP, MCP, cloud models, OCR, hybrid search/reranking, PostgreSQL/Qdrant and multi-user support.

### REJECT for the initial build
Mandatory Docker, microservices, Redis/Celery/Kafka, autonomous-agent swarms, arbitrary shell, unrestricted filesystem, Kubernetes writes, silent cloud fallback, secrets/location history in RAG, unsupported Google Maps scraping, broad Kiro permissions, and WebSockets without a real bidirectional requirement.

## Important additions made by this review

1. **Workspace/domain field from the beginning.** Seed one default workspace now; documents/conversations carry `workspace_id`. This gives a clean path to later personal/work isolation without separate databases.
2. **Stable event contract.** Streamed events have `event_id`, `request_id`, sequence, type, timestamp and payload.
3. **Typed errors.** UI receives stable error codes, not raw stack traces.
4. **Document ingestion state machine.** Parsing/embedding/indexing state is explicit so failed indexes cannot masquerade as complete.
5. **Same-origin local production path.** Vite is a development server; normal local build should prefer serving the built GUI with/from the local backend origin.
6. **No distributed worker for v0.1.** Use bounded in-process background execution; keep a replaceable boundary.
7. **No future-module scaffolding.** Amazon Q must not generate empty voice/Kubernetes/Kiro/location modules during Phase 0 just because the master spec describes them.

## Phase 0 deliverables

Phase 0 should produce only the foundation needed for later phases:
- repository/project structure for current needs
- `.venv` workflow
- `pyproject.toml`
- config/settings
- SQLite + SQLAlchemy + Alembic foundation
- FastAPI application
- request/correlation IDs
- Ollama provider abstraction + health probe
- ContextBuilder interface/capability model, not full RAG behavior
- liveness/readiness/dependency health
- bounded inference manager/basic concurrency controls
- React/Vite shell with HUD design tokens and System Status
- exact local dev CORS/origin rules
- test infrastructure/fakes
- lint/type/security tooling
- CI foundation
- README/setup docs

**Do not implement RAG in Phase 0. Do not implement chat persistence in Phase 0 unless required by a tiny smoke path. Do not implement future integrations.**

## Phase 0 exit decision

At completion, run the repository checks and then use `JARVIS_READINESS_CHECKLIST.md` in read-only review mode.

The next phase starts only after the review returns:

`READY FOR NEXT PHASE: YES`

## Command to give Amazon Q

```text
You are implementing JARVIS under an approved architecture baseline.

Read JARVIS_ARCHITECT_APPROVAL.md first, then JARVIS_MASTER_SPEC.md and JARVIS_READINESS_CHECKLIST.md.

The Chief Architect has approved the project to start PHASE 0 ONLY.
Treat Section 123 of JARVIS_MASTER_SPEC.md as the final override for the initial build.

Before writing code:
1. inspect the workspace
2. confirm the v0.1 scope freeze
3. list the exact Phase 0 files/dependencies you propose
4. flag any conflict between the approval baseline and older sections
5. do not implement future-phase modules or placeholder scaffolding

Then implement Phase 0, write tests, run lint/type/tests/security checks, update docs, and stop.
Report exact results and wait for approval before Phase 1.
```

## Final Chief Architect verdict

**GO. Start Phase 0.**

Do not redesign the project again before coding unless implementation exposes a concrete blocker.

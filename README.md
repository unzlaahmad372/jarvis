# JARVIS — Local-First Personal AI Assistant

A private, local-first AI assistant inspired by JARVIS from Iron Man.
Runs entirely on your machine. No cloud account required.

**Current status: Phase 31 — Conversation Intelligence complete.**

- ✅ Phase 0 — FastAPI backend, SQLite, Ollama, health endpoints
- ✅ Phase 1 — Persistent chat, streaming (SSE), context budgeting, React/Vite frontend
- ✅ Phase 2 — Document ingestion, embeddings, Chroma vector store, RAG citations
- ✅ Phase 3 — CI/CD ops (Jenkins, Spinnaker, Grafana)
- ✅ Phase 4 — Kubernetes read-only cluster queries
- ✅ Phase 5 — Voice push-to-talk, STT, TTS
- ✅ Phase 6 — Safe tools, filesystem, policy engine
- ✅ Phase 7 — Long-term memory
- ✅ Phase 8 — Automation Engine (scheduler, overlap policies, permission ceilings, REST API)
- ✅ Phase 9 — Advanced Agent Capabilities (multi-step planning, task decomposition, confirmation flow)
- ✅ Phase 10 — Backup & Recovery Hardening (BackupManager, RestoreDrill, integrity checks)
- ✅ Phase 11 — Remote/Mobile Auth (JWT, device registry, scoped authorization, rate limiting)
- ✅ Phase 12 — Production Hardening (audit log API, data retention enforcement, secrets validation, privacy docs)
- ✅ Phase 13 — MCP (Model Context Protocol adapter, server registry)
- ✅ Phase 14 — Vision (image analysis, llava model routing)
- ✅ Phase 20 — OpenTelemetry spans (ToolExecutor, RAG, OllamaProvider, InferenceManager)
- ✅ Phase 21 — HUD Visual Overhaul (JarvisCore SVG orb, TopBar, live clock, model chip)
- ✅ Phase 22 — Wake Word (continuous browser STT, "Hey JARVIS", mic conflict fix)
- ✅ Phase 23 — Conversation Search & Smart Sidebar (debounced search, date groups)
- ✅ Phase 24 — Settings API (DB-persisted runtime overrides, safe pydantic-settings)
- ✅ Phase 25 — Conversation Export (markdown/json/txt, export-all with eager load)
- ✅ Phase 26 — Workspaces (CRUD, cascade guard, conversation count)
- ✅ Phase 27 — Notifications (browser Notification API, automation polling)
- ✅ Phase 28 — Plugins (drop-in tools, JARVIS_ENABLE_PLUGINS flag, 403 when disabled)
- ✅ Phase 29 — Conversation Intelligence — auto-title, on-demand summary + panel
- ✅ Phase 30 — Topic Tags — LLM tag generation, persistence, tag chips in sidebar
- ✅ Phase 31 — Auto-tag on first turn, tag button in header, tag filter bar in sidebar

---

## Architecture

```
Browser (React + Vite)  →  http://127.0.0.1:5173
           |
      FastAPI backend   →  http://127.0.0.1:8000
           |
   Orchestrator + ContextBuilder + RAG Retrieval
           |
   OllamaProvider  ──  Ollama  →  http://127.0.0.1:11434
           |
   SQLite (chat history)  +  Chroma (vector index)
           |
   AutomationScheduler  ──  APScheduler (FakeBackend now, real backend next)
```

---

## Prerequisites

Install these before anything else:

| Tool | Version | Download |
|---|---|---|
| Python | 3.12+ | https://www.python.org/downloads/ |
| Node.js | 20 LTS or newer | https://nodejs.org/ |
| Ollama | latest | https://ollama.com |
| Git | any | https://git-scm.com |

---

## Installation

### 1 — Clone the repo

```bash
git clone <your-repo-url> jarvis
cd jarvis
```

### 2 — Pull the required Ollama models

Ollama must be running before you start JARVIS.

```bash
# Start Ollama (if not already running as a service)
ollama serve

# In a separate terminal — pull the chat model
ollama pull llama3.2

# Pull the embedding model (required for RAG / document search)
ollama pull nomic-embed-text
```

### 3 — Set up the Python backend

**Windows (PowerShell)**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

> If PowerShell blocks the activation script:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> ```

**macOS / Linux / WSL**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

### 4 — Configure environment

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

The defaults work out of the box. Edit `.env` only if you need to change the model or ports:

```env
JARVIS_LLM_MODEL=llama3.2          # chat model pulled in step 2
JARVIS_EMBEDDING_MODEL=nomic-embed-text  # embedding model pulled in step 2
JARVIS_OLLAMA_URL=http://127.0.0.1:11434
```

### 5 — Set up the frontend

```bash
cd frontend
npm install
cd ..
```

---

## Running JARVIS

You need **three terminals** running at the same time.

### Terminal 1 — Ollama

```bash
ollama serve
```

Skip this if Ollama is already running as a background service.

### Terminal 2 — Backend

```bash
# Windows — activate venv first
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

# Start the backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Verify it's up:
```
GET http://127.0.0.1:8000/health/live
GET http://127.0.0.1:8000/health/dependencies
```

### Terminal 3 — Frontend

```bash
cd frontend
npm run dev
```

Open your browser at **http://127.0.0.1:5173**

---

## What you can do

| Feature | How |
|---|---|
| Chat with JARVIS | Type in the chat box on the main page |
| Upload documents for RAG | Go to `/documents`, upload a `.txt`, `.md`, `.pdf`, or `.docx` file |
| Ask questions about your documents | Chat normally — JARVIS retrieves relevant chunks automatically |
| View conversation history | Sidebar on the left |
| Manage automation jobs | Go to `/automations` — create, enable/disable, trigger, view execution history |

---

## Tests

```bash
# Activate venv first, then:

# Unit + integration tests
python -m pytest tests/ -v

# RAG evaluation suite
python -m pytest evals/ -v

# All tests with coverage
python -m pytest
```

## Quality checks

```bash
python -m ruff check app/ tests/    # lint
python -m mypy app/                 # type check
python -m pip_audit                 # dependency audit
```

---

## Directory structure

```
app/
  api/          FastAPI routes (chat, conversations, documents, health, automation)
  automation/   Scheduler, job persistence, overlap policies, permission ceilings
  brain/        Orchestrator, ContextBuilder, compaction
  core/         Config, logging
  db/           SQLAlchemy models, Alembic migrations
  health/       Per-dependency health checks
  inference/    Concurrency guard (InferenceManager)
  knowledge/    Parser, chunker, embeddings, vector store, ingestion, retrieval
  llm/          LLMProvider abstraction + OllamaProvider
frontend/
  src/
    app/        Zustand stores, router
    features/   Chat page, Documents page, Automations page
    services/   API client (REST + SSE)
    types/      TypeScript types matching FastAPI schemas
tests/
  fakes/        FakeLLMProvider, FakeEmbeddingProvider, FakeVectorStore
  unit/         Unit tests — no Ollama or network required
evals/          Golden Q&A RAG evaluation suite
data/
  database/     SQLite database (jarvis.db)
  indexes/      Chroma vector index
  documents/    Processed document store
  inbox/        Drop files here for future auto-ingestion
docs/
  adr/          Architecture Decision Records
  architecture.md
  security.md
  setup.md
```

---

## Troubleshooting

**"Ollama is not reachable at 127.0.0.1:11434"**
→ Run `ollama serve` in a terminal and leave it running.

**"Model 'llama3.2' not found"**
→ Run `ollama pull llama3.2`

**"Model 'nomic-embed-text' not found"**
→ Run `ollama pull nomic-embed-text` (required for document search / RAG)

**Document stuck in `processing` state**
→ Check the backend terminal for errors. Usually means Ollama isn't running or `nomic-embed-text` isn't pulled.

**PowerShell activation blocked**
→ `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

**`npm: command not found` on Windows**
→ Open a new terminal after installing Node.js so the PATH updates, or prefix commands with `set PATH=C:\Progra~1\nodejs;%PATH% &&`

**Frontend shows blank page / API errors**
→ Make sure the backend is running on port 8000 before opening the frontend.

---

## Security model

- Binds to `127.0.0.1` only — not accessible from other machines by default
- No cloud AI without explicit opt-in (`JARVIS_ENABLE_CLOUD=false`)
- All feature flags default to the safer/off state
- Retrieved document content is treated as untrusted data, not instructions

See [docs/security.md](docs/security.md) for full details.

---

## Roadmap

| Phase | Description | Status |
|---|---|---|
| 0 | Foundation — FastAPI, SQLite, Ollama, health | ✅ Done |
| 1 | Local chat — persistence, context, streaming | ✅ Done |
| 2 | RAG — document ingestion, embeddings, citations | ✅ Done |
| 3 | CI/CD ops — Jenkins, Spinnaker, Grafana | ✅ Done |
| 4 | Kubernetes — read-only cluster queries | ✅ Done |
| 5 | Voice — push-to-talk, STT, TTS | ✅ Done |
| 6 | Safe tools — filesystem, policy engine | ✅ Done |
| 7 | Memory — long-term, remember/forget | ✅ Done |
| 8 | Automation — scheduler, overlap policies, permission ceilings | ✅ Done |
| 9 | Advanced Agent — multi-step planning, task decomposition, confirmation flow | ✅ Done |
| 10 | Backup & Recovery — BackupManager, RestoreDrill, integrity checks | ✅ Done |
| 11 | Remote/Mobile Auth — JWT, device registry, scoped authorization, rate limiting | ✅ Done |
| 12 | Production Hardening — audit log, retention enforcement, secrets validation | ✅ Done |
| 13 | MCP — Model Context Protocol adapter | ✅ Done |
| 14 | Vision — image analysis, llava routing | ✅ Done |
| 20 | OpenTelemetry — distributed tracing spans | ✅ Done |
| 21 | HUD Visual Overhaul — JarvisCore orb, TopBar, live clock | ✅ Done |
| 22 | Wake Word — continuous browser STT, "Hey JARVIS" | ✅ Done |
| 23 | Conversation Search & Smart Sidebar | ✅ Done |
| 24–28 | Settings / Export / Workspaces / Notifications / Plugins | ✅ Done |
| 29 | Conversation Intelligence — auto-title, on-demand summary + panel | ✅ Done |
| 30 | Topic Tags — LLM tag generation, persistence, tag chips in sidebar | ✅ Done |
| 31 | Auto-tag on first turn, tag button in header, tag filter bar in sidebar | ✅ Done |
| 32 | Model Switcher — runtime model selection per conversation | 🔄 Next |

# ADR-004 — Runtime: Native Local Mode

**Date:** 2025  
**Status:** Accepted

## Decision

**Native Local Mode** (Python `.venv` + native Ollama + SQLite) is the primary runtime.
Docker Compose is a secondary optional target.

## Reasons

- Simplest path for a personal assistant on a developer laptop
- No Docker required for daily use
- Ollama runs natively and benefits from GPU access without Docker GPU passthrough complexity
- SQLite + embedded Chroma require no daemons

## Consequences

- Docker Compose added only after native v0.1 is stable
- All core components must work without containerisation
- Platform-specific paths use `pathlib` throughout

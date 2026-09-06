# ADR-005 — Runtime Settings Persistence

**Status**: Accepted  
**Phase**: 24  
**Date**: 2025

## Context

JARVIS needs a way to patch runtime settings (model name, token budgets, feature flags) without restarting the process. The initial implementation mutated the frozen pydantic-settings `@lru_cache` singleton via `object.__setattr__`, which bypasses validation and is architecturally unsafe.

## Decision

Runtime setting overrides are persisted to the existing `settings` DB table (key/value store). On `GET /api/v1/settings`, the pydantic-settings defaults are merged with DB overrides. On `POST /api/v1/settings`, only a declared allowlist of fields (`_PATCHABLE`) may be written. The `@lru_cache` singleton is never mutated.

## Consequences

- **+** Overrides survive process restart (stored in SQLite).
- **+** Pydantic-settings singleton remains immutable; validators are not bypassed.
- **+** Structural/security config (host, auth_secret_key, database_url) cannot be patched via API.
- **−** A process restart is still required for changes to take effect in subsystems that read config at startup (e.g. Ollama URL, DB URL). This is documented in the API response.

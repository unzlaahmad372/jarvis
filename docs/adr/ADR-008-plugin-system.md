# ADR-008 — Plugin System

**Status**: Accepted  
**Phase**: 28  
**Date**: 2025

## Context

Power users need a way to extend JARVIS with custom tools without modifying core source. Drop-in Python files are the simplest mechanism for a local-first app.

## Decision

Plugins are `.py` files placed in `data/plugins/`. Each must expose a `plugin_tool` attribute that is a `BaseTool` subclass instance. Plugins are loaded via `importlib` and registered into the tool registry.

**Security gates (mandatory)**:
1. `JARVIS_ENABLE_PLUGINS=true` must be explicitly set (defaults to `false`).
2. `data/plugins/` is in `.gitignore` — plugin files are never committed.
3. `POST /api/v1/plugins/reload` returns HTTP 403 when the flag is off.

Plugin execution is subject to the same policy engine as built-in tools (risk level, confirmation requirements).

## Consequences

- **+** Zero-friction extensibility for local use.
- **+** Feature flag ensures plugins are opt-in; default posture is safe.
- **−** Plugins run in-process with full Python access. This is acceptable for a local-first, single-user app but would be unacceptable in a multi-tenant deployment.
- **−** No sandboxing. Future phases may add a subprocess/WASM execution boundary.

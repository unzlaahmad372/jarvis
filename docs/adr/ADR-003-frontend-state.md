# ADR-003 — Frontend State: Zustand

**Date:** 2025  
**Status:** Accepted

## Decision

Use **Zustand** for cross-cutting client/HUD/event state in the React frontend.

## Reasons

- Lightweight — no boilerplate compared to Redux
- Simple API — plain functions, no reducers/actions required
- Works well alongside TanStack Query (server state stays in Query, UI state in Zustand)
- Easy to test with deterministic store snapshots

## Consequences

- Server-authoritative data (conversations, documents, health) stays in TanStack Query
- Zustand stores: chatStore, hudStore, toolExecutionStore, voiceStore, settingsStore

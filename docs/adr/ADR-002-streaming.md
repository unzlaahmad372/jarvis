# ADR-002 — Streaming: Server-Sent Events (Phase 1)

**Date:** 2025  
**Status:** Accepted

## Decision

Use **SSE (Server-Sent Events)** for server-to-browser streaming in Phase 1.

## Reasons

- One-way stream from server to browser — SSE is the correct primitive
- Simpler lifecycle than WebSockets (no handshake, automatic reconnect)
- Easy to debug with standard HTTP tooling
- FastAPI has native SSE support via `StreamingResponse`

## Consequences

- WebSockets deferred until a true bidirectional requirement exists (e.g. voice)
- SSE does not support binary frames — acceptable for text token streaming

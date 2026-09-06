# ADR-006 — Conversation Export

**Status**: Accepted  
**Phase**: 25  
**Date**: 2025

## Context

Users need to export their conversation history for archival, migration, or offline reading. Export must support multiple formats and be efficient for large histories.

## Decision

`GET /api/v1/export/conversations/{id}?format=markdown|json|txt` exports a single conversation. `GET /api/v1/export/conversations?format=json` exports all conversations using a single `selectinload` eager-load query to avoid N+1 database round-trips.

Responses use `Content-Disposition: attachment` headers so browsers trigger a file download.

## Consequences

- **+** No N+1 queries — all messages loaded in two SQL statements (conversations + messages via selectinload).
- **+** Three formats cover the main use cases: human-readable (md/txt) and machine-readable (json).
- **−** Export-all loads all conversations into memory. For very large histories (>10k conversations) a streaming/paginated export would be needed — deferred to a future phase.

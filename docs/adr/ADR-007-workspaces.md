# ADR-007 — Workspaces

**Status**: Accepted  
**Phase**: 26  
**Date**: 2025

## Context

JARVIS needs logical isolation between different domains of use (e.g. "Work", "Personal", "Research"). Conversations, documents, and memories should be scoped to a workspace.

## Decision

A `Workspace` model with `is_default` flag provides the isolation boundary. All `Conversation`, `Document`, and `Memory` rows carry a `workspace_id` FK with `ondelete=CASCADE`.

Delete safety: deleting a workspace with existing conversations is rejected with HTTP 409. Users must explicitly move or delete conversations first. This prevents silent data loss from the cascade.

The default workspace cannot be deleted. Activating a workspace atomically clears all other `is_default` flags.

## Consequences

- **+** Cascade is safe — the API guard prevents accidental data loss.
- **+** Simple integer FK — no UUID overhead for a local-first app.
- **−** Moving conversations between workspaces is not yet implemented (future phase).

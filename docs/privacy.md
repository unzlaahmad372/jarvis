# JARVIS — Privacy & Data Lifecycle

This document describes what JARVIS stores, where it stores it, why, how long it keeps it, how to delete it, and what happens to copies in backups.

---

## Data Classification

Every piece of information JARVIS handles is classified into one of four tiers:

| Classification | Examples | Default handling |
|---|---|---|
| PUBLIC | General knowledge, public documentation | May be used freely |
| PERSONAL | Notes, preferences, project decisions, conversation history | Local only, never sent to cloud without explicit approval |
| CONFIDENTIAL | Work documents, internal project data | Local only, restricted retrieval |
| SECRET | Passwords, API keys, private keys, credentials | Never stored in RAG/vector DB; environment variables only |

Classification affects:
- Whether content may be sent to a cloud LLM (never by default)
- Whether content appears in retrieval results
- Logging verbosity (SECRET values are never logged)
- Backup inclusion and encryption requirements

---

## What JARVIS Stores

### SQLite Database (`data/database/jarvis.db`)

| Table | Contents | Retention |
|---|---|---|
| `conversations` | Chat session metadata | `JARVIS_CONVERSATION_RETENTION_DAYS` (default 365) |
| `messages` | Individual chat messages | Deleted with parent conversation (CASCADE) |
| `conversation_summaries` | Compacted summaries of older turns | Deleted with parent conversation (CASCADE) |
| `memories` | Explicitly remembered facts | Durable until deliberately forgotten/purged |
| `documents` | Document metadata (filename, hash, status) | Until document is deleted via API |
| `document_chunks` | Text chunks with vector store references | Deleted with parent document (CASCADE) |
| `tool_executions` | Audit log of every tool call | `JARVIS_TOOL_LOG_RETENTION_DAYS` (default 90) |
| `automation_jobs` | Scheduled job definitions | Until job is deleted |
| `automation_executions` | Execution history per job | `JARVIS_TOOL_LOG_RETENTION_DAYS` (default 90) |
| `devices` | Registered remote/mobile devices | Until device is revoked and manually removed |
| `workspaces` | Logical data domains | Until workspace is deleted |
| `settings` | Application key-value settings | Persistent |

### Vector Index (`data/indexes/`)

Chroma persistent store containing:
- Text embeddings for document chunks
- Metadata references back to SQLite `document_chunks`

The vector index is **derived data**. It can always be rebuilt from the original documents and SQLite metadata. It is not the authoritative source of truth.

### Document Store (`data/documents/`)

Processed document text extracted during ingestion. The original source files are not moved here — only extracted text representations.

### Inbox (`data/inbox/`)

Drop zone for documents to be ingested. Files placed here are not automatically deleted after ingestion unless the inbox watcher is configured to do so.

---

## What JARVIS Does NOT Store

- Passwords, API keys, or private keys in the database or vector index
- Raw microphone audio (push-to-talk audio is processed in memory and discarded)
- Speaker biometric embeddings in the normal RAG vector database
- Precise family location history (when location features are enabled, only last-known position is retained by default)
- Cloud AI provider credentials in source code or the database

---

## Retention Policies

Retention periods are configurable via environment variables:

```env
JARVIS_CONVERSATION_RETENTION_DAYS=365
JARVIS_TOOL_LOG_RETENTION_DAYS=90
JARVIS_TEMP_RETENTION_HOURS=24
```

Retention enforcement runs on demand via:

```
POST /api/v1/audit/retention/run
```

This is idempotent and safe to call repeatedly. It purges:
- Conversations last updated before the retention cutoff (messages and summaries are removed via CASCADE)
- Tool execution audit records older than the tool log retention period
- Automation execution history older than the tool log retention period

**Memories are never automatically purged by retention enforcement.** They are durable until explicitly forgotten via the memory API or `DELETE /api/v1/memory/{id}`.

---

## Forget vs Purge

### FORGET (memory)

Removes a specific remembered fact from active memory:

```
DELETE /api/v1/memory/{id}
```

The memory record is deleted from SQLite. If the memory was embedded in the vector index, the corresponding vector is also removed.

### PURGE (document)

Completely removes a document and all associated data:

```
DELETE /api/v1/documents/{id}
```

This removes:
- The document record from SQLite
- All associated `document_chunks` records
- The corresponding vectors from the Chroma index
- The extracted text from `data/documents/` if present

After purge, the document will no longer appear in any retrieval results.

### Conversation deletion

Deleting a conversation removes:
- The `conversations` record
- All `messages` (CASCADE)
- All `conversation_summaries` (CASCADE)

Conversation deletion does not affect memories that were created from that conversation — those must be forgotten separately.

---

## Backup Implications

JARVIS backups (`data/backups/`) contain:
- A copy of `jarvis.db` at the time of backup
- Backup metadata (ID, timestamp, checksum, schema version)

**Backups are not automatically purged when you delete data from the live system.**

If you delete a conversation, memory, or document from the live JARVIS instance, copies may still exist in historical backups until those backups expire according to `JARVIS_BACKUP_RETENTION_DAYS` (default 30).

The vector index is not included in backups by default because it is derived data and can be rebuilt. If you need to purge a document from all backups, you must:
1. Delete the document from the live system
2. Wait for backups containing the document to expire, or manually delete those backup files

This is documented clearly rather than claiming instant complete deletion when backup copies exist.

---

## Cloud Boundary

By default, JARVIS never sends any of your data to a cloud AI provider:

```env
JARVIS_ENABLE_CLOUD=false   # default
JARVIS_ALLOW_CLOUD=false    # default
```

If cloud AI is enabled in the future, JARVIS will:
1. Explicitly tell you what type of information would be sent
2. Require your approval before sending anything
3. Never silently fall back from local to cloud

Retrieved document content, memories, and conversation history are never sent to cloud providers without explicit opt-in.

---

## Remote Access & Device Data

When remote access is enabled (`JARVIS_ENABLE_REMOTE_ACCESS=true`):
- Each device is registered with an explicit identity in the `devices` table
- Access tokens are short-lived (default 60 minutes)
- Refresh tokens are longer-lived (default 30 days)
- Revoked devices cannot obtain new tokens
- Device records persist until manually removed even after revocation

Token data is never stored in the database — only device identity and scope metadata.

---

## Secrets Handling

JARVIS validates secret configuration at startup:

- `JARVIS_AUTH_SECRET_KEY` must not be the default placeholder value
- It must be at least 32 characters
- If remote access is enabled and the key is insecure, startup fails with a clear error
- If remote access is disabled, an insecure key produces a warning only (to allow local development)

Generate a strong secret key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Logging

JARVIS uses structured logging. The following are **never** logged:

- Passwords or API keys
- JWT tokens or refresh tokens
- Private keys
- Full document contents
- Raw voice recordings
- Speaker biometric embeddings
- Precise family location coordinates

Tool execution audit logs record sanitized parameter summaries only — file contents and credential values are stripped before storage.

---

## Data Portability

You own your data. To export or migrate:

- **Conversations**: Query `GET /api/v1/conversations` and `GET /api/v1/conversations/{id}`
- **Memories**: Query `GET /api/v1/memory`
- **Documents**: The original source files are yours; document metadata is in SQLite
- **Database backup**: `POST /api/v1/backup` creates a portable backup with integrity checksum
- **Vector index**: Rebuild at any time with `POST /api/v1/documents/reindex` — the index is derived from your documents

The vector database is never the sole copy of important information.

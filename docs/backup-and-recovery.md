# JARVIS Backup & Recovery

## Overview

JARVIS backs up the SQLite database (`jarvis.db`). The vector index is **derived data** and is always rebuildable from the source documents — it is not included in backups.

Each backup is a directory under `data/backups/{uuid}/` containing:

| File | Purpose |
|---|---|
| `jarvis.db` | Copy of the live database |
| `metadata.json` | Backup ID, timestamps, versions, checksum |
| `checksum.sha256` | SHA-256 of `jarvis.db` for integrity verification |

---

## REST API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/backup` | Create a new backup |
| `GET` | `/api/v1/backups` | List all backups (newest first) |
| `GET` | `/api/v1/backups/{id}` | Get a single backup |
| `POST` | `/api/v1/backups/{id}/verify` | Verify checksum |
| `POST` | `/api/v1/backups/{id}/restore` | Restore (creates safety copy first) |
| `POST` | `/api/v1/backups/{id}/drill` | Non-destructive restore drill |
| `DELETE` | `/api/v1/backups/{id}` | Delete a backup |

---

## Creating a Backup

```bash
curl -X POST http://127.0.0.1:8000/api/v1/backup
```

Optional notes parameter:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/backup?notes=before+upgrade"
```

---

## Restore Procedure

### 1. List available backups

```bash
curl http://127.0.0.1:8000/api/v1/backups
```

### 2. Run a restore drill (non-destructive)

```bash
curl -X POST http://127.0.0.1:8000/api/v1/backups/{id}/drill
```

The drill verifies:
1. Backup file exists
2. Database opens and passes integrity check
3. Schema version is readable
4. All required tables are present
5. Conversations are readable
6. Memories are readable
7. Documents are readable

### 3. Verify checksum

```bash
curl -X POST http://127.0.0.1:8000/api/v1/backups/{id}/verify
```

### 4. Restore

```bash
curl -X POST http://127.0.0.1:8000/api/v1/backups/{id}/restore
```

**Safety invariant**: before overwriting the live database, JARVIS creates a `.pre_restore_{timestamp}.db` safety copy in the same directory.

**After restore**: restart JARVIS to use the restored database.

---

## Retention

Backups are retained for `JARVIS_BACKUP_RETENTION_DAYS` (default: 30 days). Pruning is not automatic — call the delete endpoint or implement a scheduled automation job.

---

## Backup Metadata

Every backup records:

```json
{
  "backup_id": "uuid",
  "created_at": "2025-01-01T12:00:00+00:00",
  "app_version": "0.1.0",
  "backup_format_version": "1",
  "database_schema_version": "abc123",
  "contents": ["jarvis.db", "metadata.json", "checksum.sha256"],
  "checksum_sha256": "sha256hex",
  "source_db_path": "/path/to/jarvis.db",
  "notes": ""
}
```

---

## What Is NOT Backed Up

| Item | Reason |
|---|---|
| Vector index (`data/indexes/`) | Derived data — always rebuildable via `POST /api/v1/documents/{id}/reindex` |
| Source documents (`data/documents/`) | Original files are the authoritative source |
| `.env` / secrets | Never backed up — secrets must be managed separately |

---

## Disaster Recovery

If the live database is lost or corrupted:

1. Stop JARVIS.
2. Identify the most recent good backup: `GET /api/v1/backups`
3. Run the drill to confirm it is valid: `POST /api/v1/backups/{id}/drill`
4. Restore: `POST /api/v1/backups/{id}/restore`
5. Restart JARVIS.
6. Rebuild the vector index if needed: re-ingest documents via the Documents API.

---

## Security Notes

- Backups contain all conversation history, memories, and document metadata.
- Treat backup files with the same sensitivity as the live database.
- Backup files are stored locally under `data/backups/` — never committed to Git.
- The `.gitignore` excludes `data/` by default.

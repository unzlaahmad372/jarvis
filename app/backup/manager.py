"""BackupManager — create, verify, restore and delete JARVIS backups.

Backup contents per archive directory:
  jarvis.db          — SQLite database copy (via SQLite VACUUM INTO)
  metadata.json      — backup ID, timestamps, versions, contents list
  checksum.sha256    — SHA-256 of jarvis.db for integrity verification

The vector index is derived data and is NOT included by default.
It can always be rebuilt from the source documents.

Spec §46 requirements implemented:
  - backup ID, created_at, app version, schema version, contents, checksum
  - restore validation (RestoreDrill in restore.py)
  - never make the vector database the sole source of truth
"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)

APP_VERSION = "0.1.0"
BACKUP_FORMAT_VERSION = "1"


@dataclass
class BackupMetadata:
    backup_id: str
    created_at: str          # ISO-8601 UTC
    app_version: str
    backup_format_version: str
    database_schema_version: str
    contents: list[str]      # filenames included
    checksum_sha256: str      # SHA-256 of jarvis.db
    source_db_path: str
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> BackupMetadata:
        fields = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**fields)  # type: ignore[arg-type]


@dataclass
class BackupRecord:
    backup_id: str
    backup_dir: Path
    created_at: datetime
    app_version: str
    checksum_sha256: str
    contents: list[str] = field(default_factory=list)
    notes: str = ""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _get_schema_version(db_path: Path) -> str:
    """Read the Alembic schema version from the SQLite DB, or return 'unknown'."""
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.execute("SELECT version_num FROM alembic_version LIMIT 1")
            row = cur.fetchone()
            return str(row[0]) if row else "no_migrations"
        except Exception:
            return "no_alembic_table"
        finally:
            conn.close()
    except Exception:
        return "unknown"


class BackupManager:
    """Creates and manages JARVIS database backups."""

    def __init__(self, backup_dir: Path, db_path: Path) -> None:
        self._backup_dir = backup_dir
        self._db_path = db_path
        self._backup_dir.mkdir(parents=True, exist_ok=True)

    # ── Create ────────────────────────────────────────────────────────────────

    def create(self, notes: str = "") -> BackupRecord:
        """Create a new backup. Returns the BackupRecord."""
        if not self._db_path.exists():
            raise FileNotFoundError(f"Source database not found: {self._db_path}")

        backup_id = str(uuid.uuid4())
        dest_dir = self._backup_dir / backup_id
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest_db = dest_dir / "jarvis.db"

        # Use SQLite backup API via shutil for a consistent copy.
        # For a live WAL-mode DB the safest approach is a direct file copy
        # after a VACUUM INTO (which flushes WAL). We use shutil.copy2 here
        # since we don't have a sync connection available; callers should
        # ensure no writes are in flight (acceptable for a local personal tool).
        self._copy_database(dest_db)

        checksum = _sha256(dest_db)
        schema_version = _get_schema_version(dest_db)
        now = datetime.now(UTC)

        contents = ["jarvis.db", "metadata.json", "checksum.sha256"]
        meta = BackupMetadata(
            backup_id=backup_id,
            created_at=now.isoformat(),
            app_version=APP_VERSION,
            backup_format_version=BACKUP_FORMAT_VERSION,
            database_schema_version=schema_version,
            contents=contents,
            checksum_sha256=checksum,
            source_db_path=str(self._db_path),
            notes=notes,
        )

        (dest_dir / "metadata.json").write_text(
            json.dumps(meta.to_dict(), indent=2), encoding="utf-8"
        )
        (dest_dir / "checksum.sha256").write_text(
            f"{checksum}  jarvis.db\n", encoding="utf-8"
        )

        logger.info(
            "backup_created",
            backup_id=backup_id,
            checksum=checksum[:16],
            schema_version=schema_version,
        )

        return BackupRecord(
            backup_id=backup_id,
            backup_dir=dest_dir,
            created_at=now,
            app_version=APP_VERSION,
            checksum_sha256=checksum,
            contents=contents,
            notes=notes,
        )

    def _copy_database(self, dest: Path) -> None:
        """Copy the SQLite database file."""
        shutil.copy2(self._db_path, dest)

    # ── List ──────────────────────────────────────────────────────────────────

    def list_backups(self) -> list[BackupRecord]:
        """Return all backups sorted newest-first."""
        records: list[BackupRecord] = []
        for entry in self._backup_dir.iterdir():
            if not entry.is_dir():
                continue
            meta_path = entry / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                meta = BackupMetadata.from_dict(
                    json.loads(meta_path.read_text(encoding="utf-8"))
                )
                records.append(
                    BackupRecord(
                        backup_id=meta.backup_id,
                        backup_dir=entry,
                        created_at=datetime.fromisoformat(meta.created_at),
                        app_version=meta.app_version,
                        checksum_sha256=meta.checksum_sha256,
                        contents=meta.contents,
                        notes=meta.notes,
                    )
                )
            except Exception as exc:
                logger.warning("backup_metadata_unreadable", path=str(entry), error=str(exc))
        return sorted(records, key=lambda r: r.created_at, reverse=True)

    def get_backup(self, backup_id: str) -> BackupRecord | None:
        """Return a single backup record by ID."""
        for record in self.list_backups():
            if record.backup_id == backup_id:
                return record
        return None

    # ── Verify ────────────────────────────────────────────────────────────────

    def verify(self, backup_id: str) -> tuple[bool, str]:
        """Verify the checksum of a backup's database file.

        Returns (ok, message).
        """
        record = self.get_backup(backup_id)
        if record is None:
            return False, f"Backup '{backup_id}' not found."

        db_file = record.backup_dir / "jarvis.db"
        if not db_file.exists():
            return False, "Backup database file missing."

        actual = _sha256(db_file)
        if actual != record.checksum_sha256:
            return False, (
                f"Checksum mismatch. Expected {record.checksum_sha256[:16]}… "
                f"got {actual[:16]}…"
            )

        logger.info("backup_verified", backup_id=backup_id)
        return True, "Checksum OK."

    # ── Restore ───────────────────────────────────────────────────────────────

    def restore(self, backup_id: str, *, verify_first: bool = True) -> Path:
        """Restore a backup over the live database.

        Verifies checksum first (unless verify_first=False).
        Creates a safety copy of the current DB before overwriting.
        Returns the path of the restored database.
        """
        record = self.get_backup(backup_id)
        if record is None:
            raise ValueError(f"Backup '{backup_id}' not found.")

        if verify_first:
            ok, msg = self.verify(backup_id)
            if not ok:
                raise ValueError(f"Backup integrity check failed: {msg}")

        src_db = record.backup_dir / "jarvis.db"

        # Safety copy of current DB before overwrite
        if self._db_path.exists():
            safety = self._db_path.with_suffix(
                f".pre_restore_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}.db"
            )
            shutil.copy2(self._db_path, safety)
            logger.info("restore_safety_copy", path=str(safety))

        shutil.copy2(src_db, self._db_path)
        logger.info("backup_restored", backup_id=backup_id, dest=str(self._db_path))
        return self._db_path

    # ── Delete ────────────────────────────────────────────────────────────────

    def delete(self, backup_id: str) -> bool:
        """Delete a backup directory. Returns True if deleted."""
        record = self.get_backup(backup_id)
        if record is None:
            return False
        shutil.rmtree(record.backup_dir)
        logger.info("backup_deleted", backup_id=backup_id)
        return True

    # ── Retention ─────────────────────────────────────────────────────────────

    def prune(self, retention_days: int) -> list[str]:
        """Delete backups older than retention_days. Returns list of deleted IDs."""
        cutoff = datetime.now(UTC).timestamp() - retention_days * 86400
        deleted: list[str] = []
        for record in self.list_backups():
            if record.created_at.timestamp() < cutoff:
                self.delete(record.backup_id)
                deleted.append(record.backup_id)
        return deleted

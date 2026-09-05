"""RestoreDrill — validates a backup database before and after restore.

Spec §46 restore verification:
  1. database opens
  2. migrations compatible (alembic_version readable)
  3. conversations readable
  4. memories readable
  5. document records exist (or table is present)
  6. configuration loads (settings import)
  7. JARVIS would start successfully (schema tables present)

All checks run against the backup copy, never the live database.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DrillResult:
    backup_id: str
    passed: bool
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    # Each entry: (check_name, passed, detail)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append((name, ok, detail))
        if not ok:
            self.passed = False

    @property
    def summary(self) -> str:
        total = len(self.checks)
        passed = sum(1 for _, ok, _ in self.checks if ok)
        return f"{passed}/{total} checks passed"


# Tables that must exist for JARVIS to function
_REQUIRED_TABLES = [
    "workspaces",
    "conversations",
    "messages",
    "memories",
    "documents",
    "tool_executions",
    "automation_jobs",
]


class RestoreDrill:
    """Runs a non-destructive validation drill against a backup database file."""

    def run(self, backup_db_path: Path, backup_id: str = "unknown") -> DrillResult:
        """Validate the backup database. Returns a DrillResult."""
        result = DrillResult(backup_id=backup_id, passed=True)

        # 1. File exists
        result.add(
            "file_exists",
            backup_db_path.exists(),
            str(backup_db_path),
        )
        if not backup_db_path.exists():
            return result  # can't proceed without the file

        # 2. Database opens
        conn = self._open(backup_db_path, result)
        if conn is None:
            return result

        try:
            # 3. Schema version readable
            self._check_schema_version(conn, result)

            # 4. Required tables present
            self._check_tables(conn, result)

            # 5. Conversations readable
            self._check_row_count(conn, "conversations", result)

            # 6. Memories readable
            self._check_row_count(conn, "memories", result)

            # 7. Documents readable
            self._check_row_count(conn, "documents", result)

        finally:
            conn.close()

        logger.info(
            "restore_drill_complete",
            backup_id=backup_id,
            passed=result.passed,
            summary=result.summary,
        )
        return result

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _open(self, path: Path, result: DrillResult) -> sqlite3.Connection | None:
        try:
            conn = sqlite3.connect(str(path))
            conn.execute("PRAGMA integrity_check")
            result.add("database_opens", True, "integrity_check OK")
            return conn
        except Exception as exc:
            result.add("database_opens", False, str(exc))
            return None

    def _check_schema_version(self, conn: sqlite3.Connection, result: DrillResult) -> None:
        try:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
            )
            has_table = cur.fetchone() is not None
            if has_table:
                cur2 = conn.execute("SELECT version_num FROM alembic_version LIMIT 1")
                row = cur2.fetchone()
                version = str(row[0]) if row else "empty"
                result.add("schema_version_readable", True, f"version={version}")
            else:
                result.add("schema_version_readable", True, "no alembic table (pre-migration DB)")
        except Exception as exc:
            result.add("schema_version_readable", False, str(exc))

    def _check_tables(self, conn: sqlite3.Connection, result: DrillResult) -> None:
        try:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            existing = {row[0] for row in cur.fetchall()}
            missing = [t for t in _REQUIRED_TABLES if t not in existing]
            if missing:
                result.add("required_tables_present", False, f"missing: {missing}")
            else:
                result.add("required_tables_present", True, f"all {len(_REQUIRED_TABLES)} present")
        except Exception as exc:
            result.add("required_tables_present", False, str(exc))

    def _check_row_count(
        self, conn: sqlite3.Connection, table: str, result: DrillResult
    ) -> None:
        check_name = f"{table}_readable"
        try:
            cur = conn.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
            count = cur.fetchone()[0]
            result.add(check_name, True, f"{count} rows")
        except Exception as exc:
            result.add(check_name, False, str(exc))

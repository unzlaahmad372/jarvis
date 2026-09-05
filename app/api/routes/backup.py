"""Backup & Recovery REST API — Phase 10.

Endpoints:
  POST   /api/v1/backup                    — create a new backup
  GET    /api/v1/backups                   — list all backups
  GET    /api/v1/backups/{id}              — get single backup
  POST   /api/v1/backups/{id}/verify       — verify checksum
  POST   /api/v1/backups/{id}/restore      — restore (safety copy first)
  POST   /api/v1/backups/{id}/drill        — run restore drill (non-destructive)
  DELETE /api/v1/backups/{id}              — delete a backup
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas.chat import (
    BackupDrillCheckOut,
    BackupDrillOut,
    BackupListOut,
    BackupOut,
    BackupRestoreOut,
    BackupVerifyOut,
)
from app.backup.manager import BackupManager, BackupRecord
from app.backup.restore import RestoreDrill
from app.core.config import get_settings
from app.core.logging import get_logger

router = APIRouter(prefix="/api/v1", tags=["backup"])
logger = get_logger(__name__)


def _get_manager() -> BackupManager:
    settings = get_settings()
    db_path = settings.database_dir / "jarvis.db"
    return BackupManager(backup_dir=settings.backup_dir, db_path=db_path)


def _record_to_out(r: BackupRecord) -> BackupOut:
    return BackupOut(
        backup_id=r.backup_id,
        created_at=r.created_at,
        app_version=r.app_version,
        database_schema_version="",  # not stored on record; read from metadata if needed
        contents=r.contents,
        checksum_sha256=r.checksum_sha256,
        notes=r.notes,
    )


@router.post("/backup", response_model=BackupOut, status_code=201)
def create_backup(notes: str = "") -> BackupOut:
    """Create a new database backup."""
    mgr = _get_manager()
    try:
        record = mgr.create(notes=notes)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _record_to_out(record)


@router.get("/backups", response_model=BackupListOut)
def list_backups() -> BackupListOut:
    """List all available backups, newest first."""
    mgr = _get_manager()
    records = mgr.list_backups()
    return BackupListOut(backups=[_record_to_out(r) for r in records], total=len(records))


@router.get("/backups/{backup_id}", response_model=BackupOut)
def get_backup(backup_id: str) -> BackupOut:
    """Get a single backup by ID."""
    mgr = _get_manager()
    record = mgr.get_backup(backup_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Backup '{backup_id}' not found.")
    return _record_to_out(record)


@router.post("/backups/{backup_id}/verify", response_model=BackupVerifyOut)
def verify_backup(backup_id: str) -> BackupVerifyOut:
    """Verify the SHA-256 checksum of a backup."""
    mgr = _get_manager()
    ok, message = mgr.verify(backup_id)
    if not ok and "not found" in message:
        raise HTTPException(status_code=404, detail=message)
    return BackupVerifyOut(backup_id=backup_id, ok=ok, message=message)


@router.post("/backups/{backup_id}/restore", response_model=BackupRestoreOut)
def restore_backup(backup_id: str) -> BackupRestoreOut:
    """Restore a backup over the live database (creates safety copy first)."""
    mgr = _get_manager()
    try:
        restored_path = mgr.restore(backup_id)
    except ValueError as exc:
        msg = str(exc)
        status = 404 if "not found" in msg else 422
        raise HTTPException(status_code=status, detail=msg) from exc
    return BackupRestoreOut(
        backup_id=backup_id,
        restored_db_path=str(restored_path),
        message="Restore complete. Restart JARVIS to use the restored database.",
    )


@router.post("/backups/{backup_id}/drill", response_model=BackupDrillOut)
def drill_backup(backup_id: str) -> BackupDrillOut:
    """Run a non-destructive restore drill against a backup."""
    mgr = _get_manager()
    record = mgr.get_backup(backup_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Backup '{backup_id}' not found.")
    drill = RestoreDrill()
    result = drill.run(record.backup_dir / "jarvis.db", backup_id=backup_id)
    return BackupDrillOut(
        backup_id=backup_id,
        passed=result.passed,
        summary=result.summary,
        checks=[
            BackupDrillCheckOut(name=name, passed=ok, detail=detail)
            for name, ok, detail in result.checks
        ],
    )


@router.delete("/backups/{backup_id}", status_code=204)
def delete_backup(backup_id: str) -> None:
    """Delete a backup directory."""
    mgr = _get_manager()
    deleted = mgr.delete(backup_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Backup '{backup_id}' not found.")

"""Tests for Phase 10 — Backup & Recovery.

Covers:
  - BackupManager: create, list, get, verify, restore, delete, prune
  - RestoreDrill: all 7 checks, missing file, corrupted DB
  - REST API: all 7 endpoints
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.backup.manager import BACKUP_FORMAT_VERSION, BackupManager, _sha256
from app.backup.restore import RestoreDrill

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_dirs(tmp_path):
    """Provide temporary backup_dir and a minimal SQLite database."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    db_path = tmp_path / "jarvis.db"

    # Create a minimal DB with required tables
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE alembic_version (version_num TEXT NOT NULL);
        INSERT INTO alembic_version VALUES ('abc123');
        CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE conversations (id INTEGER PRIMARY KEY);
        CREATE TABLE messages (id INTEGER PRIMARY KEY);
        CREATE TABLE memories (id INTEGER PRIMARY KEY);
        CREATE TABLE documents (id INTEGER PRIMARY KEY);
        CREATE TABLE tool_executions (id INTEGER PRIMARY KEY);
        CREATE TABLE automation_jobs (id INTEGER PRIMARY KEY);
    """)
    conn.close()

    return backup_dir, db_path


@pytest.fixture
def manager(tmp_dirs):
    backup_dir, db_path = tmp_dirs
    return BackupManager(backup_dir=backup_dir, db_path=db_path)


# ── BackupManager ─────────────────────────────────────────────────────────────


def test_create_returns_record(manager):
    record = manager.create(notes="test backup")
    assert record.backup_id
    assert record.checksum_sha256
    assert "jarvis.db" in record.contents
    assert record.notes == "test backup"


def test_create_writes_files(manager, tmp_dirs):
    backup_dir, _ = tmp_dirs
    record = manager.create()
    dest = backup_dir / record.backup_id
    assert (dest / "jarvis.db").exists()
    assert (dest / "metadata.json").exists()
    assert (dest / "checksum.sha256").exists()


def test_create_metadata_json(manager, tmp_dirs):
    backup_dir, _ = tmp_dirs
    record = manager.create(notes="meta test")
    meta_path = backup_dir / record.backup_id / "metadata.json"
    meta = json.loads(meta_path.read_text())
    assert meta["backup_id"] == record.backup_id
    assert meta["backup_format_version"] == BACKUP_FORMAT_VERSION
    assert meta["notes"] == "meta test"
    assert meta["checksum_sha256"] == record.checksum_sha256


def test_create_checksum_file(manager, tmp_dirs):
    backup_dir, _ = tmp_dirs
    record = manager.create()
    checksum_file = backup_dir / record.backup_id / "checksum.sha256"
    content = checksum_file.read_text()
    assert record.checksum_sha256 in content
    assert "jarvis.db" in content


def test_create_missing_db_raises(tmp_dirs):
    backup_dir, _ = tmp_dirs
    mgr = BackupManager(backup_dir=backup_dir, db_path=Path("/nonexistent/jarvis.db"))
    with pytest.raises(FileNotFoundError):
        mgr.create()


def test_list_backups_empty(manager):
    assert manager.list_backups() == []


def test_list_backups_sorted_newest_first(manager):
    r1 = manager.create(notes="first")
    r2 = manager.create(notes="second")
    records = manager.list_backups()
    assert len(records) == 2
    # newest first — r2 was created after r1
    ids = [r.backup_id for r in records]
    assert ids.index(r2.backup_id) <= ids.index(r1.backup_id)


def test_get_backup_found(manager):
    record = manager.create()
    found = manager.get_backup(record.backup_id)
    assert found is not None
    assert found.backup_id == record.backup_id


def test_get_backup_not_found(manager):
    assert manager.get_backup("nonexistent-id") is None


def test_verify_ok(manager):
    record = manager.create()
    ok, msg = manager.verify(record.backup_id)
    assert ok is True
    assert "OK" in msg


def test_verify_not_found(manager):
    ok, msg = manager.verify("no-such-id")
    assert ok is False
    assert "not found" in msg


def test_verify_corrupted(manager, tmp_dirs):
    backup_dir, _ = tmp_dirs
    record = manager.create()
    # Corrupt the backup DB
    db_file = backup_dir / record.backup_id / "jarvis.db"
    db_file.write_bytes(b"corrupted data")
    ok, msg = manager.verify(record.backup_id)
    assert ok is False
    assert "mismatch" in msg.lower()


def test_restore_overwrites_db(manager, tmp_dirs):
    backup_dir, db_path = tmp_dirs
    record = manager.create()
    original_checksum = _sha256(db_path)
    # Modify the live DB
    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO workspaces VALUES (1, 'modified')")
    conn.commit()
    conn.close()
    # Restore
    restored = manager.restore(record.backup_id)
    assert restored == db_path
    assert _sha256(db_path) == original_checksum


def test_restore_creates_safety_copy(manager, tmp_dirs):
    backup_dir, db_path = tmp_dirs
    record = manager.create()
    manager.restore(record.backup_id)
    safety_files = list(db_path.parent.glob("*.pre_restore_*.db"))
    assert len(safety_files) == 1


def test_restore_not_found_raises(manager):
    with pytest.raises(ValueError, match="not found"):
        manager.restore("no-such-id")


def test_restore_checksum_fail_raises(manager, tmp_dirs):
    backup_dir, _ = tmp_dirs
    record = manager.create()
    db_file = backup_dir / record.backup_id / "jarvis.db"
    db_file.write_bytes(b"bad")
    with pytest.raises(ValueError, match="integrity"):
        manager.restore(record.backup_id)


def test_restore_skip_verify(manager, tmp_dirs):
    backup_dir, db_path = tmp_dirs
    record = manager.create()
    db_file = backup_dir / record.backup_id / "jarvis.db"
    db_file.write_bytes(b"bad")
    # Should not raise when verify_first=False
    manager.restore(record.backup_id, verify_first=False)


def test_delete_removes_directory(manager, tmp_dirs):
    backup_dir, _ = tmp_dirs
    record = manager.create()
    dest = backup_dir / record.backup_id
    assert dest.exists()
    deleted = manager.delete(record.backup_id)
    assert deleted is True
    assert not dest.exists()


def test_delete_not_found_returns_false(manager):
    assert manager.delete("no-such-id") is False


def test_prune_removes_old_backups(manager):
    record = manager.create()
    # Prune with 0 days — everything is "old"
    deleted = manager.prune(retention_days=0)
    assert record.backup_id in deleted
    assert manager.list_backups() == []


def test_prune_keeps_recent_backups(manager):
    record = manager.create()
    deleted = manager.prune(retention_days=365)
    assert record.backup_id not in deleted
    assert len(manager.list_backups()) == 1


def test_list_ignores_non_backup_dirs(tmp_dirs):
    backup_dir, db_path = tmp_dirs
    # Create a directory without metadata.json
    (backup_dir / "not-a-backup").mkdir()
    mgr = BackupManager(backup_dir=backup_dir, db_path=db_path)
    mgr.create()
    records = mgr.list_backups()
    assert len(records) == 1


# ── RestoreDrill ──────────────────────────────────────────────────────────────


@pytest.fixture
def drill():
    return RestoreDrill()


def test_drill_passes_valid_db(tmp_dirs, drill):
    _, db_path = tmp_dirs
    result = drill.run(db_path, backup_id="test-id")
    assert result.passed is True
    assert "7/7" in result.summary


def test_drill_fails_missing_file(drill):
    result = drill.run(Path("/nonexistent/jarvis.db"), backup_id="x")
    assert result.passed is False
    check_names = [name for name, _, _ in result.checks]
    assert "file_exists" in check_names
    file_check = next(ok for name, ok, _ in result.checks if name == "file_exists")
    assert file_check is False


def test_drill_fails_corrupted_db(tmp_path, drill):
    bad_path = tmp_path / "bad.db"
    bad_path.write_bytes(b"not a sqlite database")
    result = drill.run(bad_path, backup_id="bad")
    assert result.passed is False
    db_check = next(ok for name, ok, _ in result.checks if name == "database_opens")
    assert db_check is False


def test_drill_missing_tables(drill, tmp_path):
    path = tmp_path / "partial.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE conversations (id INTEGER PRIMARY KEY)")
    conn.close()
    result = drill.run(path, backup_id="partial")
    assert result.passed is False
    table_check = next(ok for name, ok, _ in result.checks if name == "required_tables_present")
    assert table_check is False


def test_drill_no_alembic_table(drill, tmp_path):
    path = tmp_path / "no_alembic.db"
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE conversations (id INTEGER PRIMARY KEY);
        CREATE TABLE messages (id INTEGER PRIMARY KEY);
        CREATE TABLE memories (id INTEGER PRIMARY KEY);
        CREATE TABLE documents (id INTEGER PRIMARY KEY);
        CREATE TABLE tool_executions (id INTEGER PRIMARY KEY);
        CREATE TABLE automation_jobs (id INTEGER PRIMARY KEY);
    """)
    conn.close()
    result = drill.run(path, backup_id="no-alembic")
    # Should still pass — pre-migration DB is acceptable
    schema_check = next(ok for name, ok, _ in result.checks if name == "schema_version_readable")
    assert schema_check is True


def test_drill_summary_format(tmp_dirs, drill):
    _, db_path = tmp_dirs
    result = drill.run(db_path)
    assert "/" in result.summary
    passed_count = int(result.summary.split("/")[0])
    total_count = int(result.summary.split("/")[1].split()[0])
    assert passed_count == total_count


# ── REST API ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_create_backup(test_client, tmp_path, monkeypatch):
    """POST /api/v1/backup creates a backup and returns 201."""
    import app.api.routes.backup as backup_module

    db_path = tmp_path / "jarvis.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE alembic_version (version_num TEXT NOT NULL);
        INSERT INTO alembic_version VALUES ('v1');
        CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE conversations (id INTEGER PRIMARY KEY);
        CREATE TABLE messages (id INTEGER PRIMARY KEY);
        CREATE TABLE memories (id INTEGER PRIMARY KEY);
        CREATE TABLE documents (id INTEGER PRIMARY KEY);
        CREATE TABLE tool_executions (id INTEGER PRIMARY KEY);
        CREATE TABLE automation_jobs (id INTEGER PRIMARY KEY);
    """)
    conn.close()

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    def fake_manager():
        return BackupManager(backup_dir=backup_dir, db_path=db_path)

    monkeypatch.setattr(backup_module, "_get_manager", fake_manager)

    resp = await test_client.post("/api/v1/backup")
    assert resp.status_code == 201
    data = resp.json()
    assert "backup_id" in data
    assert data["checksum_sha256"]


@pytest.mark.asyncio
async def test_api_list_backups_empty(test_client, tmp_path, monkeypatch):
    import app.api.routes.backup as backup_module

    db_path = tmp_path / "jarvis.db"
    db_path.write_bytes(b"")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    monkeypatch.setattr(
        backup_module, "_get_manager",
        lambda: BackupManager(backup_dir=backup_dir, db_path=db_path),
    )

    resp = await test_client.get("/api/v1/backups")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_api_get_backup_not_found(test_client, tmp_path, monkeypatch):
    import app.api.routes.backup as backup_module

    db_path = tmp_path / "jarvis.db"
    db_path.write_bytes(b"")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    monkeypatch.setattr(
        backup_module, "_get_manager",
        lambda: BackupManager(backup_dir=backup_dir, db_path=db_path),
    )

    resp = await test_client.get("/api/v1/backups/no-such-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_verify_not_found(test_client, tmp_path, monkeypatch):
    import app.api.routes.backup as backup_module

    db_path = tmp_path / "jarvis.db"
    db_path.write_bytes(b"")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    monkeypatch.setattr(
        backup_module, "_get_manager",
        lambda: BackupManager(backup_dir=backup_dir, db_path=db_path),
    )

    resp = await test_client.post("/api/v1/backups/no-such-id/verify")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_restore_not_found(test_client, tmp_path, monkeypatch):
    import app.api.routes.backup as backup_module

    db_path = tmp_path / "jarvis.db"
    db_path.write_bytes(b"")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    monkeypatch.setattr(
        backup_module, "_get_manager",
        lambda: BackupManager(backup_dir=backup_dir, db_path=db_path),
    )

    resp = await test_client.post("/api/v1/backups/no-such-id/restore")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_drill_not_found(test_client, tmp_path, monkeypatch):
    import app.api.routes.backup as backup_module

    db_path = tmp_path / "jarvis.db"
    db_path.write_bytes(b"")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    monkeypatch.setattr(
        backup_module, "_get_manager",
        lambda: BackupManager(backup_dir=backup_dir, db_path=db_path),
    )

    resp = await test_client.post("/api/v1/backups/no-such-id/drill")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_delete_not_found(test_client, tmp_path, monkeypatch):
    import app.api.routes.backup as backup_module

    db_path = tmp_path / "jarvis.db"
    db_path.write_bytes(b"")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    monkeypatch.setattr(
        backup_module, "_get_manager",
        lambda: BackupManager(backup_dir=backup_dir, db_path=db_path),
    )

    resp = await test_client.delete("/api/v1/backups/no-such-id")
    assert resp.status_code == 404

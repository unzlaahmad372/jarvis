"""Unit tests for InboxWatcher — Section 98."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from app.knowledge.watcher import InboxWatcher, _is_temp_file, _quick_hash

# ── _is_temp_file ─────────────────────────────────────────────────────────────


def test_temp_file_dot_prefix(tmp_path: Path) -> None:
    assert _is_temp_file(tmp_path / ".hidden.txt") is True


def test_temp_file_tilde_prefix(tmp_path: Path) -> None:
    assert _is_temp_file(tmp_path / "~lockfile") is True


def test_temp_file_tmp_suffix(tmp_path: Path) -> None:
    assert _is_temp_file(tmp_path / "upload.tmp") is True


def test_temp_file_part_suffix(tmp_path: Path) -> None:
    assert _is_temp_file(tmp_path / "download.part") is True


def test_temp_file_crdownload_suffix(tmp_path: Path) -> None:
    assert _is_temp_file(tmp_path / "file.crdownload") is True


def test_not_temp_file(tmp_path: Path) -> None:
    assert _is_temp_file(tmp_path / "report.pdf") is False
    assert _is_temp_file(tmp_path / "notes.md") is False


# ── _quick_hash ───────────────────────────────────────────────────────────────


def test_quick_hash_deterministic(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("hello world")
    h1 = _quick_hash(f)
    h2 = _quick_hash(f)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_quick_hash_different_content(tmp_path: Path) -> None:
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("aaa")
    f2.write_text("bbb")
    assert _quick_hash(f1) != _quick_hash(f2)


def test_quick_hash_missing_file(tmp_path: Path) -> None:
    result = _quick_hash(tmp_path / "nonexistent.txt")
    assert result == ""


# ── InboxWatcher scan ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_watcher_detects_new_file(tmp_path: Path) -> None:
    watcher = InboxWatcher(tmp_path)
    f = tmp_path / "doc.txt"
    f.write_text("content")
    # Backdate mtime so file appears stable
    old_time = time.time() - 10
    import os
    os.utime(f, (old_time, old_time))

    await watcher._scan()
    assert not watcher.queue.empty()
    detected = watcher.queue.get_nowait()
    assert detected == f.resolve()


@pytest.mark.asyncio
async def test_watcher_ignores_unsupported_extension(tmp_path: Path) -> None:
    watcher = InboxWatcher(tmp_path)
    f = tmp_path / "image.png"
    f.write_bytes(b"\x89PNG")
    old_time = time.time() - 10
    import os
    os.utime(f, (old_time, old_time))

    await watcher._scan()
    assert watcher.queue.empty()


@pytest.mark.asyncio
async def test_watcher_ignores_temp_files(tmp_path: Path) -> None:
    watcher = InboxWatcher(tmp_path)
    f = tmp_path / "upload.tmp"
    f.write_text("partial")
    old_time = time.time() - 10
    import os
    os.utime(f, (old_time, old_time))

    await watcher._scan()
    assert watcher.queue.empty()


@pytest.mark.asyncio
async def test_watcher_skips_unstable_file(tmp_path: Path) -> None:
    """File modified very recently should be skipped (not yet stable)."""
    watcher = InboxWatcher(tmp_path)
    f = tmp_path / "doc.md"
    f.write_text("content")
    # mtime is now — file is not stable yet

    await watcher._scan()
    assert watcher.queue.empty()


@pytest.mark.asyncio
async def test_watcher_deduplicates_unchanged_file(tmp_path: Path) -> None:
    watcher = InboxWatcher(tmp_path)
    f = tmp_path / "doc.txt"
    f.write_text("content")
    old_time = time.time() - 10
    import os
    os.utime(f, (old_time, old_time))

    await watcher._scan()
    assert watcher.queue.qsize() == 1

    # Second scan — same mtime, same hash — should not re-enqueue
    await watcher._scan()
    assert watcher.queue.qsize() == 1  # still 1, not 2


@pytest.mark.asyncio
async def test_watcher_re_enqueues_changed_file(tmp_path: Path) -> None:
    watcher = InboxWatcher(tmp_path)
    f = tmp_path / "doc.txt"
    f.write_text("version 1")
    old_time = time.time() - 10
    import os
    os.utime(f, (old_time, old_time))

    await watcher._scan()
    assert watcher.queue.qsize() == 1
    watcher.queue.get_nowait()  # drain

    # Modify file content and backdate again
    f.write_text("version 2")
    newer_time = time.time() - 5
    os.utime(f, (newer_time, newer_time))

    await watcher._scan()
    assert watcher.queue.qsize() == 1  # re-enqueued


@pytest.mark.asyncio
async def test_watcher_ignores_missing_inbox(tmp_path: Path) -> None:
    """Watcher should not crash if inbox dir does not exist yet."""
    watcher = InboxWatcher(tmp_path / "nonexistent")
    await watcher._scan()  # should not raise
    assert watcher.queue.empty()


@pytest.mark.asyncio
async def test_watcher_start_stop() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        watcher = InboxWatcher(Path(d))
        watcher.start()
        assert watcher._running is True
        await asyncio.sleep(0.05)
        await watcher.stop()
        assert watcher._running is False


@pytest.mark.asyncio
async def test_watcher_start_idempotent() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        watcher = InboxWatcher(Path(d))
        watcher.start()
        task1 = watcher._task
        watcher.start()  # second call should be no-op
        assert watcher._task is task1
        await watcher.stop()

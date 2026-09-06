"""Inbox watcher — Section 98 / 123.2.

Monitors the configured inbox directory for new or changed files and
schedules them through the canonical ingestion pipeline.

Enabled only when JARVIS_INBOX_WATCHER_ENABLED=true.

Security boundary:
  - Only the configured inbox root is watched; no arbitrary crawling.
  - Files are still treated as untrusted content (prompt-injection protections
    remain in the ingestion pipeline).
  - Temporary/partial files are ignored until stable.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.knowledge.parser import SUPPORTED_EXTENSIONS

logger = get_logger(__name__)

# Seconds a file must be unchanged before we consider it stable
_STABILITY_SECONDS = 2.0
# Polling interval when watchdog is unavailable
_POLL_INTERVAL = 5.0


class InboxWatcher:
    """Watches an inbox directory and enqueues stable new/changed files.

    Uses watchdog when available; falls back to polling otherwise.
    The caller is responsible for draining the queue and calling ingest.
    """

    def __init__(self, inbox_dir: Path) -> None:
        self._inbox = inbox_dir.resolve()
        self._queue: asyncio.Queue[Path] = asyncio.Queue()
        self._seen: dict[Path, tuple[float, str]] = {}  # path -> (mtime, hash)
        self._running = False
        self._task: asyncio.Task[None] | None = None

    @property
    def queue(self) -> asyncio.Queue[Path]:
        return self._queue

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name="inbox_watcher")
        logger.info("inbox_watcher_started", inbox=str(self._inbox))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("inbox_watcher_stopped")

    # ------------------------------------------------------------------
    # Internal polling loop (watchdog integration can replace this later)
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        while self._running:
            try:
                await self._scan()
            except Exception:
                logger.exception("inbox_watcher_scan_error")
            await asyncio.sleep(_POLL_INTERVAL)

    async def _scan(self) -> None:
        if not self._inbox.is_dir():
            return

        for path in self._inbox.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if _is_temp_file(path):
                continue

            try:
                stat = path.stat()
            except OSError:
                continue

            mtime = stat.st_mtime
            age = time.time() - mtime
            if age < _STABILITY_SECONDS:
                # File still being written — skip this cycle
                continue

            prev = self._seen.get(path)
            if prev is not None:
                prev_mtime, prev_hash = prev
                if mtime == prev_mtime:
                    continue  # unchanged since last scan
                # mtime changed — recheck hash
                current_hash = _quick_hash(path)
                if current_hash == prev_hash:
                    self._seen[path] = (mtime, current_hash)
                    continue  # content identical despite mtime change

            current_hash = _quick_hash(path)
            self._seen[path] = (mtime, current_hash)
            logger.info("inbox_file_detected", path=str(path))
            await self._queue.put(path)


def _is_temp_file(path: Path) -> bool:
    """Return True for partial/temporary files that should be ignored."""
    name = path.name
    return (
        name.startswith(".")
        or name.startswith("~")
        or name.endswith(".tmp")
        or name.endswith(".part")
        or name.endswith(".crdownload")
    )


def _quick_hash(path: Path) -> str:
    """SHA-256 of first 64 KB — fast stability check, not a full integrity hash."""
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            h.update(f.read(65536))
    except OSError:
        return ""
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Application-level watcher runner — wired into lifespan
# ---------------------------------------------------------------------------

async def run_inbox_watcher(
    inbox_dir: Path,
    embedding_provider: Any,
    vector_store: Any,
    session_factory: Any,
    chunk_size_tokens: int = 512,
    overlap_tokens: int = 64,
) -> None:
    """Start the watcher and drain its queue, calling ingest for each file.

    Designed to run as a background asyncio task.
    """
    from app.knowledge.ingestion import ingest_document

    watcher = InboxWatcher(inbox_dir)
    watcher.start()

    try:
        while True:
            path: Path = await watcher.queue.get()
            logger.info("inbox_ingesting", path=str(path))
            try:
                async with session_factory() as session:
                    await ingest_document(
                        path=path,
                        session=session,
                        embedding_provider=embedding_provider,
                        vector_store=vector_store,
                        chunk_size_tokens=chunk_size_tokens,
                        overlap_tokens=overlap_tokens,
                    )
                logger.info("inbox_ingested", path=str(path))
            except Exception:
                logger.exception("inbox_ingest_failed", path=str(path))
            finally:
                watcher.queue.task_done()
    except asyncio.CancelledError:
        await watcher.stop()
        raise

"""Filesystem read tools — list_directory, read_file, search_files, file_metadata, open_file.

All paths are validated through FileAccessRegistry before any filesystem access.
"""

from __future__ import annotations

import json
import platform
import subprocess
from typing import Any

from app.tools.base import RiskLevel, Tool, ToolResult
from app.tools.filesystem.access import FileAccessRegistry, PathNotAllowedError

_MAX_READ_BYTES = 512 * 1024  # 512 KB hard cap for read_file
_MAX_SEARCH_RESULTS = 50


class ListDirectoryTool(Tool):
    def __init__(self, registry: FileAccessRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "list_directory"

    @property
    def description(self) -> str:
        return "List files and subdirectories in an allowed directory."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "path": {"type": "string", "description": "Directory path to list"},
        }

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        raw_path = parameters.get("path", "")
        try:
            resolved = self._registry.validate(raw_path)
        except PathNotAllowedError as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))

        if not resolved.is_dir():
            return ToolResult(
                tool_name=self.name, success=False, output="",
                error=f"Not a directory: {resolved}",
            )

        entries = []
        for item in sorted(resolved.iterdir()):
            kind = "dir" if item.is_dir() else "file"
            size = item.stat().st_size if item.is_file() else 0
            entries.append({"name": item.name, "type": kind, "size_bytes": size})

        return ToolResult(tool_name=self.name, success=True, output=json.dumps(entries))


class ReadFileTool(Tool):
    def __init__(self, registry: FileAccessRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the text content of an allowed file."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "path": {"type": "string", "description": "File path to read"},
        }

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        raw_path = parameters.get("path", "")
        try:
            resolved = self._registry.validate(raw_path)
        except PathNotAllowedError as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))

        if not resolved.is_file():
            return ToolResult(
                tool_name=self.name, success=False, output="",
                error=f"Not a file: {resolved}",
            )

        size = resolved.stat().st_size
        truncated = size > _MAX_READ_BYTES
        content = resolved.read_bytes()[:_MAX_READ_BYTES].decode("utf-8", errors="replace")
        return ToolResult(tool_name=self.name, success=True, output=content, truncated=truncated)


class SearchFilesTool(Tool):
    def __init__(self, registry: FileAccessRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "search_files"

    @property
    def description(self) -> str:
        return "Search for files by name pattern within an allowed directory."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "path": {"type": "string", "description": "Root directory to search"},
            "pattern": {"type": "string", "description": "Glob pattern, e.g. '*.pdf'"},
        }

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        raw_path = parameters.get("path", "")
        pattern = parameters.get("pattern", "*")
        try:
            resolved = self._registry.validate(raw_path)
        except PathNotAllowedError as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))

        if not resolved.is_dir():
            return ToolResult(
                tool_name=self.name, success=False, output="",
                error=f"Not a directory: {resolved}",
            )

        matches = []
        for match in resolved.rglob(pattern):
            if not self._registry.is_allowed(match):
                continue
            matches.append({"path": str(match), "type": "dir" if match.is_dir() else "file"})
            if len(matches) >= _MAX_SEARCH_RESULTS:
                break

        return ToolResult(tool_name=self.name, success=True, output=json.dumps(matches))


class FileMetadataTool(Tool):
    def __init__(self, registry: FileAccessRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "file_metadata"

    @property
    def description(self) -> str:
        return "Get metadata (size, modified time, type) for an allowed file or directory."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "path": {"type": "string", "description": "Path to inspect"},
        }

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        raw_path = parameters.get("path", "")
        try:
            resolved = self._registry.validate(raw_path)
        except PathNotAllowedError as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))

        stat = resolved.stat()
        meta = {
            "path": str(resolved),
            "type": "dir" if resolved.is_dir() else "file",
            "size_bytes": stat.st_size,
            "modified_at": stat.st_mtime,
            "exists": resolved.exists(),
        }
        return ToolResult(tool_name=self.name, success=True, output=json.dumps(meta))


class OpenFileTool(Tool):
    """Open a file with the OS default application.

    The path is validated against the FileAccessRegistry before any OS call.
    Opening is distinct from reading — the file content is never sent to the LLM.
    If multiple files match a pattern, candidates are returned instead of
    opening an arbitrary one.
    """

    def __init__(self, registry: FileAccessRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "open_file"

    @property
    def description(self) -> str:
        return (
            "Open a file with the operating system's default application. "
            "The path must be inside an allowed root. "
            "If a glob pattern matches multiple files, candidates are returned instead."
        )

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW_RISK

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "path": {"type": "string", "description": "Exact file path or glob pattern to open"},
        }

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        raw_path = parameters.get("path", "")

        # ── Glob resolution: if pattern, collect candidates ───────────────────
        from pathlib import Path
        p = Path(raw_path)
        parent = p.parent
        name_pattern = p.name

        # Try to validate the parent directory first
        try:
            resolved_parent = self._registry.validate(str(parent))
        except PathNotAllowedError as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))

        if any(c in name_pattern for c in ("*", "?", "[")):
            # Glob — return candidates, never open ambiguously
            candidates = [
                str(m) for m in resolved_parent.glob(name_pattern)
                if m.is_file() and self._registry.is_allowed(m)
            ]
            if not candidates:
                return ToolResult(
                    tool_name=self.name, success=False, output="",
                    error=f"No files matched pattern '{raw_path}' in allowed roots.",
                )
            if len(candidates) == 1:
                raw_path = candidates[0]
            else:
                return ToolResult(
                    tool_name=self.name, success=True,
                    output=json.dumps({"candidates": candidates}),
                )

        # ── Validate exact path ───────────────────────────────────────────────
        try:
            resolved = self._registry.validate(raw_path)
        except PathNotAllowedError as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))

        if not resolved.is_file():
            return ToolResult(
                tool_name=self.name, success=False, output="",
                error=f"Not a file: {resolved}",
            )

        # ── Open with OS default application ──────────────────────────────────
        try:
            system = platform.system()
            if system == "Windows":
                subprocess.Popen(["cmd", "/c", "start", "", str(resolved)])  # noqa: S603 S607
            elif system == "Darwin":
                subprocess.Popen(["open", str(resolved)])  # noqa: S603 S607
            else:
                subprocess.Popen(["xdg-open", str(resolved)])  # noqa: S603 S607
        except OSError as exc:
            return ToolResult(
                tool_name=self.name, success=False, output="",
                error=f"OS could not open file: {exc}",
            )

        return ToolResult(
            tool_name=self.name, success=True,
            output=json.dumps({"opened": str(resolved)}),
        )

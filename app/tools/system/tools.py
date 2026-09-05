"""System information tools — read-only, no shell exposure.

Uses the 'psutil' library for cross-platform system metrics.
psutil is added as an optional dependency; tools degrade gracefully if absent.
"""

from __future__ import annotations

import json
import platform
import sys
from typing import Any

from app.tools.base import RiskLevel, Tool, ToolResult


class SystemInfoTool(Tool):
    @property
    def name(self) -> str:
        return "system_info"

    @property
    def description(self) -> str:
        return "Return basic system information: OS, Python version, platform."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {}

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        info = {
            "os": platform.system(),
            "os_version": platform.version(),
            "machine": platform.machine(),
            "python_version": sys.version,
            "node": platform.node(),
        }
        return ToolResult(tool_name=self.name, success=True, output=json.dumps(info))


class DiskUsageTool(Tool):
    @property
    def name(self) -> str:
        return "disk_usage"

    @property
    def description(self) -> str:
        return "Return disk usage for a given path (defaults to current directory)."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "path": {
                "type": "string",
                "description": "Path to check disk usage for",
                "default": ".",
            },
        }

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        path = parameters.get("path", ".")
        try:
            import shutil
            total, used, free = shutil.disk_usage(path)
            info = {
                "path": path,
                "total_bytes": total,
                "used_bytes": used,
                "free_bytes": free,
                "used_pct": round(used / total * 100, 1) if total else 0,
            }
            return ToolResult(tool_name=self.name, success=True, output=json.dumps(info))
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))

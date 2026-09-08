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


class CpuUsageTool(Tool):
    @property
    def name(self) -> str:
        return "cpu_usage"

    @property
    def description(self) -> str:
        return "Return current CPU usage percentage (requires psutil)."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {}

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        try:
            import psutil
            per_cpu = psutil.cpu_percent(interval=0.2, percpu=True)
            info = {
                "cpu_percent_total": round(sum(per_cpu) / len(per_cpu), 1),
                "cpu_percent_per_core": per_cpu,
                "cpu_count": psutil.cpu_count(),
            }
            return ToolResult(tool_name=self.name, success=True, output=json.dumps(info))
        except ImportError:
            return ToolResult(
                tool_name=self.name, success=False, output="",
                error="psutil is not installed. Run: pip install psutil",
            )
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))


class MemoryUsageTool(Tool):
    @property
    def name(self) -> str:
        return "memory_usage"

    @property
    def description(self) -> str:
        return "Return current RAM usage (requires psutil)."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {}

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        try:
            import psutil
            vm = psutil.virtual_memory()
            info = {
                "total_bytes": vm.total,
                "available_bytes": vm.available,
                "used_bytes": vm.used,
                "used_pct": vm.percent,
                "total_gb": round(vm.total / 1024 ** 3, 2),
                "available_gb": round(vm.available / 1024 ** 3, 2),
            }
            return ToolResult(tool_name=self.name, success=True, output=json.dumps(info))
        except ImportError:
            return ToolResult(
                tool_name=self.name, success=False, output="",
                error="psutil is not installed. Run: pip install psutil",
            )
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))


class ProcessListTool(Tool):
    @property
    def name(self) -> str:
        return "process_list"

    @property
    def description(self) -> str:
        return "Return the top processes by CPU usage (requires psutil)."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "limit": {
                "type": "integer",
                "description": "Number of top processes to return (default 10)",
                "default": 10,
            }
        }

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        try:
            import psutil
            limit = int(parameters.get("limit", 10))
            procs = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                try:
                    procs.append(p.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
            return ToolResult(
                tool_name=self.name, success=True,
                output=json.dumps(procs[:limit]),
            )
        except ImportError:
            return ToolResult(
                tool_name=self.name, success=False, output="",
                error="psutil is not installed. Run: pip install psutil",
            )
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))


class OpenApplicationTool(Tool):
    """Open an application by name using the OS default launcher.

    Uses the OS shell to open an application by name or path.
    Risk level is LOW_RISK — requires confirmation in default config.
    Never executes arbitrary shell commands; only opens named applications.
    """

    # Built-in safe application names (lowercase).
    _BUILTIN_SAFE_NAMES: set[str] = {
        "vscode", "code", "notepad", "notepad++", "explorer",
        "terminal", "cmd", "powershell", "wt",  # Windows Terminal
        "chrome", "firefox", "edge", "brave",
        "slack", "teams", "zoom", "discord",
        "excel", "word", "outlook", "onenote",
        "calculator", "paint", "mspaint",
    }

    def __init__(self, extra_apps: set[str] | None = None) -> None:
        self._safe_names = self._BUILTIN_SAFE_NAMES | (extra_apps or set())

    @property
    def name(self) -> str:
        return "open_application"

    @property
    def description(self) -> str:
        return (
            "Open an application by name (e.g. 'vscode', 'chrome', 'notepad'). "
            "Only known safe application names are permitted."
        )

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW_RISK

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "app_name": {
                "type": "string",
                "description": "Application name to open (e.g. 'vscode', 'chrome')",
            }
        }

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        import subprocess
        app_name = str(parameters.get("app_name", "")).strip().lower()
        if not app_name:
            return ToolResult(
                tool_name=self.name, success=False, output="",
                error="app_name is required",
            )
        if app_name not in self._safe_names:
            return ToolResult(
                tool_name=self.name, success=False, output="",
                error=(
                    f"'{app_name}' is not in the permitted application list. "
                    f"Allowed: {sorted(self._safe_names)}"
                ),
            )
        try:
            if platform.system() == "Windows":
                subprocess.Popen(["cmd", "/c", "start", app_name], shell=False)  # noqa: S603
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", "-a", app_name])  # noqa: S603
            else:
                subprocess.Popen([app_name])  # noqa: S603
            return ToolResult(
                tool_name=self.name, success=True,
                output=json.dumps({"launched": app_name}),
            )
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))

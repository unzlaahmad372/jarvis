"""Tool registration — wires all built-in tools into the ToolRegistry at startup."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.tools.filesystem.access import FileAccessRegistry
from app.tools.filesystem.tools import (
    FileMetadataTool,
    ListDirectoryTool,
    OpenFileTool,
    ReadFileTool,
    SearchFilesTool,
)
from app.tools.registry import get_registry, reset_registry
from app.tools.system.tools import (
    CpuUsageTool,
    DiskUsageTool,
    MemoryUsageTool,
    OpenApplicationTool,
    ProcessListTool,
    SystemInfoTool,
)


def register_all_tools(settings: Settings) -> None:
    """Register all built-in tools. Called once at startup."""
    reset_registry()
    registry = get_registry()

    far = FileAccessRegistry()
    far.add_root("data", settings.data_dir.resolve())
    for i, root_path in enumerate(settings.extra_file_roots_list):
        far.add_root(f"extra_{i}", Path(root_path))

    registry.register(ListDirectoryTool(far))
    registry.register(ReadFileTool(far))
    registry.register(SearchFilesTool(far))
    registry.register(FileMetadataTool(far))
    registry.register(OpenFileTool(far))
    registry.register(SystemInfoTool())
    registry.register(DiskUsageTool())
    registry.register(CpuUsageTool())
    registry.register(MemoryUsageTool())
    registry.register(ProcessListTool())
    registry.register(OpenApplicationTool(extra_apps=settings.allowed_apps_set))

    from app.tools.memory.tools import MemorySearchTool
    registry.register(MemorySearchTool())

    if settings.enable_vision:
        from app.tools.vision.tools import VisionTool
        registry.register(VisionTool())

    if settings.enable_web_search:
        from app.tools.web.tools import WebSearchTool
        registry.register(WebSearchTool())

    if settings.enable_calendar and settings.calendar_ics_path:
        from app.tools.calendar.tools import GetTodaysEventsTool, ListCalendarEventsTool
        registry.register(ListCalendarEventsTool(settings.calendar_ics_path))
        registry.register(GetTodaysEventsTool(settings.calendar_ics_path))

    if settings.enable_kubernetes:
        from app.tools.kubernetes.client import RealKubernetesClient
        from app.tools.kubernetes.tools import (
            ClusterHealthTool,
            GetPodLogsTool,
            ListContextsTool,
            ListDeploymentsTool,
            ListNamespacesTool,
            ListPodsTool,
        )
        k8s_client = RealKubernetesClient()
        registry.register(ListContextsTool(k8s_client, settings))
        registry.register(ListNamespacesTool(k8s_client, settings))
        registry.register(ListPodsTool(k8s_client, settings))
        registry.register(GetPodLogsTool(k8s_client, settings))
        registry.register(ListDeploymentsTool(k8s_client, settings))
        registry.register(ClusterHealthTool(k8s_client, settings))

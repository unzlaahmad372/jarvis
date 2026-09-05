"""Read-only Kubernetes tools — Phase 6.

All tools are READ_ONLY. Protected contexts (configurable) are flagged
in results but still readable — mutations are never permitted in Phase 6.
Fan-out is bounded by k8s_fan_out_limit in Settings.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import Settings
from app.tools.base import RiskLevel, Tool, ToolResult
from app.tools.kubernetes.client import KubernetesClient


def _is_protected(context: str, settings: Settings) -> bool:
    return context in settings.k8s_protected_contexts_list


class ListContextsTool(Tool):
    def __init__(self, client: KubernetesClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    @property
    def name(self) -> str:
        return "k8s_list_contexts"

    @property
    def description(self) -> str:
        return "List all available Kubernetes contexts from kubeconfig."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {}

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        try:
            contexts = await self._client.list_contexts()
            current = await self._client.current_context()
            data = [
                {
                    "name": c.name,
                    "cluster": c.cluster,
                    "namespace": c.namespace,
                    "current": c.is_current,
                    "protected": _is_protected(c.name, self._settings),
                }
                for c in contexts
            ]
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=json.dumps({"current_context": current, "contexts": data}, indent=2),
            )
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))


class ListNamespacesTool(Tool):
    def __init__(self, client: KubernetesClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    @property
    def name(self) -> str:
        return "k8s_list_namespaces"

    @property
    def description(self) -> str:
        return "List namespaces in a Kubernetes context."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {"context": {"type": "string", "description": "Kubernetes context name"}}

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        context = str(parameters.get("context", ""))
        if not context:
            return ToolResult(
                tool_name=self.name, success=False, output="", error="context is required"
            )
        try:
            namespaces = await self._client.list_namespaces(context)
            data = [{"name": ns.name, "status": ns.status} for ns in namespaces]
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=json.dumps(
                    {
                        "context": context,
                        "protected": _is_protected(context, self._settings),
                        "namespaces": data,
                    },
                    indent=2,
                ),
            )
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))


class ListPodsTool(Tool):
    def __init__(self, client: KubernetesClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    @property
    def name(self) -> str:
        return "k8s_list_pods"

    @property
    def description(self) -> str:
        return "List pods in a Kubernetes namespace."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "context": {"type": "string"},
            "namespace": {"type": "string", "default": "default"},
        }

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        context = str(parameters.get("context", ""))
        namespace = str(parameters.get("namespace", "default"))
        if not context:
            return ToolResult(
                tool_name=self.name, success=False, output="", error="context is required"
            )
        try:
            pods = await self._client.list_pods(context, namespace)
            data = [
                {
                    "name": p.name,
                    "status": p.status,
                    "ready": p.ready,
                    "restarts": p.restarts,
                    "age": p.age,
                    "node": p.node,
                }
                for p in pods
            ]
            unhealthy = [
                p for p in data
                if p["status"] not in ("Running", "Succeeded", "Completed")
            ]
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=json.dumps(
                    {
                        "context": context,
                        "namespace": namespace,
                        "protected": _is_protected(context, self._settings),
                        "pod_count": len(data),
                        "unhealthy_count": len(unhealthy),
                        "pods": data,
                    },
                    indent=2,
                ),
            )
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))


class GetPodLogsTool(Tool):
    def __init__(self, client: KubernetesClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    @property
    def name(self) -> str:
        return "k8s_get_pod_logs"

    @property
    def description(self) -> str:
        return "Retrieve recent log lines from a Kubernetes pod."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "context": {"type": "string"},
            "namespace": {"type": "string", "default": "default"},
            "pod_name": {"type": "string"},
            "tail_lines": {"type": "integer", "default": 50},
        }

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        context = str(parameters.get("context", ""))
        namespace = str(parameters.get("namespace", "default"))
        pod_name = str(parameters.get("pod_name", ""))
        tail_lines = min(int(parameters.get("tail_lines", 50)), self._settings.k8s_max_log_lines)
        if not context or not pod_name:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error="context and pod_name are required",
            )
        try:
            logs = await self._client.get_pod_logs(context, namespace, pod_name, tail_lines)
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=json.dumps(
                    {
                        "context": context,
                        "namespace": namespace,
                        "pod": pod_name,
                        "tail_lines": tail_lines,
                        "logs": logs,
                    },
                    indent=2,
                ),
            )
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))


class ListDeploymentsTool(Tool):
    def __init__(self, client: KubernetesClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    @property
    def name(self) -> str:
        return "k8s_list_deployments"

    @property
    def description(self) -> str:
        return "List deployments in a Kubernetes namespace."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "context": {"type": "string"},
            "namespace": {"type": "string", "default": "default"},
        }

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        context = str(parameters.get("context", ""))
        namespace = str(parameters.get("namespace", "default"))
        if not context:
            return ToolResult(
                tool_name=self.name, success=False, output="", error="context is required"
            )
        try:
            deployments = await self._client.list_deployments(context, namespace)
            data = [
                {
                    "name": d.name,
                    "ready": d.ready,
                    "up_to_date": d.up_to_date,
                    "available": d.available,
                    "age": d.age,
                }
                for d in deployments
            ]
            degraded = [
                d for d in data
                if str(d["ready"]).split("/")[0] != str(d["ready"]).split("/")[-1]
            ]
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=json.dumps(
                    {
                        "context": context,
                        "namespace": namespace,
                        "protected": _is_protected(context, self._settings),
                        "deployment_count": len(data),
                        "degraded_count": len(degraded),
                        "deployments": data,
                    },
                    indent=2,
                ),
            )
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))


class ClusterHealthTool(Tool):
    def __init__(self, client: KubernetesClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    @property
    def name(self) -> str:
        return "k8s_cluster_health"

    @property
    def description(self) -> str:
        return "Get a health summary for a Kubernetes cluster context."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {"context": {"type": "string"}}

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        context = str(parameters.get("context", ""))
        if not context:
            return ToolResult(
                tool_name=self.name, success=False, output="", error="context is required"
            )
        try:
            health = await self._client.cluster_health(context)
            status = "HEALTHY" if health.reachable and health.failed_pods == 0 else "DEGRADED"
            if not health.reachable:
                status = "UNREACHABLE"
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=json.dumps(
                    {
                        "context": context,
                        "protected": _is_protected(context, self._settings),
                        "status": status,
                        "reachable": health.reachable,
                        "nodes": {"total": health.node_count, "ready": health.ready_nodes},
                        "pods": {
                            "total": health.total_pods,
                            "running": health.running_pods,
                            "failed": health.failed_pods,
                        },
                        "error": health.error,
                    },
                    indent=2,
                ),
            )
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))

"""Kubernetes client abstraction.

KubernetesClient is the interface all k8s tools use.
RealKubernetesClient wraps the official kubernetes Python SDK.
FakeKubernetesClient is used in tests — no real cluster required.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class K8sContext:
    name: str
    cluster: str
    namespace: str = "default"
    is_current: bool = False


@dataclass
class K8sNamespace:
    name: str
    status: str = "Active"


@dataclass
class K8sPod:
    name: str
    namespace: str
    status: str
    ready: str  # e.g. "2/2"
    restarts: int
    age: str
    node: str = ""


@dataclass
class K8sDeployment:
    name: str
    namespace: str
    ready: str  # e.g. "3/3"
    up_to_date: int
    available: int
    age: str


@dataclass
class K8sClusterHealth:
    context: str
    reachable: bool
    node_count: int
    ready_nodes: int
    total_pods: int
    running_pods: int
    failed_pods: int
    error: str | None = None


class KubernetesClient(ABC):
    """Abstract interface for all Kubernetes operations."""

    @abstractmethod
    async def list_contexts(self) -> list[K8sContext]: ...

    @abstractmethod
    async def current_context(self) -> str | None: ...

    @abstractmethod
    async def list_namespaces(self, context: str) -> list[K8sNamespace]: ...

    @abstractmethod
    async def list_pods(self, context: str, namespace: str = "default") -> list[K8sPod]: ...

    @abstractmethod
    async def get_pod_logs(
        self, context: str, namespace: str, pod_name: str, tail_lines: int = 100
    ) -> str: ...

    @abstractmethod
    async def list_deployments(
        self, context: str, namespace: str = "default"
    ) -> list[K8sDeployment]: ...

    @abstractmethod
    async def cluster_health(self, context: str) -> K8sClusterHealth: ...


class FakeKubernetesClient(KubernetesClient):
    """Deterministic fake for tests — no real cluster required."""

    def __init__(
        self,
        contexts: list[K8sContext] | None = None,
        namespaces: dict[str, list[K8sNamespace]] | None = None,
        pods: dict[str, list[K8sPod]] | None = None,
        deployments: dict[str, list[K8sDeployment]] | None = None,
        health: dict[str, K8sClusterHealth] | None = None,
        logs: dict[str, str] | None = None,
        unavailable_contexts: set[str] | None = None,
    ) -> None:
        self._contexts = contexts or [
            K8sContext("dev", "dev-cluster", is_current=True),
            K8sContext("staging", "staging-cluster"),
            K8sContext("production", "prod-cluster"),
        ]
        self._namespaces = namespaces or {
            "dev": [K8sNamespace("default"), K8sNamespace("kube-system")],
            "staging": [K8sNamespace("default"), K8sNamespace("app")],
            "production": [
                K8sNamespace("default"),
                K8sNamespace("app"),
                K8sNamespace("monitoring"),
            ],
        }
        self._pods: dict[str, list[K8sPod]] = pods or {
            "dev/default": [
                K8sPod("api-7d9f8b-xkz", "default", "Running", "1/1", 0, "2d"),
                K8sPod("worker-5c6d7e-abc", "default", "Running", "1/1", 2, "2d"),
            ],
            "staging/default": [
                K8sPod("api-abc123", "default", "Running", "2/2", 0, "1d"),
                K8sPod("db-xyz789", "default", "CrashLoopBackOff", "0/1", 5, "1d"),
            ],
        }
        self._deployments: dict[str, list[K8sDeployment]] = deployments or {
            "dev/default": [K8sDeployment("api", "default", "1/1", 1, 1, "2d")],
            "staging/default": [
                K8sDeployment("api", "default", "2/2", 2, 2, "1d"),
                K8sDeployment("db", "default", "0/1", 1, 0, "1d"),
            ],
        }
        self._health: dict[str, K8sClusterHealth] = health or {
            "dev": K8sClusterHealth("dev", True, 3, 3, 2, 2, 0),
            "staging": K8sClusterHealth("staging", True, 2, 2, 2, 1, 1),
            "production": K8sClusterHealth("production", True, 5, 5, 10, 10, 0),
        }
        self._logs = logs or {
            "dev/default/api-7d9f8b-xkz": "INFO starting server\nINFO listening on :8080\n",
        }
        self._unavailable = unavailable_contexts or set()

    def _check_available(self, context: str) -> None:
        if context in self._unavailable:
            raise ConnectionError(f"Kubernetes context '{context}' is not reachable")

    async def list_contexts(self) -> list[K8sContext]:
        return list(self._contexts)

    async def current_context(self) -> str | None:
        for ctx in self._contexts:
            if ctx.is_current:
                return ctx.name
        return None

    async def list_namespaces(self, context: str) -> list[K8sNamespace]:
        self._check_available(context)
        return list(self._namespaces.get(context, []))

    async def list_pods(self, context: str, namespace: str = "default") -> list[K8sPod]:
        self._check_available(context)
        return list(self._pods.get(f"{context}/{namespace}", []))

    async def get_pod_logs(
        self, context: str, namespace: str, pod_name: str, tail_lines: int = 100
    ) -> str:
        self._check_available(context)
        key = f"{context}/{namespace}/{pod_name}"
        return self._logs.get(key, f"No logs found for pod {pod_name}")

    async def list_deployments(
        self, context: str, namespace: str = "default"
    ) -> list[K8sDeployment]:
        self._check_available(context)
        return list(self._deployments.get(f"{context}/{namespace}", []))

    async def cluster_health(self, context: str) -> K8sClusterHealth:
        self._check_available(context)
        return self._health.get(
            context,
            K8sClusterHealth(context, False, 0, 0, 0, 0, 0, error="Context not found"),
        )


class RealKubernetesClient(KubernetesClient):
    """Wraps the official kubernetes Python SDK.

    Loads kubeconfig from the default location (~/.kube/config).
    Each method switches to the requested context before querying.
    """

    def __init__(self) -> None:
        try:
            from kubernetes import client as k8s_client  # noqa: PLC0415
            from kubernetes import config as k8s_config  # noqa: PLC0415

            self._k8s_client = k8s_client
            self._k8s_config = k8s_config
            self._available = True
        except ImportError:
            self._available = False

    def _load_context(self, context: str) -> Any:
        """Return a CoreV1Api loaded for the given context."""
        if not self._available:
            raise RuntimeError("kubernetes package is not installed")
        cfg = self._k8s_config.new_client_from_config(context=context)
        return self._k8s_client.CoreV1Api(api_client=cfg)

    def _load_apps_context(self, context: str) -> Any:
        if not self._available:
            raise RuntimeError("kubernetes package is not installed")
        cfg = self._k8s_config.new_client_from_config(context=context)
        return self._k8s_client.AppsV1Api(api_client=cfg)

    async def list_contexts(self) -> list[K8sContext]:
        if not self._available:
            return []
        try:
            contexts_raw, active = self._k8s_config.list_kube_config_contexts()
        except Exception:
            return []
        active_name = active["name"] if active else None
        result = []
        for ctx in contexts_raw:
            name = ctx["name"]
            cluster = ctx.get("context", {}).get("cluster", name)
            namespace = ctx.get("context", {}).get("namespace", "default")
            result.append(K8sContext(name, cluster, namespace, is_current=(name == active_name)))
        return result

    async def current_context(self) -> str | None:
        if not self._available:
            return None
        try:
            _, active = self._k8s_config.list_kube_config_contexts()
        except Exception:
            return None
        return active["name"] if active else None

    async def list_namespaces(self, context: str) -> list[K8sNamespace]:
        core = self._load_context(context)
        ns_list = core.list_namespace()
        return [
            K8sNamespace(ns.metadata.name, ns.status.phase or "Unknown")
            for ns in ns_list.items
        ]

    async def list_pods(self, context: str, namespace: str = "default") -> list[K8sPod]:
        core = self._load_context(context)
        pod_list = core.list_namespaced_pod(namespace=namespace)
        result = []
        for pod in pod_list.items:
            phase = pod.status.phase or "Unknown"
            containers = pod.spec.containers or []
            statuses = pod.status.container_statuses or []
            ready_count = sum(1 for s in statuses if s.ready)
            restarts = sum(s.restart_count for s in statuses)
            result.append(
                K8sPod(
                    name=pod.metadata.name,
                    namespace=namespace,
                    status=phase,
                    ready=f"{ready_count}/{len(containers)}",
                    restarts=restarts,
                    age="",
                    node=pod.spec.node_name or "",
                )
            )
        return result

    async def get_pod_logs(
        self, context: str, namespace: str, pod_name: str, tail_lines: int = 100
    ) -> str:
        core = self._load_context(context)
        return core.read_namespaced_pod_log(  # type: ignore[no-any-return]
            name=pod_name, namespace=namespace, tail_lines=tail_lines
        )

    async def list_deployments(
        self, context: str, namespace: str = "default"
    ) -> list[K8sDeployment]:
        apps = self._load_apps_context(context)
        dep_list = apps.list_namespaced_deployment(namespace=namespace)
        result = []
        for dep in dep_list.items:
            spec_replicas = dep.spec.replicas or 0
            status = dep.status
            ready = status.ready_replicas or 0
            result.append(
                K8sDeployment(
                    name=dep.metadata.name,
                    namespace=namespace,
                    ready=f"{ready}/{spec_replicas}",
                    up_to_date=status.updated_replicas or 0,
                    available=status.available_replicas or 0,
                    age="",
                )
            )
        return result

    async def cluster_health(self, context: str) -> K8sClusterHealth:
        try:
            core = self._load_context(context)
            nodes = core.list_node()
            node_count = len(nodes.items)
            ready_nodes = sum(
                1
                for n in nodes.items
                if any(
                    c.type == "Ready" and c.status == "True"
                    for c in (n.status.conditions or [])
                )
            )
            pods = core.list_pod_for_all_namespaces()
            total = len(pods.items)
            running = sum(1 for p in pods.items if (p.status.phase or "") == "Running")
            failed = sum(1 for p in pods.items if (p.status.phase or "") == "Failed")
            return K8sClusterHealth(context, True, node_count, ready_nodes, total, running, failed)
        except Exception as exc:
            return K8sClusterHealth(context, False, 0, 0, 0, 0, 0, error=str(exc))

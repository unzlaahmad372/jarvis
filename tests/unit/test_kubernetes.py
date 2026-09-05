"""Unit tests for Phase 6 — Kubernetes tools (no real cluster required)."""

from __future__ import annotations

import json

import pytest

from app.core.config import Settings
from app.tools.kubernetes.client import (
    FakeKubernetesClient,
    K8sClusterHealth,
    K8sContext,
)
from app.tools.kubernetes.tools import (
    ClusterHealthTool,
    GetPodLogsTool,
    ListContextsTool,
    ListDeploymentsTool,
    ListNamespacesTool,
    ListPodsTool,
)


def _settings(**overrides: object) -> Settings:
    base = {
        "k8s_protected_contexts": "production",
        "k8s_max_log_lines": 100,
        "k8s_fan_out_limit": 5,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# ── ListContextsTool ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_contexts_returns_all() -> None:
    client = FakeKubernetesClient()
    tool = ListContextsTool(client, _settings())
    result = await tool.execute({})
    assert result.success
    data = json.loads(result.output)
    assert len(data["contexts"]) == 3
    names = [c["name"] for c in data["contexts"]]
    assert "dev" in names
    assert "production" in names


@pytest.mark.asyncio
async def test_list_contexts_marks_current() -> None:
    client = FakeKubernetesClient()
    tool = ListContextsTool(client, _settings())
    result = await tool.execute({})
    data = json.loads(result.output)
    assert data["current_context"] == "dev"
    current = next(c for c in data["contexts"] if c["name"] == "dev")
    assert current["current"] is True


@pytest.mark.asyncio
async def test_list_contexts_marks_protected() -> None:
    client = FakeKubernetesClient()
    tool = ListContextsTool(client, _settings(k8s_protected_contexts="production"))
    result = await tool.execute({})
    data = json.loads(result.output)
    prod = next(c for c in data["contexts"] if c["name"] == "production")
    dev = next(c for c in data["contexts"] if c["name"] == "dev")
    assert prod["protected"] is True
    assert dev["protected"] is False


@pytest.mark.asyncio
async def test_list_contexts_client_error() -> None:
    class _FailClient(FakeKubernetesClient):
        async def list_contexts(self) -> list[K8sContext]:
            raise ConnectionError("kubeconfig not found")

    tool = ListContextsTool(_FailClient(), _settings())
    result = await tool.execute({})
    assert not result.success
    assert "kubeconfig not found" in (result.error or "")


# ── ListNamespacesTool ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_namespaces_success() -> None:
    client = FakeKubernetesClient()
    tool = ListNamespacesTool(client, _settings())
    result = await tool.execute({"context": "dev"})
    assert result.success
    data = json.loads(result.output)
    assert data["context"] == "dev"
    assert len(data["namespaces"]) == 2


@pytest.mark.asyncio
async def test_list_namespaces_missing_context_param() -> None:
    client = FakeKubernetesClient()
    tool = ListNamespacesTool(client, _settings())
    result = await tool.execute({})
    assert not result.success
    assert "context is required" in (result.error or "")


@pytest.mark.asyncio
async def test_list_namespaces_unavailable_context() -> None:
    client = FakeKubernetesClient(unavailable_contexts={"dev"})
    tool = ListNamespacesTool(client, _settings())
    result = await tool.execute({"context": "dev"})
    assert not result.success
    assert "not reachable" in (result.error or "")


# ── ListPodsTool ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_pods_success() -> None:
    client = FakeKubernetesClient()
    tool = ListPodsTool(client, _settings())
    result = await tool.execute({"context": "dev", "namespace": "default"})
    assert result.success
    data = json.loads(result.output)
    assert data["pod_count"] == 2
    assert data["unhealthy_count"] == 0


@pytest.mark.asyncio
async def test_list_pods_detects_unhealthy() -> None:
    client = FakeKubernetesClient()
    tool = ListPodsTool(client, _settings())
    result = await tool.execute({"context": "staging", "namespace": "default"})
    assert result.success
    data = json.loads(result.output)
    assert data["unhealthy_count"] == 1


@pytest.mark.asyncio
async def test_list_pods_missing_context() -> None:
    client = FakeKubernetesClient()
    tool = ListPodsTool(client, _settings())
    result = await tool.execute({"namespace": "default"})
    assert not result.success


@pytest.mark.asyncio
async def test_list_pods_empty_namespace() -> None:
    client = FakeKubernetesClient()
    tool = ListPodsTool(client, _settings())
    result = await tool.execute({"context": "dev", "namespace": "nonexistent"})
    assert result.success
    data = json.loads(result.output)
    assert data["pod_count"] == 0


# ── GetPodLogsTool ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_pod_logs_success() -> None:
    client = FakeKubernetesClient()
    tool = GetPodLogsTool(client, _settings())
    result = await tool.execute(
        {"context": "dev", "namespace": "default", "pod_name": "api-7d9f8b-xkz"}
    )
    assert result.success
    data = json.loads(result.output)
    assert "INFO starting server" in data["logs"]


@pytest.mark.asyncio
async def test_get_pod_logs_missing_params() -> None:
    client = FakeKubernetesClient()
    tool = GetPodLogsTool(client, _settings())
    result = await tool.execute({"context": "dev"})
    assert not result.success
    assert "pod_name" in (result.error or "")


@pytest.mark.asyncio
async def test_get_pod_logs_respects_max_lines() -> None:
    client = FakeKubernetesClient()
    tool = GetPodLogsTool(client, _settings(k8s_max_log_lines=10))
    result = await tool.execute(
        {"context": "dev", "namespace": "default", "pod_name": "api-7d9f8b-xkz", "tail_lines": 9999}
    )
    assert result.success
    data = json.loads(result.output)
    assert data["tail_lines"] == 10  # capped at max


@pytest.mark.asyncio
async def test_get_pod_logs_unknown_pod() -> None:
    client = FakeKubernetesClient()
    tool = GetPodLogsTool(client, _settings())
    result = await tool.execute(
        {"context": "dev", "namespace": "default", "pod_name": "ghost-pod"}
    )
    assert result.success
    data = json.loads(result.output)
    assert "No logs found" in data["logs"]


# ── ListDeploymentsTool ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_deployments_success() -> None:
    client = FakeKubernetesClient()
    tool = ListDeploymentsTool(client, _settings())
    result = await tool.execute({"context": "staging", "namespace": "default"})
    assert result.success
    data = json.loads(result.output)
    assert data["deployment_count"] == 2


@pytest.mark.asyncio
async def test_list_deployments_missing_context() -> None:
    client = FakeKubernetesClient()
    tool = ListDeploymentsTool(client, _settings())
    result = await tool.execute({})
    assert not result.success


# ── ClusterHealthTool ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cluster_health_healthy() -> None:
    client = FakeKubernetesClient()
    tool = ClusterHealthTool(client, _settings())
    result = await tool.execute({"context": "dev"})
    assert result.success
    data = json.loads(result.output)
    assert data["status"] == "HEALTHY"
    assert data["reachable"] is True
    assert data["nodes"]["total"] == 3
    assert data["nodes"]["ready"] == 3


@pytest.mark.asyncio
async def test_cluster_health_degraded() -> None:
    client = FakeKubernetesClient()
    tool = ClusterHealthTool(client, _settings())
    result = await tool.execute({"context": "staging"})
    assert result.success
    data = json.loads(result.output)
    assert data["status"] == "DEGRADED"
    assert data["pods"]["failed"] == 1


@pytest.mark.asyncio
async def test_cluster_health_unreachable() -> None:
    client = FakeKubernetesClient(
        health={"dev": K8sClusterHealth("dev", False, 0, 0, 0, 0, 0, error="connection refused")}
    )
    tool = ClusterHealthTool(client, _settings())
    result = await tool.execute({"context": "dev"})
    assert result.success
    data = json.loads(result.output)
    assert data["status"] == "UNREACHABLE"
    assert data["error"] == "connection refused"


@pytest.mark.asyncio
async def test_cluster_health_protected_context() -> None:
    client = FakeKubernetesClient()
    tool = ClusterHealthTool(client, _settings(k8s_protected_contexts="production"))
    result = await tool.execute({"context": "production"})
    assert result.success
    data = json.loads(result.output)
    assert data["protected"] is True


@pytest.mark.asyncio
async def test_cluster_health_missing_context_param() -> None:
    client = FakeKubernetesClient()
    tool = ClusterHealthTool(client, _settings())
    result = await tool.execute({})
    assert not result.success
    assert "context is required" in (result.error or "")


# ── FakeKubernetesClient ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fake_client_unavailable_raises() -> None:
    client = FakeKubernetesClient(unavailable_contexts={"staging"})
    with pytest.raises(ConnectionError, match="not reachable"):
        await client.list_namespaces("staging")


@pytest.mark.asyncio
async def test_fake_client_current_context() -> None:
    client = FakeKubernetesClient()
    current = await client.current_context()
    assert current == "dev"


@pytest.mark.asyncio
async def test_fake_client_no_current_context() -> None:
    client = FakeKubernetesClient(
        contexts=[K8sContext("a", "cluster-a"), K8sContext("b", "cluster-b")]
    )
    current = await client.current_context()
    assert current is None


# ── API endpoints ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_list_contexts_disabled(test_client) -> None:
    """When k8s is disabled the endpoint returns 503."""
    from unittest.mock import patch

    from app.core.config import Settings

    disabled = Settings(enable_kubernetes=False)
    with patch("app.api.routes.kubernetes.get_settings", return_value=disabled):
        resp = await test_client.get("/api/v1/kubernetes/contexts")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_api_cluster_health_disabled(test_client) -> None:
    from unittest.mock import patch

    from app.core.config import Settings

    disabled = Settings(enable_kubernetes=False)
    with patch("app.api.routes.kubernetes.get_settings", return_value=disabled):
        resp = await test_client.get("/api/v1/kubernetes/health/dev")
    assert resp.status_code == 503

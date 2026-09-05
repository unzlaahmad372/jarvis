"""Kubernetes endpoints — GET /api/v1/kubernetes/contexts, /health."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.schemas.chat import K8sClusterHealthOut, K8sContextOut, K8sContextsOut
from app.core.config import get_settings
from app.tools.kubernetes.client import RealKubernetesClient

router = APIRouter(prefix="/api/v1/kubernetes", tags=["kubernetes"])

_client: RealKubernetesClient | None = None

_DISABLED_MSG = "Kubernetes integration is disabled"


def _get_client() -> RealKubernetesClient:
    global _client
    if _client is None:
        _client = RealKubernetesClient()
    return _client


@router.get("/contexts", response_model=K8sContextsOut)
async def list_contexts() -> K8sContextsOut:
    settings = get_settings()
    if not settings.enable_kubernetes:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_DISABLED_MSG
        )
    try:
        client = _get_client()
        contexts = await client.list_contexts()
        current = await client.current_context()
        return K8sContextsOut(
            current_context=current,
            contexts=[
                K8sContextOut(
                    name=c.name,
                    cluster=c.cluster,
                    namespace=c.namespace,
                    current=c.is_current,
                    protected=c.name in settings.k8s_protected_contexts_list,
                )
                for c in contexts
            ],
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.get("/health/{context}", response_model=K8sClusterHealthOut)
async def cluster_health(context: str) -> K8sClusterHealthOut:
    settings = get_settings()
    if not settings.enable_kubernetes:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_DISABLED_MSG
        )
    try:
        client = _get_client()
        health = await client.cluster_health(context)
        if not health.reachable:
            status_str = "UNREACHABLE"
        elif health.failed_pods > 0:
            status_str = "DEGRADED"
        else:
            status_str = "HEALTHY"
        return K8sClusterHealthOut(
            context=context,
            protected=context in settings.k8s_protected_contexts_list,
            status=status_str,
            reachable=health.reachable,
            node_total=health.node_count,
            node_ready=health.ready_nodes,
            pod_total=health.total_pods,
            pod_running=health.running_pods,
            pod_failed=health.failed_pods,
            error=health.error,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

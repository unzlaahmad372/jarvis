"""Model management endpoints — Phase 32.

GET  /api/v1/models         — list available Ollama models
GET  /api/v1/models/active  — current active model
POST /api/v1/models/active  — switch active model at runtime
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.api.deps import SettingsDep, get_orchestrator

router = APIRouter(prefix="/api/v1/models", tags=["models"])


class ModelOut(BaseModel):
    name: str
    size_gb: float | None = None
    family: str | None = None


class ModelsOut(BaseModel):
    models: list[ModelOut]


class ActiveModelOut(BaseModel):
    model: str
    provider: str


class SetModelRequest(BaseModel):
    model: str


@router.get("", response_model=ModelsOut, summary="List available Ollama models")
async def list_models(settings: SettingsDep) -> ModelsOut:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{settings.ollama_url}/api/tags")
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ollama unreachable: {exc}",
        ) from exc

    models = [
        ModelOut(
            name=m.get("name", ""),
            size_gb=round(m.get("size", 0) / 1e9, 1) if m.get("size") else None,
            family=m.get("details", {}).get("family"),
        )
        for m in data.get("models", [])
        if m.get("name")
    ]
    return ModelsOut(models=models)


@router.get("/active", response_model=ActiveModelOut, summary="Get active model")
async def get_active_model(request: Request) -> ActiveModelOut:
    from app.brain.orchestrator import ChatOrchestrator
    orchestrator: ChatOrchestrator = get_orchestrator(request)  # type: ignore[assignment]
    return ActiveModelOut(
        model=orchestrator._llm.model_name,  # noqa: SLF001
        provider=orchestrator._llm.provider_name,  # noqa: SLF001
    )


@router.post("/active", response_model=ActiveModelOut, summary="Switch active model")
async def set_active_model(
    body: SetModelRequest,
    request: Request,
    settings: SettingsDep,
) -> ActiveModelOut:
    from app.brain.orchestrator import ChatOrchestrator
    from app.llm.ollama import OllamaProvider

    if not body.model.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="model is required"
        )

    orchestrator: ChatOrchestrator = get_orchestrator(request)  # type: ignore[assignment]
    new_llm = OllamaProvider(base_url=settings.ollama_url, model=body.model.strip())
    orchestrator._llm = new_llm  # noqa: SLF001
    return ActiveModelOut(model=new_llm.model_name, provider=new_llm.provider_name)

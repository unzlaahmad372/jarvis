"""Workspace management endpoints.

GET    /api/v1/workspaces          — list workspaces
POST   /api/v1/workspaces          — create workspace
POST   /api/v1/workspaces/{id}/activate — set as active (default)
DELETE /api/v1/workspaces/{id}     — delete (not default)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession
from app.db.models import Conversation, Workspace

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


class WorkspaceOut(BaseModel):
    id: int
    name: str
    description: str | None
    is_default: bool
    conversation_count: int = 0

    model_config = {"from_attributes": True}


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


@router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(session: DbSession) -> list[WorkspaceOut]:
    workspaces = (await session.execute(select(Workspace))).scalars().all()
    result = []
    for w in workspaces:
        count = len((await session.execute(
            select(Conversation).where(Conversation.workspace_id == w.id)
        )).scalars().all())
        result.append(WorkspaceOut(id=w.id, name=w.name, description=w.description,
                                   is_default=w.is_default, conversation_count=count))
    return result


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
async def create_workspace(body: WorkspaceCreate, session: DbSession) -> WorkspaceOut:
    existing = (await session.execute(
        select(Workspace).where(Workspace.name == body.name)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f"Workspace '{body.name}' already exists")
    ws = Workspace(name=body.name, description=body.description, is_default=False)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return WorkspaceOut(id=ws.id, name=ws.name, description=ws.description,
                        is_default=ws.is_default, conversation_count=0)


@router.post("/{workspace_id}/activate", response_model=WorkspaceOut)
async def activate_workspace(workspace_id: int, session: DbSession) -> WorkspaceOut:
    ws = (await session.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )).scalar_one_or_none()
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    # Clear existing default
    all_ws = (await session.execute(select(Workspace))).scalars().all()
    for w in all_ws:
        w.is_default = w.id == workspace_id
    await session.commit()
    await session.refresh(ws)
    return WorkspaceOut(id=ws.id, name=ws.name, description=ws.description, is_default=ws.is_default)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(workspace_id: int, session: DbSession) -> None:
    ws = (await session.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )).scalar_one_or_none()
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    if ws.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete the default workspace")
    await session.delete(ws)
    await session.commit()

"""Auth & Device Registry REST API — Phase 11.

Endpoints:
  POST   /api/v1/auth/devices          — register a new device, get tokens
  GET    /api/v1/auth/devices          — list all devices
  GET    /api/v1/auth/devices/{id}     — get a device
  POST   /api/v1/auth/devices/{id}/revoke   — revoke a device
  POST   /api/v1/auth/token/refresh    — refresh access token
  GET    /api/v1/auth/me               — introspect current token

Auth is only enforced when JARVIS_ENABLE_REMOTE_ACCESS=true.
Local loopback requests bypass auth (single-user local mode).

Security invariants:
  - Revoked devices cannot refresh tokens
  - Scope escalation is blocked at normalize_scopes()
  - Dangerous operations are never in the scope list
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.schemas.chat import (
    DeviceOut,
    DeviceRegisterRequest,
    RefreshRequest,
    TokenResponse,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Device
from app.security.auth import (
    DESKTOP_DEFAULT_SCOPES,
    MOBILE_DEFAULT_SCOPES,
    create_access_token,
    create_refresh_token,
    normalize_scopes,
    verify_refresh_token,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
logger = get_logger(__name__)


def _device_to_out(d: Device) -> DeviceOut:
    return DeviceOut(
        device_id=d.device_id,
        name=d.name,
        device_type=d.device_type,
        scopes=d.scopes.split(",") if d.scopes else [],
        revoked=d.revoked,
        created_at=d.created_at,
        last_seen_at=d.last_seen_at,
    )


def _default_scopes_for_type(device_type: str) -> list[str]:
    if device_type == "mobile":
        return sorted(MOBILE_DEFAULT_SCOPES)
    return sorted(DESKTOP_DEFAULT_SCOPES)


def _resolve_scopes(requested: list[str], device_type: str) -> list[str]:
    """Resolve final scopes: intersection of requested and device-type ceiling."""
    ceiling = _default_scopes_for_type(device_type)
    if not requested:
        return ceiling
    return normalize_scopes(requested, ceiling)


@router.post("/devices", response_model=TokenResponse, status_code=201)
async def register_device(
    body: DeviceRegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    """Register a new device and issue access + refresh tokens."""
    settings = get_settings()

    scopes = _resolve_scopes(body.requested_scopes, body.device_type)
    if not scopes:
        raise HTTPException(status_code=422, detail="No valid scopes granted for this device type.")

    device_id = str(uuid.uuid4())
    device = Device(
        device_id=device_id,
        name=body.name,
        device_type=body.device_type,
        scopes=",".join(scopes),
        revoked=False,
        created_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    session.add(device)
    await session.commit()

    access_token = create_access_token(device_id, scopes)
    refresh_token = create_refresh_token(device_id, scopes)

    logger.info("device_registered", device_id=device_id, device_type=body.device_type)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in_seconds=settings.auth_access_token_expire_minutes * 60,
        scopes=scopes,
    )


@router.get("/devices", response_model=list[DeviceOut])
async def list_devices(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[DeviceOut]:
    """List all registered devices."""
    result = await session.execute(select(Device).order_by(Device.created_at.desc()))
    devices = result.scalars().all()
    return [_device_to_out(d) for d in devices]


@router.get("/devices/{device_id}", response_model=DeviceOut)
async def get_device(
    device_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DeviceOut:
    """Get a device by ID."""
    result = await session.execute(select(Device).where(Device.device_id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.")
    return _device_to_out(device)


@router.post("/devices/{device_id}/revoke", status_code=204)
async def revoke_device(
    device_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    """Revoke a device. Revoked devices cannot refresh tokens."""
    result = await session.execute(select(Device).where(Device.device_id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.")
    if device.revoked:
        return  # idempotent
    device.revoked = True
    device.revoked_at = datetime.now(UTC)
    await session.commit()
    logger.info("device_revoked", device_id=device_id)


@router.post("/token/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    """Exchange a refresh token for a new access token.

    Scope escalation is blocked — new token cannot exceed device's registered scopes.
    Revoked devices are rejected.
    """
    settings = get_settings()

    try:
        device_id, token_scopes = verify_refresh_token(body.refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    result = await session.execute(select(Device).where(Device.device_id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=401, detail="Device not found.")
    if device.revoked:
        raise HTTPException(status_code=401, detail="Device has been revoked.")

    # Enforce scope ceiling — token cannot exceed device's registered scopes
    device_scopes = device.scopes.split(",") if device.scopes else []
    final_scopes = normalize_scopes(token_scopes, device_scopes)

    # Update last_seen
    device.last_seen_at = datetime.now(UTC)
    await session.commit()

    access_token = create_access_token(device_id, final_scopes)
    new_refresh = create_refresh_token(device_id, final_scopes)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in_seconds=settings.auth_access_token_expire_minutes * 60,
        scopes=final_scopes,
    )


@router.get("/me")
async def introspect_token(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    """Introspect the current access token (if provided)."""
    if not authorization or not authorization.startswith("Bearer "):
        return {
            "authenticated": False,
            "remote_access_enabled": get_settings().enable_remote_access,
        }

    token = authorization.removeprefix("Bearer ")
    from app.security.auth import verify_access_token
    try:
        device_id, scopes = verify_access_token(token)
        return {"authenticated": True, "device_id": device_id, "scopes": scopes}
    except ValueError:
        return {"authenticated": False, "error": "Invalid or expired token."}

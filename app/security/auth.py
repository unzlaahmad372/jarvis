"""JWT authentication for Phase 11 — Remote/Mobile access.

Architecture:
  - Access tokens: short-lived (default 60 min), carry device_id + scopes
  - Refresh tokens: longer-lived (default 30 days), used to obtain new access tokens
  - Device registry: each device has an explicit ID, name, type, scopes, revoked flag
  - Auth is ONLY enforced when JARVIS_ENABLE_REMOTE_ACCESS=true
  - Local loopback requests bypass auth by default (single-user local mode)

Scopes (spec §43):
  chat, knowledge.read, memory.read, memory.write,
  automation.read, system.read, tool.low_risk

Security invariants:
  - Revoked devices cannot obtain new tokens
  - Expired tokens are rejected
  - Scope escalation is not possible through token refresh
  - Dangerous tool operations are never granted via token scope alone
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# All valid scopes — dangerous operations are never in scope list
VALID_SCOPES = frozenset(
    [
        "chat",
        "knowledge.read",
        "memory.read",
        "memory.write",
        "automation.read",
        "system.read",
        "tool.low_risk",
    ]
)

# Default scopes for desktop (local) devices
DESKTOP_DEFAULT_SCOPES = frozenset(
    ["chat", "knowledge.read", "memory.read", "memory.write", "automation.read", "system.read"]
)

# Restricted scopes for mobile devices (spec §43)
MOBILE_DEFAULT_SCOPES = frozenset(["chat", "knowledge.read", "memory.read"])

TOKEN_TYPE_ACCESS = "access"  # noqa: S105
TOKEN_TYPE_REFRESH = "refresh"  # noqa: S105


def _settings() -> Settings:
    return get_settings()


def create_access_token(device_id: str, scopes: list[str]) -> str:
    """Issue a short-lived access token for a device."""
    settings = _settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": device_id,
        "scopes": scopes,
        "type": TOKEN_TYPE_ACCESS,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=settings.auth_access_token_expire_minutes),
    }
    return str(jwt.encode(payload, settings.auth_secret_key, algorithm=settings.auth_algorithm))


def create_refresh_token(device_id: str, scopes: list[str]) -> str:
    """Issue a long-lived refresh token for a device."""
    settings = _settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": device_id,
        "scopes": scopes,
        "type": TOKEN_TYPE_REFRESH,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(days=settings.auth_refresh_token_expire_days),
    }
    return str(jwt.encode(payload, settings.auth_secret_key, algorithm=settings.auth_algorithm))


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises JWTError on failure."""
    settings = _settings()
    return dict(jwt.decode(token, settings.auth_secret_key, algorithms=[settings.auth_algorithm]))


def verify_access_token(token: str) -> tuple[str, list[str]]:
    """Verify an access token. Returns (device_id, scopes).

    Raises ValueError on invalid/expired/wrong-type token.
    """
    try:
        payload = decode_token(token)
    except JWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc

    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise ValueError("Token is not an access token.")

    device_id = payload.get("sub")
    if not device_id:
        raise ValueError("Token missing subject.")

    scopes = payload.get("scopes", [])
    return str(device_id), list(scopes)


def verify_refresh_token(token: str) -> tuple[str, list[str]]:
    """Verify a refresh token. Returns (device_id, scopes).

    Raises ValueError on invalid/expired/wrong-type token.
    """
    try:
        payload = decode_token(token)
    except JWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc

    if payload.get("type") != TOKEN_TYPE_REFRESH:
        raise ValueError("Token is not a refresh token.")

    device_id = payload.get("sub")
    if not device_id:
        raise ValueError("Token missing subject.")

    scopes = payload.get("scopes", [])
    return str(device_id), list(scopes)


def normalize_scopes(requested: list[str], device_max: list[str]) -> list[str]:
    """Return the intersection of requested scopes and device's maximum allowed scopes.

    Prevents scope escalation: a refresh cannot grant more than the device's ceiling.
    """
    allowed = set(device_max) & VALID_SCOPES
    return [s for s in requested if s in allowed]


def has_scope(token_scopes: list[str], required: str) -> bool:
    """Check whether a token carries a required scope."""
    return required in token_scopes

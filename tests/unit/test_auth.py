"""Tests for Phase 11 — Remote/Mobile: Auth, Device Registry, Rate Limiting.

Covers:
  - JWT token creation and verification
  - Scope normalization and escalation prevention
  - Device registration, listing, revocation
  - Token refresh (including revoked device rejection)
  - Rate limiter token bucket behavior
  - REST API endpoints
"""

from __future__ import annotations

import time

import pytest

from app.security.auth import (
    DESKTOP_DEFAULT_SCOPES,
    MOBILE_DEFAULT_SCOPES,
    VALID_SCOPES,
    create_access_token,
    create_refresh_token,
    has_scope,
    normalize_scopes,
    verify_access_token,
    verify_refresh_token,
)
from app.security.rate_limiter import RateLimiter, TokenBucket

# ── JWT Token Tests ───────────────────────────────────────────────────────────


def test_create_and_verify_access_token():
    scopes = ["chat", "knowledge.read"]
    token = create_access_token("device-1", scopes)
    device_id, returned_scopes = verify_access_token(token)
    assert device_id == "device-1"
    assert returned_scopes == scopes


def test_create_and_verify_refresh_token():
    scopes = ["chat"]
    token = create_refresh_token("device-2", scopes)
    device_id, returned_scopes = verify_refresh_token(token)
    assert device_id == "device-2"
    assert returned_scopes == scopes


def test_access_token_rejected_as_refresh():
    token = create_access_token("d", ["chat"])
    with pytest.raises(ValueError, match="not a refresh token"):
        verify_refresh_token(token)


def test_refresh_token_rejected_as_access():
    token = create_refresh_token("d", ["chat"])
    with pytest.raises(ValueError, match="not an access token"):
        verify_access_token(token)


def test_invalid_token_raises():
    with pytest.raises(ValueError, match="Invalid token"):
        verify_access_token("not.a.jwt")


def test_tampered_token_raises():
    token = create_access_token("d", ["chat"])
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(ValueError):
        verify_access_token(tampered)


def test_has_scope_true():
    assert has_scope(["chat", "knowledge.read"], "chat") is True


def test_has_scope_false():
    assert has_scope(["chat"], "memory.write") is False


# ── Scope Normalization ───────────────────────────────────────────────────────


def test_normalize_scopes_intersection():
    result = normalize_scopes(["chat", "memory.write"], ["chat", "knowledge.read"])
    assert result == ["chat"]


def test_normalize_scopes_no_escalation():
    # Requesting dangerous scope not in VALID_SCOPES
    result = normalize_scopes(["chat", "tool.dangerous"], list(VALID_SCOPES))
    assert "tool.dangerous" not in result


def test_normalize_scopes_empty_request():
    result = normalize_scopes([], ["chat"])
    assert result == []


def test_normalize_scopes_all_valid():
    scopes = list(VALID_SCOPES)
    result = normalize_scopes(scopes, scopes)
    assert set(result) == VALID_SCOPES


def test_mobile_scopes_subset_of_desktop():
    assert MOBILE_DEFAULT_SCOPES.issubset(DESKTOP_DEFAULT_SCOPES)


def test_valid_scopes_no_dangerous():
    assert "tool.dangerous" not in VALID_SCOPES
    assert "tool.sensitive" not in VALID_SCOPES


# ── Rate Limiter ──────────────────────────────────────────────────────────────


def test_token_bucket_allows_within_limit():
    bucket = TokenBucket(rate_per_minute=60)
    # Should allow first request immediately
    assert bucket.consume() is True


def test_token_bucket_exhausted():
    bucket = TokenBucket(rate_per_minute=2)
    assert bucket.consume() is True
    assert bucket.consume() is True
    assert bucket.consume() is False


def test_token_bucket_refills_over_time():
    bucket = TokenBucket(rate_per_minute=60)
    # Drain all tokens
    for _ in range(60):
        bucket.consume()
    # Should be empty
    assert bucket.consume() is False
    # Wait for refill (1 token per second at 60/min)
    time.sleep(1.1)
    assert bucket.consume() is True


def test_rate_limiter_allows_different_keys():
    limiter = RateLimiter(rate_per_minute=1)
    assert limiter.is_allowed("key-a") is True
    assert limiter.is_allowed("key-b") is True  # different key, own bucket


def test_rate_limiter_blocks_same_key():
    limiter = RateLimiter(rate_per_minute=1)
    assert limiter.is_allowed("key-x") is True
    assert limiter.is_allowed("key-x") is False


def test_rate_limiter_reset():
    limiter = RateLimiter(rate_per_minute=1)
    limiter.is_allowed("key-r")
    limiter.is_allowed("key-r")  # exhaust
    limiter.reset("key-r")
    assert limiter.is_allowed("key-r") is True


# ── REST API ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_device(test_client):
    resp = await test_client.post(
        "/api/v1/auth/devices",
        json={"name": "My Laptop", "device_type": "desktop", "requested_scopes": ["chat"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["access_token"]
    assert data["refresh_token"]
    assert "chat" in data["scopes"]
    assert data["token_type"] == "bearer"  # noqa: S105


@pytest.mark.asyncio
async def test_register_mobile_device_restricted_scopes(test_client):
    resp = await test_client.post(
        "/api/v1/auth/devices",
        json={
            "name": "My Phone",
            "device_type": "mobile",
            "requested_scopes": ["chat", "memory.write", "tool.low_risk"],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    # memory.write and tool.low_risk are not in mobile ceiling
    assert "tool.low_risk" not in data["scopes"]


@pytest.mark.asyncio
async def test_register_device_invalid_scopes_only(test_client):
    resp = await test_client.post(
        "/api/v1/auth/devices",
        json={
            "name": "Bad Device",
            "device_type": "mobile",
            "requested_scopes": ["tool.dangerous"],
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_devices_empty(test_client):
    resp = await test_client.get("/api/v1/auth/devices")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_devices_after_register(test_client):
    await test_client.post(
        "/api/v1/auth/devices",
        json={"name": "Test Device", "device_type": "desktop"},
    )
    resp = await test_client.get("/api/v1/auth/devices")
    assert resp.status_code == 200
    devices = resp.json()
    assert len(devices) >= 1
    assert any(d["name"] == "Test Device" for d in devices)


@pytest.mark.asyncio
async def test_get_device_not_found(test_client):
    resp = await test_client.get("/api/v1/auth/devices/no-such-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_device_found(test_client):
    reg = await test_client.post(
        "/api/v1/auth/devices",
        json={"name": "Find Me", "device_type": "desktop"},
    )
    # Get device_id from the token payload
    token = reg.json()["access_token"]
    device_id, _ = verify_access_token(token)

    resp = await test_client.get(f"/api/v1/auth/devices/{device_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Find Me"


@pytest.mark.asyncio
async def test_revoke_device(test_client):
    reg = await test_client.post(
        "/api/v1/auth/devices",
        json={"name": "Revoke Me", "device_type": "desktop"},
    )
    token = reg.json()["access_token"]
    device_id, _ = verify_access_token(token)

    resp = await test_client.post(f"/api/v1/auth/devices/{device_id}/revoke")
    assert resp.status_code == 204

    # Device should now be revoked
    get_resp = await test_client.get(f"/api/v1/auth/devices/{device_id}")
    assert get_resp.json()["revoked"] is True


@pytest.mark.asyncio
async def test_revoke_device_not_found(test_client):
    resp = await test_client.post("/api/v1/auth/devices/no-such-id/revoke")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_revoke_idempotent(test_client):
    reg = await test_client.post(
        "/api/v1/auth/devices",
        json={"name": "Revoke Twice", "device_type": "desktop"},
    )
    token = reg.json()["access_token"]
    device_id, _ = verify_access_token(token)

    await test_client.post(f"/api/v1/auth/devices/{device_id}/revoke")
    resp = await test_client.post(f"/api/v1/auth/devices/{device_id}/revoke")
    assert resp.status_code == 204  # idempotent


@pytest.mark.asyncio
async def test_refresh_token_success(test_client):
    reg = await test_client.post(
        "/api/v1/auth/devices",
        json={"name": "Refresh Me", "device_type": "desktop"},
    )
    refresh_token = reg.json()["refresh_token"]

    resp = await test_client.post(
        "/api/v1/auth/token/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"]
    assert data["refresh_token"]


@pytest.mark.asyncio
async def test_refresh_token_revoked_device(test_client):
    reg = await test_client.post(
        "/api/v1/auth/devices",
        json={"name": "Revoke Then Refresh", "device_type": "desktop"},
    )
    token = reg.json()["access_token"]
    refresh_token = reg.json()["refresh_token"]
    device_id, _ = verify_access_token(token)

    await test_client.post(f"/api/v1/auth/devices/{device_id}/revoke")

    resp = await test_client.post(
        "/api/v1/auth/token/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_invalid(test_client):
    resp = await test_client.post(
        "/api/v1/auth/token/refresh",
        json={"refresh_token": "not.a.valid.token"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_no_scope_escalation(test_client):
    """Refresh cannot grant more scopes than device's registered ceiling."""
    reg = await test_client.post(
        "/api/v1/auth/devices",
        json={"name": "Limited", "device_type": "mobile", "requested_scopes": ["chat"]},
    )
    refresh_token = reg.json()["refresh_token"]

    resp = await test_client.post(
        "/api/v1/auth/token/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    # Scopes should not exceed mobile ceiling
    returned_scopes = resp.json()["scopes"]
    assert "tool.low_risk" not in returned_scopes
    assert "memory.write" not in returned_scopes


@pytest.mark.asyncio
async def test_introspect_no_token(test_client):
    resp = await test_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["authenticated"] is False


@pytest.mark.asyncio
async def test_introspect_valid_token(test_client):
    reg = await test_client.post(
        "/api/v1/auth/devices",
        json={"name": "Introspect Me", "device_type": "desktop"},
    )
    access_token = reg.json()["access_token"]

    resp = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is True
    assert "scopes" in data


@pytest.mark.asyncio
async def test_introspect_invalid_token(test_client):
    resp = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 200
    assert resp.json()["authenticated"] is False

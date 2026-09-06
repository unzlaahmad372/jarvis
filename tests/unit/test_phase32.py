"""Tests for Phase 32 — Model Switcher API."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


def _make_httpx_mock(json_data: dict) -> MagicMock:
    """Build a properly-structured mock for httpx.AsyncClient context manager."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = json_data

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)
    return mock_client


class TestListModels:
    async def test_returns_503_when_ollama_unreachable(
        self, test_client: AsyncClient
    ) -> None:
        import httpx
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

        with patch("app.api.routes.models.httpx.AsyncClient", return_value=mock_client):
            resp = await test_client.get("/api/v1/models")
        assert resp.status_code == 503

    async def test_returns_model_list(self, test_client: AsyncClient) -> None:
        fake_tags = {
            "models": [
                {"name": "llama3.2", "size": 2_000_000_000, "details": {"family": "llama"}},
                {"name": "mistral", "size": 4_000_000_000, "details": {"family": "mistral"}},
            ]
        }
        mock_client = _make_httpx_mock(fake_tags)
        with patch("app.api.routes.models.httpx.AsyncClient", return_value=mock_client):
            resp = await test_client.get("/api/v1/models")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["models"]) == 2
        names = [m["name"] for m in data["models"]]
        assert "llama3.2" in names
        assert "mistral" in names

    async def test_model_size_converted_to_gb(self, test_client: AsyncClient) -> None:
        fake_tags = {"models": [{"name": "llama3.2", "size": 2_100_000_000, "details": {}}]}
        mock_client = _make_httpx_mock(fake_tags)
        with patch("app.api.routes.models.httpx.AsyncClient", return_value=mock_client):
            resp = await test_client.get("/api/v1/models")

        assert resp.status_code == 200
        m = resp.json()["models"][0]
        assert m["size_gb"] == pytest.approx(2.1, abs=0.1)

    async def test_empty_models_list(self, test_client: AsyncClient) -> None:
        mock_client = _make_httpx_mock({"models": []})
        with patch("app.api.routes.models.httpx.AsyncClient", return_value=mock_client):
            resp = await test_client.get("/api/v1/models")

        assert resp.status_code == 200
        assert resp.json()["models"] == []

    async def test_model_family_included(self, test_client: AsyncClient) -> None:
        fake_tags = {"models": [{"name": "llava", "size": 0, "details": {"family": "llava"}}]}
        mock_client = _make_httpx_mock(fake_tags)
        with patch("app.api.routes.models.httpx.AsyncClient", return_value=mock_client):
            resp = await test_client.get("/api/v1/models")

        assert resp.json()["models"][0]["family"] == "llava"


class TestGetActiveModel:
    async def test_returns_current_model(self, test_client: AsyncClient) -> None:
        resp = await test_client.get("/api/v1/models/active")
        assert resp.status_code == 200
        data = resp.json()
        assert "model" in data
        assert "provider" in data
        assert isinstance(data["model"], str)
        assert len(data["model"]) > 0

    async def test_provider_name_is_string(self, test_client: AsyncClient) -> None:
        resp = await test_client.get("/api/v1/models/active")
        assert isinstance(resp.json()["provider"], str)


class TestSetActiveModel:
    async def test_switches_model(self, test_client: AsyncClient) -> None:
        resp = await test_client.post(
            "/api/v1/models/active", json={"model": "mistral"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"] == "mistral"
        assert data["provider"] == "ollama"

    async def test_active_model_reflects_switch(self, test_client: AsyncClient) -> None:
        await test_client.post("/api/v1/models/active", json={"model": "llava"})
        resp = await test_client.get("/api/v1/models/active")
        assert resp.json()["model"] == "llava"

    async def test_empty_model_name_rejected(self, test_client: AsyncClient) -> None:
        resp = await test_client.post("/api/v1/models/active", json={"model": "  "})
        assert resp.status_code == 422

    async def test_switch_persists_across_requests(self, test_client: AsyncClient) -> None:
        await test_client.post("/api/v1/models/active", json={"model": "codellama"})
        r1 = await test_client.get("/api/v1/models/active")
        r2 = await test_client.get("/api/v1/models/active")
        assert r1.json()["model"] == r2.json()["model"] == "codellama"

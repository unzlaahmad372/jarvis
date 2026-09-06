"""Tests for Phases 24-28: settings, export, workspaces, search, plugins."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Workspace


async def _seed_workspace(session: AsyncSession, name: str = "default") -> Workspace:
    ws = Workspace(name=name, description="test", is_default=True)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return ws


# ── Settings ──────────────────────────────────────────────────────────────────


class TestSettingsAPI:
    async def test_get_returns_defaults(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.get("/api/v1/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "llm_model" in data
        assert "max_context_tokens" in data
        assert "log_level" in data

    async def test_patch_persists_value(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.post(
            "/api/v1/settings", json={"max_context_tokens": 4096}
        )
        assert resp.status_code == 200
        assert resp.json()["max_context_tokens"] == 4096

    async def test_patch_bool_field(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.post(
            "/api/v1/settings", json={"enable_voice": False}
        )
        assert resp.status_code == 200
        assert resp.json()["enable_voice"] is False

    async def test_patch_then_get_reflects_change(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await test_client.post("/api/v1/settings", json={"log_level": "DEBUG"})
        resp = await test_client.get("/api/v1/settings")
        assert resp.json()["log_level"] == "DEBUG"

    async def test_ollama_url_not_patchable(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        # ollama_url is not in SettingsPatch — should be ignored / 422
        resp = await test_client.post(
            "/api/v1/settings", json={"ollama_url": "http://evil.example.com"}
        )
        # Either 422 (validation) or 200 with original url unchanged
        if resp.status_code == 200:
            get_resp = await test_client.get("/api/v1/settings")
            assert "evil" not in get_resp.json()["ollama_url"]


# ── Export ────────────────────────────────────────────────────────────────────


class TestExportAPI:
    async def test_export_single_markdown(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        chat = await test_client.post(
            "/api/v1/chat", json={"message": "Export me", "stream": False}
        )
        conv_id = chat.json()["conversation_id"]

        resp = await test_client.get(
            f"/api/v1/export/conversations/{conv_id}?format=markdown"
        )
        assert resp.status_code == 200
        assert "Export me" in resp.text
        assert resp.headers["content-disposition"].endswith(".md\"")

    async def test_export_single_json(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        chat = await test_client.post(
            "/api/v1/chat", json={"message": "JSON export", "stream": False}
        )
        conv_id = chat.json()["conversation_id"]

        resp = await test_client.get(
            f"/api/v1/export/conversations/{conv_id}?format=json"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == conv_id
        assert any(m["content"] == "JSON export" for m in data["messages"])

    async def test_export_single_txt(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        chat = await test_client.post(
            "/api/v1/chat", json={"message": "TXT export", "stream": False}
        )
        conv_id = chat.json()["conversation_id"]

        resp = await test_client.get(
            f"/api/v1/export/conversations/{conv_id}?format=txt"
        )
        assert resp.status_code == 200
        assert "TXT export" in resp.text

    async def test_export_nonexistent_returns_404(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.get("/api/v1/export/conversations/99999")
        assert resp.status_code == 404

    async def test_export_all_json(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        await test_client.post("/api/v1/chat", json={"message": "A", "stream": False})
        await test_client.post("/api/v1/chat", json={"message": "B", "stream": False})

        resp = await test_client.get("/api/v1/export/conversations?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_export_invalid_format_rejected(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        chat = await test_client.post(
            "/api/v1/chat", json={"message": "fmt test", "stream": False}
        )
        conv_id = chat.json()["conversation_id"]
        resp = await test_client.get(
            f"/api/v1/export/conversations/{conv_id}?format=csv"
        )
        assert resp.status_code == 422


# ── Workspaces ────────────────────────────────────────────────────────────────


class TestWorkspacesAPI:
    async def test_list_empty(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.get("/api/v1/workspaces")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_workspace(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.post(
            "/api/v1/workspaces", json={"name": "Work", "description": "Work stuff"}
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Work"
        assert data["is_default"] is False

    async def test_create_duplicate_rejected(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await test_client.post("/api/v1/workspaces", json={"name": "Dup"})
        resp = await test_client.post("/api/v1/workspaces", json={"name": "Dup"})
        assert resp.status_code == 400

    async def test_activate_workspace(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        r1 = await test_client.post("/api/v1/workspaces", json={"name": "WS1"})
        r2 = await test_client.post("/api/v1/workspaces", json={"name": "WS2"})
        ws2_id = r2.json()["id"]

        resp = await test_client.post(f"/api/v1/workspaces/{ws2_id}/activate")
        assert resp.status_code == 200
        assert resp.json()["is_default"] is True

        # WS1 should no longer be default
        listed = await test_client.get("/api/v1/workspaces")
        ws1 = next(w for w in listed.json() if w["id"] == r1.json()["id"])
        assert ws1["is_default"] is False

    async def test_delete_default_rejected(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        ws = await _seed_workspace(db_session, name="main")
        resp = await test_client.delete(f"/api/v1/workspaces/{ws.id}")
        assert resp.status_code == 400

    async def test_delete_workspace_with_conversations_rejected(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        # Create a non-default workspace, seed a conversation in it
        await _seed_workspace(db_session, name="default")
        r = await test_client.post("/api/v1/workspaces", json={"name": "ToDelete"})
        ws_id = r.json()["id"]

        # Manually add a conversation to this workspace
        from app.db.models import Conversation
        conv = Conversation(workspace_id=ws_id, title="orphan")
        db_session.add(conv)
        await db_session.commit()

        resp = await test_client.delete(f"/api/v1/workspaces/{ws_id}")
        assert resp.status_code == 409

    async def test_delete_empty_workspace_succeeds(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        r = await test_client.post("/api/v1/workspaces", json={"name": "Empty"})
        ws_id = r.json()["id"]
        resp = await test_client.delete(f"/api/v1/workspaces/{ws_id}")
        assert resp.status_code == 204

    async def test_delete_nonexistent_returns_404(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.delete("/api/v1/workspaces/99999")
        assert resp.status_code == 404

    async def test_conversation_count_in_list(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        await test_client.post("/api/v1/chat", json={"message": "hi", "stream": False})
        resp = await test_client.get("/api/v1/workspaces")
        ws = resp.json()[0]
        assert ws["conversation_count"] == 1


# ── Conversation search ───────────────────────────────────────────────────────


class TestConversationSearch:
    async def test_search_by_title(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        chat = await test_client.post(
            "/api/v1/chat", json={"message": "unique_search_term_xyz", "stream": False}
        )
        conv_id = chat.json()["conversation_id"]

        resp = await test_client.get("/api/v1/conversations/search?q=unique_search_term_xyz")
        assert resp.status_code == 200
        ids = [c["id"] for c in resp.json()]
        assert conv_id in ids

    async def test_search_no_results(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.get("/api/v1/conversations/search?q=zzznomatch999")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_search_empty_query_rejected(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.get("/api/v1/conversations/search?q=")
        assert resp.status_code == 422

    async def test_search_limit_respected(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        for i in range(5):
            await test_client.post(
                "/api/v1/chat", json={"message": f"common_word {i}", "stream": False}
            )
        resp = await test_client.get("/api/v1/conversations/search?q=common_word&limit=3")
        assert resp.status_code == 200
        assert len(resp.json()) <= 3


# ── Plugins ───────────────────────────────────────────────────────────────────


class TestPluginsAPI:
    async def test_list_plugins_disabled_returns_empty(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        # enable_plugins defaults to False
        resp = await test_client.get("/api/v1/plugins")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_reload_plugins_disabled_returns_403(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.post("/api/v1/plugins/reload")
        assert resp.status_code == 403

    async def test_reload_plugins_enabled(
        self, test_client: AsyncClient, db_session: AsyncSession, tmp_path: pytest.TempPathFactory
    ) -> None:
        # Directly test _scan_plugins with an empty plugins dir — no mocking needed
        from pathlib import Path

        from app.api.routes.plugins import _scan_plugins
        plugins_dir = Path(str(tmp_path)) / "plugins"
        plugins_dir.mkdir()
        result = _scan_plugins(plugins_dir)
        assert isinstance(result, list)

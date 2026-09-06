"""Tests for Phase 33 — Conversation Pinning."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Workspace


async def _seed_workspace(session: AsyncSession) -> None:
    from sqlalchemy import select
    existing = (await session.execute(
        select(Workspace).where(Workspace.is_default == True)  # noqa: E712
    )).scalar_one_or_none()
    if not existing:
        session.add(Workspace(name="default", description="test", is_default=True))
        await session.commit()


class TestPinEndpoint:
    async def test_pin_unknown_conversation_returns_404(
        self, test_client: AsyncClient
    ) -> None:
        resp = await test_client.post("/api/v1/conversations/99999/pin")
        assert resp.status_code == 404

    async def test_pin_toggles_to_true(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        chat_resp = await test_client.post(
            "/api/v1/chat", json={"message": "hello", "stream": False}
        )
        conv_id = chat_resp.json()["conversation_id"]

        resp = await test_client.post(f"/api/v1/conversations/{conv_id}/pin")
        assert resp.status_code == 200
        data = resp.json()
        assert data["conversation_id"] == conv_id
        assert data["pinned"] is True

    async def test_pin_toggles_back_to_false(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        chat_resp = await test_client.post(
            "/api/v1/chat", json={"message": "hello", "stream": False}
        )
        conv_id = chat_resp.json()["conversation_id"]

        await test_client.post(f"/api/v1/conversations/{conv_id}/pin")
        resp = await test_client.post(f"/api/v1/conversations/{conv_id}/pin")
        assert resp.json()["pinned"] is False

    async def test_pinned_reflected_in_conversation_list(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        chat_resp = await test_client.post(
            "/api/v1/chat", json={"message": "hello", "stream": False}
        )
        conv_id = chat_resp.json()["conversation_id"]
        await test_client.post(f"/api/v1/conversations/{conv_id}/pin")

        list_resp = await test_client.get("/api/v1/conversations")
        convs = list_resp.json()
        match = next((c for c in convs if c["id"] == conv_id), None)
        assert match is not None
        assert match["pinned"] is True

    async def test_pinned_conversations_appear_first_in_list(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        r1 = await test_client.post(
            "/api/v1/chat", json={"message": "first", "stream": False}
        )
        r2 = await test_client.post(
            "/api/v1/chat", json={"message": "second", "stream": False}
        )
        id1 = r1.json()["conversation_id"]
        id2 = r2.json()["conversation_id"]

        await test_client.post(f"/api/v1/conversations/{id1}/pin")

        convs = (await test_client.get("/api/v1/conversations")).json()
        ids = [c["id"] for c in convs]
        assert ids.index(id1) < ids.index(id2)

    async def test_conversation_out_has_pinned_field(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        chat_resp = await test_client.post(
            "/api/v1/chat", json={"message": "hello", "stream": False}
        )
        conv_id = chat_resp.json()["conversation_id"]
        convs = (await test_client.get("/api/v1/conversations")).json()
        match = next(c for c in convs if c["id"] == conv_id)
        assert "pinned" in match
        assert match["pinned"] is False

    async def test_unpin_reflected_in_list(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        chat_resp = await test_client.post(
            "/api/v1/chat", json={"message": "hello", "stream": False}
        )
        conv_id = chat_resp.json()["conversation_id"]
        await test_client.post(f"/api/v1/conversations/{conv_id}/pin")
        await test_client.post(f"/api/v1/conversations/{conv_id}/pin")

        convs = (await test_client.get("/api/v1/conversations")).json()
        match = next(c for c in convs if c["id"] == conv_id)
        assert match["pinned"] is False

    async def test_multiple_pins_all_appear_first(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        ids = []
        for msg in ["a", "b", "c"]:
            r = await test_client.post(
                "/api/v1/chat", json={"message": msg, "stream": False}
            )
            ids.append(r.json()["conversation_id"])

        await test_client.post(f"/api/v1/conversations/{ids[0]}/pin")
        await test_client.post(f"/api/v1/conversations/{ids[1]}/pin")

        convs = (await test_client.get("/api/v1/conversations")).json()
        last_pinned_pos = max(convs.index(c) for c in convs if c["pinned"])
        first_unpinned_pos = min(convs.index(c) for c in convs if not c["pinned"])
        assert last_pinned_pos < first_unpinned_pos

"""Tests for Phase 14 — VisionTool."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.vision.tools import VisionTool


@pytest.fixture()
def tool() -> VisionTool:
    return VisionTool()


@pytest.mark.asyncio
async def test_vision_file_not_found(tool: VisionTool) -> None:
    result = await tool.execute({"image_path": "/nonexistent/image.png"})
    assert not result.success
    assert "not found" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_vision_unsupported_format(tool: VisionTool, tmp_path: Path) -> None:
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"fake")
    result = await tool.execute({"image_path": str(f)})
    assert not result.success
    assert "unsupported" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_vision_success(tool: VisionTool, tmp_path: Path) -> None:
    img = tmp_path / "test.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"response": "A plain white image."}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.tools.vision.tools.httpx.AsyncClient", return_value=mock_client):
        result = await tool.execute({"image_path": str(img), "prompt": "What is this?"})

    assert result.success
    assert "white" in result.output


@pytest.mark.asyncio
async def test_vision_http_error(tool: VisionTool, tmp_path: Path) -> None:
    img = tmp_path / "test.jpg"
    img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 50)

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.tools.vision.tools.httpx.AsyncClient", return_value=mock_client):
        result = await tool.execute({"image_path": str(img)})

    assert not result.success
    assert "connection refused" in (result.error or "")


def test_vision_tool_metadata(tool: VisionTool) -> None:
    assert tool.name == "vision_describe"
    assert tool.risk_level.value == "READ_ONLY"
    assert "image_path" in tool.parameters_schema["properties"]

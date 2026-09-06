"""VisionTool — describe or query an image using a local vision model.

Uses Ollama /api/generate with images field (base64).
Requires a vision-capable model: llava, bakllava, moondream, etc.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings
from app.tools.base import RiskLevel, Tool, ToolResult

_SUPPORTED = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


class VisionTool(Tool):
    """Analyse an image file using a local vision model."""

    @property
    def name(self) -> str:
        return "vision_describe"

    @property
    def description(self) -> str:
        return (
            "Describe or answer questions about an image file. "
            "Provide the absolute path to the image and an optional prompt."
        )

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Absolute path to the image file"},
                "prompt": {
                    "type": "string",
                    "description": "Question or instruction about the image",
                    "default": "Describe this image in detail.",
                },
            },
            "required": ["image_path"],
        }

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        settings = get_settings()
        image_path = Path(parameters["image_path"])
        prompt = str(parameters.get("prompt", "Describe this image in detail."))

        if not image_path.exists() or not image_path.is_file():
            return ToolResult(
                tool_name=self.name, success=False, output="",
                error=f"File not found: {image_path}",
            )
        if image_path.suffix.lower() not in _SUPPORTED:
            return ToolResult(
                tool_name=self.name, success=False, output="",
                error=f"Unsupported image format: {image_path.suffix}",
            )

        image_b64 = base64.b64encode(image_path.read_bytes()).decode()
        vision_model = getattr(settings, "vision_model", "llava")

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{settings.ollama_url}/api/generate",
                    json={
                        "model": vision_model,
                        "prompt": prompt,
                        "images": [image_b64],
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            return ToolResult(tool_name=self.name, success=True, output=data.get("response", ""))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))

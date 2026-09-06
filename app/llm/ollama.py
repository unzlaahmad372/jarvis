"""Ollama LLM provider — communicates with a local Ollama instance via HTTP."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx

from app.core.logging import get_logger
from app.core.telemetry import span
from app.llm.base import LLMProvider, LLMResponse, ModelCapabilities

logger = get_logger(__name__)

# Conservative fallback when Ollama cannot report context size
_FALLBACK_CONTEXT_WINDOW = 4096
# Safety margin reserved for system prompt + output generation
_SAFETY_MARGIN_TOKENS = 256


class OllamaProvider(LLMProvider):
    """LLM provider backed by a local Ollama instance."""

    def __init__(self, base_url: str, model: str, timeout: int = 120) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._capabilities_cache: ModelCapabilities | None = None

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(self, prompt: str, system: str | None = None) -> LLMResponse:
        """Send a non-streaming completion request to Ollama."""
        with span("llm.complete", {"llm.model": self._model, "llm.provider": "ollama"}):
            return await self._complete_inner(prompt, system)

    async def _complete_inner(self, prompt: str, system: str | None) -> LLMResponse:
        payload: dict[str, object] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(f"{self._base_url}/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()

        return LLMResponse(
            content=data.get("response", ""),
            model=data.get("model", self._model),
            provider=self.provider_name,
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
            finish_reason=data.get("done_reason"),
            raw=data,
        )

    async def complete_stream(
        self, prompt: str, system: str | None = None
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from Ollama as they are generated."""
        payload: dict[str, object] = {
            "model": self._model,
            "prompt": prompt,
            "stream": True,
        }
        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST", f"{self._base_url}/api/generate", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    import json as _json
                    try:
                        chunk = _json.loads(line)
                    except ValueError:
                        continue
                    token = chunk.get("response", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        break

    async def get_capabilities(self) -> ModelCapabilities:
        """Probe Ollama for model metadata and derive context capabilities."""
        if self._capabilities_cache is not None:
            return self._capabilities_cache

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"{self._base_url}/api/show",
                    json={"name": self._model},
                )
                response.raise_for_status()
                data = response.json()

            context_window = self._extract_context_window(data)
            caps = ModelCapabilities(
                context_window_tokens=context_window,
                max_output_tokens=None,
                supports_tools=False,
                supports_structured_output=False,
                source="provider",
            )
        except Exception as exc:
            logger.warning(
                "ollama_capability_probe_failed",
                model=self._model,
                error=str(exc),
                fallback_context=_FALLBACK_CONTEXT_WINDOW,
            )
            caps = ModelCapabilities(
                context_window_tokens=_FALLBACK_CONTEXT_WINDOW,
                source="fallback",
            )

        self._capabilities_cache = caps
        return caps

    def _extract_context_window(self, show_data: dict[str, object]) -> int | None:
        """Extract context window size from Ollama /api/show response."""
        model_info = show_data.get("model_info", {})
        if isinstance(model_info, dict):
            for key in model_info:
                if "context" in key.lower():
                    val = model_info[key]
                    if isinstance(val, int) and val > 0:
                        return val

        # Fallback: parse parameters string
        params_str = show_data.get("parameters", "")
        if isinstance(params_str, str):
            for line in params_str.splitlines():
                if "num_ctx" in line.lower():
                    parts = line.split()
                    for part in parts:
                        if part.isdigit():
                            return int(part)

        return None

    async def health_check(self) -> bool:
        """Return True if Ollama is reachable and the configured model exists."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                # Check Ollama is alive
                r = await client.get(f"{self._base_url}/api/tags")
                r.raise_for_status()
                tags = r.json()

            models = [m.get("name", "") for m in tags.get("models", [])]
            # Ollama model names may include tags like "llama3.2:latest"
            model_available = any(
                m == self._model or m.startswith(f"{self._model}:") for m in models
            )
            if not model_available:
                logger.warning(
                    "ollama_model_not_found",
                    model=self._model,
                    available=models,
                )
            return model_available
        except httpx.ConnectError:
            logger.warning("ollama_unreachable", url=self._base_url)
            return False
        except Exception as exc:
            logger.warning("ollama_health_check_failed", error=str(exc))
            return False

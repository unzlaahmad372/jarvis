"""Fake LLM provider for deterministic unit tests.

Never requires a live Ollama server. Supports configurable scenarios.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from enum import StrEnum

from app.llm.base import LLMProvider, LLMResponse, ModelCapabilities


class FakeScenario(StrEnum):
    NORMAL = "normal"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    MALFORMED = "malformed"
    CONTEXT_TOO_LARGE = "context_too_large"


class FakeLLMProvider(LLMProvider):
    """Deterministic LLM provider for tests."""

    def __init__(
        self,
        scenario: FakeScenario = FakeScenario.NORMAL,
        response_text: str = "This is a fake response.",
        context_window: int = 8192,
    ) -> None:
        self._scenario = scenario
        self._response_text = response_text
        self._context_window = context_window
        self.call_count = 0
        self.last_prompt: str | None = None
        self.last_system: str | None = None

    @property
    def provider_name(self) -> str:
        return "fake"

    @property
    def model_name(self) -> str:
        return "fake-model"

    async def complete(self, prompt: str, system: str | None = None) -> LLMResponse:
        self.call_count += 1
        self.last_prompt = prompt
        self.last_system = system

        if self._scenario == FakeScenario.TIMEOUT:
            raise TimeoutError("Fake timeout")
        if self._scenario == FakeScenario.UNAVAILABLE:
            raise ConnectionError("Fake provider unavailable")
        if self._scenario == FakeScenario.CONTEXT_TOO_LARGE:
            raise ValueError("Fake context too large")
        if self._scenario == FakeScenario.MALFORMED:
            raise ValueError("Fake malformed response")

        return LLMResponse(
            content=self._response_text,
            model=self.model_name,
            provider=self.provider_name,
            input_tokens=len(prompt) // 4,
            output_tokens=len(self._response_text) // 4,
            finish_reason="stop",
        )

    async def complete_stream(
        self, prompt: str, system: str | None = None
    ) -> AsyncGenerator[str, None]:
        # Yield response word-by-word for realistic fake streaming
        await self.complete(prompt, system)  # honour scenario checks
        for word in self._response_text.split():
            yield word + " "

    async def get_capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            context_window_tokens=self._context_window,
            max_output_tokens=2048,
            supports_tools=False,
            supports_structured_output=False,
            source="fake",
        )

    async def health_check(self) -> bool:
        return self._scenario not in (FakeScenario.UNAVAILABLE,)

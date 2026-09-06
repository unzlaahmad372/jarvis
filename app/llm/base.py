"""LLM provider abstraction — the rest of JARVIS depends on this interface, not on Ollama."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field


@dataclass
class ModelCapabilities:
    """Runtime capabilities reported by or inferred for the active model."""

    context_window_tokens: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool = False
    supports_structured_output: bool = False
    source: str = "unknown"  # "provider", "configured", "fallback"


@dataclass
class LLMResponse:
    """Structured response from an LLM provider."""

    content: str
    model: str
    provider: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    raw: dict[str, object] = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract base for all LLM providers.

    The application must never import a concrete provider directly.
    Use the provider returned by get_llm_provider().
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier, e.g. 'ollama'."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Currently configured model name."""

    @abstractmethod
    async def complete(self, prompt: str, system: str | None = None) -> LLMResponse:
        """Send a completion request and return a structured response."""

    @abstractmethod
    async def complete_stream(
        self, prompt: str, system: str | None = None
    ) -> AsyncGenerator[str, None]:
        """Stream completion tokens as they are generated."""
        yield ""  # pragma: no cover

    @abstractmethod
    async def get_capabilities(self) -> ModelCapabilities:
        """Probe and return model capabilities. May cache the result."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the provider is reachable and the model is available."""

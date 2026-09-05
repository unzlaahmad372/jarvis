"""JARVIS configuration — validated at startup via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM ──────────────────────────────────────────────────────────────────
    llm_provider: Literal["ollama"] = "ollama"
    llm_model: str = "llama3.2"
    ollama_url: str = "http://127.0.0.1:11434"
    allow_cloud: bool = False

    # ── Embedding ─────────────────────────────────────────────────────────────
    embedding_model: str = "nomic-embed-text"

    # ── Context / token budgets ───────────────────────────────────────────────
    max_context_tokens: int = 8192
    max_response_tokens: int = 2048
    recent_history_tokens: int = 2048
    rag_context_tokens: int = 3072
    memory_context_tokens: int = 512
    compaction_keep_recent: int = 4  # number of recent messages to keep verbatim

    # ── Inference guardrails ──────────────────────────────────────────────────
    max_concurrent_llm_requests: int = 2
    llm_request_timeout: int = 120
    max_queue_length: int = 10
    max_tool_output_size: int = 16384
    max_rag_chunks: int = 10

    # ── Data ──────────────────────────────────────────────────────────────────
    data_dir: Path = Path("./data")
    database_url: str = "sqlite+aiosqlite:///./data/database/jarvis.db"

    # ── RAG / knowledge ───────────────────────────────────────────────────────
    chunk_size: int = 512
    chunk_overlap: int = 64
    retrieval_top_k: int = 6
    retrieval_score_threshold: float = 0.0
    index_version: str = "1"

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 8000
    allowed_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ── Runtime ───────────────────────────────────────────────────────────────
    runtime_mode: Literal["native", "container"] = "native"

    # ── Safety ───────────────────────────────────────────────────────────────
    require_confirmation: bool = True

    # ── Retention ────────────────────────────────────────────────────────────
    conversation_retention_days: int = 365
    tool_log_retention_days: int = 90
    temp_retention_hours: int = 24

    # ── Kubernetes ─────────────────────────────────────────────────────────────────
    enable_kubernetes: bool = True
    k8s_protected_contexts: str = ""  # comma-separated context names treated as protected
    k8s_max_log_lines: int = 100
    k8s_fan_out_limit: int = 5  # max parallel cluster queries

    # ── Voice ─────────────────────────────────────────────────────────────────
    enable_voice: bool = True
    voice_auto_speak: bool = True

    # ── Feature flags ────────────────────────────────────────────────────────
    enable_cloud: bool = False
    enable_shell: bool = False
    enable_k8s_write: bool = False
    enable_remote_access: bool = False
    enable_always_listening: bool = False
    inbox_watcher_enabled: bool = False

    @field_validator("host")
    @classmethod
    def host_must_be_loopback(cls, v: str) -> str:
        """Enforce localhost-only binding unless remote access is explicitly enabled."""
        # Full remote-access check happens in model_validator below
        return v

    @model_validator(mode="after")
    def validate_security_constraints(self) -> Settings:
        if self.host not in ("127.0.0.1", "::1", "localhost") and not self.enable_remote_access:
            raise ValueError(
                f"JARVIS_HOST is set to '{self.host}' but JARVIS_ENABLE_REMOTE_ACCESS=false. "
                "Remote access is a separate security milestone. "
                "Set JARVIS_HOST=127.0.0.1 or explicitly enable remote access."
            )
        if self.allow_cloud and not self.enable_cloud:
            raise ValueError(
                "JARVIS_ALLOW_CLOUD=true requires JARVIS_ENABLE_CLOUD=true. "
                "Cloud processing requires explicit opt-in."
            )
        return self

    @property
    def k8s_protected_contexts_list(self) -> list[str]:
        return [c.strip() for c in self.k8s_protected_contexts.split(",") if c.strip()]

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def database_dir(self) -> Path:
        return self.data_dir / "database"

    @property
    def indexes_dir(self) -> Path:
        return self.data_dir / "indexes"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance. Call once at startup to validate."""
    return Settings()

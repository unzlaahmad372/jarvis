"""Tests for JARVIS configuration validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def make_settings(**overrides) -> Settings:
    """Create a Settings instance with test-safe defaults."""
    defaults = {
        "JARVIS_LLM_MODEL": "test-model",
        "JARVIS_DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    }
    defaults.update({f"JARVIS_{k.upper()}": v for k, v in overrides.items()})
    return Settings(**{k.replace("JARVIS_", "").lower(): v for k, v in defaults.items()})


def test_default_host_is_loopback():
    s = Settings(_env_file=None)
    assert s.host == "127.0.0.1"


def test_allowed_origins_list_parsed():
    s = Settings(
        _env_file=None,
        allowed_origins="http://127.0.0.1:5173,http://localhost:5173",
    )
    assert "http://127.0.0.1:5173" in s.allowed_origins_list
    assert "http://localhost:5173" in s.allowed_origins_list


def test_cloud_disabled_by_default():
    s = Settings(_env_file=None)
    assert s.allow_cloud is False
    assert s.enable_cloud is False


def test_all_feature_flags_off_by_default():
    s = Settings(_env_file=None)
    assert s.enable_shell is False
    assert s.enable_k8s_write is False
    assert s.enable_remote_access is False
    assert s.enable_always_listening is False
    assert s.inbox_watcher_enabled is False


def test_remote_host_rejected_without_flag():
    with pytest.raises(ValidationError, match="JARVIS_ENABLE_REMOTE_ACCESS"):
        Settings(_env_file=None, host="0.0.0.0", enable_remote_access=False)  # noqa: S104


def test_remote_host_allowed_with_flag():
    s = Settings(_env_file=None, host="0.0.0.0", enable_remote_access=True)  # noqa: S104
    assert s.host == "0.0.0.0"  # noqa: S104


def test_allow_cloud_requires_enable_cloud():
    with pytest.raises(ValidationError, match="JARVIS_ENABLE_CLOUD"):
        Settings(_env_file=None, allow_cloud=True, enable_cloud=False)


def test_database_dir_property():
    s = Settings(_env_file=None)
    assert s.database_dir == s.data_dir / "database"


def test_log_level_default():
    s = Settings(_env_file=None)
    assert s.log_level == "INFO"


def test_inference_guardrail_defaults():
    s = Settings(_env_file=None)
    assert s.max_concurrent_llm_requests >= 1
    assert s.llm_request_timeout > 0
    assert s.max_queue_length > 0

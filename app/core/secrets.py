"""Startup secrets validation for JARVIS.

Validates that sensitive configuration values are not left at insecure defaults
before the application begins serving requests.

Rules:
  - auth_secret_key must not be the shipped placeholder value
  - auth_secret_key must be at least 32 characters
  - Warnings are emitted for non-fatal issues; errors raise ValueError
"""

from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_SECRET = "change-me-in-production-use-a-long-random-secret"  # noqa: S105
_MIN_SECRET_LENGTH = 32


class SecretsValidationError(ValueError):
    """Raised when a required secret fails validation."""


def validate_secrets(secret_key: str, *, remote_access_enabled: bool) -> list[str]:
    """Validate secret configuration.  Returns a list of warning strings.

    Raises SecretsValidationError if remote access is enabled and the secret
    key is insecure (default value or too short).

    When remote access is disabled, insecure keys produce warnings only so
    that local-only development still works out of the box.
    """
    warnings: list[str] = []

    is_default = secret_key == _DEFAULT_SECRET
    is_short = len(secret_key) < _MIN_SECRET_LENGTH

    if is_default:
        msg = (
            "JARVIS_AUTH_SECRET_KEY is set to the default placeholder value. "
            "Generate a strong random secret before enabling remote access."
        )
        if remote_access_enabled:
            raise SecretsValidationError(msg)
        warnings.append(msg)
        logger.warning("insecure_default_secret_key")

    elif is_short:
        msg = (
            f"JARVIS_AUTH_SECRET_KEY is only {len(secret_key)} characters. "
            f"Use at least {_MIN_SECRET_LENGTH} characters for adequate security."
        )
        if remote_access_enabled:
            raise SecretsValidationError(msg)
        warnings.append(msg)
        logger.warning("short_secret_key", length=len(secret_key))

    else:
        logger.info("secret_key_ok", length=len(secret_key))

    return warnings

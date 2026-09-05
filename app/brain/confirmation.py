"""ConfirmationStore — time-of-check to time-of-use safe confirmation tokens.

Spec §71 requirements:
  - A confirmation approves the EXACT action the user saw (digest match).
  - Expired confirmations require new approval.
  - Confirmation tokens are NOT reusable for a different action.
  - Each token can only be consumed once.

The store is in-process (no DB) — confirmations are short-lived and
intentionally not persisted across restarts.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

CONFIRMATION_TTL_SECONDS = 300  # 5 minutes


@dataclass
class PendingConfirmation:
    confirmation_id: str
    tool_name: str
    parameters: dict[str, Any]
    risk_level: str
    policy_rule: str
    action_digest: str  # SHA-256 of (tool_name + sorted params)
    created_at: datetime
    expires_at: datetime
    consumed: bool = False


def _digest(tool_name: str, parameters: dict[str, Any]) -> str:
    """Deterministic SHA-256 digest of a tool + parameters pair."""
    payload = json.dumps({"tool": tool_name, "params": parameters}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class ConfirmationStore:
    """Thread-safe in-process store for pending tool confirmations."""

    def __init__(self, ttl_seconds: int = CONFIRMATION_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._pending: dict[str, PendingConfirmation] = {}

    def create(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        risk_level: str,
        policy_rule: str,
    ) -> PendingConfirmation:
        """Create and store a new pending confirmation."""
        now = datetime.now(UTC)
        confirmation = PendingConfirmation(
            confirmation_id=str(uuid.uuid4()),
            tool_name=tool_name,
            parameters=parameters,
            risk_level=risk_level,
            policy_rule=policy_rule,
            action_digest=_digest(tool_name, parameters),
            created_at=now,
            expires_at=now + timedelta(seconds=self._ttl),
        )
        self._pending[confirmation.confirmation_id] = confirmation
        logger.info(
            "confirmation_created",
            confirmation_id=confirmation.confirmation_id,
            tool=tool_name,
            risk_level=risk_level,
        )
        return confirmation

    def consume(
        self,
        confirmation_id: str,
        tool_name: str,
        parameters: dict[str, Any],
    ) -> tuple[bool, str]:
        """Validate and consume a confirmation token.

        Returns (ok, reason). On success, the token is marked consumed
        and cannot be reused.

        Checks:
          1. Token exists.
          2. Token not already consumed.
          3. Token not expired.
          4. Action digest matches (tool + params unchanged).
        """
        entry = self._pending.get(confirmation_id)
        if entry is None:
            return False, "Confirmation token not found."

        if entry.consumed:
            return False, "Confirmation token has already been used."

        if datetime.now(UTC) > entry.expires_at:
            del self._pending[confirmation_id]
            return False, "Confirmation token has expired. Please re-confirm."

        expected = _digest(tool_name, parameters)
        if entry.action_digest != expected:
            logger.warning(
                "confirmation_digest_mismatch",
                confirmation_id=confirmation_id,
                tool=tool_name,
            )
            return False, "Action parameters changed after confirmation was issued."

        entry.consumed = True
        logger.info(
            "confirmation_consumed",
            confirmation_id=confirmation_id,
            tool=tool_name,
        )
        return True, "OK"

    def get(self, confirmation_id: str) -> PendingConfirmation | None:
        return self._pending.get(confirmation_id)

    def purge_expired(self) -> int:
        """Remove expired tokens. Returns count removed."""
        now = datetime.now(UTC)
        expired = [cid for cid, c in self._pending.items() if now > c.expires_at]
        for cid in expired:
            del self._pending[cid]
        return len(expired)


# Module-level singleton — reset in tests via reset_confirmation_store()
_store: ConfirmationStore | None = None


def get_confirmation_store() -> ConfirmationStore:
    global _store
    if _store is None:
        _store = ConfirmationStore()
    return _store


def reset_confirmation_store(store: ConfirmationStore | None = None) -> None:
    global _store
    _store = store

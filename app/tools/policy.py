"""PolicyEngine — deterministic tool authorization.

The LLM proposes. The PolicyEngine decides. Never the other way around.

Rules (in priority order):
  1. DANGEROUS  → always REQUIRES_CONFIRMATION (never auto-approved)
  2. SENSITIVE  → REQUIRES_CONFIRMATION unless confirmation_id provided
  3. LOW_RISK   → ALLOW (configurable to REQUIRES_CONFIRMATION)
  4. READ_ONLY  → ALLOW

Feature flags can disable entire risk tiers (e.g. enable_shell=false blocks
any tool that would require shell access — enforced at registration time via
tool naming conventions or explicit flag checks).
"""

from __future__ import annotations

from app.core.config import Settings
from app.tools.base import PolicyDecision, PolicyDecisionType, RiskLevel, ToolRequest

POLICY_VERSION = "1.0"


class PolicyEngine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def evaluate(self, request: ToolRequest, risk_level: RiskLevel) -> PolicyDecision:
        """Return a deterministic PolicyDecision for the given tool request."""

        # DANGEROUS — always requires explicit confirmation, no exceptions
        if risk_level == RiskLevel.DANGEROUS:
            return PolicyDecision(
                decision=PolicyDecisionType.REQUIRES_CONFIRMATION,
                risk_level=risk_level,
                tool_name=request.tool_name,
                policy_rule="DANGEROUS_ALWAYS_CONFIRM",
                reason=(
                    "This operation is classified DANGEROUS and always requires "
                    "explicit confirmation before execution."
                ),
            )

        # SENSITIVE — requires confirmation unless a valid confirmation_id is present
        if risk_level == RiskLevel.SENSITIVE:
            if request.confirmation_id:
                return PolicyDecision(
                    decision=PolicyDecisionType.ALLOW,
                    risk_level=risk_level,
                    tool_name=request.tool_name,
                    policy_rule="SENSITIVE_CONFIRMED",
                    reason="Sensitive action approved via confirmation.",
                )
            return PolicyDecision(
                decision=PolicyDecisionType.REQUIRES_CONFIRMATION,
                risk_level=risk_level,
                tool_name=request.tool_name,
                policy_rule="SENSITIVE_ACTION_CONFIRMATION",
                reason=(
                    "This operation is classified SENSITIVE and requires "
                    "explicit confirmation before execution."
                ),
            )

        # LOW_RISK — allowed by default; require_confirmation setting can tighten this
        if risk_level == RiskLevel.LOW_RISK:
            if self._settings.require_confirmation:
                if request.confirmation_id:
                    return PolicyDecision(
                        decision=PolicyDecisionType.ALLOW,
                        risk_level=risk_level,
                        tool_name=request.tool_name,
                        policy_rule="LOW_RISK_CONFIRMED",
                        reason="Low-risk action approved via confirmation.",
                    )
                return PolicyDecision(
                    decision=PolicyDecisionType.REQUIRES_CONFIRMATION,
                    risk_level=risk_level,
                    tool_name=request.tool_name,
                    policy_rule="LOW_RISK_CONFIRMATION_REQUIRED",
                    reason=(
                        "Low-risk action requires confirmation "
                        "(JARVIS_REQUIRE_CONFIRMATION=true)."
                    ),
                )
            return PolicyDecision(
                decision=PolicyDecisionType.ALLOW,
                risk_level=risk_level,
                tool_name=request.tool_name,
                policy_rule="LOW_RISK_AUTO_ALLOW",
                reason="Low-risk read/create action is permitted.",
            )

        # READ_ONLY — always allowed
        return PolicyDecision(
            decision=PolicyDecisionType.ALLOW,
            risk_level=risk_level,
            tool_name=request.tool_name,
            policy_rule="READ_ONLY_ALLOW",
            reason="Read-only operations are always permitted.",
        )

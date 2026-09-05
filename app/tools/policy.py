"""PolicyEngine — deterministic tool authorization.

The LLM proposes. The PolicyEngine decides. Never the other way around.

Rules (in priority order):
  1. DANGEROUS  → always REQUIRES_CONFIRMATION (never auto-approved)
  2. SENSITIVE  → REQUIRES_CONFIRMATION unless a *validated* confirmation_id is present
  3. LOW_RISK   → ALLOW (configurable to REQUIRES_CONFIRMATION)
  4. READ_ONLY  → ALLOW

Confirmation validation:
  confirmation_id is validated against ConfirmationStore.consume() inside
  ToolExecutor before PolicyEngine is called with confirmed=True.  PolicyEngine
  itself never trusts a raw confirmation_id string — it only trusts the
  `confirmed` flag that ToolExecutor sets after successful consume().
"""

from __future__ import annotations

from app.core.config import Settings
from app.tools.base import PolicyDecision, PolicyDecisionType, RiskLevel, ToolRequest

POLICY_VERSION = "1.0"


class PolicyEngine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def evaluate(
        self,
        request: ToolRequest,
        risk_level: RiskLevel,
        *,
        confirmed: bool = False,
    ) -> PolicyDecision:
        """Return a deterministic PolicyDecision for the given tool request.

        Args:
            request: The tool request.
            risk_level: The tool's risk classification.
            confirmed: True only when ToolExecutor has already validated the
                confirmation token via ConfirmationStore.consume().  Never set
                this based on the raw presence of confirmation_id.
        """

        # DANGEROUS — always requires explicit confirmation, no exceptions
        if risk_level == RiskLevel.DANGEROUS:
            if confirmed:
                return PolicyDecision(
                    decision=PolicyDecisionType.ALLOW,
                    risk_level=risk_level,
                    tool_name=request.tool_name,
                    policy_rule="DANGEROUS_CONFIRMED",
                    reason="Dangerous action approved via validated confirmation.",
                )
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

        # SENSITIVE — requires confirmation unless token was validated
        if risk_level == RiskLevel.SENSITIVE:
            if confirmed:
                return PolicyDecision(
                    decision=PolicyDecisionType.ALLOW,
                    risk_level=risk_level,
                    tool_name=request.tool_name,
                    policy_rule="SENSITIVE_CONFIRMED",
                    reason="Sensitive action approved via validated confirmation.",
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
                if confirmed:
                    return PolicyDecision(
                        decision=PolicyDecisionType.ALLOW,
                        risk_level=risk_level,
                        tool_name=request.tool_name,
                        policy_rule="LOW_RISK_CONFIRMED",
                        reason="Low-risk action approved via validated confirmation.",
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

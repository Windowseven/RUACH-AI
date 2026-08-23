"""Deterministic policy evaluation: ALLOW / DENY / REQUIRE_APPROVAL (docs/05 §51–§53)."""

from __future__ import annotations

from .paths import PathOutsideWorkspaceError, WorkspaceBoundary
from .schemas import (
    PolicyDecision,
    PolicyOutcome,
    RiskLevel,
    ToolRequest,
)

CAPABILITY_RISK: dict[str, RiskLevel] = {
    "filesystem.read": RiskLevel.READ_ONLY,
    "filesystem.list": RiskLevel.READ_ONLY,
    "filesystem.write": RiskLevel.LOW,
    "filesystem.delete": RiskLevel.DESTRUCTIVE,
}


class PolicyEngine:
    def __init__(self, boundary: WorkspaceBoundary) -> None:
        self._boundary = boundary

    def risk_for(self, capability: str) -> RiskLevel | None:
        return CAPABILITY_RISK.get(capability)

    def evaluate(self, request: ToolRequest) -> PolicyOutcome:
        try:
            return self._evaluate(request)
        except PathOutsideWorkspaceError:
            raise
        except Exception as exc:  # noqa: BLE001 - fail-closed is mandatory (docs/05 §3.5)
            return PolicyOutcome(
                PolicyDecision.DENY,
                f"Policy evaluation failed closed: {type(exc).__name__}",
                RiskLevel.SENSITIVE,
            )

    def _evaluate(self, request: ToolRequest) -> PolicyOutcome:
        risk = CAPABILITY_RISK.get(request.capability)
        if risk is None:
            return PolicyOutcome(
                PolicyDecision.DENY,
                "Unknown or unregistered capability",
                RiskLevel.SENSITIVE,
            )

        target = request.arguments.get("path")
        if isinstance(target, str):
            self._boundary.resolve_within(target)
        elif target is not None:
            return PolicyOutcome(PolicyDecision.DENY, "Path argument must be a string", risk)

        if risk == RiskLevel.DESTRUCTIVE:
            return PolicyOutcome(
                PolicyDecision.REQUIRE_APPROVAL,
                "Destructive operation requires explicit approval",
                risk,
            )
        return PolicyOutcome(PolicyDecision.ALLOW, "Within workspace policy", risk)

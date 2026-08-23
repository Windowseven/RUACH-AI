"""ToolEngine facade: validate → policy → approval → execute → audit.

Invariants enforced here (docs/05 §54): AI output never executes directly,
every execution passes policy, sensitive ops need external authorization,
authorization can never come from model-generated content, failures close.
"""

from __future__ import annotations

import time
from typing import Any

from .approvals import ApprovalStore, action_fingerprint
from .audit import AuditLog
from .filesystem import FilesystemExecutor
from .paths import PathOutsideWorkspaceError, WorkspaceBoundary
from .policy import PolicyEngine
from .schemas import (
    ApprovalError,
    InvalidToolRequestError,
    PolicyDecision,
    PolicyOutcome,
    ToolOutcome,
    ToolRequest,
)

EXECUTORS = {
    "filesystem.read": FilesystemExecutor.read_file,
    "filesystem.list": FilesystemExecutor.list_directory,
    "filesystem.write": FilesystemExecutor.write_file,
    "filesystem.delete": FilesystemExecutor.delete_file,
}

# Honest user-facing text for infrastructure failures. Deliberately NOT a
# security refusal: policy denials and system errors are different events
# (docs/13 P4 #7-#9). Both fail closed; only one is a denial.
SYSTEM_ERROR_TEXT = (
    "RUACH could not complete the operation because an internal "
    "system error occurred. Nothing was executed."
)


class ToolEngine:
    def __init__(
        self,
        boundary: WorkspaceBoundary,
        approvals: ApprovalStore,
        audit: AuditLog,
        max_tool_calls_per_request: int = 8,
        clock: Any = time.time,
    ) -> None:
        self._boundary = boundary
        self._policy = PolicyEngine(boundary)
        self._approvals = approvals
        self._fs = FilesystemExecutor(boundary)
        self._audit = audit
        self._max_calls = max_tool_calls_per_request
        self._clock = clock

    def submit(
        self, request: ToolRequest, conversation_id: str | None = None
    ) -> ToolOutcome:
        started = self._clock()
        try:
            request = self._validate(request)
            outcome = self._policy.evaluate(request)
            if outcome.decision == PolicyDecision.DENY:
                return self._denied(request, outcome)
            if outcome.decision == PolicyDecision.REQUIRE_APPROVAL:
                return self._awaiting(request, outcome, conversation_id, started)

            result = self._execute_classified(request, started)
            self._audit_emit(request, outcome, "tool_executed", started, ok=True)
            return result
        except PathOutsideWorkspaceError as exc:
            self._security_event(request, started, str(exc))
            return ToolOutcome(state="DENIED", reason="Path escapes the approved workspace")
        except InvalidToolRequestError as exc:
            self._audit.emit(
                "tool_invalid",
                tool=request.tool,
                capability=request.capability,
                reason=str(exc),
            )
            return ToolOutcome(state="DENIED", reason=str(exc))
        except Exception as exc:  # noqa: BLE001
            # Fail-closed: no execution. But an infrastructure failure is NOT
            # a policy denial and must never emit a security event (P4 #7-#9).
            self._infrastructure_error(exc, phase="submit", approval_id=None)
            return ToolOutcome(state="SYSTEM_ERROR", reason=SYSTEM_ERROR_TEXT)

    def _execute_classified(
        self, request: ToolRequest, started: float
    ) -> ToolOutcome:
        """Execute with failure classes separated (docs/13 P4 #7-#9).

        ValueError from the executor is a deterministic validation/policy-cap
        boundary (size caps, argument types) -> DENIED + tool_invalid.
        Anything else during execution -> FAILED + tool_failed.
        """
        try:
            return self._execute(request)
        except PathOutsideWorkspaceError:
            self._security_event(request, started, "path escape at execution")
            return ToolOutcome(state="DENIED", reason="Path escapes the approved workspace")
        except ValueError as exc:
            self._audit.emit(
                "tool_invalid",
                tool=request.tool,
                capability=request.capability,
                category="validation",
                reason=str(exc),
            )
            return ToolOutcome(state="DENIED", reason=str(exc))
        except Exception as exc:  # noqa: BLE001 - tool failures must not escape
            self._audit.emit(
                "tool_failed",
                tool=request.tool,
                capability=request.capability,
                reason=type(exc).__name__,
                duration_ms=self._ms(started),
            )
            return ToolOutcome(state="FAILED", reason=str(exc))

    def _awaiting(
        self,
        request: ToolRequest,
        outcome: PolicyOutcome,
        conversation_id: str | None,
        started: float,
    ) -> ToolOutcome:
        """Create the pending approval; store outages are SYSTEM_ERROR."""
        try:
            return self._awaiting_approval(request, outcome, conversation_id)
        except Exception as exc:  # noqa: BLE001 - store outage != denial
            self._infrastructure_error(exc, phase="approval_creation", approval_id=None)
            return ToolOutcome(state="SYSTEM_ERROR", reason=SYSTEM_ERROR_TEXT)

    def _infrastructure_error(
        self, exc: Exception, phase: str, approval_id: str | None
    ) -> None:
        """Audit an infrastructure failure WITHOUT emitting a security event."""
        self._audit.emit(
            "tool_execution_error",
            category="infrastructure",
            error_type=type(exc).__name__,
            phase=phase,
            **({"approval_id": approval_id} if approval_id else {}),
        )

    def approve_and_execute(self, approval_id: str) -> ToolOutcome:
        try:
            record = self._approvals.get(approval_id)
        except ApprovalError as exc:
            return ToolOutcome(state="DENIED", reason=str(exc))
        if record.state.value != "PENDING":
            return ToolOutcome(state="DENIED", reason=f"Approval is {record.state.value}")
        fingerprint = action_fingerprint(
            record.tool, record.capability, record.arguments
        )
        try:
            self._approvals.approve(approval_id, fingerprint)
            arguments = dict(record.arguments)
            self._approvals.consume(approval_id)
        except ApprovalError as exc:
            return ToolOutcome(state="DENIED", reason=str(exc))
        except Exception as exc:  # noqa: BLE001 - store outage != denial
            self._infrastructure_error(exc, phase="approval_resolution", approval_id=approval_id)
            return ToolOutcome(state="SYSTEM_ERROR", reason=SYSTEM_ERROR_TEXT)

        request = ToolRequest(tool=record.tool, capability=record.capability, arguments=arguments)
        started = self._clock()
        outcome = PolicyOutcome(PolicyDecision.ALLOW, "Approved by user", record.risk_level)
        try:
            result = self._execute(request)
        except PathOutsideWorkspaceError:
            self._security_event(request, started, "path escape at execution")
            return ToolOutcome(state="DENIED", reason="Path escapes the approved workspace")
        except Exception as exc:  # noqa: BLE001 - tool failures must not escape
            self._audit.emit(
                "tool_failed",
                tool=request.tool,
                capability=request.capability,
                risk_level=record.risk_level.name,
                reason=type(exc).__name__,
                duration_ms=self._ms(started),
            )
            return ToolOutcome(state="FAILED", reason=str(exc), approval_id=approval_id)
        self._audit_emit(request, outcome, "tool_executed", started, ok=True)
        return ToolOutcome(state=result.state, output=result.output, approval_id=approval_id)

    def reject(self, approval_id: str) -> ToolOutcome:
        try:
            self._approvals.reject(approval_id)
        except ApprovalError as exc:
            return ToolOutcome(state="DENIED", reason=str(exc))
        except Exception as exc:  # noqa: BLE001 - store outage != denial
            self._infrastructure_error(exc, phase="approval_rejection", approval_id=approval_id)
            return ToolOutcome(state="SYSTEM_ERROR", reason=SYSTEM_ERROR_TEXT)
        self._audit.emit("tool_rejected_by_user")
        return ToolOutcome(state="REJECTED")

    def capability_for(self, approval_id: str) -> str:
        record = self.approval_info(approval_id)
        return record.capability if record is not None else "unknown"

    def approval_info(self, approval_id: str) -> Any:
        """Non-raising record read for UX/routing; None if unknown."""
        return self._approvals.peek(approval_id)

    def pending_conversation(self, approval_id: str) -> str | None:
        record = self.approval_info(approval_id)
        return record.conversation_id if record is not None else None

    def expire_stale_approvals(self) -> int:
        """Startup sweep: stale PENDING become explicitly EXPIRED (docs/13 P4)."""
        expire_stale = getattr(self._approvals, "expire_stale", None)
        return int(expire_stale()) if callable(expire_stale) else 0

    # ------------------------------------------------------------------
    def _validate(self, request: ToolRequest) -> ToolRequest:
        if not isinstance(request.tool, str) or not request.tool.strip():
            raise InvalidToolRequestError("Tool id is required")
        if request.capability not in EXECUTORS:
            raise InvalidToolRequestError("Capability has no registered executor")
        if not isinstance(request.arguments, dict):
            raise InvalidToolRequestError("Arguments must be an object")
        # Model-supplied authorization fields are stripped and ignored (§25/§61).
        cleaned = {k: v for k, v in request.arguments.items() if k != "approved"}
        return ToolRequest(
            tool=request.tool,
            capability=request.capability,
            arguments=cleaned,
            request_id=request.request_id,
        )

    def _awaiting_approval(
        self,
        request: ToolRequest,
        outcome: PolicyOutcome,
        conversation_id: str | None = None,
    ) -> ToolOutcome:
        record = self._approvals.create_pending(
            request.tool,
            request.capability,
            dict(request.arguments),
            request.arguments.get("path"),
            conversation_id=conversation_id,
        )
        self._audit.emit(
            "tool_awaiting_approval",
            tool=request.tool,
            capability=request.capability,
            risk_level=outcome.risk_level.name,
            target=record.target,
            approval_id=record.approval_id,
        )
        return ToolOutcome(
            state="AWAITING_APPROVAL",
            reason=outcome.reason,
            approval_id=record.approval_id,
        )

    def _denied(self, request: ToolRequest, outcome: PolicyOutcome) -> ToolOutcome:
        self._audit.emit(
            "tool_denied",
            tool=request.tool,
            capability=request.capability,
            risk_level=outcome.risk_level.name,
            reason=outcome.reason,
        )
        return ToolOutcome(state="DENIED", reason=outcome.reason)

    def _execute(self, request: ToolRequest) -> ToolOutcome:
        executor = EXECUTORS[request.capability]
        output = executor(self._fs, request.arguments)
        return ToolOutcome(state="COMPLETED", output=output)

    def _audit_emit(
        self,
        request: ToolRequest,
        outcome: PolicyOutcome,
        event: str,
        started: float,
        ok: bool,
    ) -> None:
        self._audit.emit(
            event,
            tool=request.tool,
            capability=request.capability,
            risk_level=outcome.risk_level.name,
            ok=ok,
            duration_ms=self._ms(started),
        )

    def _security_event(self, request: ToolRequest, started: float, detail: str) -> None:
        self._audit.emit(
            "security_violation",
            tool=request.tool,
            capability=request.capability,
            detail=detail,
            duration_ms=self._ms(started),
        )

    def _ms(self, started: float) -> float:
        return round((self._clock() - started) * 1000, 2)

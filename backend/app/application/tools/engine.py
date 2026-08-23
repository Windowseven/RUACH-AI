"""ToolEngine facade: validate → policy → approval → execute → audit.

Invariants enforced here (docs/05 §54): AI output never executes directly,
every execution passes policy, sensitive ops need external authorization,
authorization can never come from model-generated content, failures close.
"""

from __future__ import annotations

import time
from typing import Any

from .approvals import InMemoryApprovalStore, action_fingerprint
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


class ToolEngine:
    def __init__(
        self,
        boundary: WorkspaceBoundary,
        approvals: InMemoryApprovalStore,
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
        self._pending_arguments: dict[str, dict[str, Any]] = {}

    def submit(self, request: ToolRequest) -> ToolOutcome:
        started = self._clock()
        try:
            request = self._validate(request)
            outcome = self._policy.evaluate(request)
            if outcome.decision == PolicyDecision.DENY:
                return self._denied(request, outcome)
            if outcome.decision == PolicyDecision.REQUIRE_APPROVAL:
                return self._awaiting_approval(request, outcome)

            result = self._execute(request)
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
        except Exception as exc:  # noqa: BLE001 - fail-closed is mandatory (docs/05 §3.5)
            self._security_event(request, started, f"unexpected {type(exc).__name__}")
            return ToolOutcome(state="DENIED", reason="Operation denied by security policy")

    def approve_and_execute(self, approval_id: str) -> ToolOutcome:
        try:
            record = self._approvals.get(approval_id)
        except ApprovalError as exc:
            return ToolOutcome(state="DENIED", reason=str(exc))
        if record.state.value != "PENDING":
            return ToolOutcome(state="DENIED", reason=f"Approval is {record.state.value}")
        fingerprint = action_fingerprint(
            record.tool, record.capability, self._pending_arguments[approval_id]
        )
        try:
            self._approvals.approve(approval_id, fingerprint)
            arguments = self._pending_arguments.pop(approval_id)
            self._approvals.consume(approval_id)
        except ApprovalError as exc:
            return ToolOutcome(state="DENIED", reason=str(exc))

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
            self._pending_arguments.pop(approval_id, None)
        except ApprovalError as exc:
            return ToolOutcome(state="DENIED", reason=str(exc))
        self._audit.emit("tool_rejected_by_user")
        return ToolOutcome(state="REJECTED")

    def capability_for(self, approval_id: str) -> str:
        try:
            return self._approvals.get(approval_id).capability
        except ApprovalError:
            return "unknown"

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

    def _awaiting_approval(self, request: ToolRequest, outcome: PolicyOutcome) -> ToolOutcome:
        record = self._approvals.create_pending(
            request.tool,
            request.capability,
            request.arguments,
            request.arguments.get("path"),
        )
        self._pending_arguments[record.approval_id] = request.arguments
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

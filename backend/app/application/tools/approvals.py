"""Approval store with binding + single use (docs/05 §21–§25)."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import replace
from typing import Any

from .policy import CAPABILITY_RISK
from .schemas import ApprovalError, ApprovalRecord, ApprovalState, RiskLevel


def action_fingerprint(tool: str, capability: str, arguments: dict[str, Any]) -> str:
    payload = json.dumps(
        {"tool": tool, "capability": capability, "arguments": arguments},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class InMemoryApprovalStore:
    def __init__(self, ttl_seconds: float = 300.0, clock: Any = time.time) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._records: dict[str, ApprovalRecord] = {}

    def create_pending(
        self, tool: str, capability: str, arguments: dict[str, Any], target: str | None
    ) -> ApprovalRecord:
        now = self._clock()
        record = ApprovalRecord(
            approval_id=secrets.token_hex(16),
            tool=tool,
            capability=capability,
            arguments_digest=action_fingerprint(tool, capability, arguments),
            target=target,
            risk_level=CAPABILITY_RISK.get(capability, RiskLevel.SENSITIVE),
            state=ApprovalState.PENDING,
            created_at=now,
            expires_at=now + self._ttl,
        )
        self._records[record.approval_id] = record
        return record

    def get(self, approval_id: str) -> ApprovalRecord:
        record = self._records.get(approval_id)
        if record is None:
            raise ApprovalError("Unknown approval id")
        if record.state == ApprovalState.PENDING and self._clock() > record.expires_at:
            self._records[approval_id] = _with_state(record, ApprovalState.EXPIRED)
            raise ApprovalError("Approval has expired")
        return self._records[approval_id]

    def approve(self, approval_id: str, fingerprint: str) -> ApprovalRecord:
        record = self._require_pending(approval_id)
        if record.arguments_digest != fingerprint:
            raise ApprovalError("Action changed after approval request; approval is invalid")
        approved = _with_state(record, ApprovalState.APPROVED)
        self._records[approval_id] = approved
        return approved

    def reject(self, approval_id: str) -> ApprovalRecord:
        record = self._require_pending(approval_id)
        rejected = _with_state(record, ApprovalState.REJECTED)
        self._records[approval_id] = rejected
        return rejected

    def consume(self, approval_id: str) -> None:
        record = self.get(approval_id)
        if record.state != ApprovalState.APPROVED:
            raise ApprovalError(f"Approval is not executable (state={record.state.value})")
        self._records[approval_id] = _with_state(record, ApprovalState.CONSUMED)

    def _require_pending(self, approval_id: str) -> ApprovalRecord:
        record = self.get(approval_id)
        if record.state != ApprovalState.PENDING:
            raise ApprovalError(f"Approval is not pending (state={record.state.value})")
        return record


def _with_state(record: ApprovalRecord, state: ApprovalState) -> ApprovalRecord:
    return replace(record, state=state)

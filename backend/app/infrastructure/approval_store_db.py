"""Database-backed approval store (Priority 4).

Approval requests survive process restarts and expire EXPLICITLY:
- lazy expiry on access (get raises ApprovalError, state becomes EXPIRED)
- startup sweep via expire_stale() marks stale PENDING rows
No silent orphaned state: every record ends in APPROVED/CONSUMED,
REJECTED or EXPIRED.
"""

from __future__ import annotations

import json
import secrets
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.tools.approvals import action_fingerprint
from app.application.tools.policy import CAPABILITY_RISK
from app.application.tools.schemas import (
    ApprovalError,
    ApprovalRecord,
    ApprovalState,
    RiskLevel,
)
from app.infrastructure.models import ApprovalRequest


class PersistentApprovalStore:
    def __init__(
        self,
        session_factory: Any,
        ttl_seconds: float = 900.0,
        clock: Any = time.time,
    ) -> None:
        self._sessions = session_factory
        self._ttl = ttl_seconds
        self._clock = clock

    # ---------------------------------------------------------------- create
    def create_pending(
        self,
        tool: str,
        capability: str,
        arguments: dict[str, Any],
        target: str | None,
        conversation_id: str | None = None,
    ) -> ApprovalRecord:
        now = self._clock()
        with self._sessions() as session:
            row = ApprovalRequest(
                id=secrets.token_hex(16),
                conversation_id=conversation_id,
                tool_name=tool,
                capability=capability,
                arguments_json=json.dumps(arguments, sort_keys=True),
                fingerprint=action_fingerprint(tool, capability, arguments),
                target=target,
                risk_level=int(CAPABILITY_RISK.get(capability, RiskLevel.SENSITIVE)),
                status=ApprovalState.PENDING.value,
                created_at=_to_datetime(now),
                expires_at=_to_datetime(now + self._ttl),
            )
            session.add(row)
            session.commit()
            return self._row_to_record(row)

    # ------------------------------------------------------------------ read
    def get(self, approval_id: str) -> ApprovalRecord:
        with self._sessions() as session:
            row = session.get(ApprovalRequest, approval_id)
            if row is None:
                raise ApprovalError("Unknown approval id")
            if self._lazily_expire(session, row):
                raise ApprovalError("Approval has expired")
            return self._row_to_record(row)

    def peek(self, approval_id: str) -> ApprovalRecord | None:
        with self._sessions() as session:
            row = session.get(ApprovalRequest, approval_id)
            if row is None:
                return None
            self._lazily_expire(session, row)
            return self._row_to_record(row)

    # ---------------------------------------------------------------- mutate
    def approve(self, approval_id: str, fingerprint: str) -> ApprovalRecord:
        with self._sessions() as session:
            row = self._require_pending(session, approval_id)
            if row.fingerprint != fingerprint:
                raise ApprovalError(
                    "Action changed after approval request; approval is invalid"
                )
            row.status = ApprovalState.APPROVED.value
            row.resolved_at = _now_dt()
            row.decision = "approved"
            session.commit()
            return self._row_to_record(row)

    def reject(self, approval_id: str) -> ApprovalRecord:
        with self._sessions() as session:
            row = self._require_pending(session, approval_id)
            row.status = ApprovalState.REJECTED.value
            row.resolved_at = _now_dt()
            row.decision = "rejected"
            session.commit()
            return self._row_to_record(row)

    def consume(self, approval_id: str) -> None:
        with self._sessions() as session:
            row = session.get(ApprovalRequest, approval_id)
            if row is None:
                raise ApprovalError("Unknown approval id")
            if row.status != ApprovalState.APPROVED.value:
                raise ApprovalError(f"Approval is not executable (state={row.status})")
            row.status = ApprovalState.CONSUMED.value
            session.commit()

    # ----------------------------------------------------------------- sweep
    def expire_stale(self) -> int:
        with self._sessions() as session:
            rows = session.scalars(
                select(ApprovalRequest).where(
                    ApprovalRequest.status == ApprovalState.PENDING.value
                )
            ).all()
            count = 0
            for row in rows:
                if self._past_expiry(row):
                    row.status = ApprovalState.EXPIRED.value
                    row.resolved_at = _now_dt()
                    row.decision = "system_expired"
                    count += 1
            session.commit()
            return count

    # -------------------------------------------------------------- internal
    def _lazily_expire(self, session: Session, row: ApprovalRequest) -> bool:
        """Expire-on-touch for PENDING rows; returns True if just expired."""
        if row.status == ApprovalState.PENDING.value and self._past_expiry(row):
            row.status = ApprovalState.EXPIRED.value
            row.resolved_at = _now_dt()
            row.decision = "system_expired"
            session.commit()
            return True
        return False

    def _past_expiry(self, row: ApprovalRequest) -> bool:
        if row.expires_at is None:
            return False
        # _as_utc fixes SQLite's naive readback (local-tz skew); comparison
        # stays on the INJECTED clock so TTL logic remains testable.
        return self._clock() > _as_utc(row.expires_at).timestamp()

    def _require_pending(self, session: Session, approval_id: str) -> ApprovalRequest:
        row = session.get(ApprovalRequest, approval_id)
        if row is None:
            raise ApprovalError("Unknown approval id")
        if self._lazily_expire(session, row):
            raise ApprovalError("Approval has expired")
        if row.status != ApprovalState.PENDING.value:
            raise ApprovalError(f"Approval is not pending (state={row.status})")
        return row

    @staticmethod
    def _row_to_record(row: ApprovalRequest) -> ApprovalRecord:
        return ApprovalRecord(
            approval_id=row.id,
            tool=row.tool_name,
            capability=row.capability,
            arguments=json.loads(row.arguments_json),
            arguments_digest=row.fingerprint,
            target=row.target,
            risk_level=RiskLevel(row.risk_level),
            state=ApprovalState(row.status),
            created_at=_as_utc(row.created_at).timestamp(),
            expires_at=_as_utc(row.expires_at).timestamp() if row.expires_at else 0.0,
            conversation_id=row.conversation_id,
            decision=row.decision,
        )


def _now_dt() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; interpret stored walls as UTC.

    Without this, .timestamp() on a naive value uses the LOCAL timezone and
    every TTL comparison skews by the UTC offset (P4 bug found in EAT/+03:00).
    """
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _to_datetime(epoch_seconds: float) -> datetime:
    return datetime.fromtimestamp(epoch_seconds, tz=UTC)

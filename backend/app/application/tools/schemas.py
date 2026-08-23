"""Core types for the RUACH Tool Engine (docs/05 Security Architecture)."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class RiskLevel(enum.IntEnum):
    READ_ONLY = 0
    LOW = 1
    SENSITIVE = 2
    DESTRUCTIVE = 3


class PolicyDecision(enum.Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class ApprovalState(enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class ToolRequest:
    tool: str
    capability: str
    arguments: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""


@dataclass(frozen=True)
class PolicyOutcome:
    decision: PolicyDecision
    reason: str
    risk_level: RiskLevel = RiskLevel.READ_ONLY


@dataclass(frozen=True)
class ApprovalRecord:
    approval_id: str
    tool: str
    capability: str
    arguments: dict[str, Any]
    arguments_digest: str
    target: str | None
    risk_level: RiskLevel
    state: ApprovalState
    created_at: float
    expires_at: float
    conversation_id: str | None = None
    decision: str | None = None


class ToolSecurityError(Exception):
    """Raised when a tool request violates a security invariant."""


class PathOutsideWorkspaceError(ToolSecurityError):
    pass


class InvalidToolRequestError(ToolSecurityError):
    pass


class ApprovalError(ToolSecurityError):
    pass


@dataclass(frozen=True)
class ToolOutcome:
    state: str
    output: Any = None
    reason: str = ""
    approval_id: str | None = None

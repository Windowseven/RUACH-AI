"""Diagnostic result model shared by Doctor, Planner and Guided UI.

Implements the structured finding contract required by:
  - docs/15 §22 (capability graph nodes carry structured results)
  - docs/16 §5/§6 (capability states; hard vs soft failures)
  - docs/17 §27 (DiagnosticResult: status/severity/capability/message/
    technical_reason/recommended_actions)

The UI renders the human-facing fields; technical_reason is level-4
disclosure shown only on request (docs/17 §5). Everything here is pure
data: probes produce results, engines consume them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Status(str, Enum):
    """Probe outcome (docs/17 §27)."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class Severity(str, Enum):
    """How much a finding should influence strategy (docs/17 §27)."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Capability states (docs/16 §5). A missing capability MUST NOT
# automatically mean the whole installation is impossible.
AVAILABLE = "AVAILABLE"
UNAVAILABLE = "UNAVAILABLE"
UNKNOWN = "UNKNOWN"
RESTRICTED = "RESTRICTED"
NOT_REQUIRED = "NOT_REQUIRED"

CAPABILITY_STATES = (AVAILABLE, UNAVAILABLE, UNKNOWN, RESTRICTED, NOT_REQUIRED)


# Python dependency capability states (docs/15 §11). "Package exists on
# PyPI" and "package can actually be installed on this device" are
# different claims; these states keep them separate.
class DependencyState(str, Enum):
    AVAILABLE_WHEEL = "AVAILABLE_WHEEL"
    SOURCE_BUILD_REQUIRED = "SOURCE_BUILD_REQUIRED"
    SOURCE_BUILDABLE = "SOURCE_BUILDABLE"
    SOURCE_BUILD_BLOCKED = "SOURCE_BUILD_BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


# Native inference capability levels (docs/15 §12/§13). A successful
# compilation MUST NOT be interpreted as successful inference; each level
# is a distinct claim backed only by its own measurement.
class InferenceLevel(str, Enum):
    NOT_TESTED = "NOT_TESTED"
    SOURCE_AVAILABLE = "SOURCE_AVAILABLE"
    BUILDABLE = "BUILDABLE"
    EXECUTABLE = "EXECUTABLE"
    MODEL_LOADABLE = "MODEL_LOADABLE"
    INFERENCE_FUNCTIONAL = "INFERENCE_FUNCTIONAL"
    INFERENCE_DEGRADED = "INFERENCE_DEGRADED"
    INFERENCE_FAILED = "INFERENCE_FAILED"


_INFERENCE_ORDER = {
    InferenceLevel.NOT_TESTED: 0,
    InferenceLevel.SOURCE_AVAILABLE: 1,
    InferenceLevel.BUILDABLE: 2,
    InferenceLevel.EXECUTABLE: 3,
    InferenceLevel.MODEL_LOADABLE: 4,
    InferenceLevel.INFERENCE_FUNCTIONAL: 5,
    InferenceLevel.INFERENCE_DEGRADED: 4,
    InferenceLevel.INFERENCE_FAILED: 0,
}


def inference_rank(level: InferenceLevel) -> int:
    """Monotonic strength of an inference claim (degraded counts as loadable)."""
    return _INFERENCE_ORDER[level]


@dataclass(frozen=True)
class DiagnosticResult:
    """One structured finding (docs/17 §27).

    message is the short human-readable explanation (level 1-3);
    technical_reason is the level-4 detail shown only on request.
    """

    capability: str
    status: Status
    severity: Severity = Severity.INFO
    message: str = ""
    technical_reason: str = ""
    recommended_actions: tuple[str, ...] = ()
    details: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "status": self.status.value,
            "severity": self.severity.value,
            "message": self.message,
            "technical_reason": self.technical_reason,
            "recommended_actions": list(self.recommended_actions),
            "details": dict(self.details),
        }


def result(
    capability: str,
    status: Status,
    *,
    severity: Severity = Severity.INFO,
    message: str = "",
    technical_reason: str = "",
    actions: tuple[str, ...] = (),
    **details: str,
) -> DiagnosticResult:
    """Convenience constructor keeping probe call sites readable."""
    return DiagnosticResult(
        capability=capability,
        status=status,
        severity=severity,
        message=message,
        technical_reason=technical_reason,
        recommended_actions=actions,
        details=dict(details),
    )


def worst(results: list[DiagnosticResult]) -> Status:
    """Aggregate status: FAIL dominates, then WARN, then UNKNOWN, then PASS."""
    statuses = {item.status for item in results}
    if Status.FAIL in statuses:
        return Status.FAIL
    if Status.WARN in statuses:
        return Status.WARN
    if Status.UNKNOWN in statuses:
        return Status.UNKNOWN
    return Status.PASS


def failures(results: list[DiagnosticResult]) -> list[DiagnosticResult]:
    return [item for item in results if item.status is Status.FAIL]


def warnings(results: list[DiagnosticResult]) -> list[DiagnosticResult]:
    return [item for item in results if item.status is Status.WARN]
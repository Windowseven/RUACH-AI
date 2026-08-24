"""Centralized user-facing response texts + error classification (P17 §8/§9).

Every canned user-facing sentence lives HERE, never in exception handlers
or route code. Each text maps to exactly one failure class so the taxonomy
stays distinct:

- model_protocol_error : the MODEL produced unparseable/degenerate output.
  Never blame the user; never expose protocol details.
- tool_failed          : a correctly-formed, authorized action failed for
  a real reason (missing file, ...). Honest reason included.
- policy_denied        : the action was refused by policy or the human.
- system_error         : infrastructure failure; fail-closed, honest.
"""

from __future__ import annotations

MODEL_PROTOCOL_ERROR_EVENT = "MODEL_PROTOCOL_ERROR"

RESPONSE_TEXTS: dict[str, str] = {
    "model_protocol_error": (
        "I couldn't safely interpret my own last response. Please try again."
    ),
    "tool_failed_prefix": "The action could not be completed. Reason:",
    "policy_denied_prefix": "I did not perform this action. Reason:",
    "system_error": (
        "RUACH could not complete the operation because an internal "
        "system error occurred. Nothing was executed."
    ),
    "empty_response": "(empty response)",
}


def model_protocol_error_text() -> str:
    return RESPONSE_TEXTS["model_protocol_error"]


def policy_denied_text(reason: str) -> str:
    return f"{RESPONSE_TEXTS['policy_denied_prefix']} {reason}"


def tool_failed_text(reason: str) -> str:
    return f"{RESPONSE_TEXTS['tool_failed_prefix']} {reason}"

"""Conversation orchestrator.

Turn logic only: parse proposals, consult the Tool Engine, produce final
replies. Prompt ASSEMBLY (system instructions + bounded history) lives in
app.application.context and is performed before this module is called.


1. Every model turn carries a system preamble describing the available
   capabilities and the request format.
2. The model may emit exactly one tool proposal per turn:

       <tool_request>{"tool": "...", "capability": "...",
        "arguments": {...}}</tool_request>

3. Proposals are NEVER executed by the model itself. They are submitted
   to the Tool Engine, which enforces policy (deny-by-default,
   workspace boundary, risk-based approval).
4. Outcomes:
   - no proposal          -> plain reply
   - COMPLETED            -> second inference turn summarising the result
   - AWAITING_APPROVAL    -> surfaced to the UI with an approval id
   - DENIED               -> honest refusal text including the reason

The model cannot bypass this flow: only parsed proposals reach the
engine, and the engine alone decides execution.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.application import response_texts
from app.application.context import USER_SENTINEL
from app.application.inference import InferencePort
from app.application.output_normalizer import normalize
from app.application.tools.engine import SYSTEM_ERROR_TEXT, ToolEngine
from app.application.tools.schemas import ToolRequest

REQUEST_PATTERN = re.compile(
    r"<tool_request>\s*(\{.*?\})\s*</tool_request>", re.DOTALL
)
REQUEST_TAG_PATTERN = re.compile(r"<tool_request>[\s\S]*?</tool_request>")
REQUEST_OPEN_TAG = re.compile(r"<tool_request>")


def has_request_block(text: str) -> bool:
    return REQUEST_TAG_PATTERN.search(text) is not None


def _looks_like_broken_proposal(text: str) -> bool:
    """Truncated request blocks OR degenerate echo loops (P4: the 0.6B
    model occasionally locks into template-header repetition). Safe:
    none of these execute; a resample goes through the same parser."""
    if not text.strip():
        # Everything normalized away (e.g. pure control-token output).
        return True
    if REQUEST_OPEN_TAG.search(text) and parse_tool_request(text) is None:
        # Opened a request block but no balanced JSON payload followed
        # (truncated close tag AND unparsable body).
        return True
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    header_lines = sum(1 for line in lines if line.startswith("###"))
    if header_lines >= 4:
        return True
    return len(lines) >= 4 and len(set(lines)) <= 2


def parse_tool_request(text: str) -> dict[str, Any] | None:
    """Extract a proposal payload from model output (P17 §8/§10).

    Well-formed blocks are matched by the tag pair. Small models
    frequently omit the CLOSING tag while emitting clean JSON (observed
    consistently on Qwen3-0.6B with finish_reason=stop); the unclosed
    form is accepted ONLY when a balanced JSON object follows the open
    tag - anything else fails closed to the protocol-error path.
    """
    match = REQUEST_PATTERN.search(text)
    if match is not None:
        return _payload(match.group(1))
    open_match = REQUEST_OPEN_TAG.search(text)
    if open_match is not None:
        return _unclosed_payload(text[open_match.end():])
    return None


def _payload(raw_json: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _unclosed_payload(fragment: str) -> dict[str, Any] | None:
    start = fragment.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(fragment)):
        char = fragment[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return _payload(fragment[start:index + 1])
    return None


@dataclass
class PendingTool:
    approval_id: str
    tool: str
    capability: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnResult:
    kind: str  # "reply" | "awaiting_approval"
    reply: str
    pending: PendingTool | None = None
    tool_state: str = ""  # "" | "COMPLETED" | "DENIED" | "REJECTED" | "FAILED"
    tool_capability: str = ""
    tool_arguments: dict[str, Any] = field(default_factory=dict)
    tool_result_preview: str = ""  # bounded result text for context/history
    error_class: str = ""  # "" | response_texts.MODEL_PROTOCOL_ERROR_EVENT


def _proposal_from_payload(payload: dict[str, Any]) -> ToolRequest | None:
    tool = payload.get("tool")
    capability = payload.get("capability")
    arguments = payload.get("arguments", {})
    if not isinstance(tool, str) or not isinstance(capability, str):
        return None
    if not isinstance(arguments, dict):
        return None
    return ToolRequest(tool=tool, capability=capability, arguments=arguments)


def _continuation_prompt(capability: str, outcome_json: str) -> str:
    return (
        f"{USER_SENTINEL} (continuation)\n"
        f"Tool {capability} returned:\n{outcome_json}\n"
        "Summarise the outcome for the user in plain prose. "
        "Do not claim anything beyond what the result shows."
    )


def _preview(output: Any, limit: int = 400) -> str:
    try:
        text = output if isinstance(output, str) else json.dumps(output)
    except (TypeError, ValueError):
        text = repr(output)
    return text[:limit]


def _clean(text: str) -> str:
    cleaned = text.replace(USER_SENTINEL, "").strip()
    return cleaned or response_texts.RESPONSE_TEXTS["empty_response"]


# The 0.6B model occasionally locks into degenerate loops (template echo,
# reasoning spill + endless code fences). Bounded resampling keeps this a
# sampling-quality concern, not a safety one: every sample goes through the
# same parser and the policy engine regardless (docs/13 P4 hardening).
MAX_SAMPLES = 3


def run_turn(
    inference: InferencePort,
    engine: ToolEngine,
    prompt: str,
    conversation_id: str = "",
) -> TurnResult:
    # Defense-in-depth: every sample is normalized at the orchestrator too,
    # so no code path - even with a non-normalizing InferencePort double -
    # can parse or surface raw control tokens (P17 §10).
    first = normalize(inference.complete(prompt)).text
    for _ in range(MAX_SAMPLES - 1):
        if not _looks_like_broken_proposal(first):
            break
        first = normalize(inference.complete(prompt)).text
    if _looks_like_broken_proposal(first):
        # Still degenerate after bounded resamples: graceful no-action
        # reply classified as a MODEL protocol error - the user did
        # nothing wrong (P17 §8).
        return TurnResult(
            kind="reply",
            reply=response_texts.model_protocol_error_text(),
            error_class=response_texts.MODEL_PROTOCOL_ERROR_EVENT,
        )
    payload = parse_tool_request(first)
    if payload is None:
        if has_request_block(first):
            return TurnResult(
                kind="reply",
                reply=response_texts.model_protocol_error_text(),
                error_class=response_texts.MODEL_PROTOCOL_ERROR_EVENT,
            )
        return TurnResult(kind="reply", reply=_clean(first))

    request = _proposal_from_payload(payload)
    if request is None:
        return TurnResult(
            kind="reply",
            reply=response_texts.model_protocol_error_text(),
            error_class=response_texts.MODEL_PROTOCOL_ERROR_EVENT,
        )

    outcome = engine.submit(request, conversation_id=conversation_id or None)
    common: dict[str, Any] = {
        "tool_capability": request.capability,
        "tool_arguments": dict(request.arguments),
        "tool_result_preview": _preview(outcome.output),
    }
    if outcome.state == "COMPLETED":
        final = normalize(
            inference.complete(
                _continuation_prompt(request.capability, json.dumps(outcome.output))
            )
        ).text
        return TurnResult(
            kind="reply", reply=_clean(final), tool_state="COMPLETED", **common
        )
    if outcome.state == "DENIED":
        return TurnResult(
            kind="reply",
            reply=response_texts.policy_denied_text(str(outcome.reason)),
            tool_state="DENIED",
            **common,
        )
    if outcome.state == "FAILED":
        return TurnResult(
            kind="reply",
            reply=response_texts.tool_failed_text(str(outcome.reason)),
            tool_state="FAILED",
            **common,
        )
    if outcome.state == "SYSTEM_ERROR":
        # Infrastructure failure: fail-closed, honestly labelled. Never
        # presented as a security denial and never audited as one.
        return TurnResult(
            kind="reply",
            reply=SYSTEM_ERROR_TEXT,
            tool_state="SYSTEM_ERROR",
            **common,
        )
    assert outcome.approval_id is not None  # AWAITING_APPROVAL always carries one
    pending = PendingTool(
        approval_id=outcome.approval_id,
        tool=request.tool,
        capability=request.capability,
        arguments=dict(request.arguments),
    )
    return TurnResult(
        kind="awaiting_approval",
        reply=(
            f"This action requires your approval: {request.capability}. "
            "Nothing has been executed yet."
        ),
        pending=pending,
        **common,
    )


def resolve_decision(
    inference: InferencePort,
    engine: ToolEngine,
    approval_id: str,
    approved: bool,
) -> TurnResult:
    """Apply a human decision and produce the final conversational reply."""
    capability = engine.capability_for(approval_id)
    if approved:
        outcome = engine.approve_and_execute(approval_id)
    else:
        outcome = engine.reject(approval_id)

    if outcome.state == "COMPLETED":
        final = normalize(
            inference.complete(
                _continuation_prompt(capability, json.dumps(outcome.output))
            )
        ).text
        return TurnResult(
            kind="reply",
            reply=_clean(final),
            tool_state="COMPLETED",
            tool_capability=capability,
            tool_arguments={},
            tool_result_preview=_preview(outcome.output),
        )
    if outcome.state == "REJECTED":
        return TurnResult(
            kind="reply",
            reply="Understood. The action was cancelled; nothing was executed.",
            tool_state="REJECTED",
            tool_capability=capability,
        )
    if outcome.state == "SYSTEM_ERROR":
        return TurnResult(
            kind="reply",
            reply=SYSTEM_ERROR_TEXT,
            tool_state="SYSTEM_ERROR",
            tool_capability=capability,
        )
    return TurnResult(
        kind="reply",
        reply=response_texts.tool_failed_text(str(outcome.reason)),
        tool_state=outcome.state,
    )

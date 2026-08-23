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

from app.application.context import USER_SENTINEL
from app.application.inference import InferencePort
from app.application.tools.engine import ToolEngine
from app.application.tools.schemas import ToolRequest

REQUEST_PATTERN = re.compile(
    r"<tool_request>\s*(\{.*?\})\s*</tool_request>", re.DOTALL
)
REQUEST_TAG_PATTERN = re.compile(r"<tool_request>[\s\S]*?</tool_request>")
REQUEST_OPEN_TAG = re.compile(r"<tool_request>")


def has_request_block(text: str) -> bool:
    return REQUEST_TAG_PATTERN.search(text) is not None


def _looks_like_broken_proposal(text: str) -> bool:
    """A block that opened but never closed (truncation) or closed without
    well-formed JSON inside. Safe: none of these execute."""
    if REQUEST_TAG_PATTERN.search(text) is None and REQUEST_OPEN_TAG.search(text):
        return True
    return parse_tool_request(text) is None and has_request_block(text)


def parse_tool_request(text: str) -> dict[str, Any] | None:
    match = REQUEST_PATTERN.search(text)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


@dataclass
class PendingTool:
    approval_id: str
    conversation_id: str
    tool: str
    capability: str
    arguments: dict[str, Any] = field(default_factory=dict)


class ApprovalIndex:
    """Maps pending approval ids to the conversations that requested them."""

    def __init__(self) -> None:
        self._by_approval: dict[str, str] = {}

    def register(self, approval_id: str, conversation_id: str) -> None:
        self._by_approval[approval_id] = conversation_id

    def conversation_for(self, approval_id: str) -> str | None:
        return self._by_approval.get(approval_id)


@dataclass
class TurnResult:
    kind: str  # "reply" | "awaiting_approval"
    reply: str
    pending: PendingTool | None = None
    tool_state: str = ""  # "" | "COMPLETED" | "DENIED" | "REJECTED" | "FAILED"
    tool_capability: str = ""
    tool_arguments: dict[str, Any] = field(default_factory=dict)
    tool_result_preview: str = ""  # bounded result text for context/history


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
    return cleaned or "(empty response)"


MALFORMED_REPLY = "I formed a malformed tool request, so I took no action."


def run_turn(
    inference: InferencePort,
    engine: ToolEngine,
    approvals: ApprovalIndex,
    prompt: str,
    conversation_id: str = "",
) -> TurnResult:
    first = inference.complete(prompt)
    if _looks_like_broken_proposal(first):
        # Disciplined single resample for degenerate/truncated proposals.
        # Never a bypass: whatever comes back goes through the same parser.
        first = inference.complete(prompt)
    payload = parse_tool_request(first)
    if payload is None:
        if has_request_block(first):
            return TurnResult(kind="reply", reply=MALFORMED_REPLY)
        return TurnResult(kind="reply", reply=_clean(first))

    request = _proposal_from_payload(payload)
    if request is None:
        return TurnResult(kind="reply", reply=MALFORMED_REPLY)

    outcome = engine.submit(request)
    common: dict[str, Any] = {
        "tool_capability": request.capability,
        "tool_arguments": dict(request.arguments),
        "tool_result_preview": _preview(outcome.output),
    }
    if outcome.state == "COMPLETED":
        final = inference.complete(
            _continuation_prompt(request.capability, json.dumps(outcome.output))
        )
        return TurnResult(
            kind="reply", reply=_clean(final), tool_state="COMPLETED", **common
        )
    if outcome.state == "DENIED":
        return TurnResult(
            kind="reply",
            reply=f"I did not perform this action. Reason: {outcome.reason}",
            tool_state="DENIED",
            **common,
        )
    if outcome.state == "FAILED":
        return TurnResult(
            kind="reply",
            reply=f"The action failed while executing. Reason: {outcome.reason}",
            tool_state="FAILED",
            **common,
        )
    assert outcome.approval_id is not None  # AWAITING_APPROVAL always carries one
    pending = PendingTool(
        approval_id=outcome.approval_id,
        conversation_id=conversation_id,
        tool=request.tool,
        capability=request.capability,
        arguments=dict(request.arguments),
    )
    if conversation_id:
        approvals.register(outcome.approval_id, conversation_id)
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
    if approved:
        outcome = engine.approve_and_execute(approval_id)
        capability = engine.capability_for(approval_id)
    else:
        outcome = engine.reject(approval_id)
        capability = ""

    if outcome.state == "COMPLETED":
        final = inference.complete(
            _continuation_prompt(capability, json.dumps(outcome.output))
        )
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
        )
    return TurnResult(
        kind="reply",
        reply=f"The action could not be completed. Reason: {outcome.reason}",
        tool_state=outcome.state,
    )

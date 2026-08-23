import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application import orchestrator
from app.application.conversation_service import ConversationNotFound
from app.application.inference import InferencePort
from app.application.tools.engine import ToolEngine
from app.infrastructure.models import Conversation, Message, new_id


def _next_seq(session: Session, conversation_id: str) -> int:
    current = session.scalar(
        select(func.max(Message.seq)).where(Message.conversation_id == conversation_id)
    )
    return (current or 0) + 1


@dataclass
class ChatTurn:
    message: Message
    conversation_id: str
    tool_state: str = ""
    tool_capability: str = ""
    tool_arguments: dict[str, Any] = field(default_factory=dict)
    pending: orchestrator.PendingTool | None = None


def _derive_title(content: str) -> str:
    trimmed = content.strip()
    if len(trimmed) > 50:
        return trimmed[:50] + "…"
    return trimmed


def _existing_conversation(session: Session, conversation_id: str) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise ConversationNotFound(conversation_id)
    return conversation


def _build_tool_event(
    conversation_id: str,
    result: orchestrator.TurnResult,
    seq: int,
) -> Message | None:
    """Persist an honest record of what the tool layer actually did."""
    capability = result.tool_capability or (
        result.pending.capability if result.pending else ""
    )
    state = result.tool_state or ("AWAITING_APPROVAL" if result.pending else "")
    if not state:
        return None
    event = {
        "capability": capability,
        "arguments": result.tool_arguments
        or (result.pending.arguments if result.pending else {}),
        "state": state,
    }
    return Message(
        id=new_id(),
        conversation_id=conversation_id,
        role="tool",
        content=json.dumps(event, sort_keys=True),
        seq=seq,
    )


def _finish(
    session: Session,
    conversation: Conversation,
    user_text: str | None,
    reply_text: str,
    result: orchestrator.TurnResult,
) -> ChatTurn:
    seq = _next_seq(session, conversation.id)
    to_add: list[Message] = []
    if user_text is not None:
        to_add.append(
            Message(
                id=new_id(),
                conversation_id=conversation.id,
                role="user",
                content=user_text,
                seq=seq,
            )
        )
        seq += 1
    # Tool activity happened BEFORE the final reply was produced, so its
    # sequence sits between the user message and the assistant message.
    tool_event = _build_tool_event(conversation.id, result, seq)
    if tool_event is not None:
        to_add.append(tool_event)
        seq += 1
    to_add.append(
        Message(
            id=new_id(),
            conversation_id=conversation.id,
            role="assistant",
            content=reply_text,
            seq=seq,
        )
    )
    session.add_all(to_add)
    session.commit()
    return ChatTurn(
        message=to_add[-1],
        conversation_id=conversation.id,
        tool_state=result.tool_state,
        tool_capability=result.tool_capability,
        tool_arguments=result.tool_arguments,
        pending=result.pending,
    )


def execute_chat(
    session: Session,
    inference: InferencePort,
    engine: ToolEngine,
    approvals: orchestrator.ApprovalIndex,
    message: str,
    conversation_id: str | None = None,
) -> ChatTurn:
    if conversation_id is None:
        conversation = Conversation(id=new_id(), title=_derive_title(message))
        session.add(conversation)
        session.flush()
    else:
        conversation = _existing_conversation(session, conversation_id)
    result = orchestrator.run_turn(
        inference, engine, approvals, message, conversation_id=conversation.id
    )
    return _finish(session, conversation, message, result.reply, result)


def decide_approval(
    session: Session,
    inference: InferencePort,
    engine: ToolEngine,
    approvals: orchestrator.ApprovalIndex,
    approval_id: str,
    approved: bool,
) -> ChatTurn:
    conversation_id = approvals.conversation_for(approval_id)
    if conversation_id is None:
        raise ConversationNotFound(approval_id)
    conversation = _existing_conversation(session, conversation_id)
    result = orchestrator.resolve_decision(inference, engine, approval_id, approved)
    # The human decision itself is recorded as a tool event; no synthetic
    # user message is invented.
    return _finish(session, conversation, None, result.reply, result)

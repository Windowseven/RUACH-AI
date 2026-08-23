"""Conversation service (Priority 3).

Owns the chat turn flow. FastAPI routes stay thin; this module composes
repositories (persistence), ContextBuilder (model input), orchestrator
(turn logic) and the Tool Engine (guarded execution).

Error contract:
- unknown/invalid conversation id  -> ConversationNotFound -> HTTP 404
- empty/oversized message          -> rejected by API schema (422)
- inference failure                -> typed InferenceError -> error envelope
No silent conversation creation on invalid ids.
"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.application import orchestrator
from app.application.context import ContextBuilder, RecentMessagesStrategy
from app.application.conversation_service import ConversationNotFound
from app.application.inference import InferencePort
from app.application.repositories import (
    ConversationRepository,
    MessageRepository,
    to_context_message,
)
from app.application.tools.engine import ToolEngine
from app.config.settings import get_settings
from app.infrastructure.models import Message

MAX_TOOL_RESULT_CHARS = 400


@dataclass
class ChatTurn:
    message: Message
    conversation_id: str
    tool_state: str = ""
    tool_capability: str = ""
    tool_arguments: dict[str, Any] = field(default_factory=dict)
    pending: orchestrator.PendingTool | None = None


def _tool_event_content(result: orchestrator.TurnResult) -> str | None:
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
    if result.tool_result_preview:
        event["result"] = result.tool_result_preview[:MAX_TOOL_RESULT_CHARS]
    import json

    return json.dumps(event, sort_keys=True)


def execute_chat(
    session: Session,
    inference: InferencePort,
    engine: ToolEngine,
    message: str,
    conversation_id: str | None = None,
) -> ChatTurn:
    settings = get_settings()
    conversations = ConversationRepository(session)
    messages = MessageRepository(session)

    # --- Transaction 1: durable turn start (docs/13 P4 #1/#3) -------------
    # The user message COMMITS before inference. If inference or tool
    # orchestration crashes, the user's words remain persisted. We never
    # hold a SQLite write transaction across model inference.
    if conversation_id is None:
        conversation = conversations.create(title=message)
    else:
        conversation = conversations.get(conversation_id)
    # History BEFORE this turn; read prior to the append so the current
    # message is not duplicated into its own context.
    history_rows = messages.recent(
        conversation.id, limit=settings.context_max_messages
    )
    messages.append(conversation.id, "user", message)
    session.commit()

    # --- Inference + orchestration: NO outer write transaction held -------
    builder = ContextBuilder(
        RecentMessagesStrategy(max_messages=settings.context_max_messages)
    )
    prompt = builder.build(
        [to_context_message(row) for row in history_rows], message
    )
    result = orchestrator.run_turn(
        inference, engine, prompt, conversation_id=conversation.id
    )

    # --- Transaction 2: turn outcome --------------------------------------
    event_json = _tool_event_content(result)
    if event_json is not None:
        messages.append(conversation.id, "tool", event_json)
    reply = messages.append(conversation.id, "assistant", result.reply)
    conversations.touch(conversation.id)
    session.commit()

    return ChatTurn(
        message=reply,
        conversation_id=conversation.id,
        tool_state=result.tool_state
        or ("AWAITING_APPROVAL" if result.pending else ""),
        tool_capability=result.tool_capability,
        tool_arguments=result.tool_arguments,
        pending=result.pending,
    )


def decide_approval(
    session: Session,
    inference: InferencePort,
    engine: ToolEngine,
    approval_id: str,
    approved: bool,
) -> ChatTurn:
    conversation_id = engine.pending_conversation(approval_id)
    if conversation_id is None:
        raise ConversationNotFound(approval_id)
    conversations = ConversationRepository(session)
    conversation = conversations.get(conversation_id)
    session.commit()  # release the read snapshot before store/inference work

    result = orchestrator.resolve_decision(inference, engine, approval_id, approved)

    messages = MessageRepository(session)
    event_json = _tool_event_content(result)
    if event_json is not None:
        messages.append(conversation.id, "tool", event_json)
    reply = messages.append(conversation.id, "assistant", result.reply)
    conversations.touch(conversation.id)
    session.commit()

    return ChatTurn(
        message=reply,
        conversation_id=conversation.id,
        tool_state=result.tool_state,
        tool_capability=result.tool_capability,
        tool_arguments=result.tool_arguments,
    )

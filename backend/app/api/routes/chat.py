from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_approval_index, get_inference, get_session, get_tool_engine
from app.api.middleware import request_id_var
from app.api.schemas.chat import (
    ApprovalDecisionRequest,
    ChatRequest,
    ChatResponse,
    ChatResponseData,
    PendingApprovalOut,
    ToolActivityOut,
)
from app.application import chat_service
from app.application.conversation_service import ConversationNotFound
from app.application.inference import InferencePort
from app.application.orchestrator import ApprovalIndex
from app.application.tools.engine import ToolEngine

router = APIRouter(tags=["chat"])


def _response(turn: chat_service.ChatTurn) -> ChatResponse:
    pending_out = None
    if turn.pending is not None:
        pending_out = PendingApprovalOut(
            approval_id=turn.pending.approval_id,
            conversation_id=turn.pending.conversation_id or turn.conversation_id,
            tool=turn.pending.tool,
            capability=turn.pending.capability,
            arguments=turn.pending.arguments,
        )
    tool_out = None
    if turn.tool_state:
        tool_out = ToolActivityOut(
            state=turn.tool_state,
            capability=turn.tool_capability,
            arguments=turn.tool_arguments,
        )
    elif turn.pending is not None:
        tool_out = ToolActivityOut(
            state="AWAITING_APPROVAL",
            capability=turn.pending.capability,
            arguments=turn.pending.arguments,
        )
    return ChatResponse(
        data=ChatResponseData(
            message_id=turn.message.id,
            conversation_id=turn.conversation_id,
            role=turn.message.role,
            content=turn.message.content,
            tool=tool_out,
            pending_approval=pending_out,
        ),
        request_id=request_id_var.get(),
    )


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    session: Session = Depends(get_session),
    inference: InferencePort = Depends(get_inference),
    engine: ToolEngine = Depends(get_tool_engine),
    approvals: ApprovalIndex = Depends(get_approval_index),
) -> ChatResponse:
    try:
        turn = chat_service.execute_chat(
            session,
            inference,
            engine,
            approvals,
            payload.message,
            payload.conversation_id,
        )
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return _response(turn)


def _decide(
    approval_id: str,
    approved: bool,
    session: Session,
    inference: InferencePort,
    engine: ToolEngine,
    approvals: ApprovalIndex,
) -> ChatResponse:
    try:
        turn = chat_service.decide_approval(
            session, inference, engine, approvals, approval_id, approved
        )
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Unknown approval request.")
    return _response(turn)


@router.post("/chat/approvals/{approval_id}/approve", response_model=ChatResponse)
def approve_tool(
    approval_id: str,
    decision: ApprovalDecisionRequest,
    session: Session = Depends(get_session),
    inference: InferencePort = Depends(get_inference),
    engine: ToolEngine = Depends(get_tool_engine),
    approvals: ApprovalIndex = Depends(get_approval_index),
) -> ChatResponse:
    if not decision.approved:
        raise HTTPException(status_code=422, detail="Use the reject endpoint.")
    return _decide(approval_id, True, session, inference, engine, approvals)


@router.post("/chat/approvals/{approval_id}/reject", response_model=ChatResponse)
def reject_tool(
    approval_id: str,
    session: Session = Depends(get_session),
    inference: InferencePort = Depends(get_inference),
    engine: ToolEngine = Depends(get_tool_engine),
    approvals: ApprovalIndex = Depends(get_approval_index),
) -> ChatResponse:
    return _decide(approval_id, False, session, inference, engine, approvals)

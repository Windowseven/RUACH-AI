from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.api.middleware import request_id_var
from app.api.schemas.conversations import (
    ConversationCreatedData,
    ConversationCreatedResponse,
    ConversationCreateRequest,
    ConversationDetailData,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationSummary,
    MessageOut,
)
from app.application import conversation_service
from app.application.conversation_service import ConversationNotFound, iso_utc
from app.infrastructure.models import Conversation

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _summary(conversation: Conversation) -> ConversationSummary:
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        created_at=iso_utc(conversation.created_at),
    )


def _detail(conversation: Conversation) -> ConversationDetailData:
    return ConversationDetailData(
        id=conversation.id,
        title=conversation.title,
        created_at=iso_utc(conversation.created_at),
        updated_at=iso_utc(conversation.updated_at),
        messages=[
            MessageOut(
                id=message.id,
                role=message.role,
                content=message.content,
                created_at=iso_utc(message.created_at),
            )
            for message in conversation.messages
        ],
    )


@router.post("", response_model=ConversationCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreateRequest, session: Session = Depends(get_session)
) -> ConversationCreatedResponse:
    conversation = conversation_service.create_conversation(session, payload.title)
    return ConversationCreatedResponse(
        data=ConversationCreatedData(id=conversation.id, title=conversation.title),
        request_id=request_id_var.get(),
    )


@router.get("", response_model=ConversationListResponse)
def list_conversations(session: Session = Depends(get_session)) -> ConversationListResponse:
    return ConversationListResponse(
        data=[_summary(c) for c in conversation_service.list_conversations(session)],
        request_id=request_id_var.get(),
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(
    conversation_id: str, session: Session = Depends(get_session)
) -> ConversationDetailResponse:
    try:
        conversation = conversation_service.get_conversation(session, conversation_id)
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return ConversationDetailResponse(data=_detail(conversation), request_id=request_id_var.get())


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, session: Session = Depends(get_session)) -> None:
    try:
        conversation_service.delete_conversation(session, conversation_id)
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation not found.")

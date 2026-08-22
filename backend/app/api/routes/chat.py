from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_inference, get_session
from app.api.middleware import request_id_var
from app.api.schemas.chat import ChatRequest, ChatResponse, ChatResponseData
from app.application import chat_service
from app.application.conversation_service import ConversationNotFound
from app.application.inference import InferencePort

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    session: Session = Depends(get_session),
    inference: InferencePort = Depends(get_inference),
) -> ChatResponse:
    try:
        reply = chat_service.execute_chat(
            session,
            inference,
            payload.message,
            payload.conversation_id,
        )
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return ChatResponse(
        data=ChatResponseData(
            message_id=reply.id,
            conversation_id=reply.conversation_id,
            role=reply.role,
            content=reply.content,
        ),
        request_id=request_id_var.get(),
    )

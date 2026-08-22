from sqlalchemy.orm import Session

from app.application.conversation_service import ConversationNotFound
from app.application.inference import InferencePort
from app.infrastructure.models import Conversation, Message, new_id


def _derive_title(content: str) -> str:
    trimmed = content.strip()
    if len(trimmed) > 50:
        return trimmed[:50] + "…"
    return trimmed


def execute_chat(
    session: Session,
    inference: InferencePort,
    message: str,
    conversation_id: str | None = None,
) -> Message:
    conversation: Conversation | None = None
    if conversation_id is None:
        conversation = Conversation(id=new_id(), title=_derive_title(message))
        session.add(conversation)
        session.flush()
    else:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            raise ConversationNotFound(conversation_id)

    user_message = Message(
        id=new_id(),
        conversation_id=conversation.id,
        role="user",
        content=message,
    )
    reply = Message(
        id=new_id(),
        conversation_id=conversation.id,
        role="assistant",
        content=inference.complete(message),
    )
    session.add_all([user_message, reply])
    session.commit()
    return reply

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Conversation, new_id


class ConversationNotFound(Exception):
    pass


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_conversation(session: Session, title: str) -> Conversation:
    conversation = Conversation(id=new_id(), title=title)
    session.add(conversation)
    session.commit()
    return conversation


def list_conversations(session: Session) -> list[Conversation]:
    rows = session.scalars(select(Conversation).order_by(Conversation.created_at.desc())).all()
    return list(rows)


def get_conversation(session: Session, conversation_id: str) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise ConversationNotFound(conversation_id)
    return conversation


def delete_conversation(session: Session, conversation_id: str) -> None:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise ConversationNotFound(conversation_id)
    session.delete(conversation)
    session.commit()

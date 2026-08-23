"""Persistence repositories for conversations and messages (Priority 3).

Repositories are the ONLY components that touch the SQLAlchemy models.
Services depend on these classes, never on the ORM directly.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.context import ContextMessage
from app.application.conversation_service import ConversationNotFound
from app.infrastructure.models import Conversation, Message, new_id


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, conversation_id: str) -> Conversation:
        conversation = self._session.get(Conversation, conversation_id)
        if conversation is None:
            raise ConversationNotFound(conversation_id)
        return conversation

    def create(self, title: str) -> Conversation:
        conversation = Conversation(
            id=new_id(), title=_derive_title(title), updated_at=_now()
        )
        self._session.add(conversation)
        self._session.flush()
        return conversation

    def touch(self, conversation_id: str) -> None:
        conversation = self.get(conversation_id)
        conversation.updated_at = _now()
        self._session.flush()


class MessageRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(
        self, conversation_id: str, role: str, content: str
    ) -> Message:
        message = Message(
            id=new_id(),
            conversation_id=conversation_id,
            role=role,
            content=content,
            seq=self._next_seq(conversation_id),
        )
        self._session.add(message)
        self._session.flush()
        return message

    def recent(self, conversation_id: str, limit: int) -> list[Message]:
        """The `limit` most recent messages in ascending sequence order."""
        rows = self._session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.seq.desc())
            .limit(limit)
        ).all()
        return list(reversed(rows))

    def count(self, conversation_id: str) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.conversation_id == conversation_id)
            )
            or 0
        )

    def _next_seq(self, conversation_id: str) -> int:
        current = self._session.scalar(
            select(func.max(Message.seq)).where(
                Message.conversation_id == conversation_id
            )
        )
        return (current or 0) + 1


def to_context_message(message: Message) -> ContextMessage:
    return ContextMessage(role=message.role, content=message.content)


def _derive_title(content: str) -> str:
    trimmed = content.strip()
    if len(trimmed) > 50:
        return trimmed[:50] + "…"
    return trimmed


def _now() -> datetime:
    return datetime.now(UTC)

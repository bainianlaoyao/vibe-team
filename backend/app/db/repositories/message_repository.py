from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, select

from app.db.enums import MessageRole, MessageType
from app.db.models import Message
from app.db.repositories.common import Page, Pagination, paginate


@dataclass(frozen=True, slots=True)
class MessageFilters:
    conversation_id: int | None = None
    role: MessageRole | None = None
    message_type: MessageType | None = None
    after_sequence: int | None = None


class MessageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, message: Message) -> Message:
        self.session.add(message)
        self.session.commit()
        self.session.refresh(message)
        return message

    def create_batch(self, messages: list[Message]) -> list[Message]:
        for msg in messages:
            self.session.add(msg)
        self.session.commit()
        for msg in messages:
            self.session.refresh(msg)
        return messages

    def get(self, message_id: int) -> Message | None:
        return self.session.get(Message, message_id)

    def get_next_sequence_num(self, conversation_id: int) -> int:
        statement = select(func.max(Message.sequence_num)).where(
            Message.conversation_id == conversation_id
        )
        result: Any = self.session.exec(statement).one()
        max_seq = result[0] if hasattr(result, "__getitem__") else result
        return (max_seq or 0) + 1

    def list_messages(
        self,
        *,
        pagination: Pagination | None = None,
        filters: MessageFilters | None = None,
    ) -> Page[Message]:
        active_filters = filters or MessageFilters()
        active_pagination = pagination or Pagination()

        statement = select(Message)
        if active_filters.conversation_id is not None:
            statement = statement.where(Message.conversation_id == active_filters.conversation_id)
        if active_filters.role is not None:
            statement = statement.where(Message.role == active_filters.role.value)
        if active_filters.message_type is not None:
            statement = statement.where(Message.message_type == active_filters.message_type.value)
        if active_filters.after_sequence is not None:
            statement = statement.where(Message.sequence_num > active_filters.after_sequence)

        statement = statement.order_by(Message.sequence_num.asc())  # type: ignore[attr-defined]
        return paginate(self.session, statement, pagination=active_pagination)

    def list_by_conversation(
        self,
        conversation_id: int,
        *,
        after_sequence: int | None = None,
        limit: int = 100,
    ) -> list[Message]:
        statement = select(Message).where(Message.conversation_id == conversation_id)
        if after_sequence is not None:
            statement = statement.where(Message.sequence_num > after_sequence)
        statement = statement.order_by(Message.sequence_num.asc()).limit(limit)  # type: ignore[attr-defined]
        return list(self.session.exec(statement).all())

    def get_latest_message(self, conversation_id: int) -> Message | None:
        statement = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.sequence_num.desc())  # type: ignore[attr-defined]
            .limit(1)
        )
        return self.session.exec(statement).first()

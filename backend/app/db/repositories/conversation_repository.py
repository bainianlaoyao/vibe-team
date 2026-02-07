from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import update
from sqlmodel import Session, select

from app.db.enums import ConversationStatus
from app.db.models import Conversation, utc_now
from app.db.repositories.common import OptimisticLockError, Page, Pagination, paginate


@dataclass(frozen=True, slots=True)
class ConversationFilters:
    project_id: int | None = None
    agent_id: int | None = None
    task_id: int | None = None
    status: ConversationStatus | None = None
    title_query: str | None = None


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, conversation: Conversation) -> Conversation:
        self.session.add(conversation)
        self.session.commit()
        self.session.refresh(conversation)
        return conversation

    def get(self, conversation_id: int) -> Conversation | None:
        return self.session.get(Conversation, conversation_id)

    def list(
        self,
        *,
        pagination: Pagination | None = None,
        filters: ConversationFilters | None = None,
    ) -> Page[Conversation]:
        active_filters = filters or ConversationFilters()
        active_pagination = pagination or Pagination()

        statement = select(Conversation)
        if active_filters.project_id is not None:
            statement = statement.where(Conversation.project_id == active_filters.project_id)
        if active_filters.agent_id is not None:
            statement = statement.where(Conversation.agent_id == active_filters.agent_id)
        if active_filters.task_id is not None:
            statement = statement.where(Conversation.task_id == active_filters.task_id)
        if active_filters.status is not None:
            statement = statement.where(Conversation.status == active_filters.status.value)
        if active_filters.title_query:
            statement = statement.where(
                Conversation.title.ilike(f"%{active_filters.title_query}%")  # type: ignore[attr-defined]
            )

        statement = statement.order_by(Conversation.id.desc())  # type: ignore[union-attr]
        return paginate(self.session, statement, pagination=active_pagination)

    def update_status(
        self,
        *,
        conversation_id: int,
        status: ConversationStatus,
        expected_version: int,
    ) -> Conversation:
        now = utc_now()
        values: dict[str, object] = {
            "status": status.value,
            "updated_at": now,
            "version": expected_version + 1,
        }
        if status == ConversationStatus.CLOSED:
            values["closed_at"] = now

        statement = (
            update(Conversation)
            .where(Conversation.id == conversation_id)  # type: ignore[arg-type]
            .where(Conversation.version == expected_version)  # type: ignore[arg-type]
            .values(**values)
        )
        result = self.session.exec(statement)

        if result.rowcount != 1:
            self.session.rollback()
            raise OptimisticLockError(
                f"conversation {conversation_id} version mismatch, expected {expected_version}"
            )

        self.session.commit()
        updated = self.session.get(Conversation, conversation_id)
        if updated is None:
            raise OptimisticLockError(
                f"conversation {conversation_id} missing after optimistic update"
            )
        return updated

    def update_title(
        self,
        *,
        conversation_id: int,
        title: str,
        expected_version: int,
    ) -> Conversation:
        statement = (
            update(Conversation)
            .where(Conversation.id == conversation_id)  # type: ignore[arg-type]
            .where(Conversation.version == expected_version)  # type: ignore[arg-type]
            .values(
                title=title,
                updated_at=utc_now(),
                version=expected_version + 1,
            )
        )
        result = self.session.exec(statement)

        if result.rowcount != 1:
            self.session.rollback()
            raise OptimisticLockError(
                f"conversation {conversation_id} version mismatch, expected {expected_version}"
            )

        self.session.commit()
        updated = self.session.get(Conversation, conversation_id)
        if updated is None:
            raise OptimisticLockError(
                f"conversation {conversation_id} missing after optimistic update"
            )
        return updated

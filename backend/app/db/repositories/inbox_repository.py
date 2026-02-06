from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import update
from sqlmodel import Session, select

from app.db.enums import InboxCategory, InboxStatus, SourceType
from app.db.models import InboxItem, utc_now
from app.db.repositories.common import OptimisticLockError, Page, Pagination, paginate


@dataclass(frozen=True, slots=True)
class InboxFilters:
    project_id: int | None = None
    source_type: SourceType | None = None
    category: InboxCategory | None = None
    status: InboxStatus | None = None


class InboxRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, item: InboxItem) -> InboxItem:
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def list(
        self,
        *,
        pagination: Pagination | None = None,
        filters: InboxFilters | None = None,
    ) -> Page[InboxItem]:
        active_filters = filters or InboxFilters()
        active_pagination = pagination or Pagination()

        statement = select(InboxItem)
        if active_filters.project_id is not None:
            statement = statement.where(InboxItem.project_id == active_filters.project_id)
        if active_filters.source_type is not None:
            statement = statement.where(InboxItem.source_type == active_filters.source_type.value)
        if active_filters.category is not None:
            statement = statement.where(InboxItem.category == active_filters.category.value)
        if active_filters.status is not None:
            statement = statement.where(InboxItem.status == active_filters.status.value)

        statement = statement.order_by(InboxItem.created_at.desc(), InboxItem.id.desc())
        return paginate(self.session, statement, pagination=active_pagination)

    def update_status(
        self,
        *,
        item_id: int,
        status: InboxStatus,
        expected_version: int,
        resolver: str | None = None,
    ) -> InboxItem:
        values: dict[str, object] = {
            "status": status.value,
            "version": expected_version + 1,
        }

        if status == InboxStatus.RESOLVED:
            values["resolved_at"] = utc_now()
            values["resolver"] = resolver
        elif status == InboxStatus.OPEN:
            values["resolved_at"] = None
            values["resolver"] = None

        statement = (
            update(InboxItem)
            .where(InboxItem.id == item_id)
            .where(InboxItem.version == expected_version)
            .values(**values)
        )
        result = self.session.exec(statement)

        if result.rowcount != 1:
            self.session.rollback()
            raise OptimisticLockError(
                f"inbox_item {item_id} version mismatch, expected {expected_version}"
            )

        self.session.commit()
        updated = self.session.get(InboxItem, item_id)
        if updated is None:
            raise OptimisticLockError(f"inbox_item {item_id} missing after optimistic update")
        return updated

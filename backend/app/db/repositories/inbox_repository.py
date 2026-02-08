from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import update
from sqlmodel import Session, select

from app.db.enums import InboxItemType, InboxStatus, SourceType
from app.db.models import Event, InboxItem, utc_now
from app.db.repositories.common import OptimisticLockError, Page, Pagination, paginate

INBOX_ITEM_CREATED_EVENT_TYPE = "inbox.item.created"


def _build_inbox_item_payload(item: InboxItem) -> dict[str, object]:
    if item.id is None:
        raise ValueError("Inbox item must be persisted before creating an event payload.")
    return {
        "item_id": item.id,
        "project_id": item.project_id,
        "source_type": item.source_type.value,
        "source_id": item.source_id,
        "item_type": item.item_type.value,
        "status": item.status.value,
        "version": item.version,
    }


@dataclass(frozen=True, slots=True)
class InboxFilters:
    project_id: int | None = None
    source_type: SourceType | None = None
    item_type: InboxItemType | None = None
    status: InboxStatus | None = None


class InboxRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, item: InboxItem, *, trace_id: str | None = None) -> InboxItem:
        self.session.add(item)
        self.session.flush()
        self.session.add(
            Event(
                project_id=item.project_id,
                event_type=INBOX_ITEM_CREATED_EVENT_TYPE,
                payload_json=_build_inbox_item_payload(item),
                trace_id=trace_id,
            )
        )
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
        if active_filters.item_type is not None:
            statement = statement.where(InboxItem.item_type == active_filters.item_type.value)
        if active_filters.status is not None:
            statement = statement.where(InboxItem.status == active_filters.status.value)

        statement = statement.order_by(InboxItem.created_at.desc(), InboxItem.id.desc())  # type: ignore[attr-defined,union-attr]
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

        if status == InboxStatus.CLOSED:
            values["resolved_at"] = utc_now()
            values["resolver"] = resolver
        elif status == InboxStatus.OPEN:
            values["resolved_at"] = None
            values["resolver"] = None

        statement = (
            update(InboxItem)
            .where(InboxItem.id == item_id)  # type: ignore[arg-type]
            .where(InboxItem.version == expected_version)  # type: ignore[arg-type]
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

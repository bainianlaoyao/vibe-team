from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.errors import ApiException, error_response_docs
from app.db.enums import InboxItemType, InboxStatus
from app.db.models import Event, InboxItem, utc_now
from app.db.session import get_session

INBOX_ITEM_CLOSED_EVENT_TYPE = "inbox.item.closed"
USER_INPUT_SUBMITTED_EVENT_TYPE = "user.input.submitted"
DEFAULT_RESOLVER = "user"

router = APIRouter(prefix="/inbox", tags=["inbox"])


class InboxItemRead(BaseModel):
    id: int
    project_id: int
    source_type: str
    source_id: str
    item_type: str
    title: str
    content: str
    status: str
    created_at: datetime
    resolved_at: datetime | None
    resolver: str | None
    version: int
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 31,
                "project_id": 1,
                "source_type": "task",
                "source_id": "task:18",
                "item_type": "await_user_input",
                "title": "Need user decision",
                "content": "Select target release branch for deployment.",
                "status": "open",
                "created_at": "2026-02-06T18:30:00Z",
                "resolved_at": None,
                "resolver": None,
                "version": 1,
            }
        },
    )


class InboxCloseRequest(BaseModel):
    user_input: str | None = Field(default=None, max_length=4000)
    resolver: str | None = Field(default=DEFAULT_RESOLVER, min_length=1, max_length=120)
    trace_id: str | None = Field(default=None, max_length=64)
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_input": "Proceed with the release after checklist pass.",
                "resolver": "product-owner",
                "trace_id": "trace-inbox-close-001",
            }
        }
    )


DbSession = Annotated[Session, Depends(get_session)]


def _get_inbox_item_or_404(session: Session, item_id: int) -> InboxItem:
    item = session.get(InboxItem, item_id)
    if item is None:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "INBOX_ITEM_NOT_FOUND",
            f"Inbox item {item_id} does not exist.",
        )
    return item


def _normalized_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _enum_value(value: str | StrEnum) -> str:
    return value.value if isinstance(value, StrEnum) else str(value)


def _commit_or_conflict(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "RESOURCE_CONFLICT",
            "Operation violates a database constraint.",
        ) from exc


@router.get(
    "",
    response_model=list[InboxItemRead],
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_422_UNPROCESSABLE_ENTITY),
    ),
)
def list_inbox_items(
    session: DbSession,
    project_id: Annotated[int | None, Query(gt=0)] = None,
    item_type: Annotated[InboxItemType | None, Query(alias="item_type")] = None,
    status_filter: Annotated[InboxStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[InboxItemRead]:
    statement = select(InboxItem).order_by(InboxItem.created_at.desc(), InboxItem.id.desc())  # type: ignore[attr-defined,union-attr]
    if project_id is not None:
        statement = statement.where(InboxItem.project_id == project_id)
    if item_type is not None:
        statement = statement.where(InboxItem.item_type == item_type.value)
    if status_filter is not None:
        statement = statement.where(InboxItem.status == status_filter.value)
    statement = statement.offset(offset).limit(limit)
    return [InboxItemRead.model_validate(item) for item in session.exec(statement).all()]


@router.post(
    "/{item_id}/close",
    response_model=InboxItemRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ),
    ),
)
def close_inbox_item(item_id: int, payload: InboxCloseRequest, session: DbSession) -> InboxItemRead:
    item = _get_inbox_item_or_404(session, item_id)
    current_status = _enum_value(item.status)
    if current_status == InboxStatus.CLOSED.value:
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "INBOX_ITEM_ALREADY_CLOSED",
            f"Inbox item {item_id} is already closed.",
        )

    user_input = _normalized_optional_text(payload.user_input)
    item_type = _enum_value(item.item_type)
    if item_type == InboxItemType.AWAIT_USER_INPUT.value and user_input is None:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "USER_INPUT_REQUIRED",
            "Closing await_user_input items requires non-empty user_input.",
        )

    resolver = _normalized_optional_text(payload.resolver) or DEFAULT_RESOLVER
    source_type = _enum_value(item.source_type)
    previous_status = current_status
    item.status = InboxStatus.CLOSED
    item.resolved_at = utc_now()
    item.resolver = resolver
    item.version += 1

    closed_payload: dict[str, object] = {
        "item_id": item.id,
        "project_id": item.project_id,
        "source_type": source_type,
        "source_id": item.source_id,
        "item_type": item_type,
        "previous_status": previous_status,
        "status": InboxStatus.CLOSED.value,
        "resolver": resolver,
        "version": item.version,
        "user_input_submitted": user_input is not None,
    }
    session.add(
        Event(
            project_id=item.project_id,
            event_type=INBOX_ITEM_CLOSED_EVENT_TYPE,
            payload_json=closed_payload,
            trace_id=payload.trace_id,
        )
    )

    if user_input is not None:
        if item.id is None:
            raise ApiException(
                status.HTTP_409_CONFLICT,
                "RESOURCE_CONFLICT",
                "Inbox item missing primary key during close operation.",
            )
        session.add(
            Event(
                project_id=item.project_id,
                event_type=USER_INPUT_SUBMITTED_EVENT_TYPE,
                payload_json={
                    "item_id": item.id,
                    "project_id": item.project_id,
                    "source_type": source_type,
                    "source_id": item.source_id,
                    "item_type": item_type,
                    "user_input": user_input,
                    "resolver": resolver,
                },
                trace_id=payload.trace_id,
            )
        )

    _commit_or_conflict(session)
    session.refresh(item)
    return InboxItemRead.model_validate(item)

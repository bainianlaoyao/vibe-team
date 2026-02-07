from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.api.errors import ApiException, error_response_docs
from app.db.enums import ConversationStatus, MessageRole, MessageType
from app.db.models import Agent, Conversation, Message, Project, Task
from app.db.repositories import (
    ConversationFilters,
    ConversationRepository,
    MessageFilters,
    MessageRepository,
    Pagination,
)
from app.db.session import get_session

router = APIRouter(prefix="/conversations", tags=["conversations"])


# ============================================================================
# Request/Response Schemas
# ============================================================================


class ConversationCreate(BaseModel):
    project_id: int = Field(gt=0)
    agent_id: int = Field(gt=0)
    task_id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=200)
    context_json: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": 1,
                "agent_id": 1,
                "task_id": None,
                "title": "Discuss implementation details",
                "context_json": {"focus": "architecture"},
            }
        }
    )


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: ConversationStatus | None = None
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Updated discussion topic",
                "status": "closed",
            }
        }
    )

    @model_validator(mode="after")
    def validate_non_empty_payload(self) -> ConversationUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        return self


class ConversationRead(BaseModel):
    id: int
    project_id: int
    agent_id: int
    task_id: int | None
    title: str
    status: str
    context_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    version: int
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "project_id": 1,
                "agent_id": 1,
                "task_id": None,
                "title": "Discuss implementation details",
                "status": "active",
                "context_json": {"focus": "architecture"},
                "created_at": "2026-02-07T12:00:00Z",
                "updated_at": "2026-02-07T12:00:00Z",
                "closed_at": None,
                "version": 1,
            }
        },
    )


class MessageCreate(BaseModel):
    role: MessageRole
    message_type: MessageType = Field(default=MessageType.TEXT)
    content: str = Field(min_length=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    token_count: int | None = Field(default=None, ge=0)
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "role": "user",
                "message_type": "text",
                "content": "Can you explain the architecture?",
                "metadata_json": {},
            }
        }
    )


class MessageRead(BaseModel):
    id: int
    conversation_id: int
    role: str
    message_type: str
    content: str
    metadata_json: dict[str, Any]
    sequence_num: int
    created_at: datetime
    token_count: int | None
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "conversation_id": 1,
                "role": "user",
                "message_type": "text",
                "content": "Can you explain the architecture?",
                "metadata_json": {},
                "sequence_num": 1,
                "created_at": "2026-02-07T12:00:00Z",
                "token_count": 15,
            }
        },
    )


class ConversationListResponse(BaseModel):
    items: list[ConversationRead]
    total: int
    page: int
    page_size: int


class MessageListResponse(BaseModel):
    items: list[MessageRead]
    total: int
    page: int
    page_size: int


# ============================================================================
# Dependencies
# ============================================================================

DbSession = Annotated[Session, Depends(get_session)]


def _require_project(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "PROJECT_NOT_FOUND",
            f"Project {project_id} does not exist.",
        )
    return project


def _require_agent(session: Session, agent_id: int) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "AGENT_NOT_FOUND",
            f"Agent {agent_id} does not exist.",
        )
    return agent


def _get_conversation_or_404(session: Session, conversation_id: int) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "CONVERSATION_NOT_FOUND",
            f"Conversation {conversation_id} does not exist.",
        )
    return conversation


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


# ============================================================================
# Conversation Endpoints
# ============================================================================


@router.get(
    "",
    response_model=ConversationListResponse,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_422_UNPROCESSABLE_ENTITY),
    ),
)
def list_conversations(
    session: DbSession,
    project_id: Annotated[int | None, Query(gt=0)] = None,
    agent_id: Annotated[int | None, Query(gt=0)] = None,
    task_id: Annotated[int | None, Query(gt=0)] = None,
    status_filter: Annotated[ConversationStatus | None, Query(alias="status")] = None,
    title_query: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ConversationListResponse:
    repo = ConversationRepository(session)
    filters = ConversationFilters(
        project_id=project_id,
        agent_id=agent_id,
        task_id=task_id,
        status=status_filter,
        title_query=title_query,
    )
    result = repo.list(pagination=Pagination(page=page, page_size=page_size), filters=filters)
    return ConversationListResponse(
        items=[ConversationRead.model_validate(c) for c in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ConversationRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ),
    ),
)
def create_conversation(payload: ConversationCreate, session: DbSession) -> ConversationRead:
    _require_project(session, payload.project_id)
    _require_agent(session, payload.agent_id)
    if payload.task_id is not None:
        task = session.get(Task, payload.task_id)
        if task is None:
            raise ApiException(
                status.HTTP_404_NOT_FOUND,
                "TASK_NOT_FOUND",
                f"Task {payload.task_id} does not exist.",
            )

    conversation = Conversation(**payload.model_dump(mode="python"))
    session.add(conversation)
    _commit_or_conflict(session)
    session.refresh(conversation)
    return ConversationRead.model_validate(conversation)


@router.get(
    "/{conversation_id}",
    response_model=ConversationRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_ENTITY),
    ),
)
def get_conversation(conversation_id: int, session: DbSession) -> ConversationRead:
    return ConversationRead.model_validate(_get_conversation_or_404(session, conversation_id))


@router.patch(
    "/{conversation_id}",
    response_model=ConversationRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ),
    ),
)
def update_conversation(
    conversation_id: int, payload: ConversationUpdate, session: DbSession
) -> ConversationRead:
    conversation = _get_conversation_or_404(session, conversation_id)
    repo = ConversationRepository(session)

    if payload.status is not None and payload.title is not None:
        conversation = repo.update_status(
            conversation_id=conversation_id,
            status=payload.status,
            expected_version=conversation.version,
        )
        conversation = repo.update_title(
            conversation_id=conversation_id,
            title=payload.title,
            expected_version=conversation.version,
        )
    elif payload.status is not None:
        conversation = repo.update_status(
            conversation_id=conversation_id,
            status=payload.status,
            expected_version=conversation.version,
        )
    elif payload.title is not None:
        conversation = repo.update_title(
            conversation_id=conversation_id,
            title=payload.title,
            expected_version=conversation.version,
        )

    return ConversationRead.model_validate(conversation)


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_ENTITY),
    ),
)
def delete_conversation(conversation_id: int, session: DbSession) -> Response:
    conversation = _get_conversation_or_404(session, conversation_id)
    session.delete(conversation)
    _commit_or_conflict(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ============================================================================
# Message Endpoints
# ============================================================================


@router.get(
    "/{conversation_id}/messages",
    response_model=MessageListResponse,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_ENTITY),
    ),
)
def list_messages(
    conversation_id: int,
    session: DbSession,
    role: Annotated[MessageRole | None, Query()] = None,
    message_type: Annotated[MessageType | None, Query()] = None,
    after_sequence: Annotated[int | None, Query(ge=0)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> MessageListResponse:
    _get_conversation_or_404(session, conversation_id)
    repo = MessageRepository(session)
    filters = MessageFilters(
        conversation_id=conversation_id,
        role=role,
        message_type=message_type,
        after_sequence=after_sequence,
    )
    result = repo.list_messages(
        pagination=Pagination(page=page, page_size=page_size), filters=filters
    )
    return MessageListResponse(
        items=[MessageRead.model_validate(m) for m in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.post(
    "/{conversation_id}/messages",
    status_code=status.HTTP_201_CREATED,
    response_model=MessageRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ),
    ),
)
def create_message(conversation_id: int, payload: MessageCreate, session: DbSession) -> MessageRead:
    conversation = _get_conversation_or_404(session, conversation_id)
    if conversation.status == ConversationStatus.CLOSED:
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "CONVERSATION_CLOSED",
            "Cannot add messages to a closed conversation.",
        )

    repo = MessageRepository(session)
    sequence_num = repo.get_next_sequence_num(conversation_id)

    message = Message(
        conversation_id=conversation_id,
        role=payload.role,
        message_type=payload.message_type,
        content=payload.content,
        metadata_json=payload.metadata_json,
        sequence_num=sequence_num,
        token_count=payload.token_count,
    )
    message = repo.create(message)
    return MessageRead.model_validate(message)


@router.get(
    "/{conversation_id}/messages/{message_id}",
    response_model=MessageRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_ENTITY),
    ),
)
def get_message(conversation_id: int, message_id: int, session: DbSession) -> MessageRead:
    _get_conversation_or_404(session, conversation_id)
    repo = MessageRepository(session)
    message = repo.get(message_id)
    if message is None or message.conversation_id != conversation_id:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "MESSAGE_NOT_FOUND",
            f"Message {message_id} does not exist in conversation {conversation_id}.",
        )
    return MessageRead.model_validate(message)

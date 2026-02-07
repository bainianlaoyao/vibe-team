from __future__ import annotations

import asyncio
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.errors import ApiException, error_response_docs
from app.core.config import get_settings
from app.db.enums import CommentStatus, MessageRole, MessageType
from app.db.models import Agent, Comment, Conversation, Document, Message, Task
from app.db.session import get_session
from app.llm import create_llm_client
from app.runtime import ConversationExecutor, ExecutionContext

router = APIRouter(prefix="/comments", tags=["comments"])


class CommentReplyRequest(BaseModel):
    agent_id: int | None = Field(default=None, gt=0)
    prompt: str | None = Field(default=None, min_length=1, max_length=4000)
    timeout_seconds: float | None = Field(default=90, gt=0, le=600)
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_id": 2,
                "prompt": "请根据评论给出修改方案并简述下一步。",
                "timeout_seconds": 90,
            }
        }
    )


class CommentReplyResponse(BaseModel):
    comment_id: int
    conversation_id: int
    assistant_message_id: int | None
    status: str


class _NoopPusher:
    async def send_chunk(self, content: str) -> bool:
        return True

    async def send_tool_call(self, tool_call: Any) -> bool:
        return True

    async def send_tool_result(self, tool_id: str, result: str) -> bool:
        return True

    async def send_thinking(self, content: str) -> bool:
        return True

    async def send_request_input(self, content: str) -> bool:
        return True

    async def send_complete(self, usage: Any) -> bool:
        return True

    async def send_error(self, code: str, message: str) -> bool:
        return True


DbSession = Annotated[Session, Depends(get_session)]


def _resolve_project_and_task(session: Session, comment: Comment) -> tuple[int, int | None]:
    if comment.task_id is not None:
        task = session.get(Task, comment.task_id)
        if task is None:
            raise ApiException(
                status.HTTP_404_NOT_FOUND,
                "TASK_NOT_FOUND",
                "Comment task not found.",
            )
        return task.project_id, task.id
    if comment.document_id is None:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INVALID_COMMENT",
            "Comment must reference a task or document.",
        )
    document = session.get(Document, comment.document_id)
    if document is None:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "DOCUMENT_NOT_FOUND",
            "Comment document not found.",
        )
    return document.project_id, None


def _resolve_agent(
    session: Session,
    *,
    project_id: int,
    task_id: int | None,
    requested_agent_id: int | None,
) -> Agent:
    if requested_agent_id is not None:
        agent = session.get(Agent, requested_agent_id)
        if agent is None or agent.project_id != project_id:
            raise ApiException(
                status.HTTP_404_NOT_FOUND,
                "AGENT_NOT_FOUND",
                "Requested agent does not belong to the comment project.",
            )
        return agent

    if task_id is not None:
        task = session.get(Task, task_id)
        if task is not None and task.assignee_agent_id is not None:
            task_agent = session.get(Agent, task.assignee_agent_id)
            if task_agent is not None and task_agent.project_id == project_id:
                return task_agent

    fallback = session.exec(
        select(Agent)
        .where(Agent.project_id == project_id)
        .order_by(cast(Any, Agent.id).asc())
        .limit(1)
    ).first()
    if fallback is None:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "AGENT_NOT_FOUND",
            "No available agent in comment project.",
        )
    return fallback


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


@router.post(
    "/{comment_id}/reply",
    response_model=CommentReplyResponse,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ),
    ),
)
def reply_comment(
    comment_id: int,
    payload: CommentReplyRequest,
    session: DbSession,
) -> CommentReplyResponse:
    comment = session.get(Comment, comment_id)
    if comment is None:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "COMMENT_NOT_FOUND",
            "Comment does not exist.",
        )

    project_id, task_id = _resolve_project_and_task(session, comment)
    agent = _resolve_agent(
        session,
        project_id=project_id,
        task_id=task_id,
        requested_agent_id=payload.agent_id,
    )
    prompt = payload.prompt or "请根据该评论给出处理建议并说明下一步。"
    if agent.id is None:
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "RESOURCE_CONFLICT",
            "Agent missing primary key.",
        )
    agent_id = agent.id

    conversation = Conversation(
        project_id=project_id,
        agent_id=agent_id,
        task_id=task_id,
        title=f"Comment #{comment_id} Reply",
        context_json={
            "source": "comment_reply",
            "comment_id": comment.id,
            "comment_text": comment.comment_text,
        },
    )
    session.add(conversation)
    _commit_or_conflict(session)
    session.refresh(conversation)
    if conversation.id is None:
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "RESOURCE_CONFLICT",
            "Conversation creation failed.",
        )

    user_message = Message(
        conversation_id=conversation.id,
        role=MessageRole.USER,
        message_type=MessageType.TEXT,
        content=f"{prompt}\n\n评论内容：{comment.comment_text}",
        sequence_num=1,
        metadata_json={"comment_id": comment.id},
    )
    session.add(user_message)
    _commit_or_conflict(session)
    session.refresh(user_message)

    llm_client = create_llm_client(provider=agent.model_provider, settings=get_settings())
    executor = ConversationExecutor(llm_client=cast(Any, llm_client))
    result = asyncio.run(
        executor.execute(
            context=ExecutionContext(
                conversation_id=conversation.id,
                agent_id=agent_id,
                session_id=f"comment-{comment_id}",
                user_message_id=user_message.id or 0,
                user_content=user_message.content,
            ),
            pusher=_NoopPusher(),
            timeout_seconds=payload.timeout_seconds,
        )
    )
    if not result.success:
        raise ApiException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "LLM_UNAVAILABLE",
            result.error_message or "Comment reply execution failed.",
        )

    comment.conversation_id = conversation.id
    comment.status = CommentStatus.ADDRESSED
    comment.version += 1
    _commit_or_conflict(session)

    return CommentReplyResponse(
        comment_id=comment.id or comment_id,
        conversation_id=conversation.id,
        assistant_message_id=result.assistant_message_id,
        status=str(comment.status),
    )

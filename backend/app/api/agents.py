from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.errors import ApiException, error_response_docs
from app.db.models import Agent, Project, Task, utc_now
from app.db.session import get_session

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class AgentCreate(BaseModel):
    project_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=80)
    model_provider: str = Field(min_length=1, max_length=80)
    model_name: str = Field(min_length=1, max_length=120)
    initial_persona_prompt: str = Field(min_length=1)
    enabled_tools_json: list[str] = Field(default_factory=list)
    status: AgentStatus = Field(default=AgentStatus.ACTIVE)
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": 1,
                "name": "Planning Agent",
                "role": "planner",
                "model_provider": "openai",
                "model_name": "gpt-4.1-mini",
                "initial_persona_prompt": "You are responsible for planning backend tasks.",
                "enabled_tools_json": [
                    "list_path_tool",
                    "read_file_tool",
                    "search_project_files_tool",
                ],
                "status": "active",
            }
        }
    )


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, min_length=1, max_length=80)
    model_provider: str | None = Field(default=None, min_length=1, max_length=80)
    model_name: str | None = Field(default=None, min_length=1, max_length=120)
    initial_persona_prompt: str | None = Field(default=None, min_length=1)
    enabled_tools_json: list[str] | None = None
    status: AgentStatus | None = None
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "role": "reviewer",
                "status": "inactive",
                "enabled_tools_json": ["read_file_tool"],
            }
        }
    )

    @model_validator(mode="after")
    def validate_non_empty_payload(self) -> AgentUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        return self


class AgentRead(BaseModel):
    id: int
    project_id: int
    name: str
    role: str
    model_provider: str
    model_name: str
    initial_persona_prompt: str
    enabled_tools_json: list[str]
    status: str
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 12,
                "project_id": 1,
                "name": "Planning Agent",
                "role": "planner",
                "model_provider": "openai",
                "model_name": "gpt-4.1-mini",
                "initial_persona_prompt": "You are responsible for planning backend tasks.",
                "enabled_tools_json": [
                    "list_path_tool",
                    "read_file_tool",
                    "search_project_files_tool",
                ],
                "status": "active",
            }
        },
    )


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


def _get_agent_or_404(session: Session, agent_id: int) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "AGENT_NOT_FOUND",
            f"Agent {agent_id} does not exist.",
        )
    return agent


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
    response_model=list[AgentRead],
    responses=error_response_docs(status.HTTP_422_UNPROCESSABLE_ENTITY),
)
def list_agents(
    session: DbSession,
    project_id: Annotated[int | None, Query(gt=0)] = None,
    status_filter: Annotated[AgentStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AgentRead]:
    statement = select(Agent).order_by(Agent.id).offset(offset).limit(limit)
    if project_id is not None:
        statement = statement.where(Agent.project_id == project_id)
    if status_filter is not None:
        statement = statement.where(Agent.status == status_filter.value)
    return [AgentRead.model_validate(agent) for agent in session.exec(statement).all()]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=AgentRead,
    responses=error_response_docs(
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    ),
)
def create_agent(payload: AgentCreate, session: DbSession) -> AgentRead:
    _require_project(session, payload.project_id)

    agent = Agent(**payload.model_dump(mode="python"))
    session.add(agent)
    _commit_or_conflict(session)
    session.refresh(agent)
    return AgentRead.model_validate(agent)


@router.get(
    "/{agent_id}",
    response_model=AgentRead,
    responses=error_response_docs(status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_ENTITY),
)
def get_agent(agent_id: int, session: DbSession) -> AgentRead:
    return AgentRead.model_validate(_get_agent_or_404(session, agent_id))


@router.patch(
    "/{agent_id}",
    response_model=AgentRead,
    responses=error_response_docs(
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    ),
)
def update_agent(agent_id: int, payload: AgentUpdate, session: DbSession) -> AgentRead:
    agent = _get_agent_or_404(session, agent_id)
    update_data = payload.model_dump(exclude_unset=True, mode="python")
    for field_name, value in update_data.items():
        setattr(agent, field_name, value)
    _commit_or_conflict(session)
    session.refresh(agent)
    return AgentRead.model_validate(agent)


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_response_docs(status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_ENTITY),
)
def delete_agent(agent_id: int, session: DbSession) -> Response:
    agent = _get_agent_or_404(session, agent_id)
    assigned_tasks = session.exec(select(Task).where(Task.assignee_agent_id == agent_id)).all()
    for task in assigned_tasks:
        task.assignee_agent_id = None
        task.updated_at = utc_now()
    session.delete(agent)
    _commit_or_conflict(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

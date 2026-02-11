from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.agents.persona_loader import PersonaLoader
from app.api.errors import ApiException, error_response_docs
from app.db.enums import TaskRunStatus, TaskStatus
from app.db.models import Agent, Project, Task, TaskRun, utc_now
from app.db.session import get_session
from app.security import SecureFileGateway

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
    initial_persona_prompt: str | None = Field(default=None, min_length=1)
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


class PersonaUpdate(BaseModel):
    content: str = Field(min_length=1)


class AgentRead(BaseModel):
    id: int
    project_id: int
    name: str
    role: str
    model_provider: str
    model_name: str
    persona_path: str | None
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
                "persona_path": "docs/agents/planning_agent.md",
                "enabled_tools_json": [
                    "list_path_tool",
                    "read_file_tool",
                    "search_project_files_tool",
                ],
                "status": "active",
            }
        },
    )


class AgentHealthRead(BaseModel):
    agent_id: int
    health: int = Field(ge=0, le=100)
    state: str
    active_task_count: int
    blocked_task_count: int
    failed_task_count: int
    done_task_count: int
    active_run_count: int


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


def _health_state_from_score(score: int) -> str:
    if score >= 75:
        return "healthy"
    if score >= 45:
        return "degraded"
    return "critical"


def _ensure_agents_dir(project_root: str) -> Path:
    """Ensure docs/agents directory exists."""
    agents_dir = Path(project_root) / "docs" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    return agents_dir


def _create_persona_file(project_root: str, agent_name: str, content: str) -> str:
    """Create persona file and return relative path.

    Uses atomic write pattern from roles.py.
    """
    agents_dir = _ensure_agents_dir(project_root)
    sanitized = agent_name.strip().lower().replace(" ", "_")
    file_path = agents_dir / f"{sanitized}.md"
    temp_path = file_path.with_suffix(f"{file_path.suffix}.tmp")

    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(file_path)

    return file_path.relative_to(Path(project_root)).as_posix()


def _update_persona_file(project_root: str, persona_path: str, content: str) -> None:
    """Update existing persona file atomically."""
    file_path = Path(project_root) / persona_path
    temp_path = file_path.with_suffix(f"{file_path.suffix}.tmp")

    # Ensure parent dir exists (in case path is custom)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(file_path)


def _delete_persona_file(project_root: str, persona_path: str) -> None:
    """Delete persona file if it exists."""
    file_path = Path(project_root) / persona_path
    if file_path.exists():
        file_path.unlink()


@router.get(
    "",
    response_model=list[AgentRead],
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_422_UNPROCESSABLE_ENTITY),
    ),
)
def list_agents(
    session: DbSession,
    project_id: Annotated[int | None, Query(gt=0)] = None,
    status_filter: Annotated[AgentStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AgentRead]:
    statement = select(Agent).order_by(Agent.id).offset(offset).limit(limit)  # type: ignore[arg-type]
    if project_id is not None:
        statement = statement.where(Agent.project_id == project_id)
    if status_filter is not None:
        statement = statement.where(Agent.status == status_filter.value)
    return [AgentRead.model_validate(agent) for agent in session.exec(statement).all()]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=AgentRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ),
    ),
)
def create_agent(payload: AgentCreate, session: DbSession) -> AgentRead:
    project = _require_project(session, payload.project_id)

    # Handle persona file creation
    persona_path = None
    if payload.initial_persona_prompt:
        persona_path = _create_persona_file(
            project.root_path,
            payload.name,
            payload.initial_persona_prompt,
        )
    else:
        # Create default persona file
        default_content = f"# {payload.name}\n\nDefault persona for {payload.name}."
        persona_path = _create_persona_file(
            project.root_path,
            payload.name,
            default_content,
        )

    agent_data = payload.model_dump(exclude={"initial_persona_prompt"}, mode="python")
    agent_data["persona_path"] = persona_path

    agent = Agent(**agent_data)
    session.add(agent)
    _commit_or_conflict(session)
    session.refresh(agent)
    return AgentRead.model_validate(agent)


@router.get(
    "/{agent_id}",
    response_model=AgentRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_ENTITY),
    ),
)
def get_agent(agent_id: int, session: DbSession) -> AgentRead:
    return AgentRead.model_validate(_get_agent_or_404(session, agent_id))


@router.get(
    "/{agent_id}/health",
    response_model=AgentHealthRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_ENTITY),
    ),
)
def get_agent_health(agent_id: int, session: DbSession) -> AgentHealthRead:
    _get_agent_or_404(session, agent_id)
    tasks = list(session.exec(select(Task).where(Task.assignee_agent_id == agent_id)).all())
    active_runs = list(
        session.exec(
            select(TaskRun).where(
                TaskRun.agent_id == agent_id,
                cast(Any, TaskRun.run_status).in_(
                    [
                        TaskRunStatus.RUNNING.value,
                        TaskRunStatus.RETRY_SCHEDULED.value,
                        TaskRunStatus.INTERRUPTED.value,
                    ]
                ),
            )
        ).all()
    )
    blocked_task_count = sum(1 for task in tasks if str(task.status) == TaskStatus.BLOCKED.value)
    failed_task_count = sum(1 for task in tasks if str(task.status) == TaskStatus.FAILED.value)
    done_task_count = sum(1 for task in tasks if str(task.status) == TaskStatus.DONE.value)
    active_task_count = sum(1 for task in tasks if str(task.status) == TaskStatus.RUNNING.value)

    raw_score = 100
    raw_score -= blocked_task_count * 20
    raw_score -= failed_task_count * 15
    raw_score -= len(active_runs) * 5
    raw_score += done_task_count * 2
    health = max(0, min(100, raw_score))
    return AgentHealthRead(
        agent_id=agent_id,
        health=health,
        state=_health_state_from_score(health),
        active_task_count=active_task_count,
        blocked_task_count=blocked_task_count,
        failed_task_count=failed_task_count,
        done_task_count=done_task_count,
        active_run_count=len(active_runs),
    )


@router.patch(
    "/{agent_id}",
    response_model=AgentRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ),
    ),
)
def update_agent(agent_id: int, payload: AgentUpdate, session: DbSession) -> AgentRead:
    agent = _get_agent_or_404(session, agent_id)
    project = _require_project(session, agent.project_id)

    update_data = payload.model_dump(
        exclude_unset=True, exclude={"initial_persona_prompt"}, mode="python"
    )

    # Handle persona file update
    if "initial_persona_prompt" in payload.model_fields_set:
        persona_content = payload.initial_persona_prompt
        if persona_content is not None:
            if agent.persona_path:
                _update_persona_file(project.root_path, agent.persona_path, persona_content)
            else:
                persona_path = _create_persona_file(
                    project.root_path,
                    agent.name,
                    persona_content,
                )
                update_data["persona_path"] = persona_path

    # Handle name change (requires renaming file)
    if "name" in update_data and update_data["name"] != agent.name:
        new_name = update_data["name"]
        old_path = agent.persona_path

        # Only rename if using standard naming convention
        # If user manually changed path or it doesn't match name, we might want to be careful
        # For MVP, we'll create a new file for the new name if the old one existed

        # We need to know if we just updated content above or not.
        # But _create_persona_file overwrites.

        # Let's simplify: always create new file path for new name
        # If content was updated above, we use that. If not, we try to read old file.

        content_to_write = ""
        if "initial_persona_prompt" in payload.model_fields_set and payload.initial_persona_prompt:
            content_to_write = payload.initial_persona_prompt
        elif old_path:
            old_full_path = Path(project.root_path) / old_path
            if old_full_path.exists():
                content_to_write = old_full_path.read_text(encoding="utf-8")

        if not content_to_write:
            content_to_write = f"# {new_name}\n\nRenamed from {agent.name}"

        new_path = _create_persona_file(
            project.root_path,
            new_name,
            content_to_write,
        )

        update_data["persona_path"] = new_path

        # Clean up old file if it matches standard convention for old name
        # For safety in MVP, maybe we don't auto-delete on rename?
        # The plan said: "Handle name change (requires renaming file)"
        # Let's stick to the plan's logic: rename file.

        if old_path:
            old_file = Path(project.root_path) / old_path
            new_file = Path(project.root_path) / new_path
            # If we didn't just create new_file via _create_persona_file above...
            # Actually _create_persona_file was called.
            # So we should delete old file.
            if old_file.exists() and old_file != new_file:
                old_file.unlink()

    for field_name, value in update_data.items():
        setattr(agent, field_name, value)
    _commit_or_conflict(session)
    session.refresh(agent)
    return AgentRead.model_validate(agent)


@router.get(
    "/{agent_id}/persona",
    response_model=dict[str, str],
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ),
    ),
)
def get_agent_persona(agent_id: int, session: DbSession) -> dict[str, str]:
    """Get agent persona content directly."""
    agent = _get_agent_or_404(session, agent_id)
    project = _require_project(session, agent.project_id)

    if not agent.persona_path:
        return {"name": agent.name, "content": "(no persona configured)"}

    gateway = SecureFileGateway(root_path=project.root_path)
    loader = PersonaLoader(gateway=gateway)
    try:
        result = loader.load_by_path(agent.persona_path)
        return {
            "name": agent.name,
            "path": agent.persona_path,
            "content": result.content,
        }
    except FileNotFoundError:
        return {
            "name": agent.name,
            "path": agent.persona_path,
            "content": "(persona file missing)",
        }


@router.put(
    "/{agent_id}/persona",
    response_model=AgentRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ),
    ),
)
def update_agent_persona(
    agent_id: int,
    payload: PersonaUpdate,
    session: DbSession,
) -> AgentRead:
    """Update agent persona content directly.

    Accepts JSON body: {"content": "..."}
    """
    agent = _get_agent_or_404(session, agent_id)
    project = _require_project(session, agent.project_id)

    # Extract content
    persona_content = payload.content

    if agent.persona_path:
        _update_persona_file(project.root_path, agent.persona_path, persona_content)
    else:
        persona_path = _create_persona_file(project.root_path, agent.name, persona_content)
        agent.persona_path = persona_path
        session.add(agent)
        _commit_or_conflict(session)

    session.refresh(agent)
    return AgentRead.model_validate(agent)


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_ENTITY),
    ),
)
def delete_agent(agent_id: int, session: DbSession) -> Response:
    agent = _get_agent_or_404(session, agent_id)
    project = _require_project(session, agent.project_id)

    # Delete persona file
    if agent.persona_path:
        _delete_persona_file(project.root_path, agent.persona_path)

    assigned_tasks = session.exec(select(Task).where(Task.assignee_agent_id == agent_id)).all()
    for task in assigned_tasks:
        task.assignee_agent_id = None
        task.updated_at = utc_now()
    session.delete(agent)
    _commit_or_conflict(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

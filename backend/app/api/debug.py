from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.errors import ApiException, error_response_docs
from app.db.enums import AgentStatus, TaskStatus
from app.db.models import Agent, Project, Task, utc_now
from app.db.session import get_session

router = APIRouter(prefix="/debug", tags=["debug"])
_DEBUG_PANEL_PATH = Path(__file__).resolve().parents[1] / "static" / "debug_panel.html"
_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
_PLAYGROUND_DIR_NAME = "play_ground"
_PLAYGROUND_FILE_NAME = "README.md"
_PLAYGROUND_FILE_CONTENT = "114514\n"
_PLAYGROUND_AGENT_NAME = "Debug Playground Agent"
_PLAYGROUND_TASK_TITLE_PREFIX = "Debug Playground Task"

DbSession = Annotated[Session, Depends(get_session)]


class AgentPlaygroundSetupRequest(BaseModel):
    project_id: int = Field(default=1, gt=0)


class AgentPlaygroundSetupResponse(BaseModel):
    project_id: int
    project_root_path: str
    workspace_playground_path: str
    project_playground_path: str
    agent_id: int
    task_id: int
    task_title: str
    run_prompt: str


@router.get("/panel", response_class=HTMLResponse)
def debug_panel() -> HTMLResponse:
    html = _DEBUG_PANEL_PATH.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


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


def _build_run_prompt(*, readme_path: Path) -> str:
    return (
        "请读取文件 "
        f"{readme_path} "
        "的内容。"
        "仅返回文件内容本身，不要添加解释、标点或额外文本。"
    )


@router.post(
    "/agent-playground/setup",
    status_code=status.HTTP_201_CREATED,
    response_model=AgentPlaygroundSetupResponse,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ),
    ),
)
def setup_agent_playground(
    payload: AgentPlaygroundSetupRequest,
    session: DbSession,
) -> AgentPlaygroundSetupResponse:
    project = session.get(Project, payload.project_id)
    if project is None:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "PROJECT_NOT_FOUND",
            f"Project {payload.project_id} does not exist.",
        )
    if project.id is None:
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "RESOURCE_CONFLICT",
            "Project row is missing primary key.",
        )
    project_id = project.id

    workspace_playground_dir = _WORKSPACE_ROOT / _PLAYGROUND_DIR_NAME
    workspace_playground_dir.mkdir(parents=True, exist_ok=True)
    workspace_readme_path = workspace_playground_dir / _PLAYGROUND_FILE_NAME
    workspace_readme_path.write_text(_PLAYGROUND_FILE_CONTENT, encoding="utf-8")

    project_root = Path(project.root_path).resolve()
    project_playground_dir = project_root / _PLAYGROUND_DIR_NAME
    project_playground_dir.mkdir(parents=True, exist_ok=True)
    project_readme_path = project_playground_dir / _PLAYGROUND_FILE_NAME
    project_readme_path.write_text(_PLAYGROUND_FILE_CONTENT, encoding="utf-8")

    agent = session.exec(
        select(Agent)
        .where(Agent.project_id == project_id)
        .where(Agent.name == _PLAYGROUND_AGENT_NAME)
    ).first()
    if agent is None:
        agent = Agent(
            project_id=project_id,
            name=_PLAYGROUND_AGENT_NAME,
            role="executor",
            model_provider="claude_code",
            model_name="claude-sonnet-4-5",
            initial_persona_prompt=(
                "You are a local debug agent. Read requested files and return exact content."
            ),
            enabled_tools_json=[
                "list_path_tool",
                "read_file_tool",
                "search_project_files_tool",
            ],
            status=AgentStatus.ACTIVE,
        )
        session.add(agent)
        session.flush()
    else:
        agent.model_provider = "claude_code"
        agent.model_name = "claude-sonnet-4-5"
        agent.status = AgentStatus.ACTIVE
        agent.enabled_tools_json = [
            "list_path_tool",
            "read_file_tool",
            "search_project_files_tool",
        ]
        session.add(agent)
        session.flush()

    if agent.id is None:
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "RESOURCE_CONFLICT",
            "Playground agent was created without primary key.",
        )

    timestamp = utc_now().strftime("%Y%m%d%H%M%S")
    task = Task(
        project_id=project_id,
        title=f"{_PLAYGROUND_TASK_TITLE_PREFIX}-{timestamp}",
        description=(
            "Read the playground README and return exact content.\n"
            f"workspace_path={workspace_readme_path}\n"
            f"project_path={project_readme_path}"
        ),
        status=TaskStatus.TODO,
        priority=2,
        assignee_agent_id=agent.id,
    )
    session.add(task)
    _commit_or_conflict(session)
    session.refresh(task)

    if task.id is None:
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "RESOURCE_CONFLICT",
            "Playground task was created without primary key.",
        )

    return AgentPlaygroundSetupResponse(
        project_id=project_id,
        project_root_path=str(project_root),
        workspace_playground_path=str(workspace_readme_path),
        project_playground_path=str(project_readme_path),
        agent_id=agent.id,
        task_id=task.id,
        task_title=task.title,
        run_prompt=_build_run_prompt(readme_path=project_readme_path),
    )

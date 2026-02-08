from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, select

from app.db.enums import AgentStatus, TaskStatus
from app.db.models import Agent, Event, Project, Task

DEFAULT_PROJECT_NAME = "BeeBeeBrain Playground Project"
DEFAULT_TASK_TITLE = "开发前后端分离的贪吃蛇"
DEFAULT_TASK_DESCRIPTION = (
    "目标：实现前后端分离的贪吃蛇。" "前端负责渲染与交互，后端负责游戏状态、存档与排行榜 API。"
)
SEED_EVENT_TYPE = "system.seeded"
DEFAULT_PLAYGROUND_DIR_NAMES: tuple[str, ...] = ("playground", "play_ground")

DEFAULT_AGENT_DEFINITIONS: tuple[dict[str, str | list[str]], ...] = (
    {
        "name": "Frontend Agent",
        "role": "frontend",
        "model_provider": "claude_code",
        "model_name": "claude-sonnet-4-5",
        "initial_persona_prompt": (
            "You are responsible for frontend implementation of a separated snake game."
        ),
        "enabled_tools_json": ["list_path_tool", "read_file_tool", "search_project_files_tool"],
    },
    {
        "name": "Backend Agent",
        "role": "backend",
        "model_provider": "claude_code",
        "model_name": "claude-sonnet-4-5",
        "initial_persona_prompt": (
            "You are responsible for backend API and state management of a separated snake game."
        ),
        "enabled_tools_json": ["list_path_tool", "read_file_tool", "search_project_files_tool"],
    },
)


def _resolve_default_project_root() -> Path:
    cwd = Path.cwd().resolve()
    candidates: list[Path] = []
    for name in DEFAULT_PLAYGROUND_DIR_NAMES:
        candidates.append(cwd / name)
        candidates.append(cwd.parent / name)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    fallback = cwd / DEFAULT_PLAYGROUND_DIR_NAMES[0]
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback.resolve()


def seed_initial_data(session: Session, *, project_root: Path | None = None) -> None:
    resolved_root = (project_root or _resolve_default_project_root()).resolve()
    resolved_root.mkdir(parents=True, exist_ok=True)
    root_path = str(resolved_root)

    project = session.exec(select(Project).where(Project.root_path == root_path)).first()
    if project is None:
        project = Project(name=DEFAULT_PROJECT_NAME, root_path=root_path)
        session.add(project)
        session.flush()

    agent_ids_by_name: dict[str, int] = {}
    if project.id is not None:
        existing_agents = session.exec(select(Agent).where(Agent.project_id == project.id)).all()
        agent_ids_by_name = {
            agent.name: int(agent.id) for agent in existing_agents if agent.id is not None
        }

        for definition in DEFAULT_AGENT_DEFINITIONS:
            agent_name = str(definition["name"])
            if agent_name in agent_ids_by_name:
                continue
            created_agent = Agent(
                project_id=project.id,
                name=agent_name,
                role=str(definition["role"]),
                model_provider=str(definition["model_provider"]),
                model_name=str(definition["model_name"]),
                initial_persona_prompt=str(definition["initial_persona_prompt"]),
                enabled_tools_json=list(definition["enabled_tools_json"]),
                status=AgentStatus.ACTIVE,
            )
            session.add(created_agent)
            session.flush()
            if created_agent.id is not None:
                agent_ids_by_name[agent_name] = int(created_agent.id)

    task = (
        session.exec(
            select(Task)
            .where(Task.project_id == project.id)
            .where(Task.title == DEFAULT_TASK_TITLE)
        ).first()
        if project.id is not None
        else None
    )
    if task is None and project.id is not None:
        task = Task(
            project_id=project.id,
            title=DEFAULT_TASK_TITLE,
            description=DEFAULT_TASK_DESCRIPTION,
            status=TaskStatus.TODO,
            priority=1,
            assignee_agent_id=agent_ids_by_name.get("Frontend Agent"),
        )
        session.add(task)

    seeded_event_exists = (
        session.exec(
            select(Event)
            .where(Event.project_id == project.id)
            .where(Event.event_type == SEED_EVENT_TYPE)
        ).first()
        if project.id is not None
        else None
    )
    if seeded_event_exists is None and project.id is not None:
        session.add(
            Event(
                project_id=project.id,
                event_type=SEED_EVENT_TYPE,
                payload_json={
                    "seed_version": 2,
                    "project_name": project.name,
                    "project_root": root_path,
                    "agents": [str(definition["name"]) for definition in DEFAULT_AGENT_DEFINITIONS],
                    "task_title": DEFAULT_TASK_TITLE,
                },
                trace_id="seed-init",
            )
        )

    session.commit()

from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, select

from app.core.config import get_settings
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

            # Create persona file
            sanitized_name = agent_name.strip().lower().replace(" ", "_")
            persona_filename = f"{sanitized_name}.md"
            agents_dir = resolved_root / "docs" / "agents"
            agents_dir.mkdir(parents=True, exist_ok=True)
            persona_file = agents_dir / persona_filename

            # Only write if not exists to avoid overwriting user changes
            if not persona_file.exists():
                persona_file.write_text(str(definition["initial_persona_prompt"]), encoding="utf-8")

            persona_rel_path = f"docs/agents/{persona_filename}"

            created_agent = Agent(
                project_id=project.id,
                name=agent_name,
                role=str(definition["role"]),
                model_provider=str(definition["model_provider"]),
                model_name=str(definition["model_name"]),
                persona_path=persona_rel_path,
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


def generate_test_project_data(session: Session | None = None) -> None:
    """生成测试项目数据，用于开发和演示。

    这个函数可以独立运行，用于快速创建测试数据。
    如果提供了 session，则使用提供的 session；否则创建新 session。
    """
    from app.db.engine import get_engine

    if session is None:
        engine = get_engine()
        with Session(engine) as new_session:
            _generate_test_data_impl(new_session)
    else:
        _generate_test_data_impl(session)


def _generate_test_data_impl(session: Session) -> None:
    """实际生成测试数据的实现。"""
    from app.db.enums import InboxItemType, InboxStatus, SourceType
    from app.db.models import InboxItem

    settings = get_settings()
    if settings.project_root is None:
        raise ValueError("PROJECT_ROOT must be set to generate test data")

    project_root = settings.project_root.resolve()
    root_path = str(project_root)

    # 查找或创建项目
    project = session.exec(select(Project).where(Project.root_path == root_path)).first()
    if project is None:
        project = Project(name="Test Project", root_path=root_path)
        session.add(project)
        session.flush()

    if project.id is None:
        raise RuntimeError("Failed to create or retrieve project")

    # 创建测试 Agents
    test_agents = [
        {
            "name": "Test Frontend Agent",
            "role": "frontend",
            "model_provider": "claude_code",
            "model_name": "claude-sonnet-4-5",
            "enabled_tools_json": ["list_path_tool", "read_file_tool"],
        },
        {
            "name": "Test Backend Agent",
            "role": "backend",
            "model_provider": "claude_code",
            "model_name": "claude-sonnet-4-5",
            "enabled_tools_json": ["list_path_tool", "read_file_tool", "search_project_files_tool"],
        },
    ]

    agent_ids: dict[str, int] = {}
    for agent_def in test_agents:
        agent_name = str(agent_def["name"])
        existing_agent = session.exec(
            select(Agent).where(Agent.project_id == project.id, Agent.name == agent_name)
        ).first()

        if existing_agent is None:
            agent = Agent(
                project_id=project.id,
                name=agent_name,
                role=str(agent_def["role"]),
                model_provider=str(agent_def["model_provider"]),
                model_name=str(agent_def["model_name"]),
                enabled_tools_json=list(agent_def["enabled_tools_json"]),
                status=AgentStatus.ACTIVE,
            )
            session.add(agent)
            session.flush()
            if agent.id is not None:
                agent_ids[agent_name] = agent.id
        else:
            if existing_agent.id is not None:
                agent_ids[agent_name] = int(existing_agent.id)

    # 创建测试 Tasks
    test_tasks = [
        {
            "title": "Setup project structure",
            "description": "Initialize the basic project structure and configuration",
            "status": TaskStatus.DONE,
            "priority": 5,
        },
        {
            "title": "Design database schema",
            "description": "Create the initial database schema for the application",
            "status": TaskStatus.RUNNING,
            "priority": 4,
        },
        {
            "title": "Implement API endpoints",
            "description": "Build the REST API endpoints for core functionality",
            "status": TaskStatus.TODO,
            "priority": 3,
        },
        {
            "title": "Create frontend components",
            "description": "Develop the React/Vue components for the UI",
            "status": TaskStatus.TODO,
            "priority": 3,
        },
        {
            "title": "Write tests",
            "description": "Add unit and integration tests for the application",
            "status": TaskStatus.TODO,
            "priority": 2,
        },
    ]

    for task_def in test_tasks:
        task_title = str(task_def["title"])
        existing_task = session.exec(
            select(Task).where(Task.project_id == project.id, Task.title == task_title)
        ).first()

        if existing_task is None:
            task = Task(
                project_id=project.id,
                title=task_def["title"],
                description=task_def["description"],
                status=task_def["status"],
                priority=task_def["priority"],
                assignee_agent_id=(
                    agent_ids.get("Test Frontend Agent")
                    if "frontend" in str(task_def["title"]).lower()
                    else agent_ids.get("Test Backend Agent")
                ),
            )
            session.add(task)

    # 创建测试 Inbox Items
    test_inbox_items = [
        {
            "title": "Review API design",
            "content": "Please review the proposed API design before implementation",
            "item_type": InboxItemType.AWAIT_USER_INPUT,
            "source_type": SourceType.SYSTEM,
            "source_id": "test-agent-1",
        },
        {
            "title": "Task completed notification",
            "content": "The frontend component development task has been completed",
            "item_type": InboxItemType.TASK_COMPLETED,
            "source_type": SourceType.SYSTEM,
            "source_id": "task-notifier",
        },
    ]

    for inbox_def in test_inbox_items:
        source_id = str(inbox_def["source_id"])
        existing_inbox = session.exec(
            select(InboxItem).where(
                InboxItem.project_id == project.id, InboxItem.source_id == source_id
            )
        ).first()

        if existing_inbox is None:
            inbox_item = InboxItem(
                project_id=project.id,
                source_type=inbox_def["source_type"],
                source_id=inbox_def["source_id"],
                item_type=inbox_def["item_type"],
                title=inbox_def["title"],
                content=inbox_def["content"],
                status=InboxStatus.OPEN,
            )
            session.add(inbox_item)

    session.commit()
    print(f"✅ Test data generated successfully for project: {project.name}")
    print(f"   - Agents: {len(test_agents)}")
    print(f"   - Tasks: {len(test_tasks)}")
    print(f"   - Inbox Items: {len(test_inbox_items)}")

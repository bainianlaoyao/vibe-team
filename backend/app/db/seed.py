from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, select

from app.db.models import Agent, Event, Project, Task

DEFAULT_PROJECT_NAME = "BeeBeeBrain Demo Project"
DEFAULT_AGENT_NAME = "Planner Agent"
DEFAULT_TASK_TITLE = "Bootstrap workspace"


def seed_initial_data(session: Session, *, project_root: Path | None = None) -> None:
    resolved_root = (project_root or Path.cwd()).resolve()
    root_path = str(resolved_root)

    project = session.exec(select(Project).where(Project.root_path == root_path)).first()
    if project is None:
        project = Project(name=DEFAULT_PROJECT_NAME, root_path=root_path)
        session.add(project)
        session.flush()

    agent = (
        session.exec(
            select(Agent)
            .where(Agent.project_id == project.id)
            .where(Agent.name == DEFAULT_AGENT_NAME)
        ).first()
        if project.id is not None
        else None
    )
    if agent is None and project.id is not None:
        agent = Agent(
            project_id=project.id,
            name=DEFAULT_AGENT_NAME,
            role="planner",
            model_provider="openai",
            model_name="gpt-4.1-mini",
            initial_persona_prompt="You are the default planning agent for BeeBeeBrain.",
            enabled_tools_json=["list_path_tool", "read_file_tool", "search_project_files_tool"],
            status="active",
        )
        session.add(agent)
        session.flush()

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
            description="Initialize database baseline and verify migrations.",
            status="todo",
            priority=1,
            assignee_agent_id=agent.id if agent is not None else None,
        )
        session.add(task)

    seeded_event_exists = (
        session.exec(
            select(Event)
            .where(Event.project_id == project.id)
            .where(Event.event_type == "system.seeded")
        ).first()
        if project.id is not None
        else None
    )
    if seeded_event_exists is None and project.id is not None:
        session.add(
            Event(
                project_id=project.id,
                event_type="system.seeded",
                payload_json={
                    "seed_version": 1,
                    "project_name": project.name,
                    "project_root": root_path,
                },
                trace_id="seed-init",
            )
        )

    session.commit()

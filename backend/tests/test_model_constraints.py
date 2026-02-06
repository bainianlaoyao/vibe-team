from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.db.bootstrap import initialize_database
from app.db.engine import create_engine_from_url
from app.db.enums import AgentStatus, DocumentType, TaskRunStatus, TaskStatus
from app.db.models import (
    Agent,
    ApiUsageDaily,
    Comment,
    Document,
    Project,
    Task,
    TaskDependency,
    TaskRun,
)


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _create_project_agent_and_tasks(
    session: Session, root: Path
) -> tuple[Project, Agent, Task, Task]:
    project = Project(name="Constraint Project", root_path=str(root / "workspace"))
    session.add(project)
    session.flush()

    agent = Agent(
        project_id=project.id,
        name="Constraint Agent",
        role="planner",
        model_provider="openai",
        model_name="gpt-4.1-mini",
        initial_persona_prompt="Constraint test agent",
        enabled_tools_json=[],
        status=AgentStatus.ACTIVE,
    )
    session.add(agent)
    session.flush()

    task_a = Task(
        project_id=project.id,
        title="Task A",
        status=TaskStatus.TODO,
        priority=2,
        assignee_agent_id=agent.id,
    )
    task_b = Task(
        project_id=project.id,
        title="Task B",
        status=TaskStatus.TODO,
        priority=3,
        assignee_agent_id=agent.id,
    )
    session.add(task_a)
    session.add(task_b)
    session.flush()

    return project, agent, task_a, task_b


def test_task_dependency_rejects_self_reference(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "dependency-self.db")
    initialize_database(database_url=db_url, seed=False)

    engine = create_engine_from_url(db_url)
    try:
        with Session(engine) as session:
            _, _, task_a, _ = _create_project_agent_and_tasks(session, tmp_path)

            session.add(
                TaskDependency(
                    task_id=task_a.id,
                    depends_on_task_id=task_a.id,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


def test_task_dependency_unique_pair(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "dependency-unique.db")
    initialize_database(database_url=db_url, seed=False)

    engine = create_engine_from_url(db_url)
    try:
        with Session(engine) as session:
            _, _, task_a, task_b = _create_project_agent_and_tasks(session, tmp_path)

            dependency = TaskDependency(task_id=task_a.id, depends_on_task_id=task_b.id)
            session.add(dependency)
            session.commit()

            session.add(TaskDependency(task_id=task_a.id, depends_on_task_id=task_b.id))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


def test_document_unique_path_per_project(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "document-unique.db")
    initialize_database(database_url=db_url, seed=False)

    engine = create_engine_from_url(db_url)
    try:
        with Session(engine) as session:
            project, _, _, _ = _create_project_agent_and_tasks(session, tmp_path)

            session.add(
                Document(
                    project_id=project.id,
                    path="docs/spec.md",
                    title="Spec",
                    doc_type=DocumentType.SPEC,
                    is_mandatory=True,
                    tags_json=["mvp"],
                )
            )
            session.commit()

            session.add(
                Document(
                    project_id=project.id,
                    path="docs/spec.md",
                    title="Spec Duplicate",
                    doc_type=DocumentType.SPEC,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


def test_comment_requires_document_or_task_reference(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "comment-target.db")
    initialize_database(database_url=db_url, seed=False)

    engine = create_engine_from_url(db_url)
    try:
        with Session(engine) as session:
            session.add(
                Comment(
                    comment_text="Missing target",
                    author="tester",
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


def test_api_usage_daily_unique_dimension(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "api-usage-unique.db")
    initialize_database(database_url=db_url, seed=False)

    engine = create_engine_from_url(db_url)
    try:
        with Session(engine) as session:
            usage = ApiUsageDaily(
                provider="openai",
                model_name="gpt-4.1-mini",
                date=date(2026, 2, 6),
                request_count=3,
                token_in=120,
                token_out=48,
                cost_usd=Decimal("0.0132"),
            )
            session.add(usage)
            session.commit()

            session.add(
                ApiUsageDaily(
                    provider="openai",
                    model_name="gpt-4.1-mini",
                    date=date(2026, 2, 6),
                    request_count=5,
                    token_in=200,
                    token_out=80,
                    cost_usd=Decimal("0.0200"),
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


def test_task_run_non_negative_constraints(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "task-run-checks.db")
    initialize_database(database_url=db_url, seed=False)

    engine = create_engine_from_url(db_url)
    try:
        with Session(engine) as session:
            _, agent, task_a, _ = _create_project_agent_and_tasks(session, tmp_path)

            session.add(
                TaskRun(
                    task_id=task_a.id,
                    agent_id=agent.id,
                    run_status=TaskRunStatus.RUNNING,
                    attempt=1,
                    token_in=-1,
                    token_out=0,
                    cost_usd=Decimal("0.0000"),
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()

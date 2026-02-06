from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
from sqlmodel import Session, select

from app.db.bootstrap import initialize_database
from app.db.engine import create_engine_from_url
from app.db.enums import (
    AgentStatus,
    DocumentType,
    InboxItemType,
    InboxStatus,
    SourceType,
    TaskRunStatus,
    TaskStatus,
)
from app.db.models import Agent, Document, Event, InboxItem, Project, Task
from app.db.repositories import (
    DocumentFilters,
    DocumentRepository,
    InboxFilters,
    InboxRepository,
    OptimisticLockError,
    Pagination,
    TaskFilters,
    TaskRepository,
    TaskRunFilters,
    TaskRunRepository,
)
from app.orchestration.run_state_machine import InvalidTaskRunTransitionError


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _create_project_and_agent(session: Session, root: Path) -> tuple[Project, Agent]:
    project = Project(name="Repository Project", root_path=str(root / "workspace"))
    session.add(project)
    session.flush()

    agent = Agent(
        project_id=project.id,
        name="Repository Agent",
        role="executor",
        model_provider="openai",
        model_name="gpt-4.1-mini",
        initial_persona_prompt="Repository test agent",
        enabled_tools_json=[],
        status=AgentStatus.ACTIVE,
    )
    session.add(agent)
    session.flush()

    return project, agent


def test_task_repository_pagination_and_filtering(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "task-repository.db")
    initialize_database(database_url=db_url, seed=False)

    engine = create_engine_from_url(db_url)
    try:
        with Session(engine) as session:
            project, agent = _create_project_and_agent(session, tmp_path)
            session.add(
                Task(
                    project_id=project.id,
                    title="Backlog Task",
                    status=TaskStatus.TODO,
                    priority=3,
                    assignee_agent_id=agent.id,
                )
            )
            session.add(
                Task(
                    project_id=project.id,
                    title="Running Task",
                    status=TaskStatus.RUNNING,
                    priority=2,
                    assignee_agent_id=agent.id,
                )
            )
            session.add(
                Task(
                    project_id=project.id,
                    title="Another Backlog Task",
                    status=TaskStatus.TODO,
                    priority=1,
                    assignee_agent_id=agent.id,
                )
            )
            session.commit()

            repository = TaskRepository(session)
            page = repository.list(pagination=Pagination(page=1, page_size=2))
            assert page.total == 3
            assert len(page.items) == 2

            filtered = repository.list(
                pagination=Pagination(page=1, page_size=10),
                filters=TaskFilters(project_id=project.id, status=TaskStatus.TODO),
            )
            assert filtered.total == 2
            assert all(item.status == TaskStatus.TODO for item in filtered.items)

            title_filtered = repository.list(
                pagination=Pagination(page=1, page_size=10),
                filters=TaskFilters(title_query="Running"),
            )
            assert title_filtered.total == 1
            assert title_filtered.items[0].title == "Running Task"
    finally:
        engine.dispose()


def test_task_repository_optimistic_locking(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "task-optimistic-lock.db")
    initialize_database(database_url=db_url, seed=False)

    engine = create_engine_from_url(db_url)
    try:
        with Session(engine) as session:
            project, agent = _create_project_and_agent(session, tmp_path)
            task = Task(
                project_id=project.id,
                title="Optimistic Task",
                status=TaskStatus.TODO,
                priority=3,
                assignee_agent_id=agent.id,
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            assert task.id is not None

            repository = TaskRepository(session)
            updated = repository.update_status(
                task_id=task.id,
                status=TaskStatus.RUNNING,
                expected_version=1,
            )
            assert updated.status == TaskStatus.RUNNING
            assert updated.version == 2

            with pytest.raises(OptimisticLockError):
                repository.update_status(
                    task_id=task.id,
                    status=TaskStatus.DONE,
                    expected_version=1,
                )
    finally:
        engine.dispose()


def test_inbox_repository_filtering_and_optimistic_locking(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "inbox-repository.db")
    initialize_database(database_url=db_url, seed=False)

    engine = create_engine_from_url(db_url)
    try:
        with Session(engine) as session:
            project, _ = _create_project_and_agent(session, tmp_path)
            session.add(
                InboxItem(
                    project_id=project.id,
                    source_type=SourceType.SYSTEM,
                    source_id="system:1",
                    item_type=InboxItemType.AWAIT_USER_INPUT,
                    title="Risk Alert",
                    content="Potential deadlock detected",
                    status=InboxStatus.OPEN,
                )
            )
            session.add(
                InboxItem(
                    project_id=project.id,
                    source_type=SourceType.TASK,
                    source_id="task:2",
                    item_type=InboxItemType.TASK_COMPLETED,
                    title="Blocked Task",
                    content="Task waiting for dependency",
                    status=InboxStatus.OPEN,
                )
            )
            session.commit()

            repository = InboxRepository(session)
            filtered = repository.list(
                pagination=Pagination(page=1, page_size=10),
                filters=InboxFilters(
                    project_id=project.id,
                    item_type=InboxItemType.AWAIT_USER_INPUT,
                ),
            )
            assert filtered.total == 1
            assert filtered.items[0].title == "Risk Alert"

            item = filtered.items[0]
            assert item.id is not None
            updated = repository.update_status(
                item_id=item.id,
                status=InboxStatus.CLOSED,
                expected_version=1,
                resolver="alice",
            )
            assert updated.status == InboxStatus.CLOSED
            assert updated.version == 2
            assert updated.resolved_at is not None
            assert updated.resolver == "alice"

            with pytest.raises(OptimisticLockError):
                repository.update_status(
                    item_id=item.id,
                    status=InboxStatus.OPEN,
                    expected_version=1,
                )
    finally:
        engine.dispose()


def test_document_repository_filtering_and_optimistic_locking(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "document-repository.db")
    initialize_database(database_url=db_url, seed=False)

    engine = create_engine_from_url(db_url)
    try:
        with Session(engine) as session:
            project, _ = _create_project_and_agent(session, tmp_path)
            session.add(
                Document(
                    project_id=project.id,
                    path="docs/spec.md",
                    title="Product Spec",
                    doc_type=DocumentType.SPEC,
                    is_mandatory=True,
                    tags_json=["mvp", "product"],
                )
            )
            session.add(
                Document(
                    project_id=project.id,
                    path="docs/note.md",
                    title="Meeting Note",
                    doc_type=DocumentType.NOTE,
                    is_mandatory=False,
                    tags_json=["meeting"],
                )
            )
            session.commit()

            repository = DocumentRepository(session)
            filtered = repository.list(
                pagination=Pagination(page=1, page_size=10),
                filters=DocumentFilters(project_id=project.id, doc_type=DocumentType.SPEC),
            )
            assert filtered.total == 1
            assert filtered.items[0].title == "Product Spec"

            document = filtered.items[0]
            assert document.id is not None
            updated = repository.update_metadata(
                document_id=document.id,
                expected_version=1,
                title="Product Spec v2",
                tags_json=["mvp", "release"],
            )
            assert updated.title == "Product Spec v2"
            assert updated.tags_json == ["mvp", "release"]
            assert updated.version == 2

            with pytest.raises(OptimisticLockError):
                repository.update_metadata(
                    document_id=document.id,
                    expected_version=1,
                    title="Should Fail",
                )
    finally:
        engine.dispose()


def test_task_run_repository_lifecycle_and_event_contract(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "task-run-repository.db")
    initialize_database(database_url=db_url, seed=False)

    engine = create_engine_from_url(db_url)
    try:
        with Session(engine) as session:
            project, agent = _create_project_and_agent(session, tmp_path)
            task = Task(
                project_id=project.id,
                title="Run Lifecycle Task",
                status=TaskStatus.TODO,
                priority=2,
                assignee_agent_id=agent.id,
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            assert task.id is not None

            repository = TaskRunRepository(session)
            run = repository.create_for_task(
                task_id=task.id,
                agent_id=agent.id,
                idempotency_key=f"task-{task.id}-request-001",
                trace_id="trace-run-create-001",
                actor="scheduler",
            )
            assert run.id is not None
            assert run.attempt == 1
            assert run.run_status == TaskRunStatus.QUEUED
            assert run.version == 1

            duplicate = repository.create_for_task(
                task_id=task.id,
                agent_id=agent.id,
                idempotency_key=f"task-{task.id}-request-001",
            )
            assert duplicate.id == run.id

            running = repository.mark_running(run_id=run.id, expected_version=run.version)
            assert running.id is not None
            assert running.run_status == TaskRunStatus.RUNNING
            assert running.next_retry_at is None
            assert running.version == 2

            retry_at = datetime.now(UTC) + timedelta(minutes=5)
            scheduled = repository.mark_failed(
                run_id=running.id,
                expected_version=running.version,
                error_code="TEMP_UPSTREAM",
                error_message="Injected transient timeout",
                next_retry_at=retry_at,
            )
            assert scheduled.run_status == TaskRunStatus.RETRY_SCHEDULED
            assert scheduled.next_retry_at == retry_at
            assert scheduled.error_code == "TEMP_UPSTREAM"
            assert scheduled.version == 3
            assert scheduled.id is not None

            due_retries = repository.list_due_retries(due_before=retry_at + timedelta(seconds=1))
            assert [item.id for item in due_retries] == [scheduled.id]

            retry_filtered = repository.list(
                pagination=Pagination(page=1, page_size=10),
                filters=TaskRunFilters(task_id=task.id, run_status=TaskRunStatus.RETRY_SCHEDULED),
            )
            assert retry_filtered.total == 1
            assert retry_filtered.items[0].id == scheduled.id

            resumed = repository.mark_running(
                run_id=scheduled.id,
                expected_version=scheduled.version,
            )
            assert resumed.id is not None
            assert resumed.run_status == TaskRunStatus.RUNNING
            assert resumed.next_retry_at is None
            assert resumed.version == 4

            succeeded = repository.mark_succeeded(
                run_id=resumed.id,
                expected_version=resumed.version,
                token_in=321,
                token_out=145,
                cost_usd=Decimal("0.0123"),
            )
            assert succeeded.run_status == TaskRunStatus.SUCCEEDED
            assert succeeded.token_in == 321
            assert succeeded.token_out == 145
            assert succeeded.cost_usd == Decimal("0.0123")
            assert succeeded.version == 5
            assert succeeded.ended_at is not None

            event_id = cast(Any, Event.id)
            run_events = session.exec(
                select(Event)
                .where(Event.project_id == project.id)
                .where(Event.event_type == "run.status.changed")
                .order_by(event_id)
            ).all()
            assert len(run_events) == 5
            retry_event = run_events[2]
            assert retry_event.payload_json["status"] == "retry_scheduled"
            assert retry_event.payload_json["attempt"] == 1
            assert retry_event.payload_json["idempotency_key"] == f"task-{task.id}-request-001"
    finally:
        engine.dispose()


def test_task_run_repository_optimistic_locking_and_transition_guard(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "task-run-repository-guard.db")
    initialize_database(database_url=db_url, seed=False)

    engine = create_engine_from_url(db_url)
    try:
        with Session(engine) as session:
            project, agent = _create_project_and_agent(session, tmp_path)
            task = Task(
                project_id=project.id,
                title="Run Guard Task",
                status=TaskStatus.TODO,
                priority=3,
                assignee_agent_id=agent.id,
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            assert task.id is not None

            repository = TaskRunRepository(session)
            run = repository.create_for_task(
                task_id=task.id,
                agent_id=agent.id,
                idempotency_key=f"task-{task.id}-request-guard",
            )
            assert run.id is not None

            with pytest.raises(OptimisticLockError):
                repository.mark_running(run_id=run.id, expected_version=99)

            with pytest.raises(InvalidTaskRunTransitionError):
                repository.mark_succeeded(run_id=run.id, expected_version=run.version)
    finally:
        engine.dispose()

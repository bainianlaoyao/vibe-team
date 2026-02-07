from __future__ import annotations

from pathlib import Path

from sqlmodel import Session

from app.db.bootstrap import initialize_database
from app.db.engine import create_engine_from_url
from app.db.enums import TaskStatus
from app.db.models import Project, Task, TaskDependency
from app.orchestration.scheduler import list_schedulable_tasks, pick_next_schedulable_task


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def test_scheduler_selects_ready_tasks_by_priority_and_dependencies(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "scheduler-ready-tasks.db")
    initialize_database(database_url=db_url, seed=False)

    engine = create_engine_from_url(db_url)
    try:
        with Session(engine) as session:
            project = Project(name="Scheduler Project", root_path=str(tmp_path / "workspace"))
            session.add(project)
            session.flush()
            assert project.id is not None
            project_id = project.id

            dependency_done = Task(
                project_id=project_id,
                title="Dependency Done",
                status=TaskStatus.DONE,
                priority=5,
            )
            dependency_running = Task(
                project_id=project_id,
                title="Dependency Running",
                status=TaskStatus.RUNNING,
                priority=5,
            )
            session.add(dependency_done)
            session.add(dependency_running)
            session.flush()

            waiting_parent = Task(
                project_id=project_id,
                title="Waiting Parent",
                status=TaskStatus.TODO,
                priority=1,
                parent_task_id=dependency_running.id,
            )
            ready_parent = Task(
                project_id=project_id,
                title="Ready Parent",
                status=TaskStatus.TODO,
                priority=1,
                parent_task_id=dependency_done.id,
            )
            waiting_dependency = Task(
                project_id=project_id,
                title="Waiting Dependency",
                status=TaskStatus.TODO,
                priority=1,
            )
            ready_dependency = Task(
                project_id=project_id,
                title="Ready Dependency",
                status=TaskStatus.TODO,
                priority=1,
            )
            ready_without_dependency = Task(
                project_id=project_id,
                title="Ready No Dependency",
                status=TaskStatus.TODO,
                priority=2,
            )
            session.add(waiting_parent)
            session.add(ready_parent)
            session.add(waiting_dependency)
            session.add(ready_dependency)
            session.add(ready_without_dependency)
            session.flush()

            session.add(
                TaskDependency(
                    task_id=waiting_dependency.id,
                    depends_on_task_id=dependency_running.id,
                )
            )
            session.add(
                TaskDependency(
                    task_id=ready_dependency.id,
                    depends_on_task_id=dependency_done.id,
                )
            )
            session.commit()

            ready_tasks = list_schedulable_tasks(session, project_id=project_id, limit=10)
            assert [task.title for task in ready_tasks] == [
                "Ready Parent",
                "Ready Dependency",
                "Ready No Dependency",
            ]

            next_task = pick_next_schedulable_task(session, project_id=project_id)
            assert next_task is not None
            assert next_task.title == "Ready Parent"
    finally:
        engine.dispose()

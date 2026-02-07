from __future__ import annotations

from collections import defaultdict
from typing import Any, cast

from sqlmodel import Session, select

from app.db.enums import TaskStatus
from app.db.models import Task, TaskDependency


def _build_dependency_map(
    session: Session,
    *,
    candidate_task_ids: list[int],
) -> dict[int, set[int]]:
    dependency_map: dict[int, set[int]] = defaultdict(set)
    if not candidate_task_ids:
        return dependency_map

    dependency_rows = session.exec(
        select(TaskDependency).where(cast(Any, TaskDependency.task_id).in_(candidate_task_ids))
    ).all()
    for dependency in dependency_rows:
        dependency_map[dependency.task_id].add(dependency.depends_on_task_id)
    return dependency_map


def _load_dependency_statuses(
    session: Session, *, dependency_ids: set[int]
) -> dict[int, TaskStatus]:
    if not dependency_ids:
        return {}

    dependency_tasks = session.exec(
        select(Task).where(cast(Any, Task.id).in_(dependency_ids))
    ).all()
    status_by_task_id: dict[int, TaskStatus] = {}
    for task in dependency_tasks:
        if task.id is None:
            continue
        status_by_task_id[task.id] = task.status
    return status_by_task_id


def list_schedulable_tasks(
    session: Session,
    *,
    project_id: int,
    limit: int = 50,
) -> list[Task]:
    if limit <= 0:
        raise ValueError("limit must be greater than 0")

    candidate_tasks = list(
        session.exec(
            select(Task)
            .where(Task.project_id == project_id)
            .where(Task.status == TaskStatus.TODO.value)
            .order_by(
                cast(Any, Task.priority).asc(),
                cast(Any, Task.created_at).asc(),
                cast(Any, Task.id).asc(),
            )
        ).all()
    )
    if not candidate_tasks:
        return []

    candidate_task_ids = [task.id for task in candidate_tasks if task.id is not None]
    dependency_map = _build_dependency_map(session, candidate_task_ids=candidate_task_ids)

    for task in candidate_tasks:
        if task.id is None:
            continue
        if task.parent_task_id is not None:
            dependency_map[task.id].add(task.parent_task_id)

    dependency_ids = {dep_id for dep_ids in dependency_map.values() for dep_id in dep_ids}
    dependency_statuses = _load_dependency_statuses(session, dependency_ids=dependency_ids)

    schedulable: list[Task] = []
    for task in candidate_tasks:
        if task.id is None:
            continue
        dependency_ids_for_task = dependency_map.get(task.id, set())
        if not dependency_ids_for_task:
            schedulable.append(task)
        elif all(
            dependency_statuses.get(dependency_id) == TaskStatus.DONE
            for dependency_id in dependency_ids_for_task
        ):
            schedulable.append(task)

        if len(schedulable) >= limit:
            break

    return schedulable


def pick_next_schedulable_task(session: Session, *, project_id: int) -> Task | None:
    candidates = list_schedulable_tasks(session, project_id=project_id, limit=1)
    if not candidates:
        return None
    return candidates[0]

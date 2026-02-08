from __future__ import annotations

from collections import defaultdict
from typing import Any, cast

from sqlmodel import Session, select

from app.core.logging import get_logger
from app.db.enums import TaskStatus
from app.db.models import Task, TaskDependency

logger = get_logger("bbb.orchestration.scheduler")


def _build_dependency_map(
    session: Session,
    *,
    candidate_task_ids: list[int],
) -> dict[int, set[int]]:
    """
    Build a map of task dependencies for the given candidate tasks.

    Args:
        session: Database session.
        candidate_task_ids: List of task IDs to resolve dependencies for.

    Returns:
        dict[int, set[int]]: A dictionary mapping task ID to a set of required dependency task IDs.
    """
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
    """
    List tasks that are ready to be scheduled (status=TODO and all dependencies are DONE).

    Args:
        session: Database session.
        project_id: The project ID to filter tasks by.
        limit: Maximum number of tasks to return.

    Returns:
        list[Task]: List of schedulable tasks, ordered by priority and creation time.

    Raises:
        ValueError: If limit is less than or equal to 0.
    """
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
        logger.debug("scheduler.no_candidates", project_id=project_id)
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
        else:
            logger.debug(
                "scheduler.skip_unsatisfied_dependencies",
                project_id=project_id,
                task_id=task.id,
                dependency_ids=sorted(dependency_ids_for_task),
            )

        if len(schedulable) >= limit:
            break

    logger.info(
        "scheduler.completed",
        project_id=project_id,
        schedulable_count=len(schedulable),
        candidate_count=len(candidate_tasks),
    )
    return schedulable


def pick_next_schedulable_task(session: Session, *, project_id: int) -> Task | None:
    """
    Pick the next highest priority task that is ready to run.

    Args:
        session: Database session.
        project_id: The project ID.

    Returns:
        Task | None: The next task to run, or None if no tasks are ready.
    """
    candidates = list_schedulable_tasks(session, project_id=project_id, limit=1)
    if not candidates:
        return None
    return candidates[0]

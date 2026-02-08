from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import update
from sqlmodel import Session, select

from app.db.enums import TaskStatus
from app.db.models import Task, utc_now
from app.db.repositories.common import OptimisticLockError, Page, Pagination, paginate


@dataclass(frozen=True, slots=True)
class TaskFilters:
    project_id: int | None = None
    status: TaskStatus | None = None
    assignee_agent_id: int | None = None
    title_query: str | None = None


class TaskRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, task: Task) -> Task:
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def get(self, task_id: int) -> Task | None:
        return self.session.get(Task, task_id)

    def list(
        self,
        *,
        pagination: Pagination | None = None,
        filters: TaskFilters | None = None,
    ) -> Page[Task]:
        active_filters = filters or TaskFilters()
        active_pagination = pagination or Pagination()

        statement = select(Task)
        if active_filters.project_id is not None:
            statement = statement.where(Task.project_id == active_filters.project_id)
        if active_filters.status is not None:
            statement = statement.where(Task.status == active_filters.status.value)
        if active_filters.assignee_agent_id is not None:
            statement = statement.where(Task.assignee_agent_id == active_filters.assignee_agent_id)
        if active_filters.title_query:
            statement = statement.where(
                Task.title.ilike(f"%{active_filters.title_query}%")  # type: ignore[attr-defined]
            )

        statement = statement.order_by(Task.id.desc())  # type: ignore[union-attr]
        return paginate(self.session, statement, pagination=active_pagination)

    def update_status(
        self,
        *,
        task_id: int,
        status: TaskStatus,
        expected_version: int,
    ) -> Task:
        statement = (
            update(Task)
            .where(Task.id == task_id)  # type: ignore[arg-type]
            .where(Task.version == expected_version)  # type: ignore[arg-type]
            .values(
                status=status.value,
                updated_at=utc_now(),
                version=expected_version + 1,
            )
        )
        result = self.session.exec(statement)

        if result.rowcount != 1:
            self.session.rollback()
            raise OptimisticLockError(
                f"task {task_id} version mismatch, expected {expected_version}"
            )

        self.session.commit()
        updated = self.session.get(Task, task_id)
        if updated is None:
            raise OptimisticLockError(f"task {task_id} missing after optimistic update")
        return updated

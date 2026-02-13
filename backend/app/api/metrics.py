from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as date_type
from decimal import Decimal
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session, select

from app.api.errors import error_response_docs
from app.core.logging import get_logger
from app.db.enums import TaskRunStatus
from app.db.models import ApiUsageDaily, Task, TaskRun
from app.db.session import get_session

router = APIRouter(prefix="/metrics", tags=["metrics"])
logger = get_logger("bbb.api.metrics")

DbSession = Annotated[Session, Depends(get_session)]


class UsageDailyMetricRead(BaseModel):
    provider: str
    model_name: str
    date: date_type
    request_count: int
    token_in: int
    token_out: int
    cost_usd: Decimal
    model_config = ConfigDict(from_attributes=True)


class RunsSummaryMetricRead(BaseModel):
    total_runs: int
    queued_runs: int
    running_runs: int
    retry_scheduled_runs: int
    interrupted_runs: int
    succeeded_runs: int
    failed_runs: int
    cancelled_runs: int
    total_token_in: int
    total_token_out: int
    total_cost_usd: Decimal
    avg_duration_seconds: float | None
    max_duration_seconds: float | None


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@router.get(
    "/usage-daily",
    response_model=list[UsageDailyMetricRead],
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_422_UNPROCESSABLE_CONTENT),
    ),
)
def usage_daily_metrics(
    session: DbSession,
    provider: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    model_name: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    date_from: Annotated[date_type | None, Query()] = None,
    date_to: Annotated[date_type | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=365)] = 90,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[UsageDailyMetricRead]:
    statement = select(ApiUsageDaily)
    if provider is not None:
        statement = statement.where(ApiUsageDaily.provider == provider.strip())
    if model_name is not None:
        statement = statement.where(ApiUsageDaily.model_name == model_name.strip())
    if date_from is not None:
        statement = statement.where(ApiUsageDaily.date >= date_from)
    if date_to is not None:
        statement = statement.where(ApiUsageDaily.date <= date_to)
    statement = (
        statement.order_by(
            cast(Any, ApiUsageDaily.date).desc(),
            cast(Any, ApiUsageDaily.provider).asc(),
            cast(Any, ApiUsageDaily.model_name).asc(),
        )
        .offset(offset)
        .limit(limit)
    )

    rows = list(session.exec(statement).all())
    logger.info(
        "metrics.usage_daily.query",
        provider=provider,
        model_name=model_name,
        date_from=date_from.isoformat() if date_from is not None else None,
        date_to=date_to.isoformat() if date_to is not None else None,
        limit=limit,
        offset=offset,
        result_count=len(rows),
    )
    return [UsageDailyMetricRead.model_validate(row) for row in rows]


@router.get(
    "/runs-summary",
    response_model=RunsSummaryMetricRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_422_UNPROCESSABLE_CONTENT),
    ),
)
def runs_summary_metrics(
    session: DbSession,
    project_id: Annotated[int | None, Query(gt=0)] = None,
    started_from: Annotated[datetime | None, Query()] = None,
    started_to: Annotated[datetime | None, Query()] = None,
) -> RunsSummaryMetricRead:
    statement = select(TaskRun)
    if project_id is not None:
        task_id_column = cast(Any, Task.id)
        run_task_id_column = cast(Any, TaskRun.task_id)
        statement = statement.join(Task, task_id_column == run_task_id_column).where(
            Task.project_id == project_id
        )
    if started_from is not None:
        statement = statement.where(TaskRun.started_at >= _normalize_utc_datetime(started_from))
    if started_to is not None:
        statement = statement.where(TaskRun.started_at <= _normalize_utc_datetime(started_to))

    runs = list(session.exec(statement).all())
    counts: dict[TaskRunStatus, int] = {status: 0 for status in TaskRunStatus}
    durations: list[float] = []
    total_cost = Decimal("0.0000")
    total_token_in = 0
    total_token_out = 0

    for run in runs:
        run_status = TaskRunStatus(str(run.run_status))
        counts[run_status] += 1
        total_cost += run.cost_usd
        total_token_in += run.token_in
        total_token_out += run.token_out
        if run.ended_at is not None:
            start = _normalize_utc_datetime(run.started_at)
            end = _normalize_utc_datetime(run.ended_at)
            if end >= start:
                durations.append((end - start).total_seconds())

    avg_duration_seconds = sum(durations) / len(durations) if durations else None
    max_duration_seconds = max(durations) if durations else None

    logger.info(
        "metrics.runs_summary.query",
        project_id=project_id,
        started_from=started_from.isoformat() if started_from is not None else None,
        started_to=started_to.isoformat() if started_to is not None else None,
        total_runs=len(runs),
    )
    return RunsSummaryMetricRead(
        total_runs=len(runs),
        queued_runs=counts[TaskRunStatus.QUEUED],
        running_runs=counts[TaskRunStatus.RUNNING],
        retry_scheduled_runs=counts[TaskRunStatus.RETRY_SCHEDULED],
        interrupted_runs=counts[TaskRunStatus.INTERRUPTED],
        succeeded_runs=counts[TaskRunStatus.SUCCEEDED],
        failed_runs=counts[TaskRunStatus.FAILED],
        cancelled_runs=counts[TaskRunStatus.CANCELLED],
        total_token_in=total_token_in,
        total_token_out=total_token_out,
        total_cost_usd=total_cost.quantize(Decimal("0.0001")),
        avg_duration_seconds=avg_duration_seconds,
        max_duration_seconds=max_duration_seconds,
    )

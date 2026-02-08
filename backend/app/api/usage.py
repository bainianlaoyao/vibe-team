from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from decimal import Decimal
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.errors import error_response_docs
from app.db.models import Agent, ApiUsageDaily, Event, TaskRun
from app.db.session import get_session
from app.events.schemas import RUN_LOG_EVENT_TYPE, RUN_STATUS_CHANGED_EVENT_TYPE

router = APIRouter(prefix="/usage", tags=["usage"])

DbSession = Annotated[Session, Depends(get_session)]


class UsageBudgetRead(BaseModel):
    month: str
    budget_usd: Decimal
    used_usd: Decimal
    remaining_usd: Decimal
    utilization_ratio: float


class UsageTimelineProviderRead(BaseModel):
    request_count: int
    token_in: int
    token_out: int
    cost_usd: Decimal


class UsageTimelinePointRead(BaseModel):
    date: date_type
    total_request_count: int
    total_token_in: int
    total_token_out: int
    total_cost_usd: Decimal
    providers: dict[str, UsageTimelineProviderRead]


class UsageErrorRead(BaseModel):
    timestamp: datetime
    model_id: str | None = None
    error_type: str
    message: str
    task_id: int | None = None
    run_id: int | None = None


def _resolve_model_map(session: Session, run_ids: set[int]) -> dict[int, str]:
    if not run_ids:
        return {}
    statement = (
        select(TaskRun.id, Agent.model_provider, Agent.model_name)
        .join(Agent, cast(Any, TaskRun.agent_id) == cast(Any, Agent.id))
        .where(cast(Any, TaskRun.id).in_(run_ids))
    )
    rows = list(session.exec(statement).all())
    result: dict[int, str] = {}
    for run_id, provider, model_name in rows:
        if run_id is None:
            continue
        result[int(run_id)] = f"{provider}:{model_name}"
    return result


@router.get(
    "/budget",
    response_model=UsageBudgetRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_422_UNPROCESSABLE_ENTITY),
    ),
)
def get_usage_budget(
    session: DbSession,
    budget_usd: Annotated[Decimal, Query(gt=0)] = Decimal("500"),
) -> UsageBudgetRead:
    today = datetime.now(UTC).date()
    month_start = today.replace(day=1)
    next_month = (month_start + timedelta(days=32)).replace(day=1)

    statement = (
        select(ApiUsageDaily)
        .where(ApiUsageDaily.date >= month_start)
        .where(ApiUsageDaily.date < next_month)
    )
    rows = list(session.exec(statement).all())
    used = sum((row.cost_usd for row in rows), Decimal("0.0000"))
    remaining = max(Decimal("0.0000"), budget_usd - used)
    utilization = float((used / budget_usd) if budget_usd > 0 else Decimal("0"))
    return UsageBudgetRead(
        month=month_start.strftime("%Y-%m"),
        budget_usd=budget_usd.quantize(Decimal("0.0001")),
        used_usd=used.quantize(Decimal("0.0001")),
        remaining_usd=remaining.quantize(Decimal("0.0001")),
        utilization_ratio=round(utilization, 6),
    )


@router.get(
    "/timeline",
    response_model=list[UsageTimelinePointRead],
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_422_UNPROCESSABLE_ENTITY),
    ),
)
def get_usage_timeline(
    session: DbSession,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> list[UsageTimelinePointRead]:
    start_date = datetime.now(UTC).date() - timedelta(days=days - 1)
    statement = (
        select(ApiUsageDaily)
        .where(ApiUsageDaily.date >= start_date)
        .order_by(cast(Any, ApiUsageDaily.date).asc())
    )
    rows = list(session.exec(statement).all())
    grouped: dict[date_type, list[ApiUsageDaily]] = defaultdict(list)
    for row in rows:
        grouped[row.date].append(row)

    points: list[UsageTimelinePointRead] = []
    for day in sorted(grouped):
        day_rows = grouped[day]
        providers = {
            f"{item.provider}:{item.model_name}": UsageTimelineProviderRead(
                request_count=item.request_count,
                token_in=item.token_in,
                token_out=item.token_out,
                cost_usd=item.cost_usd.quantize(Decimal("0.0001")),
            )
            for item in day_rows
        }
        points.append(
            UsageTimelinePointRead(
                date=day,
                total_request_count=sum(item.request_count for item in day_rows),
                total_token_in=sum(item.token_in for item in day_rows),
                total_token_out=sum(item.token_out for item in day_rows),
                total_cost_usd=(
                    sum((item.cost_usd for item in day_rows), Decimal("0.0000")).quantize(
                        Decimal("0.0001")
                    )
                ),
                providers=providers,
            )
        )
    return points


@router.get(
    "/errors",
    response_model=list[UsageErrorRead],
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_422_UNPROCESSABLE_ENTITY),
    ),
)
def get_usage_errors(
    session: DbSession,
    project_id: Annotated[int | None, Query(gt=0)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[UsageErrorRead]:
    event_id = cast(Any, Event.id)
    statement = (
        select(Event)
        .where(cast(Any, Event.event_type).in_([RUN_LOG_EVENT_TYPE, RUN_STATUS_CHANGED_EVENT_TYPE]))
        .order_by(event_id.desc())
        .limit(limit * 5)
    )
    if project_id is not None:
        statement = statement.where(Event.project_id == project_id)
    rows = list(session.exec(statement).all())

    candidate_payloads: list[tuple[Event, dict[str, Any]]] = []
    run_ids: set[int] = set()
    for row in rows:
        payload = row.payload_json
        run_id = payload.get("run_id")
        if isinstance(run_id, int):
            run_ids.add(run_id)
        if row.event_type == RUN_LOG_EVENT_TYPE and payload.get("level") == "error":
            candidate_payloads.append((row, payload))
        elif row.event_type == RUN_STATUS_CHANGED_EVENT_TYPE and payload.get("status") == "failed":
            candidate_payloads.append((row, payload))
    model_map = _resolve_model_map(session, run_ids)

    errors: list[UsageErrorRead] = []
    for row, payload in candidate_payloads:
        run_id = payload.get("run_id")
        normalized_run_id = int(run_id) if isinstance(run_id, int) else None
        if row.event_type == RUN_LOG_EVENT_TYPE:
            error_type = "RunLogError"
            message = str(payload.get("message", "Run log error"))
        else:
            error_code = payload.get("error_code")
            error_type = str(error_code) if error_code else "RunFailed"
            message = f"Run #{run_id} failed."
        errors.append(
            UsageErrorRead(
                timestamp=row.created_at,
                model_id=model_map.get(normalized_run_id) if normalized_run_id else None,
                error_type=error_type,
                message=message,
                task_id=payload.get("task_id") if isinstance(payload.get("task_id"), int) else None,
                run_id=normalized_run_id,
            )
        )
        if len(errors) >= limit:
            break
    return errors

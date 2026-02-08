from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha1
from typing import Any, cast

from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.enums import InboxItemType, InboxStatus, SourceType
from app.db.models import ApiUsageDaily, Event, InboxItem, Task, TaskRun
from app.events.schemas import ALERT_RAISED_EVENT_TYPE
from app.llm.contracts import LLMUsage

_COST_SCALE = Decimal("0.0001")
_INBOX_ITEM_CREATED_EVENT_TYPE = "inbox.item.created"
_COST_ALERT_CODE = "COST_THRESHOLD_EXCEEDED"
logger = get_logger("bbb.metrics.cost")


def record_usage_for_run(
    session: Session,
    *,
    run_id: int,
    provider: str,
    model_name: str,
    usage: LLMUsage,
    occurred_at: datetime | None = None,
) -> None:
    if run_id <= 0:
        raise ValueError("run_id must be a positive integer.")
    if usage.request_count < 0:
        raise ValueError("usage.request_count cannot be negative.")
    if usage.token_in < 0:
        raise ValueError("usage.token_in cannot be negative.")
    if usage.token_out < 0:
        raise ValueError("usage.token_out cannot be negative.")
    if usage.cost_usd < 0:
        raise ValueError("usage.cost_usd cannot be negative.")

    run = session.get(TaskRun, run_id)
    if run is None:
        raise ValueError(f"TaskRun {run_id} does not exist.")

    normalized_cost = usage.cost_usd.quantize(_COST_SCALE, rounding=ROUND_HALF_UP)
    run.token_in += usage.token_in
    run.token_out += usage.token_out
    run.cost_usd = _normalize_decimal(run.cost_usd + normalized_cost)

    usage_date = (occurred_at or datetime.now(UTC)).date()
    usage_row = session.exec(
        select(ApiUsageDaily).where(
            ApiUsageDaily.provider == provider,
            ApiUsageDaily.model_name == model_name,
            ApiUsageDaily.date == usage_date,
        )
    ).one_or_none()

    if usage_row is None:
        usage_row = ApiUsageDaily(
            provider=provider,
            model_name=model_name,
            date=usage_date,
            request_count=usage.request_count,
            token_in=usage.token_in,
            token_out=usage.token_out,
            cost_usd=normalized_cost,
        )
        session.add(usage_row)
    else:
        usage_row.request_count += usage.request_count
        usage_row.token_in += usage.token_in
        usage_row.token_out += usage.token_out
        usage_row.cost_usd = _normalize_decimal(usage_row.cost_usd + normalized_cost)

    _maybe_emit_cost_alert(
        session=session,
        run=run,
        usage_row=usage_row,
        provider=provider,
        model_name=model_name,
    )

    session.commit()


def _normalize_decimal(value: Decimal) -> Decimal:
    if value < 0:
        return Decimal("0.0000")
    return value.quantize(_COST_SCALE, rounding=ROUND_HALF_UP)


def _maybe_emit_cost_alert(
    *,
    session: Session,
    run: TaskRun,
    usage_row: ApiUsageDaily,
    provider: str,
    model_name: str,
) -> None:
    threshold = get_settings().cost_alert_threshold_usd
    if threshold <= Decimal("0"):
        return
    if usage_row.cost_usd < threshold:
        return

    task = session.get(Task, run.task_id)
    if task is None:
        return

    source_id = _build_cost_alert_source_id(
        provider=provider,
        model_name=model_name,
        usage_date=usage_row.date.isoformat(),
    )
    existing_inbox_item_id = session.exec(
        select(cast(Any, InboxItem.id))
        .where(InboxItem.project_id == task.project_id)
        .where(InboxItem.source_type == SourceType.SYSTEM.value)
        .where(InboxItem.source_id == source_id)
        .where(InboxItem.status == InboxStatus.OPEN.value)
        .limit(1)
    ).first()
    if existing_inbox_item_id is not None:
        return

    title = _build_alert_title(provider=provider, model_name=model_name)
    message = (
        f"Daily API cost exceeded threshold: cost_usd={usage_row.cost_usd} "
        ">= threshold="
        f"{threshold} (provider={provider}, model={model_name}, date={usage_row.date})."
    )
    trace_id = f"trace-cost-alert-{run.id}-{usage_row.date.isoformat()}"
    session.add(
        Event(
            project_id=task.project_id,
            event_type=ALERT_RAISED_EVENT_TYPE,
            payload_json={
                "code": _COST_ALERT_CODE,
                "severity": "warning",
                "title": title,
                "message": message,
                "task_id": run.task_id,
                "run_id": run.id,
            },
            trace_id=trace_id,
        )
    )

    inbox_item = InboxItem(
        project_id=task.project_id,
        source_type=SourceType.SYSTEM,
        source_id=source_id,
        item_type=InboxItemType.AWAIT_USER_INPUT,
        title=title,
        content=message,
        status=InboxStatus.OPEN,
    )
    session.add(inbox_item)
    session.flush()
    if inbox_item.id is not None:
        session.add(
            Event(
                project_id=task.project_id,
                event_type=_INBOX_ITEM_CREATED_EVENT_TYPE,
                payload_json={
                    "item_id": inbox_item.id,
                    "project_id": task.project_id,
                    "item_type": InboxItemType.AWAIT_USER_INPUT.value,
                    "source_type": SourceType.SYSTEM.value,
                    "source_id": source_id,
                    "title": title,
                    "status": InboxStatus.OPEN.value,
                },
                trace_id=trace_id,
            )
        )
    logger.warning(
        "metrics.cost.alert_raised",
        run_id=run.id,
        task_id=run.task_id,
        provider=provider,
        model_name=model_name,
        usage_date=usage_row.date.isoformat(),
        cost_usd=str(usage_row.cost_usd),
        threshold=str(threshold),
    )


def _build_cost_alert_source_id(*, provider: str, model_name: str, usage_date: str) -> str:
    digest = sha1(f"{usage_date}:{provider}:{model_name}".encode()).hexdigest()[:20]
    return f"cost-alert:{digest}"


def _build_alert_title(*, provider: str, model_name: str) -> str:
    title = f"Cost Alert: {provider}/{model_name}"
    return title[:160]

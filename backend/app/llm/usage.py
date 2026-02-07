from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlmodel import Session, select

from app.db.models import ApiUsageDaily, TaskRun
from app.llm.contracts import LLMUsage

_COST_SCALE = Decimal("0.0001")


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

    session.commit()


def _normalize_decimal(value: Decimal) -> Decimal:
    if value < 0:
        return Decimal("0.0000")
    return value.quantize(_COST_SCALE, rounding=ROUND_HALF_UP)

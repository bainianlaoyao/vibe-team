from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha1
from typing import Any, cast

from sqlmodel import Session, select

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.enums import InboxItemType, InboxStatus, SourceType, TaskRunStatus
from app.db.models import Event, InboxItem, Task, TaskRun
from app.db.session import session_scope
from app.events.schemas import ALERT_RAISED_EVENT_TYPE, RUN_LOG_EVENT_TYPE

_INBOX_ITEM_CREATED_EVENT_TYPE = "inbox.item.created"
_INBOX_ITEM_CLOSED_EVENT_TYPE = "inbox.item.closed"
_AUTOMATED_RESOLVER = "system:stuck-detector"
_ERROR_WINDOW_SIZE = 10
_REPEAT_WINDOW_SIZE = 6
_MIN_ERROR_RATE_SAMPLES = 3
logger = get_logger("bbb.runtime.stuck_detector")


class StuckAlertKind(StrEnum):
    IDLE_TIMEOUT = "idle_timeout"
    REPEATED_ACTIONS = "repeated_actions"
    HIGH_ERROR_RATE = "high_error_rate"


@dataclass(frozen=True, slots=True)
class StuckAlert:
    kind: StuckAlertKind
    project_id: int
    task_id: int | None
    run_id: int | None
    code: str
    title: str
    message: str
    source_id: str
    diagnostics: dict[str, object]


class StuckRunDetector:
    def __init__(
        self,
        *,
        idle_timeout_seconds: int,
        repeat_threshold: float,
        error_rate_threshold: float,
    ) -> None:
        if idle_timeout_seconds <= 0:
            raise ValueError("idle_timeout_seconds must be greater than 0")
        if repeat_threshold < 0 or repeat_threshold > 1:
            raise ValueError("repeat_threshold must be between 0 and 1")
        if error_rate_threshold < 0 or error_rate_threshold > 1:
            raise ValueError("error_rate_threshold must be between 0 and 1")
        self._idle_timeout_seconds = idle_timeout_seconds
        self._repeat_threshold = repeat_threshold
        self._error_rate_threshold = error_rate_threshold

    def run_once(
        self,
        *,
        session: Session,
        now: datetime | None = None,
        trace_id: str | None = None,
    ) -> list[StuckAlert]:
        detector_now = _normalize_utc_datetime(now or datetime.now(UTC))
        run_logs = _load_recent_run_logs(session=session)
        closed_count = self._auto_close_resolved_idle_alerts(
            session=session,
            now=detector_now,
            trace_id=trace_id,
        )
        if closed_count > 0:
            logger.info("stuck_detector.alerts_auto_closed", count=closed_count)

        alerts: list[StuckAlert] = []
        alerts.extend(
            self._detect_idle_timeout_alerts(
                session=session,
                now=detector_now,
                run_logs=run_logs,
            )
        )
        alerts.extend(
            self._detect_repeated_action_alerts(
                session=session,
                run_logs=run_logs,
            )
        )
        alerts.extend(self._detect_high_error_rate_alerts(session=session))

        applied: list[StuckAlert] = []
        for alert in alerts:
            try:
                if self._apply_alert(
                    session=session,
                    alert=alert,
                    trace_id=trace_id,
                ):
                    applied.append(alert)
            except Exception:
                session.rollback()
                logger.exception(
                    "stuck_detector.apply_failed",
                    kind=alert.kind.value,
                    run_id=alert.run_id,
                    task_id=alert.task_id,
                )
        return applied

    def _auto_close_resolved_idle_alerts(
        self,
        *,
        session: Session,
        now: datetime,
        trace_id: str | None,
    ) -> int:
        open_idle_items = list(
            session.exec(
                select(InboxItem)
                .where(InboxItem.source_type == SourceType.SYSTEM.value)
                .where(InboxItem.status == InboxStatus.OPEN.value)
                .where(cast(Any, InboxItem.source_id).like("stuck:idle:%"))
            ).all()
        )

        closed_count = 0
        for item in open_idle_items:
            run_id = _parse_idle_alert_run_id(item.source_id)
            if run_id is None:
                continue
            run = session.get(TaskRun, run_id)
            if run is None:
                self._close_alert_item(
                    session=session,
                    item=item,
                    now=now,
                    trace_id=trace_id,
                    reason="run_not_found",
                )
                closed_count += 1
                continue

            run_status = TaskRunStatus(str(run.run_status))
            if run_status == TaskRunStatus.RUNNING:
                continue
            self._close_alert_item(
                session=session,
                item=item,
                now=now,
                trace_id=trace_id,
                reason=f"run_status={run_status.value}",
            )
            closed_count += 1

        if closed_count > 0:
            session.commit()
        return closed_count

    def _close_alert_item(
        self,
        *,
        session: Session,
        item: InboxItem,
        now: datetime,
        trace_id: str | None,
        reason: str,
    ) -> None:
        previous_status = InboxStatus.OPEN.value
        item.status = InboxStatus.CLOSED
        item.resolved_at = now
        item.resolver = _AUTOMATED_RESOLVER
        item.version += 1
        session.add(
            Event(
                project_id=item.project_id,
                event_type=_INBOX_ITEM_CLOSED_EVENT_TYPE,
                payload_json={
                    "item_id": item.id,
                    "project_id": item.project_id,
                    "source_type": SourceType.SYSTEM.value,
                    "source_id": item.source_id,
                    "item_type": InboxItemType.AWAIT_USER_INPUT.value,
                    "previous_status": previous_status,
                    "status": InboxStatus.CLOSED.value,
                    "resolver": _AUTOMATED_RESOLVER,
                    "version": item.version,
                    "auto_closed": True,
                    "reason": reason,
                },
                trace_id=trace_id,
            )
        )

    def _detect_idle_timeout_alerts(
        self,
        *,
        session: Session,
        now: datetime,
        run_logs: dict[int, list[Event]],
    ) -> list[StuckAlert]:
        running_runs = list(
            session.exec(
                select(TaskRun).where(TaskRun.run_status == TaskRunStatus.RUNNING.value)
            ).all()
        )
        threshold_delta = timedelta(seconds=self._idle_timeout_seconds)
        project_cache: dict[int, int] = {}
        alerts: list[StuckAlert] = []

        for run in running_runs:
            if run.id is None:
                continue
            reference_time = _normalize_utc_datetime(run.started_at)
            logs_for_run = run_logs.get(run.id)
            if logs_for_run:
                latest_log_time = _normalize_utc_datetime(logs_for_run[0].created_at)
                if latest_log_time > reference_time:
                    reference_time = latest_log_time
            if now - reference_time < threshold_delta:
                continue

            project_id = _resolve_project_id_for_task(
                session=session,
                task_id=run.task_id,
                cache=project_cache,
            )
            if project_id is None:
                continue
            alerts.append(
                StuckAlert(
                    kind=StuckAlertKind.IDLE_TIMEOUT,
                    project_id=project_id,
                    task_id=run.task_id,
                    run_id=run.id,
                    code="RUN_IDLE_TIMEOUT",
                    title="Run idle timeout detected",
                    message=(
                        f"Run {run.id} has no output for at least "
                        f"{self._idle_timeout_seconds} seconds."
                    ),
                    source_id=f"stuck:idle:{run.id}",
                    diagnostics={
                        "idle_timeout_seconds": self._idle_timeout_seconds,
                        "reference_time": reference_time.isoformat(),
                        "detected_at": now.isoformat(),
                    },
                )
            )
        return alerts

    def _detect_repeated_action_alerts(
        self,
        *,
        session: Session,
        run_logs: dict[int, list[Event]],
    ) -> list[StuckAlert]:
        alerts: list[StuckAlert] = []
        project_cache: dict[int, int] = {}

        for run_id, events in run_logs.items():
            if len(events) < _REPEAT_WINDOW_SIZE:
                continue

            samples = events[:_REPEAT_WINDOW_SIZE]
            messages = [_extract_run_log_message(event) for event in samples]
            if any(message is None for message in messages):
                continue
            message_values = [message for message in messages if message is not None]
            if len(message_values) < _REPEAT_WINDOW_SIZE:
                continue

            unique_hashes = {sha1(message.encode()).hexdigest() for message in message_values}
            repeat_ratio = 1 - (len(unique_hashes) / len(message_values))
            if repeat_ratio < self._repeat_threshold:
                continue

            run = session.get(TaskRun, run_id)
            if run is None or TaskRunStatus(str(run.run_status)) != TaskRunStatus.RUNNING:
                continue
            if run.id is None:
                continue

            project_id = _resolve_project_id_for_task(
                session=session,
                task_id=run.task_id,
                cache=project_cache,
            )
            if project_id is None:
                continue
            alerts.append(
                StuckAlert(
                    kind=StuckAlertKind.REPEATED_ACTIONS,
                    project_id=project_id,
                    task_id=run.task_id,
                    run_id=run.id,
                    code="RUN_REPEATED_ACTION",
                    title="Run repeated actions detected",
                    message=(
                        f"Run {run.id} repeated similar logs with ratio "
                        f"{repeat_ratio:.2f} in last {_REPEAT_WINDOW_SIZE} entries."
                    ),
                    source_id=f"stuck:repeat:{run.id}",
                    diagnostics={
                        "repeat_ratio": round(repeat_ratio, 4),
                        "threshold": self._repeat_threshold,
                        "sample_size": _REPEAT_WINDOW_SIZE,
                    },
                )
            )
        return alerts

    def _detect_high_error_rate_alerts(self, *, session: Session) -> list[StuckAlert]:
        runs = list(
            session.exec(
                select(TaskRun).order_by(TaskRun.started_at.desc(), TaskRun.id.desc())  # type: ignore[attr-defined,union-attr]
            ).all()
        )
        runs_by_task: dict[int, list[TaskRun]] = defaultdict(list)
        for run in runs:
            bucket = runs_by_task[run.task_id]
            if len(bucket) >= _ERROR_WINDOW_SIZE:
                continue
            status = TaskRunStatus(str(run.run_status))
            if status in {TaskRunStatus.SUCCEEDED, TaskRunStatus.FAILED, TaskRunStatus.CANCELLED}:
                bucket.append(run)

        project_cache: dict[int, int] = {}
        alerts: list[StuckAlert] = []
        for task_id, history in runs_by_task.items():
            if len(history) < _MIN_ERROR_RATE_SAMPLES:
                continue
            failed_count = sum(
                1 for run in history if TaskRunStatus(str(run.run_status)) == TaskRunStatus.FAILED
            )
            error_rate = failed_count / len(history)
            if error_rate < self._error_rate_threshold:
                continue
            latest_run = history[0]
            if latest_run.id is None:
                continue

            project_id = _resolve_project_id_for_task(
                session=session,
                task_id=task_id,
                cache=project_cache,
            )
            if project_id is None:
                continue
            alerts.append(
                StuckAlert(
                    kind=StuckAlertKind.HIGH_ERROR_RATE,
                    project_id=project_id,
                    task_id=task_id,
                    run_id=latest_run.id,
                    code="RUN_HIGH_ERROR_RATE",
                    title="Run error rate exceeded threshold",
                    message=(
                        f"Task {task_id} failed {failed_count}/{len(history)} recent runs "
                        f"(rate={error_rate:.2f})."
                    ),
                    source_id=f"stuck:error-rate:{latest_run.id}",
                    diagnostics={
                        "error_rate": round(error_rate, 4),
                        "threshold": self._error_rate_threshold,
                        "window_size": len(history),
                        "failed_count": failed_count,
                    },
                )
            )
        return alerts

    def _apply_alert(
        self,
        *,
        session: Session,
        alert: StuckAlert,
        trace_id: str | None,
    ) -> bool:
        existing_item = session.exec(
            select(InboxItem.id)
            .where(InboxItem.project_id == alert.project_id)
            .where(InboxItem.source_type == SourceType.SYSTEM.value)
            .where(InboxItem.source_id == alert.source_id)
            .where(InboxItem.status == InboxStatus.OPEN.value)
            .limit(1)
        ).first()
        if existing_item is not None:
            return False

        session.add(
            Event(
                project_id=alert.project_id,
                event_type=ALERT_RAISED_EVENT_TYPE,
                payload_json={
                    "code": alert.code,
                    "severity": "warning",
                    "title": alert.title,
                    "message": alert.message,
                    "task_id": alert.task_id,
                    "run_id": alert.run_id,
                },
                trace_id=trace_id,
            )
        )

        inbox_item = InboxItem(
            project_id=alert.project_id,
            source_type=SourceType.SYSTEM,
            source_id=alert.source_id,
            item_type=InboxItemType.AWAIT_USER_INPUT,
            title=alert.title[:160],
            content=_build_inbox_content(alert),
            status=InboxStatus.OPEN,
        )
        session.add(inbox_item)
        session.flush()

        if inbox_item.id is not None:
            session.add(
                Event(
                    project_id=alert.project_id,
                    event_type=_INBOX_ITEM_CREATED_EVENT_TYPE,
                    payload_json={
                        "item_id": inbox_item.id,
                        "project_id": alert.project_id,
                        "item_type": InboxItemType.AWAIT_USER_INPUT.value,
                        "source_type": SourceType.SYSTEM.value,
                        "source_id": alert.source_id,
                        "title": alert.title[:160],
                        "status": InboxStatus.OPEN.value,
                    },
                    trace_id=trace_id,
                )
            )

        session.commit()
        logger.warning(
            "stuck_detector.alert_raised",
            kind=alert.kind.value,
            project_id=alert.project_id,
            task_id=alert.task_id,
            run_id=alert.run_id,
            code=alert.code,
        )
        return True


def build_stuck_run_detector(settings: Settings | None = None) -> StuckRunDetector:
    active_settings = settings or get_settings()
    return StuckRunDetector(
        idle_timeout_seconds=active_settings.stuck_idle_timeout_s,
        repeat_threshold=active_settings.stuck_repeat_threshold,
        error_rate_threshold=active_settings.stuck_error_rate_threshold,
    )


async def run_stuck_detector_loop(
    *,
    detector: StuckRunDetector,
    interval_seconds: int,
) -> None:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be greater than 0")
    while True:
        try:
            with session_scope() as session:
                detector.run_once(
                    session=session,
                    trace_id=f"trace-stuck-detector-{datetime.now(UTC).timestamp()}",
                )
        except Exception:
            logger.exception("stuck_detector.loop_failed")
        await asyncio.sleep(interval_seconds)


def _load_recent_run_logs(*, session: Session, limit: int = 2000) -> dict[int, list[Event]]:
    event_id = cast(Any, Event.id)
    events = list(
        session.exec(
            select(Event)
            .where(Event.event_type == RUN_LOG_EVENT_TYPE)
            .order_by(event_id.desc())
            .limit(limit)
        ).all()
    )
    result: dict[int, list[Event]] = defaultdict(list)
    for event in events:
        run_id = _extract_run_id(event)
        if run_id is None:
            continue
        result[run_id].append(event)
    return result


def _extract_run_id(event: Event) -> int | None:
    raw_run_id = event.payload_json.get("run_id")
    if isinstance(raw_run_id, int) and raw_run_id > 0:
        return raw_run_id
    if isinstance(raw_run_id, str) and raw_run_id.isdigit():
        parsed = int(raw_run_id)
        return parsed if parsed > 0 else None
    return None


def _extract_run_log_message(event: Event) -> str | None:
    message = event.payload_json.get("message")
    if not isinstance(message, str):
        return None
    normalized = message.strip()
    return normalized if normalized else None


def _resolve_project_id_for_task(
    *,
    session: Session,
    task_id: int,
    cache: dict[int, int],
) -> int | None:
    cached = cache.get(task_id)
    if cached is not None:
        return cached
    task = session.get(Task, task_id)
    if task is None:
        return None
    cache[task_id] = task.project_id
    return task.project_id


def _build_inbox_content(alert: StuckAlert) -> str:
    details = ", ".join(f"{key}={value}" for key, value in sorted(alert.diagnostics.items()))
    return f"{alert.message}\n\nDiagnostics: {details}"


def _parse_idle_alert_run_id(source_id: str) -> int | None:
    prefix = "stuck:idle:"
    if not source_id.startswith(prefix):
        return None
    raw_value = source_id.removeprefix(prefix)
    if not raw_value.isdigit():
        return None
    parsed = int(raw_value)
    return parsed if parsed > 0 else None


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

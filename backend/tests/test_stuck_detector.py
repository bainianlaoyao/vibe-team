from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlmodel import Session, SQLModel, select

from app.db.engine import create_engine_from_url
from app.db.enums import InboxStatus, TaskRunStatus, TaskStatus
from app.db.models import Event, InboxItem, Project, Task, TaskRun
from app.runtime.stuck_detector import StuckAlertKind, StuckRunDetector


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _create_task_with_project(session: Session, *, root: Path) -> Task:
    project = Project(name="Stuck Detector Project", root_path=str((root / "workspace").resolve()))
    session.add(project)
    session.flush()

    task = Task(
        project_id=project.id,
        title="Stuck Detector Task",
        status=TaskStatus.RUNNING,
        priority=2,
    )
    session.add(task)
    session.flush()
    return task


def test_idle_timeout_detection_creates_single_alert(tmp_path: Path) -> None:
    engine = create_engine_from_url(_to_sqlite_url(tmp_path / "stuck-idle.db"))
    SQLModel.metadata.create_all(engine)
    now = datetime(2026, 2, 7, 12, 0, 0, tzinfo=UTC)

    with Session(engine) as session:
        task = _create_task_with_project(session, root=tmp_path)
        run = TaskRun(
            task_id=task.id,
            run_status=TaskRunStatus.RUNNING,
            attempt=1,
            started_at=now - timedelta(minutes=10),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        assert run.id is not None

        detector = StuckRunDetector(
            idle_timeout_seconds=60,
            repeat_threshold=0.9,
            error_rate_threshold=0.9,
        )
        alerts = detector.run_once(session=session, now=now, trace_id="trace-stuck-idle")
        assert [alert.kind for alert in alerts] == [StuckAlertKind.IDLE_TIMEOUT]

        duplicate = detector.run_once(
            session=session,
            now=now + timedelta(minutes=1),
            trace_id="trace-stuck-idle-repeat",
        )
        assert duplicate == []

        inbox_items = session.exec(
            select(InboxItem).where(InboxItem.status == InboxStatus.OPEN.value)
        ).all()
        assert len(inbox_items) == 1
        assert inbox_items[0].source_id == f"stuck:idle:{run.id}"
        alert_events = session.exec(select(Event).where(Event.event_type == "alert.raised")).all()
        assert len(alert_events) == 1
        assert alert_events[0].payload_json["code"] == "RUN_IDLE_TIMEOUT"

    engine.dispose()


def test_repeated_action_detection(tmp_path: Path) -> None:
    engine = create_engine_from_url(_to_sqlite_url(tmp_path / "stuck-repeat.db"))
    SQLModel.metadata.create_all(engine)
    now = datetime(2026, 2, 7, 12, 0, 0, tzinfo=UTC)

    with Session(engine) as session:
        task = _create_task_with_project(session, root=tmp_path)
        run = TaskRun(
            task_id=task.id,
            run_status=TaskRunStatus.RUNNING,
            attempt=1,
            started_at=now - timedelta(seconds=30),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        assert run.id is not None

        for sequence in range(1, 7):
            session.add(
                Event(
                    project_id=task.project_id,
                    event_type="run.log",
                    payload_json={
                        "run_id": run.id,
                        "task_id": task.id,
                        "level": "info",
                        "message": "looping on same action",
                        "sequence": sequence,
                    },
                    trace_id="trace-repeat-seed",
                    created_at=now - timedelta(seconds=sequence),
                )
            )
        session.commit()

        detector = StuckRunDetector(
            idle_timeout_seconds=600,
            repeat_threshold=0.7,
            error_rate_threshold=0.9,
        )
        alerts = detector.run_once(session=session, now=now, trace_id="trace-stuck-repeat")
        assert [alert.kind for alert in alerts] == [StuckAlertKind.REPEATED_ACTIONS]

        alert_events = session.exec(select(Event).where(Event.event_type == "alert.raised")).all()
        assert len(alert_events) == 1
        assert alert_events[0].payload_json["code"] == "RUN_REPEATED_ACTION"

    engine.dispose()


def test_high_error_rate_detection(tmp_path: Path) -> None:
    engine = create_engine_from_url(_to_sqlite_url(tmp_path / "stuck-error-rate.db"))
    SQLModel.metadata.create_all(engine)
    now = datetime(2026, 2, 7, 12, 0, 0, tzinfo=UTC)

    with Session(engine) as session:
        task = _create_task_with_project(session, root=tmp_path)
        for index, status in enumerate(
            [
                TaskRunStatus.FAILED,
                TaskRunStatus.FAILED,
                TaskRunStatus.SUCCEEDED,
                TaskRunStatus.FAILED,
            ],
            start=1,
        ):
            session.add(
                TaskRun(
                    task_id=task.id,
                    run_status=status,
                    attempt=index,
                    started_at=now - timedelta(minutes=index),
                    ended_at=now - timedelta(minutes=index) + timedelta(seconds=10),
                )
            )
        session.commit()

        detector = StuckRunDetector(
            idle_timeout_seconds=600,
            repeat_threshold=0.9,
            error_rate_threshold=0.7,
        )
        alerts = detector.run_once(session=session, now=now, trace_id="trace-stuck-error-rate")
        assert [alert.kind for alert in alerts] == [StuckAlertKind.HIGH_ERROR_RATE]

        alert_events = session.exec(select(Event).where(Event.event_type == "alert.raised")).all()
        assert len(alert_events) == 1
        assert alert_events[0].payload_json["code"] == "RUN_HIGH_ERROR_RATE"

        strict_detector = StuckRunDetector(
            idle_timeout_seconds=600,
            repeat_threshold=0.9,
            error_rate_threshold=0.95,
        )
        strict_alerts = strict_detector.run_once(
            session=session,
            now=now + timedelta(minutes=1),
            trace_id="trace-stuck-error-rate-strict",
        )
        assert strict_alerts == []

    engine.dispose()

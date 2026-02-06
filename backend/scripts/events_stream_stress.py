from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

EVENTS_API_PATH = "/api/v1/events"
EVENTS_STREAM_API_PATH = "/api/v1/events/stream"


@dataclass(slots=True)
class ConsumeResult:
    received: int
    reconnects: int
    last_event_id: int
    duration_seconds: float


def _build_event_payload(*, index: int, project_id: int, trace_prefix: str) -> dict[str, Any]:
    event_type_index = index % 3
    trace_id = f"{trace_prefix}-{index}"

    if event_type_index == 0:
        statuses = ["todo", "running", "review", "done"]
        previous_status = statuses[index % len(statuses)]
        current_status = statuses[(index + 1) % len(statuses)]
        return {
            "project_id": project_id,
            "event_type": "task.status.changed",
            "payload": {
                "task_id": (index % 500) + 1,
                "previous_status": previous_status,
                "status": current_status,
                "run_id": (index % 200) + 1,
                "actor": "stress-generator",
            },
            "trace_id": trace_id,
        }

    if event_type_index == 1:
        return {
            "project_id": project_id,
            "event_type": "run.log",
            "payload": {
                "run_id": (index % 200) + 1,
                "task_id": (index % 500) + 1,
                "level": "info",
                "message": f"stress-log-{index}",
                "sequence": index + 1,
            },
            "trace_id": trace_id,
        }

    severities = ["info", "warning", "error", "critical"]
    return {
        "project_id": project_id,
        "event_type": "alert.raised",
        "payload": {
            "code": "STRESS_ALERT",
            "severity": severities[index % len(severities)],
            "title": "Stress signal",
            "message": f"stress-alert-{index}",
            "task_id": (index % 500) + 1,
            "run_id": (index % 200) + 1,
        },
        "trace_id": trace_id,
    }


async def _post_event(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    payload: dict[str, Any],
) -> int:
    response = await client.post(f"{base_url}{EVENTS_API_PATH}", json=payload)
    response.raise_for_status()
    body = response.json()
    return int(body["id"])


async def _create_marker_event(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    project_id: int,
    trace_prefix: str,
) -> int:
    payload: dict[str, Any] = {
        "project_id": project_id,
        "event_type": "run.log",
        "payload": {
            "run_id": 1,
            "task_id": 1,
            "level": "info",
            "message": "stress-marker",
            "sequence": 1,
        },
        "trace_id": f"{trace_prefix}-marker",
    }
    return await _post_event(client, base_url=base_url, payload=payload)


async def _produce_events(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    project_id: int,
    total_events: int,
    producer_concurrency: int,
    trace_prefix: str,
) -> float:
    start = time.perf_counter()
    for start_index in range(0, total_events, producer_concurrency):
        end_index = min(start_index + producer_concurrency, total_events)
        await asyncio.gather(
            *[
                _post_event(
                    client,
                    base_url=base_url,
                    payload=_build_event_payload(
                        index=event_index,
                        project_id=project_id,
                        trace_prefix=trace_prefix,
                    ),
                )
                for event_index in range(start_index, end_index)
            ]
        )
    return time.perf_counter() - start


async def _consume_events(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    project_id: int,
    start_after_id: int,
    total_events: int,
    reconnect_every: int,
) -> ConsumeResult:
    received = 0
    reconnects = 0
    last_event_id = start_after_id
    started_at = time.perf_counter()

    while received < total_events:
        headers = {"Last-Event-ID": str(last_event_id)}
        params = {
            "project_id": project_id,
            "batch_size": 200,
            "poll_interval_ms": 100,
        }

        async with client.stream(
            "GET",
            f"{base_url}{EVENTS_STREAM_API_PATH}",
            params=params,
            headers=headers,
            timeout=None,
        ) as response:
            response.raise_for_status()
            current_event_id: int | None = None

            async for raw_line in response.aiter_lines():
                line = raw_line.strip()
                if line.startswith(":"):
                    continue
                if line.startswith("id:"):
                    id_text = line.split(":", maxsplit=1)[1].strip()
                    if id_text.isdigit():
                        current_event_id = int(id_text)
                    continue
                if line != "":
                    continue

                if current_event_id is None:
                    continue
                if current_event_id <= last_event_id:
                    current_event_id = None
                    continue

                last_event_id = current_event_id
                current_event_id = None
                received += 1
                if received >= total_events:
                    break

                should_reconnect = reconnect_every > 0 and received % reconnect_every == 0
                if should_reconnect:
                    reconnects += 1
                    break

    return ConsumeResult(
        received=received,
        reconnects=reconnects,
        last_event_id=last_event_id,
        duration_seconds=time.perf_counter() - started_at,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SSE events stream stress tool for BeeBeeBrain backend."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL.")
    parser.add_argument("--project-id", required=True, type=int, help="Project ID used for events.")
    parser.add_argument(
        "--total-events",
        default=2000,
        type=int,
        help="Total number of events to publish and consume.",
    )
    parser.add_argument(
        "--producer-concurrency",
        default=50,
        type=int,
        help="Concurrent POST requests when publishing events.",
    )
    parser.add_argument(
        "--reconnect-every",
        default=500,
        type=int,
        help="Reconnect stream after every N consumed events. Set 0 to disable.",
    )
    parser.add_argument(
        "--consumer-warmup-ms",
        default=200,
        type=int,
        help="Warmup delay before producer starts, in milliseconds.",
    )
    parser.add_argument(
        "--timeout-seconds",
        default=120,
        type=float,
        help="Overall timeout waiting for stream consumption.",
    )
    parser.add_argument(
        "--trace-prefix",
        default="events-stress",
        help="Trace ID prefix for generated events.",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    if args.project_id <= 0:
        raise ValueError("--project-id must be a positive integer.")
    if args.total_events <= 0:
        raise ValueError("--total-events must be greater than 0.")
    if args.producer_concurrency <= 0:
        raise ValueError("--producer-concurrency must be greater than 0.")
    if args.reconnect_every < 0:
        raise ValueError("--reconnect-every cannot be negative.")
    if args.consumer_warmup_ms < 0:
        raise ValueError("--consumer-warmup-ms cannot be negative.")
    if args.timeout_seconds <= 0:
        raise ValueError("--timeout-seconds must be greater than 0.")

    base_url = str(args.base_url).rstrip("/")

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=30.0, write=10.0)) as client:
        marker_event_id = await _create_marker_event(
            client,
            base_url=base_url,
            project_id=args.project_id,
            trace_prefix=args.trace_prefix,
        )

        consume_task = asyncio.create_task(
            _consume_events(
                client,
                base_url=base_url,
                project_id=args.project_id,
                start_after_id=marker_event_id,
                total_events=args.total_events,
                reconnect_every=args.reconnect_every,
            )
        )

        await asyncio.sleep(args.consumer_warmup_ms / 1000)
        produce_seconds = await _produce_events(
            client,
            base_url=base_url,
            project_id=args.project_id,
            total_events=args.total_events,
            producer_concurrency=args.producer_concurrency,
            trace_prefix=args.trace_prefix,
        )

        consume_result = await asyncio.wait_for(consume_task, timeout=args.timeout_seconds)

    produced_rate = args.total_events / produce_seconds
    consumed_rate = consume_result.received / consume_result.duration_seconds
    print(
        "marker_event_id="
        f"{marker_event_id} produced={args.total_events} "
        f"produce_seconds={produce_seconds:.3f} produced_per_second={produced_rate:.1f}"
    )
    print(
        "consumed="
        f"{consume_result.received} consume_seconds={consume_result.duration_seconds:.3f} "
        f"consumed_per_second={consumed_rate:.1f} reconnects={consume_result.reconnects} "
        f"last_event_id={consume_result.last_event_id}"
    )
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args))
    except Exception as exc:  # noqa: BLE001
        print(f"[events_stream_stress] failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

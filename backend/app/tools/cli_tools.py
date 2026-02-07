from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class CliToolExecutionError(RuntimeError):
    """Raised when CLI domain tool invocation fails."""


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    tool: str
    task_id: int
    task_status: str
    task_version: int
    idempotency_key: str
    idempotency_hit: bool
    inbox_item_id: int | None


class CliDomainTools:
    def __init__(
        self,
        *,
        base_url: str,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._timeout_seconds = timeout_seconds

    async def finish_task(
        self,
        *,
        task_id: int,
        idempotency_key: str,
        trace_id: str | None = None,
        actor: str = "cli_tool",
    ) -> ToolExecutionResult:
        return await self._invoke(
            endpoint="/api/v1/tools/finish_task",
            payload={
                "task_id": task_id,
                "idempotency_key": idempotency_key,
                "trace_id": trace_id,
                "actor": actor,
            },
        )

    async def block_task(
        self,
        *,
        task_id: int,
        reason: str | None,
        idempotency_key: str,
        trace_id: str | None = None,
        actor: str = "cli_tool",
    ) -> ToolExecutionResult:
        return await self._invoke(
            endpoint="/api/v1/tools/block_task",
            payload={
                "task_id": task_id,
                "reason": reason,
                "idempotency_key": idempotency_key,
                "trace_id": trace_id,
                "actor": actor,
            },
        )

    async def request_input(
        self,
        *,
        task_id: int,
        title: str,
        content: str,
        idempotency_key: str,
        trace_id: str | None = None,
        actor: str = "cli_tool",
    ) -> ToolExecutionResult:
        return await self._invoke(
            endpoint="/api/v1/tools/request_input",
            payload={
                "task_id": task_id,
                "title": title,
                "content": content,
                "idempotency_key": idempotency_key,
                "trace_id": trace_id,
                "actor": actor,
            },
        )

    async def _invoke(self, *, endpoint: str, payload: dict[str, Any]) -> ToolExecutionResult:
        if self._client is not None:
            response = await self._client.post(
                endpoint,
                json=payload,
                timeout=self._timeout_seconds,
            )
        else:
            async with httpx.AsyncClient(base_url=self._base_url) as client:
                response = await client.post(endpoint, json=payload, timeout=self._timeout_seconds)

        if response.status_code >= 400:
            try:
                payload_json = response.json()
                error_message = payload_json["error"]["message"]
            except Exception:  # pragma: no cover - defensive branch
                error_message = response.text
            raise CliToolExecutionError(
                f"Tool endpoint {endpoint} failed with status "
                f"{response.status_code}: {error_message}"
            )

        result_payload = response.json()
        return ToolExecutionResult(
            tool=str(result_payload["tool"]),
            task_id=int(result_payload["task_id"]),
            task_status=str(result_payload["task_status"]),
            task_version=int(result_payload["task_version"]),
            idempotency_key=str(result_payload["idempotency_key"]),
            idempotency_hit=bool(result_payload["idempotency_hit"]),
            inbox_item_id=(
                int(result_payload["inbox_item_id"])
                if result_payload.get("inbox_item_id") is not None
                else None
            ),
        )

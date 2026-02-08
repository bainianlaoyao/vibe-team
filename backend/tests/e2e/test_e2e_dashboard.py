from __future__ import annotations

from .conftest import E2EContext


def test_dashboard_endpoints_return_live_data(e2e_context: E2EContext) -> None:
    stats_response = e2e_context.client.get(
        "/api/v1/tasks/stats",
        params={"project_id": e2e_context.project_id},
    )
    assert stats_response.status_code == 200
    payload = stats_response.json()
    assert payload["total"] >= 0
    assert "running" in payload

    updates_response = e2e_context.client.get(
        "/api/v1/updates",
        params={"project_id": e2e_context.project_id},
    )
    assert updates_response.status_code == 200
    assert isinstance(updates_response.json(), list)

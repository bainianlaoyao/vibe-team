from __future__ import annotations

from .conftest import E2EContext


def test_file_permission_flow(e2e_context: E2EContext) -> None:
    tree_response = e2e_context.client.get(
        "/api/v1/files",
        params={"project_id": e2e_context.project_id, "path": ".", "max_depth": 2},
    )
    assert tree_response.status_code == 200
    root = tree_response.json()["root"]
    readme = next(child for child in root["children"] if child["name"] == "README.md")
    file_id = readme["id"]

    content_response = e2e_context.client.get(
        f"/api/v1/files/{file_id}/content",
        params={"project_id": e2e_context.project_id},
    )
    assert content_response.status_code == 200
    assert "E2E workspace" in content_response.json()["content"]

    lock_response = e2e_context.client.patch(
        f"/api/v1/files/{file_id}/permissions",
        json={
            "project_id": e2e_context.project_id,
            "permission": "none",
        },
    )
    assert lock_response.status_code == 200

    denied_response = e2e_context.client.get(
        f"/api/v1/files/{file_id}/content",
        params={"project_id": e2e_context.project_id},
    )
    assert denied_response.status_code == 403

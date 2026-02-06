from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz() -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "BeeBeeBrain Backend"
    assert payload["env"] in {"development", "test", "production"}


def test_readyz() -> None:
    response = client.get("/readyz")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {"status": "ready", "checks": {"configuration": "ok"}}

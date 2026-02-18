from fastapi.testclient import TestClient

from app import main as main_module
from app.main import app, get_redis


class FakeRedis:
    def ping(self) -> bool:
        return True


def test_health() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "API is running"
    assert payload["docs"] == "/docs"


def test_ui_page_served() -> None:
    client = TestClient(app)
    response = client.get("/ui")
    assert response.status_code == 200
    assert "<html" in response.text.lower()


def test_redis_ping() -> None:
    app.dependency_overrides[get_redis] = lambda: FakeRedis()
    client = TestClient(app)
    response = client.get("/redis-ping")
    assert response.status_code == 200
    assert response.json() == {"redis": True}
    app.dependency_overrides.clear()


def test_restart_endpoint_disabled_by_default() -> None:
    client = TestClient(app)
    response = client.post("/admin/restart")
    assert response.status_code == 403


def test_restart_endpoint_enabled_with_token(monkeypatch) -> None:
    captured: dict[str, float] = {}

    def fake_schedule(delay_seconds: float) -> None:
        captured["delay_seconds"] = delay_seconds

    monkeypatch.setattr(main_module, "schedule_process_restart", fake_schedule)
    monkeypatch.setattr(main_module.settings, "enable_self_restart", True)
    monkeypatch.setattr(main_module.settings, "self_restart_token", "secret-token")
    monkeypatch.setattr(main_module.settings, "self_restart_delay_seconds", 0.25)

    client = TestClient(app)
    response = client.post("/admin/restart", headers={"X-Restart-Token": "secret-token"})
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert captured["delay_seconds"] == 0.25


def test_restart_endpoint_enabled_with_bearer(monkeypatch) -> None:
    captured: dict[str, float] = {}

    def fake_schedule(delay_seconds: float) -> None:
        captured["delay_seconds"] = delay_seconds

    monkeypatch.setattr(main_module, "schedule_process_restart", fake_schedule)
    monkeypatch.setattr(main_module.settings, "enable_self_restart", True)
    monkeypatch.setattr(main_module.settings, "self_restart_token", "bearer-secret")
    monkeypatch.setattr(main_module.settings, "self_restart_delay_seconds", 0.3)

    client = TestClient(app)
    response = client.post("/admin/restart", headers={"Authorization": "Bearer bearer-secret"})
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert captured["delay_seconds"] == 0.3

from fastapi.testclient import TestClient

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


def test_redis_ping() -> None:
    app.dependency_overrides[get_redis] = lambda: FakeRedis()
    client = TestClient(app)
    response = client.get("/redis-ping")
    assert response.status_code == 200
    assert response.json() == {"redis": True}
    app.dependency_overrides.clear()

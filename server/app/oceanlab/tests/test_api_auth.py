def test_health_open_no_auth(db):
    from fastapi.testclient import TestClient

    from app.oceanlab.db import get_db
    from app.oceanlab.main import app

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as c:
            resp = c.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["db"] is True
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_health_reports_degraded_when_storage_unreachable(db, monkeypatch):
    # The probe is a read against the configured store, so "unhealthy" means
    # the store raised — a dead S3 client or bad credentials — not a missing
    # local directory (LocalDiskStore creates its own root).
    from app.oceanlab.routers import health as health_module

    class _DeadStore:
        def ping(self):
            raise RuntimeError("S3 unreachable")

    monkeypatch.setattr(health_module, "get_store", lambda: _DeadStore())

    body = health_module.health(db)
    assert body["storage"] is False
    assert body["status"] == "degraded"


def test_no_header_401(client):
    client.headers.pop("Authorization", None)
    resp = client.get("/api/artists")
    assert resp.status_code == 401


def test_bad_token_401(client):
    client.headers.update({"Authorization": "Bearer wrong-token"})
    resp = client.get("/api/artists")
    assert resp.status_code == 401


def test_good_token_200(client):
    resp = client.get("/api/artists")
    assert resp.status_code == 200


def test_missing_token_returns_503(client, monkeypatch):
    from app.oceanlab.config import settings

    monkeypatch.setattr(settings, "token", "")
    resp = client.get("/api/artists")
    assert resp.status_code == 503

def test_health_open_no_auth(db):
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import app

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


def test_health_reports_degraded_when_storage_root_missing(db, tmp_path, monkeypatch):
    # Calls the endpoint function directly (rather than round-tripping through
    # TestClient) so the app lifespan's `storage_root.mkdir(...)` doesn't
    # recreate the very directory we're testing the absence of.
    from app.config import settings
    from app.routers.health import health

    monkeypatch.setattr(settings, "storage_root", tmp_path / "does-not-exist")

    body = health(db)
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


def test_settings_rejects_short_oceanlab_token():
    import pytest
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="postgresql://x/y", oceanlab_token="")

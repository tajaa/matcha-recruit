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

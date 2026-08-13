"""Request-size tests for the public Cappe booking suggestion route."""
import os

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.models.bookings import CappeBookingSuggestionRequest  # noqa: E402
from app.cappe.routes.public.bookings import _BookingSuggestionBodyLimitRoute  # noqa: E402


def _client(monkeypatch):
    router = APIRouter(route_class=_BookingSuggestionBodyLimitRoute)

    @router.post("/suggestions")
    async def suggestions(body: CappeBookingSuggestionRequest):
        return {"request": body.request}

    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_declared_oversized_body_is_rejected_before_endpoint(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/suggestions",
        content=b"{}",
        headers={"content-length": "8193"},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Request is too large"


def test_chunked_oversized_body_is_rejected_before_endpoint(monkeypatch):
    client = _client(monkeypatch)

    def chunks():
        yield b'{"booking_type_id":"00000000-0000-0000-0000-000000000000",'
        yield b'"request":"' + (b"x" * 8200) + b'"}'

    response = client.post("/suggestions", content=chunks())

    assert response.status_code == 413
    assert response.json()["detail"] == "Request is too large"

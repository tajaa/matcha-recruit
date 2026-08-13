"""Route-boundary tests for public Cappe booking suggestions."""
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.models.bookings import CappeBookingSuggestionRequest  # noqa: E402
from app.cappe.routes.public import bookings as route  # noqa: E402
from app.cappe.services.booking_suggestions import BookingPreference  # noqa: E402


SITE_ID = uuid4()
TYPE_ID = uuid4()
MARIA_ID = UUID("11111111-1111-1111-1111-111111111111")
REQUEST = SimpleNamespace(headers={})


class _Conn:
    def __init__(self):
        self.writes = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def fetchrow(self, query, *_args):
        if "cappe_booking_types" in query:
            return {
                "id": TYPE_ID,
                "duration_minutes": 60,
                "price_cents": 5000,
                "pricing_mode": "flat",
                "requires_approval": False,
                "buffer_minutes": 0,
                "status": "active",
            }
        raise AssertionError(f"unexpected fetchrow: {query}")

    async def fetch(self, query, *_args):
        if "cappe_staff_services" in query:
            return [{"id": MARIA_ID, "name": "Maria"}]
        raise AssertionError(f"unexpected fetch: {query}")

    async def fetchval(self, query, *_args):
        assert "NOW()" in query
        return datetime(2026, 8, 13, 12, tzinfo=timezone.utc)

    async def execute(self, *args):
        self.writes.append(args)


@pytest.mark.asyncio
async def test_suggestion_route_returns_options_without_writes(monkeypatch):
    conn = _Conn()
    pref = BookingPreference(staff_names=("Maria",), windows=(), requested_count=1)
    slot = {
        "start": "2026-08-18T10:00:00",
        "end": "2026-08-18T11:00:00",
        "date": "2026-08-18",
        "day_label": "Tue Aug 18",
        "time_label": "10:00 AM",
        "price_cents": 5000,
        "available_staff_ids": [str(MARIA_ID)],
    }
    monkeypatch.setattr(route, "client_ip", lambda _request: "127.0.0.1")
    monkeypatch.setattr(route, "check_rate_limit", _noop_rate_limit)
    monkeypatch.setattr(route, "get_connection", lambda: conn)
    monkeypatch.setattr(route, "_published_site", _published_site)
    monkeypatch.setattr(route, "_location_ctx", _location_ctx)
    calls = []
    monkeypatch.setattr(route, "_load_live_booking_slots", _live_slots(slot, calls))
    monkeypatch.setattr(route, "extract_booking_preference", _preference(pref))

    result = await route.public_booking_suggestions(
        "demo",
        CappeBookingSuggestionRequest(booking_type_id=TYPE_ID, request="Maria Tuesday"),
        REQUEST,
    )

    assert result.timezone == "UTC"
    assert result.options[0].staff_id == MARIA_ID
    assert conn.writes == []
    assert calls[0]["days"] == 14
    assert calls[0]["max_slots"] is None


@pytest.mark.asyncio
async def test_suggestion_route_uses_tight_rate_limits(monkeypatch):
    conn = _Conn()
    calls = []
    monkeypatch.setattr(route, "client_ip", lambda _request: "127.0.0.1")
    monkeypatch.setattr(route, "check_rate_limit", _record_rate_limit(calls))
    monkeypatch.setattr(route, "get_connection", lambda: conn)
    monkeypatch.setattr(route, "_published_site", _published_site)
    monkeypatch.setattr(route, "_location_ctx", _location_ctx)
    async def no_slots(*_args, **_kwargs):
        return []

    monkeypatch.setattr(route, "_load_live_booking_slots", no_slots)
    monkeypatch.setattr(route, "extract_booking_preference", _preference(
        BookingPreference(staff_names=(), windows=(), requested_count=1)
    ))

    await route.public_booking_suggestions(
        "demo",
        CappeBookingSuggestionRequest(booking_type_id=TYPE_ID, request="Tuesday"),
        REQUEST,
    )

    assert calls == [
        ("127.0.0.1", "cappe_booking_suggest_min", 1, 60),
        ("127.0.0.1", "cappe_booking_suggest_hr", 6, 3600),
        (str(SITE_ID), "cappe_booking_suggest_site_hr", 30, 3600),
    ]


@pytest.mark.asyncio
async def test_honeypot_rejects_before_database_or_model(monkeypatch):
    monkeypatch.setattr(route, "client_ip", lambda _request: "127.0.0.1")
    monkeypatch.setattr(route, "check_rate_limit", _noop_rate_limit)
    monkeypatch.setattr(route, "get_connection", lambda: (_ for _ in ()).throw(AssertionError("DB opened")))
    monkeypatch.setattr(route, "extract_booking_preference", _unexpected_model)

    with pytest.raises(HTTPException) as exc:
        await route.public_booking_suggestions(
            "demo",
            CappeBookingSuggestionRequest(
                booking_type_id=TYPE_ID, request="Maria Tuesday", website="bot"
            ),
            REQUEST,
        )
    assert exc.value.status_code == 400


async def _noop_rate_limit(*_args, **_kwargs):
    return None


async def _published_site(*_args, **_kwargs):
    return {"id": SITE_ID, "name": "Demo", "slug": "demo", "timezone": "UTC"}


async def _location_ctx(*_args, **_kwargs):
    return None, "UTC"


def _live_slots(slot, calls=None):
    async def load(*_args, **_kwargs):
        if calls is not None:
            calls.append(_kwargs)
        return [slot]
    return load


def _preference(pref):
    async def extract(*_args, **_kwargs):
        return pref
    return extract


async def _unexpected_model(*_args, **_kwargs):
    raise AssertionError("model called")


def _record_rate_limit(calls):
    async def record(*args, **kwargs):
        calls.append(args)
    return record

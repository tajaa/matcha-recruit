"""Authorization + scope invariants for the Week Start pane's endpoints."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.matcha.models.scheduling.employee_schedule import LocationScheduleProfileUpdate
from app.matcha.routes.employee_schedule import location_profile as routes


COMPANY_ID = UUID("11111111-1111-1111-1111-111111111111")
LOCATION_ID = UUID("66666666-6666-6666-6666-666666666666")
TEMPLATE_ID = UUID("22222222-2222-2222-2222-222222222222")
JOB_ID = UUID("88888888-8888-8888-8888-888888888888")
ACTOR_ID = UUID("77777777-7777-7777-7777-777777777777")


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_args):
        return False


def _conn(*, owned=1):
    conn = MagicMock()
    conn.transaction.return_value = _AsyncContext(None)
    conn.fetchval = AsyncMock(return_value=owned)
    return conn


def _patch(monkeypatch, conn, *, bundle=None):
    monkeypatch.setattr(routes, "get_connection", lambda: _AsyncContext(conn))
    monkeypatch.setattr(routes, "require_company_id", AsyncMock(return_value=COMPANY_ID))
    monkeypatch.setattr(routes, "assert_manager_location", AsyncMock())
    monkeypatch.setattr(routes, "assert_job_available", AsyncMock())
    monkeypatch.setattr(routes, "load_profile_bundle", AsyncMock(return_value=bundle or {
        "profile": None, "template": None, "leader_job_name": None,
    }))


def _user():
    return SimpleNamespace(id=ACTOR_ID, role="client")


@pytest.mark.asyncio
async def test_get_checks_the_location_before_reading_it(monkeypatch):
    """Role alone is not enough — a location-scoped manager must not read
    another store's setup."""
    conn = _conn()
    _patch(monkeypatch, conn)
    guard = AsyncMock()
    monkeypatch.setattr(routes, "assert_manager_location", guard)

    await routes.get_location_schedule_profile(LOCATION_ID, _user())

    guard.assert_awaited_once()
    assert guard.await_args.kwargs["location_id"] == LOCATION_ID
    assert guard.await_args.kwargs["company_id"] == COMPANY_ID


@pytest.mark.asyncio
async def test_get_defaults_an_unconfigured_location_to_sunday(monkeypatch):
    conn = _conn()
    _patch(monkeypatch, conn)

    result = await routes.get_location_schedule_profile(LOCATION_ID, _user())

    assert result["week_start_weekday"] == 0
    assert result["operating_hours"] == {}
    assert result["default_week_template_id"] is None


@pytest.mark.asyncio
async def test_put_writes_only_the_fields_the_caller_sent(monkeypatch):
    """The pane saves one section at a time; a PATCH that rewrote the rest
    would clear whatever Huume had just interviewed for."""
    conn = _conn()
    _patch(monkeypatch, conn)
    upsert = AsyncMock(return_value={"id": TEMPLATE_ID})
    monkeypatch.setattr(routes, "upsert_location_profile", upsert)

    await routes.update_location_schedule_profile(
        LOCATION_ID, LocationScheduleProfileUpdate(week_start_weekday=1), _user(),
    )

    kwargs = upsert.await_args.kwargs
    assert kwargs["week_start_weekday"] == 1
    assert kwargs["operating_hours"] is routes.UNSET
    assert kwargs["notes"] is routes.UNSET
    assert kwargs["leader_job_id"] is routes.UNSET


@pytest.mark.asyncio
async def test_put_rejects_a_default_template_from_another_location(monkeypatch):
    """A company-wide template (location_id NULL) shows in every store's
    picker; making it one store's default would let another store's edits
    silently rewrite this store's week."""
    conn = _conn(owned=None)
    _patch(monkeypatch, conn)
    monkeypatch.setattr(routes, "upsert_location_profile", AsyncMock())

    with pytest.raises(HTTPException) as excinfo:
        await routes.update_location_schedule_profile(
            LOCATION_ID,
            LocationScheduleProfileUpdate(default_week_template_id=TEMPLATE_ID),
            _user(),
        )
    assert excinfo.value.status_code == 422


@pytest.mark.asyncio
async def test_put_rejects_a_leader_job_from_another_location(monkeypatch):
    conn = _conn()
    _patch(monkeypatch, conn)
    monkeypatch.setattr(routes, "upsert_location_profile", AsyncMock())
    monkeypatch.setattr(
        routes, "assert_job_available",
        AsyncMock(side_effect=routes.JobUnavailable("Job is not available at this location")),
    )

    with pytest.raises(HTTPException) as excinfo:
        await routes.update_location_schedule_profile(
            LOCATION_ID, LocationScheduleProfileUpdate(leader_job_id=JOB_ID), _user(),
        )
    assert excinfo.value.status_code == 422


@pytest.mark.asyncio
async def test_put_surfaces_a_service_validation_error_as_422(monkeypatch):
    conn = _conn()
    _patch(monkeypatch, conn)
    monkeypatch.setattr(
        routes, "upsert_location_profile", AsyncMock(side_effect=ValueError("Location not found")),
    )

    with pytest.raises(HTTPException) as excinfo:
        await routes.update_location_schedule_profile(
            LOCATION_ID, LocationScheduleProfileUpdate(notes="Busy on match days"), _user(),
        )
    assert excinfo.value.status_code == 422


def test_operating_hours_keys_must_be_weekday_indexes():
    with pytest.raises(ValueError):
        LocationScheduleProfileUpdate(operating_hours={"monday": {"open": "08:00", "close": "17:00"}})
    with pytest.raises(ValueError):
        LocationScheduleProfileUpdate(operating_hours={"7": {"open": "08:00", "close": "17:00"}})


def test_operating_hours_accepts_a_closed_day_as_null():
    body = LocationScheduleProfileUpdate(operating_hours={"0": None, "1": {"open": "08:00", "close": "17:00"}})
    assert body.operating_hours["0"] is None
    assert body.operating_hours["1"].open.hour == 8

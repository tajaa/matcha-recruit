"""Espresso users share the clients profile table with business clients."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.models.auth import UpdateProfileRequest
from app.core.routes.auth import profile


@pytest.mark.asyncio
async def test_individual_profile_update_writes_name_and_phone(monkeypatch):
    calls = []

    class Connection:
        async def execute(self, query, *values):
            calls.append((query, values))

    @asynccontextmanager
    async def connection():
        yield Connection()

    monkeypatch.setattr(profile, "get_connection", connection)
    user_id = uuid4()
    result = await profile.update_profile(
        UpdateProfileRequest(name="Espresso User", phone="555-0100"),
        SimpleNamespace(id=user_id, role="individual"),
    )

    assert result == {"status": "profile_updated"}
    assert len(calls) == 1
    query, values = calls[0]
    assert "UPDATE clients SET name = $1, phone = $2 WHERE user_id = $3" == query
    assert values == ("Espresso User", "555-0100", user_id)


async def _run_update(monkeypatch, request, role):
    calls = []

    class Connection:
        async def execute(self, query, *values):
            calls.append((query, values))

    @asynccontextmanager
    async def connection():
        yield Connection()

    monkeypatch.setattr(profile, "get_connection", connection)
    user_id = uuid4()
    await profile.update_profile(request, SimpleNamespace(id=user_id, role=role))
    return calls, user_id


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["individual", "client"])
async def test_empty_phone_clears_it_for_individuals_and_business_clients(monkeypatch, role):
    calls, user_id = await _run_update(monkeypatch, UpdateProfileRequest(phone=""), role)

    assert calls == [("UPDATE clients SET phone = $1 WHERE user_id = $2", ("", user_id))]


@pytest.mark.asyncio
async def test_name_only_update_leaves_phone_untouched(monkeypatch):
    calls, user_id = await _run_update(monkeypatch, UpdateProfileRequest(name="Renamed"), "individual")

    assert calls == [("UPDATE clients SET name = $1 WHERE user_id = $2", ("Renamed", user_id))]

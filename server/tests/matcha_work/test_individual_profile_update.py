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

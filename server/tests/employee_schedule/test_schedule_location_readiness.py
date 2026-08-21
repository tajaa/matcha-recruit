"""Location-readiness tests using a tiny asyncpg-like fake."""

import asyncio
from uuid import uuid4

import pytest

from app.matcha.services.scheduling.schedule_location_readiness import (
    assert_schedule_location_ready_to_publish,
    get_schedule_location_readiness,
)


class FakeConn:
    def __init__(self, location, industry="retail"):
        self.location = location
        self.industry = industry

    async def fetchrow(self, query, *args):
        if "FROM business_locations" in query:
            return self.location
        raise AssertionError(query)

    async def fetchval(self, query, *args):
        if "SELECT industry FROM companies" in query:
            return self.industry
        raise AssertionError(query)


def _location(**overrides):
    row = {
        "id": uuid4(),
        "address": "100 Main St",
        "city": "Los Angeles",
        "state": "CA",
        "zipcode": "90001",
        "jurisdiction_id": uuid4(),
        "timezone": "America/Los_Angeles",
        "naics": None,
    }
    row.update(overrides)
    return row


def _run(coro):
    return asyncio.run(coro)


def test_complete_location_is_ready():
    row = _location()
    result = _run(get_schedule_location_readiness(FakeConn(row), uuid4(), row["id"]))
    assert result.ready_to_publish is True
    assert result.missing_fields == ()
    assert result.industry_code == "retail"


@pytest.mark.parametrize("field", ["address", "city", "state", "zipcode", "jurisdiction_id", "timezone"])
def test_missing_location_prerequisite_is_reported(field):
    row = _location(**{field: None})
    result = _run(get_schedule_location_readiness(FakeConn(row), uuid4(), row["id"]))
    assert result.ready_to_publish is False
    assert field in result.missing_fields


def test_invalid_timezone_is_not_ready():
    row = _location(timezone="Not/AZone")
    result = _run(get_schedule_location_readiness(FakeConn(row), uuid4(), row["id"]))
    assert result.ready_to_publish is False
    assert result.missing_fields == ("timezone",)


def test_missing_industry_is_not_ready():
    row = _location()
    result = _run(get_schedule_location_readiness(FakeConn(row, industry=None), uuid4(), row["id"]))
    assert result.ready_to_publish is False
    assert result.missing_fields == ("industry",)


def test_assertion_raises_stable_http_error():
    from fastapi import HTTPException

    row = _location(address=None)
    with pytest.raises(HTTPException) as exc:
        _run(assert_schedule_location_ready_to_publish(FakeConn(row), uuid4(), row["id"]))
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "schedule_location_not_ready"
    assert "address" in exc.value.detail["missing_fields"]

"""Location-picker access for the scheduling eligibility manager queue."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.matcha.routes import locations


class _ConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_args):
        return False


class _Conn:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        return self.rows


def _row(location_id):
    return {
        "id": location_id, "name": "Wilshire", "address": "3435 Wilshire Blvd",
        "city": "Los Angeles", "state": "CA", "zipcode": "90010", "is_active": True,
    }


def test_location_manager_gets_only_their_managed_location(monkeypatch):
    company_id, user_id, location_id = uuid4(), uuid4(), uuid4()
    conn = _Conn([_row(location_id)])

    async def company_for_user(_user):
        return company_id

    monkeypatch.setattr(locations, "get_client_company_id", company_for_user)
    monkeypatch.setattr(locations, "get_connection", lambda: _ConnectionContext(conn))
    result = asyncio.run(locations.list_company_locations(
        current_user=SimpleNamespace(id=user_id, role="employee"),
    ))

    assert result["locations"][0]["id"] == str(location_id)
    query, args = conn.calls[0]
    assert "e.user_id = $2" in query
    assert args == (company_id, user_id)


def test_company_operator_keeps_full_location_list(monkeypatch):
    company_id, location_id = uuid4(), uuid4()
    conn = _Conn([_row(location_id)])

    async def company_for_user(_user):
        return company_id

    monkeypatch.setattr(locations, "get_client_company_id", company_for_user)
    monkeypatch.setattr(locations, "get_connection", lambda: _ConnectionContext(conn))
    result = asyncio.run(locations.list_company_locations(
        current_user=SimpleNamespace(id=uuid4(), role="client"),
    ))

    assert result["locations"][0]["id"] == str(location_id)
    query, args = conn.calls[0]
    assert "e.user_id = $2" not in query
    assert args == (company_id,)


def test_manager_queue_marks_two_party_confirmation_explicitly():
    source = (Path(__file__).parents[3] / "client/src/pages/app/employees/EmployeeSchedule.tsx").read_text()
    assert "Both employees confirmed." in source

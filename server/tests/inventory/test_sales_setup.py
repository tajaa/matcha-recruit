from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.matcha.models.inventory import SalesSetupStatus, SalesSourceUpsert
from app.matcha.routes import inventory as routes
from app.matcha.services.inventory import sales_setup as service


class Connection:
    def __init__(self, company_id, location_id, *, owned=True, tz="America/Los_Angeles", sales=False, enabled=False):
        self.company_id, self.location_id = company_id, location_id
        self.owned, self.tz, self.sales, self.enabled = owned, tz, sales, enabled
        self.calls = []

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        if "FROM business_locations" in query:
            assert args == (self.location_id, self.company_id)
            return {"timezone": self.tz} if self.owned else None
        assert args == (self.company_id, self.location_id)
        assert "s.location_id=$2" in query
        assert "b.company_id=$1 AND b.location_id=$2" in query
        assert "p.company_id=b.company_id" in query
        return dict(square_connected=True, square_bound=False, email_registered=True, draft_imports=2)

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        if "FROM scheduler_settings" in query:
            return [{"task_key": task, "enabled": self.enabled} for task in args[0]]
        assert args[:2] == (self.company_id, self.location_id)
        assert "gross_sales IS NOT NULL" in query or "si.status IN ('committed', 'discarded')" in query
        return [{"business_date": date(2026, 10, 16), "gross_sales": 0}] if self.sales else []


def configured(monkeypatch, enabled=True):
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(
        pos_intake_gmail_refresh_token="private-token" if enabled else None,
        pos_intake_gmail_client_id="private-id", pos_intake_gmail_client_secret="private-secret",
    ))
    monkeypatch.setattr(service.SquareProvider, "_CLIENT_ID", "private-id" if enabled else "")
    monkeypatch.setattr(service.SquareProvider, "_CLIENT_SECRET", "private-secret")
    monkeypatch.setenv("SQUARE_OAUTH_REDIRECT_URI", "https://example.com/callback")
    monkeypatch.setenv("POS_INTAKE_GMAIL_ADDRESS", "sales@example.com")


@pytest.mark.asyncio
@pytest.mark.parametrize("sales", [False, True])
async def test_setup_uses_the_actual_autopilot_sales_readers_and_deduplicates_days(monkeypatch, sales):
    configured(monkeypatch)
    conn = Connection(uuid4(), uuid4(), sales=sales)
    result = await service.sales_setup_status(conn, company_id=conn.company_id, location_id=conn.location_id, today=date(2026, 10, 17))
    payload = SalesSetupStatus(**result).model_dump_json()
    assert result["days_with_sales"] == (1 if sales else 0)
    assert result["latest_sales_date"] == (date(2026, 10, 16) if sales else None)
    assert result["square_connected"] and not result["square_bound"]
    assert not result["email_poll_enabled"] and not result["square_sync_enabled"]
    assert result["email_registered"] and result["draft_imports"] == 2
    assert result["mailbox_configured"] and result["square_configured"]
    assert "private-token" not in payload and "private-secret" not in payload
    assert "sales@example.com" in payload


@pytest.mark.asyncio
@pytest.mark.parametrize("tz", [None, "invalid/timezone", "America/Los_Angeles"])
async def test_missing_configuration_is_distinct_from_registered_sources(monkeypatch, tz):
    configured(monkeypatch, enabled=False)
    monkeypatch.delenv("POS_INTAKE_GMAIL_ADDRESS")
    conn = Connection(uuid4(), uuid4(), tz=tz, enabled=True)
    result = await service.sales_setup_status(conn, company_id=conn.company_id, location_id=conn.location_id)
    assert not result["mailbox_configured"] and not result["square_configured"]
    assert result["mailbox_address"] is None
    assert result["email_poll_enabled"] and result["square_sync_enabled"]


@pytest.mark.asyncio
async def test_other_tenants_or_inactive_locations_are_not_read():
    conn = Connection(uuid4(), uuid4(), owned=False)
    assert await service.sales_setup_status(conn, company_id=conn.company_id, location_id=conn.location_id) is None
    assert len(conn.calls) == 1


@pytest.mark.asyncio
async def test_route_preserves_the_store_ownership_refusal(monkeypatch):
    conn = Connection(uuid4(), uuid4(), owned=False)

    @asynccontextmanager
    async def connection():
        yield conn

    monkeypatch.setattr(routes, "get_connection", connection)
    with pytest.raises(HTTPException) as caught:
        await routes.get_sales_setup(location_id=conn.location_id, company_id=conn.company_id)
    assert caught.value.status_code == 404


@pytest.mark.asyncio
async def test_route_serializes_only_the_status_for_an_owned_store(monkeypatch):
    configured(monkeypatch)
    conn = Connection(uuid4(), uuid4())

    @asynccontextmanager
    async def connection():
        yield conn

    monkeypatch.setattr(routes, "get_connection", connection)
    result = await routes.get_sales_setup(location_id=conn.location_id, company_id=conn.company_id)
    assert SalesSetupStatus(**result).location_id == conn.location_id


def test_status_endpoint_requires_an_admin_and_sales_intake():
    from tests._helpers.routes import iter_api_routes

    route = next(route for route in iter_api_routes(routes.router) if route.endpoint is routes.get_sales_setup)
    dependencies = [dependency.call for dependency in route.dependant.dependencies]
    assert routes.require_admin_or_client in dependencies
    features = [cell.cell_contents for dependency in dependencies for cell in (dependency.__closure__ or ())]
    assert "sales_intake" in features


def test_registered_senders_are_validated_as_email_addresses():
    assert SalesSourceUpsert(from_address="sales@example.com").from_address == "sales@example.com"
    with pytest.raises(ValidationError):
        SalesSourceUpsert(from_address="not an email")

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.matcha.services.inventory.pos import provider_for
from app.matcha.services.inventory.pos.square import SquareProvider
from app.matcha.services.inventory.pos.sync import _credentials
from app.workers.tasks.pos_sales_sync import previous_completed_business_date


class FakeSquare(SquareProvider):
    def __init__(self):
        super().__init__(environment="sandbox")
        self.calls = 0

    async def _request(self, method, path, credentials, **kwargs):
        assert method == "POST"
        assert path == "/v2/orders/search"
        self.calls += 1
        if self.calls == 1:
            return {
                "orders": [{
                    "state": "COMPLETED",
                    "closed_at": "2026-08-18T02:00:00Z",
                    "line_items": [
                        {"catalog_object_id": "coffee", "name": "Latte", "quantity": "2", "total_money": {"amount": 900}},
                        {"catalog_object_id": "coffee", "name": "Latte", "quantity": "1", "total_money": {"amount": 450}},
                    ],
                }],
                "cursor": None,
            }
        raise AssertionError("unexpected second page")


class FakeCatalogSquare(SquareProvider):
    def __init__(self):
        super().__init__(environment="sandbox")
        self.calls = 0

    async def _request(self, method, path, credentials, **kwargs):
        assert method == "GET"
        assert path.startswith("/v2/catalog/list?types=ITEM_VARIATION")
        self.calls += 1
        item_id = "var-1" if self.calls == 1 else "var-2"
        name = "Latte" if self.calls == 1 else "Cappuccino"
        return {
            "objects": [{
                "type": "ITEM_VARIATION", "id": item_id,
                "item_variation_data": {"name": name, "sku": name.upper()},
            }],
            "cursor": "next" if self.calls == 1 else None,
        }


@pytest.mark.asyncio
async def test_square_normalizes_completed_orders_by_local_business_date():
    days = await FakeSquare().fetch_finalized_sales(
        credentials={"access_token": "token"},
        external_location_id="loc-1",
        start_date=date(2026, 8, 17),
        end_date=date(2026, 8, 18),
        timezone="America/Los_Angeles",
    )

    assert len(days) == 1
    assert days[0].business_date == date(2026, 8, 17)
    assert days[0].external_batch_id == "loc-1:2026-08-17"
    assert days[0].lines[0].external_item_id == "coffee"
    assert days[0].lines[0].quantity == Decimal("3")
    assert days[0].lines[0].gross_sales == Decimal("13.50")


@pytest.mark.asyncio
async def test_square_normalizes_inline_refunds_as_negative_quantity():
    provider = FakeSquare()

    async def request_with_return(method, path, credentials, **kwargs):
        return {
            "orders": [{
                "closed_at": "2026-08-18T02:00:00Z",
                "line_items": [{
                    "catalog_object_id": "coffee", "name": "Latte",
                    "quantity": "2", "returned_quantity": "1",
                    "total_money": {"amount": 900},
                }],
            }],
            "cursor": None,
        }

    provider._request = request_with_return
    days = await provider.fetch_finalized_sales(
        credentials={"access_token": "token"},
        external_location_id="loc-1",
        start_date=date(2026, 8, 17),
        end_date=date(2026, 8, 18),
        timezone="America/Los_Angeles",
    )

    assert days[0].lines[0].quantity == Decimal("1")


@pytest.mark.asyncio
async def test_square_catalog_paginates_item_variations():
    items = await FakeCatalogSquare().list_catalog_items(credentials={"access_token": "token"})

    assert items == [{"external_item_id": "var-1", "name": "Latte", "sku": "LATTE"},
                     {"external_item_id": "var-2", "name": "Cappuccino", "sku": "CAPPUCCINO"}]


def test_unknown_pos_provider_does_not_claim_to_be_implemented():
    with pytest.raises(ValueError, match="not implemented"):
        provider_for("toast")


def test_pos_credentials_are_decrypted_before_provider_use():
    credentials = _credentials({"access_token": "plain-token", "refresh_token": None})
    assert credentials == {"access_token": "plain-token", "refresh_token": None}


def test_scheduled_sync_uses_each_binding_timezone_for_yesterday():
    now = datetime(2026, 8, 22, 0, 30, tzinfo=timezone.utc)

    assert previous_completed_business_date("America/Los_Angeles", now) == date(2026, 8, 20)
    assert previous_completed_business_date("Asia/Tokyo", now) == date(2026, 8, 21)
    assert previous_completed_business_date("not/a-timezone", now) == date(2026, 8, 21)


@pytest.mark.asyncio
async def test_square_buckets_the_same_dollars_by_local_close_hour():
    provider = FakeSquare()

    async def request(method, path, credentials, **kwargs):
        line = {"catalog_object_id": "coffee", "name": "Latte", "quantity": "1", "total_money": {"amount": 500}}
        return {
            "orders": [
                # 07:10 and 07:40 PDT, then 12:05 PDT with a refund.
                {"closed_at": "2026-08-17T14:10:00Z", "line_items": [line]},
                {"closed_at": "2026-08-17T14:40:00Z", "line_items": [line, line]},
                {"closed_at": "2026-08-17T19:05:00Z", "line_items": [line],
                 "returns": [{"line_items": [{**line, "total_money": {"amount": 200}}]}]},
            ],
            "cursor": None,
        }

    provider._request = request
    days = await provider.fetch_finalized_sales(
        credentials={"access_token": "token"}, external_location_id="loc-1",
        start_date=date(2026, 8, 17), end_date=date(2026, 8, 17), timezone="America/Los_Angeles",
    )
    hours = {item.hour: (item.gross_sales, item.order_count) for item in days[0].hours}
    assert hours == {7: (Decimal("15"), 2), 12: (Decimal("3"), 1)}
    # The hours carry exactly the day's line dollars, refunds included.
    assert sum(value for value, _ in hours.values()) == sum(line.gross_sales for line in days[0].lines)


class _HourConn:
    def __init__(self):
        self.calls = []

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self):
                conn.calls.append(("BEGIN",))

            async def __aexit__(self, *_exc):
                conn.calls.append(("COMMIT",))
                return False

        return _Tx()

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))

    async def executemany(self, query, rows):
        self.calls.append(("executemany", query, rows))


@pytest.mark.asyncio
async def test_sales_hours_replace_the_day_whole():
    from uuid import uuid4

    from app.matcha.services.inventory.pos.base import ExternalSalesHour
    from app.matcha.services.inventory.sales_hourly import replace_sales_hours

    conn = _HourConn()
    company_id, location_id, connection_id = uuid4(), uuid4(), uuid4()
    written = await replace_sales_hours(
        conn, company_id=company_id, location_id=location_id, business_date=date(2026, 8, 17),
        source="square", connection_id=connection_id,
        hours=[ExternalSalesHour(7, Decimal("15"), 2), ExternalSalesHour(12, Decimal("3"), 1)],
    )
    assert written == 2
    kinds = [call[0] for call in conn.calls]
    assert kinds == ["BEGIN", "execute", "executemany", "COMMIT"]
    assert "DELETE FROM inventory_sales_hourly" in conn.calls[1][1]
    assert conn.calls[2][2][0] == (
        company_id, location_id, date(2026, 8, 17), 7, Decimal("15"), 2, "square", connection_id,
    )
    # A provider with nothing to say by hour never erases a day that had hours.
    conn = _HourConn()
    assert await replace_sales_hours(
        conn, company_id=company_id, location_id=location_id, business_date=date(2026, 8, 17),
        source="square", connection_id=connection_id, hours=[],
    ) == 0
    assert conn.calls == []


class _SyncConn(_HourConn):
    def __init__(self, binding):
        super().__init__()
        self.binding = binding

    async def fetch(self, query, *args):
        return [self.binding] if "inventory_pos_location_bindings" in query else []

    async def fetchrow(self, query, *args):
        return {"id": "run-1"}


@pytest.mark.asyncio
async def test_sync_records_hours_even_for_a_duplicate_day(monkeypatch):
    from uuid import uuid4

    from app.matcha.services.inventory.pos import sync
    from app.matcha.services.inventory.pos.base import ExternalSalesHour, FinalizedSalesDay
    from app.matcha.services.inventory.sales_commit import DuplicateSalesPeriodError

    location_id = uuid4()
    binding = {"id": uuid4(), "location_id": location_id, "external_location_id": "loc-1",
               "timezone": "America/Los_Angeles"}
    day = FinalizedSalesDay(
        external_location_id="loc-1", business_date=date(2026, 8, 17), timezone="America/Los_Angeles",
        external_batch_id="loc-1:2026-08-17", lines=[], hours=(ExternalSalesHour(7, Decimal("15"), 2),),
    )

    class Provider:
        async def fetch_finalized_sales(self, **_kwargs):
            return [day]

    async def duplicate(*_args, **_kwargs):
        raise DuplicateSalesPeriodError("already committed")

    monkeypatch.setattr(sync, "provider_for", lambda _name: Provider())
    monkeypatch.setattr(sync, "_credentials", lambda _secrets: {"access_token": "t"})
    monkeypatch.setattr(sync, "encrypt_secret", lambda value: value)
    monkeypatch.setattr(sync.sales_commit, "commit_sales_import", duplicate)
    conn = _SyncConn(binding)
    connection = {"id": uuid4(), "company_id": uuid4(), "provider": "square", "secrets": {}}
    result = await sync._sync_one_connection(
        conn, connection=connection, start_date=date(2026, 8, 17), end_date=date(2026, 8, 17),
    )
    assert result["duplicates_skipped"] == 1
    rows = next(call[2] for call in conn.calls if call[0] == "executemany")
    assert rows[0][1] == location_id and rows[0][3] == 7

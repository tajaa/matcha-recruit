from datetime import date
from decimal import Decimal

import pytest

from app.matcha.services.inventory.pos import provider_for
from app.matcha.services.inventory.pos.square import SquareProvider
from app.matcha.services.inventory.pos.sync import _credentials


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

import asyncio
from decimal import Decimal

from app.matcha.services.inventory.waste.lots import spoilage_risk_score
from app.matcha.services.inventory.waste.lots import consume_fefo


class _LotConn:
    def __init__(self):
        self.update_query = ""

    async def fetch(self, *_args):
        return [{"id": "first", "quantity_remaining": Decimal("2")}]

    async def fetchrow(self, query, *args):
        self.update_query = query
        return {"id": args[0], "quantity_remaining": args[1], "status": "open"}


def test_spoilage_risk_is_deterministic_and_bounded():
    result = spoilage_risk_score(
        quantity_remaining=Decimal("10"), days_to_expiry=3, average_daily_demand=Decimal("2"),
    )
    assert result == {
        "score": Decimal("0.4"), "days_of_cover": Decimal("5"),
        "at_risk_quantity": Decimal("4"), "basis": "expiry_vs_demand",
    }


def test_spoilage_risk_without_expiry_is_not_a_spoilage_claim():
    result = spoilage_risk_score(
        quantity_remaining=Decimal("10"), days_to_expiry=None, average_daily_demand=Decimal("2"),
    )
    assert result["score"] == 0
    assert result["basis"] == "no_expiry"


def test_consume_fefo_binds_remaining_quantity_as_numeric():
    conn = _LotConn()
    consumed = asyncio.run(consume_fefo(conn, company_id="company", item_id="item", quantity=1))

    assert consumed[0]["quantity"] == Decimal("1")
    assert "$2::numeric" in conn.update_query

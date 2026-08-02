from datetime import datetime, timedelta, timezone

from app.matcha.services.inventory.reorder import DEFAULT_COVER_DAYS, suggest_order

NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)


def _out(days_ago, qty):
    return {"kind": "out", "quantity": qty, "quantity_delta": -qty,
            "created_at": NOW - timedelta(days=days_ago)}


def _stockout(days_ago):
    return {"kind": "stockout", "quantity": None, "quantity_delta": None,
            "created_at": NOW - timedelta(days=days_ago)}


def _receipt(days_ago, qty):
    return {"kind": "in", "quantity": qty, "quantity_delta": qty,
            "created_at": NOW - timedelta(days=days_ago)}


def test_steady_consumption_rate_times_cover_days():
    movements = [_out(d, 2) for d in range(1, 11)]  # 2/day over ~10 days
    result = suggest_order(movements, NOW)
    assert result is not None
    assert result["suggested_quantity"] == round(2 * DEFAULT_COVER_DAYS)


def test_thin_history_returns_none():
    movements = [_out(1, 1)]
    assert suggest_order(movements, NOW) is None


def test_stockout_interval_average():
    movements = [_stockout(30), _stockout(21), _stockout(12), _out(5, 3), _out(3, 3)]
    result = suggest_order(movements, NOW)
    assert result["avg_stockout_interval_days"] == 9.0


def test_fallback_to_last_receipt_when_no_rate():
    movements = [_receipt(60, 24)]
    result = suggest_order(movements, NOW)
    assert result["suggested_quantity"] == 24.0


def test_null_quantity_movements_excluded():
    movements = [_out(1, 2), _out(2, 2), {"kind": "out", "quantity": None,
                 "quantity_delta": None, "created_at": NOW - timedelta(days=3)}]
    result = suggest_order(movements, NOW)
    assert result is not None  # the two valid outs still count


def test_confidence_tiers():
    many = [_out(d, 1) for d in range(1, 9)]
    assert suggest_order(many, NOW)["confidence"] in ("high", "medium")
    few = [_out(1, 1), _out(2, 1)]
    assert suggest_order(few, NOW)["confidence"] == "low"

"""Pure unit tests for the discount resolver (no DB)."""
from datetime import date

from app.cappe.services.discounts import apply_discount_cents, best_discount_percent

D = date(2026, 6, 12)


def _d(pct, scope="all", target=None, active=True, s=None, e=None):
    return {"percent_off": pct, "scope": scope, "target_id": target,
            "active": active, "starts_on": s, "ends_on": e}


def test_site_wide_applies_to_everything():
    assert best_discount_percent([_d(20)], kind="booking_type", target_id="x", on_date=D) == 20
    assert best_discount_percent([_d(20)], kind="product", target_id="y", on_date=D) == 20


def test_best_single_discount_wins_no_stacking():
    ds = [_d(20), _d(50, "booking_type", "bt1")]
    assert best_discount_percent(ds, kind="booking_type", target_id="bt1", on_date=D) == 50


def test_scoped_discount_only_hits_its_target():
    ds = [_d(50, "booking_type", "bt1")]
    assert best_discount_percent(ds, kind="booking_type", target_id="bt2", on_date=D) == 0


def test_inactive_ignored():
    assert best_discount_percent([_d(80, active=False)], kind="product", target_id="p", on_date=D) == 0


def test_date_window():
    future = _d(30, s=date(2026, 7, 1))
    assert best_discount_percent([future], kind="product", target_id="p", on_date=D) == 0
    assert best_discount_percent([future], kind="product", target_id="p", on_date=date(2026, 7, 2)) == 30
    past = _d(40, e=date(2026, 6, 1))
    assert best_discount_percent([past], kind="product", target_id="p", on_date=D) == 0


def test_apply_rounds_to_cents():
    assert apply_discount_cents(10000, 20) == 8000
    assert apply_discount_cents(10000, 0) == 10000
    assert apply_discount_cents(999, 33) == 669   # 999*0.67 = 669.33 → 669


def test_percent_clamped():
    assert best_discount_percent([_d(200)], kind="product", target_id="p", on_date=D) == 90
    assert apply_discount_cents(10000, 200) == 1000  # clamped to 90% off

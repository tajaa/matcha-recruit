"""Pure-logic tests for the Fair Workweek exposure engine (no DB, no network)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.matcha.services import fair_workweek as fw


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


# ── curated table shape ────────────────────────────────────────────────────

def test_every_ordinance_row_is_cited():
    for key, ordinance in fw._FAIR_WORKWEEK_ORDINANCES.items():
        assert ordinance.get("citation"), f"{key} missing citation"
        assert ordinance.get("authority_url"), f"{key} missing authority_url"
        assert ordinance.get("notice_days"), f"{key} missing notice_days"
        for bracket in ordinance.get("predictability_pay", []):
            assert bracket["unit"] in ("flat", "hours_at_rate")
        clopening = ordinance.get("clopening")
        if clopening:
            assert clopening["premium"]["unit"] in ("flat", "hours_at_rate")


# ── ordinance_for_location ─────────────────────────────────────────────────

def test_ordinance_for_location_covered_industry_match():
    ordinance, applicability = fw.ordinance_for_location("NY", "New York City", "retail")
    assert ordinance is not None
    assert applicability == "covered"


def test_ordinance_for_location_review_industry_when_mismatched():
    ordinance, applicability = fw.ordinance_for_location("NY", "New York City", "manufacturing")
    assert ordinance is not None
    assert applicability == "review_industry"


def test_ordinance_for_location_unmapped_when_no_curated_row():
    ordinance, applicability = fw.ordinance_for_location("TX", "Austin", "retail")
    assert ordinance is None
    assert applicability == "unmapped"


def test_ordinance_for_location_unmapped_when_state_or_city_missing():
    assert fw.ordinance_for_location(None, "New York City", "retail") == (None, "unmapped")
    assert fw.ordinance_for_location("NY", None, "retail") == (None, "unmapped")


# ── classify_change ────────────────────────────────────────────────────────

def test_classify_change_ignores_irrelevant_actions():
    row = {"action": "shift.publish", "entity_id": "s1", "details": {}, "created_at": _dt("2026-01-01T00:00:00+00:00")}
    assert fw.classify_change(row, {}) is None


def test_classify_change_excludes_employee_initiated():
    approved_at = _dt("2026-01-01T12:00:00+00:00")
    row = {
        "action": "assignment.delete", "entity_id": "s1",
        "details": {"employee_id": "e1", "shift_status": "published"},
        "created_at": approved_at,
    }
    assert fw.classify_change(row, {"s1": [approved_at]}) is None


def test_classify_change_requires_published_shift():
    row = {
        "action": "assignment.create", "entity_id": "s1",
        "details": {"employee_id": "e1", "shift_status": "draft"},
        "created_at": _dt("2026-01-01T00:00:00+00:00"),
    }
    assert fw.classify_change(row, {}) is None


def test_classify_change_shift_update_reduced_hours():
    row = {
        "action": "shift.update", "entity_id": "s1",
        "details": {
            "was_published": True,
            "before": {"starts_at": "2026-01-10T09:00:00+00:00", "ends_at": "2026-01-10T17:00:00+00:00",
                       "status": "published", "location_id": "loc1"},
            "after": {"starts_at": "2026-01-10T09:00:00+00:00", "ends_at": "2026-01-10T13:00:00+00:00",
                      "status": "published", "location_id": "loc1"},
        },
        "created_at": _dt("2026-01-08T00:00:00+00:00"),
    }
    event = fw.classify_change(row, {})
    assert event["kind"] == "reduced_hours"
    assert event["notice_hours"] == 57.0  # 2026-01-10T09:00 minus 2026-01-08T00:00


def test_classify_change_shift_delete_is_cancellation():
    row = {
        "action": "shift.delete", "entity_id": "s1",
        "details": {
            "was_published": True,
            "before": {"starts_at": "2026-01-10T09:00:00+00:00", "ends_at": "2026-01-10T17:00:00+00:00",
                       "status": "published", "location_id": "loc1"},
        },
        "created_at": _dt("2026-01-09T00:00:00+00:00"),
    }
    event = fw.classify_change(row, {})
    assert event["kind"] == "cancellation"


def test_classify_change_unpublished_shift_is_skipped():
    row = {
        "action": "shift.update", "entity_id": "s1",
        "details": {
            "was_published": False,
            "before": {"starts_at": "2026-01-10T09:00:00+00:00", "ends_at": "2026-01-10T17:00:00+00:00",
                       "status": "draft", "location_id": "loc1"},
            "after": {"starts_at": "2026-01-10T10:00:00+00:00", "ends_at": "2026-01-10T18:00:00+00:00",
                      "status": "draft", "location_id": "loc1"},
        },
        "created_at": _dt("2026-01-09T00:00:00+00:00"),
    }
    assert fw.classify_change(row, {}) is None


# ── predictability_pay_estimate / price_event ──────────────────────────────

def test_predictability_pay_estimate_flat():
    bracket = {"unit": "flat", "amount": 75.0}
    assert fw.predictability_pay_estimate(bracket, None) == Decimal("75.0")


def test_predictability_pay_estimate_hours_at_rate_needs_pay_rate():
    bracket = {"unit": "hours_at_rate", "amount": 1.0, "rate_multiplier": 1.0}
    assert fw.predictability_pay_estimate(bracket, None) is None
    assert fw.predictability_pay_estimate(bracket, Decimal("20.00")) == Decimal("20.00")


def test_price_event_uncostable_legacy_when_not_costable():
    ordinance = fw._FAIR_WORKWEEK_ORDINANCES[("NY", "new-york-city")]
    event = {"kind": "cancellation", "notice_hours": None, "costable": False}
    priced = fw.price_event(event, ordinance, None)
    assert priced["estimate"] is None
    assert priced["uncostable_reason"] == "uncostable_legacy"


def test_price_event_matches_nyc_bracket():
    ordinance = fw._FAIR_WORKWEEK_ORDINANCES[("NY", "new-york-city")]
    event = {"kind": "cancellation", "notice_hours": 12.0, "costable": True}  # 0.5 days notice
    priced = fw.price_event(event, ordinance, None)
    assert priced["estimate"] == 75.0
    assert priced["notice_days"] == 0.5


def test_summarize_location_exposure_totals_costed_events_only():
    priced = [
        {"estimate": 75.0}, {"estimate": 20.0}, {"estimate": None},
    ]
    summary = fw.summarize_location_exposure(priced)
    assert summary["event_count"] == 3
    assert summary["costed_event_count"] == 2
    assert summary["uncostable_event_count"] == 1
    assert summary["exposure_estimate"] == 95.0

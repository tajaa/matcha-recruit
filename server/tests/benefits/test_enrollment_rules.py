"""Pure-logic tests for the benefits enrollment engine (no DB)."""
from datetime import date

import pytest

from app.matcha.services.benefits_enrollment import (
    allowed_transition,
    build_closing_soon_email,
    build_unsubmitted_nudge_email,
    build_window_opened_email,
    compute_policy_month,
    life_event_window_ends_on,
    resolve_active_window,
    validate_election_payload,
)

TODAY = date(2027, 3, 15)


# ── allowed_transition ──────────────────────────────────────────────────────

def test_draft_can_submit():
    assert allowed_transition("draft", "submit") == "submitted"


def test_draft_can_edit_in_place():
    assert allowed_transition("draft", "edit") == "draft"


def test_submitted_can_approve_or_reject():
    assert allowed_transition("submitted", "approve") == "approved"
    assert allowed_transition("submitted", "reject") == "rejected"


def test_approved_is_terminal():
    assert allowed_transition("approved", "submit") is None
    assert allowed_transition("approved", "edit") is None


def test_rejected_can_edit_back_to_draft():
    assert allowed_transition("rejected", "edit") == "draft"


def test_unknown_transition_returns_none():
    assert allowed_transition("draft", "approve") is None
    assert allowed_transition("bogus_status", "submit") is None


# ── resolve_active_window ───────────────────────────────────────────────────

def test_open_period_covering_today_wins():
    period = {"id": "p1", "starts_on": date(2027, 3, 1), "ends_on": date(2027, 3, 31)}
    window = resolve_active_window(TODAY, period, [])
    assert window == {"kind": "oe", "id": "p1", "row": period}


def test_open_period_outside_dates_is_ignored():
    period = {"id": "p1", "starts_on": date(2027, 4, 1), "ends_on": date(2027, 4, 30)}
    assert resolve_active_window(TODAY, period, []) is None


def test_no_open_period_falls_back_to_approved_life_event():
    event = {"id": "le1", "window_ends_on": date(2027, 3, 20)}
    window = resolve_active_window(TODAY, None, [event])
    assert window == {"kind": "life_event", "id": "le1", "row": event}


def test_expired_life_event_window_is_excluded():
    event = {"id": "le1", "window_ends_on": date(2027, 3, 1)}
    assert resolve_active_window(TODAY, None, [event]) is None


def test_life_event_without_window_ends_on_is_excluded():
    event = {"id": "le1", "window_ends_on": None}
    assert resolve_active_window(TODAY, None, [event]) is None


def test_multiple_eligible_life_events_picks_latest_window():
    older = {"id": "le1", "window_ends_on": date(2027, 3, 18)}
    newer = {"id": "le2", "window_ends_on": date(2027, 3, 25)}
    window = resolve_active_window(TODAY, None, [older, newer])
    assert window["id"] == "le2"


def test_open_period_takes_precedence_over_life_event():
    period = {"id": "p1", "starts_on": date(2027, 3, 1), "ends_on": date(2027, 3, 31)}
    event = {"id": "le1", "window_ends_on": date(2027, 3, 25)}
    window = resolve_active_window(TODAY, period, [event])
    assert window["kind"] == "oe"


# ── validate_election_payload ───────────────────────────────────────────────

def test_waived_election_is_valid_when_type_waivable():
    validate_election_payload(None, None, waived=True, plan_waivable_for_type=True)  # no raise


def test_waived_election_rejected_when_type_not_waivable():
    with pytest.raises(ValueError):
        validate_election_payload(None, None, waived=True, plan_waivable_for_type=False)


def test_non_waived_requires_plan_and_tier_rows():
    with pytest.raises(ValueError, match="plan not found"):
        validate_election_payload(None, {"plan_id": "p1"}, waived=False)
    with pytest.raises(ValueError, match="tier not found"):
        validate_election_payload({"id": "p1", "status": "active"}, None, waived=False)


def test_tier_must_belong_to_plan():
    plan = {"id": "p1", "status": "active"}
    tier = {"plan_id": "p2"}
    with pytest.raises(ValueError, match="does not belong"):
        validate_election_payload(plan, tier, waived=False)


def test_plan_must_be_active():
    plan = {"id": "p1", "status": "archived"}
    tier = {"plan_id": "p1"}
    with pytest.raises(ValueError, match="not active"):
        validate_election_payload(plan, tier, waived=False)


def test_valid_non_waived_election_passes():
    plan = {"id": "p1", "status": "active"}
    tier = {"plan_id": "p1"}
    validate_election_payload(plan, tier, waived=False)  # no raise


# ── compute_policy_month ─────────────────────────────────────────────────────

def test_policy_month_none_without_plan_year_start():
    assert compute_policy_month(TODAY, None) is None


def test_policy_month_first_month_of_plan_year():
    assert compute_policy_month(date(2027, 1, 1), date(2027, 1, 1)) == 1


def test_policy_month_mid_year():
    # Plan year starts Jan 1; March is month 3.
    assert compute_policy_month(date(2027, 3, 15), date(2027, 1, 1)) == 3


def test_policy_month_wraps_around_year_boundary():
    # Plan year starts Oct 1 (2026); by March the policy year is in month 6.
    assert compute_policy_month(date(2027, 3, 1), date(2026, 10, 1)) == 6


# ── life_event_window_ends_on ────────────────────────────────────────────────

def test_window_ends_on_from_future_event_date():
    result = life_event_window_ends_on(date(2027, 4, 1), TODAY, 30)
    assert result == date(2027, 5, 1)


def test_window_ends_on_from_past_event_date_uses_today():
    # Event happened before today — the window starts counting from today, not
    # a lapsed date, so late-approved requests still get a full window.
    result = life_event_window_ends_on(date(2027, 1, 1), TODAY, 30)
    assert result == date(2027, 4, 14)


# ── email builders ───────────────────────────────────────────────────────────

def test_window_opened_email_contains_portal_link():
    subject, html = build_window_opened_email("2027 Open Enrollment", date(2027, 3, 31), "https://hey-matcha.com")
    assert "2027 Open Enrollment" in subject
    assert "https://hey-matcha.com/portal/benefits" in html


def test_unsubmitted_nudge_email_contains_portal_link():
    subject, html = build_unsubmitted_nudge_email("2027 Open Enrollment", date(2027, 3, 31), "https://hey-matcha.com")
    assert "https://hey-matcha.com/portal/benefits" in html


def test_closing_soon_email_contains_portal_link():
    subject, html = build_closing_soon_email("2027 Open Enrollment", date(2027, 3, 31), "https://hey-matcha.com")
    assert "https://hey-matcha.com/portal/benefits" in html


def test_email_builders_strip_trailing_slash_from_base_url():
    _, html = build_window_opened_email("P", date(2027, 3, 31), "https://hey-matcha.com/")
    assert "https://hey-matcha.com/portal/benefits" in html
    assert "https://hey-matcha.com//portal/benefits" not in html

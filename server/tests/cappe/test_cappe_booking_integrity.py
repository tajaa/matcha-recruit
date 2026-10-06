"""Bookings correctness — the 2026-10 commerce readiness review, PR 2.

What each block pins:

  * the owner's status changes follow a transition graph (no re-opening a
    released slot, confirming is approving, a business cancel tells the
    customer);
  * a booking write locks the resource it contends for, and keeps the larger
    of the two bookings' buffers between them;
  * "any available" moves past a stylist who doesn't work then, and only
    offers staff who work at the chosen location;
  * the hidden bot-trap field is checked;
  * slots are capped after the "any available" merge, not before;
  * the public price quote is bounded;
  * a customer's reschedule re-enters approval, tells both sides, and refuses
    a deleted service cleanly;
  * a customer's cancel tells the owner when the booking's money is still held;
  * accepting a held shop order confirms its booking;
  * a reminder no provider took is given back for another try;
  * every booking time in an email says its timezone.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_booking_integrity.py -q
"""
import asyncio
import os
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.cappe.models.bookings import (  # noqa: E402
    CappeBookingQuoteRequest,
    CappeBookingRequest,
    CappeBookingReschedule,
    CappeBookingStatusUpdate,
)
from app.cappe.routes import bookings as owner_mod  # noqa: E402
from app.cappe.routes import shop as shop_mod  # noqa: E402
from app.cappe.routes.public import booking_selfserve as selfserve  # noqa: E402
from app.cappe.routes.public import bookings as public_mod  # noqa: E402
from app.cappe.services import booking_lifecycle as lifecycle  # noqa: E402
from app.cappe.services import commerce  # noqa: E402
from app.cappe.services.email import format_when  # noqa: E402
from app.cappe.services.slots import generate_slots  # noqa: E402

SITE, TYPE, BOOKING, ORDER = uuid4(), uuid4(), uuid4(), uuid4()
ANA, BEN = uuid4(), uuid4()
ACCOUNT = SimpleNamespace(id=uuid4(), plan="business")
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
REQUEST = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))


class Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class SqlConn:
    """Answers by the first matching SQL fragment; records every call."""

    def __init__(self, answers=()):
        self.answers, self.calls = list(answers), []

    def _answer(self, kind, sql, args):
        self.calls.append((kind, sql, args))
        for needle, value in self.answers:
            if needle in sql:
                return value(sql, args) if callable(value) else value
        return None

    async def fetchrow(self, sql, *args):
        return self._answer("fetchrow", sql, args)

    async def fetchval(self, sql, *args):
        return self._answer("fetchval", sql, args)

    async def fetch(self, sql, *args):
        return self._answer("fetch", sql, args) or []

    async def execute(self, sql, *args):
        self._answer("execute", sql, args)

    def transaction(self):
        return Tx()

    def sql(self, needle):
        return [c for c in self.calls if needle in c[1]]


class Background:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((fn.__name__, args, kwargs))

    def names(self):
        return [name for name, _a, _k in self.tasks]


# ── the transition graph ─────────────────────────────────────────────────────

@pytest.mark.parametrize("current,new", [
    ("pending", "confirmed"), ("pending", "cancelled"),
    ("confirmed", "cancelled"), ("confirmed", "completed"),
])
def test_allowed_moves_pass(current, new):
    assert lifecycle.transition_error(current, new) is None


@pytest.mark.parametrize("current", ["cancelled", "declined"])
@pytest.mark.parametrize("new", ["pending", "confirmed", "completed"])
def test_a_released_slot_is_never_taken_back(current, new):
    """Re-confirming a cancelled booking used to grab its slot unchecked."""
    assert "can't be reopened" in lifecycle.transition_error(current, new)


@pytest.mark.parametrize("current,new,fragment", [
    ("confirmed", "pending", "can't be moved to pending"),
    ("completed", "confirmed", "can't be changed"),
    ("pending", "declined", "Use Decline"),
])
def test_other_refusals_say_why(current, new, fragment):
    assert fragment in lifecycle.transition_error(current, new)


@pytest.mark.parametrize("status_now", ["pending", "confirmed", "cancelled", "completed", "declined"])
def test_a_repeat_is_never_refused(status_now):
    assert lifecycle.transition_error(status_now, status_now) is None


def test_no_status_change_can_take_a_released_slot_back():
    for released in ("cancelled", "declined", "completed"):
        assert lifecycle.ALLOWED_TRANSITIONS[released] == frozenset()
    for frm, tos in lifecycle.ALLOWED_TRANSITIONS.items():
        if frm not in lifecycle.HOLDING_STATUSES:
            assert not (tos & set(lifecycle.HOLDING_STATUSES))


def test_the_lock_key_names_the_contended_resource():
    loc = uuid4()
    staffed = lifecycle.booking_lock_key(site_id=SITE, booking_type_id=TYPE, staff_id=ANA, location_id=loc)
    # A stylist is one resource across every service they offer.
    assert staffed == lifecycle.booking_lock_key(site_id=SITE, booking_type_id=uuid4(), staff_id=ANA, location_id=None)
    unstaffed = lifecycle.booking_lock_key(site_id=SITE, booking_type_id=TYPE, staff_id=None, location_id=loc)
    assert unstaffed != lifecycle.booking_lock_key(site_id=SITE, booking_type_id=TYPE, staff_id=None, location_id=None)
    assert str(TYPE) in unstaffed and str(loc) in unstaffed


@pytest.mark.parametrize("status_now,expected", [
    ("paid", True), ("fulfilled", True), ("pending", False), ("refunded", False),
])
def test_holds_money(status_now, expected):
    assert lifecycle.holds_money({"id": ORDER, "status": status_now}) is expected
    assert lifecycle.holds_money(None) is False


# ── the slot resolver ────────────────────────────────────────────────────────

SITE_ROW = {"id": SITE, "timezone": "UTC", "name": "Salon"}
BTYPE = {"id": TYPE, "duration_minutes": 60, "pricing_mode": "flat", "price_cents": 5000,
         "requires_approval": False, "buffer_minutes": 15}
TOMORROW_10 = (NOW + timedelta(days=1)).replace(hour=10, tzinfo=None)


def _resolver_conn(*, window=1, overlap=None):
    return SqlConn([
        ("SELECT NOW()", NOW),
        ("FROM cappe_availability", window),
        ("FROM cappe_bookings b", overlap),
        ("FROM cappe_rate_rules", []),
        ("FROM cappe_discounts", []),
    ])


def test_the_resource_is_locked_before_the_overlap_check():
    conn = _resolver_conn()
    out = asyncio.run(commerce.resolve_booking_slot(conn, SITE_ROW, BTYPE, TOMORROW_10, staff_id=ANA))
    assert out["booking_status"] == "confirmed"
    sqls = [c[1] for c in conn.calls]
    lock_at = next(i for i, s in enumerate(sqls) if "pg_advisory_xact_lock" in s)
    check_at = next(i for i, s in enumerate(sqls) if "FROM cappe_bookings b" in s)
    assert lock_at < check_at
    assert conn.calls[lock_at][2] == (f"cappe-booking:staff:{ANA}",)


def test_the_gap_between_bookings_is_the_larger_buffer():
    conn = _resolver_conn()
    asyncio.run(commerce.resolve_booking_slot(conn, SITE_ROW, BTYPE, TOMORROW_10, staff_id=ANA))
    (_, sql, args), = conn.sql("FROM cappe_bookings b")
    assert "GREATEST($7::integer, COALESCE(obt.buffer_minutes, 0))" in sql
    assert "LEFT JOIN cappe_booking_types obt" in sql and args[6] == 15


def test_a_taken_slot_is_a_409():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(commerce.resolve_booking_slot(_resolver_conn(overlap=1), SITE_ROW, BTYPE, TOMORROW_10, staff_id=ANA))
    assert exc.value.status_code == 409


def test_no_window_is_its_own_error():
    with pytest.raises(commerce.OutsideAvailability) as exc:
        asyncio.run(commerce.resolve_booking_slot(_resolver_conn(window=None), SITE_ROW, BTYPE, TOMORROW_10, staff_id=ANA))
    assert exc.value.status_code == 400 and exc.value.detail == "Time is outside availability"


# ── slots ────────────────────────────────────────────────────────────────────

def _day_window():
    return [{"weekday": (NOW + timedelta(days=1)).weekday(), "start_time": time(9), "end_time": time(13),
             "booking_type_id": None, "staff_id": None}]


def test_an_existing_bookings_own_buffer_is_kept_clear():
    """A 0-buffer service used to be offered right up against a booking that
    needs half an hour to turn the room around."""
    day = (NOW + timedelta(days=1)).date()
    booked = (datetime.combine(day, time(10), tzinfo=timezone.utc), datetime.combine(day, time(11), tzinfo=timezone.utc))
    btype = {"id": str(TYPE), "duration_minutes": 60, "price_cents": 0, "buffer_minutes": 0}
    starts = lambda busy: [s["time_label"] for s in generate_slots(_day_window(), btype, busy, "UTC", NOW, days_ahead=2)]  # noqa: E731
    assert starts([booked]) == ["9:00 AM", "11:00 AM", "12:00 PM"]              # no buffer anywhere
    assert starts([(*booked, 30)]) == ["12:00 PM"]                              # its 30 min clears 9 and 11
    assert starts([(*booked, 0)]) == ["9:00 AM", "11:00 AM", "12:00 PM"]


def _slots_conn(staff):
    return SqlConn([
        ("FROM cappe_availability", [{"weekday": (NOW + timedelta(days=d)).weekday(), "start_time": time(9),
                                      "end_time": time(17), "booking_type_id": None, "staff_id": None}
                                     for d in range(1, 8)]),
        ("FROM cappe_staff_services", [{"staff_id": s} for s in staff]),
        ("FROM cappe_bookings b", []),
        ("FROM cappe_rate_rules", []),
        ("SELECT NOW()", NOW),
    ])


@pytest.mark.asyncio
async def test_any_available_is_capped_after_the_merge():
    """Capping each stylist first cut everyone off at the same COUNT, which
    made the merged list end early and unevenly."""
    btype = {"id": TYPE, "duration_minutes": 30, "price_cents": 0, "pricing_mode": "flat", "buffer_minutes": 0}
    conn = _slots_conn([ANA, BEN])
    slots = await public_mod._load_live_booking_slots(
        conn, site={"id": SITE}, booking_type=btype, location_id=None, timezone_name="UTC",
        days=8, staff_id=None, discounts=[], max_slots=20,
    )
    assert len(slots) == 20
    # Both stylists are free for each of the 20 earliest times — the cap kept
    # the EARLIEST 20 of the union, not 20 of each.
    assert all(sorted(s["available_staff_ids"]) == sorted([str(ANA), str(BEN)]) for s in slots)
    assert "SELECT DISTINCT weekday" in conn.sql("FROM cappe_availability")[0][1]


@pytest.mark.asyncio
async def test_the_public_cap_shows_more_than_two_days():
    btype = {"id": TYPE, "duration_minutes": 15, "price_cents": 0, "pricing_mode": "flat", "buffer_minutes": 0}
    slots = await public_mod._load_live_booking_slots(
        _slots_conn([]), site={"id": SITE}, booking_type=btype, location_id=None, timezone_name="UTC",
        days=8, staff_id=None, discounts=[],
    )
    assert len({s["date"] for s in slots}) >= 7


@pytest.mark.asyncio
async def test_only_staff_who_work_at_the_location_are_offered():
    loc = uuid4()
    conn = SqlConn([("FROM cappe_staff_services", [{"staff_id": ANA}])])
    assert await public_mod._active_staff_for_type(conn, SITE, TYPE, loc) == [ANA]
    _, sql, args = conn.calls[0]
    assert "s.location_id IS NULL OR s.location_id = $3" in sql and args == (TYPE, SITE, loc)


# ── creating a booking ───────────────────────────────────────────────────────

def _booking_body(**kw):
    return CappeBookingRequest(booking_type_id=TYPE, starts_at=TOMORROW_10,
                               customer_email="client@example.com", **kw)


def _wire_create(monkeypatch, *, offering, outcomes):
    """`outcomes`: per candidate, an exception to raise or None to succeed."""
    conn = SqlConn([
        ("FROM cappe_booking_types", {"id": TYPE, "name": "Cut", "duration_minutes": 60, "status": "active",
                                      "price_cents": 5000, "pricing_mode": "flat", "requires_approval": False,
                                      "buffer_minutes": 0}),
    ])
    tried = []

    async def _create(_conn, _site, _btype, _starts, _name, _email, _note, **kw):
        tried.append(kw["staff_id"])
        outcome = outcomes[len(tried) - 1]
        if outcome is not None:
            raise outcome
        return {"id": BOOKING, "status": "confirmed", "starts_at": NOW, "ends_at": NOW,
                "quoted_price_cents": 5000, "requires_approval": False, "access_token": "t" * 32}

    monkeypatch.setattr(public_mod, "client_ip", lambda _r: "127.0.0.1")
    monkeypatch.setattr(public_mod, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(public_mod, "_reject_reserved", lambda _e: None)
    monkeypatch.setattr(public_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(public_mod, "_published_site", AsyncMock(return_value={"id": SITE, "name": "Salon", "timezone": "UTC"}))
    monkeypatch.setattr(public_mod, "_location_ctx", AsyncMock(return_value=(None, "America/Los_Angeles")))
    monkeypatch.setattr(public_mod, "_site_rider", AsyncMock(return_value=[]))
    monkeypatch.setattr(public_mod, "_active_staff_for_type", AsyncMock(return_value=offering))
    monkeypatch.setattr(public_mod, "create_booking_in_tx", _create)
    monkeypatch.setattr(public_mod, "_site_owner", AsyncMock(return_value=None))
    monkeypatch.setattr(public_mod, "_recipient_send_ok", AsyncMock(return_value=False))
    return tried


def _create(body):
    return asyncio.run(public_mod.public_create_booking("salon", body, REQUEST, Background()))


def test_any_available_moves_past_a_stylist_who_doesnt_work_then(monkeypatch):
    """Ana works mornings, Ben afternoons; the 2pm slot came from Ben. This
    used to fail with a 400 because Ana was tried first."""
    tried = _wire_create(monkeypatch, offering=[ANA, BEN], outcomes=[commerce.OutsideAvailability(), None])
    out = _create(_booking_body())
    assert tried == [ANA, BEN] and out["booking_id"] == str(BOOKING)
    # The customer is told what the times mean and where to change them.
    assert out["timezone"] == "America/Los_Angeles" and out["manage_url"].endswith("/cappe/booking/" + "t" * 32)


def test_any_available_says_taken_when_someone_was_busy(monkeypatch):
    taken = HTTPException(status_code=409, detail="That slot is taken")
    _wire_create(monkeypatch, offering=[ANA, BEN], outcomes=[commerce.OutsideAvailability(), taken])
    with pytest.raises(HTTPException) as exc:
        _create(_booking_body())
    assert exc.value.status_code == 409 and exc.value.detail == "That time was just taken."


def test_any_available_says_outside_hours_when_nobody_works_then(monkeypatch):
    _wire_create(monkeypatch, offering=[ANA, BEN],
                 outcomes=[commerce.OutsideAvailability(), commerce.OutsideAvailability()])
    with pytest.raises(commerce.OutsideAvailability):
        _create(_booking_body())


def test_a_named_stylist_without_a_window_is_still_a_400(monkeypatch):
    _wire_create(monkeypatch, offering=[ANA, BEN], outcomes=[commerce.OutsideAvailability()])
    with pytest.raises(commerce.OutsideAvailability):
        _create(_booking_body(staff_id=ANA))


def test_a_stylist_from_another_location_cannot_be_named(monkeypatch):
    _wire_create(monkeypatch, offering=[ANA], outcomes=[None])
    with pytest.raises(HTTPException) as exc:
        _create(_booking_body(staff_id=BEN))
    assert exc.value.status_code == 400 and "isn't available for this service" in exc.value.detail


def test_the_bot_trap_is_checked(monkeypatch):
    tried = _wire_create(monkeypatch, offering=[ANA], outcomes=[None])
    with pytest.raises(HTTPException) as exc:
        _create(_booking_body(website="http://spam.test"))
    assert exc.value.status_code == 400 and tried == []


# ── the public price quote ───────────────────────────────────────────────────

def _wire_quote(monkeypatch, pricing_mode="hourly"):
    conn = SqlConn([
        ("FROM cappe_booking_types", {"id": TYPE, "duration_minutes": 60, "status": "active", "price_cents": 6000,
                                      "pricing_mode": pricing_mode, "requires_approval": False}),
        ("FROM cappe_rate_rules", []),
        ("FROM cappe_discounts", []),
        ("SELECT NOW()", NOW),
    ])
    monkeypatch.setattr(selfserve, "_read_rate_limit", AsyncMock())
    monkeypatch.setattr(selfserve, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(selfserve, "_published_site", AsyncMock(return_value={"id": SITE, "timezone": "UTC"}))
    monkeypatch.setattr(selfserve, "_location_ctx", AsyncMock(return_value=(None, "UTC")))


def _quote(starts, ends):
    return asyncio.run(selfserve.public_booking_quote(
        "salon", CappeBookingQuoteRequest(booking_type_id=TYPE, starts_at=starts, ends_at=ends), REQUEST,
    ))


def test_an_ordinary_quote_still_prices(monkeypatch):
    _wire_quote(monkeypatch)
    out = _quote(TOMORROW_10, TOMORROW_10 + timedelta(hours=2))
    assert out.price_cents == 12000 and out.duration_minutes == 120


@pytest.mark.parametrize("length,detail", [
    (timedelta(days=400), "Booking is too long"),               # held the server for minutes
    (timedelta(hours=14), "Booking can't span midnight"),
])
def test_the_quote_is_bounded_like_the_booking(monkeypatch, length, detail):
    _wire_quote(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        _quote(TOMORROW_10, TOMORROW_10 + length)
    assert exc.value.status_code == 400 and exc.value.detail == detail


# ── the customer's own changes ───────────────────────────────────────────────

def _token_row(**kw):
    return {
        "id": BOOKING, "site_id": SITE, "booking_type_id": TYPE, "staff_id": ANA, "location_id": None,
        "status": "confirmed", "starts_at": NOW + timedelta(days=2), "ends_at": NOW + timedelta(days=2, hours=1),
        "customer_name": "Client", "customer_email": "client@example.com", "quoted_price_cents": 5000,
        "access_token": "a" * 32, "type_name": "Cut", "duration_minutes": 60, "pricing_mode": "flat",
        "buffer_minutes": 0, "bt_price_cents": 5000, "bt_requires_approval": False, "bt_status": "active",
        "site_name": "Salon", "slug": "salon", "timezone": "America/New_York",
        "staff_name": "Ana", "location_name": None, **kw,
    }


def _wire_selfserve(monkeypatch, row, *, order=None):
    conn = SqlConn([
        ("WHERE b.access_token = $1", row),
        ("SELECT NOW()", NOW),
        # The reschedule's UPDATE (five arguments); the cancel's has one.
        ("UPDATE cappe_bookings", lambda _s, a: None if len(a) < 5 else {
            "starts_at": a[1], "ends_at": a[2], "quoted_price_cents": a[3],
            "status": "pending" if a[4] else row["status"]}),
    ])
    monkeypatch.setattr(selfserve, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(selfserve, "client_ip", lambda _r: "127.0.0.1")
    monkeypatch.setattr(selfserve, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(selfserve, "_site_owner", AsyncMock(return_value={"email": "owner@example.com", "name": "Owner"}))
    monkeypatch.setattr(selfserve, "linked_order", AsyncMock(return_value=order))
    slot = AsyncMock(return_value={"s_utc": NOW + timedelta(days=3), "e_utc": NOW + timedelta(days=3, hours=1),
                                   "quote_cents": 5500})
    monkeypatch.setattr(selfserve, "resolve_booking_slot", slot)
    return conn, slot


def test_the_customer_view_says_who_and_where(monkeypatch):
    _wire_selfserve(monkeypatch, _token_row(location_id=uuid4(), location_name="Mission"))
    view = asyncio.run(selfserve.public_booking_view("a" * 32, REQUEST))
    assert view.staff_id == ANA and view.staff_name == "Ana" and view.location_name == "Mission"


def test_a_reschedule_keeps_the_stylist_and_tells_both_sides(monkeypatch):
    conn, slot = _wire_selfserve(monkeypatch, _token_row())
    bg = Background()
    view = asyncio.run(selfserve.public_booking_reschedule(
        "a" * 32, CappeBookingReschedule(starts_at=TOMORROW_10), REQUEST, bg,
    ))
    assert slot.await_args.kwargs["staff_id"] == ANA
    assert view.status == "confirmed" and view.quoted_price_cents == 5500
    assert bg.names() == ["send_cappe_booking_rescheduled_email"] * 2
    customer, owner = (t[2] for t in bg.tasks)
    assert customer["for_owner"] is False and customer["link"].endswith("/cappe/booking/" + "a" * 32)
    assert owner["for_owner"] is True and owner["needs_approval"] is False


def test_a_reschedule_of_an_approval_service_needs_approval_again(monkeypatch):
    """The owner approved a time, not the customer's right to pick another."""
    conn, _slot = _wire_selfserve(monkeypatch, _token_row(bt_requires_approval=True))
    bg = Background()
    view = asyncio.run(selfserve.public_booking_reschedule(
        "a" * 32, CappeBookingReschedule(starts_at=TOMORROW_10), REQUEST, bg,
    ))
    (_, sql, args), = conn.sql("UPDATE cappe_bookings")
    assert args[4] is True and "status = CASE WHEN $5 THEN 'pending'" in sql
    assert view.status == "pending"
    assert all(t[2]["needs_approval"] for t in bg.tasks)


@pytest.mark.parametrize("change", [
    {"booking_type_id": None, "duration_minutes": None, "bt_status": None},   # service deleted
    {"bt_status": "archived"},                                                # taken off sale
])
def test_a_reschedule_of_a_service_no_longer_offered_is_a_clean_409(monkeypatch, change):
    """A deleted service used to 500 here (no duration to move it with)."""
    _conn, slot = _wire_selfserve(monkeypatch, _token_row(**change))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(selfserve.public_booking_reschedule(
            "a" * 32, CappeBookingReschedule(starts_at=TOMORROW_10), REQUEST, Background(),
        ))
    assert exc.value.status_code == 409 and "no longer offered" in exc.value.detail
    slot.assert_not_awaited()


@pytest.mark.parametrize("order,paid", [
    ({"id": ORDER, "status": "paid"}, True),
    ({"id": ORDER, "status": "pending"}, False),
    (None, False),
])
def test_a_customer_cancel_tells_the_owner_when_money_is_still_held(monkeypatch, order, paid):
    _wire_selfserve(monkeypatch, _token_row(), order=order)
    bg = Background()
    view = asyncio.run(selfserve.public_booking_cancel("a" * 32, REQUEST, bg))
    assert view.status == "cancelled" and view.can_modify is False
    (name, args, _kw), = bg.tasks
    assert name == "send_cappe_booking_cancelled_email" and args[-1] is paid
    # The time in the email says its zone.
    assert args[5].endswith(("EDT", "EST"))


# ── the owner's status changes ───────────────────────────────────────────────

def _owner_row(**kw):
    return {"id": BOOKING, "site_id": SITE, "booking_type_id": TYPE, "staff_id": None, "location_id": None,
            "customer_name": "Client", "customer_email": "client@example.com", "starts_at": NOW, "ends_at": NOW,
            "status": "confirmed", "note": None, "requires_approval": False, "quoted_price_cents": 5000,
            "approved_at": None, "decline_reason": None, "rider_acknowledged": False, "rider_snapshot": "[]",
            "created_at": NOW, **kw}


def _wire_owner(monkeypatch, *, current, updated):
    conn = SqlConn([
        ("FOR UPDATE", {"status": current}),
        ("UPDATE cappe_bookings", updated),
        ("SELECT name FROM cappe_booking_types", "Cut"),
        ("WHERE b.id = $1 AND b.site_id = $2", {**updated, "order_id": None, "order_status": None, "timezone": "UTC"}),
    ])
    monkeypatch.setattr(owner_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(owner_mod, "get_owned_site", AsyncMock(return_value={"id": SITE, "name": "Salon", "timezone": "UTC"}))
    return conn


def _patch(status_new, bg=None):
    return asyncio.run(owner_mod.update_booking_status(
        SITE, BOOKING, CappeBookingStatusUpdate(status=status_new), bg or Background(), account=ACCOUNT,
    ))


def test_reopening_a_cancelled_booking_is_refused_and_nothing_is_written(monkeypatch):
    conn = _wire_owner(monkeypatch, current="cancelled", updated=_owner_row())
    with pytest.raises(HTTPException) as exc:
        _patch("confirmed")
    assert exc.value.status_code == 409 and "can't be reopened" in exc.value.detail
    assert not conn.sql("UPDATE cappe_bookings")


def test_confirming_a_request_is_approving_it(monkeypatch):
    """It used to skip the approval stamp and the customer's email."""
    conn = _wire_owner(monkeypatch, current="pending", updated=_owner_row(requires_approval=True))
    bg = Background()
    out = _patch("confirmed", bg)
    (_, sql, args), = conn.sql("UPDATE cappe_bookings")
    assert "approved_at = CASE WHEN $4 THEN NOW()" in sql and args[3] is True
    assert bg.names() == ["send_cappe_booking_decision_email"]
    assert out["timezone"] == "UTC"


def test_a_business_cancel_tells_the_customer(monkeypatch):
    _wire_owner(monkeypatch, current="confirmed", updated=_owner_row(status="cancelled"))
    bg = Background()
    _patch("cancelled", bg)
    (name, args, _kw), = bg.tasks
    assert name == "send_cappe_booking_cancelled_by_host_email"
    assert args[0] == "client@example.com" and args[3] == "Cut" and args[4].endswith("UTC")


def test_completing_a_booking_sends_nothing(monkeypatch):
    _wire_owner(monkeypatch, current="confirmed", updated=_owner_row(status="completed"))
    bg = Background()
    _patch("completed", bg)
    assert bg.tasks == []


def test_the_bookings_list_is_paged_and_shows_the_linked_order(monkeypatch):
    conn = SqlConn()
    monkeypatch.setattr(owner_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(owner_mod, "get_owned_site", AsyncMock())
    asyncio.run(owner_mod.list_bookings(SITE, location_id=None, limit=100, offset=200, account=ACCOUNT))
    _, sql, args = conn.calls[0]
    assert "ord.id AS order_id" in sql and "COALESCE(loc.timezone, s.timezone) AS timezone" in sql
    assert "LIMIT $2 OFFSET $3" in sql and args == (SITE, 100, 200)


@pytest.mark.asyncio
async def test_a_decision_email_uses_the_locations_time(monkeypatch):
    loc = uuid4()
    conn = SqlConn([("SELECT name FROM cappe_booking_types", "Cut"), ("FROM cappe_locations", "Asia/Tokyo")])
    bg = Background()
    await owner_mod._notify_booking_decision(
        conn, bg, {"name": "Salon", "timezone": "UTC"}, _owner_row(location_id=loc), approved=True,
    )
    (_name, args, _kw), = bg.tasks
    assert args[4].endswith("JST")      # 12:00 UTC is 9:00 PM in Tokyo
    assert "9:00 PM" in args[4]


# ── accepting a held order approves its booking ──────────────────────────────

def test_accepting_an_order_confirms_its_bookings(monkeypatch):
    """When there's nothing to pay by card. One the buyer now pays for keeps
    its bookings held until the payment lands (test_cappe_booking_deposits.py)."""
    conn = SqlConn([("UPDATE cappe_orders", {"id": ORDER, "pay_by": None})])
    monkeypatch.setattr(shop_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(shop_mod, "get_owned_site", AsyncMock())
    monkeypatch.setattr(shop_mod, "_order_row", lambda order, items: dict(order))
    asyncio.run(shop_mod.accept_order(SITE, ORDER, Background(), account=ACCOUNT))
    (_, sql, args), = conn.sql("UPDATE cappe_bookings")
    assert "status = 'confirmed', approved_at = NOW()" in sql and "status = 'pending'" in sql
    assert args == (ORDER, SITE)


# ── reminders ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("delivered,expected", [(True, {"sent": 1, "failed": 0}), (False, {"sent": 0, "failed": 1})])
def test_a_reminder_no_provider_took_is_given_back(monkeypatch, delivered, expected):
    from app.workers.tasks import cappe_booking_reminders as worker

    booking = {"id": BOOKING, "access_token": "a" * 32, "status": "confirmed",
               "starts_at": datetime.now(timezone.utc) + timedelta(hours=5), "reminder_sent_at": None,
               "customer_email": "client@gmail.com", "customer_name": "Client", "type_name": "Cut",
               "site_name": "Salon", "timezone": "Europe/London"}
    conn = SqlConn([("FROM cappe_bookings b", [booking]), ("reminder_sent_at = NOW()", BOOKING)])
    conn.close = AsyncMock()
    monkeypatch.setattr(worker, "get_db_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr(worker, "scheduler_settings_row", AsyncMock(return_value={"enabled": True, "max_per_cycle": 10}))
    send = AsyncMock(return_value=delivered)
    monkeypatch.setattr(worker, "send_cappe_booking_reminder_email", send)
    out = asyncio.run(worker._run())
    assert {k: out[k] for k in expected} == expected
    released = conn.sql("SET reminder_sent_at = NULL")
    assert bool(released) is (not delivered)
    # The location's timezone is what the reminder shows.
    assert "COALESCE(loc.timezone, s.timezone) AS timezone" in conn.sql("FROM cappe_bookings b")[0][1]
    assert send.await_args.args[4].endswith(("BST", "GMT"))


# ── times say their zone ─────────────────────────────────────────────────────

@pytest.mark.parametrize("tz,label", [("America/New_York", "4:00 PM EDT"), ("UTC", "8:00 PM UTC"), (None, "8:00 PM UTC")])
def test_every_booking_time_says_its_zone(tz, label):
    assert format_when(datetime(2026, 6, 15, 20, 0, tzinfo=timezone.utc), tz).endswith(label)


# ── a timezone has to be one ─────────────────────────────────────────────────

@pytest.mark.parametrize("value,stored", [
    ("America/Denver", "America/Denver"), (" Europe/Paris ", "Europe/Paris"), ("", None), (None, None),
])
def test_site_and_location_timezones_accept_iana_names(value, stored):
    from app.cappe.models.bookings import CappeLocationCreate, CappeLocationUpdate
    from app.cappe.models.sites import CappeSiteUpdate

    assert CappeSiteUpdate(timezone=value).timezone == stored
    assert CappeLocationCreate(name="Main", timezone=value).timezone == stored
    assert CappeLocationUpdate(timezone=value).timezone == stored


@pytest.mark.parametrize("value", ["Mars/Olympus", "../../etc/passwd", "EST5EDT; DROP"])
def test_an_unloadable_timezone_is_refused_instead_of_silently_meaning_utc(value):
    from pydantic import ValidationError

    from app.cappe.models.sites import CappeSiteUpdate

    with pytest.raises(ValidationError) as exc:
        CappeSiteUpdate(timezone=value)
    assert "Unknown timezone" in str(exc.value)

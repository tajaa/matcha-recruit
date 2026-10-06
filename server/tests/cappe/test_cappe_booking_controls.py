"""Booking controls — the 2026-10 commerce readiness review, PR 10.

What each block pins:

  * minimum notice and the booking horizon: slots outside them aren't
    offered, and the server refuses them (a slot five minutes away used to be
    both offered and accepted);
  * time off — the business, a location or one staff member — is kept clear
    of slots and of bookings, and "any available" moves on when only one
    staff member is off;
  * the cancel cutoff: customers change or cancel online only until then;
  * the owner books and moves bookings without those rules, but never
    double-books;
  * the widget pages through later dates.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_booking_controls.py -q
"""
import asyncio
import inspect
import os
import pathlib
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import BackgroundTasks, HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.cappe.models.cappe import (  # noqa: E402
    CappeOwnerBookingCreate, CappeOwnerReschedule, CappeTimeOffInput,
)
from app.cappe.routes import bookings as owner_routes  # noqa: E402
from app.cappe.routes.public import booking_selfserve  # noqa: E402
from app.cappe.services import booking_rules, commerce  # noqa: E402
from app.cappe.services.slots import generate_slots  # noqa: E402

SITE, TYPE, STAFF, OTHER = uuid4(), uuid4(), uuid4(), uuid4()
NOW = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)   # a Tuesday, 15:00 UTC
ASSETS = pathlib.Path(commerce.__file__).parent / "render" / "assets"
MIGRATION = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "zzzzcappe48_booking_controls.py"

# Open every day 09:00–18:00 UTC, 60-minute appointments.
EVERY_DAY = [{"weekday": d, "start_time": time(9), "end_time": time(18), "booking_type_id": None, "staff_id": None}
             for d in range(7)]


def _slots(**over):
    btype = {"id": str(TYPE), "duration_minutes": 60, "price_cents": 1000, "pricing_mode": "flat",
             **over.pop("btype", {})}
    return generate_slots(EVERY_DAY, btype, [], "UTC", NOW, days_ahead=over.pop("days", 2), max_slots=None, **over)


# ── notice and horizon ───────────────────────────────────────────────────────

def test_slots_inside_the_minimum_notice_are_not_offered():
    assert _slots()[0]["start"] == "2026-10-06T16:00:00"
    # 15:00 + 3 hours = 18:00, when today's hours end: tomorrow's first slot.
    assert _slots(btype={"min_notice_minutes": 180})[0]["start"] == "2026-10-07T09:00:00"
    assert _slots(btype={"min_notice_minutes": 24 * 60})[0]["start"] == "2026-10-07T15:00:00"


def test_no_slot_is_offered_past_the_horizon():
    slots = _slots(btype={"max_advance_days": 1}, days=5)
    assert slots[-1]["start"] <= "2026-10-07T15:00:00" and slots[-1]["date"] == "2026-10-07"


def test_paging_starts_on_a_later_day():
    slots = _slots(start_day=7, days=1)
    assert {s["date"] for s in slots} == {"2026-10-13"}


def test_time_off_is_kept_clear():
    blocked = [(datetime(2026, 10, 7, 9, tzinfo=timezone.utc), datetime(2026, 10, 7, 12, tzinfo=timezone.utc))]
    starts = {s["start"] for s in _slots(blocked=blocked) if s["date"] == "2026-10-07"}
    assert "2026-10-07T11:00:00" not in starts and "2026-10-07T12:00:00" in starts


def test_the_server_refuses_what_the_widget_hides():
    btype = {"min_notice_minutes": 120, "max_advance_days": 30}
    with pytest.raises(HTTPException) as exc:
        booking_rules.check_window(btype, NOW + timedelta(minutes=90), NOW)
    assert exc.value.status_code == 400 and "at least 2 hours ahead" in exc.value.detail
    with pytest.raises(HTTPException) as exc:
        booking_rules.check_window(btype, NOW + timedelta(days=31), NOW)
    assert "30 days ahead" in exc.value.detail
    booking_rules.check_window(btype, NOW + timedelta(days=2), NOW)
    booking_rules.check_window({}, NOW + timedelta(minutes=1), NOW)        # no rules: any future time


@pytest.mark.parametrize("minutes,text", [(30, "30 minutes"), (60, "1 hour"), (180, "3 hours"), (1440, "1 day"), (2880, "2 days")])
def test_spans_read_naturally(minutes, text):
    assert booking_rules._span(minutes) == text


# ── time off ─────────────────────────────────────────────────────────────────

def test_time_off_applies_to_its_staff_member_and_business_wide_to_everyone():
    t = [{"staff_id": None, "starts_at": 1, "ends_at": 2}, {"staff_id": STAFF, "starts_at": 3, "ends_at": 4}]
    assert booking_rules.blocked_for(t, str(STAFF)) == [(1, 2), (3, 4)]
    assert booking_rules.blocked_for(t, str(OTHER)) == [(1, 2)]
    assert booking_rules.blocked_for(t, None) == [(1, 2)]


def test_time_off_is_a_kind_of_outside_availability():
    """So "any available" moves on to the next staff member."""
    assert isinstance(commerce.TimeOff(), commerce.OutsideAvailability)
    assert commerce.TimeOff().detail == "That time isn't available. Choose another."


class SlotConn:
    def __init__(self, *, window=1, time_off=None, overlap=None):
        self.window, self.time_off, self.overlap, self.calls = window, time_off, overlap, []

    async def fetchval(self, sql, *args):
        self.calls.append(sql)
        if sql == "SELECT NOW()":
            return NOW
        if "FROM cappe_availability" in sql:
            return self.window
        if "FROM cappe_time_off" in sql:
            return self.time_off
        if "FROM cappe_bookings b" in sql:
            return self.overlap
        return None

    async def execute(self, sql, *args):
        self.calls.append(sql)

    async def fetch(self, sql, *args):
        return []


def _resolve(conn, monkeypatch, *, owner=False, starts=datetime(2026, 10, 7, 10, 0), btype=None):
    monkeypatch.setattr(commerce, "fetch_rate_rules", AsyncMock(return_value=[]))
    monkeypatch.setattr(commerce, "fetch_active_discounts", AsyncMock(return_value=[]))
    bt = {"id": TYPE, "duration_minutes": 60, "price_cents": 1000, "pricing_mode": "flat",
          "requires_approval": True, **(btype or {})}
    return asyncio.run(commerce.resolve_booking_slot(
        conn, {"id": SITE, "timezone": "UTC"}, bt, starts, staff_id=STAFF, owner=owner,
    ))


def test_a_customer_booking_in_time_off_is_refused(monkeypatch):
    with pytest.raises(commerce.TimeOff):
        _resolve(SlotConn(time_off=1), monkeypatch)


def test_a_customer_booking_inside_the_notice_is_refused(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _resolve(SlotConn(), monkeypatch, btype={"min_notice_minutes": 48 * 60})
    assert "2 days ahead" in exc.value.detail


def test_the_owner_skips_hours_notice_and_time_off_and_is_the_approval(monkeypatch):
    conn = SlotConn(window=None, time_off=1)
    out = _resolve(conn, monkeypatch, owner=True, btype={"min_notice_minutes": 48 * 60})
    assert out["booking_status"] == "confirmed" and out["requires_approval"] is False
    assert not any("cappe_availability" in sql or "cappe_time_off" in sql for sql in conn.calls)


def test_the_owner_still_cannot_double_book(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _resolve(SlotConn(overlap=1), monkeypatch, owner=True)
    assert exc.value.status_code == 409


# ── the cancel cutoff ────────────────────────────────────────────────────────

def _booking(**over):
    return {"status": "confirmed", "starts_at": NOW + timedelta(hours=10), "cancel_cutoff_hours": 0, **over}


def test_a_customer_can_change_it_until_the_cutoff():
    assert booking_rules.self_service_open(_booking(), NOW)
    assert booking_rules.self_service_open(_booking(cancel_cutoff_hours=6), NOW)
    assert not booking_rules.self_service_open(_booking(cancel_cutoff_hours=12), NOW)
    assert not booking_rules.self_service_open(_booking(status="cancelled"), NOW)
    assert not booking_rules.self_service_open(_booking(starts_at=NOW - timedelta(hours=1)), NOW)


def test_past_the_cutoff_the_customer_is_told_who_to_ask():
    msg = booking_rules.cutoff_message(_booking(cancel_cutoff_hours=24), "Lumière", NOW)
    assert msg == "Changes close 1 day before the appointment. Contact Lumière to change it."
    assert booking_rules.cutoff_message(_booking(starts_at=NOW - timedelta(hours=1)), "L", NOW) == \
        "This booking can no longer be changed."


def test_self_serve_uses_the_cutoff():
    assert "self_service_open(row, now_utc)" in inspect.getsource(booking_selfserve._booking_can_modify)
    src = inspect.getsource(booking_selfserve)
    assert "bt.cancel_cutoff_hours" in src and src.count("cutoff_message(row, row[\"site_name\"])") == 2


# ── the owner books and moves ────────────────────────────────────────────────

class Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class OwnerConn:
    def __init__(self, answers=()):
        self.answers, self.calls = list(answers), []

    def _answer(self, sql, args):
        self.calls.append((sql, args))
        for needle, value in self.answers:
            if needle in sql:
                return value
        return None

    async def fetchrow(self, sql, *args):
        return self._answer(sql, args)

    async def fetchval(self, sql, *args):
        return self._answer(sql, args)

    async def fetch(self, sql, *args):
        return self._answer(sql, args) or []

    async def execute(self, sql, *args):
        self._answer(sql, args)

    def transaction(self):
        return Ctx(self)


BTYPE = {"id": TYPE, "name": "Cut", "duration_minutes": 60, "price_cents": 4000, "pricing_mode": "flat",
         "requires_approval": False, "buffer_minutes": 0, "status": "active"}


def _wire_owner(monkeypatch, conn):
    account = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(owner_routes, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(owner_routes, "get_owned_site",
                        AsyncMock(return_value={"id": SITE, "name": "Lumière", "timezone": "UTC"}))
    monkeypatch.setattr(owner_routes, "_booking_view", AsyncMock(return_value={"id": "view"}))
    return account


def test_the_owner_books_someone_in_and_they_get_a_confirmation(monkeypatch):
    conn = OwnerConn([("FROM cappe_booking_types", BTYPE), ("FROM cappe_staff", 1)])
    account = _wire_owner(monkeypatch, conn)
    booked = {"id": uuid4(), "starts_at": datetime(2026, 10, 7, 9, tzinfo=timezone.utc), "access_token": "tok"}
    create = AsyncMock(return_value=booked)
    monkeypatch.setattr(owner_routes, "create_booking_in_tx", create)
    bg = BackgroundTasks()
    body = CappeOwnerBookingCreate(booking_type_id=TYPE, starts_at=datetime(2026, 10, 7, 9), staff_id=STAFF,
                                   customer_name=" Ana ", customer_email="Ana@Example.com")
    assert asyncio.run(owner_routes.create_owner_booking(SITE, body, bg, account)) == {"id": "view"}
    assert create.await_args.kwargs["owner"] is True and create.await_args.args[4:6] == ("Ana", "ana@example.com")
    assert any("SET created_by_owner = true" in sql for sql, _a in conn.calls)
    (task,) = bg.tasks
    assert task.func.__name__ == "send_cappe_booking_received_email" and task.args[6].endswith("tok")


def test_an_owner_booking_without_an_email_or_with_notify_off_sends_nothing(monkeypatch):
    conn = OwnerConn([("FROM cappe_booking_types", BTYPE)])
    account = _wire_owner(monkeypatch, conn)
    monkeypatch.setattr(owner_routes, "create_booking_in_tx", AsyncMock(return_value={
        "id": uuid4(), "starts_at": NOW, "access_token": "t"}))
    bg = BackgroundTasks()
    asyncio.run(owner_routes.create_owner_booking(SITE, CappeOwnerBookingCreate(
        booking_type_id=TYPE, starts_at=NOW, customer_name="Walk-in"), bg, account))
    asyncio.run(owner_routes.create_owner_booking(SITE, CappeOwnerBookingCreate(
        booking_type_id=TYPE, starts_at=NOW, customer_name="Ana", customer_email="a@example.com", notify=False),
        bg, account))
    assert bg.tasks == []


@pytest.mark.parametrize("answers,code", [
    ([("FROM cappe_booking_types", None)], 404),
    ([("FROM cappe_booking_types", BTYPE), ("FROM cappe_staff", None)], 400),
])
def test_an_owner_booking_needs_this_sites_service_and_staff(monkeypatch, answers, code):
    account = _wire_owner(monkeypatch, OwnerConn(answers))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(owner_routes.create_owner_booking(SITE, CappeOwnerBookingCreate(
            booking_type_id=TYPE, starts_at=NOW, staff_id=STAFF, customer_name="Ana"), BackgroundTasks(), account))
    assert exc.value.status_code == code


CURRENT = {"id": uuid4(), "booking_type_id": TYPE, "staff_id": STAFF, "location_id": None, "status": "confirmed",
           "starts_at": NOW + timedelta(days=1), "customer_email": "a@example.com", "customer_name": "Ana",
           "access_token": "tok"}


def test_the_owner_moves_a_booking_and_the_customer_hears(monkeypatch):
    conn = OwnerConn([("FOR UPDATE", CURRENT), ("FROM cappe_booking_types", BTYPE), ("FROM cappe_staff", 1)])
    account = _wire_owner(monkeypatch, conn)
    new_start = NOW + timedelta(days=2)
    resolve = AsyncMock(return_value={"s_utc": new_start, "e_utc": new_start + timedelta(hours=1), "quote_cents": 4000})
    monkeypatch.setattr(owner_routes, "resolve_booking_slot", resolve)
    bg = BackgroundTasks()
    asyncio.run(owner_routes.reschedule_owner_booking(
        SITE, CURRENT["id"], CappeOwnerReschedule(starts_at=new_start.replace(tzinfo=None)), bg, account))
    kw = resolve.await_args.kwargs
    assert kw["owner"] is True and kw["exclude_booking_id"] == CURRENT["id"] and kw["staff_id"] == STAFF
    update = [a for sql, a in conn.calls if sql.startswith("UPDATE cappe_bookings SET starts_at")][0]
    assert update[1:4] == (new_start, new_start + timedelta(hours=1), 4000)
    (task,) = bg.tasks
    assert task.func.__name__ == "send_cappe_booking_rescheduled_email" and task.kwargs["for_owner"] is False


@pytest.mark.parametrize("current,code", [(None, 404), ({**CURRENT, "status": "cancelled"}, 409),
                                          ({**CURRENT, "booking_type_id": None}, 409)])
def test_only_a_live_booking_with_its_service_can_be_moved(monkeypatch, current, code):
    account = _wire_owner(monkeypatch, OwnerConn([("FOR UPDATE", current)]))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(owner_routes.reschedule_owner_booking(
            SITE, uuid4(), CappeOwnerReschedule(starts_at=NOW), BackgroundTasks(), account))
    assert exc.value.status_code == code


# ── time off, the owner's side ───────────────────────────────────────────────

def test_time_off_must_end_after_it_starts():
    with pytest.raises(ValidationError):
        CappeTimeOffInput(starts_at=NOW, ends_at=NOW)


def test_adding_time_off_checks_the_staff_member(monkeypatch):
    conn = OwnerConn([("FROM cappe_staff", None)])
    account = _wire_owner(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(owner_routes.add_time_off(SITE, CappeTimeOffInput(
            starts_at=NOW, ends_at=NOW + timedelta(hours=8), staff_id=OTHER), account))
    assert exc.value.status_code == 400 and not any("INSERT" in sql for sql, _a in conn.calls)


def test_adding_listing_and_removing_time_off(monkeypatch):
    new_id = uuid4()
    row = {"id": new_id, "staff_id": None, "location_id": None, "starts_at": NOW, "ends_at": NOW + timedelta(days=1),
           "reason": "Holiday", "created_at": NOW, "staff_name": None, "location_name": None}
    conn = OwnerConn([("INSERT INTO cappe_time_off", new_id), ("ORDER BY t.starts_at", [row]),
                      ("FROM cappe_time_off t", row),
                      ("DELETE FROM cappe_time_off", new_id)])
    account = _wire_owner(monkeypatch, conn)
    out = asyncio.run(owner_routes.add_time_off(SITE, CappeTimeOffInput(
        starts_at=NOW, ends_at=NOW + timedelta(days=1), reason="  Holiday "), account))
    assert out["reason"] == "Holiday"
    insert = [a for sql, a in conn.calls if "INSERT INTO cappe_time_off" in sql][0]
    assert insert[-1] == "Holiday"
    asyncio.run(owner_routes.list_time_off(SITE, include_past=False, account=account))
    listing = [sql for sql, _a in conn.calls if "ORDER BY t.starts_at" in sql][0]
    assert "($2 OR t.ends_at > NOW())" in listing
    asyncio.run(owner_routes.delete_time_off(SITE, new_id, account))
    gone = OwnerConn([])
    account = _wire_owner(monkeypatch, gone)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(owner_routes.delete_time_off(SITE, uuid4(), account))
    assert exc.value.status_code == 404


def test_service_rules_are_saved_and_returned():
    src = inspect.getsource(owner_routes)
    assert "min_notice_minutes, max_advance_days, cancel_cutoff_hours, payment_mode, deposit_cents)" in src
    assert '"min_notice_minutes", "max_advance_days", "cancel_cutoff_hours",' in src


# ── the widget ───────────────────────────────────────────────────────────────

def test_the_widget_pages_through_dates():
    js = (ASSETS / "booking.js").read_text()
    assert "from='+encodeURIComponent(from)" in js and "loadSlots(d.next_from)" in js
    assert "Later dates" in js


def test_the_slots_endpoint_pages_and_stops_at_the_horizon():
    from app.cappe.routes.public import bookings as public_bookings
    src = inspect.getsource(public_bookings.public_booking_slots)
    assert 'alias="from"' in src and '"next_from": next_from' in src
    assert "if next_day <= (int(horizon) if horizon else MAX_SLOT_DAYS) else None" in src
    loader = inspect.getsource(public_bookings._load_live_booking_slots)
    assert loader.count("blocked=blocked_for(time_off,") == 3


def test_the_migration_chains():
    src = MIGRATION.read_text()
    assert 'down_revision = "zzzzcappe47"' in src and 'revision = "zzzzcappe48"' in src
    assert "CREATE TABLE IF NOT EXISTS cappe_time_off" in src and "created_by_owner" in src
    assert date(2026, 1, 1)  # keep the date import honest

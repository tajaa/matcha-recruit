"""Per-service booking rules and closed periods.

  * minimum notice — the soonest a customer can book;
  * how far ahead — the latest;
  * cancel cutoff — customers can cancel or move a booking themselves until
    this long before it starts (after that they contact the business);
  * time off — closed periods for the whole business, one location or one
    staff member (`cappe_time_off`).

Slot generation hides what these rules forbid and `commerce.resolve_booking_slot`
refuses it — the widget used to offer, and the server accept, a slot five
minutes from now or on a public holiday. A booking the OWNER makes skips them
(a phone call at 8am for 8:30 is the owner's call); it still can't double-book.

Pure except `load_time_off` / `time_off_overlaps`.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

from fastapi import HTTPException, status


def _get(row: Any, key: str, default=None):
    try:
        value = row.get(key)
    except AttributeError:
        return default
    return default if value is None else value


def notice_cutoff(btype: Any, now_utc: datetime) -> datetime:
    """The earliest start a customer may book."""
    return now_utc + timedelta(minutes=int(_get(btype, "min_notice_minutes", 0)))


def advance_limit(btype: Any, now_utc: datetime) -> Optional[datetime]:
    """The latest start a customer may book (None = no limit)."""
    days = _get(btype, "max_advance_days")
    return now_utc + timedelta(days=int(days)) if days else None


def _span(minutes: int) -> str:
    if minutes % 1440 == 0 and minutes >= 1440:
        n = minutes // 1440
        return f"{n} day{'s' if n != 1 else ''}"
    if minutes % 60 == 0 and minutes >= 60:
        n = minutes // 60
        return f"{n} hour{'s' if n != 1 else ''}"
    return f"{minutes} minutes"


def check_window(btype: Any, start_utc: datetime, now_utc: datetime) -> None:
    """Refuse a start inside the notice period or beyond the horizon."""
    notice = int(_get(btype, "min_notice_minutes", 0))
    if notice and start_utc < notice_cutoff(btype, now_utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Book at least {_span(notice)} ahead.")
    limit = advance_limit(btype, now_utc)
    if limit is not None and start_utc > limit:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Bookings open {_get(btype, 'max_advance_days')} days ahead. Choose an earlier date.")


def self_service_open(row: Any, now_utc: datetime) -> bool:
    """Whether the customer can still cancel or move this booking themselves."""
    if _get(row, "status") not in ("pending", "confirmed"):
        return False
    cutoff = timedelta(hours=int(_get(row, "cancel_cutoff_hours", 0)))
    return row["starts_at"] - cutoff > now_utc


def cutoff_message(row: Any, site_name: str, now_utc: Optional[datetime] = None) -> str:
    """Why the customer can't change it themselves any more."""
    hours = int(_get(row, "cancel_cutoff_hours", 0))
    now = now_utc or datetime.now(row["starts_at"].tzinfo)
    if hours and _get(row, "status") in ("pending", "confirmed") and row["starts_at"] > now:
        return (f"Changes close {_span(hours * 60)} before the appointment. "
                f"Contact {site_name} to change it.")
    return "This booking can no longer be changed."


async def load_time_off(conn, site_id, *, location_id, start_utc: datetime, end_utc: datetime) -> list[dict]:
    """Closed periods overlapping [start, end) that apply at this location."""
    rows = await conn.fetch(
        "SELECT staff_id, location_id, starts_at, ends_at FROM cappe_time_off "
        "WHERE site_id = $1 AND (location_id IS NULL OR location_id = $2) "
        "AND starts_at < $4 AND ends_at > $3",
        site_id, location_id, start_utc, end_utc,
    )
    return [dict(r) for r in rows]


def blocked_for(time_off: Iterable[dict], staff_id: Optional[str]) -> list[tuple]:
    """The closed ranges that apply to one staff member (business-wide ones
    always do)."""
    return [
        (t["starts_at"], t["ends_at"]) for t in time_off
        if t.get("staff_id") is None or (staff_id is not None and str(t["staff_id"]) == str(staff_id))
    ]


async def time_off_overlaps(conn, site_id, *, start_utc, end_utc, staff_id, location_id) -> bool:
    return bool(await conn.fetchval(
        "SELECT 1 FROM cappe_time_off WHERE site_id = $1 "
        "AND (location_id IS NULL OR location_id IS NOT DISTINCT FROM $5) "
        "AND (staff_id IS NULL OR staff_id IS NOT DISTINCT FROM $4) "
        "AND starts_at < $3 AND ends_at > $2 LIMIT 1",
        site_id, start_utc, end_utc, staff_id, location_id,
    ))

"""Espresso calendar routes — the person's own events, plus what else belongs
on their calendar view: dated to-dos from their boards and, when they have
connected Google with calendar access, their Google Calendar (read-only here).

Mounted under `/matcha-work` with `require_feature("matcha_work")`, like the
productivity routes. Everything keys off `current_user.id`; `company_id` is
stored when there is one (personal Espresso accounts have their own company).
The wire shape and the rules live in `services/matcha_work/calendar_service`.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.models.auth import CurrentUser
from app.matcha.dependencies import get_client_company_id, require_admin_or_client
from app.matcha.models.matcha_work.calendar import (
    CalendarEventCreate,
    CalendarEventPatch,
    CalendarPrefs,
)
from app.matcha.services.matcha_work import calendar_service as cal

logger = logging.getLogger(__name__)

router = APIRouter()

GOOGLE_MAX_EVENTS = 250


def _bad(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


async def _tz(current_user: CurrentUser):
    return cal.zone(await cal.get_timezone(current_user.id))


def _google_view(event: dict) -> dict:
    """A Google event in this API's shape: an all-day `end` is the last day,
    not Google's exclusive next day."""
    end = event.get("end")
    if event.get("all_day") and isinstance(end, str) and len(end) == 10:
        try:
            end = (cal.parse_when(end) - timedelta(days=1)).isoformat()
        except ValueError:
            pass
    return {
        "id": event.get("id"),
        "title": event.get("title"),
        "start": event.get("start"),
        "end": end,
        "all_day": bool(event.get("all_day")),
        "location": event.get("location"),
        "link": event.get("link"),
        "attendee_count": len(event.get("attendees") or []),
    }


async def _google_events(user_id: UUID, start: str, end: str) -> dict:
    """The person's Google Calendar for the range, or why there is none. Never
    raises: Google being down must not blank the person's own calendar."""
    from app.matcha.services.matcha_work.gmail_service import SCOPE_CALENDAR_EVENTS, GmailService
    from app.matcha.services.matcha_work.google_calendar_service import GoogleCalendarService

    gmail = GmailService(user_id)
    try:
        await gmail.load_token()
    except Exception:  # noqa: BLE001
        logger.warning("calendar feed: could not load the Google connection", exc_info=True)
        return {"status": "error", "events": []}
    if not gmail.is_configured:
        return {"status": "not_connected", "events": []}
    if SCOPE_CALENDAR_EVENTS not in gmail.granted_scopes:
        return {"status": "needs_permission", "events": []}
    try:
        events = await GoogleCalendarService(user_id, gmail=gmail).list_events(
            time_min=start, time_max=end, max_results=GOOGLE_MAX_EVENTS,
        )
    except (httpx.HTTPError, ValueError):
        logger.warning("calendar feed: Google Calendar read failed", exc_info=True)
        return {"status": "error", "events": []}
    return {"status": "ok", "events": [_google_view(e) for e in events]}


@router.get("/calendar/feed")
async def calendar_feed(
    start: str = Query(..., max_length=64, description="RFC 3339 with an offset"),
    end: str = Query(..., max_length=64, description="RFC 3339 with an offset (exclusive)"),
    include_google: bool = Query(True),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Everything for one calendar view: the person's Espresso events, their
    dated to-dos, and (when connected) their Google Calendar."""
    try:
        begin, finish = cal.window(start, end)
    except ValueError as exc:
        raise _bad(exc) from exc
    tz_name = await cal.get_timezone(current_user.id)
    first_day, last_day = cal.days_touched(begin, finish)
    events = await cal.list_events(current_user.id, begin, finish, tz=cal.zone(tz_name))
    todos = await cal.list_dated_todos(current_user.id, first_day, last_day)
    google = (
        await _google_events(current_user.id, begin.isoformat(), finish.isoformat())
        if include_google else {"status": "skipped", "events": []}
    )
    return {"timezone": tz_name, "events": events, "todos": todos, "google": google}


@router.post("/calendar/events", status_code=201)
async def create_calendar_event(
    body: CalendarEventCreate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    try:
        fields = cal.event_fields(title=body.title, start=body.start, end=body.end,
                                  location=body.location, notes=body.notes)
    except ValueError as exc:
        raise _bad(exc) from exc
    company_id = await get_client_company_id(current_user)
    return await cal.create_event(
        current_user.id, company_id, fields,
        source_kind=body.source_kind, source_ref=body.source_ref, source_label=body.source_label,
        tz=await _tz(current_user),
    )


@router.get("/calendar/events/{event_id}")
async def get_calendar_event(
    event_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    event = await cal.get_event(event_id, current_user.id, tz=await _tz(current_user))
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.patch("/calendar/events/{event_id}")
async def update_calendar_event(
    event_id: UUID,
    body: CalendarEventPatch,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    try:
        event = await cal.update_event(
            event_id, current_user.id, body.model_dump(exclude_unset=True), tz=await _tz(current_user),
        )
    except ValueError as exc:
        raise _bad(exc) from exc
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.delete("/calendar/events/{event_id}", status_code=204)
async def delete_calendar_event(
    event_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    if not await cal.delete_event(event_id, current_user.id):
        raise HTTPException(status_code=404, detail="Event not found")


@router.put("/calendar/prefs")
async def set_calendar_prefs(
    body: CalendarPrefs,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """The app reports the zone it runs in, so the assistant can speak in the
    person's time."""
    try:
        return {"timezone": await cal.set_timezone(current_user.id, body.timezone)}
    except ValueError as exc:
        raise _bad(exc) from exc

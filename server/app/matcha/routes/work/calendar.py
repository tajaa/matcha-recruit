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
    CalendarPrefs, AppleConnection, AppleSnapshot, AppleActionResult,
)
from app.matcha.services.matcha_work import calendar_service as cal
from app.matcha.services.matcha_work import apple_calendar_service as apple

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


def _google_failure(exc: httpx.HTTPStatusError) -> dict:
    """Only controlled recovery copy leaves this boundary, never Google's
    response text (which can contain account or event details). Keep the
    legacy status values so older desktop builds still show the failure."""
    try:
        payload = exc.response.json()
    except ValueError:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else None
    reasons = {error} if isinstance(error, str) else set()
    if isinstance(error, dict):
        for field in ("errors", "details"):
            entries = error.get(field)
            if isinstance(entries, list):
                reasons.update(item["reason"] for item in entries
                    if isinstance(item, dict) and isinstance(item.get("reason"), str))
    status, reason = "error", "access_denied"
    message = "Google refused calendar access. Choose a Google account and reconnect. If it persists, contact support."
    if reasons & {"accessNotConfigured", "SERVICE_DISABLED", "serviceDisabled"}:
        reason = "api_disabled"
        message = "Google Calendar is not enabled for Espresso's Google connection. Contact support; reconnecting your account will not fix this."
    elif exc.response.status_code == 401 or "invalid_grant" in reasons:
        status, reason = "needs_permission", "reconnect_required"
        message = "Your Google connection expired or was revoked. Choose an account and reconnect."
    elif reasons & {"insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}:
        status, reason = "needs_permission", "calendar_permission"
        message = "Choose your Google account and allow Calendar access on Google's consent screen."
    elif exc.response.status_code == 429 or reasons & {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded"}:
        reason = "rate_limited"
        message = "Google is temporarily limiting Calendar requests. Try again later."
    elif exc.response.status_code >= 500:
        reason = "provider_unavailable"
        message = "Google Calendar is temporarily unavailable. Try again later."
    logger.warning("calendar feed: Google rejected request (HTTP %s, reason=%s)", exc.response.status_code, reason)
    return {"status": status, "reason": reason, "message": message, "events": []}


async def _google_events(user_id: UUID, start: str, end: str) -> dict:
    """The person's Google Calendar for the range, or why there is none:
    `ok`, `partial` (Google had more than the listing could read), `not_connected`,
    `needs_permission` or `error`. Never raises: Google being down must not
    blank the person's own calendar."""
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
        events, complete = await GoogleCalendarService(user_id, gmail=gmail).list_window(
            time_min=start, time_max=end, max_results=GOOGLE_MAX_EVENTS,
        )
    except httpx.HTTPStatusError as exc:
        return _google_failure(exc)
    except (httpx.HTTPError, ValueError):
        logger.warning("calendar feed: Google Calendar read failed", exc_info=True)
        return {"status": "error", "events": []}
    # `partial`: Google has more in this range than the view holds.
    return {"status": "ok" if complete else "partial", "events": [_google_view(e) for e in events]}


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
    try:
        apple_feed = await apple.feed(current_user.id, begin, finish)
    except Exception:
        logger.warning("Apple Calendar feed unavailable", exc_info=True)
        apple_feed = {"status": "error", "events": []}
    return {"timezone": tz_name, "events": events, "todos": todos, "google": google, "apple": apple_feed}


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


@router.get("/calendar/apple")
async def apple_connection(current_user: CurrentUser = Depends(require_admin_or_client)):
    row = await apple.connection(current_user.id)
    if row is None:
        return {"connected": False, "actions": []}
    return {"connected": True, "connection_id": str(row["connection_id"]),
            "calendars": row["calendars"], "destination": row["destination"],
            "synced_at": row["synced_at"].isoformat() if row["synced_at"] else None,
            "actions": await apple.recent(current_user.id)}


@router.put("/calendar/apple")
async def connect_apple(body: AppleConnection, current_user: CurrentUser = Depends(require_admin_or_client)):
    if body.user_id != current_user.id:
        raise HTTPException(409, "The signed-in account changed. Choose calendars again.")
    try:
        await apple.connect(current_user.id, body)
    except ValueError as exc:
        raise _bad(exc) from exc
    return {"ok": True}


@router.delete("/calendar/apple/{connection_id}")
async def disconnect_apple(connection_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    await apple.disconnect(current_user.id, connection_id)
    return {"ok": True}


@router.put("/calendar/apple/snapshot")
async def sync_apple(body: AppleSnapshot, current_user: CurrentUser = Depends(require_admin_or_client)):
    try:
        await apple.snapshot(current_user.id, body)
    except ValueError as exc:
        raise _bad(exc) from exc
    return {"ok": True}


@router.post("/calendar/apple/{connection_id}/claim")
async def claim_apple(connection_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    try:
        return {"actions": await apple.claim(current_user.id, connection_id)}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.put("/calendar/apple/{connection_id}/actions/{action_id}")
async def acknowledge_apple(connection_id: UUID, action_id: UUID, body: AppleActionResult,
                            current_user: CurrentUser = Depends(require_admin_or_client)):
    await apple.acknowledge(current_user.id, connection_id, action_id, body)
    return {"ok": True}

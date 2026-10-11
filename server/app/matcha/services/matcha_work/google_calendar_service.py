"""The person's Google Calendar, on the same Google connection as their Gmail.

Needs the `calendar.events` scope, which is asked for only when the person
switches the assistant's calendar ability on. Works in the API and in a worker.
"""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import httpx

from .gmail_service import GmailService

CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
# The calendar view asks for a whole month; the assistant asks for 25.
MAX_LIST_RESULTS = 250
# Pages followed for one listing. Google can return a short or even empty
# page with more behind it, so a listing follows `nextPageToken`; this bounds
# the round trips.
MAX_LIST_PAGES = 5
_EVENT_ID = re.compile(r"^[A-Za-z0-9_\-]{1,1024}$")


def _check_id(event_id: str) -> str:
    if not _EVENT_ID.fullmatch(event_id or ""):
        raise ValueError("Invalid event id")
    return event_id


def event_view(item: dict) -> dict:
    start, end = item.get("start") or {}, item.get("end") or {}
    return {
        "id": item.get("id"),
        "title": item.get("summary") or "(no title)",
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "all_day": "date" in start and "dateTime" not in start,
        "location": item.get("location"),
        "description": (item.get("description") or "")[:2000],
        "attendees": sorted({
            str(a.get("email")).lower() for a in item.get("attendees") or [] if a.get("email")
        }),
        "organizer": ((item.get("organizer") or {}).get("email") or "").lower() or None,
        "link": item.get("htmlLink"),
    }


def _when(value: str) -> dict:
    """`2026-10-02` is an all-day date; anything longer is an RFC 3339 time."""
    text = (value or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return {"date": text}
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+\-]\d{2}:\d{2})", text):
        raise ValueError("Times must be RFC 3339 with an offset, like 2026-10-02T19:00:00-07:00")
    return {"dateTime": text}


def event_body(*, title: str | None = None, start: str | None = None, end: str | None = None,
               location: str | None = None, description: str | None = None,
               attendees: list[str] | None = None) -> dict:
    body: dict[str, Any] = {}
    if title is not None:
        body["summary"] = title[:300]
    if start is not None:
        body["start"] = _when(start)
    if end is not None:
        body["end"] = _when(end)
    if location is not None:
        body["location"] = location[:300]
    if description is not None:
        body["description"] = description[:4000]
    if attendees is not None:
        body["attendees"] = [{"email": a} for a in attendees]
    return body


class GoogleCalendarService:
    def __init__(self, user_id: UUID, *, gmail: GmailService | None = None) -> None:
        self.user_id = user_id
        self._gmail = gmail or GmailService(user_id)

    async def _headers(self) -> dict:
        return {"Authorization": f"Bearer {await self._gmail.access_token()}"}

    async def _request(self, method: str, path: str, *, params=None, body=None) -> dict:
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method, f"{CALENDAR_API_BASE}{path}", headers=headers,
                params=params, json=body, timeout=30.0,
            )
        response.raise_for_status()
        return response.json() if response.content else {}

    async def list_window(self, *, time_min: str, time_max: str, query: str | None = None,
                          max_results: int = 25) -> tuple[list[dict], bool]:
        """Events in the window, following Google's pages, and whether that is
        all of them. False when `max_results` or `MAX_LIST_PAGES` stopped the
        listing with a page still to read."""
        wanted = max(1, min(int(max_results), MAX_LIST_RESULTS))
        params = {"timeMin": time_min, "timeMax": time_max, "singleEvents": "true", "orderBy": "startTime"}
        if query:
            params["q"] = query[:200]
        events: list[dict] = []
        token = None
        for _ in range(MAX_LIST_PAGES):
            page = {**params, "maxResults": str(wanted - len(events))}
            if token:
                page["pageToken"] = token
            data = await self._request("GET", "/calendars/primary/events", params=page)
            events += [event_view(item) for item in data.get("items") or [] if item.get("status") != "cancelled"]
            token = data.get("nextPageToken")
            if not token:
                return events[:wanted], True
            if len(events) >= wanted:
                return events[:wanted], False
        return events[:wanted], False

    async def list_events(self, *, time_min: str, time_max: str, query: str | None = None,
                          max_results: int = 25) -> list[dict]:
        events, _complete = await self.list_window(
            time_min=time_min, time_max=time_max, query=query, max_results=max_results,
        )
        return events

    async def get_event(self, event_id: str) -> dict:
        return event_view(await self._request("GET", f"/calendars/primary/events/{_check_id(event_id)}"))

    async def create_event(self, body: dict) -> dict:
        notify = "all" if body.get("attendees") else "none"
        return event_view(await self._request(
            "POST", "/calendars/primary/events", params={"sendUpdates": notify}, body=body,
        ))

    async def update_event(self, event_id: str, patch: dict, *, notify: bool) -> dict:
        return event_view(await self._request(
            "PATCH", f"/calendars/primary/events/{_check_id(event_id)}",
            params={"sendUpdates": "all" if notify else "none"}, body=patch,
        ))

    async def delete_event(self, event_id: str, *, notify: bool) -> None:
        await self._request(
            "DELETE", f"/calendars/primary/events/{_check_id(event_id)}",
            params={"sendUpdates": "all" if notify else "none"},
        )

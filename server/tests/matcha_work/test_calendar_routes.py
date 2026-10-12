"""/matcha-work/calendar/* — the Espresso calendar's REST surface.

`calendar.router` is mounted alone; the service calls are patched where the
route module reaches them (`calendar_service`), and Google is a fake patched
into the modules the feed imports it from.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.matcha.dependencies import require_admin_or_client
from app.matcha.routes.work import calendar as routes
from app.matcha.services.matcha_work import calendar_service as cal
from app.matcha.services.matcha_work import gmail_service, google_calendar_service
from tests._helpers.routes import iter_api_routes, route_client

USER = SimpleNamespace(id=uuid4(), role="client", email="owner@example.com")
COMPANY = uuid4()
EVENT = {"id": str(uuid4()), "title": "Dentist", "start": "2026-10-02T15:00:00-07:00",
         "end": "2026-10-02T16:00:00-07:00", "all_day": False}
WINDOW = {"start": "2026-10-01T00:00:00-07:00", "end": "2026-11-01T00:00:00-07:00"}


def _client():
    return route_client(routes.router, overrides={require_admin_or_client: USER})


@pytest.fixture
def svc(monkeypatch):
    fakes = SimpleNamespace(
        get_timezone=AsyncMock(return_value="America/Los_Angeles"),
        list_events=AsyncMock(return_value=[EVENT]),
        list_dated_todos=AsyncMock(return_value=[{"id": "c1", "title": "Renew lease", "due_date": "2026-10-02"}]),
        create_event=AsyncMock(return_value=EVENT),
        get_event=AsyncMock(return_value=EVENT),
        update_event=AsyncMock(return_value=EVENT),
        delete_event=AsyncMock(return_value=True),
        set_timezone=AsyncMock(return_value="America/Los_Angeles"),
    )
    for name, fake in vars(fakes).items():
        monkeypatch.setattr(cal, name, fake)
    monkeypatch.setattr(routes, "get_client_company_id", AsyncMock(return_value=COMPANY))
    monkeypatch.setattr(routes.apple, "feed", AsyncMock(return_value={"status": "not_connected", "events": []}))
    return fakes


def _google(monkeypatch, *, configured=True, scopes=(gmail_service.SCOPE_CALENDAR_EVENTS,),
            events=None, error=None, complete=True):
    gmail = SimpleNamespace(load_token=AsyncMock(), is_configured=configured,
                            granted_scopes=frozenset(scopes))
    monkeypatch.setattr(gmail_service, "GmailService", lambda user_id: gmail)
    seen = {}

    class Calendar:
        def __init__(self, user_id, *, gmail):
            seen["gmail"] = gmail

        async def list_window(self, *, time_min, time_max, max_results):
            seen.update(time_min=time_min, time_max=time_max, max_results=max_results)
            if error:
                raise error
            return events or [], complete

    monkeypatch.setattr(google_calendar_service, "GoogleCalendarService", Calendar)
    return seen


def test_every_calendar_route_requires_admin_or_client():
    wanted = {
        ("GET", "/calendar/feed"), ("POST", "/calendar/events"), ("GET", "/calendar/events/{event_id}"),
        ("PATCH", "/calendar/events/{event_id}"), ("DELETE", "/calendar/events/{event_id}"),
        ("PUT", "/calendar/prefs"),
        ("GET", "/calendar/apple"), ("PUT", "/calendar/apple"),
        ("DELETE", "/calendar/apple/{connection_id}"), ("PUT", "/calendar/apple/snapshot"),
        ("POST", "/calendar/apple/{connection_id}/claim"),
        ("PUT", "/calendar/apple/{connection_id}/actions/{action_id}"),
    }
    found = {}
    for route in iter_api_routes(routes.router):
        for method in getattr(route, "methods", set()) or set():
            found[(method, route.path)] = route
    assert wanted <= set(found)
    for key in wanted:
        assert require_admin_or_client in {d.call for d in found[key].dependant.dependencies}, key


def test_the_feed_merges_events_todos_and_google_with_inclusive_all_day_ends(svc, monkeypatch):
    seen = _google(monkeypatch, events=[
        {"id": "g1", "title": "Offsite", "start": "2026-10-05", "end": "2026-10-07", "all_day": True,
         "attendees": ["a@example.com", "b@example.com"], "link": "https://calendar.google.com/x"},
        {"id": "g2", "title": "Call", "start": "2026-10-06T09:00:00-07:00",
         "end": "2026-10-06T09:30:00-07:00", "all_day": False},
    ])
    with _client() as client:
        resp = client.get("/calendar/feed", params=WINDOW)
    assert resp.status_code == 200
    body = resp.json()
    assert body["timezone"] == "America/Los_Angeles"
    assert body["events"] == [EVENT] and body["todos"][0]["title"] == "Renew lease"
    assert body["google"]["status"] == "ok"
    offsite, call = body["google"]["events"]
    assert offsite["end"] == "2026-10-06" and offsite["attendee_count"] == 2
    assert call["end"] == "2026-10-06T09:30:00-07:00"
    assert seen["max_results"] == routes.GOOGLE_MAX_EVENTS
    user, begin, finish = svc.list_events.await_args.args
    assert user == USER.id and (finish - begin).days == 31
    assert svc.list_events.await_args.kwargs["tz"].key == "America/Los_Angeles"


@pytest.mark.parametrize("setup, status", [
    ({"configured": False}, "not_connected"),
    ({"scopes": ()}, "needs_permission"),
    ({"error": httpx.ConnectError("down")}, "error"),
])
def test_the_feed_says_why_google_is_missing_and_still_answers(svc, monkeypatch, setup, status):
    _google(monkeypatch, **setup)
    with _client() as client:
        body = client.get("/calendar/feed", params=WINDOW).json()
    assert body["google"] == {"status": status, "events": []} and body["events"] == [EVENT]


def test_the_feed_says_partial_when_google_had_more_than_it_read(svc, monkeypatch):
    _google(monkeypatch, events=[{"id": "g1", "title": "Call", "start": "2026-10-06T09:00:00-07:00",
                                  "end": "2026-10-06T09:30:00-07:00", "all_day": False}], complete=False)
    with _client() as client:
        body = client.get("/calendar/feed", params=WINDOW).json()
    assert body["google"]["status"] == "partial" and len(body["google"]["events"]) == 1


def test_the_feed_can_skip_google_and_refuses_a_bad_window(svc, monkeypatch):
    _google(monkeypatch, configured=False)
    with _client() as client:
        skipped = client.get("/calendar/feed", params={**WINDOW, "include_google": "false"}).json()
        bad = client.get("/calendar/feed", params={"start": "2026-10-01", "end": "2026-11-01"})
    assert skipped["google"]["status"] == "skipped"
    assert bad.status_code == 422 and "two times" in bad.json()["detail"]


def test_the_feed_survives_a_google_token_that_cannot_load(svc, monkeypatch):
    gmail = SimpleNamespace(load_token=AsyncMock(side_effect=RuntimeError("decrypt")))
    monkeypatch.setattr(gmail_service, "GmailService", lambda user_id: gmail)
    with _client() as client:
        body = client.get("/calendar/feed", params=WINDOW).json()
    assert body["google"]["status"] == "error"


def test_create_validates_and_records_where_it_came_from(svc):
    with _client() as client:
        made = client.post("/calendar/events", json={
            "title": "Dentist", "start": "2026-10-02T15:00:00-07:00",
            "source_kind": "email", "source_ref": "18c3f0a1b2c3", "source_label": "Your appointment"})
        bad = client.post("/calendar/events", json={"title": "Dentist", "start": "friday"})
        claimed = client.post("/calendar/events", json={
            "title": "x", "start": "2026-10-02", "source_kind": "assistant"})
    assert made.status_code == 201 and made.json() == EVENT
    user, company, fields = svc.create_event.await_args.args
    assert (user, company, fields["title"]) == (USER.id, COMPANY, "Dentist")
    assert svc.create_event.await_args.kwargs["source_kind"] == "email"
    assert svc.create_event.await_args.kwargs["source_ref"] == "18c3f0a1b2c3"
    assert bad.status_code == 422 and "RFC 3339" in bad.json()["detail"]
    assert claimed.status_code == 422  # only the assistant writes `assistant`
    assert svc.create_event.await_count == 1


def test_patch_sends_only_what_was_set(svc):
    event_id = uuid4()
    with _client() as client:
        ok = client.patch(f"/calendar/events/{event_id}", json={"start": "2026-10-03T09:00:00-07:00",
                                                                "location": None})
    assert ok.status_code == 200
    assert svc.update_event.await_args.args == (event_id, USER.id, {
        "start": "2026-10-03T09:00:00-07:00", "location": None})
    svc.update_event.side_effect = ValueError("An event cannot end before it starts.")
    with _client() as client:
        bad = client.patch(f"/calendar/events/{event_id}", json={"end": "2026-10-01T00:00:00Z"})
    assert bad.status_code == 422 and "before it starts" in bad.json()["detail"]
    svc.update_event.side_effect = None
    svc.update_event.return_value = None
    with _client() as client:
        assert client.patch(f"/calendar/events/{event_id}", json={"title": "x"}).status_code == 404


def test_get_and_delete_answer_404_for_someone_elses_event(svc):
    event_id = uuid4()
    with _client() as client:
        assert client.get(f"/calendar/events/{event_id}").status_code == 200
        assert client.delete(f"/calendar/events/{event_id}").status_code == 204
        svc.get_event.return_value = None
        svc.delete_event.return_value = False
        assert client.get(f"/calendar/events/{event_id}").status_code == 404
        assert client.delete(f"/calendar/events/{event_id}").status_code == 404
    assert svc.delete_event.await_args.args == (event_id, USER.id)


def test_prefs_store_a_real_zone_and_refuse_anything_else(svc):
    with _client() as client:
        ok = client.put("/calendar/prefs", json={"timezone": "America/Los_Angeles"})
        svc.set_timezone.side_effect = ValueError("Not a timezone name (like America/Los_Angeles).")
        bad = client.put("/calendar/prefs", json={"timezone": "Pacific"})
    assert ok.json() == {"timezone": "America/Los_Angeles"}
    assert bad.status_code == 422


def test_apple_failure_does_not_blank_the_persons_calendar(svc, monkeypatch):
    _google(monkeypatch, configured=False)
    monkeypatch.setattr(routes.apple, "feed", AsyncMock(side_effect=RuntimeError("Mac offline")))
    with _client() as client:
        body = client.get("/calendar/feed", params=WINDOW).json()
    assert body["events"] == [EVENT] and body["apple"] == {"status": "error", "events": []}


def test_feed_includes_selected_apple_events_and_sync_status(svc, monkeypatch):
    _google(monkeypatch, configured=False)
    feed = {"status": "stale", "events": [{"id": "a1", "title": "Focus"}], "synced_at": "2026-10-01T00:00:00Z"}
    monkeypatch.setattr(routes.apple, "feed", AsyncMock(return_value=feed))
    with _client() as client:
        body = client.get("/calendar/feed", params=WINDOW).json()
    assert body["apple"] == feed
    assert routes.apple.feed.await_args.args[0] == USER.id

from datetime import date
from uuid import uuid4

import httpx
import pytest

from app.matcha.services.matcha_work import calendar_service
from app.matcha.services.matcha_work import google_calendar_service as gcal
from app.matcha.services.matcha_work.agent_runtime import result, runner
from app.matcha.services.matcha_work.agent_runtime.abilities import calendar
from app.matcha.services.matcha_work.agent_runtime.policy import Grounding, PolicyContext
from app.matcha.services.matcha_work.gmail_service import SCOPE_CALENDAR_EVENTS

from .helpers import FakeClient, FakeConn, call, connection, context, response, wire_store

SCOPES = frozenset({SCOPE_CALENDAR_EVENTS})
START, END = "2026-10-02T15:00:00-07:00", "2026-10-02T16:00:00-07:00"


def _event(id_="evt-0001", attendees=("dana@example.org",), **over):
    base = {"id": id_, "title": "Design review", "start": START, "end": END, "all_day": False,
            "location": "Room 2", "description": "Agenda", "attendees": list(attendees),
            "organizer": "me@example.com", "link": "https://calendar.google.com/event?eid=1"}
    base.update(over)
    return base


class FakeCalendar:
    def __init__(self, events=None):
        self.events = list(events if events is not None else [_event()])
        self.created, self.updated, self.deleted = [], [], []
        self.error = None

    async def list_events(self, *, time_min, time_max, query=None, max_results=25):
        if self.error:
            raise self.error
        self.window = (time_min, time_max, query)
        return self.events

    async def create_event(self, body):
        if self.error:
            raise self.error
        self.created.append(body)
        return _event("evt-new", attendees=[a["email"] for a in body.get("attendees", [])],
                      title=body["summary"])

    async def update_event(self, event_id, patch, *, notify):
        self.updated.append((event_id, patch, notify))
        return _event(event_id)

    async def delete_event(self, event_id, *, notify):
        self.deleted.append((event_id, notify))


def _ability(cal, reminders=None):
    async def insert(user_id, company_id, title, due):
        (reminders if reminders is not None else []).append((title, due))
        return "card-1"

    return calendar.build(calendar_factory=lambda ctx: cal, insert_reminder=insert)


def _ctx(*texts, scopes=SCOPES, **over):
    return context(
        granted_scopes=scopes, commit_mode="live",
        policy=PolicyContext(surface="assistant", private_conversation=True,
                             grounding=Grounding(user_texts=texts, own_addresses=frozenset({"me@example.com"}))),
        **over,
    )


async def run(client, cal, ctx, reminders=None):
    ability = _ability(cal, reminders)
    return await runner.run_agent(
        ctx, client=client, abilities=[ability],
        contract=runner.ResultContract(
            finish=result.finish_tool([ability]),
            normalize=lambda args, state: result.normalize(args, state, [ability]),
        ),
        instructions="sys", first_input=[],
    )


FINISH = {"headline": "Done", "summary": "Handled."}
LIST = call("list_events", {"time_min": "2026-10-01T00:00:00-07:00", "time_max": "2026-10-08T00:00:00-07:00"})


@pytest.mark.asyncio
async def test_an_event_with_no_attendees_is_allowed(monkeypatch):
    wire_store(monkeypatch)
    cal = FakeCalendar()
    client = FakeClient([
        response(call("create_event", {"title": "Focus time", "start": START, "end": END, "location": "Home"})),
        response(call("finish", {**FINISH, "blocks": [{"type": "events", "event_ids": ["evt-new", "ghost"]}]})),
    ])
    out = await run(client, cal, _ctx("block focus time friday at 3"))
    assert out.kind == "result"
    assert cal.created == [{"summary": "Focus time", "start": {"dateTime": START},
                            "end": {"dateTime": END}, "location": "Home"}]
    assert out.receipts[0]["link"] == {"label": "Open in Calendar",
                                       "url": "https://calendar.google.com/event?eid=1"}
    assert out.result["blocks"][0]["items"][0]["event_id"] == "evt-new"
    assert any("never saw" in w for w in out.warnings)


@pytest.mark.asyncio
async def test_an_invitee_the_user_never_named_is_held(monkeypatch):
    wire_store(monkeypatch)
    cal = FakeCalendar()
    client = FakeClient([response(call("create_event", {
        "title": "Sync", "start": START, "end": END, "attendees": ["Eve@Attacker.test"]}))])
    out = await run(client, cal, _ctx("set up a sync on friday"))
    assert out.kind == "confirmation" and cal.created == []
    assert out.pending.args["attendees"] == ["eve@attacker.test"]
    assert {"label": "Invites", "value": "eve@attacker.test"} in out.pending.preview["lines"]


@pytest.mark.asyncio
async def test_an_invitee_the_user_named_is_invited(monkeypatch):
    wire_store(monkeypatch)
    cal = FakeCalendar()
    client = FakeClient([
        response(call("create_event", {"title": "Sync", "start": START, "end": END,
                                       "attendees": ["dana@example.org"]})),
        response(call("finish", FINISH)),
    ])
    out = await run(client, cal, _ctx("set up a sync with dana@example.org on friday"))
    assert out.kind == "result" and cal.created[0]["attendees"] == [{"email": "dana@example.org"}]


@pytest.mark.asyncio
async def test_changing_an_event_holds_for_attendees_the_user_did_not_point_at(monkeypatch):
    wire_store(monkeypatch)
    cal = FakeCalendar()
    client = FakeClient([response(LIST),
                         response(call("update_event", {"event_id": "evt-0001", "start": START, "end": END}))])
    out = await run(client, cal, _ctx("move my design review to 3"))
    assert out.kind == "confirmation" and cal.updated == []
    assert out.pending.args["existing_attendees"] == ["dana@example.org"]
    assert {"label": "Notifies", "value": "dana@example.org"} in out.pending.preview["lines"]


@pytest.mark.asyncio
async def test_updating_an_event_the_user_pointed_at_grounds_its_attendees(monkeypatch):
    wire_store(monkeypatch)
    cal = FakeCalendar()
    client = FakeClient([
        response(LIST),
        response(call("update_event", {"event_id": "evt-0001", "title": "Design review v2",
                                       "location": "Room 4", "add_attendees": ["sam@example.net"]})),
        response(call("finish", FINISH)),
    ])
    out = await run(client, cal, _ctx("rename event evt-0001 and add sam@example.net"))
    # The event was pointed at by its id, and the new attendee was typed.
    assert out.kind == "result"
    assert cal.updated == [("evt-0001", {
        "summary": "Design review v2", "location": "Room 4",
        "attendees": [{"email": "dana@example.org"}, {"email": "sam@example.net"}]}, True)]


@pytest.mark.asyncio
async def test_deleting_tells_everyone_on_the_event(monkeypatch):
    wire_store(monkeypatch)
    cal = FakeCalendar([_event(attendees=())])
    client = FakeClient([response(LIST), response(call("delete_event", {"event_id": "evt-0001"})),
                         response(call("finish", FINISH))])
    out = await run(client, cal, _ctx("cancel my design review"))
    assert out.kind == "result" and cal.deleted == [("evt-0001", False)]
    held = await run(FakeClient([response(LIST), response(call("delete_event", {"event_id": "evt-0001"}))]),
                     FakeCalendar(), _ctx("cancel my design review"))
    assert held.kind == "confirmation"
    assert held.pending.preview["title"] == "Delete a calendar event"


@pytest.mark.asyncio
async def test_unusable_event_arguments_are_refused(monkeypatch):
    _, claim, _ = wire_store(monkeypatch)
    cal = FakeCalendar()
    bad = [
        call("create_event", {"title": "No times"}),
        call("create_event", {"title": "Bad time", "start": "friday 3pm", "end": END}),
        call("create_event", {"title": "Bad guest", "start": START, "end": END, "attendees": ["nope"]}),
        call("create_event", {"title": "Crowd", "start": START, "end": END,
                              "attendees": [f"p{i}@example.com" for i in range(21)]}),
        call("update_event", {"event_id": "never-listed", "title": "x"}),
        call("delete_event", {"event_id": "never-listed"}),
    ]
    client = FakeClient([response(LIST), response(*bad),
                         response(call("update_event", {"event_id": "evt-0001"})),
                         response(call("finish", FINISH))])
    await run(client, cal, _ctx("rearrange things"))
    assert all("not usable" in item["output"] for item in client.calls[2]["input"])
    assert "nothing to change" in client.calls[3]["input"][0]["output"]
    assert claim.await_count == 0


@pytest.mark.asyncio
async def test_add_reminder_writes_only_the_requesters_board(monkeypatch):
    _, claim, _ = wire_store(monkeypatch)
    reminders = []
    client = FakeClient([
        response(call("add_reminder", {"title": "  Renew   lease ", "date": "2026-10-02"}),
                 call("add_reminder", {"title": "Bad", "date": "next week"}),
                 call("add_reminder", {"title": "Bad", "date": "2026-02-31"})),
        response(call("finish", FINISH)),
    ])
    out = await run(client, FakeCalendar(), _ctx("remind me to renew the lease", scopes=frozenset()),
                    reminders)
    assert reminders == [("Renew lease", date(2026, 10, 2))]
    outputs = [item["output"] for item in client.calls[1]["input"]]
    assert '"card_id":"card-1"' in outputs[0]
    assert "needs a title and a date" in outputs[1] and "does not exist" in outputs[2]
    # A reminder involves nobody else: it is not a commit and is never held.
    assert out.kind == "result" and claim.await_count == 0


class _Row(dict):
    def keys(self):
        return list(super().keys())


@pytest.mark.asyncio
async def test_the_reminder_insert_is_the_requesters_own_default_board(monkeypatch):
    from app.matcha.services.matcha_work import productivity_service

    user, company, board, card = uuid4(), uuid4(), uuid4(), uuid4()
    row = _Row({"id": card, "board_id": board, "title": "Renew lease", "notes": None, "board_column": "todo",
            "position": 3, "due_date": date(2026, 10, 2), "source_journal_id": None, "source_excerpt": None,
            "completed_at": None, "created_at": None, "updated_at": None})
    conn = FakeConn([("SELECT id FROM mw_productivity_boards", board), ("COALESCE(MAX(position)", 3),
                     ("INSERT INTO mw_productivity_cards", row)])
    monkeypatch.setattr(productivity_service, "connection_or_direct", connection(conn))
    assert await calendar._insert_reminder(user, company, "Renew lease", date(2026, 10, 2)) == str(card)
    assert conn.ran("SELECT id FROM mw_productivity_boards")[0][2] == (user,)
    assert conn.ran("INSERT INTO mw_productivity_cards")[0][2][:5] == (
        board, user, "Renew lease", 3, date(2026, 10, 2))
    assert conn.ran("INSERT INTO mw_productivity_boards") == []

    fresh = FakeConn([("SELECT id FROM mw_productivity_boards", None),
                      ("INSERT INTO mw_productivity_boards", board),
                      ("INSERT INTO mw_productivity_cards", row)])
    monkeypatch.setattr(productivity_service, "connection_or_direct", connection(fresh))
    await calendar._insert_reminder(user, company, "Renew lease", date(2026, 10, 2))
    assert fresh.ran("INSERT INTO mw_productivity_boards")[0][2] == (user, company)


@pytest.mark.asyncio
async def test_without_the_calendar_scope_only_the_espresso_calendar_is_offered(monkeypatch):
    wire_store(monkeypatch)
    client = FakeClient([response(call("finish", FINISH))])
    await run(client, FakeCalendar(), _ctx("what is on friday", scopes=frozenset()))
    assert [t["name"] for t in client.calls[0]["tools"]] == [
        "list_espresso_events", "add_espresso_event", "update_espresso_event", "delete_espresso_event",
        "add_reminder", "finish",
    ]


@pytest.mark.asyncio
async def test_google_refusals_and_lost_connections(monkeypatch):
    _, _, resolve = wire_store(monkeypatch)
    refused = httpx.HTTPStatusError("403", request=httpx.Request("GET", "https://x.example"),
                                    response=httpx.Response(403))
    cal = FakeCalendar()
    cal.error = refused
    client = FakeClient([
        response(LIST, call("create_event", {"title": "Solo", "start": START, "end": END})),
        response(call("finish", FINISH)),
    ])
    out = await run(client, cal, _ctx("add solo time"))
    assert "HTTP 403" in client.calls[1]["input"][0]["output"]
    assert out.receipts[0]["status"] == "failed"
    cal.error = httpx.ReadTimeout("no answer")
    client = FakeClient([response(call("create_event", {"title": "Solo", "start": START, "end": END})),
                         response(call("finish", FINISH))])
    out = await run(client, cal, _ctx("add solo time"))
    assert out.receipts[0]["status"] == "unknown" and resolve.await_args.kwargs["status"] == "unknown"


# ── the Google Calendar client ─────────────────────────────────────────────

def test_event_bodies_and_views():
    assert gcal.event_body(title="T", start="2026-10-02", end="2026-10-03") == {
        "summary": "T", "start": {"date": "2026-10-02"}, "end": {"date": "2026-10-03"}}
    assert gcal.event_body(start="2026-10-02T15:00:00Z")["start"] == {"dateTime": "2026-10-02T15:00:00Z"}
    for bad in ("tomorrow", "2026-10-02T15:00:00", "2026-10-02 15:00"):
        with pytest.raises(ValueError, match="RFC 3339"):
            gcal.event_body(start=bad)
    view = gcal.event_view({
        "id": "e1", "start": {"date": "2026-10-02"}, "end": {"date": "2026-10-03"},
        "attendees": [{"email": "Dana@Example.org"}, {"displayName": "no address"}],
        "organizer": {"email": "Me@Example.com"}, "htmlLink": "https://calendar.google.com/x"})
    assert view["title"] == "(no title)" and view["all_day"] and view["attendees"] == ["dana@example.org"]
    assert view["organizer"] == "me@example.com"
    for bad in ("", "has space", "a/b"):
        with pytest.raises(ValueError, match="Invalid event id"):
            gcal._check_id(bad)


@pytest.mark.asyncio
async def test_the_calendar_client_notifies_only_when_there_are_attendees(monkeypatch):
    sent = []

    class Gmail:
        async def access_token(self):
            return "token"

    service = gcal.GoogleCalendarService(uuid4(), gmail=Gmail())

    async def request(method, path, *, params=None, body=None):
        sent.append((method, path, params, body))
        return {"id": "e1", "items": [{"id": "e1"}, {"id": "gone", "status": "cancelled"}]}

    monkeypatch.setattr(service, "_request", request)
    await service.create_event({"summary": "Solo"})
    await service.create_event({"summary": "Group", "attendees": [{"email": "dana@example.org"}]})
    await service.update_event("e1", {"summary": "x"}, notify=False)
    await service.delete_event("e1", notify=True)
    await service.get_event("e1")
    events = await service.list_events(time_min=START, time_max=END, query="review", max_results=500)
    assert [s[2].get("sendUpdates") for s in sent[:4]] == ["none", "all", "none", "all"]
    assert [e["id"] for e in events] == ["e1"]
    assert sent[5][2]["maxResults"] == "250" and sent[5][2]["q"] == "review"
    assert await service._headers() == {"Authorization": "Bearer token"}


@pytest.mark.asyncio
async def test_listing_follows_googles_pages_and_says_when_it_stopped_short(monkeypatch):
    service = gcal.GoogleCalendarService(uuid4(), gmail=object())
    pages = [
        # Google may answer with an empty page and more behind it.
        {"items": [], "nextPageToken": "p2"},
        {"items": [{"id": "e1"}, {"id": "gone", "status": "cancelled"}], "nextPageToken": "p3"},
        {"items": [{"id": "e2"}]},
    ]
    sent = []

    async def request(method, path, *, params=None, body=None):
        sent.append(dict(params))
        return pages[len(sent) - 1]

    monkeypatch.setattr(service, "_request", request)
    events, complete = await service.list_window(time_min=START, time_max=END, max_results=50)
    assert [e["id"] for e in events] == ["e1", "e2"] and complete
    assert [s.get("pageToken") for s in sent] == [None, "p2", "p3"]
    assert [s["maxResults"] for s in sent] == ["50", "50", "49"]
    sent.clear()
    # The assistant's list_events reads through the same pages.
    assert [e["id"] for e in await service.list_events(time_min=START, time_max=END)] == ["e1", "e2"]

    endless = []

    async def always_more(method, path, *, params=None, body=None):
        endless.append(params)
        return {"items": [{"id": f"e{len(endless)}"}], "nextPageToken": "more"}

    monkeypatch.setattr(service, "_request", always_more)
    events, complete = await service.list_window(time_min=START, time_max=END, max_results=250)
    assert not complete and len(endless) == gcal.MAX_LIST_PAGES and len(events) == gcal.MAX_LIST_PAGES
    endless.clear()
    events, complete = await service.list_window(time_min=START, time_max=END, max_results=2)
    assert not complete and len(events) == 2 and len(endless) == 2


# ── the Espresso calendar ──────────────────────────────────────────────────

ESPRESSO_ID = "6f1c0d7e-8b9a-4c3d-9e2f-1a2b3c4d5e6f"


def _mine(id_=ESPRESSO_ID, **over):
    base = {"id": id_, "title": "Dentist", "start": START, "end": END, "all_day": False,
            "location": None, "notes": None, "source_kind": "manual", "source_ref": None,
            "source_label": None}
    base.update(over)
    return base


class FakeStore:
    def __init__(self, events=None):
        self.events = list(events if events is not None else [_mine()])
        self.created, self.updated, self.deleted, self.listed = [], [], [], []

    async def list_events(self, user_id, begin, finish, *, tz=None, query=None):
        self.listed.append((begin, finish, tz, query))
        return self.events

    async def list_dated_todos(self, user_id, first_day, last_day):
        return [{"title": "Renew lease", "due_date": "2026-10-02", "board_column": "todo"},
                {"title": "Old task", "due_date": "2026-10-03", "board_column": "done"}]

    async def create_event(self, user_id, company_id, fields, *, source_kind, source_ref, source_label, tz):
        self.created.append((fields, source_kind, source_ref, source_label, tz))
        return _mine("7a2b3c4d-0000-4000-8000-000000000001", title=fields["title"],
                     source_kind=source_kind, source_ref=source_ref, source_label=source_label)

    async def update_event(self, event_id, user_id, patch, *, tz):
        self.updated.append((str(event_id), patch))
        if patch.get("start") == "gone":
            return None
        if patch.get("end") == "2000-01-01T00:00:00Z":
            raise ValueError("An event cannot end before it starts.")
        return _mine(str(event_id), **{k: v for k, v in patch.items() if k == "title"})

    async def delete_event(self, event_id, user_id):
        self.deleted.append(str(event_id))
        return True


class _Mail:
    def __init__(self, messages):
        self.messages = messages


async def run_espresso(client, store, ctx, sessions=None):
    abilities = [calendar.build(calendar_factory=lambda ctx: FakeCalendar(), espresso_store=store)]
    if sessions:
        # Stands in for the email ability: only its session (what the run read) matters here.
        abilities.append(calendar.Ability(key="email", label="Email", tools=(), prompt_block=lambda c: "",
                                          session_factory=lambda c: _Mail(sessions)))
    return await runner.run_agent(
        ctx, client=client, abilities=abilities,
        contract=runner.ResultContract(
            finish=result.finish_tool(abilities),
            normalize=lambda args, state: result.normalize(args, state, abilities),
        ),
        instructions="sys", first_input=[],
    )


@pytest.mark.asyncio
async def test_adding_to_the_espresso_calendar_is_never_held_and_shows_as_an_event(monkeypatch):
    _, claim, _ = wire_store(monkeypatch)
    store = FakeStore()
    client = FakeClient([
        response(call("add_espresso_event", {"title": "Dentist", "start": START, "location": "Main St"})),
        response(call("finish", {**FINISH, "blocks": [{"type": "events",
                                                       "event_ids": ["7a2b3c4d-0000-4000-8000-000000000001"]}]})),
    ])
    out = await run_espresso(client, store, _ctx("put the dentist on my calendar friday at 3",
                                                 scopes=frozenset(), timezone="America/Los_Angeles"))
    assert out.kind == "result" and claim.await_count == 0
    fields, kind, ref, label, tz = store.created[0]
    assert fields["title"] == "Dentist" and fields["location"] == "Main St"
    assert fields["ends_at"] - fields["starts_at"] == calendar_service.DEFAULT_LENGTH
    assert (kind, ref, label) == ("assistant", None, None) and tz.key == "America/Los_Angeles"
    item = out.result["blocks"][0]["items"][0]
    assert item["calendar"] == "espresso" and item["title"] == "Dentist"


@pytest.mark.asyncio
async def test_a_result_written_beside_an_add_waits_for_the_adds_outcome(monkeypatch):
    wire_store(monkeypatch)
    store = FakeStore()
    client = FakeClient([
        # The add fails (no such date) and the model already claims success.
        response(call("add_espresso_event", {"title": "Dentist", "start": "2026-02-31"}),
                 call("finish", {"headline": "Dentist added", "summary": "Done."})),
        response(call("finish", {"headline": "Couldn't add it", "summary": "That date does not exist."})),
    ])
    out = await run_espresso(client, store, _ctx("add the dentist on feb 31", scopes=frozenset()))
    outputs = [item["output"] for item in client.calls[1]["input"]]
    assert "does not exist" in outputs[0] and "Not accepted" in outputs[1]
    assert out.result["headline"] == "Couldn't add it" and store.created == []


@pytest.mark.asyncio
async def test_an_event_from_an_email_links_back_only_to_an_email_the_run_read(monkeypatch):
    wire_store(monkeypatch)
    store = FakeStore()
    client = FakeClient([
        response(call("add_espresso_event", {"title": "Dinner", "start": "2026-10-09",
                                             "from_email_id": "never-read"}),
                 call("add_espresso_event", {"title": "Dinner", "start": "2026-10-09",
                                             "from_email_id": "18c3f0a1b2c3"}),
                 call("add_espresso_event", {"title": "Bad", "start": "next friday"})),
        response(call("finish", FINISH)),
    ])
    await run_espresso(client, store, _ctx("add the dinner from dana's email", scopes=frozenset()),
                       sessions={"18c3f0a1b2c3": {"id": "18c3f0a1b2c3", "subject": "Dinner Friday?"}})
    outputs = [item["output"] for item in client.calls[1]["input"]]
    assert "an email this run read" in outputs[0] and "RFC 3339" in outputs[2]
    assert [(c[1], c[2], c[3]) for c in store.created] == [("email", "18c3f0a1b2c3", "Dinner Friday?")]


@pytest.mark.asyncio
async def test_listing_then_moving_and_removing_espresso_events(monkeypatch):
    _, claim, _ = wire_store(monkeypatch)
    store = FakeStore()
    window = {"time_min": "2026-10-01T00:00:00-07:00", "time_max": "2026-10-08T00:00:00-07:00"}
    client = FakeClient([
        response(call("update_espresso_event", {"event_id": ESPRESSO_ID, "title": "x"}),
                 call("list_espresso_events", {"time_min": "2026-10-01", "time_max": "2026-10-08"})),
        response(call("list_espresso_events", {**window, "query": "lease"})),
        response(call("update_espresso_event", {"event_id": ESPRESSO_ID, "start": "2026-10-02T16:00:00-07:00"}),
                 call("update_espresso_event", {"event_id": ESPRESSO_ID}),
                 call("update_espresso_event", {"event_id": ESPRESSO_ID, "end": "2000-01-01T00:00:00Z"}),
                 call("delete_espresso_event", {"event_id": ESPRESSO_ID})),
        response(call("finish", FINISH)),
    ])
    out = await run_espresso(client, store, _ctx("move my dentist to 4 and then cancel it", scopes=frozenset()))
    assert out.kind == "result" and claim.await_count == 0
    first = [item["output"] for item in client.calls[1]["input"]]
    assert "list the events first" in first[0] and "two times" in first[1]
    listed = client.calls[2]["input"][0]["output"]
    assert '"Renew lease"' in listed and "Old task" not in listed  # the query filters to-dos too
    assert store.listed[0][3] == "lease"
    third = [item["output"] for item in client.calls[3]["input"]]
    assert '"ok":true' in third[0] and "nothing to change" in third[1] and "before it starts" in third[2]
    assert '"deleted"' in third[3]
    assert store.updated[0] == (ESPRESSO_ID, {"start": "2026-10-02T16:00:00-07:00"})
    assert store.deleted == [ESPRESSO_ID]


@pytest.mark.asyncio
async def test_an_event_that_vanished_mid_run_is_reported_and_forgotten(monkeypatch):
    wire_store(monkeypatch)
    store = FakeStore()
    window = {"time_min": "2026-10-01T00:00:00-07:00", "time_max": "2026-10-08T00:00:00-07:00"}
    client = FakeClient([
        response(call("list_espresso_events", window)),
        response(call("update_espresso_event", {"event_id": ESPRESSO_ID, "start": "gone"})),
        response(call("delete_espresso_event", {"event_id": ESPRESSO_ID})),
        response(call("finish", FINISH)),
    ])
    await run_espresso(client, store, _ctx("move it", scopes=frozenset()))
    assert "no longer on the calendar" in client.calls[2]["input"][0]["output"]
    assert "list the events first" in client.calls[3]["input"][0]["output"]
    assert store.deleted == []


def test_the_prompt_names_the_default_calendar_their_zone_and_google_only_when_connected():
    with_google = calendar.prompt_block(_ctx("x", timezone="America/Los_Angeles"))
    assert "They are in America/Los_Angeles" in with_google
    assert "only Google sends invitations" in with_google and "means here" in with_google
    without = calendar.prompt_block(_ctx("x", scopes=frozenset(), timezone="Nowhere/Zone"))
    assert "not connected" in without and "if you cannot tell their timezone, ask" in without


def test_the_system_prompt_gives_the_local_time_when_the_zone_is_known():
    from datetime import datetime, timezone as _tz

    from app.matcha.services.matcha_work.agent_runtime.prompt import build_system_prompt

    now = datetime(2026, 10, 10, 23, 2, tzinfo=_tz.utc)
    local = build_system_prompt(_ctx("x", timezone="America/Los_Angeles"), [], now=now)
    assert "time is 23:02 UTC" in local
    assert "For them it is Saturday, 2026-10-10 16:02 in America/Los_Angeles (UTC-07:00)" in local
    assert "For them" not in build_system_prompt(_ctx("x"), [], now=now)
    assert "For them" not in build_system_prompt(_ctx("x", timezone="Mars/Olympus"), [], now=now)

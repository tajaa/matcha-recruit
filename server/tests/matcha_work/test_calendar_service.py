"""calendar_service — the Espresso calendar's rules and its queries.

Nothing here opens a connection: the queries run against the scripted
`FakeConn` from the agent-runtime helpers.
"""
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import asyncpg
import pytest

from app.matcha.services.matcha_work import calendar_service as cal
from tests.agent_runtime.helpers import FakeConn, connection

LA = ZoneInfo("America/Los_Angeles")
USER, COMPANY = uuid4(), uuid4()


def _row(**over):
    base = {
        "id": uuid4(), "title": "Dentist", "notes": None, "location": "Main St",
        "all_day": False,
        "starts_at": datetime(2026, 10, 2, 22, 0, tzinfo=timezone.utc),
        "ends_at": datetime(2026, 10, 2, 23, 0, tzinfo=timezone.utc),
        "start_date": None, "end_date": None,
        "source_kind": "manual", "source_ref": None, "source_label": None,
        "created_at": datetime(2026, 10, 1, tzinfo=timezone.utc), "updated_at": None,
    }
    base.update(over)
    return base


# ── validation ───────────────────────────────────────────────────────────

def test_a_timed_event_without_an_end_lasts_an_hour():
    fields = cal.event_fields(title="  Dentist   visit ", start="2026-10-02T15:00:00-07:00",
                              location="  ", notes="  bring forms ")
    assert fields["title"] == "Dentist visit" and not fields["all_day"]
    assert fields["ends_at"] - fields["starts_at"] == timedelta(hours=1)
    assert fields["location"] is None and fields["notes"] == "bring forms"
    assert fields["start_date"] is None and fields["end_date"] is None


def test_an_all_day_event_without_an_end_is_one_day():
    fields = cal.event_fields(title="Offsite", start="2026-10-05")
    assert fields["all_day"] and fields["start_date"] == fields["end_date"] == date(2026, 10, 5)
    assert fields["starts_at"] is None
    trip = cal.event_fields(title="Trip", start="2026-10-05", end="2026-10-07")
    assert trip["end_date"] == date(2026, 10, 7)


@pytest.mark.parametrize("kwargs, message", [
    ({"title": " ", "start": "2026-10-05"}, "needs a title"),
    ({"title": "x", "start": ""}, "needs a start"),
    ({"title": "x", "start": "friday 3pm"}, "RFC 3339"),
    ({"title": "x", "start": "2026-10-02T15:00:00"}, "RFC 3339"),  # no offset
    ({"title": "x", "start": "2026-02-31"}, "does not exist"),
    ({"title": "x", "start": "2026-10-02T15:00:00Z", "end": "2026-10-03"}, "ends at a time"),
    ({"title": "x", "start": "2026-10-02", "end": "2026-10-03T10:00:00Z"}, "ends on a date"),
    ({"title": "x", "start": "2026-10-02T15:00:00Z", "end": "2026-10-02T14:00:00Z"}, "before it starts"),
    ({"title": "x", "start": "2026-10-05", "end": "2026-10-04"}, "before it starts"),
    ({"title": "x", "start": "2026-10-01", "end": "2026-12-01"}, "at most 31 days"),
    ({"title": "x", "start": "2026-10-01T00:00:00Z", "end": "2026-12-01T00:00:00Z"}, "at most 31 days"),
])
def test_unusable_events_are_refused_in_words_a_person_can_read(kwargs, message):
    with pytest.raises(ValueError, match=message):
        cal.event_fields(**kwargs)


def test_lengths_are_elapsed_time_across_a_dst_change():
    # 01:30 on the night Los Angeles falls back: an hour later is 01:30 again,
    # an hour behind. Wall-clock arithmetic on the ZoneInfo would say 02:30 PST.
    fields = cal.event_fields(title="Late call", start=datetime(2026, 11, 1, 1, 30, tzinfo=LA))
    assert fields["ends_at"] - fields["starts_at"] == timedelta(hours=1)
    assert cal.render_when(fields["ends_at"], LA) == "2026-11-01T01:30:00-08:00"
    # 00:30 PDT to 01:15 PST is 1h45 elapsed, though 45 minutes on the clock.
    span = cal.event_fields(title="x", start=datetime(2026, 11, 1, 0, 30, tzinfo=LA),
                            end=datetime(2026, 11, 1, 1, 15, fold=1, tzinfo=LA))
    assert span["ends_at"] - span["starts_at"] == timedelta(hours=1, minutes=45)
    with pytest.raises(ValueError, match="before it starts"):
        cal.event_fields(title="x", start=datetime(2026, 11, 1, 1, 30, fold=1, tzinfo=LA),
                         end=datetime(2026, 11, 1, 1, 45, fold=0, tzinfo=LA))
    moved = cal.merged_fields(_row(), {"start": "2026-11-01T01:30:00-07:00"})
    assert moved["ends_at"] - moved["starts_at"] == timedelta(hours=1)


def test_parse_when_takes_objects_and_refuses_a_naive_time():
    moment = datetime(2026, 10, 2, 15, tzinfo=LA)
    assert cal.parse_when(moment) is moment
    assert cal.parse_when(date(2026, 10, 2)) == date(2026, 10, 2)
    with pytest.raises(ValueError, match="RFC 3339"):
        cal.parse_when(datetime(2026, 10, 2, 15))


def test_moving_the_start_keeps_the_length_and_switching_kind_starts_over():
    row = _row()
    moved = cal.merged_fields(row, {"start": "2026-10-03T09:00:00-07:00"})
    assert moved["ends_at"] - moved["starts_at"] == timedelta(hours=1)
    assert moved["title"] == "Dentist" and moved["location"] == "Main St"
    to_all_day = cal.merged_fields(row, {"start": "2026-10-04"})
    assert to_all_day["all_day"] and to_all_day["end_date"] == date(2026, 10, 4)
    longer = cal.merged_fields(row, {"end": "2026-10-02T23:30:00Z"})
    assert longer["starts_at"] == row["starts_at"]
    cleared = cal.merged_fields(row, {"location": None, "notes": "x", "title": "Dentist (moved)"})
    assert cleared["location"] is None and cleared["notes"] == "x" and cleared["title"] == "Dentist (moved)"
    trip = _row(all_day=True, starts_at=None, ends_at=None,
                start_date=date(2026, 10, 5), end_date=date(2026, 10, 7))
    assert cal.merged_fields(trip, {"start": "2026-10-12"})["end_date"] == date(2026, 10, 14)
    with pytest.raises(ValueError, match="needs a title"):
        cal.merged_fields(row, {"title": ""})


def test_windows_are_two_times_at_most_100_days_apart():
    begin, finish = cal.window("2026-10-01T00:00:00-07:00", "2026-11-01T00:00:00-07:00")
    assert cal.days_touched(begin, finish) == (date(2026, 10, 1), date(2026, 10, 31))
    for bad, message in [
        (("2026-10-01", "2026-11-01"), "two times"),
        (("2026-10-02T00:00:00Z", "2026-10-01T00:00:00Z"), "end after"),
        (("2026-01-01T00:00:00Z", "2026-06-01T00:00:00Z"), "100 days"),
    ]:
        with pytest.raises(ValueError, match=message):
            cal.window(*bad)


def test_zone_accepts_only_real_iana_names():
    assert cal.zone("America/Los_Angeles") == LA
    for bad in (None, "", "America", "../etc/passwd", "Not/AZone", "x" * 65, True, 7, ["UTC"], {"tz": "UTC"}):
        assert cal.zone(bad) is None


def test_the_wire_shape_writes_times_in_the_zone_asked_for():
    row = _row(source_kind="email", source_ref="18c3f0a1b2c3", source_label="Your appointment")
    utc = cal.event_view(row)
    assert utc["start"] == "2026-10-02T22:00:00Z" and utc["end"] == "2026-10-02T23:00:00Z"
    local = cal.event_view(row, LA)
    assert local["start"] == "2026-10-02T15:00:00-07:00"
    assert local["source_kind"] == "email" and local["source_label"] == "Your appointment"
    day = cal.event_view(_row(all_day=True, starts_at=None, ends_at=None,
                              start_date=date(2026, 10, 5), end_date=date(2026, 10, 6)), LA)
    assert (day["start"], day["end"], day["all_day"]) == ("2026-10-05", "2026-10-06", True)


# ── queries ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listing_scopes_to_the_person_and_matches_days_and_text(monkeypatch):
    conn = FakeConn([("FROM mw_calendar_events", [_row()])])
    monkeypatch.setattr(cal, "connection_or_direct", connection(conn))
    begin, finish = cal.window("2026-10-01T00:00:00-07:00", "2026-10-08T00:00:00-07:00")
    events = await cal.list_events(USER, begin, finish, tz=LA, query="  dent  ")
    assert events[0]["start"] == "2026-10-02T15:00:00-07:00"
    _, query, args = conn.ran("FROM mw_calendar_events")[0]
    assert args == (USER, begin, finish, date(2026, 10, 1), date(2026, 10, 7), "%dent%")
    assert "user_id = $1" in query and "ILIKE $6" in query
    assert "LIMIT 500" in query


@pytest.mark.asyncio
async def test_dated_todos_come_only_from_active_boards(monkeypatch):
    todo = {"id": uuid4(), "board_id": uuid4(), "board_title": "My To-Dos", "title": "Renew lease",
            "board_column": "todo", "due_date": date(2026, 10, 2), "source_journal_id": None}
    conn = FakeConn([("FROM mw_productivity_cards", [todo])])
    monkeypatch.setattr(cal, "connection_or_direct", connection(conn))
    out = await cal.list_dated_todos(USER, date(2026, 10, 1), date(2026, 10, 7))
    assert out[0]["due_date"] == "2026-10-02" and out[0]["board_title"] == "My To-Dos"
    _, query, args = conn.ran("FROM mw_productivity_cards")[0]
    assert "b.status = 'active'" in query and args == (USER, date(2026, 10, 1), date(2026, 10, 7))


@pytest.mark.asyncio
async def test_create_stores_the_source_and_refuses_an_unknown_one(monkeypatch):
    conn = FakeConn([("INSERT INTO mw_calendar_events", _row(source_kind="email", source_ref="m1"))])
    monkeypatch.setattr(cal, "connection_or_direct", connection(conn))
    fields = cal.event_fields(title="Dentist", start="2026-10-02T15:00:00-07:00")
    made = await cal.create_event(USER, COMPANY, fields, source_kind="email", source_ref=" m1 ",
                                  source_label="  Your   appointment ")
    assert made["source_ref"] == "m1"
    args = conn.ran("INSERT INTO mw_calendar_events")[0][2]
    assert args[:3] == (USER, COMPANY, "Dentist") and args[10:] == ("email", "m1", "Your appointment")
    with pytest.raises(ValueError, match="unknown source"):
        await cal.create_event(USER, COMPANY, fields, source_kind="google")


@pytest.mark.asyncio
async def test_update_locks_the_persons_own_row_and_none_when_it_is_not_theirs(monkeypatch):
    row = _row()
    conn = FakeConn([("FOR UPDATE", row), ("UPDATE mw_calendar_events", _row(title="Dentist 2"))])
    monkeypatch.setattr(cal, "connection_or_direct", connection(conn))
    out = await cal.update_event(row["id"], USER, {"title": "Dentist 2"})
    assert out["title"] == "Dentist 2"
    assert conn.ran("FOR UPDATE")[0][2] == (row["id"], USER)
    assert conn.ran("UPDATE mw_calendar_events")[0][2][:3] == (row["id"], USER, "Dentist 2")

    missing = FakeConn([("FOR UPDATE", None)])
    monkeypatch.setattr(cal, "connection_or_direct", connection(missing))
    assert await cal.update_event(row["id"], USER, {"title": "x"}) is None
    assert missing.ran("UPDATE mw_calendar_events") == []


@pytest.mark.asyncio
async def test_get_delete_and_by_source_are_the_persons_own(monkeypatch):
    row = _row()
    conn = FakeConn([("DELETE FROM", "DELETE 1"), ("WHERE id = $1 AND user_id = $2", row),
                     ("source_kind = $2", [row])])
    monkeypatch.setattr(cal, "connection_or_direct", connection(conn))
    assert (await cal.get_event(row["id"], USER))["title"] == "Dentist"
    assert await cal.delete_event(row["id"], USER) is True
    assert len(await cal.events_from_source(USER, "email", "m1")) == 1
    assert conn.ran("DELETE FROM")[0][2] == (row["id"], USER)
    conn.on("DELETE FROM", "DELETE 0")
    assert await cal.delete_event(row["id"], USER) is False


@pytest.mark.asyncio
async def test_timezone_is_stored_only_when_real_and_read_without_raising(monkeypatch):
    conn = FakeConn([("SELECT timezone", "America/Los_Angeles")])
    monkeypatch.setattr(cal, "connection_or_direct", connection(conn))
    assert await cal.set_timezone(USER, " America/Los_Angeles ") == "America/Los_Angeles"
    assert conn.ran("INSERT INTO mw_calendar_prefs")[0][2] == (USER, "America/Los_Angeles")
    with pytest.raises(ValueError, match="timezone name"):
        await cal.set_timezone(USER, "Pacific Time")
    assert await cal.get_timezone(USER) == "America/Los_Angeles"
    assert await cal.get_timezone(USER, conn) == "America/Los_Angeles"
    conn.on("SELECT timezone", "Mars/Olympus")
    assert await cal.get_timezone(USER) is None
    conn.on("SELECT timezone", asyncpg.UndefinedTableError("missing"))
    assert await cal.get_timezone(USER) is None

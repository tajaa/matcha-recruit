"""Pure-function tests for evaluate_promote (no DB/Gemini) — the EMS
event->incident promotion safety envelope. Modeled on
tests/huume/test_huume_actions.py for the sibling huume envelope.

    cd server && ./venv/bin/python -m pytest tests/ems/test_promote_envelope.py -q
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.matcha.services.ems import promote
from app.matcha.services.ems.promote import (
    PromoteRaceError, evaluate_promote, naive_occurred_at, shape_witnesses,
)

FEATURES_ON = {"ems": True, "incidents": True, "matcha_work": True}


class TestPromoteRaceError:
    def test_is_not_a_value_error(self):
        # promote.py:promote_event raises this instead of ValueError
        # specifically so routes/ems.py's `except PromoteRaceError` doesn't
        # also catch unrelated ValueErrors raised deep inside
        # create_incident_core (date parse, JSON encode) and misreport them
        # as a 409 promote/dismiss race.
        assert not issubclass(PromoteRaceError, ValueError)


class TestNaiveOccurredAt:
    """`ir_incidents.occurred_at` is TIMESTAMP *WITHOUT* TIME ZONE. Handing
    asyncpg a tz-aware datetime let it convert to UTC and drop the offset,
    so an evening event west of UTC filed an incident dated a day ahead of
    what the promote modal displayed."""

    def test_naive_passes_through_unchanged(self):
        dt = datetime(2026, 7, 30, 17, 20)
        assert naive_occurred_at(dt) is dt

    def test_none_passes_through(self):
        assert naive_occurred_at(None) is None

    def test_aware_becomes_naive(self):
        aware = datetime(2026, 7, 31, 0, 20, tzinfo=timezone.utc)
        out = naive_occurred_at(aware)
        assert out.tzinfo is None

    def test_aware_keeps_local_wall_clock_not_utc(self):
        # Same instant, expressed in a +14 offset. Its LOCAL wall clock is
        # what a reporter would recognize; naive-UTC would be a day off.
        tz = timezone(timedelta(hours=14))
        aware = datetime(2026, 7, 31, 14, 20, tzinfo=tz)
        out = naive_occurred_at(aware)
        assert out == aware.astimezone().replace(tzinfo=None)
        assert out.tzinfo is None


class TestShapeWitnesses:
    def test_strings_become_name_dicts(self):
        assert shape_witnesses(["Bob", " Alice "]) == [{"name": "Bob"}, {"name": "Alice"}]

    def test_drops_blank_and_non_string(self):
        assert shape_witnesses(["", "   ", None, 3, "Bob"]) == [{"name": "Bob"}]

    def test_none_is_empty(self):
        assert shape_witnesses(None) == []

    def test_empty_list_is_empty(self):
        assert shape_witnesses([]) == []


class TestEvaluatePromote:
    def test_client_with_both_flags_and_logged_status_proceeds(self):
        v = evaluate_promote(role="client", features=FEATURES_ON, event_status="logged")
        assert v.kind == "proceed"
        assert v.ok

    def test_admin_with_both_flags_and_logged_status_proceeds(self):
        v = evaluate_promote(role="admin", features=FEATURES_ON, event_status="logged")
        assert v.ok

    def test_employee_role_refuses(self):
        v = evaluate_promote(role="employee", features=FEATURES_ON, event_status="logged")
        assert v.kind == "refuse"
        assert v.http_status == 403

    def test_individual_role_refuses(self):
        v = evaluate_promote(role="individual", features=FEATURES_ON, event_status="logged")
        assert v.kind == "refuse"
        assert v.http_status == 403

    def test_none_role_refuses(self):
        v = evaluate_promote(role=None, features=FEATURES_ON, event_status="logged")
        assert v.kind == "refuse"

    def test_refuses_without_ems_flag(self):
        features = {**FEATURES_ON, "ems": False}
        v = evaluate_promote(role="client", features=features, event_status="logged")
        assert v.kind == "refuse"
        assert v.http_status == 403

    def test_refuses_without_incidents_flag(self):
        features = {**FEATURES_ON, "incidents": False}
        v = evaluate_promote(role="client", features=features, event_status="logged")
        assert v.kind == "refuse"
        assert v.http_status == 403

    def test_refuses_already_promoted_status(self):
        v = evaluate_promote(role="client", features=FEATURES_ON, event_status="promoted")
        assert v.kind == "refuse"
        assert v.http_status == 409

    def test_refuses_dismissed_status(self):
        v = evaluate_promote(role="client", features=FEATURES_ON, event_status="dismissed")
        assert v.kind == "refuse"
        assert v.http_status == 409


class _FakeConn:
    """Just enough of asyncpg's Connection for promote_event's two
    post-create_incident_core writes (the UPDATE ems_events status stamp +
    the audit-log INSERT) — no real DB."""

    def __init__(self):
        self.executed = []

    async def fetchrow(self, query, *args):
        assert "UPDATE ems_events" in query
        return {"id": args[0]}  # non-None => not a promote race

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return "INSERT 0 1"


class TestPromoteEventLocationPassthrough:
    """oploc01: the store captured at intake (ems_events.location_id) must
    carry forward onto the created IR incident's real location_id FK —
    dropping it here would silently lose store attribution at the exact
    point it matters (the incident, and downstream the OSHA 300
    establishment)."""

    @pytest.mark.asyncio
    async def test_event_location_id_reaches_create_incident_core(self, monkeypatch):
        captured = {}

        async def fake_create_incident_core(conn, **kwargs):
            captured.update(kwargs)
            return {"id": uuid4()}, []

        monkeypatch.setattr(promote, "create_incident_core", fake_create_incident_core)

        store_id = uuid4()
        event = {
            "id": uuid4(), "title": "Spill", "created_at": datetime(2026, 8, 1, 12, 0),
            "location_id": store_id, "suggested_incident_type": None, "suggested_severity": None,
            "narrative": "Something spilled", "doc": {},
        }
        conn = _FakeConn()

        await promote.promote_event(
            conn, company_id=uuid4(), event=event, channel_name="wilshire-floor",
            reporter_name="Jane", overrides={}, actor_user_id=uuid4(), actor_email=None,
        )

        assert captured["location_id"] == store_id

    @pytest.mark.asyncio
    async def test_no_channel_location_passes_none(self, monkeypatch):
        captured = {}

        async def fake_create_incident_core(conn, **kwargs):
            captured.update(kwargs)
            return {"id": uuid4()}, []

        monkeypatch.setattr(promote, "create_incident_core", fake_create_incident_core)

        event = {
            "id": uuid4(), "title": "Spill", "created_at": datetime(2026, 8, 1, 12, 0),
            "location_id": None, "suggested_incident_type": None, "suggested_severity": None,
            "narrative": "Something spilled", "doc": {},
        }
        conn = _FakeConn()

        await promote.promote_event(
            conn, company_id=uuid4(), event=event, channel_name=None,
            reporter_name="Jane", overrides={}, actor_user_id=uuid4(), actor_email=None,
        )

        assert captured["location_id"] is None

    @pytest.mark.asyncio
    async def test_free_text_location_override_is_independent(self, monkeypatch):
        # `location` (free-text override/display) and `location_id` (real
        # FK from the channel scope) are separate create_incident_core
        # kwargs — one must not clobber the other.
        captured = {}

        async def fake_create_incident_core(conn, **kwargs):
            captured.update(kwargs)
            return {"id": uuid4()}, []

        monkeypatch.setattr(promote, "create_incident_core", fake_create_incident_core)

        store_id = uuid4()
        event = {
            "id": uuid4(), "title": "Spill", "created_at": datetime(2026, 8, 1, 12, 0),
            "location_id": store_id, "suggested_incident_type": None, "suggested_severity": None,
            "narrative": "Something spilled", "doc": {},
        }
        conn = _FakeConn()

        await promote.promote_event(
            conn, company_id=uuid4(), event=event, channel_name="wilshire-floor",
            reporter_name="Jane", overrides={"location": "Back of house"},
            actor_user_id=uuid4(), actor_email=None,
        )

        assert captured["location"] == "Back of house"
        assert captured["location_id"] == store_id

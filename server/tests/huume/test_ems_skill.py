"""Tests for services/huume/ems_skill.py's execute_promote (fake conn, no DB).

    cd server && ./venv/bin/python -m pytest tests/huume/test_ems_skill.py -q

ems_skill.execute_promote lazily imports evaluate_promote/promote_event from
app.matcha.services.ems.promote and get_company_features from
app.core.feature_flags on every call — per server/CLAUDE.md's patching rule,
monkeypatch must target THOSE modules (the ones that DEFINE the symbols),
not ems_skill's own namespace, since a lazy `from x import y` re-binds the
name fresh each call and a patch on ems_skill.y would be silently ignored.
get_connection IS a module-level import in ems_skill.py, so it's patched
directly on ems_skill itself.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.ems.promote import PromoteRaceError
from app.matcha.services.huume import ems_skill

COMPANY_ID = uuid4()
ACTOR_ID = uuid4()
EVENT_ID = uuid4()
INCIDENT_ID = uuid4()


class _NullTxn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, *, actor_row, event_row):
        self._actor_row = actor_row
        self._event_row = event_row

    async def fetchrow(self, query, *args):
        q = " ".join(query.split())
        if "SELECT role, email FROM users" in q:
            return self._actor_row
        if "FROM ems_events" in q:
            return self._event_row
        raise AssertionError(f"unexpected fetchrow: {q}")

    def transaction(self):
        return _NullTxn()


class _ConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


def _event_row(status="logged"):
    return {
        "id": EVENT_ID, "company_id": COMPANY_ID, "status": status,
        "channel_name": "front-desk", "reporter_name": "Jordan Lee",
        "title": "Equipment issue", "narrative": "The autoclave stopped mid-cycle.",
        "created_at": None,
    }


_UNSET = object()


def _patch_conn(monkeypatch, *, actor_row=None, event_row=_UNSET):
    actor_row = actor_row if actor_row is not None else {"role": "client", "email": "admin@example.com"}
    event_row = _event_row() if event_row is _UNSET else event_row
    conn = _FakeConn(actor_row=actor_row, event_row=event_row)
    monkeypatch.setattr(ems_skill, "get_connection", lambda: _ConnCtx(conn))
    return conn


def _patch_features(monkeypatch, features):
    import app.core.feature_flags as feature_flags
    monkeypatch.setattr(feature_flags, "get_company_features", AsyncMock(return_value=features))


class TestExecutePromote:
    @pytest.mark.asyncio
    async def test_bad_event_id_errors_without_touching_db(self, monkeypatch):
        result = await ems_skill.execute_promote(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID, action={"event_id": "not-a-uuid"},
        )
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_missing_event_errors(self, monkeypatch):
        _patch_conn(monkeypatch, event_row=None)
        _patch_features(monkeypatch, {"ems": True, "incidents": True})
        result = await ems_skill.execute_promote(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID, action={"event_id": str(EVENT_ID)},
        )
        assert result["status"] == "error"
        assert "no logged event" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_refuses_when_incidents_flag_off(self, monkeypatch):
        _patch_conn(monkeypatch)
        _patch_features(monkeypatch, {"ems": True, "incidents": False})
        promote_mock = AsyncMock()
        import app.matcha.services.ems.promote as promote_module
        monkeypatch.setattr(promote_module, "promote_event", promote_mock)

        result = await ems_skill.execute_promote(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID, action={"event_id": str(EVENT_ID)},
        )
        assert result["status"] == "error"
        promote_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_refuses_wrong_role(self, monkeypatch):
        _patch_conn(monkeypatch, actor_row={"role": "employee", "email": "e@example.com"})
        _patch_features(monkeypatch, {"ems": True, "incidents": True})
        result = await ems_skill.execute_promote(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID, action={"event_id": str(EVENT_ID)},
        )
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_refuses_already_promoted(self, monkeypatch):
        _patch_conn(monkeypatch, event_row=_event_row(status="promoted"))
        _patch_features(monkeypatch, {"ems": True, "incidents": True})
        result = await ems_skill.execute_promote(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID, action={"event_id": str(EVENT_ID)},
        )
        assert result["status"] == "error"
        assert "promoted" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_success_returns_created_with_bg_tasks(self, monkeypatch):
        _patch_conn(monkeypatch)
        _patch_features(monkeypatch, {"ems": True, "incidents": True})
        sentinel_task = (lambda: None, (), {})
        promote_mock = AsyncMock(return_value=(
            {"id": INCIDENT_ID, "incident_number": "INC-42", "title": "Equipment issue"},
            [sentinel_task],
        ))
        import app.matcha.services.ems.promote as promote_module
        monkeypatch.setattr(promote_module, "promote_event", promote_mock)

        result = await ems_skill.execute_promote(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID, action={"event_id": str(EVENT_ID)},
        )
        assert result["status"] == "created"
        assert result["record_id"] == str(INCIDENT_ID)
        assert result["record_label"] == "INC-42"
        assert result["bg_tasks"] == [sentinel_task]

    @pytest.mark.asyncio
    async def test_promote_race_maps_to_error_not_raise(self, monkeypatch):
        _patch_conn(monkeypatch)
        _patch_features(monkeypatch, {"ems": True, "incidents": True})
        promote_mock = AsyncMock(side_effect=PromoteRaceError("raced"))
        import app.matcha.services.ems.promote as promote_module
        monkeypatch.setattr(promote_module, "promote_event", promote_mock)

        result = await ems_skill.execute_promote(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID, action={"event_id": str(EVENT_ID)},
        )
        assert result["status"] == "error"
        assert "refresh" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_overrides_only_carry_sent_fields(self, monkeypatch):
        _patch_conn(monkeypatch)
        _patch_features(monkeypatch, {"ems": True, "incidents": True})
        promote_mock = AsyncMock(return_value=(
            {"id": INCIDENT_ID, "incident_number": "INC-42"}, [],
        ))
        import app.matcha.services.ems.promote as promote_module
        monkeypatch.setattr(promote_module, "promote_event", promote_mock)

        await ems_skill.execute_promote(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID, action={"event_id": str(EVENT_ID)},
        )
        _, kwargs = promote_mock.call_args
        assert kwargs["overrides"] == {}

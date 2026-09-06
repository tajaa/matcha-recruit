"""Deleting a job takes it out of every location's leader rule first.

`schedule_location_profiles.leader_job_ids` is a plain `UUID[]`: the FK that
carries `ON DELETE SET NULL` sits on the `leader_job_id` mirror only, and
nothing inside an array can be nulled by a referential action. A delete that
ignored the array would leave the uuid behind, where it reads as an answered
leader rule to the week-rules gate while `load_profile_bundle` and
`week_builder._coverage_profile` drop it — a green gate over a week nobody
checked for lead coverage.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.matcha.routes.employee_schedule import jobs as routes


COMPANY_ID = UUID("11111111-1111-1111-1111-111111111111")
JOB_ID = UUID("88888888-8888-8888-8888-888888888888")
ACTOR_ID = UUID("77777777-7777-7777-7777-777777777777")
LOCATION_ID = UUID("66666666-6666-6666-6666-666666666666")


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_args):
        return False


class _RecordingConn:
    """Records every statement in the order it was issued — the ordering IS
    the invariant under test."""

    def __init__(self, *, job_row, detached=1):
        self.statements: list[str] = []
        self.args: list[tuple] = []
        self._job_row = job_row
        self._detached = detached

    def _record(self, sql, args):
        self.statements.append(" ".join(sql.split()))
        self.args.append(args)

    def transaction(self):
        return _AsyncContext(None)

    async def fetchrow(self, sql, *args):
        self._record(sql, args)
        return self._job_row

    async def fetch(self, sql, *args):
        self._record(sql, args)
        return [{"location_id": LOCATION_ID}] * self._detached

    async def execute(self, sql, *args):
        self._record(sql, args)
        return "DELETE 1"


def _patch(monkeypatch, conn):
    monkeypatch.setattr(routes, "get_connection", lambda: _AsyncContext(conn))
    monkeypatch.setattr(routes, "require_company_id", AsyncMock(return_value=COMPANY_ID))


def _user():
    return SimpleNamespace(id=ACTOR_ID, role="client")


def _index_of(conn, needle):
    return next(i for i, sql in enumerate(conn.statements) if needle in sql)


@pytest.mark.asyncio
async def test_delete_detaches_the_leader_rule_before_dropping_the_job(monkeypatch):
    """Before, not after: run the scrub second and the FK has already nulled
    the mirror, so a store with a surviving second leader loses the value the
    mirror is supposed to hold."""
    conn = _RecordingConn(job_row={"id": JOB_ID, "name": "Shift Lead"})
    _patch(monkeypatch, conn)
    monkeypatch.setattr(routes, "log_audit", AsyncMock())

    await routes.delete_job(JOB_ID, _user())

    detach = _index_of(conn, "UPDATE schedule_location_profiles")
    delete = _index_of(conn, "DELETE FROM schedule_jobs")
    assert detach < delete


@pytest.mark.asyncio
async def test_the_detach_matches_both_spellings_of_the_rule(monkeypatch):
    """A row can name the job in the set, in the mirror, or in both — a store
    configured by the pre-set image has only the mirror."""
    conn = _RecordingConn(job_row={"id": JOB_ID, "name": "Shift Lead"})
    _patch(monkeypatch, conn)
    monkeypatch.setattr(routes, "log_audit", AsyncMock())

    await routes.delete_job(JOB_ID, _user())

    detach = conn.statements[_index_of(conn, "UPDATE schedule_location_profiles")]
    assert "leader_job_ids @> ARRAY[$1::uuid]" in detach
    assert "leader_job_id = $1::uuid" in detach
    # Nothing left to lead with un-answers the question rather than leaving
    # `leader_required = true` with nothing named — the state the CHECK
    # refuses, which would fail the delete itself.
    assert "leader_required = CASE" in detach
    assert "ELSE NULL" in detach


@pytest.mark.asyncio
async def test_the_audit_row_says_how_many_stores_lost_their_lead(monkeypatch):
    """A silently reset leader rule is exactly the kind of side effect the
    audit trail exists for."""
    conn = _RecordingConn(job_row={"id": JOB_ID, "name": "Shift Lead"}, detached=2)
    _patch(monkeypatch, conn)
    audit = AsyncMock()
    monkeypatch.setattr(routes, "log_audit", audit)

    await routes.delete_job(JOB_ID, _user())

    assert audit.await_args.args[6] == {"name": "Shift Lead", "leader_rules_detached": 2}


@pytest.mark.asyncio
async def test_an_unknown_job_is_a_404_and_touches_no_profile(monkeypatch):
    conn = _RecordingConn(job_row=None)
    _patch(monkeypatch, conn)
    monkeypatch.setattr(routes, "log_audit", AsyncMock())

    with pytest.raises(routes.HTTPException) as excinfo:
        await routes.delete_job(JOB_ID, _user())

    assert excinfo.value.status_code == 404
    assert not any("schedule_location_profiles" in sql for sql in conn.statements)

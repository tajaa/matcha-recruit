"""The role label a written shift carries is the job's name, on every path.

create_shift_core is the single choke point: the REST route, chat confirms and
week generation all insert through it, so the invariant cannot hold on one path
and quietly not on another.
"""

import asyncio
from uuid import uuid4

import pytest

from app.matcha.services.scheduling import shift_writes
from app.matcha.services.scheduling.shift_writes import (
    create_shift_core, resolve_job_by_name,
)

STARTS = "2026-09-01T09:00:00+00:00"


def _run(coro):
    return asyncio.run(coro)


class FakeConn:
    """Records every statement; answers the two reads create_shift_core makes
    with no assignees (the job name, then the INSERT ... RETURNING id)."""

    def __init__(self, job_name=None):
        self.job_name = job_name
        self.queries = []
        self.shift_id = uuid4()

    async def fetchval(self, query, *args):
        self.queries.append((" ".join(query.split()), args))
        if "FROM schedule_jobs" in query:
            return self.job_name
        if "INSERT INTO schedule_shifts" in query:
            return self.shift_id
        return None

    async def fetchrow(self, query, *args):
        self.queries.append((" ".join(query.split()), args))
        return None

    async def execute(self, query, *args):
        self.queries.append((" ".join(query.split()), args))
        return "INSERT 0 1"


@pytest.fixture
def stub_break_plan(monkeypatch):
    from app.matcha.services.scheduling import schedule_breaks, schedule_guidance

    async def _plan(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(schedule_guidance, "resolve_shift_break_plan", _plan)
    monkeypatch.setattr(schedule_breaks, "minimum_meal_break_minutes", lambda _plan: 0)
    return None


def _inserted_role(conn):
    insert = next(
        q for q in conn.queries if q[0].startswith("INSERT INTO schedule_shifts")
    )
    # role is the third column in the INSERT's argument list.
    return insert[1][2]


def _create(conn, **kwargs):
    from datetime import datetime, timezone

    return _run(create_shift_core(
        conn, uuid4(),
        location_id=None,
        starts_at=datetime(2026, 9, 1, 9, tzinfo=timezone.utc),
        ends_at=datetime(2026, 9, 1, 17, tzinfo=timezone.utc),
        break_minutes=0, required_staff=1,
        employee_ids=[], created_by=uuid4(),
        **kwargs,
    ))


def test_job_name_overrides_whatever_role_the_caller_passed(stub_break_plan):
    conn = FakeConn(job_name="Barista")

    _create(conn, job_id=uuid4(), role="Opener")

    assert _inserted_role(conn) == "Barista"


def test_role_is_untouched_when_the_shift_carries_no_job(stub_break_plan):
    conn = FakeConn()

    _create(conn, role="opener")

    assert _inserted_role(conn) == "opener"
    assert not any("FROM schedule_jobs" in q[0] for q in conn.queries)


def test_unknown_job_degrades_to_the_callers_label(stub_break_plan):
    # A job that isn't this company's (a stale in-flight id) must not explode
    # the write — same treatment check_job_qualification gives a dangling id.
    conn = FakeConn(job_name=None)

    _create(conn, job_id=uuid4(), role="opener")

    assert _inserted_role(conn) == "opener"


def test_the_job_row_is_locked_while_its_name_is_read(stub_break_plan):
    conn = FakeConn(job_name="Barista")

    _create(conn, job_id=uuid4(), role=None)

    job_read = next(q for q in conn.queries if "FROM schedule_jobs" in q[0])
    assert job_read[0].endswith("FOR SHARE")


# -- resolve_job_by_name ------------------------------------------------------


class RowConn:
    def __init__(self, row=None):
        self.row = row
        self.calls = []

    async def fetchrow(self, query, *args):
        self.calls.append((" ".join(query.split()), args))
        return self.row


def test_blank_labels_never_hit_the_database():
    for label in (None, "", "   "):
        conn = RowConn({"id": uuid4(), "name": "Barista"})
        assert _run(resolve_job_by_name(conn, uuid4(), label)) is None
        assert conn.calls == []


def test_a_matching_label_resolves_to_the_job():
    job_id = uuid4()
    conn = RowConn({"id": job_id, "name": "Barista"})

    row = _run(resolve_job_by_name(conn, uuid4(), " barista ", location_id=None))

    assert row["id"] == job_id
    assert conn.calls[0][1][1] == "barista"


def test_an_unmatched_label_stays_free_text():
    conn = RowConn(None)

    assert _run(resolve_job_by_name(conn, uuid4(), "opener")) is None


def test_location_scoped_jobs_are_preferred_over_company_wide_ones():
    conn = RowConn({"id": uuid4(), "name": "Barista"})
    location_id = uuid4()

    _run(resolve_job_by_name(conn, uuid4(), "Barista", location_id=location_id))

    query, args = conn.calls[0]
    assert "location_id IS NULL OR location_id = $3" in query
    assert "ORDER BY location_id NULLS LAST" in query
    assert args[2] == location_id


def test_the_resolver_is_exported_for_the_free_text_write_paths():
    # schedule_chat and week_builder both import it from here; keep the name.
    assert shift_writes.resolve_job_by_name is resolve_job_by_name

"""DB-free coverage for the scheduler wrapper around the daily digest."""

from datetime import date
from uuid import uuid4

import pytest

from app.matcha.services.scheduling import daily_digest


class _Conn:
    def __init__(self):
        self.executed = []
        self.closed = False

    async def execute(self, query, *params):
        self.executed.append((query, params))

    async def fetch(self, query, *params):
        assert "LIMIT $1" in query
        assert params == (1,)
        rows = [
            {"company_id": uuid4(), "id": uuid4(), "timezone": "America/Los_Angeles"},
            {"company_id": uuid4(), "id": uuid4(), "timezone": "UTC"},
        ]
        return rows[:params[0]]

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_worker_reads_cycle_cap_prunes_and_closes_connection(monkeypatch):
    # Import inside the test: the worker utility loads .env, and importing it
    # during collection would accidentally enable unrelated opt-in real-DB
    # tests in the same pytest command.
    from app.workers.tasks import schedule_daily_digest as worker

    conn = _Conn()
    sent_locations = []

    async def get_connection():
        return conn

    async def send_digest(conn, *, company_id, location_id, digest_date):
        sent_locations.append((company_id, location_id, digest_date))
        return {"sent": 1}

    monkeypatch.setattr(worker, "get_db_connection", get_connection)
    monkeypatch.setattr(worker, "scheduler_enabled", lambda *args, **kwargs: _enabled())
    monkeypatch.setattr(worker, "scheduler_settings_row", lambda *args, **kwargs: _settings())
    monkeypatch.setattr(daily_digest, "send_location_daily_digest", send_digest)

    result = await worker._run()

    assert result["locations"] == 1
    assert result["sent"] == 1
    assert len(sent_locations) == 1
    assert "DELETE FROM schedule_digest_deliveries" in conn.executed[0][0]
    assert conn.closed is True


def test_location_date_falls_back_to_utc_for_bad_timezone():
    from app.workers.tasks import schedule_daily_digest as worker

    assert worker._location_date("not/a-real-timezone").__class__ is date


async def _enabled():
    return True


async def _settings():
    return {"max_per_cycle": 1}

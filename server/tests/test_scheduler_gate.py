"""Scheduler-gate semantics.

The gate decides whether a scheduled task runs at all, and the tasks genuinely
disagree about what a MISSING or unreadable `scheduler_settings` row should
mean. Getting that backwards is expensive in one direction (a fail-open
`vertical_coverage_sweep` makes live Gemini calls; `cappe_domain_renewals` buys
domain renewals) and merely noisy in the other, which is why `default` is an
explicit argument rather than a house convention.
"""

import pytest

from app.workers.utils import scheduler_enabled, scheduler_settings_row


class FakeConn:
    """Minimal asyncpg stand-in: returns a canned row or raises."""

    def __init__(self, row=None, raises=False):
        self._row = row
        self._raises = raises
        self.queries = []

    async def fetchrow(self, sql, *args):
        self.queries.append((sql, args))
        if self._raises:
            raise RuntimeError("relation \"scheduler_settings\" does not exist")
        return self._row


@pytest.mark.asyncio
class TestSchedulerEnabled:
    async def test_enabled_row_runs(self):
        assert await scheduler_enabled(FakeConn({"enabled": True, "max_per_cycle": 10}), "t") is True

    async def test_disabled_row_skips(self):
        assert await scheduler_enabled(FakeConn({"enabled": False, "max_per_cycle": 10}), "t") is False

    async def test_null_enabled_is_treated_as_disabled(self):
        assert await scheduler_enabled(FakeConn({"enabled": None, "max_per_cycle": 1}), "t") is False

    async def test_missing_row_defaults_open(self):
        # auto_archive / coi_expiry / discipline_expiry / newsletter_scheduler:
        # idempotent bookkeeping, an unconfigured task should still run.
        assert await scheduler_enabled(FakeConn(None), "t") is True

    async def test_missing_row_can_default_closed(self):
        # cappe_domain_renewals / vertical_coverage_sweep: spending money or
        # Gemini quota. "We could not read the setting" must not mean "go ahead".
        assert await scheduler_enabled(FakeConn(None), "t", default=False) is False

    async def test_query_failure_uses_the_default_not_a_crash(self):
        # The table may not exist yet during a deploy — the reason every caller
        # wrapped this in its own try/except before.
        assert await scheduler_enabled(FakeConn(raises=True), "t") is True
        assert await scheduler_enabled(FakeConn(raises=True), "t", default=False) is False

    async def test_an_explicitly_disabled_row_beats_the_default(self):
        # default only governs the missing/unreadable case; a real row wins.
        conn = FakeConn({"enabled": False, "max_per_cycle": 5})
        assert await scheduler_enabled(conn, "t", default=True) is False


@pytest.mark.asyncio
class TestSchedulerSettingsRow:
    async def test_returns_the_row_including_max_per_cycle(self):
        row = await scheduler_settings_row(FakeConn({"enabled": True, "max_per_cycle": 25}), "t")
        assert row["max_per_cycle"] == 25

    async def test_returns_none_on_query_failure(self):
        assert await scheduler_settings_row(FakeConn(raises=True), "t") is None

    async def test_passes_the_task_key_as_a_bound_parameter(self):
        # Not f-stringed into the SQL — server/CLAUDE.md: "Use parameterized
        # queries. Never f-string user input into SQL."
        conn = FakeConn({"enabled": True, "max_per_cycle": 1})
        await scheduler_settings_row(conn, "compliance_checks")
        sql, args = conn.queries[0]
        assert "$1" in sql
        assert args == ("compliance_checks",)
        assert "compliance_checks" not in sql

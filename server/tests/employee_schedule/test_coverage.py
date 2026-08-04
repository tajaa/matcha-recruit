"""services/scheduling/coverage.py — the standalone "who's free to cover"
extraction of schedule_chat.build_proposal's candidate-assembly steps.
Exercises the deterministic filtering (busy/availability/inactive/self)
and ranking against a fake asyncpg connection — no real DB.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_coverage.py -q
"""

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4

from app.matcha.services.scheduling import coverage


def _run(coro):
    return asyncio.run(coro)


def _emp(eid, first, last, job_title=None, status="active"):
    return {
        "id": eid, "first_name": first, "last_name": last,
        "job_title": job_title, "employment_status": status,
    }


class FakeConn:
    """Routes each query by a keyword sniff on the SQL text — mirrors the
    fake-conn pattern used elsewhere in tests/ems for DB-shaped services."""

    def __init__(self, *, shifts=None, assignees=None, roster=None, hours=None,
                 busy=None, availability=None):
        self.shifts = shifts or []
        self.assignees = assignees or []
        self.roster = roster or []
        self.hours = hours or []
        self.busy = busy or []
        self.availability = availability or []

    async def fetch(self, query, *args):
        q = " ".join(query.split())
        if "FROM schedule_shifts s" in q and "SUM(EXTRACT" in q:
            return self.hours
        if "FROM schedule_shift_assignments a" in q and "JOIN employees e" in q:
            return self.assignees
        if "DISTINCT a.employee_id" in q:
            return self.busy
        if "FROM employees" in q and "job_title" in q:
            return self.roster
        if "FROM schedule_employee_availability" in q:
            return self.availability
        if "FROM schedule_shifts" in q and "status = 'published'" in q:
            return self.shifts
        raise AssertionError(f"unexpected query: {q[:80]}")


def _shift_row(eid, role="Front Desk", required_staff=1, location_id=None,
               starts=(2026, 8, 5, 8, 0), ends=(2026, 8, 5, 16, 0)):
    return {
        "id": eid, "role": role, "required_staff": required_staff,
        "location_id": location_id,
        "starts_at": datetime(*starts, tzinfo=timezone.utc),
        "ends_at": datetime(*ends, tzinfo=timezone.utc),
    }


class TestNoShifts:
    def test_no_published_shifts_that_day(self):
        conn = FakeConn(shifts=[])
        result = _run(coverage.find_coverage_candidates(
            conn, company_id="c1", target_date=date(2026, 8, 5),
            location_id=None, role_hint=None, features={},
        ))
        assert result == {"shifts": [], "role_note": None}


class TestFiltering:
    def test_busy_employee_excluded_from_candidates(self):
        shift_id = uuid4()
        free_id, busy_id = uuid4(), uuid4()
        conn = FakeConn(
            shifts=[_shift_row(shift_id)],
            assignees=[],
            roster=[_emp(free_id, "Dana", "Whitfield"), _emp(busy_id, "Kai", "Vega")],
            hours=[], busy=[{"employee_id": busy_id}], availability=[],
        )
        result = _run(coverage.find_coverage_candidates(
            conn, company_id="c1", target_date=date(2026, 8, 5),
            location_id=None, role_hint=None, features={},
        ))
        names = {c["name"] for c in result["shifts"][0]["candidates"]}
        assert names == {"Dana Whitfield"}

    def test_shifts_own_assignee_excluded_from_candidates(self):
        shift_id = uuid4()
        assignee_id, free_id = uuid4(), uuid4()
        conn = FakeConn(
            shifts=[_shift_row(shift_id)],
            assignees=[{"shift_id": shift_id, "employee_id": assignee_id,
                        "first_name": "Aisha", "last_name": "Kim"}],
            roster=[_emp(assignee_id, "Aisha", "Kim"), _emp(free_id, "Dana", "Whitfield")],
            hours=[], busy=[], availability=[],
        )
        result = _run(coverage.find_coverage_candidates(
            conn, company_id="c1", target_date=date(2026, 8, 5),
            location_id=None, role_hint=None, features={},
        ))
        shift = result["shifts"][0]
        assert shift["assignees"] == ["Aisha Kim"]
        names = {c["name"] for c in shift["candidates"]}
        assert names == {"Dana Whitfield"}

    def test_availability_violator_excluded(self):
        shift_id = uuid4()
        unavailable_id, available_id = uuid4(), uuid4()
        conn = FakeConn(
            shifts=[_shift_row(shift_id)],
            assignees=[],
            roster=[_emp(unavailable_id, "Ravi", "Malik"), _emp(available_id, "Dana", "Whitfield")],
            hours=[], busy=[],
            availability=[{
                "employee_id": unavailable_id, "weekday": 0,
                "start_time": time(0, 0), "end_time": time(6, 0),
            }],
        )
        result = _run(coverage.find_coverage_candidates(
            conn, company_id="c1", target_date=date(2026, 8, 5),
            location_id=None, role_hint=None, features={},
        ))
        names = {c["name"] for c in result["shifts"][0]["candidates"]}
        assert names == {"Dana Whitfield"}

    def test_inactive_employee_never_in_roster_query_result(self):
        # find_coverage_candidates trusts the roster query's own
        # employment_status filter (INACTIVE_EMPLOYMENT_STATUSES) — this
        # test just confirms an inactive-filtered roster produces an
        # inactive-filtered candidate list, i.e. nothing re-adds them.
        shift_id = uuid4()
        active_id = uuid4()
        conn = FakeConn(
            shifts=[_shift_row(shift_id)], assignees=[],
            roster=[_emp(active_id, "Dana", "Whitfield")],
            hours=[], busy=[], availability=[],
        )
        result = _run(coverage.find_coverage_candidates(
            conn, company_id="c1", target_date=date(2026, 8, 5),
            location_id=None, role_hint=None, features={},
        ))
        assert len(result["shifts"][0]["candidates"]) == 1


class TestRankingAndAnnotation:
    def test_least_hours_first_and_cap_five(self):
        shift_id = uuid4()
        ids = [uuid4() for _ in range(6)]
        roster = [_emp(i, f"F{n}", "Last") for n, i in enumerate(ids)]
        hours = [{"employee_id": ids[n], "hrs": float(10 - n)} for n in range(6)]
        conn = FakeConn(
            shifts=[_shift_row(shift_id)], assignees=[], roster=roster,
            hours=hours, busy=[], availability=[],
        )
        result = _run(coverage.find_coverage_candidates(
            conn, company_id="c1", target_date=date(2026, 8, 5),
            location_id=None, role_hint=None, features={},
        ))
        candidates = result["shifts"][0]["candidates"]
        assert len(candidates) == 5
        assert [c["week_hours"] for c in candidates] == sorted(c["week_hours"] for c in candidates)
        assert candidates[0]["week_hours"] == 5.0  # ids[5], 10-5

    def test_missing_hours_default_to_zero(self):
        shift_id = uuid4()
        eid = uuid4()
        conn = FakeConn(
            shifts=[_shift_row(shift_id)], assignees=[],
            roster=[_emp(eid, "Dana", "Whitfield")],
            hours=[], busy=[], availability=[],
        )
        result = _run(coverage.find_coverage_candidates(
            conn, company_id="c1", target_date=date(2026, 8, 5),
            location_id=None, role_hint=None, features={},
        ))
        assert result["shifts"][0]["candidates"][0]["week_hours"] == 0.0

    def test_title_mismatch_annotated_not_filtered(self):
        shift_id = uuid4()
        eid = uuid4()
        conn = FakeConn(
            shifts=[_shift_row(shift_id, role="Front Desk")], assignees=[],
            roster=[_emp(eid, "Ravi", "Malik", job_title="Hygienist")],
            hours=[], busy=[], availability=[],
        )
        result = _run(coverage.find_coverage_candidates(
            conn, company_id="c1", target_date=date(2026, 8, 5),
            location_id=None, role_hint=None, features={},
        ))
        c = result["shifts"][0]["candidates"][0]
        assert c["title_mismatch"] is True

    def test_matching_title_not_flagged_as_mismatch(self):
        shift_id = uuid4()
        eid = uuid4()
        conn = FakeConn(
            shifts=[_shift_row(shift_id, role="Front Desk")], assignees=[],
            roster=[_emp(eid, "Dana", "Whitfield", job_title="Front Desk")],
            hours=[], busy=[], availability=[],
        )
        result = _run(coverage.find_coverage_candidates(
            conn, company_id="c1", target_date=date(2026, 8, 5),
            location_id=None, role_hint=None, features={},
        ))
        assert result["shifts"][0]["candidates"][0]["title_mismatch"] is False


class TestRoleHint:
    def test_no_match_falls_back_to_unfiltered_with_note(self):
        shift_id = uuid4()
        calls = {"n": 0}

        class FallbackConn(FakeConn):
            async def fetch(self, query, *args):
                if "role ILIKE" in " ".join(query.split()):
                    calls["n"] += 1
                    return []
                return await super().fetch(query, *args)

        conn = FallbackConn(shifts=[_shift_row(shift_id)], assignees=[], roster=[], hours=[], busy=[], availability=[])
        result = _run(coverage.find_coverage_candidates(
            conn, company_id="c1", target_date=date(2026, 8, 5),
            location_id=None, role_hint="opener", features={},
        ))
        assert calls["n"] == 1
        assert result["role_note"] is not None
        assert "opener" in result["role_note"]
        assert len(result["shifts"]) == 1


class TestLapseFlags:
    def test_lapsed_item_before_target_date_flags_candidate(self, monkeypatch):
        shift_id = uuid4()
        eid = uuid4()

        async def fake_lapse(conn, company_id, ids, *, credential_templates_enabled, training_enabled):
            return {str(eid): [{"source": "credential", "item": "License", "date": date(2026, 1, 1), "requirement_id": None}]}

        monkeypatch.setattr(coverage, "fetch_lapse_items", fake_lapse)
        conn = FakeConn(
            shifts=[_shift_row(shift_id)], assignees=[],
            roster=[_emp(eid, "Ravi", "Malik")],
            hours=[], busy=[], availability=[],
        )
        result = _run(coverage.find_coverage_candidates(
            conn, company_id="c1", target_date=date(2026, 8, 5),
            location_id=None, role_hint=None, features={"credential_templates": True},
        ))
        assert "License lapsed" in result["shifts"][0]["candidates"][0]["flags"]

    def test_future_lapse_not_flagged(self, monkeypatch):
        shift_id = uuid4()
        eid = uuid4()

        async def fake_lapse(conn, company_id, ids, *, credential_templates_enabled, training_enabled):
            return {str(eid): [{"source": "credential", "item": "License", "date": date(2099, 1, 1), "requirement_id": None}]}

        monkeypatch.setattr(coverage, "fetch_lapse_items", fake_lapse)
        conn = FakeConn(
            shifts=[_shift_row(shift_id)], assignees=[],
            roster=[_emp(eid, "Ravi", "Malik")],
            hours=[], busy=[], availability=[],
        )
        result = _run(coverage.find_coverage_candidates(
            conn, company_id="c1", target_date=date(2026, 8, 5),
            location_id=None, role_hint=None, features={"credential_templates": True},
        ))
        assert result["shifts"][0]["candidates"][0]["flags"] == []

"""`week_builder.plan_vacant_fill` — the server-side "fill the open shifts"
entry that replaces "the model names one person × every vacant shift".
Loaders are patched; the planner, the narrowing and the reason plumbing are
real. There is deliberately NO week-rules gate on this path: the demand is
the shifts that already exist.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_fill_vacant.py -q
"""

import asyncio
from datetime import date, datetime, timezone
from unittest import mock
from uuid import UUID, uuid4

import pytest

from app.matcha.services.scheduling import week_builder

UTC = timezone.utc
COMPANY = UUID("11111111-1111-1111-1111-111111111111")
LOCATION = UUID("c0ffeeee-0001-4001-8001-000000000001")
ANA = "33333333-3333-3333-3333-000000000001"
BEN = "33333333-3333-3333-3333-000000000002"
WEEK = date(2026, 8, 23)
CURATED = {"state": "CA", "status": "curated"}


def _run(coro):
    return asyncio.run(coro)


def _employee(employee_id, name, *, lead=True):
    return {
        "id": employee_id, "name": name, "job_title": "Barista", "availability_state": "windows",
        "jobs": [{"job_id": "lead", "qualification_status": "active",
                  "qualified_from": None, "qualified_until": None}] if lead else [],
        "min_weekly_minutes": None, "target_weekly_minutes": None, "max_weekly_minutes": 2400,
        "max_consecutive_days": None, "allow_overtime": False, "prefer_extra_hours": False,
    }


def _open(shift_id, day, start_hour, end_hour, *, job_id="lead", required=1, fixed=()):
    starts = datetime(2026, 8, day, start_hour, tzinfo=UTC)
    ends = datetime(2026, 8, day, end_hour, tzinfo=UTC)
    return {
        "key": shift_id, "source_shift_id": shift_id, "role": "Shift Lead", "department": None,
        "starts_at": starts, "ends_at": ends, "break_minutes": 0, "required_staff": required,
        "color": None, "notes": None, "kind": "work", "template_id": None, "job_id": job_id,
        "training_requirement_id": None, "fixed_employee_ids": list(fixed),
        "worked_minutes": (end_hour - start_hour) * 60,
    }


def _roster(employees, *, existing=()):
    return {"employees": employees, "availability": {}, "existing_assignments": list(existing),
            "unavailable_ranges": {}, "gated_job_ids": {"lead"}}


def _fill(*, demand, roster, preflight=None, jurisdiction=CURATED, job_match=None, **kwargs):
    calls = {"demand": [], "job": [], "preflight": 0}

    async def fake_demand(conn, **kw):
        calls["demand"].append(kw)
        return demand

    async def fake_roster(conn, **kw):
        return roster

    async def fake_rules(conn, company_id, location_id):
        return dict(jurisdiction)

    async def fake_preflight(conn, *, company_id, location_id, plan):
        calls["preflight"] += 1
        return preflight(plan) if preflight else set()

    async def fake_job(conn, company_id, name, *, location_id=None):
        calls["job"].append(name)
        return job_match

    async def gate_must_not_run(*_a, **_k):
        raise AssertionError("plan_vacant_fill must not consult the week-rules gate")

    with (
        mock.patch.object(week_builder, "_load_vacant_demand", fake_demand),
        mock.patch.object(week_builder, "_load_roster_context", fake_roster),
        mock.patch.object(week_builder, "jurisdiction_rule_status", fake_rules),
        mock.patch.object(week_builder, "_preflight_compliance_blocks", fake_preflight),
        mock.patch.object(week_builder, "resolve_job_by_name", fake_job),
        mock.patch.object(week_builder, "_week_rules_gate", gate_must_not_run),
        mock.patch.object(week_builder, "load_profile_bundle", gate_must_not_run),
    ):
        result = _run(week_builder.plan_vacant_fill(
            None, company_id=COMPANY, location_id=LOCATION, week_start=WEEK, **kwargs,
        ))
    return result, calls


def _who(result):
    return {item["shift_id"]: item["employee_name"] for item in result["assignments"]}


class TestPlanVacantFill:
    def test_two_leads_split_the_open_lead_blocks(self):
        demand = [_open(f"s{day}", day, 6, 14) for day in (23, 24, 25, 26)]
        result, calls = _fill(demand=demand, roster=_roster([_employee(ANA, "Ana"), _employee(BEN, "Ben")]))
        assert result["status"] == "ready"
        assert sorted(_who(result).values()) == ["Ana", "Ana", "Ben", "Ben"]
        assert result["unfilled"] == []
        assert result["hours_by_employee"] == {ANA: 960, BEN: 960}
        assert result["roster_size"] == 2 and result["demand_size"] == 4
        assert result["jurisdiction"]["status"] == "curated" and "on file" in result["jurisdiction"]["message"]
        assert result["assignments"][0]["starts_at"] == "2026-08-23T06:00:00+00:00"   # JSON-safe already
        assert "Available and qualified" in result["assignments"][0]["reason"]
        assert calls["preflight"] == 1

    def test_naming_one_person_narrows_the_roster_and_refuses_per_slot_with_reasons(self):
        demand = [_open("a", 23, 6, 14), _open("b", 23, 10, 18), _open("c", 23, 14, 22), _open("d", 24, 6, 14)]
        result, _ = _fill(
            demand=demand, roster=_roster([_employee(ANA, "Ana"), _employee(BEN, "Ben")]),
            only_employee_ids=[UUID(ANA)],
        )
        assert _who(result) == {"a": "Ana", "d": "Ana"}   # Ben is never considered
        by_id = {item["shift_id"]: item for item in result["unfilled"]}
        assert by_id["b"]["reason"] == "overlapping assignment"
        assert by_id["c"]["reason"] == "policy: second shift that day"
        assert by_id["c"]["exclusions"] == {"policy: second shift that day": 1}
        assert by_id["c"]["ends_at"] == "2026-08-23T22:00:00+00:00"
        assert result["roster_size"] == 1

    def test_excluded_people_are_not_planned(self):
        demand = [_open("a", 23, 6, 14), _open("b", 24, 6, 14)]
        result, _ = _fill(
            demand=demand, roster=_roster([_employee(ANA, "Ana"), _employee(BEN, "Ben")]),
            exclude_employee_ids=[UUID(ANA)],
        )
        assert _who(result) == {"a": "Ben", "b": "Ben"}

    def test_a_compliance_block_replans_the_pair_onto_someone_else(self):
        demand = [_open("a", 23, 6, 14)]

        def block_ana(plan):
            picked = {(shift["key"], item["employee_id"]) for shift in plan["shifts"] for item in shift["proposed_assignments"]}
            return {("a", ANA)} if ("a", ANA) in picked else set()

        result, calls = _fill(demand=demand, roster=_roster([_employee(ANA, "Ana"), _employee(BEN, "Ben")]), preflight=block_ana)
        assert _who(result) == {"a": "Ben"}
        assert calls["preflight"] == 2

    def test_a_role_hint_resolves_to_a_job_before_falling_back_to_a_label_match(self):
        job_id = uuid4()
        demand = [_open("a", 23, 6, 14)]
        _, resolved = _fill(demand=demand, roster=_roster([_employee(ANA, "Ana")]), role_hint="shift lead",
                            job_match={"id": job_id, "name": "Shift Lead"})
        assert resolved["job"] == ["shift lead"]
        assert resolved["demand"][0]["job_ids"] == [job_id] and resolved["demand"][0]["role_ilike"] is None
        _, unresolved = _fill(demand=demand, roster=_roster([_employee(ANA, "Ana")]), role_hint="lead")
        assert unresolved["demand"][0]["job_ids"] is None and unresolved["demand"][0]["role_ilike"] == "lead"

    def test_shift_ids_and_week_end_reach_the_demand_loader(self):
        wanted = uuid4()
        _, calls = _fill(demand=[_open("a", 23, 6, 14)], roster=_roster([_employee(ANA, "Ana")]),
                         shift_ids=[wanted], week_end=date(2026, 8, 29))
        assert calls["demand"][0]["shift_ids"] == [wanted]
        assert calls["demand"][0]["week_end"] == date(2026, 8, 29)

    def test_no_open_shifts_is_a_clarify_that_names_the_scope(self):
        result, _ = _fill(demand=[], roster=_roster([]), role_hint="barista")
        assert result["status"] == "clarify"
        assert result["message"] == 'There are no open shifts matching "barista" in this week to fill.'
        assert result["assignments"] == [] and result["unfilled"] == []
        assert result["jurisdiction"]["status"] == "curated"

    def test_nobody_left_after_narrowing_is_refused(self):
        result, _ = _fill(demand=[_open("a", 23, 6, 14)], roster=_roster([_employee(ANA, "Ana")]),
                          only_employee_ids=[uuid4()])
        assert result["status"] == "refused"
        assert "No active employees" in result["message"]

    def test_an_unmapped_state_is_disclosed_not_hidden(self):
        result, _ = _fill(demand=[_open("a", 23, 6, 14)], roster=_roster([_employee(ANA, "Ana")]),
                          jurisdiction={"state": "TX", "status": "unmapped"})
        assert result["status"] == "ready"
        assert "NOT verified for TX" in result["jurisdiction"]["message"]


class _DemandConn:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        return self.rows


class TestLoadVacantDemand:
    def test_the_query_asks_for_open_seats_in_drafts_and_published(self):
        shift_id, ana = uuid4(), UUID(ANA)
        conn = _DemandConn([{
            "id": shift_id, "role": "Shift Lead", "department": None,
            "starts_at": datetime(2026, 8, 23, 6, tzinfo=UTC), "ends_at": datetime(2026, 8, 23, 14, tzinfo=UTC),
            "break_minutes": 30, "required_staff": 2, "color": None, "notes": None, "kind": "work",
            "template_id": None, "job_id": None, "training_requirement_id": None, "employee_ids": [ana],
        }])
        demand = _run(week_builder._load_vacant_demand(
            conn, company_id=COMPANY, location_id=LOCATION, week_start=WEEK, week_end=date(2026, 8, 29),
        ))
        query, args = conn.calls[0]
        assert "HAVING COUNT(a.employee_id) < COALESCE(s.required_staff, 1)" in query
        assert "s.status = ANY($3::text[])" in query
        assert args[2] == ["draft", "published"]
        assert args[3] == datetime(2026, 8, 23, tzinfo=UTC) and args[4] == datetime(2026, 8, 30, tzinfo=UTC)
        assert args[5] is None and args[6] is None and args[7] is None
        assert demand == [{
            "key": str(shift_id), "source_shift_id": str(shift_id), "role": "Shift Lead", "department": None,
            "starts_at": datetime(2026, 8, 23, 6, tzinfo=UTC), "ends_at": datetime(2026, 8, 23, 14, tzinfo=UTC),
            "break_minutes": 30, "required_staff": 2, "color": None, "notes": None, "kind": "work",
            "template_id": None, "job_id": None, "training_requirement_id": None,
            "fixed_employee_ids": [ANA], "worked_minutes": 450,
        }]

    def test_filters_bind_as_arrays_and_label(self):
        job_id, shift_id = uuid4(), uuid4()
        conn = _DemandConn([])
        _run(week_builder._load_vacant_demand(
            conn, company_id=COMPANY, location_id=LOCATION, week_start=WEEK,
            job_ids=[job_id], shift_ids=[shift_id], role_ilike="lead", statuses=("published",),
        ))
        _, args = conn.calls[0]
        assert args[2] == ["published"]
        assert args[4] == datetime(2026, 8, 30, tzinfo=UTC)   # no week_end → seven days
        assert args[5] == [job_id] and args[6] == [shift_id] and args[7] == "lead"


class _BoundaryConn:
    def __init__(self, assignments, max_days=None):
        self.assignments = assignments
        self.max_days = max_days

    async def fetch(self, query, *args):
        if "FROM employees e" in query:
            return [{"id": UUID(ANA), "first_name": "Ana", "last_name": "Example", "job_title": "Lead",
                     "availability_state": "windows", "min_weekly_minutes": None, "target_weekly_minutes": None,
                     "max_weekly_minutes": 2400, "max_consecutive_days": self.max_days,
                     "allow_overtime": False, "prefer_extra_hours": False}]
        if "SELECT a.employee_id, s.id AS shift_id" in query:
            assert args[3] == [UUID(ANA)]
            return [row for row in self.assignments if row["starts_at"] < args[2] and row["ends_at"] > args[1]]
        return []


def _db_assignment(day, start, end):
    return {"employee_id": UUID(ANA), "shift_id": uuid4(),
            "starts_at": datetime(2026, 8, day, start, tzinfo=UTC),
            "ends_at": datetime(2026, 8, day, end, tzinfo=UTC),
            "break_minutes": 0, "location_id": LOCATION, "status": "published"}


@pytest.mark.parametrize("split", [False, True])
@pytest.mark.parametrize("existing,demand", [
    ([_db_assignment(22, 19, 23)], _open("s", 23, 3, 7, job_id=None)),
    ([_db_assignment(30, 3, 7)], _open("s", 29, 19, 23, job_id=None)),
])
def test_rest_checks_use_real_roster_history_on_both_week_boundaries(existing, demand, split):
    roster = _run(week_builder._load_roster_context(
        _BoundaryConn(existing), company_id=COMPANY, location_id=LOCATION, week_start=WEEK,
    ))
    result, _ = _fill(demand=[demand], roster=roster, allow_split_shift=split)
    assert result["assignments"] == []
    assert result["unfilled"][0]["reason"] == "policy: less than 8h rest"
    assert result["hours_by_employee"][ANA] == 0


@pytest.mark.parametrize("max_days", [None, 14])
def test_consecutive_day_history_crosses_weeks_without_counting_previous_hours(max_days):
    count = max_days or 6
    history = [_db_assignment(day, 9, 13) for day in range(23 - count, 23)]
    roster = _run(week_builder._load_roster_context(
        _BoundaryConn(history, max_days), company_id=COMPANY, location_id=LOCATION, week_start=WEEK,
    ))
    result, _ = _fill(demand=[_open("s", 23, 9, 13, job_id=None)], roster=roster)
    assert result["unfilled"][0]["reason"] == "maximum consecutive days"
    assert result["hours_by_employee"][ANA] == 0


def test_adjacent_week_hours_do_not_consume_the_current_week_cap():
    history = [_db_assignment(day, 7, 15) for day in range(16, 22)]  # 48 hours, then a day off
    roster = _run(week_builder._load_roster_context(
        _BoundaryConn(history), company_id=COMPANY, location_id=LOCATION, week_start=WEEK,
    ))
    result, _ = _fill(demand=[_open("s", 23, 7, 11, job_id=None)], roster=roster)
    assert len(result["assignments"]) == 1 and result["hours_by_employee"][ANA] == 240


def test_fill_counts_seats_for_the_cap_and_returns_a_day_split():
    people = [_employee(str(uuid4()), f"Employee {i}", lead=False) for i in range(7)]
    result, _ = _fill(
        demand=[_open(f"s{day}", day, 9, 13, job_id=None, required=7) for day in range(23, 29)],
        roster=_roster(people),
    )
    assert len(result["assignments"]) == 42
    requests, error = week_builder.vacant_fill_edit_requests(result["assignments"])
    assert requests == [] and "42 schedule operations" in error and "2 batches" in error
    requests, error = week_builder.vacant_fill_edit_requests(result["assignments"][:40])
    assert len(requests) == 40 and error is None
    assert requests[0]["to_employee_id"] == result["assignments"][0]["employee_id"]

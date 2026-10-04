"""DB-free regressions for schedule planning, apply, and full-week ownership."""

import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.matcha.services.scheduling import (
    location_profile, schedule_breaks, schedule_compliance, schedule_guidance,
    shift_writes, week_builder,
)
from app.matcha.services.scheduling.autopilot.engine import generate_autopilot_demand
from app.matcha.services.scheduling.autopilot.windows import off_week_demand_refusal

UTC = timezone.utc
WEEK = date(2026, 10, 4)
COMPANY, LOCATION = uuid4(), uuid4()
EMPLOYEE = str(uuid4())


def _shift(key="one", *, day=0, hour=8, hours=4, required=1):
    start = datetime.combine(WEEK + timedelta(days=day), time(hour), tzinfo=UTC)
    end = start + timedelta(hours=hours)
    return dict(key=key, source_shift_id=None, starts_at=start, ends_at=end,
                worked_minutes=int(hours * 60), break_minutes=0, required_staff=required,
                role="Crew", kind="work", fixed_employee_ids=[], job_id=None,
                proposed_assignments=[{"employee_id": EMPLOYEE, "employee_name": "Employee"}])


def _employee(ident=EMPLOYEE):
    return dict(id=ident, name="Employee", availability_state="always_available", jobs=[],
                allow_overtime=True, max_consecutive_days=7, max_weekly_minutes=None)


def _plan(demand, *, employees=None, unavailable=None, blocked=None):
    return week_builder.build_plan(
        demand=demand, employees=employees or [_employee()], availability={},
        existing_assignments=[], adjacent_assignments=[], unavailable_ranges=unavailable or {},
        exclude_employee_ids=set(), employee_hour_caps={}, gated_job_ids=set(),
        blocked_pairs=blocked or set(),
    )


@pytest.mark.parametrize("day,away_offset", [(1, 2), (6, 7)])
def test_overnight_planning_checks_time_away_after_midnight_and_week_end(day, away_offset):
    shift = _shift(day=day, hour=22, hours=4)
    away = WEEK + timedelta(days=away_offset)
    plan = _plan([shift], unavailable={EMPLOYEE: [(away, away)]})
    assert plan["metrics"]["filled_positions"] == 0
    assert plan["unfilled"][0]["reason_code"] == "approved_time_away"


def test_time_away_interval_is_half_open_and_checks_whole_date_range():
    start = datetime.combine(WEEK, time(22), tzinfo=UTC)
    midnight = datetime.combine(WEEK + timedelta(days=1), time.min, tzinfo=UTC)
    away = {EMPLOYEE: [(midnight.date(), midnight.date())]}
    assert not week_builder._has_time_away(EMPLOYEE, start, midnight, away)
    assert week_builder._has_time_away(EMPLOYEE, start, midnight + timedelta(seconds=1), away)
    assert not week_builder._has_time_away(EMPLOYEE, start, start, away)
    assert week_builder._has_time_away(EMPLOYEE, start, start + timedelta(days=3), away)


@pytest.mark.asyncio
async def test_roster_time_away_loader_includes_final_week_spillover(monkeypatch):
    queries = []
    away = WEEK + timedelta(days=8)

    class Conn:
        async def fetch(self, sql, *args):
            queries.append((sql, args))
            if "SELECT e.id, e.first_name" in sql:
                return [{"id": UUID(EMPLOYEE), "first_name": "Employee", "last_name": None,
                         "availability_state": "always_available", "max_consecutive_days": None}]
            if "FROM pto_requests" in sql and args[1] <= away <= args[2]:
                return [{"employee_id": UUID(EMPLOYEE), "start_date": away, "end_date": away}]
            return []

    monkeypatch.setattr(week_builder, "fetch_availability", AsyncMock(return_value={}))
    roster = await week_builder._load_roster_context(
        Conn(), company_id=COMPANY, location_id=LOCATION, week_start=WEEK,
    )
    assert roster["unavailable_ranges"] == {EMPLOYEE: [(away, away)]}
    away_query = next(args for sql, args in queries if "FROM pto_requests" in sql)
    assert away_query[1:] == (WEEK - timedelta(days=1), WEEK + timedelta(days=8))


@pytest.mark.asyncio
async def test_snapshot_reuses_loaded_autopilot_roster_and_keeps_hash_contract(monkeypatch):
    roster = dict(employees=[_employee()], availability={}, existing_assignments=[],
                  adjacent_assignments=[], unavailable_ranges={}, gated_job_ids=set())
    loader = AsyncMock(side_effect=AssertionError("must reuse the forecast roster"))
    monkeypatch.setattr(week_builder, "_load_roster_context", loader)
    monkeypatch.setattr(week_builder, "_load_week_shift_state", AsyncMock(return_value=[]))
    demand = [_shift()]
    snapshot, actual, name = await week_builder._planning_snapshot(
        None, company_id=COMPANY, location_id=LOCATION, week_start=WEEK,
        source_mode="autopilot", week_template_id=None,
        demand_override=demand, roster_override=roster,
    )
    assert actual is demand and name is None
    assert snapshot["employees"] is roster["employees"]
    assert "profile" not in snapshot and "profile_bundle" not in snapshot
    loader.assert_not_awaited()


@pytest.mark.asyncio
async def test_snapshot_loads_time_away_through_actual_long_demand_end(monkeypatch):
    demand = [_shift(hours=24 * 12)]
    loader = AsyncMock(return_value={"employees": []})
    monkeypatch.setattr(week_builder, "_load_roster_context", loader)
    monkeypatch.setattr(week_builder, "_load_week_shift_state", AsyncMock(return_value=[]))
    monkeypatch.setattr(week_builder, "_load_existing_demand", AsyncMock(return_value=demand))
    await week_builder._planning_snapshot(
        None, company_id=COMPANY, location_id=LOCATION, week_start=WEEK,
        source_mode="existing", week_template_id=None,
    )
    assert loader.await_args.kwargs["time_away_end"] == demand[0]["ends_at"].date()


def test_static_scarcity_is_counted_once_per_shift(monkeypatch):
    calls = 0
    original = week_builder._job_qualified

    def counted(*args):
        nonlocal calls
        calls += 1
        return original(*args)

    monkeypatch.setattr(week_builder, "_job_qualified", counted)
    plan = _plan([_shift(required=3)], employees=[_employee(str(uuid4())) for _ in range(6)])
    assert plan["metrics"]["filled_positions"] == 3
    # Initial pool6 + three dynamic pools6,5,4. Previously initial pool was
    # recomputed per seat (18 +15 =33); mutable assignment checks still run.
    assert calls == 21


@pytest.mark.asyncio
async def test_coverage_profile_reuses_bundle_job_names_without_queries():
    job = uuid4()
    bundle = {"profile": {"leader_job_ids": [job], "operating_hours": {}},
              "leader_jobs": [{"id": str(job), "name": "Shift Lead"}]}
    profile = await week_builder._coverage_profile(
        None, company_id=COMPANY, location_id=LOCATION, profile_bundle=bundle,
    )
    assert profile["leader_job_ids"] == [str(job)]
    assert profile["leader_job_names"] == ["Shift Lead"]


def _persisted_hours(total_hours):
    rows, remaining = [], total_hours
    for day in range(2, 7):
        hours = min(8, remaining)
        start = datetime.combine(WEEK + timedelta(days=day), time(8), tzinfo=UTC)
        rows.append(dict(employee_id=EMPLOYEE, shift_id=f"existing-{day}", starts_at=start,
                         ends_at=start + timedelta(hours=hours), break_minutes=0,
                         worked_minutes=int(hours * 60)))
        remaining -= hours
    return rows


def _preflight_setup(monkeypatch, *, state="NY", age=16, invalid_day=None):
    seen = []

    async def checker(_conn, _company, **kwargs):
        context = kwargs["planning_context"]
        seen.append((kwargs["starts_at"], context))
        result = schedule_compliance.evaluate_shift_for_employee(
            state=state, shift_hours=(kwargs["ends_at"] - kwargs["starts_at"]).total_seconds() / 3600,
            break_minutes=kwargs["break_minutes"], week_hours=context.week_hours,
            min_rest_gap_hours=context.min_rest_gap_hours, age=age,
        )
        if kwargs["starts_at"].date() == invalid_day:
            result.append(dict(check="schedule_eligibility", code="credential_missing", severity="block",
                               message="Missing credential for this job."))
        return result

    monkeypatch.setattr(week_builder, "check_shift_compliance", checker)
    monkeypatch.setattr(week_builder, "get_company_features", AsyncMock(return_value={}))
    monkeypatch.setattr(week_builder, "fetch_lapse_items", AsyncMock(return_value={}))
    return seen


@pytest.mark.asyncio
async def test_rejected_credential_sibling_does_not_poison_later_weekly_limit(monkeypatch):
    seen = _preflight_setup(monkeypatch, invalid_day=WEEK)
    shifts = [_shift("restricted", day=0, hours=5), _shift("valid", day=1, hours=5)]

    def build(blocked, _reasons):
        return _plan(shifts, blocked=blocked)

    plan, _advisories = await week_builder._plan_with_preflight(
        None, company_id=COMPANY, location_id=LOCATION, build=build,
        existing_assignments=_persisted_hours(40), adjacent_assignments=[], week_start_weekday=0,
    )
    assert [(s["key"], a["employee_id"]) for s in plan["shifts"] for a in s["proposed_assignments"]] == [("valid", EMPLOYEE)]
    assert [ctx.week_hours for _start, ctx in seen[:2]] == [45, 45]


@pytest.mark.asyncio
async def test_rejected_sibling_does_not_poison_later_rest_gap(monkeypatch):
    _preflight_setup(monkeypatch, invalid_day=WEEK)
    first, second = _shift("restricted", day=0, hour=18, hours=4), _shift("valid", day=1, hour=1, hours=4)
    seen = []

    async def checker(_conn, _company, **kwargs):
        context = kwargs["planning_context"]
        seen.append(context.min_rest_gap_hours)
        if kwargs["starts_at"].date() == WEEK:
            return [dict(code="credential_missing", severity="block", message="Missing credential.")]
        if context.min_rest_gap_hours is not None and context.min_rest_gap_hours < 11:
            return [dict(code="rest_gap", severity="block", message="Insufficient rest.")]
        return []

    monkeypatch.setattr(week_builder, "check_shift_compliance", checker)
    plan = {"shifts": [week_builder._iso(first), week_builder._iso(second)]}
    blocked, _warnings, _reasons = await week_builder._preflight_compliance(
        None, company_id=COMPANY, location_id=LOCATION, plan=plan,
        existing_assignments=[], adjacent_assignments=[],
    )
    assert blocked == {("restricted", EMPLOYEE)}
    assert seen == [None, None]


@pytest.mark.asyncio
async def test_minor_weekly_limit_counts_all_accepted_proposals_and_replans(monkeypatch):
    _preflight_setup(monkeypatch, state="CA", age=15)
    demand = [_shift(str(day), day=day, hours=7.5) for day in range(6)]
    plan, _ = await week_builder._plan_with_preflight(
        None, company_id=COMPANY, location_id=LOCATION,
        build=lambda blocked, _reasons: _plan(demand, blocked=blocked),
        existing_assignments=[], adjacent_assignments=[], week_start_weekday=0,
    )
    assert plan["metrics"]["filled_positions"] == 5
    assert plan["metrics"]["open_positions"] == 1


@pytest.mark.asyncio
async def test_weekly_minor_limit_preserves_subminute_duration_parity(monkeypatch):
    _preflight_setup(monkeypatch, state="CA", age=15)
    existing = _persisted_hours(40 - 30 / 3600)
    shift = _shift(hours=1 / 60)
    blocked, _warnings, _reasons = await week_builder._preflight_compliance(
        None, company_id=COMPANY, location_id=LOCATION, plan={"shifts": [week_builder._iso(shift)]},
        existing_assignments=existing, adjacent_assignments=[],
    )
    assert blocked == {("one", EMPLOYEE)}


def test_compliance_ledger_deduplicates_persisted_rows_and_normalizes_datetimes():
    existing = _persisted_hours(8)[:1]
    ledger = week_builder._PlannedComplianceLedger(
        existing_assignments=existing, adjacent_assignments=existing, week_start_weekday=0,
    )
    shift = week_builder._iso(_shift(hours=4))
    assert ledger.context(shift, EMPLOYEE).week_hours == 12
    ledger.accept(shift, EMPLOYEE)
    assert ledger.context(_shift(day=1, hours=4), EMPLOYEE).week_hours == 16


def _engine(profile):
    return generate_autopilot_demand(
        week_start=WEEK, profile=profile, jobs=[{"id": str(uuid4()), "name": "Crew"}],
        roster={"employees": [_employee()]}, gated_job_ids=set(),
        sales_by_day={}, weather_by_day={}, history_shifts=[],
    )


def test_autopilot_rejects_opening_buffer_before_week():
    with pytest.raises(ValueError, match="opening prep buffer starts before"):
        _engine({"operating_hours": {"0": {"open": "00:15", "close": "04:15"}},
                 "open_buffer_minutes": 30, "min_floor_staff": 1})


def test_autopilot_rejects_final_overnight_split_start_in_next_week():
    with pytest.raises(ValueError, match="starting outside this schedule week"):
        _engine({"operating_hours": {"6": {"open": "18:00", "close": "06:00"}},
                 "min_floor_staff": 1, "autopilot_shift_min_minutes": 240,
                 "autopilot_shift_max_minutes": 240})


def test_autopilot_allows_final_overnight_end_in_next_week():
    result = _engine({"operating_hours": {"6": {"open": "22:00", "close": "02:00"}},
                      "min_floor_staff": 1})
    assert len(result.demand) == 1
    assert result.demand[0]["starts_at"].date() == WEEK + timedelta(days=6)
    assert result.demand[0]["ends_at"].date() == WEEK + timedelta(days=7)
    assert off_week_demand_refusal(WEEK, result.demand) is None


class _ApplyConn:
    def __init__(self, run, *, live=None, away=()):
        self.run, self.live, self.away = run, live or {}, list(away)
        self.operations = []

    @asynccontextmanager
    async def transaction(self):
        yield self

    async def fetchrow(self, sql, *args):
        self.operations.append((sql, args))
        return self.run if "schedule_generation_runs" in sql else self.live.get(args[0])

    async def fetchval(self, sql, *args):
        self.operations.append((sql, args))
        return 0

    async def fetch(self, sql, *args):
        self.operations.append((sql, args))
        return self.away if "FROM pto_requests" in sql else []

    async def execute(self, sql, *args):
        self.operations.append((sql, args))
        return "UPDATE 1"


def _apply_setup(monkeypatch, conn, snapshot):
    @asynccontextmanager
    async def connection():
        yield conn
    monkeypatch.setattr(week_builder, "connection_or_direct", connection)
    monkeypatch.setattr(week_builder, "_week_rules_gate", AsyncMock(return_value=None))
    monkeypatch.setattr(week_builder, "_week_shift_counts", AsyncMock(return_value={"draft": 0, "published": 0}))
    monkeypatch.setattr(week_builder, "_planning_snapshot", AsyncMock(return_value=(snapshot, [], None)))
    monkeypatch.setattr(week_builder, "jurisdiction_rule_status", AsyncMock(return_value={"state": "CA", "status": "curated"}))
    monkeypatch.setattr(week_builder, "lock_scheduling_employees", AsyncMock())
    monkeypatch.setattr(week_builder, "fetch_availability", AsyncMock(return_value={}))
    monkeypatch.setattr(week_builder, "find_conflicts", AsyncMock(return_value=[]))
    monkeypatch.setattr(week_builder, "fetch_effective_job_employee_ids", AsyncMock(return_value={UUID(EMPLOYEE)}))
    monkeypatch.setattr(week_builder, "check_shift_compliance", AsyncMock(return_value=[]))
    monkeypatch.setattr(week_builder, "apply_assignment_core", AsyncMock())
    monkeypatch.setattr(week_builder, "log_audit", AsyncMock())
    monkeypatch.setattr(week_builder, "_reconcile_warnings_best_effort", AsyncMock())


def _run(proposal, *, mode="existing", snapshot=None):
    return dict(id=uuid4(), location_id=LOCATION, week_start=WEEK, status="proposed",
                source_mode=mode, week_template_id=None, proposal=proposal,
                input_hash=week_builder._input_hash(snapshot or {"same": True}))


@pytest.mark.asyncio
async def test_apply_rechecks_fresh_time_away_across_final_night(monkeypatch):
    shift = _shift(day=6, hour=22, hours=4)
    shift_id = uuid4()
    shift["source_shift_id"] = str(shift_id)
    live = dict(shift, id=shift_id, location_id=LOCATION, status="draft",
                training_requirement_id=None, published_at=None)
    snapshot = {"same": True}
    away = WEEK + timedelta(days=7)
    conn = _ApplyConn(_run({"shifts": [week_builder._iso(shift)]}, snapshot=snapshot),
                      live={shift_id: live}, away=[{"employee_id": UUID(EMPLOYEE), "start_date": away, "end_date": away}])
    _apply_setup(monkeypatch, conn, snapshot)
    result = await week_builder.apply_week_draft(
        company_id=COMPANY, actor_user_id=None, generation_run_id=conn.run["id"],
        location_id=LOCATION, week_start=WEEK,
    )
    assert result["status"] == "created"
    assert result["dropped"][0]["reason"] == "employee has approved time away during this shift"
    week_builder.apply_assignment_core.assert_not_awaited()
    query = next(args for sql, args in conn.operations if "FROM pto_requests" in sql)
    assert query[1] <= away <= query[2]
    assert "pg_advisory_xact_lock" in conn.operations[0][0]
    assert conn.operations[0][1] == (f"schedule-materialization:{COMPANY}:{LOCATION}",)
    assert conn.operations[1][1] == (f"schedule-week:{COMPANY}:{LOCATION}:{WEEK}",)


@pytest.mark.asyncio
@pytest.mark.parametrize("day", [-1, 7])
async def test_legacy_autopilot_apply_marks_offweek_starts_stale_before_creation(monkeypatch, day):
    conn = _ApplyConn(_run({"shifts": [week_builder._iso(_shift(day=day))]}, mode="autopilot"))
    _apply_setup(monkeypatch, conn, {"same": True})
    create = AsyncMock()
    monkeypatch.setattr(week_builder, "create_shift_core", create)
    result = await week_builder.apply_week_draft(
        company_id=COMPANY, actor_user_id=None, generation_run_id=conn.run["id"],
        location_id=LOCATION, week_start=WEEK,
    )
    assert result["status"] == "error" and "outside this schedule week" in result["message"]
    assert any("status='stale'" in sql for sql, _ in conn.operations)
    week_builder._planning_snapshot.assert_not_awaited()
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_week_scope_locks_are_deduplicated_and_stably_ordered():
    conn = _ApplyConn({})
    locations = sorted([uuid4(), uuid4()], key=str)
    await shift_writes.lock_scheduling_weeks(
        conn, COMPANY, [(locations[1], WEEK), (locations[0], WEEK + timedelta(days=7)),
                        (locations[0], WEEK), (locations[1], WEEK)],
    )
    assert [args[0] for _, args in conn.operations] == [
        f"schedule-materialization:{COMPANY}:{locations[0]}",
        f"schedule-materialization:{COMPANY}:{locations[1]}",
        f"schedule-week:{COMPANY}:{locations[0]}:{WEEK}",
        f"schedule-week:{COMPANY}:{locations[0]}:{WEEK + timedelta(days=7)}",
        f"schedule-week:{COMPANY}:{locations[1]}:{WEEK}",
    ]


@pytest.mark.asyncio
async def test_bulk_template_writer_locks_all_locations_and_weeks_before_writes(monkeypatch):
    operations = []
    locations = [uuid4(), uuid4()]

    class Conn:
        async def fetchval(self, sql, *args):
            operations.append(("lock", args[0]))
        async def fetch(self, sql, *args):
            operations.append(("write", args[1]))
            return [{"id": uuid4()} for _ in args[6]]

    async def plans(*_args, **kwargs):
        operations.append(("plans", kwargs["location_id"]))
        return [object() for _ in kwargs["windows"]]

    monkeypatch.setattr(location_profile, "resolve_week_start_weekday", AsyncMock(return_value=0))
    monkeypatch.setattr(schedule_guidance, "resolve_open_shift_break_plans", plans)
    monkeypatch.setattr(schedule_breaks, "minimum_meal_break_minutes", lambda _: 0)
    from app.matcha.services.scheduling import shift_compliance
    monkeypatch.setattr(shift_compliance, "check_shift_compliance", AsyncMock(return_value=[]))
    blocks = [dict(id=uuid4(), name="Crew", role="Crew", department=None, location_id=loc,
                   start_time=time(8), end_time=time(12), days_of_week=[0, 1], break_minutes=0,
                   required_staff=1, color=None, notes=None, job_id=None) for loc in locations]
    result = await shift_writes.generate_week_template_shifts(
        Conn(), COMPANY, blocks=blocks, start_date=WEEK, end_date=WEEK + timedelta(days=8), created_by=uuid4(),
    )
    assert result["created"] == 8
    assert [kind for kind, _ in operations[:6]] == ["lock"] * 6
    assert [key for kind, key in operations if kind == "lock"] == [
        *[f"schedule-materialization:{COMPANY}:{loc}" for loc in sorted(locations, key=str)],
        *[f"schedule-week:{COMPANY}:{loc}:{week}" for loc in sorted(locations, key=str)
        for week in [WEEK, WEEK + timedelta(days=7)]],
    ]


@pytest.mark.asyncio
async def test_preflight_orders_offset_datetimes_by_instant(monkeypatch):
    _preflight_setup(monkeypatch)
    earlier = week_builder._iso(_shift("earlier", hour=9))
    later = week_builder._iso(_shift("later", hour=15))
    later["starts_at"], later["ends_at"] = "2026-10-04T08:00:00-07:00", "2026-10-04T12:00:00-07:00"
    observed = []

    async def checker(_conn, _company, **kwargs):
        observed.append(kwargs["starts_at"])
        return []

    monkeypatch.setattr(week_builder, "check_shift_compliance", checker)
    await week_builder._preflight_compliance(
        None, company_id=COMPANY, location_id=LOCATION,
        plan={"shifts": [later, earlier]}, existing_assignments=[],
    )
    assert observed == [datetime(2026, 10, 4, 9, tzinfo=UTC), datetime.fromisoformat(later["starts_at"])]


@pytest.mark.asyncio
async def test_shared_checker_uses_simulated_totals_without_persisted_hours_reads(monkeypatch):
    from app.matcha.services.scheduling import schedule_eligibility, shift_compliance
    monkeypatch.setattr(shift_compliance, "_location_state", AsyncMock(return_value=("CA", None)))
    monkeypatch.setattr(shift_compliance, "_location_timezone", AsyncMock(return_value="UTC"))
    monkeypatch.setattr(shift_compliance, "_employee_age", AsyncMock(return_value=(15, False)))
    monkeypatch.setattr(shift_compliance, "_meal_break_waiver_on_file", AsyncMock(return_value=False))
    monkeypatch.setattr(schedule_eligibility, "schedule_eligibility_violations", AsyncMock(return_value=[]))
    hours = AsyncMock(side_effect=AssertionError("should use simulated ledger"))
    rest = AsyncMock(side_effect=AssertionError("should use simulated ledger"))
    monkeypatch.setattr(shift_compliance, "_week_hours", hours)
    monkeypatch.setattr(shift_compliance, "_min_rest_gap", rest)
    shift = _shift(hours=7.5)
    violations = await shift_compliance.check_shift_compliance(
        None, COMPANY, location_id=LOCATION, employee_id=UUID(EMPLOYEE),
        starts_at=shift["starts_at"], ends_at=shift["ends_at"], break_minutes=0, lapse_items=[],
        planning_context=shift_compliance.PlannedShiftComplianceContext(45, 16),
    )
    assert any(item["severity"] == "block" and item["check"] == "minor_hours" for item in violations)
    hours.assert_not_awaited()
    rest.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("anchor_changes", [False, True])
async def test_two_manual_fullweek_applies_serialize_before_empty_week_check(monkeypatch, anchor_changes):
    snapshot = {"same": True}
    proposal = {"shifts": [week_builder._iso(_shift(day=1 if anchor_changes else 0))]}
    current_weekday = 0
    committed = []
    scope_lock = asyncio.Lock()
    connections = []

    class Conn(_ApplyConn):
        def __init__(self):
            super().__init__(_run(proposal, mode="autopilot", snapshot=snapshot))
            self.local = []
            self.held = False

        @asynccontextmanager
        async def transaction(self):
            try:
                yield self
                committed.extend(self.local)
            finally:
                if self.held:
                    scope_lock.release()

        async def fetchval(self, sql, *args):
            self.operations.append((sql, args))
            if "pg_advisory_xact_lock" in sql:
                assert args[0].startswith(("schedule-materialization:", "schedule-week:"))
                if args[0].startswith("schedule-materialization:"):
                    await scope_lock.acquire()
                    self.held = True
            return 0

    connections.extend([Conn(), Conn()])
    first, second = connections
    if anchor_changes:
        second.run["week_start"] = WEEK + timedelta(days=1)
    _apply_setup(monkeypatch, first, snapshot)

    async def weekday(*_args, **_kwargs):
        return current_weekday

    monkeypatch.setattr(week_builder, "resolve_week_start_weekday", weekday)

    @asynccontextmanager
    async def connection():
        yield connections.pop(0)

    async def counts(conn, **kwargs):
        assert conn.held
        lo = kwargs["week_start"]
        hi = lo + timedelta(days=7)
        return {"draft": sum(lo <= row["starts_at"].date() < hi for row in [*committed, *conn.local]), "published": 0}

    async def create(conn, _company, **kwargs):
        nonlocal current_weekday
        new_id = uuid4()
        live = dict(kwargs, id=new_id, status="draft", published_at=None)
        conn.live[new_id] = live
        conn.local.append(live)
        if anchor_changes:
            # Location settings change after the old Sunday run validated its
            # anchor. The new Monday run has a different week mutex, but must
            # wait on the same materialization mutex before reading the week.
            current_weekday = 1
        # Yield while the first transaction owns the week; a second request
        # is ready to read emptiness, but must wait for the first to commit.
        await asyncio.sleep(0)
        return new_id

    monkeypatch.setattr(week_builder, "connection_or_direct", connection)
    monkeypatch.setattr(week_builder, "_week_shift_counts", counts)
    monkeypatch.setattr(week_builder, "create_shift_core", create)
    monkeypatch.setattr(week_builder, "resolve_job_by_name", AsyncMock(return_value=None))
    results = await asyncio.wait_for(asyncio.gather(*[
        week_builder.apply_week_draft(
            company_id=COMPANY, actor_user_id=None, generation_run_id=conn.run["id"],
            location_id=LOCATION, week_start=conn.run["week_start"],
        ) for conn in [first, second]
    ]), timeout=2)
    assert sorted(result["status"] for result in results) == ["created", "error"]
    assert len(committed) == 1
    if anchor_changes:
        assert first.operations[0][1] == second.operations[0][1]
        assert first.operations[1][1] != second.operations[1][1]
    week_builder.apply_assignment_core.assert_awaited_once()
    assert any("status='stale'" in sql for sql, _args in second.operations)
    for conn in [first, second]:
        assert "pg_advisory_xact_lock" in conn.operations[0][0]
        assert "pg_advisory_xact_lock" in conn.operations[1][0]
        assert "schedule_generation_runs" in conn.operations[2][0]


@pytest.mark.asyncio
async def test_apply_marks_proposal_stale_when_location_week_anchor_changed(monkeypatch):
    conn = _ApplyConn(_run({"shifts": [week_builder._iso(_shift())]}, mode="autopilot"))
    _apply_setup(monkeypatch, conn, {"same": True})
    create = AsyncMock()
    monkeypatch.setattr(week_builder, "create_shift_core", create)
    monkeypatch.setattr(week_builder, "resolve_week_start_weekday", AsyncMock(return_value=1))
    result = await week_builder.apply_week_draft(
        company_id=COMPANY, actor_user_id=None, generation_run_id=conn.run["id"],
        location_id=LOCATION, week_start=WEEK,
    )
    assert result["status"] == "error" and "weeks start on Monday" in result["message"]
    assert any("status='stale'" in sql for sql, _ in conn.operations)
    week_builder._week_shift_counts.assert_not_awaited()
    week_builder._planning_snapshot.assert_not_awaited()
    create.assert_not_awaited()

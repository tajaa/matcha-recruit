"""`planning_inputs.build_planning_inputs` — what a scheduler (human or Huume)
should SEE before picking a person. One builder behind the overview's
`roster_load` and the REST inputs route. Loaders patched; shaping real.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_planning_inputs.py -q
"""

import asyncio
from datetime import date, datetime, time, timezone
from unittest import mock
from uuid import UUID

from app.matcha.services.scheduling import planning_inputs, week_builder
from app.matcha.services.scheduling.assignment_guard import POLICY_DEFAULTS

UTC = timezone.utc
COMPANY = UUID("11111111-1111-1111-1111-111111111111")
LOCATION = UUID("c0ffeeee-0001-4001-8001-000000000001")
ANA = "33333333-3333-3333-3333-000000000001"
BEN = "33333333-3333-3333-3333-000000000002"
LEAD_JOB = "44444444-4444-4444-4444-000000000001"
WEEK = date(2026, 8, 23)
HOURS = {"0": None, "6": None, **{str(day): {"open": "08:00", "close": "17:00"} for day in range(1, 6)}}


def _run(coro):
    return asyncio.run(coro)


class _Conn:
    async def fetch(self, query, *args):
        assert "FROM schedule_jobs" in query
        return [{"id": UUID(LEAD_JOB), "name": "Shift Lead"}]


def _employee(employee_id, name, **overrides):
    item = {
        "id": employee_id, "name": name, "job_title": "Barista", "availability_state": "windows",
        "jobs": [{"job_id": LEAD_JOB, "qualification_status": "active", "qualified_from": None, "qualified_until": None},
                 {"job_id": "gone", "qualification_status": "revoked", "qualified_from": None, "qualified_until": None}],
        "min_weekly_minutes": 600, "target_weekly_minutes": 1200, "max_weekly_minutes": 2400,
        "max_consecutive_days": None, "allow_overtime": False, "prefer_extra_hours": True,
    }
    item.update(overrides)
    return item


def _assignment(employee_id, day, start_hour, end_hour):
    return {"employee_id": employee_id, "shift_id": f"db-{day}", "starts_at": datetime(2026, 8, day, start_hour, tzinfo=UTC),
            "ends_at": datetime(2026, 8, day, end_hour, tzinfo=UTC), "worked_minutes": (end_hour - start_hour) * 60,
            "location_id": str(LOCATION), "status": "published"}


def _open(shift_id, day, *, required=1, fixed=()):
    return {"key": shift_id, "source_shift_id": shift_id, "role": "Shift Lead", "job_id": LEAD_JOB,
            "starts_at": datetime(2026, 8, day, 6, tzinfo=UTC), "ends_at": datetime(2026, 8, day, 14, tzinfo=UTC),
            "required_staff": required, "fixed_employee_ids": list(fixed), "worked_minutes": 480}


def _build(*, employees, existing=(), demand=(), bundle=None, rules=None, availability=None, unavailable=None):
    roster = {
        "employees": list(employees), "availability": availability or {},
        "existing_assignments": list(existing), "unavailable_ranges": unavailable or {}, "gated_job_ids": {LEAD_JOB},
    }
    bundle = bundle or {
        "profile": {"operating_hours": HOURS, "leader_required": True},
        "template": {"blocks": [{"name": "Opener"}]}, "leader_jobs": [{"id": LEAD_JOB, "name": "Shift Lead"}],
    }

    async def fake_roster(conn, **kw):
        return roster

    async def fake_demand(conn, **kw):
        return list(demand)

    async def fake_bundle(conn, **kw):
        return bundle

    async def fake_rules(conn, company_id, location_id):
        return rules or {"state": "CA", "status": "curated"}

    with (
        mock.patch.object(week_builder, "_load_roster_context", fake_roster),
        mock.patch.object(week_builder, "_load_vacant_demand", fake_demand),
        mock.patch.object(planning_inputs, "load_profile_bundle", fake_bundle),
        mock.patch.object(planning_inputs, "jurisdiction_rule_status", fake_rules),
    ):
        return _run(planning_inputs.build_planning_inputs(
            _Conn(), company_id=COMPANY, location_id=LOCATION, week_start=WEEK,
        ))


class TestBuildPlanningInputs:
    def test_load_counts_only_this_week_and_the_heaviest_person_sorts_first(self):
        existing = [
            _assignment(ANA, 24, 6, 14), _assignment(ANA, 25, 6, 14),   # 16h inside the week
            _assignment(ANA, 20, 6, 14),                                # last week — ignored
            _assignment(BEN, 26, 8, 12),                                # 4h
        ]
        inputs = _build(employees=[_employee(BEN, "Ben"), _employee(ANA, "Ana")], existing=existing)
        assert inputs["week_start"] == "2026-08-23" and inputs["week_end"] == "2026-08-29"
        assert [person["name"] for person in inputs["roster"]] == ["Ana", "Ben"]
        assert inputs["roster"][0]["load"] == {"minutes": 960, "shifts": 2, "days": ["2026-08-24", "2026-08-25"]}
        assert inputs["roster"][1]["load"] == {"minutes": 240, "shifts": 1, "days": ["2026-08-26"]}
        assert inputs["roster_truncated"] is False

    def test_each_person_carries_jobs_windows_time_away_and_caps(self):
        availability = {ANA: {0: [(time(6), time(14))], 3: [(time(6), time(12)), (time(16), time(22))]}}
        unavailable = {ANA: [(date(2026, 8, 27), date(2026, 8, 28))]}
        inputs = _build(employees=[_employee(ANA, "Ana")], availability=availability, unavailable=unavailable)
        ana = inputs["roster"][0]
        assert ana["employee_id"] == ANA and ana["job_title"] == "Barista"
        assert ana["jobs"] == ["Shift Lead"]                       # active only, by name
        assert ana["availability_state"] == "windows"
        assert ana["windows"] == {"0": ["06:00–14:00"], "3": ["06:00–12:00", "16:00–22:00"]}
        assert ana["time_away"] == [{"start": "2026-08-27", "end": "2026-08-28"}]
        assert ana["caps"] == {
            "max_weekly_minutes": 2400, "target_weekly_minutes": 1200, "min_weekly_minutes": 600,
            "allow_overtime": False, "max_consecutive_days": None, "prefer_extra_hours": True,
        }
        assert ana["load"] == {"minutes": 0, "shifts": 0, "days": []}

    def test_open_slots_report_how_many_seats_are_still_open(self):
        inputs = _build(employees=[_employee(ANA, "Ana")], demand=[_open("s1", 24, required=2, fixed=[BEN]), _open("s2", 25)])
        assert inputs["open_slots"] == [
            {"shift_id": "s1", "role": "Shift Lead", "job_id": LEAD_JOB, "starts_at": "2026-08-24T06:00:00+00:00",
             "ends_at": "2026-08-24T14:00:00+00:00", "required_staff": 2, "open": 1},
            {"shift_id": "s2", "role": "Shift Lead", "job_id": LEAD_JOB, "starts_at": "2026-08-25T06:00:00+00:00",
             "ends_at": "2026-08-25T14:00:00+00:00", "required_staff": 1, "open": 1},
        ]

    def test_policy_jurisdiction_week_rules_and_profile_ride_along(self):
        inputs = _build(employees=[], rules={"state": "TX", "status": "unmapped"})
        assert inputs["policy"] == dict(POLICY_DEFAULTS)
        assert inputs["jurisdiction"]["status"] == "unmapped" and "NOT verified for TX" in inputs["jurisdiction"]["message"]
        assert inputs["week_rules"] == {"established": True, "missing": []}
        assert inputs["profile"] == {
            "operating_hours": HOURS, "leader_required": True, "leader_job_names": ["Shift Lead"],
        }

    def test_unsaved_week_rules_are_reported_not_a_gate(self):
        inputs = _build(employees=[], bundle={"profile": None, "template": None, "leader_jobs": []})
        assert inputs["week_rules"]["established"] is False
        assert "operating_hours" in inputs["week_rules"]["missing"]
        assert inputs["profile"] == {"operating_hours": {}, "leader_required": None, "leader_job_names": []}

    def test_the_roster_cap_sets_the_truncated_flag(self):
        with mock.patch.object(planning_inputs, "_ROSTER_LOAD_CAP", 1):
            inputs = _build(employees=[_employee(ANA, "Ana"), _employee(BEN, "Ben")])
        assert len(inputs["roster"]) == 1 and inputs["roster_truncated"] is True


class TestCompactRosterLoad:
    def test_the_model_slice_keeps_load_jobs_caps_and_drops_windows(self):
        inputs = _build(employees=[_employee(ANA, "Ana")], existing=[_assignment(ANA, 24, 6, 14)],
                        availability={ANA: {0: [(time(6), time(14))]}},
                        unavailable={ANA: [(date(2026, 8, 27), date(2026, 8, 27))]})
        assert planning_inputs.compact_roster_load(inputs) == [{
            "employee_id": ANA, "name": "Ana", "jobs": ["Shift Lead"], "availability_state": "windows",
            "scheduled_minutes": 480, "shift_count": 1, "days": ["2026-08-24"],
            "time_away": [{"start": "2026-08-27", "end": "2026-08-27"}],
            "max_weekly_minutes": 2400, "allow_overtime": False,
        }]

    def test_an_empty_or_missing_roster_is_an_empty_list(self):
        assert planning_inputs.compact_roster_load({}) == []
        assert planning_inputs.compact_roster_load({"roster": []}) == []

"""Scheduled labor cost — the arithmetic, exhaustively.

Pure-function suite: the engine takes rows, pay profiles and a rule dict, so
none of this needs a database. The thresholds and multipliers come from the
real `schedule_compliance` table rather than fixtures, so a change to the
cited law is caught here rather than in production.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.matcha.services.scheduling import labor_cost as lc
from app.matcha.services.scheduling.schedule_compliance import rules_for_state
from app.matcha.services.scheduling.schedule_rules import summarize_shifts

WEEK = date(2026, 9, 13)   # a Sunday
CA = rules_for_state("CA")
NY = rules_for_state("NY")
UNMAPPED = rules_for_state("ZZ")   # no curated state, no db_rules -> federal floor


def shift(employee_id: str, day: int, minutes: int, hour: int = 9) -> dict:
    return {
        "employee_id": employee_id,
        "starts_at": datetime(2026, 9, day, hour, tzinfo=timezone.utc),
        "worked_minutes": minutes,
    }


def hourly(employee_id: str, rate: str) -> dict[str, lc.PayProfile]:
    return {employee_id: lc.PayProfile(employee_id, Decimal(rate), lc.HOURLY, False)}


# ── Straight time ────────────────────────────────────────────────────────


def test_five_eights_at_eighteen_is_seven_twenty_and_no_overtime():
    week = lc.cost_week(
        [shift("g", 14 + i, 480) for i in range(5)], hourly("g", "18"), CA, week_start=WEEK,
    )
    assert week.payload()["total"] == 720.00
    assert week.ot_minutes == 0
    assert week.payload()["ot_premium"] == 0.0


def test_break_minutes_are_the_caller_s_job_not_the_engine_s():
    """`worked_minutes` arrives net of the break — the engine never re-subtracts."""
    week = lc.cost_week([shift("g", 14, 450)], hourly("g", "20"), CA, week_start=WEEK)
    assert week.payload()["total"] == 150.00   # 7.5h


# ── Weekly overtime (FLSA § 207(a)) ──────────────────────────────────────


def test_forty_six_hours_in_an_unmapped_state_prices_on_the_federal_floor():
    rows = [shift("m", 14 + i, 480) for i in range(5)] + [shift("m", 19, 360)]
    week = lc.cost_week(rows, hourly("m", "20"), UNMAPPED, week_start=WEEK)
    payload = week.payload()
    # 40h straight ($800) + 6h at 1.5x ($180)
    assert payload["total"] == 980.00
    assert payload["ot_minutes"] == 360
    assert payload["ot_premium"] == 60.00      # the avoidable half-rate part
    assert payload["basis"]["overtime_citation"] == "FLSA, 29 U.S.C. § 207(a)"
    assert payload["basis"]["daily_ot_hours"] is None


def test_new_york_has_no_daily_overtime_so_a_long_day_alone_costs_straight_time():
    week = lc.cost_week([shift("n", 14, 660)], hourly("n", "20"), NY, week_start=WEEK)
    assert week.payload()["total"] == 220.00   # 11h straight, no CA-style daily rule
    assert week.ot_minutes == 0


def test_new_york_still_pays_weekly_overtime():
    rows = [shift("n", 14 + i, 480) for i in range(5)] + [shift("n", 19, 360)]
    week = lc.cost_week(rows, hourly("n", "20"), NY, week_start=WEEK)
    assert week.payload()["ot_minutes"] == 360
    assert week.payload()["total"] == 980.00


# ── California daily overtime + doubletime (Cal. Lab. Code § 510) ────────


def test_twelve_hour_california_day_is_overtime_but_not_yet_doubletime():
    week = lc.cost_week([shift("c", 14, 720)], hourly("c", "20"), CA, week_start=WEEK)
    person = week.employees[0]
    assert person.straight_cost == Decimal("160")     # 8h
    assert person.ot_minutes == 240 and person.doubletime_minutes == 0
    assert week.payload()["total"] == 280.00          # 160 + 4h * 20 * 1.5


def test_thirteen_hour_california_day_crosses_into_doubletime():
    week = lc.cost_week([shift("c", 14, 780)], hourly("c", "20"), CA, week_start=WEEK)
    person = week.employees[0]
    assert person.ot_minutes == 240                   # hours 9-12
    assert person.doubletime_minutes == 60            # hour 13
    assert week.payload()["total"] == 320.00          # 160 + 120 + 40


def test_daily_and_weekly_overtime_do_not_pyramid():
    """Six 9-hour CA days = 54h. Six hours are daily OT; the 48 straight-time
    hours then cross 40, making 8 more OT. An hour is never counted twice, so
    total OT is 14h and NOT 6 + 14."""
    week = lc.cost_week(
        [shift("c", 14 + i, 540) for i in range(6)], hourly("c", "20"), CA, week_start=WEEK,
    )
    person = week.employees[0]
    assert sum(day.straight_minutes for day in person.days) == 2400   # capped at 40h
    assert person.ot_minutes == 840                                   # 14h
    assert person.doubletime_minutes == 0
    assert week.payload()["total"] == 1220.00                         # 800 + 14h * 30


# ── Missing data degrades honestly, never to zero ────────────────────────


def test_an_employee_with_no_pay_rate_is_reported_unpriced_not_free():
    week = lc.cost_week([shift("u", 14, 480)], {}, CA, week_start=WEEK)
    payload = week.payload()
    assert payload["total"] == 0.0
    assert payload["unpriced_employee_ids"] == ["u"]
    assert payload["employees"][0]["priced"] is False
    assert payload["employees"][0]["reason"] == "no_pay_rate"
    # The hours are still there — only the money is missing.
    assert payload["employees"][0]["minutes"] == 480


def test_a_negative_rate_is_corrupt_data_and_refuses_to_price():
    profile = lc.resolve_pay_profile({"id": "x", "pay_rate": Decimal("-5")})
    assert profile.rate is None and profile.priced is False


def test_unpriced_people_do_not_contaminate_the_priced_total():
    pay = hourly("g", "18")
    week = lc.cost_week(
        [shift("g", 14, 480), shift("u", 14, 480)], pay, CA, week_start=WEEK,
    )
    assert week.payload()["total"] == 144.00
    assert week.payload()["unpriced_employee_count"] == 1


# ── Exempt / salaried ────────────────────────────────────────────────────


def test_exempt_pay_is_a_fixed_weekly_share_and_never_earns_overtime():
    pay = {"e": lc.PayProfile("e", Decimal("104000"), lc.EXEMPT, False)}
    week = lc.cost_week([shift("e", 14 + i, 480) for i in range(5)], pay, CA, week_start=WEEK)
    payload = week.payload()
    assert payload["salaried_total"] == 2000.00        # 104000 / 52
    assert payload["hourly_total"] == 0.0
    assert payload["employees"][0]["ot_minutes"] == 0
    assert [day["total"] for day in payload["employees"][0]["days"]] == [400.0] * 5


def test_a_sixth_shift_does_not_change_what_a_salaried_manager_costs():
    pay = {"e": lc.PayProfile("e", Decimal("104000"), lc.EXEMPT, False)}
    five = lc.cost_week([shift("e", 14 + i, 480) for i in range(5)], pay, CA, week_start=WEEK)
    six = lc.cost_week([shift("e", 14 + i, 480) for i in range(6)], pay, CA, week_start=WEEK)
    assert five.payload()["total"] == six.payload()["total"] == 2000.00


def test_salaried_day_shares_sum_to_the_week_exactly():
    """Three uneven days must not lose a cent to rounding."""
    pay = {"e": lc.PayProfile("e", Decimal("100000"), lc.EXEMPT, False)}
    week = lc.cost_week(
        [shift("e", 14, 300), shift("e", 15, 420), shift("e", 16, 380)],
        pay, CA, week_start=WEEK,
    )
    days = [day["total"] for day in week.payload()["employees"][0]["days"]]
    assert round(sum(days), 2) == week.payload()["salaried_total"]


# ── Classification inference (shared with wc_classmap) ───────────────────


@pytest.mark.parametrize(
    "rate,expected",
    [(Decimal("18"), lc.HOURLY), (Decimal("1999"), lc.HOURLY),
     (Decimal("2000"), lc.EXEMPT), (Decimal("104000"), lc.EXEMPT)],
)
def test_a_missing_classification_is_inferred_by_magnitude(rate, expected):
    profile = lc.resolve_pay_profile({"id": "a", "pay_rate": rate, "pay_classification": None})
    assert profile.classification == expected
    assert profile.inferred is True


def test_a_stored_classification_is_never_second_guessed():
    profile = lc.resolve_pay_profile(
        {"id": "a", "pay_rate": Decimal("104000"), "pay_classification": "hourly"},
    )
    assert profile.classification == lc.HOURLY and profile.inferred is False


# ── Open seats ───────────────────────────────────────────────────────────


def test_open_seats_price_at_the_job_s_default_rate():
    week = lc.cost_week(
        [], {}, CA, week_start=WEEK,
        open_seats=[{
            "job_id": "j1", "open": 2, "worked_minutes": 480,
            "starts_at": datetime(2026, 9, 14, 9, tzinfo=timezone.utc),
        }],
        job_rates={"j1": Decimal("17")},
    )
    payload = week.payload()
    assert payload["open_seat_total"] == 272.00      # 2 * 8h * 17
    assert payload["by_day"]["2026-09-14"] == 272.00


def test_an_open_seat_on_a_job_with_no_rate_is_unpriced_not_free():
    week = lc.cost_week(
        [], {}, CA, week_start=WEEK,
        open_seats=[{"job_id": "j2", "open": 3, "worked_minutes": 480}], job_rates={},
    )
    assert week.payload()["open_seat_total"] == 0.0
    assert week.payload()["unpriced_open_seats"] == 3


# ── Day rollup ───────────────────────────────────────────────────────────


def test_by_day_totals_add_up_to_the_week():
    pay = {**hourly("g", "18"), **hourly("m", "22")}
    rows = [shift("g", 14, 480), shift("g", 15, 480), shift("m", 15, 480)]
    week = lc.cost_week(rows, pay, CA, week_start=WEEK)
    payload = week.payload()
    assert round(sum(payload["by_day"].values()), 2) == payload["total"]
    assert payload["by_day"]["2026-09-14"] == 144.00


# ── The absent-not-zero contract at the serialization edge ───────────────


def test_summarize_shifts_omits_cost_entirely_when_the_caller_has_no_access():
    summary = summarize_shifts([])
    assert "cost" not in summary


def test_summarize_shifts_includes_cost_when_one_was_resolved():
    summary = summarize_shifts([], cost={"total": 0.0})
    assert summary["cost"] == {"total": 0.0}


# ── The rule table carries the multipliers, with citations ───────────────


def test_every_state_with_an_overtime_threshold_also_states_its_rate():
    for state in ("US", "CA", "NY"):
        rules = rules_for_state(state)
        assert rules.get("ot_multiplier") is not None, state
        assert rules["citations"].get("overtime_rate"), state
    assert rules_for_state("CA")["doubletime_multiplier"] == 2.0


# ── Who may see a wage ───────────────────────────────────────────────────


class TestLaborCostVisibility:
    """Flag AND role. `individual` is admitted by `require_admin_or_client`
    but must not read a company's payroll, and no role gets in without the
    company having bought the feature."""

    @staticmethod
    def _service(monkeypatch, *, enabled: bool):
        from app.matcha.services.scheduling import labor_cost_service as svc

        async def fake_features(company_id, conn=None):
            return {"labor_cost": enabled}

        monkeypatch.setattr(svc, "get_company_features", fake_features)
        return svc

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", ["admin", "client"])
    async def test_business_admins_see_cost_when_the_flag_is_on(self, monkeypatch, role):
        svc = self._service(monkeypatch, enabled=True)
        assert await svc.is_labor_cost_visible("co", role) is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", ["individual", "employee", "broker", "candidate", None])
    async def test_every_other_role_is_refused_even_with_the_flag_on(self, monkeypatch, role):
        svc = self._service(monkeypatch, enabled=True)
        assert await svc.is_labor_cost_visible("co", role) is False

    @pytest.mark.asyncio
    async def test_the_flag_off_refuses_a_business_admin(self, monkeypatch):
        svc = self._service(monkeypatch, enabled=False)
        assert await svc.is_labor_cost_visible("co", "client") is False

    @pytest.mark.asyncio
    async def test_a_feature_read_failure_leaves_a_review_uncosted_rather_than_raising(
        self, monkeypatch,
    ):
        """Cost is additive to a staged change. A broken feature read must not
        stop a manager staging a schedule edit."""
        from app.matcha.services.scheduling import labor_cost_service as svc

        async def boom(company_id, conn=None):
            raise RuntimeError("no pool")

        monkeypatch.setattr(svc, "get_company_features", boom)
        assert await svc.cost_delta_for_rows(
            None, company_id="co", location_id=None, weeks=[(WEEK, [], [])],
        ) is None
        assert await svc.review_cost_for_ops(
            None, company_id="co", location_id=None,
            ops=[{"kind": "assign", "shift_id": "s", "to_employee_id": "e",
                  "starts_at": "2026-09-14T09:00:00+00:00", "ends_at": "2026-09-14T17:00:00+00:00"}],
        ) is None


class TestFeatureFlagWiring:
    def test_labor_cost_is_off_by_default_and_requires_scheduling(self):
        from app.core.feature_flags import DEFAULT_COMPANY_FEATURES, FEATURE_REQUIRES

        assert DEFAULT_COMPANY_FEATURES["labor_cost"] is False
        assert FEATURE_REQUIRES["labor_cost"] == ("employee_schedule",)

    def test_labor_cost_is_in_no_tier_bundle(self):
        """Wage visibility is bought deliberately, never inherited by upgrading."""
        from app.core.feature_flags import TIER_REQUIRED_FEATURES

        for tier, features in TIER_REQUIRED_FEATURES.items():
            assert "labor_cost" not in features, tier


# ── Regressions from the 2026-09-13 review ───────────────────────────────


class TestUnpricedDaysAreNotFreeDays:
    """A day worked entirely by people with no rate on file must be
    distinguishable from a day nobody worked. `$0` beside a fully-staffed
    Tuesday reads as "Tuesday is free" and gets it staffed harder."""

    def test_a_day_with_only_unpriced_people_is_flagged_not_zeroed(self):
        week = lc.cost_week(
            [shift("g", 14, 480), shift("u", 15, 480)], hourly("g", "20"), CA, week_start=WEEK,
        )
        payload = week.payload()
        assert payload["by_day"]["2026-09-14"] == 160.00
        # Present (zero-filled) but named as unpriced, so the UI shows a dash.
        assert payload["by_day"]["2026-09-15"] == 0.0
        assert payload["unpriced_days"] == ["2026-09-15"]

    def test_a_genuine_day_off_is_zero_and_not_flagged(self):
        week = lc.cost_week([shift("g", 14, 480)], hourly("g", "20"), CA, week_start=WEEK)
        payload = week.payload()
        assert payload["by_day"]["2026-09-16"] == 0.0
        assert payload["unpriced_days"] == []

    def test_every_day_of_the_week_is_present(self):
        week = lc.cost_week([], {}, CA, week_start=WEEK)
        assert sorted(week.payload()["by_day"]) == [
            f"2026-09-{day}" for day in range(13, 20)
        ]


class TestAbsentIsNotUnpriced:
    """`employee_total` returning None for "not in this scenario" is how an
    unassignment rendered as "$620 → —, no pay rate on file" instead of as a
    $620 saving."""

    def test_a_priced_employee_absent_from_the_scenario_costs_zero(self):
        week = lc.cost_week([shift("g", 14, 480)], hourly("g", "20"), CA, week_start=WEEK)
        assert week.employee_total("someone-else", absent=Decimal("0")) == Decimal("0")

    def test_an_unpriced_employee_stays_none_even_with_an_absent_default(self):
        week = lc.cost_week([shift("u", 14, 480)], {}, CA, week_start=WEEK)
        assert week.employee_total("u", absent=Decimal("0")) is None

    def test_the_default_is_still_none_so_existing_callers_are_unchanged(self):
        week = lc.cost_week([shift("g", 14, 480)], hourly("g", "20"), CA, week_start=WEEK)
        assert week.employee_total("nobody") is None


class TestMultiplierGuard:
    """`_multiplier` merges values from catalog-extracted `db_rules`, which can
    carry the `NO_CAP` sentinel or any other non-numeric an approver let
    through. On the /week path an exception there would 500 the whole board."""

    def test_the_no_cap_sentinel_does_not_crash_the_cost_path(self):
        from app.matcha.services.scheduling.schedule_compliance import NO_CAP

        rules = {**dict(CA), "ot_multiplier": NO_CAP}
        week = lc.cost_week([shift("c", 14, 780)], hourly("c", "20"), rules, week_start=WEEK)
        # No usable OVERTIME rate ⇒ no overtime split, rather than one priced
        # at an invented multiplier. Doubletime still has its own valid rate,
        # so the 13th hour is unaffected: 12h straight + 1h at 2x.
        assert week.employees[0].ot_minutes == 0
        assert week.employees[0].doubletime_minutes == 60
        assert week.payload()["total"] == 280.00
        assert week.payload()["basis"]["daily_ot_hours"] is None
        assert week.payload()["basis"]["daily_doubletime_hours"] == 12

    def test_a_doubletime_threshold_without_its_rate_never_borrows_the_ot_rate(self):
        rules = {k: v for k, v in CA.items() if k != "doubletime_multiplier"}
        week = lc.cost_week([shift("c", 14, 780)], hourly("c", "20"), rules, week_start=WEEK)
        person = week.employees[0]
        # The 13th hour stays ordinary daily overtime instead of being priced
        # at 1.5x and called doubletime.
        assert person.doubletime_minutes == 0
        assert person.ot_minutes == 300
        assert week.payload()["basis"]["daily_doubletime_hours"] is None

    def test_a_string_rate_still_parses(self):
        rules = {**dict(CA), "ot_multiplier": "1.5"}
        week = lc.cost_week([shift("c", 14, 600)], hourly("c", "20"), rules, week_start=WEEK)
        assert week.employees[0].ot_minutes == 120


class TestApplyOps:
    """`_apply_ops` must model every kind in `schedule_chat._EDIT_KINDS`. A
    kind that slips through unmodelled reports a confident $0 for a change
    that costs real money — worse than reporting nothing, because a manager
    acts on it."""

    SHIFTS = {
        "a": {"starts_at": datetime(2026, 9, 14, 9, tzinfo=timezone.utc),
              "ends_at": datetime(2026, 9, 14, 17, tzinfo=timezone.utc), "break_minutes": 0},
        "b": {"starts_at": datetime(2026, 9, 15, 9, tzinfo=timezone.utc),
              "ends_at": datetime(2026, 9, 15, 21, tzinfo=timezone.utc), "break_minutes": 0},
    }

    @staticmethod
    def _rows():
        return [
            {"employee_id": "e1", "shift_id": "a",
             "starts_at": datetime(2026, 9, 14, 9, tzinfo=timezone.utc), "worked_minutes": 480},
            {"employee_id": "e2", "shift_id": "b",
             "starts_at": datetime(2026, 9, 15, 9, tzinfo=timezone.utc), "worked_minutes": 720},
        ]

    def test_every_edit_kind_is_modelled(self):
        from app.matcha.services.scheduling.schedule_chat import _EDIT_KINDS
        from app.matcha.services.scheduling import labor_cost_service as svc
        import inspect

        source = inspect.getsource(svc._apply_ops)
        for kind in _EDIT_KINDS:
            assert f'"{kind}"' in source, kind

    def test_retime_reprices_the_shift_instead_of_reporting_no_change(self):
        from app.matcha.services.scheduling.labor_cost_service import _apply_ops

        after = _apply_ops(self._rows(), [{
            "kind": "retime", "shift_id": "a", "break_minutes": 0,
            "starts_at": "2026-09-14T09:00:00+00:00", "ends_at": "2026-09-14T17:00:00+00:00",
            "new_starts_at": "2026-09-14T09:00:00+00:00", "new_ends_at": "2026-09-14T21:00:00+00:00",
        }], self.SHIFTS)
        moved = next(row for row in after if row["employee_id"] == "e1")
        assert moved["worked_minutes"] == 720      # was 480 — a real 4h increase

    def test_swap_exchanges_both_shifts_whole_assignee_sets(self):
        from app.matcha.services.scheduling.labor_cost_service import _apply_ops

        after = _apply_ops(self._rows(), [{
            "kind": "swap", "shift_id": "a", "second_shift_id": "b",
            "starts_at": "2026-09-14T09:00:00+00:00", "ends_at": "2026-09-14T17:00:00+00:00",
        }], self.SHIFTS)
        by_employee = {row["employee_id"]: row for row in after}
        assert by_employee["e1"]["shift_id"] == "b" and by_employee["e1"]["worked_minutes"] == 720
        assert by_employee["e2"]["shift_id"] == "a" and by_employee["e2"]["worked_minutes"] == 480

    def test_cancel_removes_everyone_on_the_shift(self):
        from app.matcha.services.scheduling.labor_cost_service import _apply_ops

        after = _apply_ops(self._rows(), [{
            "kind": "cancel", "shift_id": "a",
            "starts_at": "2026-09-14T09:00:00+00:00", "ends_at": "2026-09-14T17:00:00+00:00",
        }], self.SHIFTS)
        assert [row["employee_id"] for row in after] == ["e2"]

    def test_reassign_moves_the_seat(self):
        from app.matcha.services.scheduling.labor_cost_service import _apply_ops

        after = _apply_ops(self._rows(), [{
            "kind": "reassign", "shift_id": "a",
            "from_employee_id": "e1", "to_employee_id": "e3",
            "starts_at": "2026-09-14T09:00:00+00:00", "ends_at": "2026-09-14T17:00:00+00:00",
        }], self.SHIFTS)
        assert sorted(row["employee_id"] for row in after) == ["e2", "e3"]


class TestCostDeltaForRows:
    """The review block's own happy path.

    Only its refusal branches were covered before, and because
    `cost_delta_for_rows` swallows exceptions, a `NameError` inside it looked
    exactly like "this tenant has no labor_cost" — a dropped helper shipped
    undetected until ruff caught it. Exercise the real arithmetic here.
    """

    @staticmethod
    def _service(monkeypatch, pay):
        from app.matcha.services.scheduling import labor_cost_service as svc

        async def features(company_id, conn=None):
            return {"labor_cost": True}

        async def profiles(conn, *, company_id, employee_ids):
            return {eid: pay[eid] for eid in employee_ids if eid in pay}

        async def rules(conn, company_id, location_id):
            return CA

        monkeypatch.setattr(svc, "get_company_features", features)
        monkeypatch.setattr(svc, "load_pay_profiles", profiles)
        monkeypatch.setattr(svc, "_load_rules", rules)
        return svc

    @pytest.mark.asyncio
    async def test_adding_a_shift_reports_the_real_increase(self, monkeypatch):
        svc = self._service(monkeypatch, hourly("g", "20"))
        before = [shift("g", 14, 480)]
        block = await svc.cost_delta_for_rows(
            None, company_id="co", location_id=None,
            weeks=[(WEEK, before, before + [shift("g", 15, 480)])],
        )
        assert block["before"] == 160.00
        assert block["after"] == 320.00
        assert block["delta"] == 160.00
        assert block["by_employee"]["g"] == {"before": 160.00, "after": 320.00}

    @pytest.mark.asyncio
    async def test_removing_someone_s_only_shift_is_a_saving_not_a_dash(self, monkeypatch):
        svc = self._service(monkeypatch, hourly("g", "20"))
        block = await svc.cost_delta_for_rows(
            None, company_id="co", location_id=None, weeks=[(WEEK, [shift("g", 14, 480)], [])],
        )
        assert block["delta"] == -160.00
        # 0.00, NOT None — None means "no pay rate on file", and the UI copy
        # for it actively says so.
        assert block["by_employee"]["g"] == {"before": 160.00, "after": 0.0}

    @pytest.mark.asyncio
    async def test_an_unpriced_person_stays_none_on_both_sides(self, monkeypatch):
        svc = self._service(monkeypatch, {})
        block = await svc.cost_delta_for_rows(
            None, company_id="co", location_id=None, weeks=[(WEEK, [shift("u", 14, 480)], [])],
        )
        assert block["by_employee"]["u"] == {"before": None, "after": None}
        assert block["unpriced_employee_ids"] == ["u"]

    @pytest.mark.asyncio
    async def test_crossing_forty_hours_shows_up_as_overtime_premium(self, monkeypatch):
        svc = self._service(monkeypatch, hourly("g", "20"))
        before = [shift("g", 14 + i, 480) for i in range(5)]
        block = await svc.cost_delta_for_rows(
            None, company_id="co", location_id=None,
            weeks=[(WEEK, before, before + [shift("g", 19, 360)])],
        )
        assert block["ot_premium_before"] == 0.0
        assert block["ot_premium_after"] == 60.00
        assert block["delta"] == 180.00      # 6h at 1.5 x $20

    @pytest.mark.asyncio
    async def test_a_change_spanning_two_weeks_sums_both(self, monkeypatch):
        """Overtime is a per-week question, so each week is costed alone."""
        svc = self._service(monkeypatch, hourly("g", "20"))
        next_week = date(2026, 9, 20)
        block = await svc.cost_delta_for_rows(
            None, company_id="co", location_id=None,
            weeks=[
                (WEEK, [], [shift("g", 14, 480)]),
                (next_week, [], [shift("g", 21, 480)]),
            ],
        )
        assert block["after"] == 320.00
        assert block["by_employee"]["g"]["after"] == 320.00

    @pytest.mark.asyncio
    async def test_rows_outside_their_own_week_are_filtered(self, monkeypatch):
        svc = self._service(monkeypatch, hourly("g", "20"))
        block = await svc.cost_delta_for_rows(
            None, company_id="co", location_id=None,
            weeks=[(WEEK, [], [shift("g", 14, 480), shift("g", 25, 480)])],
        )
        assert block["after"] == 160.00

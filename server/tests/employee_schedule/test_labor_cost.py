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
            None, company_id="co", location_id=None, week_start=WEEK,
            before_rows=[], after_rows=[],
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

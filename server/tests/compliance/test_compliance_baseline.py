"""Broad-strokes federal + CA compliance calendar baseline.

Pure-function tests for `get_baseline_calendar_items` — the headcount-
gated set of universally-known annual deadlines that populate the
compliance calendar without requiring a deeper jurisdiction check to run.
"""

import sys
from datetime import date
from types import ModuleType

import pytest

# Stub heavy optional deps before importing app code
for _name in ("google", "google.genai", "google.genai.types", "bleach",
              "audioop_lts", "audioop", "stripe"):
    if _name not in sys.modules:
        sys.modules[_name] = ModuleType(_name)
_genai = sys.modules["google.genai"]
_genai.Client = object
_genai.types = sys.modules["google.genai.types"]
_gt = sys.modules["google.genai.types"]
_gt.Tool = lambda **kw: None
_gt.GoogleSearch = lambda **kw: None
_gt.GenerateContentConfig = lambda **kw: None
_bleach = sys.modules["bleach"]
_bleach.clean = lambda text, **kw: text
_bleach.linkify = lambda text, **kw: text


from app.core.services.compliance_baseline import (
    _resolve_date,
    _resolve_second_wed_may,
    get_baseline_calendar_items,
)


# ─────────────────────────────────────────────────────────────────────
# Date resolution
# ─────────────────────────────────────────────────────────────────────

class TestResolveDate:
    def test_future_in_year_returns_this_year(self):
        # Today = March 1, deadline July 31 → this year
        assert _resolve_date(date(2026, 3, 1), 7, 31) == date(2026, 7, 31)

    def test_within_recent_window_returns_this_year(self):
        # Today = Feb 10, OSHA Form 300A posting due Feb 1 → still this year
        # (within 14-day recent window)
        assert _resolve_date(date(2026, 2, 10), 2, 1) == date(2026, 2, 1)

    def test_past_recent_window_rolls_to_next_year(self):
        # Today = Mar 1, deadline Jan 31 → rolled to next Jan 31
        # (more than 14 days past, stale)
        assert _resolve_date(date(2026, 3, 1), 1, 31) == date(2027, 1, 31)


class TestSecondWedMay:
    def test_second_wed_may_2026(self):
        # May 2026: 1st = Friday. First Wed is May 6, second Wed is May 13.
        assert _resolve_second_wed_may(date(2026, 1, 1)) == date(2026, 5, 13)

    def test_rolls_when_passed(self):
        # Late June after second Wed May → next year
        assert _resolve_second_wed_may(date(2026, 6, 30)).year == 2027


# ─────────────────────────────────────────────────────────────────────
# Baseline feed shape + headcount gating
# ─────────────────────────────────────────────────────────────────────

class TestBaselineFeed:
    def test_universal_items_for_zero_headcount(self):
        """Even a brand-new tenant with no employees yet sees the universal
        federal items (W-2, 1099, W-2/W-3 to SSA). Threshold-gated items
        (OSHA 300A, ACA, EEO-1) are filtered out."""
        items = get_baseline_calendar_items(
            today=date(2026, 1, 15),
            employee_count=0,
            has_ca_location=False,
        )
        slugs = [i.id.split(":")[2] for i in items]
        assert "w2-to-employees" in slugs
        assert "1099-nec-to-contractors" in slugs
        assert "w2-w3-ssa" in slugs
        # Threshold-gated: should NOT appear
        assert "osha-300a-post" not in slugs
        assert "osha-300a-efile" not in slugs
        assert "aca-1095c-employees" not in slugs
        assert "eeo1" not in slugs

    def test_small_employer_gets_osha_300a(self):
        items = get_baseline_calendar_items(
            today=date(2026, 1, 15),
            employee_count=15,
            has_ca_location=False,
        )
        slugs = [i.id.split(":")[2] for i in items]
        assert "osha-300a-post" in slugs
        assert "osha-300a-efile" not in slugs   # 20+ threshold
        assert "aca-1095c-employees" not in slugs  # 50+ threshold

    def test_mid_employer_gets_aca(self):
        items = get_baseline_calendar_items(
            today=date(2026, 1, 15),
            employee_count=75,
            has_ca_location=False,
        )
        slugs = [i.id.split(":")[2] for i in items]
        assert "aca-1095c-employees" in slugs
        assert "aca-1094c-irs" in slugs
        assert "eeo1" not in slugs   # 100+ threshold

    def test_large_employer_gets_eeo1(self):
        items = get_baseline_calendar_items(
            today=date(2026, 1, 15),
            employee_count=200,
            has_ca_location=False,
        )
        slugs = [i.id.split(":")[2] for i in items]
        assert "eeo1" in slugs

    def test_no_ca_location_omits_ca_items(self):
        items = get_baseline_calendar_items(
            today=date(2026, 1, 15),
            employee_count=200,
            has_ca_location=False,
        )
        scopes = {i.id.split(":")[1] for i in items}
        assert "ca" not in scopes

    def test_ca_location_includes_quarterly_de9(self):
        items = get_baseline_calendar_items(
            today=date(2026, 1, 15),
            employee_count=10,
            has_ca_location=True,
        )
        de9_slugs = [i.id.split(":")[2] for i in items if i.id.startswith("baseline:ca:ca-de9")]
        assert sorted(de9_slugs) == ["ca-de9-q1", "ca-de9-q2", "ca-de9-q3", "ca-de9-q4"]

    def test_ca_iipp_universal_for_ca_employer(self):
        items = get_baseline_calendar_items(
            today=date(2026, 1, 15),
            employee_count=1,
            has_ca_location=True,
        )
        slugs = [i.id.split(":")[2] for i in items]
        assert "ca-iipp-review" in slugs

    def test_ca_harassment_training_5plus(self):
        items_4 = get_baseline_calendar_items(
            today=date(2026, 1, 15), employee_count=4, has_ca_location=True,
        )
        items_5 = get_baseline_calendar_items(
            today=date(2026, 1, 15), employee_count=5, has_ca_location=True,
        )
        slugs_4 = [i.id.split(":")[2] for i in items_4]
        slugs_5 = [i.id.split(":")[2] for i in items_5]
        assert "ca-harassment-training" not in slugs_4
        assert "ca-harassment-training" in slugs_5

    def test_ca_pay_data_100plus(self):
        items_99 = get_baseline_calendar_items(
            today=date(2026, 1, 15), employee_count=99, has_ca_location=True,
        )
        items_100 = get_baseline_calendar_items(
            today=date(2026, 1, 15), employee_count=100, has_ca_location=True,
        )
        slugs_99 = [i.id.split(":")[2] for i in items_99]
        slugs_100 = [i.id.split(":")[2] for i in items_100]
        assert "ca-pay-data-report" not in slugs_99
        assert "ca-pay-data-report" in slugs_100


class TestItemShape:
    def test_baseline_id_format(self):
        items = get_baseline_calendar_items(
            today=date(2026, 1, 15), employee_count=10, has_ca_location=False,
        )
        for item in items:
            parts = item.id.split(":")
            assert parts[0] == "baseline"
            assert parts[1] in ("fed", "ca")
            assert parts[2]   # slug
            assert parts[3].isdigit()  # year

    def test_alert_status_is_baseline(self):
        items = get_baseline_calendar_items(
            today=date(2026, 1, 15), employee_count=10, has_ca_location=False,
        )
        assert all(i.alert_status == "baseline" for i in items)

    def test_derived_status_buckets_match_days(self):
        today = date(2026, 1, 15)
        items = get_baseline_calendar_items(
            today=today, employee_count=200, has_ca_location=True,
        )
        for item in items:
            d = item.days_until_due
            if d < 0:
                assert item.derived_status == "overdue"
            elif d <= 30:
                assert item.derived_status == "due_soon"
            elif d <= 90:
                assert item.derived_status == "upcoming"
            else:
                assert item.derived_status == "future"

    def test_sorted_by_deadline(self):
        items = get_baseline_calendar_items(
            today=date(2026, 1, 15), employee_count=200, has_ca_location=True,
        )
        deadlines = [i.deadline for i in items]
        assert deadlines == sorted(deadlines)

    def test_lookahead_window_caps_horizon(self):
        """No baseline item should be more than ~14 months out — broad
        strokes calendar is for near-term planning."""
        today = date(2026, 1, 15)
        items = get_baseline_calendar_items(
            today=today, employee_count=200, has_ca_location=True,
        )
        max_days = max(i.days_until_due for i in items)
        assert max_days <= 14 * 30 + 5  # small margin


class TestAnnualRollover:
    def test_jan_filing_rolls_after_window(self):
        """Looking at the calendar in mid-March, January W-2 filings should
        have rolled to next January (more than 14 days past)."""
        items = get_baseline_calendar_items(
            today=date(2026, 3, 15),
            employee_count=10, has_ca_location=False,
        )
        w2 = next(i for i in items if "w2-to-employees" in i.id)
        # Should be next year's deadline now
        assert w2.deadline == "2027-01-31"


# ─────────────────────────────────────────────────────────────────────
# New York
# ─────────────────────────────────────────────────────────────────────

class TestNewYork:
    def test_ny_location_includes_quarterly_nys45(self):
        items = get_baseline_calendar_items(
            today=date(2026, 1, 15),
            employee_count=10,
            has_ca_location=False,
            has_ny_location=True,
        )
        nys45_slugs = sorted(
            i.id.split(":")[2] for i in items if "ny-nys45" in i.id
        )
        assert nys45_slugs == [
            "ny-nys45-q1", "ny-nys45-q2", "ny-nys45-q3", "ny-nys45-q4",
        ]

    def test_ny_universal_items(self):
        """NY harassment training, PFL notice, and HERO Act review apply
        to every NY employer regardless of size."""
        items = get_baseline_calendar_items(
            today=date(2026, 1, 15),
            employee_count=1,
            has_ca_location=False,
            has_ny_location=True,
        )
        slugs = [i.id.split(":")[2] for i in items]
        assert "ny-harassment-training" in slugs
        assert "ny-pfl-notice" in slugs
        assert "ny-hero-act-review" in slugs

    def test_ny_pay_transparency_4plus(self):
        items_3 = get_baseline_calendar_items(
            today=date(2026, 1, 15), employee_count=3,
            has_ca_location=False, has_ny_location=True,
        )
        items_4 = get_baseline_calendar_items(
            today=date(2026, 1, 15), employee_count=4,
            has_ca_location=False, has_ny_location=True,
        )
        slugs_3 = [i.id.split(":")[2] for i in items_3]
        slugs_4 = [i.id.split(":")[2] for i in items_4]
        assert "ny-pay-transparency-review" not in slugs_3
        assert "ny-pay-transparency-review" in slugs_4

    def test_ca_only_omits_ny_items(self):
        items = get_baseline_calendar_items(
            today=date(2026, 1, 15),
            employee_count=200,
            has_ca_location=True,
            has_ny_location=False,
        )
        scopes = {i.id.split(":")[1] for i in items}
        assert "ny" not in scopes

    def test_ca_and_ny_both_present(self):
        items = get_baseline_calendar_items(
            today=date(2026, 1, 15),
            employee_count=200,
            has_ca_location=True,
            has_ny_location=True,
        )
        scopes = {i.id.split(":")[1] for i in items}
        # Both state scopes appear alongside federal
        assert scopes == {"fed", "ca", "ny"}

    def test_ny_only_omits_ca_items(self):
        items = get_baseline_calendar_items(
            today=date(2026, 1, 15),
            employee_count=200,
            has_ca_location=False,
            has_ny_location=True,
        )
        scopes = {i.id.split(":")[1] for i in items}
        assert "ca" not in scopes

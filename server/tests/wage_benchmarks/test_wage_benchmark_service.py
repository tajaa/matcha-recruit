"""Tests for wage_benchmark_service — pure functions + mocked-DB integration.

Pattern mirrors tests/employees/test_leave_eligibility_service.py: a fake
asyncpg connection class lets us exercise the service end-to-end without
touching the real database. Per CLAUDE.md the prod DB is on remote EC2 and
must not be hit from automated tests.
"""

from decimal import Decimal
from pathlib import Path
import sys
from uuid import uuid4

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import app.matcha.services.wage_benchmark_service as wbs
from app.matcha.services.wage_benchmark_service import (
    BELOW_MARKET_THRESHOLD,
    REPLACEMENT_COST_PER_EMPLOYEE,
    ANNUAL_HOURS,
    WageBenchmark,
    _BenchmarkIndex,
    _median,
    classify_title,
    compute_company_wage_gap,
)


# ─────────────────────────────────────────────────────────────────────────────
# Pure-function unit tests
# ─────────────────────────────────────────────────────────────────────────────


class TestClassifyTitle:
    """SOC code mapping from free-text job titles."""

    def test_exact_barista(self):
        soc, label = classify_title("Barista")
        assert soc == "35-3023"
        assert "Barista" in label

    def test_case_insensitive(self):
        assert classify_title("BARISTA")[0] == "35-3023"
        assert classify_title("barista")[0] == "35-3023"
        assert classify_title("BaRiStA")[0] == "35-3023"

    def test_substring_match(self):
        # "Senior Barista @ DT" should hit the "barista" keyword
        assert classify_title("Senior Barista @ DT")[0] == "35-3023"

    def test_smoothie_specialty(self):
        assert classify_title("smoothie tech")[0] == "35-3023"
        assert classify_title("Juicer")[0] == "35-3023"

    def test_supervisor_variants(self):
        assert classify_title("Shift Lead")[0] == "35-1012"
        assert classify_title("Store Manager")[0] == "35-1012"
        assert classify_title("Assistant Manager")[0] == "35-1012"
        # "GM " with trailing space — see service docstring on this trade-off
        assert classify_title("GM 4th Street")[0] == "35-1012"

    def test_cashier(self):
        assert classify_title("Cashier")[0] == "41-2011"
        assert classify_title("Front-End Cashier")[0] == "41-2011"

    def test_cook(self):
        assert classify_title("Line Cook")[0] == "35-2014"
        assert classify_title("Cook")[0] == "35-2014"

    def test_food_prep(self):
        assert classify_title("Food Prep")[0] == "35-2021"
        # "Prep Cook" hits the food-prep rule first (lists "prep cook"
        # explicitly), not the cook rule — order in title_to_soc.json
        # encodes specificity. A prep cook is a food-prep worker, not a
        # line cook, which matches BLS classification intent.
        assert classify_title("Prep Cook")[0] == "35-2021"

    def test_chef(self):
        assert classify_title("Executive Chef")[0] == "35-1011"

    def test_unmatched_returns_none(self):
        assert classify_title("Software Engineer") is None
        assert classify_title("Sales Associate") is None
        assert classify_title("Marketing Manager") is None

    def test_empty_inputs_return_none(self):
        assert classify_title(None) is None
        assert classify_title("") is None
        assert classify_title("   ") is None


class TestMedian:
    """Median helper used to summarize delta percentages."""

    def test_empty_list_returns_zero(self):
        assert _median([]) == 0.0

    def test_single_value(self):
        assert _median([0.5]) == 0.5

    def test_odd_count(self):
        assert _median([1.0, 2.0, 3.0]) == 2.0
        assert _median([3.0, 1.0, 2.0]) == 2.0  # sorts internally

    def test_even_count_averages_middle_two(self):
        assert _median([1.0, 2.0, 3.0, 4.0]) == 2.5

    def test_negative_values(self):
        # Realistic delta_pct values (e.g. 10% below market)
        assert _median([-0.20, -0.10, 0.0, 0.10]) == pytest.approx(-0.05)


class TestBenchmarkIndexPick:
    """In-memory 3-tier fallback (metro → state → national)."""

    @staticmethod
    def _bm(soc, area_type, state, area_name, p50):
        return WageBenchmark(
            soc_code=soc, soc_label=f"{soc} label",
            area_type=area_type, area_code="X", area_name=area_name,
            state=state,
            hourly_p10=None, hourly_p25=None,
            hourly_p50=Decimal(str(p50)),
            hourly_p75=None, hourly_p90=None,
            period="2024Q4", source="BLS_OEWS",
        )

    @pytest.fixture
    def index(self):
        nat = self._bm("35-3023", "national", None, "United States", 13.50)
        ca_state = self._bm("35-3023", "state", "CA", "California", 20.00)
        sf_metro = self._bm("35-3023", "metro", "CA",
                            "San Francisco-Oakland-Berkeley, CA", 22.00)
        la_metro = self._bm("35-3023", "metro", "CA",
                            "Los Angeles-Long Beach-Anaheim, CA", 20.00)
        return _BenchmarkIndex(
            national={nat.soc_code: nat},
            state={(ca_state.soc_code, "CA"): ca_state},
            metro={("35-3023", "CA"): [sf_metro, la_metro]},
        )

    def test_metro_match_oakland(self, index):
        bm = index.pick("35-3023", "Oakland", "CA")
        assert bm is not None
        assert bm.area_type == "metro"
        assert "Oakland" in bm.area_name

    def test_metro_match_los_angeles(self, index):
        bm = index.pick("35-3023", "Los Angeles", "CA")
        assert bm is not None
        assert bm.area_type == "metro"
        assert "Los Angeles" in bm.area_name

    def test_metro_match_case_insensitive(self, index):
        bm = index.pick("35-3023", "OAKLAND", "ca")
        assert bm is not None
        assert bm.area_type == "metro"

    def test_falls_to_state_when_no_metro_match(self, index):
        # Palo Alto is in CA but not in any of our metro area_names
        bm = index.pick("35-3023", "Palo Alto", "CA")
        assert bm is not None
        assert bm.area_type == "state"
        assert bm.hourly_p50 == Decimal("20.00")

    def test_falls_to_national_when_no_state(self, index):
        bm = index.pick("35-3023", None, None)
        assert bm is not None
        assert bm.area_type == "national"

    def test_falls_to_national_when_state_unknown(self, index):
        # Vermont not in our index — no state, no metro for VT
        bm = index.pick("35-3023", "Burlington", "VT")
        assert bm is not None
        assert bm.area_type == "national"

    def test_unknown_soc_returns_none(self, index):
        assert index.pick("99-9999", "Oakland", "CA") is None


# ─────────────────────────────────────────────────────────────────────────────
# Mocked-DB integration tests
# ─────────────────────────────────────────────────────────────────────────────


class _FakeConnContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


class _WageGapConn:
    """Fake asyncpg connection: returns a configured employee roster + bench rows."""

    def __init__(self, *, employee_rows=None, benchmark_rows=None):
        self.employee_rows = employee_rows or []
        self.benchmark_rows = benchmark_rows or []
        self.queries: list[str] = []

    async def fetch(self, query, *args):
        self.queries.append(query)
        if "FROM employees" in query:
            return self.employee_rows
        if "FROM wage_benchmarks" in query:
            return self.benchmark_rows
        raise AssertionError(f"Unexpected fetch query: {query[:80]}")


def _patch_connection(monkeypatch, conn):
    monkeypatch.setattr(wbs, "get_connection", lambda: _FakeConnContext(conn))


def _emp(*, job_title, work_city, work_state, pay_rate):
    """Mimic an asyncpg row dict for an employee."""
    return {
        "id": uuid4(),
        "job_title": job_title,
        "work_city": work_city,
        "work_state": work_state,
        "pay_rate": Decimal(str(pay_rate)),
    }


def _bench_row(*, soc, area_type, state, area_name, p50, area_code="X"):
    return {
        "soc_code": soc,
        "soc_label": f"{soc} label",
        "area_type": area_type,
        "area_code": area_code,
        "area_name": area_name,
        "state": state,
        "hourly_p10": None,
        "hourly_p25": None,
        "hourly_p50": Decimal(str(p50)),
        "hourly_p75": None,
        "hourly_p90": None,
        "period": "2024Q4",
        "source": "BLS_OEWS",
    }


@pytest.mark.asyncio
async def test_compute_wage_gap_empty_roster(monkeypatch):
    """Company with no hourly employees → empty summary, hourly_count=0."""
    conn = _WageGapConn(employee_rows=[])
    _patch_connection(monkeypatch, conn)

    result = await compute_company_wage_gap(uuid4())
    assert result.hourly_employees_count == 0
    assert result.employees_evaluated == 0
    assert result.employees_below_market == 0
    assert result.dollars_per_hour_to_close_gap == 0.0
    assert result.annual_cost_to_lift == 0
    assert result.max_replacement_cost_exposure == 0


@pytest.mark.asyncio
async def test_compute_wage_gap_below_market_aggregation(monkeypatch):
    """Three CA baristas: two below market, one at market.

    Market p50 = $22 in SF (metro hit for "Oakland"). Pays:
      - $18 → -$4 → -18% (below market, below threshold)
      - $19 → -$3 → -13.6% (below market, below threshold)
      - $22 → at market exactly
    Expected:
      - 3 evaluated, 2 below market, 1 at-or-above
      - $/hr to close: $4 + $3 = $7
      - annual cost to lift: $7 × 2080 = $14,560
      - max exposure: 2 × $5,864 = $11,728
    """
    conn = _WageGapConn(
        employee_rows=[
            _emp(job_title="Barista", work_city="Oakland", work_state="CA", pay_rate=18.00),
            _emp(job_title="Barista", work_city="Oakland", work_state="CA", pay_rate=19.00),
            _emp(job_title="Barista", work_city="Oakland", work_state="CA", pay_rate=22.00),
        ],
        benchmark_rows=[
            _bench_row(soc="35-3023", area_type="metro", state="CA",
                       area_name="San Francisco-Oakland-Berkeley, CA", p50=22.00),
        ],
    )
    _patch_connection(monkeypatch, conn)

    result = await compute_company_wage_gap(uuid4())

    assert result.hourly_employees_count == 3
    assert result.employees_evaluated == 3
    assert result.employees_below_market == 2
    assert result.employees_at_or_above_market == 1
    assert result.employees_unclassified == 0
    assert result.dollars_per_hour_to_close_gap == pytest.approx(7.00)
    assert result.annual_cost_to_lift == int(round(7.00 * ANNUAL_HOURS))
    assert result.max_replacement_cost_exposure == 2 * REPLACEMENT_COST_PER_EMPLOYEE


@pytest.mark.asyncio
async def test_compute_wage_gap_falls_back_to_state(monkeypatch):
    """Employee in a CA city not in our metro list → state benchmark used."""
    conn = _WageGapConn(
        employee_rows=[
            _emp(job_title="Barista", work_city="Palo Alto", work_state="CA", pay_rate=15.00),
        ],
        benchmark_rows=[
            # Only state-level benchmark provided, no metro matching Palo Alto
            _bench_row(soc="35-3023", area_type="state", state="CA",
                       area_name="California", p50=20.00),
        ],
    )
    _patch_connection(monkeypatch, conn)

    result = await compute_company_wage_gap(uuid4())
    # $15 vs $20 → -$5 → -25%, well below threshold
    assert result.employees_below_market == 1
    assert result.dollars_per_hour_to_close_gap == pytest.approx(5.00)


@pytest.mark.asyncio
async def test_compute_wage_gap_falls_back_to_national(monkeypatch):
    """Employee with no work_state → national benchmark used."""
    conn = _WageGapConn(
        employee_rows=[
            _emp(job_title="Barista", work_city=None, work_state=None, pay_rate=10.00),
        ],
        benchmark_rows=[
            _bench_row(soc="35-3023", area_type="national", state=None,
                       area_name="United States", p50=13.50),
        ],
    )
    _patch_connection(monkeypatch, conn)

    result = await compute_company_wage_gap(uuid4())
    # $10 vs $13.50 → -$3.50 → -25.9%, below threshold
    assert result.employees_below_market == 1
    assert result.dollars_per_hour_to_close_gap == pytest.approx(3.50)


@pytest.mark.asyncio
async def test_compute_wage_gap_unclassified_titles_counted_separately(monkeypatch):
    """Software Engineer can't be SOC-mapped → unclassified, not below-market."""
    conn = _WageGapConn(
        employee_rows=[
            _emp(job_title="Software Engineer", work_city="SF", work_state="CA", pay_rate=50.00),
            _emp(job_title="Marketing Manager", work_city="SF", work_state="CA", pay_rate=40.00),
            _emp(job_title="Barista", work_city="Oakland", work_state="CA", pay_rate=22.00),
        ],
        benchmark_rows=[
            _bench_row(soc="35-3023", area_type="metro", state="CA",
                       area_name="San Francisco-Oakland-Berkeley, CA", p50=22.00),
        ],
    )
    _patch_connection(monkeypatch, conn)

    result = await compute_company_wage_gap(uuid4())
    assert result.hourly_employees_count == 3
    assert result.employees_evaluated == 1   # only the barista
    assert result.employees_unclassified == 2
    assert result.employees_below_market == 0
    assert result.employees_at_or_above_market == 1


@pytest.mark.asyncio
async def test_compute_wage_gap_missing_benchmark_treated_as_unclassified(monkeypatch):
    """Title classifies but no benchmark exists for the (soc, state) → unclassified."""
    conn = _WageGapConn(
        employee_rows=[
            _emp(job_title="Barista", work_city="Reno", work_state="NV", pay_rate=14.00),
        ],
        benchmark_rows=[],  # no benchmarks at all
    )
    _patch_connection(monkeypatch, conn)

    result = await compute_company_wage_gap(uuid4())
    assert result.hourly_employees_count == 1
    assert result.employees_evaluated == 0
    assert result.employees_unclassified == 1
    assert result.employees_below_market == 0


@pytest.mark.asyncio
async def test_compute_wage_gap_threshold_boundary(monkeypatch):
    """Employee at exactly -10% (the threshold) is counted below market."""
    # Market p50 = $20.00 → -10% = $18.00 exactly
    conn = _WageGapConn(
        employee_rows=[
            _emp(job_title="Barista", work_city="Oakland", work_state="CA", pay_rate=18.00),
            # $18.01 = -9.95% → at-or-above (not below threshold)
            _emp(job_title="Barista", work_city="Oakland", work_state="CA", pay_rate=18.01),
        ],
        benchmark_rows=[
            _bench_row(soc="35-3023", area_type="metro", state="CA",
                       area_name="San Francisco-Oakland-Berkeley, CA", p50=20.00),
        ],
    )
    _patch_connection(monkeypatch, conn)

    result = await compute_company_wage_gap(uuid4())
    assert result.employees_below_market == 1   # only the $18.00 one
    assert result.employees_at_or_above_market == 1
    assert BELOW_MARKET_THRESHOLD == -0.10  # confirm constant


@pytest.mark.asyncio
async def test_compute_wage_gap_uses_two_db_queries(monkeypatch):
    """Regression test for the perf fix — verify we make exactly 2 DB queries
    (employees + benchmarks), not 1+N. This guards against accidentally
    re-introducing the per-employee lookup loop."""
    conn = _WageGapConn(
        employee_rows=[
            _emp(job_title="Barista", work_city="Oakland", work_state="CA", pay_rate=18.00),
            _emp(job_title="Barista", work_city="LA", work_state="CA", pay_rate=17.00),
            _emp(job_title="Cashier", work_city="LA", work_state="CA", pay_rate=15.00),
        ],
        benchmark_rows=[
            _bench_row(soc="35-3023", area_type="metro", state="CA",
                       area_name="San Francisco-Oakland-Berkeley, CA", p50=22.00),
            _bench_row(soc="35-3023", area_type="metro", state="CA",
                       area_name="Los Angeles-Long Beach-Anaheim, CA", p50=20.00),
            _bench_row(soc="41-2011", area_type="metro", state="CA",
                       area_name="Los Angeles-Long Beach-Anaheim, CA", p50=17.50),
        ],
    )
    _patch_connection(monkeypatch, conn)

    await compute_company_wage_gap(uuid4())

    # Exactly one employees query and one wage_benchmarks query
    employee_qs = [q for q in conn.queries if "FROM employees" in q]
    benchmark_qs = [q for q in conn.queries if "FROM wage_benchmarks" in q]
    assert len(employee_qs) == 1, f"expected 1 employees query, got {len(employee_qs)}"
    assert len(benchmark_qs) == 1, f"expected 1 benchmarks query, got {len(benchmark_qs)}"


@pytest.mark.asyncio
async def test_compute_wage_gap_no_benchmark_query_when_all_unclassified(monkeypatch):
    """If no employees can be classified, skip the benchmark query entirely
    (small optimization — empty soc_codes set short-circuits the index fetch).
    """
    conn = _WageGapConn(
        employee_rows=[
            _emp(job_title="Software Engineer", work_city="SF", work_state="CA", pay_rate=50.00),
        ],
        benchmark_rows=[],
    )
    _patch_connection(monkeypatch, conn)

    result = await compute_company_wage_gap(uuid4())
    assert result.hourly_employees_count == 1
    assert result.employees_unclassified == 1
    benchmark_qs = [q for q in conn.queries if "FROM wage_benchmarks" in q]
    assert len(benchmark_qs) == 0, "benchmark query should be skipped when no SOCs to look up"

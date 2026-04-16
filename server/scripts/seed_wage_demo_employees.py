#!/usr/bin/env python3
"""Seed a believable QSR roster so the wage-gap dashboard widget populates.

Creates (or upserts into) a demo coffee chain — "Brew & Blend Coffee" — with
8 California locations and ~96 employees spread across realistic QSR roles
(barista, shift lead, store manager, cashier, food prep, cook). Pay rates
are intentionally distributed so the wage-gap widget shows a believable mix:
roughly 60% below market, 25% at market, 15% above. That mix matches the
real QSR data (and is what makes the widget interesting in a demo).

Usage:
    cd server
    python3 scripts/seed_wage_demo_employees.py

Optional:
    --company-id <uuid>     Add the demo employees to an existing company
                            instead of creating "Brew & Blend Coffee".

Idempotent:
    Always purges the demo cohort first (matched by @brewandblend.demo
    email suffix), then re-inserts. Safe — only touches the demo cohort,
    never any real employees the company may have.

Prereqs:
    1. alembic upgrade head     (wage_benchmarks table exists)
    2. python3 scripts/seed_wage_benchmarks.py    (BLS data loaded)

After running this, hit /app in the client. The widget appears between the
"Quick Setup" nudge and the Flags & Actions table, with numbers like
"~58/82 hourly employees ≥10% below market".
"""

import argparse
import asyncio
import os
import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings
from app.database import close_pool, get_connection, init_pool

DEMO_COMPANY_NAME = "Brew & Blend Coffee"
DEMO_EMAIL_SUFFIX = "@brewandblend.demo"

# (city, state) — must match BLS area_name substring patterns in our seeded
# benchmarks. Palo Alto deliberately falls back to CA state-level (no metro
# row contains it) — that's the test for the state-fallback path.
LOCATIONS = [
    ("San Francisco", "CA"),
    ("Oakland", "CA"),
    ("Berkeley", "CA"),
    ("San Jose", "CA"),
    ("Los Angeles", "CA"),
    ("San Diego", "CA"),
    ("Sacramento", "CA"),
    ("Palo Alto", "CA"),  # → state fallback
]

# Per location: 12 employees split across these roles.
# Tuples are (job_title, count, pay_classification, soc_code).
ROLES_PER_LOCATION = [
    ("Store Manager",   1, "exempt", "35-1012"),  # salaried — won't show in widget (by design)
    ("Shift Lead",      2, "hourly", "35-1012"),
    ("Barista",         5, "hourly", "35-3023"),
    ("Cashier",         1, "hourly", "41-2011"),
    ("Food Prep",       2, "hourly", "35-2021"),
    ("Cook",            1, "hourly", "35-2014"),
]

# Approximate BLS p50s for each (city, soc_code) — used as the centerline
# we randomize around. These match server/app/matcha/data/oews_qsr_subset.csv
# so the demo math comes out clean.
MARKET_P50: dict[tuple[str, str], float] = {
    # SF metro (Oakland, Berkeley fall here via ILIKE substring)
    ("San Francisco", "35-3023"): 22.00,
    ("San Francisco", "35-1012"): 27.00,
    ("San Francisco", "41-2011"): 19.50,
    ("San Francisco", "35-2021"): 20.50,
    ("San Francisco", "35-2014"): 24.00,
    ("Oakland", "35-3023"):       22.00,
    ("Oakland", "35-1012"):       27.00,
    ("Oakland", "41-2011"):       19.50,
    ("Oakland", "35-2021"):       20.50,
    ("Oakland", "35-2014"):       24.00,
    ("Berkeley", "35-3023"):      22.00,
    ("Berkeley", "35-1012"):      27.00,
    ("Berkeley", "41-2011"):      19.50,
    ("Berkeley", "35-2021"):      20.50,
    ("Berkeley", "35-2014"):      24.00,
    # San Jose metro
    ("San Jose", "35-3023"):      22.50,
    ("San Jose", "35-1012"):      27.50,
    ("San Jose", "41-2011"):      19.50,
    ("San Jose", "35-2021"):      20.50,
    ("San Jose", "35-2014"):      24.00,
    # LA metro
    ("Los Angeles", "35-3023"):   20.00,
    ("Los Angeles", "35-1012"):   24.50,
    ("Los Angeles", "41-2011"):   17.50,
    ("Los Angeles", "35-2021"):   18.50,
    ("Los Angeles", "35-2014"):   21.50,
    # SD metro
    ("San Diego", "35-3023"):     19.50,
    ("San Diego", "35-1012"):     24.00,
    ("San Diego", "41-2011"):     17.50,
    ("San Diego", "35-2021"):     18.50,
    ("San Diego", "35-2014"):     21.00,
    # Sac metro
    ("Sacramento", "35-3023"):    19.50,
    ("Sacramento", "35-1012"):    24.00,
    ("Sacramento", "41-2011"):    17.50,
    ("Sacramento", "35-2021"):    18.50,
    ("Sacramento", "35-2014"):    21.00,
    # Palo Alto → CA state fallback
    ("Palo Alto", "35-3023"):     20.00,
    ("Palo Alto", "35-1012"):     24.00,
    ("Palo Alto", "41-2011"):     17.50,
    ("Palo Alto", "35-2021"):     18.50,
    ("Palo Alto", "35-2014"):     21.00,
}

# Realistic name pool for first/last — short list, plenty of combos.
FIRST_NAMES = [
    "Alex", "Jordan", "Sam", "Morgan", "Taylor", "Casey", "Riley", "Avery",
    "Quinn", "Reese", "Drew", "Cameron", "Skyler", "Jamie", "Phoenix",
    "River", "Sage", "Kai", "Rowan", "Dakota", "Luca", "Mateo", "Sofia",
    "Maya", "Zoe", "Ezra", "Nia", "Theo", "Asha", "Devi", "Emi", "Yara",
]
LAST_NAMES = [
    "Garcia", "Nguyen", "Patel", "Kim", "Lopez", "Rivera", "Singh", "Chen",
    "Park", "Tran", "Hernandez", "Diaz", "Lee", "Khan", "Cohen", "Bauer",
    "Reyes", "Cruz", "Vasquez", "Brooks", "Sandoval", "Tanaka", "Yamamoto",
    "Okafor", "Adeyemi", "Mensah", "Iqbal", "Roy", "Mahmood", "Sarkis",
]


def _pay_for(market_p50: float, rng: random.Random) -> float:
    """Generate a pay_rate around market_p50 with a realistic QSR distribution.

    60% below (-7% to -22%), 25% at (~±3%), 15% above (+5% to +14%). Most
    QSR operators run below market — that's the dynamic the widget surfaces.
    """
    bucket = rng.random()
    if bucket < 0.60:
        # Below market — some 10-22% under (drives below_market alerts)
        delta_pct = -rng.uniform(0.07, 0.22)
    elif bucket < 0.85:
        delta_pct = rng.uniform(-0.03, 0.03)
    else:
        delta_pct = rng.uniform(0.05, 0.14)
    pay = market_p50 * (1 + delta_pct)
    # Round to nearest $0.25 like real-world hourly rates
    return round(pay * 4) / 4


def _email(first: str, last: str, location_idx: int, seq: int) -> str:
    return f"{first.lower()}.{last.lower()}.{location_idx}{seq}{DEMO_EMAIL_SUFFIX}"


async def _ensure_demo_company(conn) -> UUID:
    row = await conn.fetchrow(
        "SELECT id FROM companies WHERE name = $1", DEMO_COMPANY_NAME
    )
    if row:
        return row["id"]
    row = await conn.fetchrow(
        """
        INSERT INTO companies (name, industry, size, headquarters_state, headquarters_city, status)
        VALUES ($1, 'Food Service', '50-200', 'CA', 'San Francisco', 'approved')
        RETURNING id
        """,
        DEMO_COMPANY_NAME,
    )
    print(f"created company: {DEMO_COMPANY_NAME} ({row['id']})")
    return row["id"]


async def _purge_demo_employees(conn, company_id: UUID) -> int:
    """Delete only the demo cohort (matched by email suffix). Safe — won't
    touch any real employees the company may have."""
    deleted = await conn.fetchval(
        """
        WITH gone AS (
            DELETE FROM employees
            WHERE org_id = $1 AND email LIKE '%' || $2
            RETURNING id
        )
        SELECT COUNT(*) FROM gone
        """,
        company_id, DEMO_EMAIL_SUFFIX,
    )
    return deleted or 0


async def seed(company_id_arg: str | None):
    settings = load_settings()
    await init_pool(settings.database_url)

    rng = random.Random(42)  # deterministic — same demo every run

    async with get_connection() as conn:
        if company_id_arg:
            company_id = UUID(company_id_arg)
            row = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", company_id)
            if not row:
                print(f"ERROR: company {company_id} not found")
                await close_pool()
                sys.exit(1)
            print(f"using existing company: {row['name']} ({company_id})")
        else:
            company_id = await _ensure_demo_company(conn)

        # Always purge the demo cohort first so re-runs are idempotent.
        # The employees table has no (org_id, email) unique constraint, so we
        # can't ON CONFLICT — clean-slate-then-insert is the safe pattern.
        # Only matches the demo email suffix, so any real employees the
        # company has are untouched.
        removed = await _purge_demo_employees(conn, company_id)
        if removed:
            print(f"purged {removed} prior demo employees")

        total_inserted = 0
        per_role_summary: dict[str, int] = {}

        async with conn.transaction():
            for loc_idx, (city, state) in enumerate(LOCATIONS):
                for role_idx, (role_title, count, pay_class, soc) in enumerate(ROLES_PER_LOCATION):
                    market = MARKET_P50.get((city, soc))
                    if market is None:
                        continue
                    for seq in range(count):
                        first = FIRST_NAMES[(loc_idx * 13 + seq * 7 + role_idx * 17) % len(FIRST_NAMES)]
                        last = LAST_NAMES[(loc_idx * 11 + seq * 5 + role_idx * 19) % len(LAST_NAMES)]
                        email = _email(first, last, loc_idx, role_idx * 10 + seq)

                        if pay_class == "exempt":
                            # Annual salary for store managers — roughly market hourly × 2080 + small premium
                            pay_rate = round(market * 2080 * 1.05, 2)
                        else:
                            pay_rate = _pay_for(market, rng)

                        # Tenure: bell-curve around ~6 months (real QSR average —
                        # short tenure is exactly the population this widget targets)
                        days_tenure = max(7, int(rng.gauss(180, 120)))
                        start = date.today() - timedelta(days=days_tenure)

                        await conn.execute(
                            """
                            INSERT INTO employees
                                (org_id, email, first_name, last_name, job_title,
                                 employment_type, pay_classification, pay_rate,
                                 work_city, work_state, start_date)
                            VALUES ($1, $2, $3, $4, $5, 'full_time', $6, $7, $8, $9, $10)
                            """,
                            company_id, email, first, last, role_title,
                            pay_class, Decimal(str(pay_rate)),
                            city, state, start,
                        )
                        total_inserted += 1
                        per_role_summary[role_title] = per_role_summary.get(role_title, 0) + 1

        print(f"\ndemo roster: {total_inserted} employees inserted across {len(LOCATIONS)} CA locations")
        for role, count in sorted(per_role_summary.items(), key=lambda x: -x[1]):
            print(f"  {role:18s}  {count}")

        # Quick self-check: how many will show as below-market?
        print("\nrunning live wage-gap computation against this company...")
        from app.matcha.services.wage_benchmark_service import compute_company_wage_gap
        gap = await compute_company_wage_gap(company_id)
        print(f"  hourly employees:       {gap.hourly_employees_count}")
        print(f"  evaluated:              {gap.employees_evaluated}")
        print(f"  below market (≥10%):    {gap.employees_below_market}")
        print(f"  at or above:            {gap.employees_at_or_above_market}")
        print(f"  unclassified:           {gap.employees_unclassified}")
        if gap.median_delta_percent is not None:
            print(f"  median delta:           {gap.median_delta_percent * 100:+.1f}% vs p50")
        print(f"  $/hr to close gap:      ${gap.dollars_per_hour_to_close_gap:.2f}")
        print(f"  annual cost to lift:    ${gap.annual_cost_to_lift:,}")
        print(f"  max replacement risk:   ${gap.max_replacement_cost_exposure:,}")

    await close_pool()
    print(f"\ndone. open /app in the client (logged in as a {DEMO_COMPANY_NAME} client user) to see the widget.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--company-id", help="Add demo employees to this existing company instead of creating Brew & Blend Coffee")
    args = parser.parse_args()
    asyncio.run(seed(args.company_id))


if __name__ == "__main__":
    main()

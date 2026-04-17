#!/usr/bin/env python3
"""Backfill pay_classification + pay_rate on 360 Behavioral Health employees.

The ADP HRIS mock that seeded the 360 BH roster imported names and titles
only — no pay data. Without pay_rate + pay_classification='hourly', the
wage-gap dashboard widget has nothing to evaluate.

This script classifies each BH employee by title, decides hourly vs. exempt
(clinician licensure tier roughly tracks W-2 convention in CA behavioral
health orgs), and sets a believable pay_rate distributed around the BLS p50
for the role at the employee's work_city. Distribution matches QSR seed:
~60% below market, 25% at, 15% above — so the widget shows a real gap worth
talking about.

Usage:
    cd server
    python3 scripts/backfill_bh_wages.py

Options:
    --company-id <uuid>   Override company (defaults to 360 BH id).
    --dry-run             Print what would change without writing.

Idempotent — safe to re-run; always recomputes and overwrites pay_rate /
pay_classification for employees matched by org_id.

Prereqs:
    1. alembic upgrade head
    2. python3 scripts/seed_wage_benchmarks.py  (oews_bh_subset.csv loaded)
"""

import argparse
import asyncio
import os
import random
import sys
from decimal import Decimal
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings
from app.database import close_pool, get_connection, init_pool
from app.matcha.services.wage_benchmark_service import classify_title, lookup_benchmark

DEFAULT_COMPANY_ID = UUID("1a1123e5-4c24-4735-8501-9a64a1dd7691")  # 360 Behavioral Health

# Titles that are W-2 hourly in real CA behavioral health orgs. Frontline
# paraprofessionals (peer support, psych tech/aide, behavior tech/RBT) and
# shift-based staff clinicians (staff RN, CADC in residential, expressive
# therapists, OT at staff level, case managers) are hourly. Fully licensed
# master's/doctoral clinicians (LCSW, LMFT, LPCC, BCBA, NP, Psychologist,
# Psychiatrist) are salaried exempt and stay out of the widget — that's the
# point: this surfaces the hourly-workforce retention lever, not clinician
# comp bands.
HOURLY_TITLE_KEYWORDS = [
    "peer support",
    "alcohol & drug counselor",
    "alcohol and drug counselor",
    "substance abuse counselor",
    "addiction counselor",
    "cadc",
    "psychiatric technician",
    "psychiatric aide",
    "behavior technician",
    "behavioral technician",
    "rbt",
    "mental health tech",
    "bh tech",
    "mht",
    "psych tech",
    "psychiatric registered nurse",
    "psych rn",
    "psychiatric nurse",
    "registered nurse",
    "art therapist",
    "music therapist",
    "drama therapist",
    "dance therapist",
    "recreational therapist",
    "occupational therapist",
    "case manager",
    "care coordinator",
]


def _is_hourly_title(title: str | None) -> bool:
    if not title:
        return False
    t = title.lower()
    return any(kw in t for kw in HOURLY_TITLE_KEYWORDS)


def _pay_around(market_p50: float, rng: random.Random) -> float:
    """Distribute pay around p50 so the widget surfaces a realistic gap.

    60% below (-7% to -22%), 25% at (~±3%), 15% above (+5% to +14%). Rounded
    to $0.25.
    """
    bucket = rng.random()
    if bucket < 0.60:
        delta = -rng.uniform(0.07, 0.22)
    elif bucket < 0.85:
        delta = rng.uniform(-0.03, 0.03)
    else:
        delta = rng.uniform(0.05, 0.14)
    return round(market_p50 * (1 + delta) * 4) / 4


async def backfill(company_id: UUID, dry_run: bool) -> None:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, job_title, work_city, work_state, pay_rate, pay_classification
            FROM employees
            WHERE org_id = $1 AND termination_date IS NULL
            """,
            company_id,
        )

    print(f"scanning {len(rows)} employees for {company_id}")

    rng = random.Random(0xB117A17)  # stable seed — re-runs produce same pay distribution
    planned_hourly = 0
    planned_exempt = 0
    skipped_no_benchmark = 0
    skipped_unclassified = 0
    updates: list[tuple[UUID, str, Decimal]] = []

    for row in rows:
        title = row["job_title"]
        cls = classify_title(title)
        if not cls:
            skipped_unclassified += 1
            continue

        soc_code, _ = cls
        if _is_hourly_title(title):
            bm = await lookup_benchmark(soc_code, row["work_city"], row["work_state"] or "CA")
            if not bm or not bm.hourly_p50:
                skipped_no_benchmark += 1
                continue
            pay = _pay_around(float(bm.hourly_p50), rng)
            updates.append((row["id"], "hourly", Decimal(str(pay))))
            planned_hourly += 1
        else:
            # Exempt — leave pay_rate NULL so the widget ignores them.
            updates.append((row["id"], "exempt", None))
            planned_exempt += 1

    print(
        f"plan: {planned_hourly} hourly · {planned_exempt} exempt · "
        f"{skipped_unclassified} unclassified · {skipped_no_benchmark} no benchmark"
    )
    if dry_run:
        print("dry-run — no writes")
        return

    async with get_connection() as conn:
        async with conn.transaction():
            for emp_id, classification, pay in updates:
                await conn.execute(
                    """
                    UPDATE employees
                    SET pay_classification = $1,
                        pay_rate = $2,
                        updated_at = NOW()
                    WHERE id = $3
                    """,
                    classification, pay, emp_id,
                )

    print(f"done · updated {len(updates)} employees")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company-id", type=UUID, default=DEFAULT_COMPANY_ID)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    await init_pool(settings.database_url)
    try:
        await backfill(args.company_id, args.dry_run)
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""Backfill employees.work_location_id from existing schedule data.

Scheduling now requires a location (assert_employee_schedulable_at,
fetch_roster's strict filter) — an employee with no work_location_id can't
be scheduled. The FK was previously only ever set implicitly (city/state
derivation on employee create/update, or HRIS sync), so most companies with
real schedule history have a large chunk of their roster with no location
at all. On the reference dev company (Sunset Smile Dental, 3 locations) this
was 48 of 67 employees, and 492 of 573 (86%) existing shift assignments
belonged to those 48.

Two passes, in order, each only touching employees still missing a
work_location_id after the previous pass:

  1. From actual assignments — if every shift an employee has ever been
     assigned to belongs to the SAME location, set it. (Covers 18 of the 48
     on the reference company.)
  2. From work_city/work_state — matched against business_locations, but
     ONLY when the (city, state) pair maps to exactly one active location
     for the company. A city with two locations (e.g. two San Diego sites)
     is deliberately left alone rather than guessed. (Covers 44 more on the
     reference company — all "Los Angeles, CA" resolving to one site.)

Whatever's left after both passes is reported, not guessed — assign those
by hand via the employee edit form (Work Location field on /app/employees).

Deliberately does NOT call ensure_location_for_employee (the helper the
employee create/update routes use) — that function CREATES a business_locations
row when nothing matches, which would seed phantom locations into the
picker. This script only matches against locations that already exist.

Usage:
    cd server
    python3 scripts/backfill_employee_work_location.py --company <uuid>
    python3 scripts/backfill_employee_work_location.py --company <uuid> --apply

Dry-run by default — prints the plan and does not write. Pass --apply to
commit it. Idempotent: re-running only ever touches employees still missing
a location, so a second run after a partial manual cleanup is safe.
"""

import argparse
import asyncio
import os
import sys
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings
from app.database import close_pool, get_connection, init_pool


async def _pass_from_assignments(conn, company_id: UUID) -> int:
    rows = await conn.fetch(
        """
        SELECT a.employee_id, MIN(s.location_id::text)::uuid AS loc
        FROM schedule_shift_assignments a
        JOIN schedule_shifts s ON s.id = a.shift_id AND s.location_id IS NOT NULL
        JOIN employees e ON e.id = a.employee_id
        WHERE e.org_id = $1 AND e.work_location_id IS NULL
        GROUP BY a.employee_id
        HAVING COUNT(DISTINCT s.location_id) = 1
        """,
        company_id,
    )
    print(f"pass 1 (from assignments): {len(rows)} employee(s) resolvable to a single location")
    if rows:
        await conn.executemany(
            "UPDATE employees SET work_location_id = $1, updated_at = NOW() WHERE id = $2",
            [(row["loc"], row["employee_id"]) for row in rows],
        )
    return len(rows)


async def _pass_from_city_state(conn, company_id: UUID) -> int:
    # Runs AFTER pass 1 has written (same transaction) — its own `IS NULL`
    # filter naturally excludes whoever pass 1 already resolved, so the two
    # passes' counts don't double-count the same employee.
    rows = await conn.fetch(
        """
        WITH uniq AS (
            SELECT lower(city) AS c, upper(state) AS s, MIN(id::text)::uuid AS loc
            FROM business_locations
            WHERE company_id = $1 AND is_active IS NOT FALSE AND city IS NOT NULL AND state IS NOT NULL
            GROUP BY 1, 2
            HAVING COUNT(*) = 1
        )
        SELECT e.id AS employee_id, uniq.loc
        FROM employees e
        JOIN uniq ON lower(e.work_city) = uniq.c AND upper(e.work_state) = uniq.s
        WHERE e.org_id = $1 AND e.work_location_id IS NULL
        """,
        company_id,
    )
    print(f"pass 2 (from work_city/work_state, unambiguous cities only): {len(rows)} employee(s)")
    if rows:
        await conn.executemany(
            "UPDATE employees SET work_location_id = $1, updated_at = NOW() WHERE id = $2",
            [(row["loc"], row["employee_id"]) for row in rows],
        )
    return len(rows)


async def _report_remainder(conn, company_id: UUID) -> None:
    rows = await conn.fetch(
        """
        SELECT id, first_name, last_name, work_city, work_state
        FROM employees
        WHERE org_id = $1 AND work_location_id IS NULL
          AND COALESCE(employment_status, 'active') NOT IN ('terminated', 'offboarded')
        ORDER BY last_name, first_name
        """,
        company_id,
    )
    print(f"remaining unresolved: {len(rows)}")
    for row in rows:
        where = f"{row['work_city'] or '?'}, {row['work_state'] or '?'}"
        print(f"  - {row['first_name']} {row['last_name']} ({where}) — assign manually")


class _DryRunRollback(Exception):
    """Raised to force a rollback after the plan is computed for real —
    same rehearse-then-roll-back idiom as MIGRATE_REHEARSAL (see
    server/CLAUDE.md's migration-authoring rules). Both passes run inside
    ONE transaction so pass 2's `work_location_id IS NULL` filter correctly
    sees pass 1's (uncommitted) writes, in dry-run and --apply alike — the
    reported plan is what --apply will actually do, not two independent
    snapshots of the same starting state."""


async def backfill(company_id: UUID, apply: bool) -> None:
    async with get_connection() as conn:
        before = await conn.fetchval(
            "SELECT COUNT(*) FROM employees WHERE org_id = $1 AND work_location_id IS NULL",
            company_id,
        )
        print(f"{before} employee(s) with no work_location_id before this run")

        try:
            async with conn.transaction():
                await _pass_from_assignments(conn, company_id)
                await _pass_from_city_state(conn, company_id)
                await _report_remainder(conn, company_id)
                if not apply:
                    raise _DryRunRollback
        except _DryRunRollback:
            pass

    if not apply:
        print("\ndry-run — no writes. Re-run with --apply to commit.")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", type=UUID, required=True)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    args = parser.parse_args()

    settings = load_settings()
    await init_pool(settings.database_url)
    try:
        await backfill(args.company, args.apply)
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())

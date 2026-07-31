#!/usr/bin/env python3
"""Extend the Sunset Smile Dental Group #Front Desk demo with a La Jolla
location + roster, for exercising "@huume I need an opener and a closer for
our La Jolla store next week" (see HUUME_SCHEDULE_COMPLIANCE_PLAN.md) live.

Idempotent: safe to re-run — every insert is guarded by an existence check
keyed on a name/email, so a second run is a no-op except for enabling the
`employee_schedule` feature flag (also idempotent).

Seeds:
- `business_locations`: "La Jolla Studio" (San Diego, CA) — a neighborhood
  name that must resolve via `match_location`'s NAME/address scoring, not
  its `city` column (the city is San Diego, not "La Jolla").
- `schedule_shift_templates`: "Opener" (06:00-14:00) and "Closer"
  (15:00-00:00, a 9h span) at that location, Mon-Sat.
- Three employees on the roster:
    - Marcus Bell — clean adult, no existing shifts. The natural pick for
      an unnamed "opener and a closer" request.
    - Dana Whitfield — adult, pre-loaded with 5 published 8h shifts (Mon-Fri,
      40h) at La Jolla NEXT week, so naming her ("@huume put Dana on the
      opener too") demos the weekly-overtime advisory (FLSA § 207(a)).
    - Riley Soto — a 17-year-old (`employee_demographics.date_of_birth`),
      demoing the minor-hours BLOCK (Cal. Lab. Code § 1391): the Closer
      template is a 9h shift, over the 8h daily cap for a 16-17 year-old in
      CA, so Riley is automatically excluded from any Closer proposal with
      the statute cited — no need to name her, she's just part of the roster
      `build_proposal` considers.
- Enables `employee_schedule` on the company (`ems`/`huume`/`matcha_work`
  are already on for this demo company).

Dev-only. Connects directly to the local dev Postgres container
(matcha-postgres:5432/matcha) — never point DATABASE_URL at this script.

Run:
    cd server && ./venv/bin/python ../scripts/seed_lajolla_schedule_demo.py

Then in #Front Desk (as an admin/client member, e.g. Priya):
    @huume I need an opener and a closer at la jolla next week
    confirm

Undo:
    DELETE FROM schedule_chat_proposals WHERE company_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400';
    DELETE FROM schedule_shift_assignments WHERE company_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400';
    DELETE FROM schedule_shifts WHERE company_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400';
    DELETE FROM schedule_shift_templates WHERE company_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400';
    DELETE FROM employee_demographics WHERE employee_id IN (
        SELECT id FROM employees WHERE org_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400'
            AND email LIKE '%@sunsetdental.test');
    DELETE FROM employees WHERE org_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400'
        AND email LIKE '%@sunsetdental.test';
    DELETE FROM business_locations WHERE company_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400'
        AND name = 'La Jolla Studio';
"""

import asyncio
import json
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import asyncpg  # noqa: E402

DATABASE_URL = "postgresql://matcha:matcha_dev@localhost:5432/matcha"

COMPANY_ID = UUID("287fffb5-ea50-40a2-bf07-6b5c2ca3c400")  # Sunset Smile Dental Group

LOCATION_NAME = "La Jolla Studio"
LOCATION_ADDRESS = "7863 Girard Ave"
LOCATION_CITY = "San Diego"
LOCATION_STATE = "CA"
LOCATION_ZIP = "92037"

# RFC 2606 reserved domain — never a real, deliverable address.
EMAIL_DOMAIN = "sunsetdental.test"


def _sunday_indexed_weekday(d: date) -> int:
    return (d.weekday() + 1) % 7


async def ensure_location(conn) -> UUID:
    existing = await conn.fetchval(
        "SELECT id FROM business_locations WHERE company_id = $1 AND name = $2",
        COMPANY_ID, LOCATION_NAME,
    )
    if existing:
        print(f"  location already exists: {LOCATION_NAME} ({existing})")
        return existing
    location_id = await conn.fetchval(
        """
        INSERT INTO business_locations (company_id, name, address, city, state, zipcode, is_active)
        VALUES ($1, $2, $3, $4, $5, $6, true)
        RETURNING id
        """,
        COMPANY_ID, LOCATION_NAME, LOCATION_ADDRESS, LOCATION_CITY, LOCATION_STATE, LOCATION_ZIP,
    )
    print(f"  created location {LOCATION_NAME} ({location_id})")
    return location_id


async def ensure_template(conn, location_id: UUID, name: str, role: str,
                          start: time, end: time, break_minutes: int) -> UUID:
    existing = await conn.fetchval(
        "SELECT id FROM schedule_shift_templates WHERE company_id = $1 AND name = $2 AND location_id = $3",
        COMPANY_ID, name, location_id,
    )
    if existing:
        print(f"  template already exists: {name} ({existing})")
        return existing
    template_id = await conn.fetchval(
        """
        INSERT INTO schedule_shift_templates
            (company_id, name, role, location_id, start_time, end_time,
             break_minutes, required_staff, days_of_week)
        VALUES ($1,$2,$3,$4,$5,$6,$7,1,$8::jsonb)
        RETURNING id
        """,
        COMPANY_ID, name, role, location_id, start, end, break_minutes,
        json.dumps([1, 2, 3, 4, 5, 6]),  # Mon-Sat
    )
    print(f"  created template {name} ({template_id})")
    return template_id


async def ensure_employee(conn, *, email: str, first: str, last: str, job_title: str) -> UUID:
    existing = await conn.fetchval("SELECT id FROM employees WHERE org_id = $1 AND email = $2", COMPANY_ID, email)
    if existing:
        print(f"  employee already exists: {first} {last} ({existing})")
        return existing
    employee_id = await conn.fetchval(
        """
        INSERT INTO employees (org_id, email, first_name, last_name, job_title, employment_type, employment_status)
        VALUES ($1, $2, $3, $4, $5, 'full_time', 'active')
        RETURNING id
        """,
        COMPANY_ID, email, first, last, job_title,
    )
    print(f"  created employee {first} {last} <{email}> ({employee_id})")
    return employee_id


async def ensure_demographics(conn, employee_id: UUID, dob: date) -> None:
    existing = await conn.fetchval(
        "SELECT employee_id FROM employee_demographics WHERE employee_id = $1", employee_id,
    )
    if existing:
        return
    await conn.execute(
        """
        INSERT INTO employee_demographics (employee_id, org_id, date_of_birth, source)
        VALUES ($1, $2, $3, 'seed')
        """,
        employee_id, COMPANY_ID, dob,
    )
    print(f"    -> demographics: DOB {dob.isoformat()}")


async def ensure_dana_shifts(conn, location_id: UUID, dana_id: UUID) -> None:
    """5 published 8h shifts (Mon-Fri) NEXT week — enough to sit right at
    40h, so naming Dana for one more shift that week triggers the
    weekly-overtime advisory (FLSA, 29 U.S.C. § 207(a))."""
    today = date.today()
    this_sunday = today - timedelta(days=_sunday_indexed_weekday(today))
    next_sunday = this_sunday + timedelta(days=7)

    existing = await conn.fetchval(
        """
        SELECT COUNT(*) FROM schedule_shifts s
        JOIN schedule_shift_assignments a ON a.shift_id = s.id
        WHERE s.company_id = $1 AND a.employee_id = $2
          AND s.starts_at >= $3 AND s.starts_at < $4
        """,
        COMPANY_ID, dana_id, next_sunday, next_sunday + timedelta(days=7),
    )
    if existing:
        print(f"  Dana already has {existing} shift(s) next week — skipping")
        return

    for offset in range(1, 6):  # Mon..Fri
        d = next_sunday + timedelta(days=offset)
        starts_at = datetime.combine(d, time(9, 0), tzinfo=timezone.utc)
        ends_at = datetime.combine(d, time(17, 0), tzinfo=timezone.utc)
        shift_id = await conn.fetchval(
            """
            INSERT INTO schedule_shifts
                (company_id, location_id, role, starts_at, ends_at, break_minutes,
                 required_staff, kind, status, published_at)
            VALUES ($1,$2,'Front Desk',$3,$4,30,1,'work','published',NOW())
            RETURNING id
            """,
            COMPANY_ID, location_id, starts_at, ends_at,
        )
        await conn.execute(
            "INSERT INTO schedule_shift_assignments (company_id, shift_id, employee_id) VALUES ($1,$2,$3)",
            COMPANY_ID, shift_id, dana_id,
        )
    print(f"  seeded 5 published 8h shifts for Dana the week of {next_sunday.isoformat()} (40h)")


async def ensure_feature(conn) -> None:
    features = await conn.fetchval("SELECT enabled_features FROM companies WHERE id = $1", COMPANY_ID)
    features = json.loads(features) if isinstance(features, str) else (features or {})
    if features.get("employee_schedule"):
        print("  employee_schedule already enabled")
        return
    features["employee_schedule"] = True
    await conn.execute(
        "UPDATE companies SET enabled_features = $1::jsonb WHERE id = $2",
        json.dumps(features), COMPANY_ID,
    )
    print("  enabled employee_schedule")


async def main() -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow("SELECT id, is_personal FROM companies WHERE id = $1", COMPANY_ID)
        if not row:
            print("Sunset Smile Dental Group not found — run seed_frontdesk_chat_demo.py first.")
            return

        print("Ensuring La Jolla location + templates...")
        location_id = await ensure_location(conn)
        await ensure_template(conn, location_id, "Opener", "Front Desk", time(6, 0), time(14, 0), 30)
        await ensure_template(conn, location_id, "Closer", "Front Desk", time(15, 0), time(0, 0), 30)

        print("Ensuring roster...")
        marcus_id = await ensure_employee(
            conn, email=f"marcus.bell@{EMAIL_DOMAIN}", first="Marcus", last="Bell", job_title="Front Desk",
        )
        dana_id = await ensure_employee(
            conn, email=f"dana.whitfield@{EMAIL_DOMAIN}", first="Dana", last="Whitfield", job_title="Front Desk",
        )
        riley_id = await ensure_employee(
            conn, email=f"riley.soto@{EMAIL_DOMAIN}", first="Riley", last="Soto", job_title="Front Desk",
        )

        today = date.today()
        seventeen_years_ago = date(today.year - 17, today.month, today.day)
        await ensure_demographics(conn, riley_id, seventeen_years_ago)

        print("Ensuring Dana's existing week...")
        await ensure_dana_shifts(conn, location_id, dana_id)

        print("Ensuring feature flag...")
        await ensure_feature(conn)

        print(
            "\nDone. In #Front Desk, as an admin/client member, try:\n"
            "  @huume I need an opener and a closer at la jolla next week\n"
            "then reply 'confirm'. Marcus is the clean pick; Riley is "
            "auto-excluded from the Closer with a cited minor-hours block; "
            "naming Dana (\"put Dana on the opener too\") demos the "
            "weekly-overtime advisory."
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

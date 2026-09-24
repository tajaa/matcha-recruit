"""Print the isolated Matcha Schedule App Review seed (or its undo SQL).

Use only through scripts/seed-prod.sh. The password comes from the environment;
the generated SQL contains a bcrypt hash and never prints the password.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import bcrypt

PREFIX = "a7700000"
TAG = "DEMO-MATCHA-SCHEDULE"
COMPANY = f"{PREFIX}-0000-4000-8000-000000000001"
LOCATION = f"{PREFIX}-0001-4000-8000-000000000001"
USERS = [f"{PREFIX}-0002-4000-8000-{n:012d}" for n in (1, 2)]
EMPLOYEES = [f"{PREFIX}-0003-4000-8000-{n:012d}" for n in (1, 2)]
EMAILS = ["demo-matcha-schedule@example.com", "coworker-matcha-schedule@example.com"]


def literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def seed_sql(password: str) -> str:
    if not password:
        raise ValueError("MATCHA_APP_REVIEW_PASSWORD must be set")
    if len(password.encode("utf-8")) > 72:
        raise ValueError("MATCHA_APP_REVIEW_PASSWORD must be at most 72 UTF-8 bytes")
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode()
    today = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    lines = [
        (
            "INSERT INTO companies (id, name, status, is_test, enabled_features, signup_source) VALUES "
            f"('{COMPANY}', '{TAG} Review Cafe', 'approved', TRUE, "
            "'{\"employee_schedule\":true,\"time_off\":true}'::jsonb, 'bespoke') "
            "ON CONFLICT (id) DO NOTHING;"
        ),
        (
            "INSERT INTO business_locations "
            "(id, company_id, name, address, city, state, zipcode, country_code, timezone, is_active, source) "
            f"VALUES ('{LOCATION}', '{COMPANY}', '{TAG} Cafe', '100 Demo Plaza', "
            "'San Francisco', 'CA', '94103', 'US', 'America/Los_Angeles', TRUE, 'manual') "
            "ON CONFLICT (id) DO NOTHING;"
        ),
    ]
    for user_id, employee_id, email, first, last in zip(
        USERS, EMPLOYEES, EMAILS, ("Alex", "Jordan"), ("Rivera", "Lee")
    ):
        lines.append(
            "INSERT INTO users (id, email, password_hash, role, is_active) VALUES "
            f"('{user_id}', '{email}', {literal(password_hash)}, 'employee', TRUE) "
            "ON CONFLICT (id) DO NOTHING;"
        )
        lines.append(
            "INSERT INTO employees "
            "(id, org_id, user_id, email, first_name, last_name, work_state, "
            "employment_type, start_date, work_location_id, job_title, "
            "employment_status) VALUES "
            f"('{employee_id}', '{COMPANY}', '{user_id}', '{email}', "
            f"'{first}', '{last}', 'CA', 'part_time', "
            f"'{today - timedelta(days=100)}', '{LOCATION}', 'Barista', 'active') "
            "ON CONFLICT (id) DO NOTHING;"
        )

    # UTC-encoded wall clocks are the scheduling API's storage convention.
    # Seed today's week plus the following eight weeks so the default view is populated.
    for day_index in range(63):
        day = today + timedelta(days=day_index)
        shift_id = f"{PREFIX}-0004-4000-8000-{day_index + 1:012d}"
        open_seat = day_index % 4 == 3
        lines.append(
            "INSERT INTO schedule_shifts "
            "(id, company_id, location_id, role, starts_at, ends_at, break_minutes, "
            "required_staff, status, published_at, notes) VALUES "
            f"('{shift_id}', '{COMPANY}', '{LOCATION}', 'Barista', "
            f"'{day}T09:00:00+00:00', '{day}T17:00:00+00:00', 30, 1, "
            f"'published', NOW(), '{TAG} App Review shift') "
            "ON CONFLICT (id) DO NOTHING;"
        )
        if not open_seat:
            employee_id = EMPLOYEES[1 if day_index % 4 == 1 else 0]
            assignment_id = f"{PREFIX}-0005-4000-8000-{day_index + 1:012d}"
            lines.append(
                "INSERT INTO schedule_shift_assignments "
                "(id, company_id, shift_id, employee_id, status) VALUES "
                f"('{assignment_id}', '{COMPANY}', '{shift_id}', '{employee_id}', 'assigned') "
                "ON CONFLICT DO NOTHING;"
            )
    return "\n".join(lines) + "\n"


def undo_sql() -> str:
    user_ids = ", ".join(literal(value) for value in USERS)
    # Inbox sender/creator FKs do not cascade. All predicates target demo IDs.
    return (
        "\n".join(
            [
                f"DELETE FROM inbox_email_batches WHERE sender_id IN ({user_ids}) OR recipient_id IN ({user_ids});",
                f"DELETE FROM inbox_messages WHERE sender_id IN ({user_ids});",
                f"DELETE FROM inbox_conversations WHERE created_by IN ({user_ids});",
                f"DELETE FROM inbox_participants WHERE user_id IN ({user_ids});",
                f"DELETE FROM schedule_audit_log WHERE company_id = '{COMPANY}';",
                f"DELETE FROM companies WHERE id = '{COMPANY}' AND name = '{TAG} Review Cafe' AND is_test = TRUE;",
                "DELETE FROM users WHERE "
                + " OR ".join(
                    f"(id = '{user_id}' AND email = '{email}')"
                    for user_id, email in zip(USERS, EMAILS)
                )
                + ";",
            ]
        )
        + "\n"
    )


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--undo"]:
            sys.stdout.write(undo_sql())
        elif not sys.argv[1:]:
            sys.stdout.write(seed_sql(os.environ.get("MATCHA_APP_REVIEW_PASSWORD", "")))
        else:
            raise ValueError("usage: matcha_schedule_app_review.py [--undo]")
    except ValueError as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)

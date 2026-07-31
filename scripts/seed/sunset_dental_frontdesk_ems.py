#!/usr/bin/env python3
"""Push the Sunset Smile Dental Group #Front Desk EMS demo (channel, its
messages, and the ems_events they produced) from dev to prod.

Deliberately NOT ./scripts/export-dev-data.py --tenant "Sunset Smile Dental
Group" — that walks the WHOLE tenant graph (3082 rows / 70 tables:
compliance test data, schedule test data, benefits, huume runs from other
threads, and two real Gmail addresses belonging to unrelated dev fixtures on
this same company). This pack is scoped to exactly the rows the #Front Desk
EMS demo touched: one channel, its members, its messages, the ems_events
they produced, and their audit trail — plus the two feature flags that gate
all of it, since prod has neither `matcha_work` nor `ems` set for this
company yet.

Prints SQL to stdout (the seed-prod.sh .py convention). --undo prints the
reversing SQL.

    ./scripts/seed-prod.sh scripts/seed/sunset_dental_frontdesk_ems.py --dry-run
    ./scripts/seed-prod.sh scripts/seed/sunset_dental_frontdesk_ems.py
    ./scripts/seed-prod.sh scripts/seed/sunset_dental_frontdesk_ems.py --undo
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

import asyncpg

DEV_DSN = "postgresql://matcha:matcha_dev@127.0.0.1:5432/matcha"

COMPANY_ID = "287fffb5-ea50-40a2-bf07-6b5c2ca3c400"  # Sunset Smile Dental Group
CHANNEL_ID = "3b98989c-708e-46c1-af66-235dd56b9fc6"  # Front Desk

# Reuse export-dev-data.py's vetted literal-escaping (E'' string handling for
# embedded newlines/backslashes, seed-prod.sh's GUARD-1-safe single-line
# form) rather than reimplementing it.
_export_mod_path = Path(__file__).resolve().parent.parent / "export-dev-data.py"
_spec = importlib.util.spec_from_file_location("export_dev_data", _export_mod_path)
_export_dev_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_export_dev_data)
lit = _export_dev_data.lit

# (table, pk_col, columns-in-insert-order, extra WHERE clause)
TABLES = [
    ("users", "id",
     ["id", "email", "password_hash", "role", "is_active", "created_at"],
     "email IN ('ops.assistant@example.com', 'priya.patel@example.com', "
     "'jordan.lee@example.com', 'casey.nguyen@example.com')"),
    ("clients", "id",
     ["id", "user_id", "company_id", "name", "phone", "job_title", "created_at", "is_hr_approver"],
     f"company_id = '{COMPANY_ID}' AND user_id != '8e7614eb-7174-4802-8f6e-b44d065993e2'"),  # Maria's client row already exists on prod
    ("employees", "id",
     ["id", "org_id", "user_id", "email", "first_name", "last_name", "work_state", "employment_type",
      "start_date", "termination_date", "manager_id", "phone", "address", "emergency_contact",
      "created_at", "updated_at", "personal_email", "work_location_id", "pay_classification",
      "pay_rate", "work_city", "job_title", "department", "employment_status", "status_changed_at",
      "status_reason", "external_uid", "is_supervisor", "hris_id", "is_manager"],
     f"org_id = '{COMPANY_ID}' AND user_id = 'b3127036-ca41-410b-8c19-1a41a9553bc2'"),  # Casey only
    ("channels", "id",
     ["id", "company_id", "name", "slug", "description", "created_by", "is_archived", "created_at",
      "updated_at", "visibility", "is_paid", "price_cents", "currency", "inactivity_threshold_days",
      "inactivity_warning_days", "stripe_product_id", "stripe_price_id", "job_posting_fee_cents", "category"],
     f"id = '{CHANNEL_ID}'"),
    ("channel_members", "id",
     ["id", "channel_id", "user_id", "joined_at", "last_read_at", "is_muted", "role",
      "last_contributed_at", "stripe_subscription_id", "subscription_status", "paid_through",
      "removed_for_inactivity", "removal_cooldown_until", "inactivity_warned_at"],
     f"channel_id = '{CHANNEL_ID}'"),
    ("channel_messages", "id",
     ["id", "channel_id", "sender_id", "content", "created_at", "edited_at", "attachments",
      "deleted_at", "deleted_by", "reply_to_id", "client_message_id", "message_type"],
     f"channel_id = '{CHANNEL_ID}'"),
    # Three of the 19 ems_events were promoted to real IR incidents — that's
    # part of the same feature (the EMS->IR bridge), so the 3 incidents ride
    # along too, scoped to exactly their own ids (never the whole company's
    # ir_incidents table). ems_events.incident_id FKs here, so this table
    # must land before ems_events below.
    ("ir_incidents", "id",
     ["id", "incident_number", "title", "description", "incident_type", "severity", "status",
      "occurred_at", "location", "reported_by_name", "reported_by_email", "reported_at",
      "assigned_to", "witnesses", "category_data", "root_cause", "corrective_actions",
      "created_by", "created_at", "updated_at", "resolved_at", "company_id", "location_id",
      "involved_employee_ids", "osha_recordable", "osha_case_number", "osha_classification",
      "days_away_from_work", "days_restricted_duty", "date_of_death", "osha_form_301_data",
      "er_case_id", "wc_claim_type", "post_termination", "return_to_work_date"],
     "id IN ('909bb4c8-2bc4-45bf-999b-bf6155d144b9', '0e7dbe19-0cea-4e99-b4d5-68708def6cee', "
     "'d75ddce4-c536-4a56-ad4b-3d6971c6ab0a')"),
    ("ems_events", "id",
     ["id", "company_id", "channel_id", "message_id", "reporter_user_id", "title", "category",
      "severity_hint", "doc", "narrative", "incident_recommendation", "incident_reasoning",
      "suggested_incident_type", "suggested_severity", "status", "incident_id", "promoted_by",
      "promoted_at", "dismissed_by", "dismissed_at", "token_usage", "clarify_message_id",
      "clarification_rounds", "created_at", "updated_at"],
     f"company_id = '{COMPANY_ID}'"),
    ("ems_event_audit_log", "id",
     ["id", "event_id", "user_id", "action", "details", "created_at"],
     f"event_id IN (SELECT id FROM ems_events WHERE company_id = '{COMPANY_ID}')"),
]

FEATURE_FLAG_UPDATE = f"""UPDATE companies SET enabled_features = enabled_features
    || '{{"matcha_work": true, "ems": true}}'::jsonb
    WHERE id = '{COMPANY_ID}';"""

FEATURE_FLAG_UNDO = f"""UPDATE companies SET enabled_features = enabled_features
    || '{{"matcha_work": false, "ems": false}}'::jsonb
    WHERE id = '{COMPANY_ID}';"""


async def fetch_rows(conn, table, cols, where):
    sel = ", ".join(f'"{c}"::text AS "{c}"' for c in cols)
    rows = await conn.fetch(f'SELECT {sel} FROM "{table}" WHERE {where}')
    return [dict(r) for r in rows]


async def build():
    conn = await asyncpg.connect(DEV_DSN)
    try:
        collected = {}
        for table, pk, cols, where in TABLES:
            rows = await fetch_rows(conn, table, cols, where)
            collected[table] = (pk, cols, rows)
            print(f"-- {table}: {len(rows)} rows", file=sys.stderr)
    finally:
        await conn.close()
    return collected


def emit_insert(table, pk, cols, rows):
    lines = []
    for row in rows:
        col_list = ", ".join(f'"{c}"' for c in cols)
        # Every value was cast ::text on the way out (a NULL round-trips as
        # Python None -> SQL NULL); no cast is needed going back in — an
        # INSERT...VALUES string literal's type is resolved against the
        # target column, so jsonb/uuid[]/timestamp/boolean all parse from
        # their own text form with no explicit cast. Same approach as
        # export-dev-data.py's emit(), which this pack mirrors.
        vals = [lit(row[c]) for c in cols]
        lines.append(
            f'INSERT INTO "{table}" ({col_list}) VALUES ({", ".join(vals)}) '
            f'ON CONFLICT ("{pk}") DO NOTHING;'
        )
    return lines


def emit_undo(table, pk, rows):
    if not rows:
        return []
    ids = ", ".join(lit(r[pk]) for r in rows)
    return [f'DELETE FROM "{table}" WHERE "{pk}" IN ({ids});']


async def main(undo: bool) -> None:
    collected = await build()

    if undo:
        # Reverse FK order: audit log -> events -> messages -> members ->
        # channel -> employees -> clients -> users. Flags revert last so a
        # partial undo (interrupted mid-run) never leaves the feature "on"
        # with the demo data gone.
        order = ["ems_event_audit_log", "ems_events", "ir_incidents", "channel_messages",
                 "channel_members", "channels", "employees", "clients", "users"]
        for table in order:
            pk, _cols, rows = collected[table]
            for line in emit_undo(table, pk, rows):
                print(line)
        print(FEATURE_FLAG_UNDO)
        return

    print(FEATURE_FLAG_UPDATE)
    # Forward FK order: users -> clients/employees -> channels ->
    # channel_members -> channel_messages -> ems_events -> audit log.
    order = ["users", "clients", "employees", "channels", "channel_members",
              "channel_messages", "ir_incidents", "ems_events", "ems_event_audit_log"]
    for table in order:
        pk, cols, rows = collected[table]
        for line in emit_insert(table, pk, cols, rows):
            print(line)


if __name__ == "__main__":
    asyncio.run(main(undo="--undo" in sys.argv))

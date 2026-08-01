#!/usr/bin/env python3
"""Push Sunset Smile Dental Group's scheduling + workforce-compliance demo
data from dev to prod: schedule templates/shifts/assignments/requests/audit
log, training, the 3 attendance progressive_discipline records
schedule_intelligence's pretext-shield module reads, and the 10
workforce-compliance register rows tagged `[seed:sched-compliance]` by
scripts/seed_sunset_scheduling_compliance.py (the dev-side seed this pack
mirrors).

Built on top of export-dev-data.py's shared graph-walking Collector rather
than a hand-rolled table list (the earlier sunset_dental_frontdesk_ems.py
pattern) — that tool already does the two hard parts correctly: it ASCENDS
into whatever FK prerequisites a collected row actually needs (so a missing
`employees`/`business_locations` row is found and exported without having to
hand-audit dev vs. prod row-by-row), and its "skip" mode emits untargeted
`ON CONFLICT DO NOTHING`, which is required here — `pay_transparency_status`
has a UNIQUE (company_id, state) and `hiring_ai_audits` a UNIQUE
(company_id, tool_name), neither of which a PK-only conflict target would
catch.

Deliberately NOT --tenant (full descend): that pulls the whole tenant graph
(3000+ rows across ~70 tables — see sunset_dental_frontdesk_ems.py's own
docstring for why it rejected that). This pack calls `collector.collect()`
directly per target table, scoped to company_id, descend=False — so only
those rows and their ASCENDED prerequisites are ever touched.

Two things ascend would otherwise get wrong, both handled explicitly below:

1. Every user FK across every one of these tables (created_by, actor_user_id,
   reviewed_by, issued_by, updated_by, ...) resolves to Maria Chen
   (8e7614eb-7174-4802-8f6e-b44d065993e2), verified already on prod. `users`/
   `clients`/`admins` are excluded from ascend entirely, so this pack never
   emits a row for a real login account, and --undo can never emit
   `DELETE FROM users`.

2. `progressive_discipline` is scoped to `infraction_type = 'attendance'`
   only (3 of dev's 5 rows) — exactly what pretext-shield reads. The other 2
   rows reference an ir_incidents row and a discipline_letter_template,
   which are out of scope by decision (2026-07-31: scheduling + compliance,
   not incidents). Both tables are also in EXTRA_EXCLUDE as a structural
   backstop in case a future dev row adds such a reference.

`employees` and `business_locations` are collected as ASCEND-ONLY
prerequisites (some may already exist on prod — INSERT...ON CONFLICT DO
NOTHING makes that safe either way). But export-dev-data.py's emit() doesn't
distinguish "this pack created it" from "already existed, INSERT no-op'd" —
its --undo blindly deletes every row it collected. Deleting a real employee
that merely happened to already be on the roster would be wrong, so undo for
those two tables is dropped (see UNDO_TABLES) and replaced with a note.

    ./scripts/seed-prod.sh scripts/seed/sunset_dental_scheduling.py --dry-run
    ./scripts/seed-prod.sh scripts/seed/sunset_dental_scheduling.py
    ./scripts/seed-prod.sh scripts/seed/sunset_dental_scheduling.py --undo
"""

import asyncio
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

import asyncpg

DEV_DSN = "postgresql://matcha:matcha_dev@127.0.0.1:5432/matcha"
COMPANY_ID = "287fffb5-ea50-40a2-bf07-6b5c2ca3c400"  # Sunset Smile Dental Group

# Reuse the schema-introspecting FK-graph collector + additive emitter rather
# than reimplementing them — see module docstring.
_export_mod_path = Path(__file__).resolve().parent.parent / "export-dev-data.py"
_spec = importlib.util.spec_from_file_location("export_dev_data", _export_mod_path)
_export_dev_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_export_dev_data)

load_schema = _export_dev_data.load_schema
Collector = _export_dev_data.Collector
topo_order = _export_dev_data.topo_order
emit = _export_dev_data.emit
DEFAULT_EXCLUDE = _export_dev_data.DEFAULT_EXCLUDE

# Tables this pack's --undo is allowed to DELETE from. Everything else this
# pack collects (employees, business_locations) is an ascend-only FK
# prerequisite that may have pre-existed on prod — see module docstring.
UNDO_TABLES = {
    "schedule_shift_templates", "schedule_shifts", "schedule_shift_assignments",
    "schedule_requests", "schedule_audit_log", "training_requirements",
    "training_records", "progressive_discipline", "pay_transparency_status",
    "hiring_ai_audits", "biometric_consent_points", "pay_equity_reviews",
}

EXTRA_EXCLUDE = {
    "users", "clients", "admins",  # see module docstring point 1
    "ir_incidents", "ir_audit_log", "discipline_letter_templates",  # point 2
    # Shared, not tenant-owned — same reasoning as export-dev-data.py's own
    # GLOBAL_TABLES. `companies` is ascended into via nearly every table's
    # company_id FK but the tenant row itself already exists on prod (that's
    # the whole premise of this pack) and must never be touched — ON
    # CONFLICT DO NOTHING makes an emitted row harmless, but the safer thing
    # is to not emit it at all. `training_lesson_templates` is the canned
    # CA harassment-prevention lesson content training_requirements.template_id
    # points at — a fixed 2-row catalog, verified already on prod with the
    # SAME ids dev's rows reference (checked by hand before writing this pack).
    "companies", "training_lesson_templates",
}

# (table, SQL, args) — company-scoped source queries, in the order collected.
# schedule_shift_assignments has no company_id column; scope via its shift.
QUERIES = [
    ("schedule_shift_templates",
     'SELECT * FROM schedule_shift_templates WHERE company_id = $1', (COMPANY_ID,)),
    ("schedule_shifts",
     'SELECT * FROM schedule_shifts WHERE company_id = $1', (COMPANY_ID,)),
    ("schedule_shift_assignments",
     'SELECT a.* FROM schedule_shift_assignments a '
     'JOIN schedule_shifts s ON s.id = a.shift_id WHERE s.company_id = $1', (COMPANY_ID,)),
    ("schedule_requests",
     'SELECT * FROM schedule_requests WHERE company_id = $1', (COMPANY_ID,)),
    ("schedule_audit_log",
     'SELECT * FROM schedule_audit_log WHERE company_id = $1', (COMPANY_ID,)),
    ("training_requirements",
     'SELECT * FROM training_requirements WHERE company_id = $1', (COMPANY_ID,)),
    ("training_records",
     'SELECT * FROM training_records WHERE company_id = $1', (COMPANY_ID,)),
    ("progressive_discipline",
     "SELECT * FROM progressive_discipline WHERE company_id = $1 AND infraction_type = 'attendance'",
     (COMPANY_ID,)),
    ("pay_transparency_status",
     "SELECT * FROM pay_transparency_status WHERE company_id = $1 AND note LIKE '%[seed:sched-compliance]%'",
     (COMPANY_ID,)),
    ("hiring_ai_audits",
     "SELECT * FROM hiring_ai_audits WHERE company_id = $1 AND notes LIKE '%[seed:sched-compliance]%'",
     (COMPANY_ID,)),
    ("biometric_consent_points",
     "SELECT * FROM biometric_consent_points WHERE company_id = $1 AND notes LIKE '%[seed:sched-compliance]%'",
     (COMPANY_ID,)),
    ("pay_equity_reviews",
     "SELECT * FROM pay_equity_reviews WHERE company_id = $1 AND notes LIKE '%[seed:sched-compliance]%'",
     (COMPANY_ID,)),
]


async def collect_all(conn):
    cols, pks, fks, _composite = await load_schema(conn)
    collector = Collector(conn, cols, pks, fks, DEFAULT_EXCLUDE | EXTRA_EXCLUDE)

    for table, sql, args in QUERIES:
        rows = await conn.fetch(sql, *args)
        for r in rows:
            await collector.collect(table, dict(r), descend=False)
        print(f"   collected {table}: {len(rows)} rows (+ ascended prerequisites)", file=sys.stderr)

    # Same self-reference computation as export-dev-data.py's own main() —
    # employees.manager_id is a real case (self-FK), so this can't be skipped.
    self_ref = defaultdict(list)
    for fk in fks:
        if fk["child"] == fk["parent"]:
            self_ref[fk["child"]].append(fk["child_col"])

    present = [t for t in collector.rows if collector.rows[t]]
    order, cyclic = topo_order(present, fks)
    if cyclic:
        print(f"!! cyclic FK order, correctness not guaranteed for: {cyclic}", file=sys.stderr)

    lines, undo, stats, no_pk = await emit(
        conn, collector, order, self_ref, ["Sunset Smile scheduling + workforce-compliance"],
    )
    if no_pk:
        print(f"!! tables with no PK, silently skipped by emit(): {no_pk}", file=sys.stderr)
    for table, n in stats:
        print(f"   -> {table}: {n} rows emitted", file=sys.stderr)
    return lines, undo


def filtered_undo(undo_lines):
    kept, dropped = [], set()
    for line in undo_lines:
        table = line.split('"')[1] if line.startswith('DELETE FROM "') else None
        if table in UNDO_TABLES:
            kept.append(line)
        elif table:
            dropped.add(table)
    return kept, dropped


async def main(undo: bool) -> None:
    conn = await asyncpg.connect(DEV_DSN)
    try:
        lines, undo_lines = await collect_all(conn)
    finally:
        await conn.close()

    if undo:
        kept, dropped = filtered_undo(undo_lines)
        if dropped:
            print(f"-- NOTE: rows in {sorted(dropped)} are intentionally NOT deleted —")
            print("-- they were collected only as FK prerequisites (may have pre-existed on prod).")
        for line in kept:
            print(line)
        return

    for line in lines:
        print(line)


if __name__ == "__main__":
    asyncio.run(main(undo="--undo" in sys.argv))

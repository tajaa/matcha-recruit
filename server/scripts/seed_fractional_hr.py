"""Seed dev DB with demo data for the Fractional HR admin tooling (/admin/fractional-hr).

Idempotent: deletes any prior rows for the known seed client names (cascades to
scope/tasks/time/assignments) then re-inserts. DEV ONLY — refuses to run unless
DATABASE_URL is a local (:5432) URL, never prod (:5433).

Run:
    cd server
    DATABASE_URL="$(grep '^DATABASE_URL' .env | head -1 | cut -d= -f2- | tr -d '\"'\"'\"' ')" \
        ./venv/bin/python scripts/seed_fractional_hr.py

All contact emails use RFC 2606 reserved domains (example.com / *.test) per the
repo test-data rule — nothing here is deliverable.
"""

import asyncio
import json
import os
import sys
from datetime import date, datetime, timedelta

import asyncpg

URL = os.environ.get("DATABASE_URL", "")
if ":5433" in URL:
    sys.exit("REFUSING: DATABASE_URL points at :5433 (prod). This script is dev-only.")
if not URL or ("localhost" not in URL and "127.0.0.1" not in URL):
    sys.exit(f"REFUSING: DATABASE_URL is not a local dev URL: {URL!r}")

TODAY = date.today()
FOM = TODAY.replace(day=1)                 # first of this month
def tm(n: int) -> date:                    # a day this month, clamped to <= today
    d = FOM + timedelta(days=n)
    return d if d <= TODAY else TODAY
INQ = FOM - timedelta(days=20)             # earlier this quarter (prev month)
OLD = FOM - timedelta(days=80)             # before this quarter (all-time only)
NOW = datetime.now()

SEED_NAMES = [
    "Northwind Health", "Acme Robotics", "Globex Corp",
    "Initech", "Umbrella Wellness", "Stark Industries",
]


async def main() -> None:
    conn = await asyncpg.connect(URL)
    try:
        admins = await conn.fetch(
            "SELECT id, email FROM users WHERE role='admin' AND is_active=true ORDER BY email"
        )
        if not admins:
            sys.exit("No active admin users in dev — cannot seed (lead/assignee/pro must be admins).")
        A = [r["id"] for r in admins]
        a0, a1, a2 = A[0], A[1 % len(A)], A[2 % len(A)]
        creator = a0

        comp = await conn.fetchrow(
            "SELECT id, name FROM companies WHERE deleted_at IS NULL "
            "AND name NOT LIKE 'ZZ%' AND name NOT LIKE 'Matcha X%' ORDER BY name LIMIT 1"
        )
        comp_id = comp["id"] if comp else None

        # --- idempotency: wipe prior seed (cascades to children) ---
        await conn.execute("DELETE FROM fractional_clients WHERE name = ANY($1::text[])", SEED_NAMES)

        # --- insert helpers ---
        async def client(**k) -> str:
            return await conn.fetchval(
                """
                INSERT INTO fractional_clients
                  (name, company_id, status, billing_model, retainer_hours, retainer_period,
                   rollover_unused, billing_rate, project_fee, currency, industry, headcount,
                   jurisdictions, contact_name, contact_email, contact_phone, lead_pro_id,
                   start_date, notes, created_by)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb,$14,$15,$16,$17,$18,$19,$20)
                RETURNING id
                """,
                k["name"], k.get("company_id"), k["status"], k["billing_model"],
                k.get("retainer_hours"), k.get("retainer_period", "monthly"),
                k.get("rollover_unused", False), k.get("billing_rate"), k.get("project_fee"),
                k.get("currency", "USD"), k.get("industry"), k.get("headcount"),
                json.dumps(k.get("jurisdictions", [])), k.get("contact_name"),
                k.get("contact_email"), k.get("contact_phone"), k.get("lead_pro_id"),
                k.get("start_date"), k.get("notes"), creator,
            )

        async def assign(cid, pro, role):
            await conn.execute(
                "INSERT INTO fractional_assignments (client_id, pro_user_id, role) "
                "VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
                cid, pro, role,
            )

        async def scope(cid, cat, title, status="active", prio="medium", desc=None) -> str:
            return await conn.fetchval(
                "INSERT INTO fractional_scope_items "
                "(client_id, service_category, title, description, status, priority, created_by) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id",
                cid, cat, title, desc, status, prio, creator,
            )

        async def task(cid, title, cat, status="todo", prio="medium", assignee=None,
                       due=None, est=None, sc=None, done_at=None) -> str:
            return await conn.fetchval(
                """
                INSERT INTO fractional_tasks
                  (client_id, scope_item_id, title, description, service_category, status,
                   priority, assignee_pro_id, due_date, estimated_hours, billable, created_by, completed_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) RETURNING id
                """,
                cid, sc, title, None, cat, status, prio, assignee, due, est, True, creator, done_at,
            )

        async def time(cid, pro, hours, d, note=None, tk=None, cat=None, billable=True):
            await conn.execute(
                "INSERT INTO fractional_time_entries "
                "(client_id, task_id, pro_id, hours, entry_date, note, billable, service_category) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                cid, tk, pro, hours, d, note, billable, cat,
            )

        # ------------------------------------------------------------------ #
        # 1) Northwind Health — monthly retainer, OVER budget this month (at-risk)
        # ------------------------------------------------------------------ #
        nw = await client(
            name="Northwind Health", company_id=comp_id, status="active",
            billing_model="monthly_retainer", retainer_hours=40, retainer_period="monthly",
            billing_rate=200, industry="Healthcare", headcount=240,
            jurisdictions=["CA", "WA"], contact_name="Dana Reed",
            contact_email="dana.reed@example.com", contact_phone="+1-555-0101",
            lead_pro_id=a0, start_date=FOM - timedelta(days=120),
            notes="Anchor account. 40h/mo retainer; multi-state (CA/WA).",
        )
        await assign(nw, a0, "lead"); await assign(nw, a1, "consultant")
        s_pol = await scope(nw, "policy", "Annual policy refresh", "active", "high")
        s_hb = await scope(nw, "handbook", "2026 handbook rebuild", "active", "high")
        await scope(nw, "compliance", "Multi-state compliance review", "planned", "medium")
        await task(nw, "Draft PTO policy update", "policy", "in_progress", "high", a0, tm(12), 6, s_pol)
        await task(nw, "OSHA 300A posting check", "compliance", "todo", "high", a1, TODAY - timedelta(days=3), 2)
        await task(nw, "Finalize handbook ToC", "handbook", "review", "medium", a0, tm(20), 4, s_hb)
        await task(nw, "Q1 onboarding audit", "audit", "done", "medium", a1, INQ, 8, done_at=NOW - timedelta(days=6))
        # this-month time = 46h > 40h budget → over budget
        await time(nw, a0, 12, tm(2), "Policy workshop", cat="policy")
        await time(nw, a0, 10, tm(4), "Handbook drafting", cat="handbook")
        await time(nw, a0, 8, tm(6), "Client sync + review", cat="strategy")
        await time(nw, a1, 9, tm(4), "Compliance scan", cat="compliance")
        await time(nw, a1, 7, tm(6), "OSHA posting", cat="compliance")
        await time(nw, a0, 20, INQ, "Prior-month carryover work", cat="policy")  # quarter/all-time

        # ------------------------------------------------------------------ #
        # 2) Acme Robotics — hours block (100h), ~64% burned
        # ------------------------------------------------------------------ #
        ac = await client(
            name="Acme Robotics", status="active", billing_model="hours_block",
            retainer_hours=100, industry="Manufacturing", headcount=90,
            jurisdictions=["TX"], contact_name="Sam Okafor", contact_email="sam@acme.test",
            lead_pro_id=a1, start_date=OLD, notes="100-hour block; org redesign engagement.",
        )
        await assign(ac, a1, "lead"); await assign(ac, a2, "jr")
        s_org = await scope(ac, "org_design", "Org redesign — engineering", "active", "high")
        await scope(ac, "team_direction", "HR team coaching cadence", "active", "medium")
        await task(ac, "Define leveling framework", "org_design", "in_progress", "high", a1, tm(15), 12, s_org)
        await task(ac, "Manager 1:1 templates", "team_direction", "done", "low", a2, INQ, 4, done_at=NOW - timedelta(days=12))
        await time(ac, a1, 10, tm(3), "Leveling design", cat="org_design")
        await time(ac, a2, 8, tm(5), "Template build", cat="team_direction")
        await time(ac, a1, 20, INQ, "Org mapping interviews", cat="org_design")
        await time(ac, a1, 16, OLD, "Kickoff + discovery", cat="org_design")
        await time(ac, a2, 10, OLD, "Data gathering", cat="other")

        # ------------------------------------------------------------------ #
        # 3) Globex Corp — hourly T&M ($185/hr)
        # ------------------------------------------------------------------ #
        gx = await client(
            name="Globex Corp", status="active", billing_model="hourly",
            billing_rate=185, industry="Technology", headcount=50,
            jurisdictions=["NY"], contact_name="Lena Park", contact_email="ops@globex.test",
            lead_pro_id=a2, start_date=INQ, notes="Time-and-materials; scaling hiring for Q3.",
        )
        await assign(gx, a2, "lead")
        await scope(gx, "hiring", "Scale hiring — Q3 (8 roles)", "active", "high")
        await scope(gx, "strategy", "Compensation strategy", "planned", "medium")
        await task(gx, "Build interview scorecards", "hiring", "in_progress", "high", a2, tm(10), 5)
        await task(gx, "Draft comp bands", "strategy", "todo", "medium", a2, TODAY - timedelta(days=2), 6)
        await time(gx, a2, 12, tm(3), "Scorecard design", cat="hiring")
        await time(gx, a2, 10, tm(6), "Recruiter calibration", cat="hiring")

        # ------------------------------------------------------------------ #
        # 4) Initech — fixed project ($25k)
        # ------------------------------------------------------------------ #
        it = await client(
            name="Initech", status="active", billing_model="project_fixed",
            project_fee=25000, industry="Financial Services", headcount=130,
            jurisdictions=["IL"], contact_name="Bill L.", contact_email="tps@initech.test",
            lead_pro_id=a0, start_date=INQ, notes="Fixed-fee full HR audit + remediation plan.",
        )
        await assign(it, a0, "lead"); await assign(it, a1, "consultant")
        s_aud = await scope(it, "audit", "HR audit — full", "active", "high")
        await task(it, "Records & I-9 audit", "audit", "done", "high", a0, INQ, 10, s_aud, done_at=NOW - timedelta(days=20))
        await task(it, "Remediation plan writeup", "audit", "in_progress", "high", a0, tm(18), 8, s_aud)
        await time(it, a0, 14, tm(4), "Findings synthesis", cat="audit")
        await time(it, a0, 20, INQ, "Audit fieldwork", cat="audit")
        await time(it, a1, 16, OLD, "Doc collection", cat="audit")

        # ------------------------------------------------------------------ #
        # 5) Umbrella Wellness — paused, has overdue tasks (at-risk)
        # ------------------------------------------------------------------ #
        um = await client(
            name="Umbrella Wellness", status="paused", billing_model="monthly_retainer",
            retainer_hours=20, retainer_period="monthly", billing_rate=175,
            industry="Healthcare", headcount=60, jurisdictions=["CA"],
            contact_name="Alice M.", contact_email="hr@umbrella.test",
            lead_pro_id=a1, start_date=OLD, notes="Paused pending renewal; two items overdue.",
        )
        await assign(um, a1, "lead")
        await scope(um, "coaching", "Leadership coaching", "on_hold", "medium")
        await task(um, "Close out leave case", "compliance", "blocked", "high", a1, TODAY - timedelta(days=5), 3)
        await task(um, "Renewal proposal", "strategy", "todo", "high", a1, TODAY - timedelta(days=10), 2)
        await time(um, a1, 5, tm(2), "Renewal prep", cat="strategy")

        # ------------------------------------------------------------------ #
        # 6) Stark Industries — prospect (pipeline, no work yet)
        # ------------------------------------------------------------------ #
        st = await client(
            name="Stark Industries", status="prospect", billing_model="monthly_retainer",
            retainer_hours=30, retainer_period="monthly", billing_rate=225,
            industry="Manufacturing", headcount=500, jurisdictions=["CA", "NY", "TX"],
            contact_name="Pepper P.", contact_email="pepper@stark.test",
            lead_pro_id=a0, notes="Pipeline — proposal sent, awaiting signature.",
        )
        await scope(st, "strategy", "Proposed: fractional HR leadership", "planned", "medium")

        # --- summary ---
        n_cli = await conn.fetchval("SELECT COUNT(*) FROM fractional_clients WHERE name = ANY($1::text[])", SEED_NAMES)
        n_tsk = await conn.fetchval("SELECT COUNT(*) FROM fractional_tasks")
        n_tim = await conn.fetchval("SELECT COUNT(*) FROM fractional_time_entries")
        print(f"Seeded {n_cli} clients. Tasks total={n_tsk}, time entries total={n_tim}.")
        print(f"Lead/assignee pros: {[r['email'] for r in admins][:3]}")
        print(f"Northwind linked to company: {comp['name'] if comp else '(none found)'}")
        print("At-risk should show: Northwind Health (over budget), Umbrella Wellness (overdue).")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

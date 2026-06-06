#!/usr/bin/env python3
"""End-to-end backend smoke test for the Matcha-X self-serve onboarding wizard.

Drives the REAL endpoints exactly as the frontend would — no UI:

  1. POST /api/auth/register/business  (tier=matcha_x)  -> admin + company + token
  2. GET  /api/matcha-x-onboarding/status               -> step=locations
  3. POST /api/matcha-x-onboarding/locations  x2         -> Denver CO + Los Angeles CA
  4. POST /api/employees/bulk-upload?send_invitations=false  (10-row CSV)
  5. GET  /api/matcha-x-onboarding/status               -> step=build
  6. POST /api/matcha-x-onboarding/build/stream          -> consume + print SSE frames
  7. GET  /api/matcha-x-onboarding/status               -> step=done

Cost control: forces the platform setting `jurisdiction_research_model_mode=lite`
(gemini-3.1-flash-lite) before the build, via a single-row UPSERT into the dev
`platform_settings` table. The getter caches for 30s, so we wait it out.

All emails use RFC 2606 reserved domains (@acme.test). No real invitations sent
(send_invitations=false). DEV ONLY — talks to localhost:5432 via dev-remote.sh.

Run:  cd server && ./venv/bin/python scripts/test_matcha_x_onboarding.py
Revert model mode afterwards: ./venv/bin/python scripts/test_matcha_x_onboarding.py --restore-mode light
"""

import asyncio
import datetime as dt
import io
import json
import os
import sys
import time

import requests

BASE = os.environ.get("MATCHA_BASE", "http://localhost:8001/api")
GETTER_CACHE_TTL = 30  # platform_settings getter cache; wait past it after the UPSERT

# Reserved (RFC 2606) domain — guaranteed non-deliverable. Use example.com (not
# *.test): pydantic EmailStr / email_validator rejects the special-use *.test /
# *.invalid TLDs, but accepts example.com, which is equally reserved.
DOMAIN = "example.com"
PASSWORD = "Testpass123!"

GREEN, RED, DIM, VIOLET, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[35m", "\033[0m"


def ok(msg):
    print(f"{GREEN}✓{RESET} {msg}")


def fail(msg):
    print(f"{RED}✗ {msg}{RESET}")
    sys.exit(1)


def _database_url():
    # Prefer the backend's own config so we hit the exact same dev DB.
    try:
        from app.config import settings  # type: ignore

        return settings.database_url
    except Exception:
        url = os.environ.get("DATABASE_URL")
        if url:
            return url
        # Last resort: scrape .env next to the server package.
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for line in open(os.path.join(here, ".env")):
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip()
    return None


async def _set_model_mode(mode: str):
    import asyncpg  # type: ignore

    url = _database_url()
    if not url:
        fail("Could not resolve DATABASE_URL")
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(
            """
            INSERT INTO platform_settings (key, value, updated_at)
            VALUES ('jurisdiction_research_model_mode', $1::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """,
            json.dumps(mode),
        )
        val = await conn.fetchval(
            "SELECT value FROM platform_settings WHERE key = 'jurisdiction_research_model_mode'"
        )
    finally:
        await conn.close()
    return val


def set_model_mode(mode: str):
    val = asyncio.run(_set_model_mode(mode))
    ok(f"platform_settings jurisdiction_research_model_mode = {val} "
       f"({'gemini-3.1-flash-lite' if mode == 'lite' else mode})")


async def _activate_incidents(email: str):
    """Flip enabled_features.incidents=true for the company owning `email` —
    the exact flag the Stripe checkout.session.completed webhook would set.
    Bypasses the Subscribe paywall for a dev test tenant. DEV ONLY."""
    import asyncpg  # type: ignore

    url = _database_url()
    if not url:
        fail("Could not resolve DATABASE_URL")
    conn = await asyncpg.connect(url)
    try:
        row = await conn.fetchrow(
            """
            UPDATE companies
               SET enabled_features =
                   jsonb_set(COALESCE(enabled_features, '{}'::jsonb),
                             '{incidents}', 'true'::jsonb)
             WHERE id = (
                 SELECT c.company_id FROM clients c
                 JOIN users u ON u.id = c.user_id
                 WHERE u.email = $1
             )
            RETURNING id, name, enabled_features->'incidents' AS incidents
            """,
            email,
        )
    finally:
        await conn.close()
    if not row:
        fail(f"no company found for {email}")
    return row


def activate_incidents(email: str):
    row = asyncio.run(_activate_incidents(email))
    ok(f"activated incidents for {row['name']} ({row['id']}) — incidents={row['incidents']}")
    print(f"{DIM}refresh/re-login in the UI; Subscribe gate is now bypassed.{RESET}")


def _utc(d: dt.date) -> dt.datetime:
    return dt.datetime.combine(d, dt.time(9, 0), tzinfo=dt.timezone.utc)


async def _seed_discipline(email: str):
    """Insert a realistic spread of progressive_discipline rows for the tenant's
    employees so /app/discipline looks populated. Direct insert (no API) so it
    skips manager emails + the supersede engine and lets us set every status /
    signature state explicitly. DEV ONLY — existing table, no DDL."""
    import asyncpg  # type: ignore

    url = _database_url()
    if not url:
        fail("Could not resolve DATABASE_URL")
    conn = await asyncpg.connect(url)
    try:
        row = await conn.fetchrow(
            """
            SELECT c.company_id AS company_id, comp.name AS company_name, c.user_id AS issued_by
            FROM clients c
            JOIN users u ON u.id = c.user_id
            JOIN companies comp ON comp.id = c.company_id
            WHERE u.email = $1
            """,
            email,
        )
        if not row:
            fail(f"no company found for {email}")
        company_id, issued_by = row["company_id"], row["issued_by"]
        emps = await conn.fetch(
            "SELECT id, first_name, last_name FROM employees WHERE org_id = $1 ORDER BY created_at LIMIT 10",
            company_id,
        )
        if len(emps) < 7:
            fail(f"need >=7 employees to seed a good spread, found {len(emps)}")

        today = dt.date.today()

        def issued(days_ago: int) -> dt.date:
            return today - dt.timedelta(days=days_ago)

        # Wipe any prior seed for a clean, idempotent re-run.
        await conn.execute("DELETE FROM progressive_discipline WHERE company_id = $1", company_id)

        # (emp_idx, type, severity, infraction, days_ago, lookback, status, sig,
        #  description, expected_improvement, review_in_days, override_reason)
        spec = [
            (0, "verbal_warning", "minor", "attendance", 210, 6, "escalated", "refused",
             "Three unexcused late arrivals within a two-week period.", None, None, None),
            (0, "written_warning", "moderate", "attendance", 55, 9, "active", "signed",
             "Continued tardiness after a prior verbal warning.", "Arrive by scheduled start time for 60 days.", 60, None),
            (1, "written_warning", "moderate", "performance", 30, 9, "active", "signed",
             "Repeated failure to meet documented quality targets.", "Meet the agreed QA threshold for two review cycles.", 45, None),
            (2, "final_warning", "severe", "safety", 14, 12, "active", "requested",
             "Bypassed a required lockout/tagout procedure on the line.", "Zero safety-procedure deviations going forward.", 30, None),
            (3, "verbal_warning", "moderate", "policy_violation", 410, 6, "expired", "refused",
             "Used a personal device on the floor against posted policy.", None, None, None),
            (4, "final_warning", "severe", "harassment", 21, 12, "active", "signed",
             "Substantiated complaint of inappropriate conduct toward a coworker.",
             "Complete harassment-prevention training; no further incidents.", 30,
             "Conduct severity warrants skipping intermediate steps per HR review."),
            (5, "suspension", "immediate_written", "gross_misconduct", 7, 12, "pending_signature", "requested",
             "Falsified time records across multiple shifts.", "Unpaid 3-day suspension; full compliance on return.", 14, None),
            (6, "pip", "severe", "performance", 10, 9, "active", "physical_uploaded",
             "Sustained underperformance across two evaluation periods.",
             "Hit all PIP milestones over the next 60 days.", 60, None),
        ]

        first_attendance_id = None
        created = []
        for (ei, dtype, sev, infraction, days, lookback, status, sig,
             desc, improve, review_days, override_reason) in spec:
            emp = emps[ei]
            issued_date = issued(days)
            expires = _utc(issued_date + dt.timedelta(days=30 * lookback))
            review_date = (issued_date + dt.timedelta(days=review_days)) if review_days else None
            escalated_from = first_attendance_id if (status == "active" and infraction == "attendance" and dtype == "written_warning") else None
            sig_requested_at = _utc(issued_date + dt.timedelta(days=1)) if sig in ("requested", "signed", "physical_uploaded") else None
            sig_completed_at = _utc(issued_date + dt.timedelta(days=3)) if sig in ("signed", "physical_uploaded") else None
            meeting_at = _utc(issued_date + dt.timedelta(days=1)) if status in ("active", "pending_signature", "escalated", "expired") else None

            rec_id = await conn.fetchval(
                """
                INSERT INTO progressive_discipline (
                    employee_id, company_id, discipline_type, issued_date, issued_by,
                    description, expected_improvement, review_date, status, infraction_type,
                    severity, lookback_months, expires_at, escalated_from_id, override_level,
                    override_reason, signature_status, signature_requested_at,
                    signature_completed_at, meeting_held_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)
                RETURNING id
                """,
                emp["id"], company_id, dtype, issued_date, issued_by,
                desc, improve, review_date, status, infraction,
                sev, lookback, expires, escalated_from, bool(override_reason),
                override_reason, sig, sig_requested_at, sig_completed_at, meeting_at,
            )
            if infraction == "attendance" and dtype == "verbal_warning":
                first_attendance_id = rec_id
            created.append((f"{emp['first_name']} {emp['last_name']}", dtype, status, sig))
        return row["company_name"], created
    finally:
        await conn.close()


def seed_discipline(email: str):
    company_name, created = asyncio.run(_seed_discipline(email))
    ok(f"seeded {len(created)} performance-action records for {company_name}")
    for name, dtype, status, sig in created:
        print(f"  {DIM}· {name:22} {dtype:16} {status:18} sig={sig}{RESET}")
    print(f"{DIM}refresh /app/discipline to view.{RESET}")


# (credential_type key, priority, review_status, due_days, ai_confidence, source)
_CRED_SPEC = [
    ("food_handler_card", "blocking", "approved", 30, None, "admin_manual"),
    ("background_check", "blocking", "approved", 7, None, "admin_manual"),
    ("drug_screening", "standard", "approved", 14, None, "auto_approved"),
    ("drivers_license", "optional", "approved", 30, None, "admin_manual"),
    ("tb_test", "standard", "pending", 30, 0.95, "ai_research"),
    ("cpr_cert", "optional", "pending", 60, 0.90, "ai_research"),
    ("health_clearance", "standard", "approved", 30, None, "admin_manual"),
]


async def _seed_credentialing(conn, company_id, reviewed_by, states):
    """Insert the credential-requirement TEMPLATE catalog for a company across its
    states (non-clinical role) — what /app/credential-templates renders. Returns
    the count. Idempotent: clears the company's templates first. Reference tables
    (credential_types, role_categories) must already be seeded."""
    role_id = await conn.fetchval("SELECT id FROM role_categories WHERE key = 'non_clinical'")
    if role_id is None:
        fail("role_categories not seeded (no 'non_clinical')")
    type_rows = await conn.fetch(
        "SELECT key, id FROM credential_types WHERE key = ANY($1::text[])",
        [s[0] for s in _CRED_SPEC],
    )
    type_id = {r["key"]: r["id"] for r in type_rows}
    missing = [s[0] for s in _CRED_SPEC if s[0] not in type_id]
    if missing:
        fail(f"credential_types missing in this DB: {missing}")

    reviewed_at = dt.datetime.combine(dt.date.today() - dt.timedelta(days=3), dt.time(10, 0))

    await conn.execute("DELETE FROM credential_requirement_templates WHERE company_id = $1", company_id)

    n = 0
    for state in states:
        for key, priority, review_status, due_days, ai_conf, source in _CRED_SPEC:
            approved = review_status in ("approved", "auto_approved")
            await conn.execute(
                """
                INSERT INTO credential_requirement_templates (
                    company_id, state, city, role_category_id, credential_type_id,
                    is_required, due_days, priority, source, ai_confidence,
                    review_status, reviewed_by, reviewed_at, is_active
                ) VALUES ($1,$2,NULL,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,true)
                """,
                company_id, state, role_id, type_id[key],
                priority != "optional", due_days, priority, source, ai_conf,
                review_status, (reviewed_by if approved else None),
                (reviewed_at if approved else None),
            )
            n += 1
    return n


async def _seed_credentialing_for_email(email: str):
    import asyncpg  # type: ignore

    url = _database_url()
    if not url:
        fail("Could not resolve DATABASE_URL")
    conn = await asyncpg.connect(url)
    try:
        row = await conn.fetchrow(
            """
            SELECT c.company_id AS company_id, comp.name AS company_name, c.user_id AS reviewed_by
            FROM clients c
            JOIN users u ON u.id = c.user_id
            JOIN companies comp ON comp.id = c.company_id
            WHERE u.email = $1
            """,
            email,
        )
        if not row:
            fail(f"no company found for {email}")
        states = [
            r["state"]
            for r in await conn.fetch(
                "SELECT DISTINCT UPPER(state) AS state FROM business_locations WHERE company_id = $1 AND is_active = true AND state <> '' ORDER BY 1",
                row["company_id"],
            )
        ]
        if not states:
            fail("no active locations with a state to scope templates to")
        n = await _seed_credentialing(conn, row["company_id"], row["reviewed_by"], states)
        return row["company_name"], states, n
    finally:
        await conn.close()


def seed_credentialing(email: str):
    company_name, states, n = asyncio.run(_seed_credentialing_for_email(email))
    ok(f"seeded {n} credential templates for {company_name} across {', '.join(states)}")
    print(f"{DIM}refresh /app/credential-templates to view.{RESET}")


def build_csv() -> bytes:
    """10 employees — 5 Los Angeles/CA, 5 Denver/CO — to mirror the two offices."""
    rows = [
        ("Ana", "Reyes", "CA", "Los Angeles", "Server", "Front of House"),
        ("Ben", "Cho", "CA", "Los Angeles", "Line Cook", "Kitchen"),
        ("Cleo", "Ramos", "CA", "Los Angeles", "Host", "Front of House"),
        ("Dani", "Okafor", "CA", "Los Angeles", "Shift Lead", "Management"),
        ("Esai", "Nguyen", "CA", "Los Angeles", "Dishwasher", "Kitchen"),
        ("Faye", "Brooks", "CO", "Denver", "Server", "Front of House"),
        ("Gus", "Hale", "CO", "Denver", "Line Cook", "Kitchen"),
        ("Hana", "Mori", "CO", "Denver", "Host", "Front of House"),
        ("Ivan", "Petrov", "CO", "Denver", "Shift Lead", "Management"),
        ("Juno", "Klein", "CO", "Denver", "Barback", "Bar"),
    ]
    buf = io.StringIO()
    buf.write("email,first_name,last_name,work_state,work_city,employment_type,job_title,department\n")
    for i, (fn, ln, st, city, title, dept) in enumerate(rows, 1):
        email = f"{fn.lower()}.{ln.lower()}+{i}@{DOMAIN}"
        buf.write(f"{email},{fn},{ln},{st},{city},full_time,{title},{dept}\n")
    return buf.getvalue().encode()


def login(email: str) -> dict:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD}, timeout=30)
    if r.status_code != 200:
        fail(f"login {email} -> {r.status_code}: {r.text[:200]}")
    token = r.json().get("access_token")
    if not token:
        fail(f"no access_token for {email}")
    return {"Authorization": f"Bearer {token}"}


def check_compliance_access(H: dict):
    """Positive path: an X tenant (compliance_lite via overlay) can READ the
    baseline the build wrote through the new shared_router endpoints."""
    locs = requests.get(f"{BASE}/compliance/locations", headers=H, timeout=30).json()
    if not locs:
        fail("no locations on /compliance/locations")
    ok(f"/compliance/locations -> {len(locs)} location(s)")

    loc_id = locs[0]["id"]
    rr = requests.get(f"{BASE}/compliance/locations/{loc_id}/requirements", headers=H, timeout=30)
    if rr.status_code != 200:
        fail(f"/compliance/locations/{{id}}/requirements -> {rr.status_code}: {rr.text[:200]}")
    reqs = rr.json()
    n = len(reqs) if isinstance(reqs, list) else len(reqs.get("requirements", []) if isinstance(reqs, dict) else [])
    if not n:
        fail("requirements list is empty — shared_router move or overlay not working")
    ok(f"/compliance/locations/{{id}}/requirements -> 200, {n} requirement(s) [compliance_lite gate]")

    for path in (f"/compliance/locations/{loc_id}/upcoming-legislation", "/compliance/summary"):
        sr = requests.get(f"{BASE}{path}", headers=H, timeout=30)
        if sr.status_code != 200:
            fail(f"{path} -> {sr.status_code}: {sr.text[:200]}")
        ok(f"{path} -> 200")

    # jurisdiction-stack stays Pro-only (raw admin/debug endpoint) → 403 for lite.
    js = requests.get(f"{BASE}/compliance/locations/{loc_id}/jurisdiction-stack", headers=H, timeout=30)
    if js.status_code not in (402, 403):
        fail(f"/compliance/.../jurisdiction-stack should be Pro-gated for lite, got {js.status_code}")
    ok(f"/compliance/.../jurisdiction-stack -> {js.status_code} (Pro-only, blocked for lite)")

    # Negative: a Pro-only endpoint must still 403 for the lite taste.
    dash = requests.get(f"{BASE}/compliance/dashboard", headers=H, timeout=30)
    if dash.status_code not in (402, 403):
        fail(f"/compliance/dashboard should be Pro-gated (403) for lite, got {dash.status_code}")
    ok(f"/compliance/dashboard -> {dash.status_code} (Pro-only, correctly blocked for lite)")


def assert_lite_tenant_blocked():
    """Negative gate: a matcha_lite tenant (no compliance/compliance_lite) is
    403 on the shared read-only endpoints."""
    stamp = int(time.time())
    email = f"lite+{stamp}@{DOMAIN}"
    r = requests.post(
        f"{BASE}/auth/register/business",
        json={"tier": "matcha_lite", "company_name": f"Lite Neg {stamp}", "name": "Lite Admin",
              "email": email, "password": PASSWORD, "headcount": 5},
        timeout=30,
    )
    if r.status_code != 200:
        fail(f"lite register {r.status_code}: {r.text[:200]}")
    H = {"Authorization": f"Bearer {r.json()['access_token']}"}
    sr = requests.get(f"{BASE}/compliance/summary", headers=H, timeout=30)
    if sr.status_code not in (402, 403):
        fail(f"matcha_lite should be 403 on /compliance/summary, got {sr.status_code}")
    ok(f"matcha_lite /compliance/summary -> {sr.status_code} (correctly blocked — no compliance_lite)")


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--restore-mode":
        set_model_mode(sys.argv[2])
        return
    if len(sys.argv) >= 3 and sys.argv[1] == "--activate":
        activate_incidents(sys.argv[2])
        return
    if len(sys.argv) >= 3 and sys.argv[1] == "--seed-discipline":
        seed_discipline(sys.argv[2])
        return
    if len(sys.argv) >= 3 and sys.argv[1] == "--seed-credentialing":
        seed_credentialing(sys.argv[2])
        return
    if len(sys.argv) >= 3 and sys.argv[1] == "--check-compliance":
        # Verify the compliance_lite read access against an already-built X tenant
        # (no expensive rebuild). Usage: --check-compliance <admin-email>
        print(f"{DIM}checking compliance_lite access for {sys.argv[2]}{RESET}")
        check_compliance_access(login(sys.argv[2]))
        assert_lite_tenant_blocked()
        print(f"\n{GREEN}COMPLIANCE ACCESS CHECKS PASSED{RESET}")
        return

    stamp = int(time.time())
    admin_email = f"admin+{stamp}@{DOMAIN}"
    company = f"Matcha X Test {stamp}"

    print(f"{DIM}BASE={BASE}  admin={admin_email}{RESET}\n")

    # 0. Force flash-lite for the live research, then wait past the getter cache.
    set_model_mode("lite")
    print(f"{DIM}waiting {GETTER_CACHE_TTL + 2}s for backend settings cache to expire…{RESET}")
    time.sleep(GETTER_CACHE_TTL + 2)

    # 1. Register the Matcha-X tenant + admin.
    r = requests.post(
        f"{BASE}/auth/register/business",
        json={
            "tier": "matcha_x",
            "company_name": company,
            "name": "Test Admin",
            "email": admin_email,
            "password": PASSWORD,
            "headcount": 10,
        },
        timeout=30,
    )
    if r.status_code != 200:
        fail(f"register {r.status_code}: {r.text[:300]}")
    reg = r.json()
    token = reg.get("access_token")
    if not token:
        fail(f"no access_token in register response: {reg}")
    if reg.get("signup_source") != "matcha_x":
        fail(f"unexpected signup_source: {reg.get('signup_source')}")
    H = {"Authorization": f"Bearer {token}"}
    ok(f"registered — signup_source={reg.get('signup_source')} status={reg.get('company_status')}")

    # 2. Status: expect locations.
    s = requests.get(f"{BASE}/matcha-x-onboarding/status", headers=H, timeout=30).json()
    if s.get("step") != "locations":
        fail(f"expected step=locations, got {s}")
    ok(f"status step={s['step']} (handbook_audit gate admits matcha_x)")

    # 3. Two locations.
    for loc in (
        {"name": "Denver Office", "city": "Denver", "state": "CO", "zipcode": "80202"},
        {"name": "Los Angeles Office", "city": "Los Angeles", "state": "CA", "zipcode": "90012"},
    ):
        lr = requests.post(f"{BASE}/matcha-x-onboarding/locations", headers=H, json=loc, timeout=30)
        if lr.status_code != 200:
            fail(f"location {loc['city']} -> {lr.status_code}: {lr.text[:300]}")
        ok(f"location added: {loc['city']}, {loc['state']} {loc['zipcode']}")

    # 4. Status: expect people.
    s = requests.get(f"{BASE}/matcha-x-onboarding/status", headers=H, timeout=30).json()
    if s.get("step") != "people":
        fail(f"expected step=people, got {s}")
    ok(f"status step={s['step']} (locations_count={s['locations_count']})")

    # 5. Bulk employees (no invitations).
    csv_bytes = build_csv()
    br = requests.post(
        f"{BASE}/employees/bulk-upload",
        headers=H,
        params={"send_invitations": "false"},
        files={"file": ("employees.csv", csv_bytes, "text/csv")},
        timeout=60,
    )
    if br.status_code != 200:
        fail(f"bulk-upload {br.status_code}: {br.text[:400]}")
    bj = br.json()
    if bj.get("created") != 10 or bj.get("failed"):
        fail(f"bulk-upload created={bj.get('created')} failed={bj.get('failed')} errors={bj.get('errors')}")
    ok(f"bulk-upload created={bj['created']} failed={bj['failed']}")

    # 6. Status: expect build.
    s = requests.get(f"{BASE}/matcha-x-onboarding/status", headers=H, timeout=30).json()
    if s.get("step") != "build":
        fail(f"expected step=build, got {s}")
    ok(f"status step={s['step']} (employees_count={s['employees_count']})")

    # 7. THE FINALE — live build SSE stream.
    print(f"\n{DIM}── build/stream (live, flash-lite) ─────────────────────────{RESET}")
    complete = None
    tally = {}
    with requests.post(
        f"{BASE}/matcha-x-onboarding/build/stream",
        headers={**H, "Content-Type": "application/json"},
        json={"handbook_url": None},
        stream=True,
        timeout=(30, 600),  # (connect, read) — generous read; build is uncapped/live
    ) as resp:
        if resp.status_code != 200:
            fail(f"build/stream {resp.status_code}: {resp.text[:300]}")
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw or raw.startswith(":"):  # heartbeat / keepalive
                continue
            if not raw.startswith("data: "):
                continue
            payload = raw[6:].strip()
            if payload == "[DONE]":
                break
            try:
                ev = json.loads(payload)
            except json.JSONDecodeError:
                continue
            t = ev.get("type", "?")
            tally[t] = tally.get(t, 0) + 1
            label = ev.get("label", "")
            msg = ev.get("message", "")
            if t == "location_built":
                extra = f"covered={ev.get('covered')} codified_new={ev.get('codified_new')} live={ev.get('researched_live')}"
                print(f"  {GREEN}● location_built{RESET} [{label}] {extra}")
            elif t in ("researching", "discovering_sources", "repository_refresh", "trigger_research"):
                print(f"  {VIOLET}◇ {t}{RESET} [{label}] {DIM}{msg[:80]}{RESET}")
            elif t == "complete":
                complete = ev
                print(f"  {GREEN}■ complete{RESET} {msg}")
            elif t in ("error", "warning"):
                print(f"  {RED}! {t}{RESET} {msg[:120]}")
            else:
                tag = f"[{label}] " if label else ""
                print(f"  {DIM}· {t} {tag}{msg[:80]}{RESET}")

    if not complete:
        fail("stream ended without a `complete` frame")
    print(
        f"\n{GREEN}complete:{RESET} locations={complete.get('locations')} "
        f"jurisdictions={complete.get('jurisdictions')} requirements={complete.get('requirements')} "
        f"codified_new={complete.get('codified_new')} "
        f"handbook_coverage_pct={complete.get('handbook_coverage_pct')}"
    )
    if complete.get("locations") != 2:
        fail(f"expected locations=2 in complete, got {complete.get('locations')}")
    if not complete.get("requirements"):
        fail("complete.requirements is 0 — no compliance_requirements were written")
    print(f"  {DIM}frame tally: {tally}{RESET}")

    # 8. Status: expect done.
    s = requests.get(f"{BASE}/matcha-x-onboarding/status", headers=H, timeout=30).json()
    if s.get("step") != "done":
        fail(f"expected step=done, got {s}")
    ok(f"status step={s['step']} (built={s['built']})")

    # 9. Compliance-lite read access — view the baseline the build just wrote.
    print(f"\n{DIM}── compliance_lite read access ─────────────────────────────{RESET}")
    check_compliance_access(H)

    print(f"\n{GREEN}ALL STEPS PASSED{RESET}")
    print(f"{DIM}restore model mode with: ./venv/bin/python scripts/test_matcha_x_onboarding.py --restore-mode light{RESET}")


if __name__ == "__main__":
    main()

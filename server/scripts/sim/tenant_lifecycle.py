#!/usr/bin/env python3
"""End-to-end tenant lifecycle simulation: signup -> gaps -> admin fix -> covered.

Drives the REAL HTTP routes against a running dev backend (dev-remote.sh, :8001)
so the gates, the tier overlay and the codified filter all execute exactly as
they would for a customer. Nothing here reaches into a service function to skip
a route it doesn't like.

The story it tells, in five stages:

  1. SIGNUP   a manufacturer registers, gets a work location, runs its first
              compliance check.
  2. BEFORE   measure what the TENANT sees (codified-only gate ON) against what
              the statutory checklist says a manufacturer owes. The delta is the
              product gap: rows we researched but never codified are invisible.
  3. ADMIN    measure what the MASTER ADMIN sees on the fit map — the same delta,
              bucketed by why each key is missing, which is the work queue.
  4. FIX      pull the levers in order: classify -> confirm -> reconcile.
  5. AFTER    re-run the tenant's check and re-measure. Coverage should rise and
              every row the tenant sees must still be codified.

Read-only against prod by construction: it refuses to run unless DATABASE_URL
points at a loopback host. Test identities use RFC 2606 reserved domains, so a
stray invitation email cannot leave the building.

Usage:
    cd server && python3 scripts/sim/tenant_lifecycle.py
    python3 scripts/sim/tenant_lifecycle.py --keep      # leave the tenant behind
    python3 scripts/sim/tenant_lifecycle.py --stage before   # stop after BEFORE
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncpg  # noqa: E402
import httpx  # noqa: E402

API = os.getenv("SIM_API", "http://127.0.0.1:8001/api")
DB = os.getenv("DATABASE_URL", "postgresql://matcha:matcha_dev@127.0.0.1:5432/matcha")

# RFC 2606 reserved — cannot resolve, cannot bounce. Note it is example.com and
# NOT a `.test` domain: pydantic's EmailStr (via email-validator) rejects
# `.test`/`.invalid` as special-use, so the signup route 422s on them before any
# of this runs. example.com validates AND is caught by the outbound
# reserved-domain guard in services/email.py.
TENANT_EMAIL = "ironoak.sim@example.com"
TENANT_COMPANY = "Iron Oak Fabrication (SIM)"
TENANT_PASSWORD = "SimTenant2026!"
MASTER_ADMIN_EMAIL = "tajatheprince@gmail.com"

# California manufacturer: the state carries both a labor-code and a Title-8
# authority index, and the federal stock (29 CFR 1910/1904/825, 40 CFR 26x) is
# the manufacturing core keyset's own spine — so every lever has something to
# pull on. A state with no authority index would stall at reconcile for reasons
# that have nothing to do with the pipeline's health.
LOCATION = {
    "name": "Iron Oak Fab — Fresno Plant",
    "address": "2400 S East Ave",
    "city": "Fresno",
    "state": "CA",
    "county": "Fresno",
    "zipcode": "93706",
}
INDUSTRY = "Manufacturing"


# ---------------------------------------------------------------- presentation

class C:
    B = "\033[1m"
    DIM = "\033[2m"
    G = "\033[32m"
    Y = "\033[33m"
    R = "\033[31m"
    CY = "\033[36m"
    X = "\033[0m"


def stage(n: Any, title: str) -> None:
    print(f"\n{C.B}{C.CY}{'=' * 74}{C.X}")
    print(f"{C.B}{C.CY}  STAGE {n}: {title}{C.X}")
    print(f"{C.B}{C.CY}{'=' * 74}{C.X}")


def step(msg: str) -> None:
    print(f"  {C.DIM}·{C.X} {msg}")


def ok(msg: str) -> None:
    print(f"  {C.G}✓{C.X} {msg}")


def warn(msg: str) -> None:
    print(f"  {C.Y}!{C.X} {msg}")


def bad(msg: str) -> None:
    print(f"  {C.R}✗{C.X} {msg}")


def kv(k: str, v: Any) -> None:
    print(f"      {C.DIM}{k:<34}{C.X} {v}")


# ---------------------------------------------------------------- assertions

class Results:
    def __init__(self) -> None:
        self.checks: List[tuple[str, bool, str]] = []

    def expect(self, name: str, cond: bool, detail: str = "") -> bool:
        self.checks.append((name, bool(cond), detail))
        (ok if cond else bad)(f"{name}{(' — ' + detail) if detail else ''}")
        return bool(cond)

    def report(self) -> int:
        passed = sum(1 for _, c, _ in self.checks if c)
        total = len(self.checks)
        print(f"\n{C.B}{'=' * 74}{C.X}")
        color = C.G if passed == total else C.R
        print(f"{C.B}  ASSERTIONS: {color}{passed}/{total} passed{C.X}")
        for name, cond, detail in self.checks:
            if not cond:
                print(f"    {C.R}FAIL{C.X} {name}{(' — ' + detail) if detail else ''}")
        print(f"{C.B}{'=' * 74}{C.X}")
        return 0 if passed == total else 1


R = Results()


# ---------------------------------------------------------------- infra

def guard_not_prod() -> None:
    """Refuse to touch anything that isn't a loopback DB.

    This script writes: it creates a company, a user, and re-runs compliance
    checks. Prod (RDS, and the legacy :5433 container) is off limits, and the
    laptop reaches RDS through a tunnel on localhost:5434 — so a host check
    alone would wave that through. Port is part of the identity.
    """
    lowered = DB.lower()
    if not any(h in lowered for h in ("127.0.0.1", "localhost", "::1")):
        sys.exit(f"REFUSING: DATABASE_URL is not loopback: {DB}")
    if "5434" in DB or "rds.amazonaws.com" in lowered or "5433" in DB:
        sys.exit(f"REFUSING: DATABASE_URL looks like the prod tunnel/instance: {DB}")


def mint(user_id: str, email: str, role: str) -> str:
    """Sign a token in-process rather than logging in.

    Passwords in a dev DB are whatever the last prod refresh left behind, and
    the master admin's is not ours to guess. The JWT secret is the same one the
    running backend validates against, so a minted token is indistinguishable
    from a logged-in one at every gate this simulation cares about.
    """
    from app.config import get_settings, load_settings
    from app.core.services.auth import create_access_token
    try:
        get_settings()
    except RuntimeError:
        load_settings()
    return create_access_token(UUID(user_id), email, role, expires_delta=timedelta(hours=2))


async def db() -> asyncpg.Connection:
    return await asyncpg.connect(DB)


def hdr(tok: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


async def sse_drain(client: httpx.AsyncClient, url: str, tok: str, label: str) -> List[dict]:
    """POST an SSE endpoint and drain it. The stream IS the work — a client that
    disconnects early cancels it server-side, so this must read to completion."""
    events: List[dict] = []
    async with client.stream("POST", url, headers=hdr(tok), timeout=900.0) as r:
        if r.status_code != 200:
            body = (await r.aread()).decode()[:300]
            bad(f"{label}: HTTP {r.status_code} {body}")
            return events
        async for line in r.aiter_lines():
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            events.append(ev)
            phase = ev.get("phase") or ev.get("type") or ev.get("status")
            msg = ev.get("message") or ev.get("detail") or ""
            if phase:
                print(f"      {C.DIM}[{label}] {phase} {str(msg)[:80]}{C.X}")
    return events


# ---------------------------------------------------------------- measurement

def norm_key_of(row: dict) -> Optional[str]:
    """Reuse the evals' own key normalizer so this measures what they measure."""
    from app.core.services.compliance_evals.keys import normalize_key
    return normalize_key(row)


def core_expectations() -> Dict[str, Set[str]]:
    from app.core.services.compliance_evals.industry_keysets import core_keys
    return core_keys("manufacturing")


async def measure_tenant(client: httpx.AsyncClient, tok: str, loc_id: str) -> Dict[str, Any]:
    """What the BUSINESS sees, through its own route, with its own token."""
    r = await client.get(f"{API}/compliance/locations/{loc_id}/requirements", headers=hdr(tok))
    r.raise_for_status()
    payload = r.json()
    reqs = payload if isinstance(payload, list) else payload.get("requirements", [])
    return {"count": len(reqs), "rows": reqs}


async def measure_fitmap(client: httpx.AsyncClient, tok: str, company_id: str) -> Dict[str, Any]:
    r = await client.get(
        f"{API}/admin/onboarding/companies/{company_id}/fit-map", headers=hdr(tok)
    )
    r.raise_for_status()
    return r.json()


async def codified_audit(conn: asyncpg.Connection, location_id: str) -> Dict[str, Any]:
    """Ground truth from the DB: of the rows PROJECTED to this tenant, how many
    carry the full codified trio? The tenant route applies the gate, so this is
    the honest denominator behind what it returns.

    The projection is keyed by LOCATION, not company — a requirement is a
    property of where you operate, not of who you are.
    """
    rows = await conn.fetch(
        """
        SELECT cr.id, cr.jurisdiction_requirement_id IS NULL AS unlinked,
               (jr.statute_citation IS NOT NULL
                AND jr.citation_verified_at IS NOT NULL
                AND jr.citation_item_id IS NOT NULL) AS codified
        FROM compliance_requirements cr
        LEFT JOIN jurisdiction_requirements jr ON jr.id = cr.jurisdiction_requirement_id
        WHERE cr.location_id = $1
        """,
        UUID(location_id),
    )
    return {
        "projected": len(rows),
        "codified": sum(1 for r in rows if r["codified"]),
        "unlinked": sum(1 for r in rows if r["unlinked"]),
    }


# ---------------------------------------------------------------- stages

async def stage_reset(conn: asyncpg.Connection) -> None:
    """Idempotent teardown of a prior run. Data only — never schema."""
    cid = await conn.fetchval("SELECT id FROM companies WHERE name = $1", TENANT_COMPANY)
    if not cid:
        step("no prior simulation tenant")
        return
    # Order is forced: companies.owner_id FKs users, so the user cannot go first.
    # compliance_requirements / business_locations / clients cascade off the
    # company, so dropping it takes the tenant's whole footprint with it.
    await conn.execute("DELETE FROM companies WHERE id = $1", cid)
    await conn.execute("DELETE FROM users WHERE email = $1", TENANT_EMAIL)
    ok(f"removed prior simulation tenant {cid}")


async def stage_signup(client: httpx.AsyncClient, conn: asyncpg.Connection) -> Dict[str, str]:
    stage(1, "SIGNUP — a manufacturer registers")

    r = await client.post(f"{API}/auth/register/business", json={
        "company_name": TENANT_COMPANY,
        "industry": INDUSTRY,
        "company_size": "51-200",
        "headcount": 120,
        "jurisdiction_count": 2,
        "email": TENANT_EMAIL,
        "password": TENANT_PASSWORD,
        "name": "Dana Okafor",
        "job_title": "Director of Operations",
        "tier": "matcha_compliance",
    })
    if r.status_code not in (200, 201):
        sys.exit(f"signup failed: {r.status_code} {r.text[:400]}")
    ok(f"registered {TENANT_COMPANY} via /auth/register/business")

    # A business user's company lives on `clients`, not on `users` — the users
    # table is identity-only and carries no tenant column.
    row = await conn.fetchrow(
        """
        SELECT u.id, u.role, cl.company_id
        FROM users u JOIN clients cl ON cl.user_id = u.id
        WHERE u.email = $1
        """,
        TENANT_EMAIL,
    )
    if not row:
        sys.exit("signup returned 200 but no client row was created")
    company_id, user_id = str(row["company_id"]), str(row["id"])
    kv("company_id", company_id)

    # Stripe's checkout.session.completed is what flips this in production. The
    # payment rail is out of scope here, so apply the webhook's exact effect and
    # say so, rather than pretending the tenant paid.
    await conn.execute(
        """
        UPDATE companies
        SET status = 'approved',
            enabled_features = COALESCE(enabled_features, '{}'::jsonb)
                               || '{"compliance": true}'::jsonb
        WHERE id = $1
        """,
        UUID(company_id),
    )
    ok("activated compliance (simulating the Stripe webhook)")

    # Through the real route, not an INSERT: create_location() is what resolves
    # the jurisdiction and reports repository coverage. A hand-written INSERT
    # leaves jurisdiction_id NULL, and every downstream projection joins on it —
    # so the check "succeeds" and writes nothing.
    tenant_tok = mint(user_id, TENANT_EMAIL, "client")
    r = await client.post(
        f"{API}/compliance/locations", headers=hdr(tenant_tok),
        json={**LOCATION, "country_code": "US", "naics": "332710",
              "max_employees": 120, "annual_avg_employees": 120},
    )
    if r.status_code not in (200, 201):
        sys.exit(f"location create failed: {r.status_code} {r.text[:300]}")
    loc_id = r.json()["id"]
    ok(f"added work location: {LOCATION['city']}, {LOCATION['state']}")

    jid = await conn.fetchval(
        "SELECT jurisdiction_id FROM business_locations WHERE id = $1", UUID(loc_id)
    )
    kv("resolved jurisdiction_id", jid or f"{C.R}NULL — nothing will project{C.X}")
    R.expect("the new location resolved to a jurisdiction", jid is not None,
             "a NULL jurisdiction_id silently projects zero requirements")
    return {"company_id": company_id, "user_id": user_id, "location_id": str(loc_id)}


async def stage_check(client: httpx.AsyncClient, tok: str, loc_id: str, label: str) -> None:
    step(f"running the compliance check ({label}) — this is a live Gemini path, be patient")
    await sse_drain(client, f"{API}/compliance/locations/{loc_id}/check", tok, label)


async def stage_measure(
    client: httpx.AsyncClient, conn: asyncpg.Connection,
    tenant_tok: str, admin_tok: str, ids: Dict[str, str], when: str,
) -> Dict[str, Any]:
    tenant = await measure_tenant(client, tenant_tok, ids["location_id"])
    audit = await codified_audit(conn, ids["location_id"])
    fit = await measure_fitmap(client, admin_tok, ids["company_id"])

    counts = fit.get("counts", {})
    print(f"\n  {C.B}What the TENANT sees ({when}){C.X}")
    kv("requirements returned by their API", tenant["count"])
    kv("rows projected to them (DB)", audit["projected"])
    kv("…of those, codified (full trio)", audit["codified"])
    kv("…unlinked to any catalog row", audit["unlinked"])

    print(f"\n  {C.B}What the MASTER ADMIN sees ({when}){C.X}")
    kv("industry resolved", fit.get("industry"))
    kv("checklist provenance", fit.get("provenance"))
    kv("visible (codified + projected)", counts.get("visible"))
    kv("gated (projected, uncodified)", counts.get("gated"))
    kv("missing (never researched)", counts.get("missing"))
    kv("codifiable now (auto-reconcilable)", counts.get("codifiable_now"))

    buckets = fit.get("buckets") or fit.get("categories") or []
    return {"tenant": tenant, "audit": audit, "fit": fit, "buckets": buckets}


async def keys_now(conn: asyncpg.Connection) -> int:
    return await conn.fetchval(
        "SELECT count(regulation_key) FROM authority_item_classifications"
    )


async def await_task(conn: asyncpg.Connection, probe, label: str, timeout_s: int = 900) -> None:
    """Poll until `probe` stops moving. Classify/key passes dispatch to Celery
    and return 'running' immediately, so there is nothing to await on the HTTP
    response — the DB is the only honest completion signal."""
    last, stable = await probe(conn), 0
    for _ in range(timeout_s // 5):
        await asyncio.sleep(5)
        cur = await probe(conn)
        if cur != last:
            print(f"      {C.DIM}[{label}] {last} → {cur}{C.X}")
            last, stable = cur, 0
        else:
            stable += 1
            # 3 minutes of stillness. A Gemini batch over ~40 sections routinely
            # runs longer than a minute and writes nothing until it returns, so a
            # short window reads "done" while the first call is still in flight.
            if stable >= 36:
                return
    warn(f"{label}: timed out after {timeout_s}s")


async def stage_fix(client: httpx.AsyncClient, conn: asyncpg.Connection, admin_tok: str) -> None:
    stage(4, "FIX — pull the levers: classify → propose-keys → confirm → reconcile")

    indexes = await conn.fetch(
        """
        SELECT slug, item_count, unclassified_count
        FROM authority_indexes
        WHERE item_count > 0
        ORDER BY item_count DESC
        """
    )
    for ix in indexes:
        kv(ix["slug"], f"{ix['item_count']} items, {ix['unclassified_count']} unclassified")

    for ix in indexes:
        if ix["unclassified_count"] == 0:
            continue
        step(f"classify {ix['slug']}")
        r = await client.post(
            f"{API}/admin/scope-registry/authority/{ix['slug']}/classify",
            headers=hdr(admin_tok), timeout=900.0,
        )
        if r.status_code != 200:
            bad(f"classify {ix['slug']}: HTTP {r.status_code} {r.text[:200]}")
            continue
        kv(f"{ix['slug']} classify", json.dumps(r.json())[:120])

    # The key pass. Without it every AI-classified section keeps a NULL key and
    # `match_codifications` skips it — which is why 353 classifications had
    # produced exactly zero codifications before this existed.
    before_keys = await keys_now(conn)
    kv("classifications carrying a key (before)", before_keys)
    for ix in indexes:
        step(f"propose keys for {ix['slug']}")
        r = await client.post(
            f"{API}/admin/scope-registry/authority/{ix['slug']}/propose-keys",
            headers=hdr(admin_tok), timeout=60.0,
        )
        if r.status_code != 200:
            bad(f"propose-keys {ix['slug']}: HTTP {r.status_code} {r.text[:200]}")
    await await_task(conn, keys_now, "propose-keys")
    after_keys = await keys_now(conn)
    kv("classifications carrying a key (after)", after_keys)
    R.expect(
        "the key pass minted keys the AI path could not",
        after_keys > before_keys,
        f"{before_keys} → {after_keys}",
    )

    # Confirm every provisional classification. In production a human reviews
    # these in the studio; the simulation is measuring whether the PIPELINE can
    # carry a key end-to-end, so it approves wholesale and says so.
    item_ids = [
        str(r["item_id"]) for r in await conn.fetch(
            "SELECT item_id FROM authority_item_classifications WHERE status = 'provisional'"
        )
    ]
    step(f"confirming {len(item_ids)} provisional classifications (a human does this in the studio)")
    for i in range(0, len(item_ids), 200):
        r = await client.post(
            f"{API}/admin/scope-registry/classifications/confirm",
            headers=hdr(admin_tok), json={"item_ids": item_ids[i:i + 200]}, timeout=300.0,
        )
        if r.status_code != 200:
            bad(f"confirm batch {i}: HTTP {r.status_code} {r.text[:200]}")

    keyed = await conn.fetchrow(
        """
        SELECT count(*) AS total, count(regulation_key) AS with_key
        FROM authority_item_classifications WHERE status = 'confirmed'
        """
    )
    kv("confirmed classifications", keyed["total"])
    kv("…carrying a regulation_key", keyed["with_key"])
    R.expect(
        "confirmed classifications carry regulation keys",
        keyed["with_key"] > 50,
        f"{keyed['with_key']}/{keyed['total']} — a NULL-key classification can never codify",
    )

    step("reconcile (bind catalog rows to authority items)")
    r = await client.post(f"{API}/admin/scope-registry/reconcile", headers=hdr(admin_tok), timeout=600.0)
    if r.status_code == 200:
        kv("reconcile", json.dumps(r.json())[:200])
    else:
        bad(f"reconcile: HTTP {r.status_code} {r.text[:200]}")


# ---------------------------------------------------------------- main

async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="leave the tenant in place")
    ap.add_argument("--stage", choices=["signup", "before", "admin", "fix", "after"],
                    default="after", help="stop after this stage")
    args = ap.parse_args()

    guard_not_prod()
    conn = await db()
    try:
        admin = await conn.fetchrow(
            "SELECT id, email FROM users WHERE email = $1", MASTER_ADMIN_EMAIL
        )
        if not admin:
            sys.exit(f"no master admin {MASTER_ADMIN_EMAIL} in this DB")
        admin_tok = mint(str(admin["id"]), admin["email"], "admin")

        gate = await conn.fetchval(
            "SELECT value FROM platform_settings WHERE key = 'tenant_codified_only'"
        )
        stage(0, "PRE-FLIGHT")
        kv("API", API)
        kv("DB", DB.split("@")[-1])
        kv("tenant_codified_only", gate)
        R.expect("codified-only gate is ON", bool(gate and json.loads(gate).get("enabled")),
                 "tenants must never see an uncodified requirement")
        await stage_reset(conn)

        async with httpx.AsyncClient(timeout=120.0) as client:
            ids = await stage_signup(client, conn)
            tenant_tok = mint(ids["user_id"], TENANT_EMAIL, "client")
            if args.stage == "signup":
                return R.report()

            stage(2, "BEFORE — the tenant's first compliance check")
            await stage_check(client, tenant_tok, ids["location_id"], "before")
            before = await stage_measure(client, conn, tenant_tok, admin_tok, ids, "before")
            if args.stage == "before":
                return R.report()

            stage(3, "ADMIN — the gap, bucketed by why")
            for b in before["buckets"]:
                if isinstance(b, dict) and b.get("missing"):
                    kv(b.get("category", "?"), f"missing {len(b['missing'])}")
            R.expect(
                "a brand-new manufacturer has real gaps",
                (before["fit"].get("counts", {}).get("gated", 0)
                 + before["fit"].get("counts", {}).get("missing", 0)) > 0,
                "if this passes trivially the checklist isn't being applied",
            )
            # Guarded against the vacuous pass: with an empty projection this is
            # 0 == 0, which "proves" the gate works on a tenant that has nothing
            # to hide. The projection must be non-empty for the equality to mean
            # anything.
            R.expect(
                "the check projected requirements at all",
                before["audit"]["projected"] > 0,
                "an empty projection makes every gate assertion below vacuous",
            )
            R.expect(
                "the tenant sees ONLY codified rows",
                before["audit"]["projected"] > 0
                and before["tenant"]["count"] == before["audit"]["codified"],
                f"API returned {before['tenant']['count']}, "
                f"{before['audit']['codified']} of {before['audit']['projected']} projected are codified",
            )
            if args.stage == "admin":
                return R.report()

            await stage_fix(client, conn, admin_tok)
            if args.stage == "fix":
                return R.report()

            stage(5, "AFTER — re-check and re-measure")
            await stage_check(client, tenant_tok, ids["location_id"], "after")
            after = await stage_measure(client, conn, tenant_tok, admin_tok, ids, "after")

            print(f"\n  {C.B}DELTA{C.X}")
            kv("tenant-visible requirements",
               f"{before['tenant']['count']} → {after['tenant']['count']}")
            kv("codified of projected",
               f"{before['audit']['codified']}/{before['audit']['projected']} → "
               f"{after['audit']['codified']}/{after['audit']['projected']}")
            kv("gated (waiting on us)",
               f"{before['fit']['counts'].get('gated')} → {after['fit']['counts'].get('gated')}")

            R.expect(
                "the tenant STILL sees only codified rows",
                after["tenant"]["count"] == after["audit"]["codified"],
                f"API {after['tenant']['count']} vs codified {after['audit']['codified']}",
            )
            # A margin, not `>`: consecutive checks re-project and the count
            # drifts by one or two on its own, so a bare increase "passes" on
            # noise while the pipeline does nothing. The fix has to clear the
            # noise floor to count.
            R.expect(
                "codification increased materially",
                after["audit"]["codified"] >= before["audit"]["codified"] + 5,
                f"{before['audit']['codified']} → {after['audit']['codified']} "
                f"(need +5 to clear run-to-run drift)",
            )
            R.expect(
                "the gated backlog shrank",
                after["fit"]["counts"].get("gated", 0) < before["fit"]["counts"].get("gated", 0),
                f"{before['fit']['counts'].get('gated')} → {after['fit']['counts'].get('gated')}",
            )
            R.expect(
                "the tenant can now see something",
                after["tenant"]["count"] > 0,
                "a paying customer with zero visible requirements is a broken product",
            )

        if not args.keep:
            await stage_reset(conn)
        else:
            warn(f"--keep: tenant left in place ({ids['company_id']})")
        return R.report()
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

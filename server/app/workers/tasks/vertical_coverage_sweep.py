"""Celery task: drive vertical (industry) compliance coverage to completion.

The vertical-coverage engine (`core/services/vertical_coverage.py`) fills the
shared, tenant-independent catalog for a company's industry — dental law for a
dental office, hospitality law for a hotel — keyed on
(jurisdiction x industry x category) so the first tenant pays for the research
and every later one reads it free.

Until now the ONLY thing that triggered a fill was the Matcha-X onboarding build.
That left three holes, all of which this one task closes:

  1. An existing tenant never filled. If a company onboarded before its vertical
     existed (or its vertical was extended later), nothing ever went back for it.
  2. Deferred calls were never picked up. `plan_fill` caps a single run at
     MAX_CALLS_PER_FILL and reports the overflow, but the overflow only gets
     researched if someone runs another build.
  3. `in_progress` cells wedged forever. `plan_fill` deliberately excludes them so
     a concurrent build can't double-bill a Gemini call — but a fill that died
     mid-flight (pod restart, DB blip) leaves its cells `in_progress` with no
     sweeper, and `plan_fill` will never look at them again.

RATE LIMITING IS LOAD-BEARING. There is no celery-beat: the hourly worker restart
re-fires `@worker_ready`, and this task makes LIVE GEMINI CALLS. Without the
atomic `last_run_at` claim (copied from `scope_registry.run_scheduled_research_cycle`)
a company whose cells keep failing would be re-researched every hour, forever.

The cycle budget is global, not per-company: MAX_CALLS_PER_CYCLE bounds the
Gemini spend of the whole sweep, so one company with a huge chain can't starve
the rest (or the bill).

Scheduler-gated on `scheduler_settings.task_key = 'vertical_coverage_sweep'`,
seeded DISABLED.
"""
import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict, List

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error
from ..utils import get_db_connection, scheduler_enabled

CHANNEL = "vertical_coverage"

# Minimum gap between scheduled sweeps. The worker restarts hourly; this is what
# stops that from becoming an hourly Gemini bill.
MIN_SWEEP_INTERVAL_HOURS = 24

# A fill that hasn't touched its cell in this long is dead, not running. The
# longest legitimate cell is one Gemini research call (45s timeout) plus its
# writes, so hours of slack is generous.
STALE_IN_PROGRESS_HOURS = 2

# Gemini research calls per SWEEP (across all companies), not per company.
MAX_CALLS_PER_CYCLE = 12

# Companies examined per sweep. Probing is cheap (a few SELECTs — plan_fill makes
# no Gemini calls), so this can be generous relative to the call budget.
MAX_COMPANIES_PER_CYCLE = 25


@asynccontextmanager
async def _worker_conn():
    """Connection FACTORY for `vertical_coverage.fill`.

    Workers are deliberately pool-free (see the NOTE in celery_app.py): each task
    runs its own `asyncio.run()` loop, and an asyncpg pool bound to one loop can't
    be reused from another — so `app.database.get_connection` raises here. `fill`
    takes a factory precisely so it can borrow a connection per research call
    rather than pin one across the whole sweep, and this shim satisfies that
    contract with a raw per-call connection.
    """
    conn = await get_db_connection()
    try:
        yield conn
    finally:
        await conn.close()


async def _reclaim_stale_cells(conn) -> int:
    """Un-wedge cells whose fill died mid-flight.

    `failed` is the retry-allowed status by construction; `empty` (researched,
    genuinely nothing there) is the never-retry one. Moving a stale `in_progress`
    to `failed` is what lets `plan_fill` see it again.
    """
    rows = await conn.fetch(
        f"""
        UPDATE jurisdiction_vertical_coverage
        SET status = 'failed',
            error = 'sweeper: reclaimed stale in_progress',
            updated_at = NOW()
        WHERE status = 'in_progress'
          AND updated_at < NOW() - INTERVAL '{STALE_IN_PROGRESS_HOURS} hours'
        RETURNING id
        """
    )
    if rows:
        print(f"[Vertical Sweep] Reclaimed {len(rows)} stale in_progress cell(s)")
    return len(rows)


async def _candidate_companies(conn) -> List[Dict[str, Any]]:
    """Companies that might have vertical work outstanding.

    Deliberately broad: any approved company with an active location that has a
    resolved jurisdiction. Whether there is anything to DO is decided by
    `plan_fill` (which makes no Gemini calls), because the deferred case has no
    ledger row at all — a status-only filter would miss exactly the companies the
    cap deferred.

    Ordered least-recently-swept first (a company that has never triggered a fill
    sorts first, via NULLS FIRST) so the cycle budget rotates fairly instead of
    starving the tail every night. `companies` has no `updated_at`, so the
    recency signal is the ledger's own — the last time this company requested a
    cell — which is the more honest measure anyway.
    """
    rows = await conn.fetch(
        """
        SELECT c.id, c.name,
               (SELECT MAX(v.updated_at) FROM jurisdiction_vertical_coverage v
                 WHERE v.requested_by_company_id = c.id) AS last_swept
        FROM companies c
        WHERE (c.status IS NULL OR c.status = 'approved')
          AND EXISTS (
              SELECT 1 FROM business_locations bl
              WHERE bl.company_id = c.id
                AND bl.is_active = true
                AND bl.jurisdiction_id IS NOT NULL
          )
        ORDER BY last_swept ASC NULLS FIRST, c.created_at ASC
        LIMIT $1
        """,
        MAX_COMPANIES_PER_CYCLE,
    )
    return [dict(r) for r in rows]


async def _sweep_company(company_id, budget: int) -> Dict[str, Any]:
    """Fill one company's outstanding vertical cells, up to `budget` Gemini calls.

    Mirrors step 3c of the Matcha-X onboarding build
    (`matcha/routes/matcha_x_onboarding.py`) — the same sequence, same guards.
    """
    from app.core.services import vertical_coverage

    conn = await get_db_connection()
    try:
        resolved = await vertical_coverage.resolve_vertical(conn, company_id)
        if not resolved:
            return {"skipped": "no vertical"}
        parent, slug, label, tag, minted = resolved

        categories, context = await vertical_coverage.ensure_specialty(
            conn, parent, slug, label
        )
        if not categories:
            return {"skipped": "no categories", "vertical": label}

        leaf_rows = await conn.fetch(
            """
            SELECT DISTINCT jurisdiction_id FROM business_locations
            WHERE company_id = $1 AND is_active = true AND jurisdiction_id IS NOT NULL
            """,
            company_id,
        )
        leaves = [r["jurisdiction_id"] for r in leaf_rows]
        chains = await vertical_coverage.chains_for_leaves(conn, leaves)
        all_nodes = sorted({jid for chain in chains.values() for jid, _ in chain})

        await vertical_coverage.backfill_ledger(conn, all_nodes, tag, categories)
        plan, deferred = await vertical_coverage.plan_fill(conn, chains, tag, categories)
    finally:
        await conn.close()

    # Trim to the cycle's remaining budget. What we drop keeps no ledger verdict,
    # so the next sweep picks it up — the same contract plan_fill's own cap has.
    if len(plan) > budget:
        deferred += len(plan) - budget
        plan = plan[:budget]

    if not plan and not minted:
        return {"skipped": "covered", "vertical": label, "deferred": deferred}

    new = deduped = 0
    async for ev in vertical_coverage.fill(
        _worker_conn, company_id, plan, tag, context
    ):
        new += ev.get("new", 0)
        deduped += ev.get("deduped", 0)

    # Reproject when the catalog changed under the tenant, and ALWAYS when the
    # specialty tag was just minted: every projection made before that write
    # filtered this vertical's rows out (the industry filter reads the company's
    # own tag set), so a fully-covered ledger still leaves the tab empty.
    if new or deduped or minted:
        conn = await get_db_connection()
        try:
            locs = await conn.fetch(
                "SELECT id FROM business_locations "
                "WHERE company_id = $1 AND is_active = true",
                company_id,
            )
            for row in locs:
                await vertical_coverage.reproject_location(conn, company_id, row["id"])
        finally:
            await conn.close()

    return {
        "vertical": label,
        "calls": len(plan),
        "new": new,
        "deduped": deduped,
        "deferred": deferred,
        "minted": minted,
    }


async def _notify(company_id, result: Dict[str, Any]) -> None:
    """Tell the company's admin their compliance picked up new obligations.

    Only on a real gain. A sweep that researched and found nothing is correct and
    uninteresting; emailing about it would train people to ignore these.

    Not `_notify_company_admins_of_compliance_changes` — that resolves its
    recipients through the app POOL, which does not exist in a worker.
    """
    from app.core.services.email import EmailService

    conn = await get_db_connection()
    try:
        company = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", company_id)
        admin = await conn.fetchrow(
            """
            SELECT u.email, cl.name AS name
            FROM users u JOIN clients cl ON cl.user_id = u.id
            WHERE u.role = 'client' AND cl.company_id = $1
            ORDER BY u.created_at ASC LIMIT 1
            """,
            company_id,
        )
    finally:
        await conn.close()

    if not admin or not admin["email"]:
        return

    vertical = result.get("vertical") or "industry"
    count = result.get("new", 0)
    company_name = (company["name"] if company else None) or "your company"
    subject = f"{count} new {vertical} compliance requirement(s) for {company_name}"
    html = (
        f"<p>We finished researching <b>{vertical}</b>-specific compliance for "
        f"<b>{company_name}</b> and added <b>{count}</b> requirement(s) that apply "
        f"to your locations.</p>"
        f"<p>They're on your Compliance tab now.</p>"
    )
    try:
        await EmailService().send_email(
            to_email=admin["email"], to_name=admin["name"],
            subject=subject, html_content=html,
        )
    except Exception as exc:
        print(f"[Vertical Sweep] Email failed for company {company_id}: {exc}")


async def _dispatch(force: bool = False) -> Dict[str, Any]:
    """`force=True` is the admin's manual Trigger: run even when the scheduler row
    is disabled, and ignore the interval claim. Both guards exist to stop the
    HOURLY WORKER RESTART from re-billing Gemini — neither should stand in the way
    of a human who deliberately pressed the button (and without this the task would
    be untestable until someone enabled the row in prod)."""
    conn = await get_db_connection()
    try:
        if not force:
            if not await scheduler_enabled(conn, "vertical_coverage_sweep", default=False):
                print("[Vertical Sweep] Scheduler disabled, skipping.")
                return {"status": "disabled"}

            # Claim the cycle atomically. Stamped BEFORE the work and regardless of
            # what it produces — a fruitless sweep burns Gemini exactly like a
            # productive one, so it must count against the interval too.
            claimed = await conn.fetchval(
                """
                UPDATE scheduler_settings SET last_run_at = NOW()
                WHERE task_key = 'vertical_coverage_sweep'
                  AND (last_run_at IS NULL
                       OR last_run_at < NOW() - ($1 || ' hours')::interval)
                RETURNING TRUE
                """,
                str(MIN_SWEEP_INTERVAL_HOURS),
            )
            if not claimed:
                return {"status": "skipped", "reason": "a sweep ran recently"}
        else:
            await conn.execute(
                "UPDATE scheduler_settings SET last_run_at = NOW() "
                "WHERE task_key = 'vertical_coverage_sweep'"
            )

        reclaimed = await _reclaim_stale_cells(conn)
        candidates = await _candidate_companies(conn)
    finally:
        await conn.close()

    budget = MAX_CALLS_PER_CYCLE
    swept: List[Dict[str, Any]] = []

    for company in candidates:
        if budget <= 0:
            break
        try:
            result = await _sweep_company(company["id"], budget)
        except Exception as exc:
            # One company's failure must not abort the sweep.
            print(f"[Vertical Sweep] {company['name']}: {exc}")
            swept.append({"company": company["name"], "error": str(exc)})
            continue

        budget -= result.get("calls", 0)
        if result.get("new", 0) > 0:
            await _notify(company["id"], result)
        if not result.get("skipped"):
            swept.append({"company": company["name"], **result})

    return {
        "status": "ok",
        "reclaimed": reclaimed,
        "companies_examined": len(candidates),
        "companies_filled": len(swept),
        "calls_used": MAX_CALLS_PER_CYCLE - budget,
        "results": swept,
    }


@celery_app.task(name="vertical_coverage.run_sweep", bind=True, max_retries=0)
def run_vertical_coverage_sweep(self, force: bool = False):
    """Reclaim wedged cells, then fill outstanding vertical coverage."""
    try:
        result = asyncio.run(_dispatch(force=force))
    except Exception as exc:
        publish_task_error(CHANNEL, "vertical_coverage_sweep", "scheduled", str(exc))
        print(f"[Vertical Sweep] Task failed: {exc}")
        raise

    print(f"[Vertical Sweep] Completed: {result}")
    publish_task_complete(CHANNEL, "vertical_coverage_sweep", "scheduled", result)
    return result

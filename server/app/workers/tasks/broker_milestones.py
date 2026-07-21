"""Celery task: broker positive-milestone detection.

Periodic (re-dispatched on every worker startup ~15 min, gated by the
`broker_milestones` row in scheduler_settings). For each active broker→client
link it recomputes the client's trailing-12mo WC metrics and records any
positive safety milestone reached — incident-free streak tiers, a DART-free
year, or TRIR dropping below sector benchmark — into the `broker_milestones`
state table for the broker Action Center's Milestones tab.

Unlike `broker_risk_alerts` there is no email digest: milestones are pull, shown
in-app. The detection rules + the de-dup decision are pure functions
(`evaluate_milestones`, `decide_milestone_action`) so they can be unit-tested
without a DB or worker.

Supersede semantics (differs from the risk worker's resolve loop): a milestone
is a point-in-time achievement, so once recorded it stays until a higher tier of
the same family fires or the underlying streak breaks — both set
`superseded_at`. A milestone that fires again after being superseded re-arms.
"""

import asyncio
from datetime import datetime
from typing import Optional

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row
from .broker_risk_alerts import should_suppress

# ── Tunables (code constants) ────────────────────────────────────────────────
INCIDENT_FREE_TIERS = (90, 180, 365)  # days-since-last-recordable thresholds


# ── Pure detection ───────────────────────────────────────────────────────────
def evaluate_milestones(metrics: dict) -> list[dict]:
    """Return positive milestone candidates for one company's compute_wc_metrics
    dict. Each candidate: {milestone_key, milestone_family, tier, title, detail,
    current_value, benchmark_value}. Empty list = nothing achieved.

    Count/streak-based milestones (incident-free, DART-free year) fire
    regardless of population size. The rate-based milestone
    (TRIR-below-benchmark) is suppressed on thin data, mirroring the risk
    worker's rate/count split.
    """
    out: list[dict] = []
    rates_unreliable = should_suppress(metrics)
    prior = metrics.get("prior") or {}

    # Incident-free streak — fire only the highest tier the streak qualifies for.
    days = metrics.get("days_since_last_recordable")
    if metrics.get("ever_recordable") and days is not None:
        tier = next((t for t in reversed(INCIDENT_FREE_TIERS) if days >= t), None)
        if tier is not None:
            out.append({
                "milestone_key": f"incident_free_{tier}",
                "milestone_family": "incident_free",
                "tier": tier,
                "title": f"{tier} days incident-free",
                "detail": f"{days} days since the last recordable incident",
                "current_value": float(days),
                "benchmark_value": None,
            })

    # DART-free year — zero lost-time cases in the trailing 12 months after a
    # prior year that had them (a genuine improvement, not a never-recordable
    # account). Count-based → not suppressed.
    dart = metrics.get("dart_cases")
    prior_dart = prior.get("dart_cases")
    if (
        metrics.get("ever_recordable")
        and dart == 0
        and prior_dart is not None and prior_dart > 0
    ):
        out.append({
            "milestone_key": "dart_free_year",
            "milestone_family": "dart_free",
            "tier": None,
            "title": "DART-free year",
            "detail": f"No lost-time (DART) cases in the last 12 months — down from {prior_dart}.",
            "current_value": 0.0,
            "benchmark_value": None,
        })

    # TRIR below sector benchmark AND improving (prior-year delta negative).
    # Rate-based → suppressed on thin population.
    trir = metrics.get("trir")
    benchmark = metrics.get("benchmark") or {}
    bench_trir = benchmark.get("trir")
    trir_delta = prior.get("trir_delta_pct")
    if (
        not rates_unreliable
        and trir is not None and bench_trir is not None
        and trir < bench_trir
        and trir_delta is not None and trir_delta < 0
    ):
        out.append({
            "milestone_key": "trir_below_benchmark",
            "milestone_family": "trir_below_benchmark",
            "tier": None,
            "title": "TRIR below benchmark",
            "detail": f"TRIR {trir} is under the {benchmark.get('label') or 'sector'} median of {bench_trir} and trending down.",
            "current_value": float(trir),
            "benchmark_value": float(bench_trir),
        })

    return out


def decide_milestone_action(existing: Optional[dict], candidate: dict) -> str:
    """'insert' (never recorded) | 'rearm' (was superseded, achieved again) |
    'skip' (already live — just bump last_evaluated)."""
    if existing is None:
        return "insert"
    if existing.get("superseded_at") is not None:
        return "rearm"
    return "skip"


# ── Async runner ─────────────────────────────────────────────────────────────
async def _run_broker_milestones() -> dict:
    from app.matcha.routes.ir_incidents import compute_wc_metrics
    from app.matcha.dependencies import BROKER_ACTIVE_LINK_STATUSES

    conn = await get_db_connection()
    try:
        sched = await scheduler_settings_row(conn, "broker_milestones")
        if not sched:
            return {"skipped": True, "reason": "scheduler_not_registered"}
        if not sched["enabled"]:
            print("[Broker Milestones] Scheduler disabled, skipping.")
            return {"skipped": True, "reason": "scheduler_disabled"}

        links = await conn.fetch(
            """
            SELECT l.broker_id, l.company_id
            FROM broker_company_links l
            JOIN companies c ON c.id = l.company_id
            JOIN brokers b ON b.id = l.broker_id
            WHERE l.status = ANY($1::text[])
              AND b.status = 'active'
              AND COALESCE(c.status, 'approved') NOT IN ('pending', 'rejected')
            ORDER BY l.broker_id
            """,
            list(BROKER_ACTIVE_LINK_STATUSES),
        )
        if not links:
            return {"evaluated": 0, "candidates": 0, "inserted": 0, "superseded": 0}

        metrics_cache: dict = {}  # company_id -> metrics dict (or None)
        n_candidates = 0
        n_inserted = 0
        n_superseded = 0

        for link in links:
            broker_id = link["broker_id"]
            company_id = link["company_id"]

            if company_id not in metrics_cache:
                try:
                    metrics_cache[company_id] = await compute_wc_metrics(conn, company_id)
                except Exception as exc:
                    print(f"[Broker Milestones] metrics failed for company {company_id}: {exc}")
                    metrics_cache[company_id] = None
            metrics = metrics_cache[company_id]
            if not metrics:
                continue

            existing_rows = await conn.fetch(
                "SELECT * FROM broker_milestones WHERE broker_id = $1 AND company_id = $2",
                broker_id, company_id,
            )
            existing_by_key = {r["milestone_key"]: dict(r) for r in existing_rows}

            candidates = evaluate_milestones(metrics)
            fired_keys = {c["milestone_key"] for c in candidates}

            # Supersede any live row whose milestone no longer fires (higher tier
            # took over, or the streak broke).
            for key, row in existing_by_key.items():
                if key not in fired_keys and row.get("superseded_at") is None:
                    await conn.execute(
                        "UPDATE broker_milestones SET superseded_at = NOW(), last_evaluated_at = NOW() WHERE id = $1",
                        row["id"],
                    )
                    n_superseded += 1

            for cand in candidates:
                n_candidates += 1
                existing = existing_by_key.get(cand["milestone_key"])
                action = decide_milestone_action(existing, cand)

                cur = float(cand["current_value"]) if cand["current_value"] is not None else None
                bench = float(cand["benchmark_value"]) if cand["benchmark_value"] is not None else None

                if action == "skip":
                    await conn.execute(
                        "UPDATE broker_milestones SET last_evaluated_at = NOW() WHERE id = $1",
                        existing["id"],
                    )
                    continue

                if action == "rearm":
                    await conn.execute(
                        """
                        UPDATE broker_milestones SET
                            milestone_family = $2, tier = $3, title = $4, detail = $5,
                            current_value = $6, benchmark_value = $7,
                            achieved_at = NOW(), last_evaluated_at = NOW(),
                            superseded_at = NULL, is_read = false
                        WHERE id = $1
                        """,
                        existing["id"], cand["milestone_family"], cand["tier"],
                        cand["title"], cand["detail"], cur, bench,
                    )
                else:  # insert
                    await conn.execute(
                        """
                        INSERT INTO broker_milestones
                            (broker_id, company_id, milestone_key, milestone_family, tier,
                             title, detail, current_value, benchmark_value,
                             achieved_at, last_evaluated_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9, NOW(), NOW())
                        ON CONFLICT (broker_id, company_id, milestone_key) DO UPDATE SET
                            milestone_family = EXCLUDED.milestone_family,
                            tier = EXCLUDED.tier, title = EXCLUDED.title, detail = EXCLUDED.detail,
                            current_value = EXCLUDED.current_value,
                            benchmark_value = EXCLUDED.benchmark_value,
                            last_evaluated_at = NOW()
                        """,
                        broker_id, company_id, cand["milestone_key"], cand["milestone_family"],
                        cand["tier"], cand["title"], cand["detail"], cur, bench,
                    )
                n_inserted += 1

        return {"evaluated": len(metrics_cache), "candidates": n_candidates,
                "inserted": n_inserted, "superseded": n_superseded}

    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_broker_milestones(self) -> dict:
    """Scan broker portfolios and record positive client safety milestones."""
    print("[Broker Milestones] Running...")
    try:
        result = asyncio.run(_run_broker_milestones())
        print(f"[Broker Milestones] Completed: {result}")
        return {"status": "success", **result}
    except Exception as exc:
        print(f"[Broker Milestones] Failed: {exc}")
        raise self.retry(exc=exc, countdown=60)

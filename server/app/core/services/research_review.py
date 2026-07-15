"""Shared codify core for staged research rows.

`approve_staged` is the catalog-facing half of the admin research-review approve
(routes/admin.py:approve_research_review) — activate the `pending` rows, then
statute-link the newly-active ones via `reconcile_codifications`, and return the
per-row codified outcome. It is deliberately WITHOUT the tenant publish loop and
the source-snapshot background task: those are caller-specific (the admin queue
publishes to waiting tenants; the Compliance Pilot builds the shared library with
no waiting tenant, so it publishes nothing). Both callers share the activate +
reconcile + results core through this one function.

`reconcile_codifications` is the single writer of `scope_codifications` +
`statute_citation`/`citation_verified_at`, so approving through here lights up the
same "authoritative" KPIs regardless of caller. Best-effort on the reconcile pass:
the rows are already active, so a codify error must never fail the approval.
"""
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.database import get_connection
from .change_context import set_change_context

logger = logging.getLogger(__name__)


async def approve_staged(
    ids: List[UUID],
    actor_id: Optional[UUID] = None,
    *,
    source: str = "approve",
) -> Dict[str, Any]:
    """Activate staged `pending` rows and codify them.

    Returns ``{activated, codified, uncodified, results, snap_targets}`` where
    ``results`` is the per-row codified outcome (the shape the Review UI renders)
    and ``snap_targets`` is ``[(requirement_id, best_url)]`` the caller MAY hand to
    its own snapshot background task (the admin route does; the pilot ignores it).

    Concurrency-safe: activation is ``WHERE status='pending'`` so a row already
    approved elsewhere (e.g. the Pipeline tab) is simply skipped — ``activated``
    can legitimately be less than ``len(ids)``.
    """
    from .scope_registry.codify import reconcile_codifications

    if not ids:
        return {"activated": 0, "codified": 0, "uncodified": 0, "results": [], "snap_targets": []}

    async with get_connection() as conn:
        # Label the activation for the version trigger (jrver01). 'approve' for the
        # admin queue; 'pilot_commit' for the Compliance Pilot.
        await set_change_context(conn, source, actor_id)
        activated = await conn.fetch(
            "UPDATE jurisdiction_requirements SET status='active', last_verified_at=NOW(), "
            "updated_at=NOW() WHERE id = ANY($1::uuid[]) AND status='pending' "
            "RETURNING id, jurisdiction_id",
            ids,
        )

    if not activated:
        return {"activated": 0, "codified": 0, "uncodified": 0, "results": [], "snap_targets": []}

    activated_ids = [r["id"] for r in activated]
    jurisdiction_ids = list({r["jurisdiction_id"] for r in activated})

    async with get_connection() as conn:
        targets = await conn.fetch(
            "SELECT DISTINCT UPPER(state) AS state, LOWER(city) AS city "
            "FROM jurisdictions WHERE id = ANY($1::uuid[]) AND state IS NOT NULL",
            jurisdiction_ids,
        )
    # One reconcile per distinct (state, city) — the chain resolver only reaches
    # city/county nodes when a city is passed, and routed research files
    # city-stamped rows on city nodes. Idempotent + deterministic, so overlapping
    # chains are repeated no-ops on the shared federal/state nodes.
    pairs = sorted({(t["state"], t["city"]) for t in targets if t["state"]},
                   key=lambda p: (p[0], p[1] or ""))
    for st, city in pairs:
        try:
            async with get_connection() as conn:
                await reconcile_codifications(conn, state=st, city=city, source=source)
        except Exception as exc:  # noqa: BLE001 — rows are already active; never fail approve
            logger.warning("approve_staged: codify failed for %s/%s: %s", st, city, exc)

    async with get_connection() as conn:
        detail = await conn.fetch(
            """
            SELECT r.id, r.title, r.description, r.current_value,
                   r.source_url, r.source_name, r.regulation_key,
                   r.statute_citation, r.citation_verified_at, r.citation_item_id,
                   ai.source_url AS citation_url,
                   UPPER(j.state) AS state, LOWER(j.city) AS city
            FROM jurisdiction_requirements r
            JOIN jurisdictions j ON j.id = r.jurisdiction_id
            LEFT JOIN authority_index_items ai ON ai.id = r.citation_item_id
            WHERE r.id = ANY($1::uuid[])
            """,
            activated_ids,
        )
    results = [{
        "id": str(d["id"]),
        "title": d["title"],
        "description": d["description"],
        "current_value": d["current_value"],
        "source_url": d["source_url"],
        "source_name": d["source_name"],
        "regulation_key": d["regulation_key"],
        "codified": d["citation_verified_at"] is not None,
        "statute_citation": d["statute_citation"],
        "citation_url": d["citation_url"],
        "citation_item_id": str(d["citation_item_id"]) if d["citation_item_id"] else None,
        "state": d["state"],
        "city": d["city"],
    } for d in detail]
    codified = sum(1 for r in results if r["codified"])
    snap_targets = [(d["id"], d["citation_url"] or d["source_url"])
                    for d in detail if (d["citation_url"] or d["source_url"])]

    return {
        "activated": len(activated),
        "codified": codified,
        "uncodified": max(len(activated) - codified, 0),
        "results": results,
        "snap_targets": snap_targets,
    }

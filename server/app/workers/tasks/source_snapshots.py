"""Backfill frozen source-page snapshots for catalog requirements.

`snapshot_source` has existed since `jrver01`, but only two write paths call it
(approve, codify), and nothing ever backfilled what predated them — so the
evidence table sat at 5 rows against 1781 requirements, and 27 of the 29
*codified* rows had no frozen page at all. "Codified" is the product's
without-a-doubt claim; a citation string plus a link that may 404 next year does
not support it. This task freezes the pages we already claim to have read.

Routed to Celery (not BackgroundTasks) for the same reason as
`scope_registry.fetch_authority_bodies`: it fetches from live regulator hosts,
serially and politely, and a slow .gov must not pin a uvicorn worker.

Idempotent by construction — `requirement_source_snapshots` has a partial unique
on (requirement_id, content_hash), so re-running stores nothing for a page whose
text hasn't changed. A failed fetch records its http_status and inserts anyway,
so misses stay auditable rather than looking like "never tried".

Admin-triggered only; no scheduler row. Re-freezing on a cadence is drift
detection, which is a different task with a different question to answer.
"""
import asyncio
from typing import Optional

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error

CHANNEL = "admin:scope_registry"

# Politeness delay between fetches. Mirrors body_fetch._fetch_html_index.
_SLEEP_SECONDS = 0.3

# Rows worth freezing, narrowest first. Each selects requirements that have a
# usable source_url and no snapshot yet.
#   codified — the asset. The trio (statute_citation + citation_verified_at +
#              citation_item_id) is the same predicate scope_registry.codify
#              .codified_sql() defines; kept in SQL here because this runs on a
#              raw worker connection with no service imports.
#   tier1    — active rows sourced from a primary government authority.
#   all      — every active row with a URL, aggregators included.
_SCOPES = {
    "codified": """
        jr.statute_citation IS NOT NULL
        AND jr.citation_verified_at IS NOT NULL
        AND jr.citation_item_id IS NOT NULL
    """,
    "tier1": """
        jr.status = 'active' AND jr.source_tier = 'tier_1_government'
    """,
    "all": """
        jr.status = 'active'
    """,
}


@celery_app.task(name="compliance.backfill_source_snapshots", max_retries=0, time_limit=3600)
def backfill_source_snapshots(
    scope: str = "codified",
    limit: Optional[int] = None,
    triggered_by: Optional[str] = None,
):
    """Freeze the cited source page for every requirement in `scope` that lacks one.

    scope: 'codified' (default) | 'tier1' | 'all'. `limit` caps one run so a
    first pass over a wide scope can be sampled before committing to the whole
    sweep. Returns per-outcome counts from snapshot_source.
    """
    if scope not in _SCOPES:
        raise ValueError(f"unknown scope {scope!r}; expected one of {sorted(_SCOPES)}")

    from app.workers.utils import get_db_connection

    async def _run():
        import httpx
        from app.core.services.source_snapshot import snapshot_source

        conn = await get_db_connection()
        try:
            rows = await conn.fetch(
                f"""
                SELECT jr.id, jr.source_url
                FROM jurisdiction_requirements jr
                WHERE {_SCOPES[scope]}
                  AND jr.source_url IS NOT NULL
                  AND jr.source_url <> ''
                  -- A row is "done" only once a fetch actually captured text.
                  -- snapshot_source INSERTs on failure too (http_status, no
                  -- text) so misses stay auditable — but keying the candidate
                  -- filter on mere existence would make that miss permanent:
                  -- the 2 codified rows whose citation URL 404s today would be
                  -- skipped by every future run, including the one after an
                  -- admin fixes the dead URL. Cost of retrying: a handful of
                  -- known-dead URLs re-fetched per run. Right trade for
                  -- evidence capture.
                  AND NOT EXISTS (
                      SELECT 1 FROM requirement_source_snapshots s
                      WHERE s.requirement_id = jr.id
                        AND s.content_text IS NOT NULL
                  )
                ORDER BY jr.id
                {"LIMIT " + str(int(limit)) if limit else ""}
                """
            )
            counts = {"stored": 0, "duplicate": 0, "skipped": 0, "failed": 0}
            if not rows:
                return {"scope": scope, "candidates": 0, **counts}

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0),
                follow_redirects=True,
                headers={"User-Agent": "MatchaComplianceBot/1.0 (+compliance evidence capture)"},
            ) as client:
                for r in rows:
                    outcome = await snapshot_source(
                        conn, r["id"], r["source_url"], "verify", client=client
                    )
                    counts[outcome] = counts.get(outcome, 0) + 1
                    await asyncio.sleep(_SLEEP_SECONDS)
            return {"scope": scope, "candidates": len(rows), **counts}
        finally:
            await conn.close()

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        publish_task_error(CHANNEL, "source_snapshots", scope, str(exc))
        raise

    publish_task_complete(CHANNEL, "source_snapshots", scope, result)
    return result

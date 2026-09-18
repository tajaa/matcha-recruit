"""Celery task: reconcile Cappe custom domains with their CloudFront tenants.

Two jobs, both idempotent and both status-guarded so a re-run is free:

1. **Go live.** A domain attached to the edge sits at `edge_status='pending_dns'`
   until the tenant points DNS at the routing endpoint and CloudFront finishes
   issuing the managed certificate. When `tenant_status` reports `live`, THIS is
   what finally writes `cappe_sites.custom_domain` — the renderer only starts
   answering for a domain whose TLS actually exists.

2. **Tear down.** A domain whose registration has ended (`expired`) keeps
   billing us an edge tenant and keeps answering on our certificate. Those get
   the tenant deleted and `custom_domain` cleared. A *requested* transfer is
   NOT torn down: transfers take days and may never complete, so the site keeps
   serving until the renewals task lapses the row to `expired`.

3. **Adopt.** An `active` domain sitting at `edge_status='none'` with no tenant
   — its provisioning background task died, or it was activated before the
   edge existed — is provisioned here, so it is never a silent dead end.

Every row is isolated: one domain raising must not abort the sweep. Rows are
ordered `edge_checked_at NULLS FIRST`, so a row that raised without having its
timestamp bumped would sort first again forever and starve every other domain.

Gated on `scheduler_settings.task_key = 'cappe_edge_sync'` (default off).
Pool-free: opens its own asyncpg connection like every other worker task.
"""

import asyncio
import logging

import asyncpg

from app.cappe.services.cloudfront_tenants import (
    CappeEdgeError,
    CappeEdgeNotFound,
    get_cloudfront_tenants,
)
from app.cappe.services.domain_register import retry_domain_edge
from app.cappe.services.render_cache import invalidate_site_render_cache
from app.config import get_settings

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row

logger = logging.getLogger(__name__)

_DEFAULT_CAP = 50


async def _go_live(conn, row, edge) -> str:
    """Poll one provisioning/pending row and record what the edge reports."""
    try:
        edge_status, detail = await edge.tenant_status(row["cf_tenant_id"])
    except CappeEdgeNotFound:
        # The tenant was deleted out from under us (manual console cleanup).
        # Clear the pointer so a retry can recreate it rather than polling a
        # tenant id that will never answer again.
        await conn.execute(
            "UPDATE cappe_domains SET edge_status = 'failed', "
            "edge_error = 'CloudFront tenant no longer exists', cf_tenant_id = NULL, "
            "edge_checked_at = NOW(), updated_at = NOW() WHERE id = $1",
            row["id"],
        )
        return "failed"
    except CappeEdgeError as exc:
        # Transient AWS failure: touch the timestamp, leave the status alone so
        # the next cycle retries.
        logger.warning("cappe edge status check failed for %s: %s", row["domain"], exc)
        await conn.execute(
            "UPDATE cappe_domains SET edge_checked_at = NOW() WHERE id = $1", row["id"]
        )
        return "error"

    if edge_status == "live":
        try:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE cappe_domains SET edge_status = 'live', edge_error = NULL, "
                    "edge_checked_at = NOW(), updated_at = NOW() "
                    "WHERE id = $1 AND edge_status <> 'live'",
                    row["id"],
                )
                await conn.execute(
                    "UPDATE cappe_sites SET custom_domain = $1, updated_at = NOW() "
                    "WHERE id = $2 AND custom_domain IS DISTINCT FROM $1",
                    row["domain"], row["site_id"],
                )
        except asyncpg.UniqueViolationError:
            # cappe_sites.custom_domain is UNIQUE: another site already answers
            # for this host (a legacy row set by hand, or a second claim). That
            # is a permanent condition, not a blip — record it and stop polling.
            await conn.execute(
                "UPDATE cappe_domains SET edge_status = 'failed', "
                "edge_error = 'Another site is already published on this domain', "
                "edge_checked_at = NOW(), updated_at = NOW() WHERE id = $1",
                row["id"],
            )
            logger.error("cappe domain %s cannot go live: custom_domain already in use", row["domain"])
            return "failed"
        await invalidate_site_render_cache(row["site_id"])
        logger.info("cappe domain %s is live at the edge", row["domain"])
        return "live"

    if edge_status == "failed":
        await conn.execute(
            "UPDATE cappe_domains SET edge_status = 'failed', edge_error = $2, "
            "edge_checked_at = NOW(), updated_at = NOW() WHERE id = $1",
            row["id"], (detail or "edge provisioning failed")[:500],
        )
        logger.warning("cappe domain %s edge failed: %s", row["domain"], detail)
        return "failed"

    await conn.execute(
        "UPDATE cappe_domains SET edge_status = $2, edge_error = $3, edge_checked_at = NOW() "
        "WHERE id = $1",
        row["id"], edge_status, (detail or None),
    )
    return edge_status


async def _tear_down(conn, row, edge) -> bool:
    """Detach a domain that is no longer ours to serve."""
    try:
        await edge.delete_tenant(row["cf_tenant_id"])
    except CappeEdgeError as exc:
        logger.warning("cappe edge teardown failed for %s: %s", row["domain"], exc)
        await conn.execute(
            "UPDATE cappe_domains SET edge_checked_at = NOW() WHERE id = $1", row["id"]
        )
        return False
    async with conn.transaction():
        await conn.execute(
            "UPDATE cappe_domains SET cf_tenant_id = NULL, edge_status = 'none', "
            "edge_error = NULL, edge_checked_at = NOW(), updated_at = NOW() WHERE id = $1",
            row["id"],
        )
        await conn.execute(
            "UPDATE cappe_sites SET custom_domain = NULL, updated_at = NOW() "
            "WHERE id = $1 AND custom_domain = $2",
            row["site_id"], row["domain"],
        )
    await invalidate_site_render_cache(row["site_id"])
    logger.info("cappe domain %s detached from the edge", row["domain"])
    return True


async def _isolated(conn, row, label: str, coro) -> object:
    """Run one row's work; on ANY exception bump its timestamp and move on."""
    try:
        return await coro
    except Exception:
        logger.exception("cappe edge sync: %s failed for %s", label, row["domain"])
        try:
            await conn.execute(
                "UPDATE cappe_domains SET edge_checked_at = NOW() WHERE id = $1", row["id"]
            )
        except Exception:
            logger.exception("cappe edge sync: could not bump %s", row["domain"])
        return None


async def _run() -> dict:
    conn = await get_db_connection()
    try:
        setting = await scheduler_settings_row(conn, "cappe_edge_sync")
        if not setting or not setting["enabled"]:
            return {"skipped": True}
        cap = setting["max_per_cycle"] or _DEFAULT_CAP
        edge = get_cloudfront_tenants()

        pending = await conn.fetch(
            """SELECT id, site_id, domain, cf_tenant_id
                 FROM cappe_domains
                WHERE edge_status IN ('provisioning', 'pending_dns')
                  AND cf_tenant_id IS NOT NULL
             ORDER BY edge_checked_at NULLS FIRST
                LIMIT $1""",
            cap,
        )
        counts: dict[str, int] = {}
        for row in pending:
            outcome = await _isolated(conn, row, "status check", _go_live(conn, row, edge)) or "error"
            counts[outcome] = counts.get(outcome, 0) + 1

        # Adopt active domains nobody ever provisioned. Only while the feature is
        # on: with it off there is no tenant distribution to attach them to.
        adopted = 0
        if get_settings().cappe_custom_domains_enabled:
            orphans = await conn.fetch(
                """SELECT id, site_id, domain
                     FROM cappe_domains
                    WHERE status = 'active' AND edge_status = 'none' AND cf_tenant_id IS NULL
                 ORDER BY edge_checked_at NULLS FIRST
                    LIMIT $1""",
                cap,
            )
            for row in orphans:
                if await _isolated(conn, row, "adoption", retry_domain_edge(row["id"])) is not None:
                    adopted += 1

        stale = await conn.fetch(
            """SELECT id, site_id, domain, cf_tenant_id
                 FROM cappe_domains
                WHERE status = 'expired'
                  AND cf_tenant_id IS NOT NULL
             ORDER BY edge_checked_at NULLS FIRST
                LIMIT $1""",
            cap,
        )
        detached = 0
        for row in stale:
            if await _isolated(conn, row, "teardown", _tear_down(conn, row, edge)):
                detached += 1

        return {"checked": len(pending), "adopted": adopted, "detached": detached, **counts}
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_cappe_edge_sync(self) -> dict:
    try:
        return {"status": "success", **asyncio.run(_run())}
    except Exception as exc:
        logger.exception("Cappe edge sync failed")
        raise self.retry(exc=exc, countdown=120)

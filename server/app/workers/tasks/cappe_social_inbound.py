"""Celery task: store the comments and messages a Meta webhook delivered,
then run the owner's reply policy on each new one.

On-demand (dispatched via .delay() from the public webhook route, NOT
scheduled). The route has already verified the signature and parsed the
payload into `InboundEvent` dicts; this task finds the connections each one
belongs to (live, inbox on), drops what the accounts sent themselves (our own
replies come back as comments), inserts what is new (re-deliveries drop on the
unique key), and hands each new row to `autoreply.handle_item`, which decides
between sending, drafting for approval, escalating, or leaving it — per the
site's settings.

`run_cappe_social_inbox_sweep` (hourly, `cappe_social_inbox_sweep` scheduler
row) runs the policy again on what it left: the model unavailable or at its
cap, a draft that failed, a task that died after storing.
"""
import asyncio
import logging
from typing import Any

from app.cappe.services.entitlements import resolve_entitlements
from app.cappe.services.social import autoreply, outbound
from app.cappe.services.social import connections as conn_store
from app.cappe.services.social import inbox as inbox_store
from app.cappe.services.social.providers.base import InboundEvent
from app.cappe.services.social.providers.meta import MetaConfig

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row

logger = logging.getLogger(__name__)

SWEEP_KEY = "cappe_social_inbox_sweep"
# A DM can be answered only within 24 hours of the customer's message; a
# reply half a day late is still worth sending, later isn't.
SWEEP_WINDOW_HOURS = 12


def _sender(conn, cfg: MetaConfig):
    async def send(item: dict[str, Any], body: str) -> str:
        return await outbound.send_reply(conn, cfg, item, body)

    return send


async def effective_settings(conn, site_id) -> dict[str, Any]:
    """The site's reply settings, with the mode forced `off` when the owner's
    plan no longer includes `social_autoreply` (a downgrade keeps the stored
    mode; the plan, not the row, decides whether the model runs)."""
    settings = await inbox_store.get_settings(conn, site_id)
    if settings.get("autoreply_mode") == "off":
        return settings
    plan = await conn.fetchval(
        "SELECT a.plan FROM cappe_sites s JOIN cappe_accounts a ON a.id = s.account_id "
        "WHERE s.id = $1 AND a.status = 'active'",
        site_id,
    )
    ent = await resolve_entitlements(plan, conn=conn) if plan else None
    if ent is None or not ent.has("social_autoreply"):
        return {**settings, "autoreply_mode": "off"}
    return settings


async def process_events(conn, cfg: MetaConfig, events: list[InboundEvent]) -> dict[str, Any]:
    """Store and handle. Returns counts by outcome."""
    outcomes: dict[str, int] = {"stored": 0, "unmatched": 0, "own": 0}
    by_recipient: dict[tuple[str, str], list[InboundEvent]] = {}
    for event in events:
        by_recipient.setdefault((event.platform, event.recipient_external_id), []).append(event)
    _send = _sender(conn, cfg)

    for (platform, external_id), group in by_recipient.items():
        connections = await conn_store.by_external_id(conn, platform, external_id)
        if not connections:
            outcomes["unmatched"] += len(group)
            continue
        theirs = await inbox_store.without_own(conn, connections, group)
        outcomes["own"] += len(group) - len(theirs)
        group = theirs
        if not group:
            continue
        for index, connection in enumerate(connections):
            new_items = await inbox_store.ingest_events(conn, connection=connection, events=group)
            outcomes["stored"] += len(new_items)
            # One Page connected on several sites is one account: every site
            # sees the comment, but only the first-connected one answers it,
            # so a customer never gets the same reply twice.
            if not new_items or index > 0:
                continue
            settings = await effective_settings(conn, connection["site_id"])
            for item in new_items:
                try:
                    result = await autoreply.handle_item(conn, item, settings, send=_send)
                except Exception:  # noqa: BLE001 — one bad item must not drop the rest of the batch
                    logger.exception("cappe social inbound: handling inbox %s failed", item["id"])
                    result = {"outcome": "error"}
                outcomes[result["outcome"]] = outcomes.get(result["outcome"], 0) + 1
    return outcomes


async def _run(raw_events: list[dict[str, Any]]) -> dict[str, Any]:
    events = [InboundEvent.from_dict(e) for e in raw_events]
    if not events:
        return {"stored": 0}
    conn = await get_db_connection()
    try:
        cfg = MetaConfig.from_settings()
        if cfg is None:
            return {"skipped": True, "reason": "meta_not_configured"}
        return await process_events(conn, cfg, events)
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=3)
def run_cappe_social_inbound(self, raw_events: list[dict[str, Any]]) -> dict[str, Any]:
    """Store a webhook delivery's comments/messages and run the reply policy."""
    try:
        return {"status": "success", **asyncio.run(_run(raw_events))}
    except Exception as exc:
        logger.exception("Cappe social inbound failed")
        raise self.retry(exc=exc, countdown=30)


async def sweep(conn, cfg: MetaConfig, *, limit: int) -> dict[str, Any]:
    """Run the policy on the items it left (`inbox.unhandled`), oldest first.
    Stops at the first "no model": the shared budget is full or there is no
    model, and every other item would find the same. A site at its own cap
    only skips that site's items."""
    items = await inbox_store.unhandled(conn, limit=limit, within_hours=SWEEP_WINDOW_HOURS,
                                        max_attempts=autoreply.MAX_ATTEMPTS)
    outcomes: dict[str, Any] = {"items": len(items)}
    settings_by_site: dict[Any, dict[str, Any]] = {}
    send = _sender(conn, cfg)
    for item in items:
        site_id = item["site_id"]
        if site_id not in settings_by_site:
            settings_by_site[site_id] = await effective_settings(conn, site_id)
        try:
            result = await autoreply.handle_item(conn, item, settings_by_site[site_id], send=send)
        except Exception:  # noqa: BLE001 — one bad item must not stop the sweep
            logger.exception("cappe social inbox sweep: handling inbox %s failed", item["id"])
            result = {"outcome": "error"}
        outcomes[result["outcome"]] = outcomes.get(result["outcome"], 0) + 1
        if result.get("reason") == "no_model":
            break
    return outcomes


async def _run_sweep() -> dict[str, Any]:
    conn = await get_db_connection()
    try:
        setting = await scheduler_settings_row(conn, SWEEP_KEY)
        if not setting or not setting["enabled"]:
            return {"skipped": True}
        cfg = MetaConfig.from_settings()
        if cfg is None:
            return {"skipped": True, "reason": "meta_not_configured"}
        limit = max(1, min(int(setting["max_per_cycle"] or 50), 500))
        return await sweep(conn, cfg, limit=limit)
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_cappe_social_inbox_sweep(self) -> dict[str, Any]:
    """Retry the reply policy on social comments and messages it left (hourly)."""
    try:
        return {"status": "success", **asyncio.run(_run_sweep())}
    except Exception as exc:
        logger.exception("Cappe social inbox sweep failed")
        raise self.retry(exc=exc, countdown=300)

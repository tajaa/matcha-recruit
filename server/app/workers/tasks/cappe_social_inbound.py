"""Celery task: store the comments and messages a Meta webhook delivered,
then run the owner's reply policy on each new one.

On-demand (dispatched via .delay() from the public webhook route, NOT
scheduled). The route has already verified the signature and parsed the
payload into `InboundEvent` dicts; this task finds the connection each one
belongs to, inserts what is new (re-deliveries drop on the unique key), and
hands each new row to `autoreply.handle_item`, which decides between sending,
drafting for approval, escalating, or leaving it — per the site's settings.
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
from ..utils import get_db_connection

logger = logging.getLogger(__name__)


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
    outcomes: dict[str, int] = {"stored": 0, "unmatched": 0}
    by_recipient: dict[tuple[str, str], list[InboundEvent]] = {}
    for event in events:
        by_recipient.setdefault((event.platform, event.recipient_external_id), []).append(event)

    async def _send(item: dict[str, Any], body: str) -> str:
        return await outbound.send_reply(conn, cfg, item, body)

    for (platform, external_id), group in by_recipient.items():
        connections = await conn_store.by_external_id(conn, platform, external_id)
        if not connections:
            outcomes["unmatched"] += len(group)
            continue
        for connection in connections:
            new_items = await inbox_store.ingest_events(conn, connection=connection, events=group)
            outcomes["stored"] += len(new_items)
            if not new_items:
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

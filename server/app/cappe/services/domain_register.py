"""Background-safe finalization of paid domain registrations."""
import logging
from uuid import UUID

from ...database import connection_or_direct
from .porkbun import PorkbunError, get_porkbun
from .render_cache import invalidate_site_render_cache
from .stripe_connect import CappeStripeError, get_cappe_stripe

logger = logging.getLogger("cappe.domain_register")


async def finalize_domain_registration(domain_id: UUID) -> None:
    """Register a paid domain and activate it; safe to retry.

    The route-level cache helper also clears a process-local host cache. This
    service uses only the Redis render cache; host-gate lag is at most its 60s
    TTL, and services must not import routes.
    """
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            "SELECT id, site_id, domain, wholesale_cents, stripe_payment_intent "
            "FROM cappe_domains WHERE id = $1 AND status = 'registering'", domain_id)
    if row is None:
        return
    pb = get_porkbun()
    try:
        await pb.register(row["domain"], cost_cents=int(row["wholesale_cents"] or 0), idempotency_key=str(domain_id))
        try:
            await pb.point_at_app(row["domain"])
        except PorkbunError as exc:
            logger.warning("cappe domain %s registered but DNS pointing failed: %s", domain_id, exc)
    except PorkbunError as exc:
        logger.error("cappe domain %s registration failed: %s", domain_id, exc)
        async with connection_or_direct() as conn:
            await conn.execute(
                "UPDATE cappe_domains SET status = 'failed', failure_reason = $2, updated_at = NOW() WHERE id = $1",
                domain_id, str(exc)[:500])
        if row["stripe_payment_intent"]:
            try:
                await get_cappe_stripe().refund(row["stripe_payment_intent"])
            except CappeStripeError as refund_exc:
                logger.error("cappe domain %s refund failed: %s", domain_id, refund_exc)
        return
    async with connection_or_direct() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE cappe_domains SET status = 'active', expires_at = NOW() + INTERVAL '1 year', updated_at = NOW() WHERE id = $1",
                domain_id)
            await conn.execute(
                "UPDATE cappe_sites SET custom_domain = $1, updated_at = NOW() WHERE id = $2",
                row["domain"], row["site_id"])
    await invalidate_site_render_cache(row["site_id"])
    logger.info("cappe domain %s active → %s", domain_id, row["domain"])

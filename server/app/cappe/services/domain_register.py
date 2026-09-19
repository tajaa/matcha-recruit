"""Porkbun registration finalization shared by webhook and reconciliation.

Order matters: register at Porkbun → attach the domain to the CloudFront
tenant distribution → point DNS at that tenant's routing endpoint. The row goes
`active` with `edge_status='pending_dns'`; it is the edge sweeper
(`workers/tasks/cappe_edge_sync.py`) that flips `edge_status='live'` and only
THEN writes `cappe_sites.custom_domain`. Setting `custom_domain` at activation
is what used to publish a domain whose certificate did not exist yet, so every
visitor got a TLS error page.
"""

import logging
from uuid import UUID

from ...database import connection_or_direct
from .cloudfront_tenants import CappeEdgeError, get_cloudfront_tenants
from .porkbun import PorkbunError, get_porkbun
from .stripe_connect import CappeStripeError, get_cappe_stripe

logger = logging.getLogger("cappe.domain_register")


# A 'provisioning' claim with no tenant older than this is a process that died
# between the claim and the AWS call; it may be re-claimed.
_STALE_CLAIM = "10 minutes"


async def provision_domain_edge(domain_id: UUID, domain: str) -> tuple[str, str | None]:
    """Create the CloudFront tenant for `domain` and persist the result.

    Returns (edge_status, routing_endpoint). A failure here is recorded but not
    raised: the domain is registered and paid for, so the row must not be lost.
    An operator (or the tenant, via POST /domains/{id}/edge/retry) re-runs it.

    **Claimed.** Verify, retry, the registration webhook and the edge sweeper
    can all reach this for the same row (a double-click is enough). Without a
    claim the second caller's `create_distribution_tenant` fails with "already
    exists" and then stamps `edge_status='failed'` over the first caller's
    healthy tenant. The conditional UPDATE lets exactly one caller through;
    everyone else reads back what the winner wrote.

    The AWS round-trip happens OUTSIDE any held connection — the same rule the
    Stripe paths follow, so a slow edge call never pins one from the pool.
    """
    async with connection_or_direct() as conn:
        claim = await conn.fetchrow(
            f"""UPDATE cappe_domains
                   SET edge_status = 'provisioning', edge_error = NULL,
                       edge_checked_at = NOW(), updated_at = NOW()
                 WHERE id = $1 AND cf_tenant_id IS NULL
                   AND (edge_status IN ('none', 'failed')
                        OR (edge_status = 'provisioning'
                            AND edge_checked_at < NOW() - INTERVAL '{_STALE_CLAIM}'))
             RETURNING kind""",
            domain_id,
        )
        if claim is None:
            current = await conn.fetchrow(
                "SELECT edge_status, cf_routing_endpoint FROM cappe_domains WHERE id = $1",
                domain_id,
            )
            if current is None:
                return "none", None
            return current["edge_status"], current["cf_routing_endpoint"]

    try:
        tenant = await get_cloudfront_tenants().create_tenant(
            domain, include_www=(claim["kind"] == "register")
        )
    except CappeEdgeError as exc:
        logger.error("cappe domain %s edge provisioning failed: %s", domain_id, exc)
        async with connection_or_direct() as conn:
            await conn.execute(
                "UPDATE cappe_domains SET edge_status = 'failed', edge_error = $2, "
                "edge_checked_at = NOW(), updated_at = NOW() "
                "WHERE id = $1 AND cf_tenant_id IS NULL",
                domain_id,
                str(exc)[:500],
            )
        return "failed", None

    async with connection_or_direct() as conn:
        await conn.execute(
            "UPDATE cappe_domains SET cf_tenant_id = $2, cf_routing_endpoint = $3, "
            "edge_status = 'pending_dns', edge_error = NULL, edge_checked_at = NOW(), "
            "updated_at = NOW() WHERE id = $1",
            domain_id,
            tenant.tenant_id,
            tenant.routing_endpoint,
        )
    return "pending_dns", tenant.routing_endpoint


async def finalize_domain_registration(domain_id: UUID) -> None:
    async with connection_or_direct() as conn:
        # Claim the row: the UPDATE both proves the domain is still awaiting
        # registration and bumps `updated_at`, which is what keeps the 15-minute
        # reconciler (`cappe_domain_finalize`) from re-entering a registration
        # a webhook-triggered run is already performing.
        row = await conn.fetchrow(
            "UPDATE cappe_domains SET updated_at = NOW() "
            "WHERE id = $1 AND status = 'registering' "
            "RETURNING id, site_id, domain, wholesale_cents, stripe_payment_intent",
            domain_id,
        )
    if row is None:
        return
    pb = get_porkbun()
    try:
        await pb.register(
            row["domain"],
            cost_cents=int(row["wholesale_cents"] or 0),
            idempotency_key=str(domain_id),
        )
    except PorkbunError as exc:
        logger.error("cappe domain %s registration failed: %s", domain_id, exc)
        async with connection_or_direct() as conn:
            await conn.execute(
                "UPDATE cappe_domains SET status = 'failed', failure_reason = $2, updated_at = NOW() WHERE id = $1",
                domain_id,
                str(exc)[:500],
            )
        if row["stripe_payment_intent"]:
            try:
                await get_cappe_stripe().refund(row["stripe_payment_intent"])
            except CappeStripeError as refund_exc:
                logger.error("cappe domain %s refund failed: %s", domain_id, refund_exc)
        return

    async with connection_or_direct() as conn:
        await conn.execute(
            "UPDATE cappe_domains SET status = 'active', "
            "expires_at = NOW() + INTERVAL '1 year', updated_at = NOW() WHERE id = $1",
            domain_id,
        )
    _edge_status, routing_endpoint = await provision_domain_edge(domain_id, row["domain"])

    if routing_endpoint:
        try:
            await pb.point_at_app(row["domain"], routing_endpoint)
        except PorkbunError as exc:
            logger.warning(
                "cappe domain %s registered but DNS pointing failed: %s", domain_id, exc
            )
    logger.info("cappe domain %s active -> %s (edge pending)", domain_id, row["domain"])


async def retry_domain_edge(domain_id: UUID) -> str:
    """Re-run edge provisioning for an active domain that is not serving.

    Two recoverable shapes:
      * no tenant yet (`edge_status` 'none' or 'failed') — creation never
        happened or errored; just provision.
      * a tenant whose certificate is dead (`edge_status='failed'` WITH a
        tenant: validation timed out, revoked…). CloudFront will not re-issue
        on a failed managed certificate, so the tenant is deleted and a fresh
        one created. Before this the retry was a no-op for that row and the
        domain had no way forward.

    A `pending_dns`/`provisioning`/`live` tenant is never touched, so a retry
    can not detach a domain that is working or still validating. Returns the
    resulting edge_status.
    """
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            "SELECT id, kind, domain, cf_tenant_id, edge_status FROM cappe_domains "
            "WHERE id = $1 AND status = 'active'",
            domain_id,
        )
    if row is None:
        return "none"
    if row["cf_tenant_id"]:
        if row["edge_status"] != "failed":
            return row["edge_status"]
        try:
            await get_cloudfront_tenants().delete_tenant(row["cf_tenant_id"])
        except CappeEdgeError as exc:
            logger.warning("cappe domain %s dead-tenant cleanup failed: %s", domain_id, exc)
            return "failed"
        async with connection_or_direct() as conn:
            await conn.execute(
                "UPDATE cappe_domains SET cf_tenant_id = NULL, updated_at = NOW() "
                "WHERE id = $1 AND cf_tenant_id = $2 AND edge_status = 'failed'",
                domain_id, row["cf_tenant_id"],
            )
    edge_status, routing_endpoint = await provision_domain_edge(domain_id, row["domain"])

    # A bought domain lives in our Porkbun account, so we can point it ourselves;
    # a connected (BYO) domain's DNS is the tenant's to change.
    if routing_endpoint and row["kind"] == "register":
        try:
            await get_porkbun().point_at_app(row["domain"], routing_endpoint)
        except PorkbunError as exc:
            logger.warning("cappe domain %s DNS re-point failed: %s", domain_id, exc)
    return edge_status

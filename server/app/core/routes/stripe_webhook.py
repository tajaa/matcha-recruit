"""Stripe webhook routes."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from ..services.stripe_service import StripeService, StripeServiceError
from ..services.product_definitions import product_for_pack_id
from ...database import get_connection
from ...matcha.services import billing_service
from ...matcha.services import token_budget_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stripe-webhooks"])


async def _claim_event(event_id: str, event_type: str) -> bool:
    """Record the event ID in stripe_webhook_events. Returns True if this
    is the first time we've seen this event, False if it's a retry that
    we already processed.

    Stripe retries webhook events on transient failures (or any non-2xx
    response). Without dedupe, a retried event would re-execute every
    side effect (feature flips, emails, subscription upserts). The unique
    primary key on event_id makes the INSERT idempotent — a duplicate
    inserts no row, so we return False. A genuine DB error is re-raised so the
    webhook fails closed and Stripe retries.
    """
    try:
        async with get_connection() as conn:
            inserted = await conn.fetchval(
                """
                INSERT INTO stripe_webhook_events (event_id, event_type)
                VALUES ($1, $2)
                ON CONFLICT (event_id) DO NOTHING
                RETURNING event_id
                """,
                event_id,
                event_type,
            )
        return inserted is not None
    except Exception:
        # Fail CLOSED: a broken dedupe table (e.g. migration not yet applied)
        # must NOT let side effects run without a durable idempotency record,
        # or a Stripe retry double-processes the money path (double token
        # grants, duplicate feature flips). Surface the error so the webhook
        # returns 500 and Stripe retries — a delayed retry beats a double-spend.
        logger.exception(
            "stripe_webhook_events insert failed for %s (%s) — failing closed",
            event_id,
            event_type,
        )
        raise


from ..services.stripe_service import extract_current_period_end as _extract_current_period_end  # noqa: E402,F401


async def _release_event(event_id: str) -> None:
    """Delete the dedupe row so Stripe retries can re-process this event.

    Called when a handler raises after we've already claimed the event_id.
    Without this, the next Stripe retry would hit the dedupe gate and skip
    the handler — leaving the caller (paid customer) permanently in a
    half-activated state.
    """
    if not event_id:
        return
    try:
        async with get_connection() as conn:
            await conn.execute(
                "DELETE FROM stripe_webhook_events WHERE event_id = $1",
                event_id,
            )
    except Exception as exc:
        logger.warning("stripe_webhook_events release failed: %s", exc)


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe signature",
        )

    stripe_service = StripeService()
    try:
        event = await stripe_service.verify_webhook(payload, signature)
    except StripeServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # stripe-python v15 uses typed objects — convert to plain dicts for compat
    event_type = str(getattr(event, "type", None) or "")
    event_id = str(getattr(event, "id", "") or "")
    _raw_obj = getattr(getattr(event, "data", None), "object", None)
    event_object = (_raw_obj.to_dict() if hasattr(_raw_obj, "to_dict") else {}) if _raw_obj is not None else {}

    # Top-level dedupe — if Stripe retries this event, ack with 200 so
    # they stop retrying, but skip all side effects.
    if event_id and not await _claim_event(event_id, event_type):
        logger.info("Stripe event %s (%s) already processed, skipping", event_id, event_type)
        return {"status": "duplicate", "event_id": event_id}

    try:
        return await _route_event(event_type, event_object)
    except Exception:
        # Critical path failure — release the dedupe row so Stripe's
        # automatic retry can re-process this event. Without this, paid
        # customers whose activation hits a transient DB error would be
        # permanently stuck in a half-paid, no-access state.
        await _release_event(event_id)
        raise


async def _route_event(event_type: str, event_object: dict) -> dict:
    """Route a verified Stripe event to its handler. Raises on critical
    handler failure so the outer wrapper can release the dedupe row and
    Stripe can retry.

    Per-branch try/except policy:
      * Channel-sub / job-posting / tip activation paths re-raise on DB
        error so Stripe retries. A paid customer must not be left without
        access on a transient failure.
      * IR upgrade / lite / recruiter-tier / generic-pack / renewal /
        cancel branches log + swallow. These are either lower-stakes
        (recoverable manually via admin tools) or intentionally idempotent
        (cancel writes are no-ops on retry). Don't add `raise` to those
        branches without thinking through the dedupe-release flow.
    """
    # ── Route channel-specific events via metadata ─────────────────────────
    meta = event_object.get("metadata") or {}
    is_channel_event = meta.get("type") == "channel_subscription"

    # ── One-time checkout completed ───────────────────────────────────────────
    if event_type == "checkout.session.completed":
        session_mode = str(event_object.get("mode") or "payment")
        stripe_session_id = str(event_object.get("id") or "")

        if session_mode == "payment" and meta.get("type") == "channel_tip":
            try:
                channel_id = UUID(meta.get("channel_id", ""))
                sender_id = UUID(meta.get("sender_id", ""))
                creator_id = UUID(meta.get("creator_id", ""))
                amount = int(meta.get("amount_cents", "0"))
                tip_message = meta.get("message", "")

                from ...database import get_connection as _gc
                async with _gc() as conn:
                    # Log the tip event
                    await conn.execute(
                        """
                        INSERT INTO channel_payment_events (channel_id, user_id, event_type, amount_cents, metadata)
                        VALUES ($1, $2, 'tip_received', $3, $4::jsonb)
                        """,
                        channel_id, creator_id, amount,
                        __import__("json").dumps({"sender_id": str(sender_id), "message": tip_message}),
                    )
                    # Also log for sender
                    await conn.execute(
                        """
                        INSERT INTO channel_payment_events (channel_id, user_id, event_type, amount_cents, metadata)
                        VALUES ($1, $2, 'tip_sent', $3, $4::jsonb)
                        """,
                        channel_id, sender_id, amount,
                        __import__("json").dumps({"creator_id": str(creator_id), "message": tip_message}),
                    )
                    # Notify creator
                    company_id = await conn.fetchval("SELECT company_id FROM channels WHERE id = $1", channel_id)
                    channel_name = await conn.fetchval("SELECT name FROM channels WHERE id = $1", channel_id)
                    sender_name = await conn.fetchval(
                        "SELECT COALESCE(c.name, u.email) FROM users u LEFT JOIN clients c ON c.user_id = u.id WHERE u.id = $1",
                        sender_id,
                    )
                    from ...matcha.services import notification_service as notif_svc
                    await notif_svc.create_notification(
                        user_id=creator_id,
                        company_id=company_id,
                        type="channel_tip_received",
                        title=f"${amount/100:.2f} tip in #{channel_name}",
                        body=f"{sender_name} sent you a tip" + (f": \"{tip_message}\"" if tip_message else ""),
                        link=f"/work/channels/{channel_id}",
                    )
                logger.info("Channel tip processed: %s -> %s, $%.2f", sender_id, creator_id, amount/100)
            except Exception as exc:
                # Re-raise so Stripe retries — top-level dedupe via
                # stripe_webhook_events still blocks duplicate side effects.
                logger.error("Failed to process channel tip: %s", exc)
                raise

        elif session_mode == "payment":
            if not stripe_session_id:
                return {"received": True}
            fulfillment = await billing_service.fulfill_checkout_session(stripe_session_id)
            if fulfillment is None:
                logger.warning("Stripe session %s not found during fulfillment", stripe_session_id)
            elif fulfillment.get("already_fulfilled"):
                logger.info("Stripe session %s already fulfilled", stripe_session_id)
            else:
                logger.info(
                    "Stripe one-time session %s fulfilled (company %s)",
                    stripe_session_id,
                    fulfillment.get("session", {}).get("company_id", "?"),
                )

        elif session_mode == "subscription" and meta.get("type") == "matcha_ir_upgrade":
            # ── Resources_free → Matcha IR upgrade ────────────────────────
            company_id_str = meta.get("company_id") or ""
            stripe_sub_id = str(event_object.get("subscription") or "")
            if company_id_str:
                try:
                    import json as _json
                    from ...database import get_connection as _gc
                    company_id = UUID(company_id_str)
                    async with _gc() as conn:
                        # Promote feature flags: incidents + employees ON,
                        # signup_source flips so TenantSidebar routes to IR.
                        existing = await conn.fetchval(
                            "SELECT enabled_features FROM companies WHERE id = $1",
                            company_id,
                        )
                        features = existing if isinstance(existing, dict) else (
                            _json.loads(existing) if existing else {}
                        )
                        features["incidents"] = True
                        features["employees"] = True
                        await conn.execute(
                            """
                            UPDATE companies
                            SET enabled_features = $1::jsonb,
                                signup_source = 'ir_only_self_serve'
                            WHERE id = $2
                            """,
                            _json.dumps(features),
                            company_id,
                        )
                    logger.info(
                        "IR upgrade fulfilled: company=%s sub=%s",
                        company_id_str, stripe_sub_id,
                    )
                except Exception as exc:
                    logger.error("Failed to fulfill IR upgrade for %s: %s", company_id_str, exc)

        elif session_mode == "subscription" and meta.get("type") in ("matcha_lite", "matcha_x", "matcha_compliance"):
            # ── Matcha Lite / Matcha-X / Matcha Compliance signup payment ──
            # Each flips its single paid gate on. The differences: which feature
            # flag (incidents for Lite/X; the full `compliance` for the
            # standalone Compliance product), the subscription pack_id (used by
            # the cancel handler), and log copy.
            _tier_type = meta.get("type")
            _tier_label = {
                "matcha_x": "Matcha-X",
                "matcha_compliance": "Matcha Compliance",
            }.get(_tier_type, "Matcha Lite")
            # The single feature flag this checkout activates on payment.
            _paid_feature = {
                "matcha_lite": "incidents",
                "matcha_x": "incidents",
                "matcha_compliance": "compliance",
            }.get(_tier_type, "incidents")
            company_id_str = meta.get("company_id") or ""
            stripe_sub_id = str(event_object.get("subscription") or "")
            stripe_customer_id = str(event_object.get("customer") or "")
            if company_id_str:
                try:
                    import json as _json
                    from ...database import get_connection as _gc
                    company_id = UUID(company_id_str)
                    owner = None
                    just_activated = False
                    async with _gc() as conn:
                        existing = await conn.fetchval(
                            "SELECT enabled_features FROM companies WHERE id = $1",
                            company_id,
                        )
                        features = existing if isinstance(existing, dict) else (
                            _json.loads(existing) if existing else {}
                        )
                        # Track first-time activation so a Stripe retry
                        # of the same checkout.session.completed event
                        # doesn't send duplicate activation emails.
                        just_activated = not bool(features.get(_paid_feature))
                        features[_paid_feature] = True
                        await conn.execute(
                            """
                            UPDATE companies
                            SET enabled_features = $1::jsonb
                            WHERE id = $2
                            """,
                            _json.dumps(features),
                            company_id,
                        )
                        # Pull the owner's email + display name for the
                        # activation email below. Falls back to the email
                        # if the client.name is null.
                        if just_activated:
                            owner = await conn.fetchrow(
                                """
                                SELECT u.email,
                                       COALESCE(c.name, u.email) AS name,
                                       comp.name AS company_name
                                FROM companies comp
                                JOIN clients c ON c.company_id = comp.id
                                JOIN users u ON u.id = c.user_id
                                WHERE comp.id = $1
                                ORDER BY c.created_at ASC
                                LIMIT 1
                                """,
                                company_id,
                            )
                    # Record subscription so cancellation handler can find it.
                    # amount_cents comes from checkout-creation metadata when the
                    # caller set it (matcha_lite does; matcha_x/matcha_compliance
                    # don't yet, so this stays 0 for them, unchanged from before).
                    if stripe_sub_id:
                        await billing_service.upsert_subscription(
                            company_id=company_id,
                            stripe_subscription_id=stripe_sub_id,
                            stripe_customer_id=stripe_customer_id,
                            pack_id=_tier_type,
                            credits_per_cycle=0,
                            amount_cents=int(meta.get("amount_cents") or 0),
                        )
                    # Best-effort activation email — never let a flaky
                    # email service 500 the webhook (Stripe will retry).
                    if owner:
                        try:
                            from ..services.email import get_email_service
                            await get_email_service().send_lite_subscription_active_email(
                                to_email=owner["email"],
                                to_name=owner["name"],
                                company_name=owner["company_name"],
                            )
                        except Exception as email_exc:
                            logger.warning(
                                "Lite activation email failed for %s: %s",
                                company_id_str, email_exc,
                            )
                    logger.info(
                        "%s activated: company=%s sub=%s",
                        _tier_label, company_id_str, stripe_sub_id,
                    )
                except Exception as exc:
                    logger.error("Failed to activate %s for %s: %s", _tier_label, company_id_str, exc)

        elif session_mode == "subscription" and meta.get("type") == "matcha_lite_addon":
            # ── Matcha Lite add-on purchase ────────────────────────────────
            # The add-on rides its own Stripe sub. Resolve metadata.addon_key
            # through the lite_addons registry and flip exactly that add-on's
            # feature — never a metadata-supplied flag name (the registry is
            # the whitelist of enabled_features keys billing may touch).
            from ..services.lite_addons import LITE_ADDONS, addon_pack_id
            _addon = LITE_ADDONS.get(meta.get("addon_key") or "")
            company_id_str = meta.get("company_id") or ""
            stripe_sub_id = str(event_object.get("subscription") or "")
            stripe_customer_id = str(event_object.get("customer") or "")
            if _addon is None:
                # Junk metadata — ack (a Stripe retry can't fix it), leave a
                # loud log for manual follow-up since the customer paid.
                logger.error(
                    "Unknown lite addon_key %r in checkout %s (company=%s) — no flag flipped",
                    meta.get("addon_key"), stripe_session_id, company_id_str,
                )
            elif company_id_str:
                try:
                    import json as _json
                    from ...database import get_connection as _gc
                    company_id = UUID(company_id_str)
                    async with _gc() as conn:
                        existing = await conn.fetchval(
                            "SELECT enabled_features FROM companies WHERE id = $1",
                            company_id,
                        )
                        features = existing if isinstance(existing, dict) else (
                            _json.loads(existing) if existing else {}
                        )
                        features[_addon.feature] = True
                        await conn.execute(
                            "UPDATE companies SET enabled_features = $1::jsonb WHERE id = $2",
                            _json.dumps(features), company_id,
                        )
                    if stripe_sub_id:
                        await billing_service.upsert_subscription(
                            company_id=company_id,
                            stripe_subscription_id=stripe_sub_id,
                            stripe_customer_id=stripe_customer_id,
                            pack_id=addon_pack_id(_addon.key),
                            credits_per_cycle=0,
                            amount_cents=int(meta.get("amount_cents") or 0),
                        )
                    logger.info(
                        "Lite add-on %s activated: company=%s sub=%s",
                        _addon.key, company_id_str, stripe_sub_id,
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to activate lite add-on %s for %s: %s",
                        _addon.key, company_id_str, exc,
                    )

        elif session_mode == "subscription" and meta.get("type") == "matcha_lite_upgrade_from_essentials":
            # ── Essentials → standard Lite upgrade ─────────────────────────
            # Checkout-first flow: nothing changed until this event. Flip
            # signup_source (the tier overlay restores employees + osha_logs
            # at read time — no backfill) + keep incidents on, record the new
            # sub, then retire the old Essentials sub. Old-sub retirement is
            # DB-record FIRST, Stripe second: deleting the Stripe sub emits
            # customer.subscription.deleted for a pack_id='matcha_lite' row,
            # and that handler would un-flip `incidents` — pre-marking the
            # row canceled makes its cancel_subscription_record call return
            # False, skipping the whole un-flip block.
            company_id_str = meta.get("company_id") or ""
            stripe_sub_id = str(event_object.get("subscription") or "")
            stripe_customer_id = str(event_object.get("customer") or "")
            old_sub_id = meta.get("old_subscription_id") or ""
            if company_id_str:
                try:
                    import json as _json
                    from ...database import get_connection as _gc
                    company_id = UUID(company_id_str)
                    async with _gc() as conn:
                        existing = await conn.fetchval(
                            "SELECT enabled_features FROM companies WHERE id = $1",
                            company_id,
                        )
                        features = existing if isinstance(existing, dict) else (
                            _json.loads(existing) if existing else {}
                        )
                        features["incidents"] = True
                        await conn.execute(
                            """
                            UPDATE companies
                            SET enabled_features = $1::jsonb,
                                signup_source = 'matcha_lite'
                            WHERE id = $2
                            """,
                            _json.dumps(features),
                            company_id,
                        )
                    if stripe_sub_id:
                        await billing_service.upsert_subscription(
                            company_id=company_id,
                            stripe_subscription_id=stripe_sub_id,
                            stripe_customer_id=stripe_customer_id,
                            pack_id="matcha_lite",
                            credits_per_cycle=0,
                            amount_cents=int(meta.get("amount_cents") or 0),
                        )
                    if old_sub_id and old_sub_id != stripe_sub_id:
                        await billing_service.cancel_subscription_record(old_sub_id)
                        try:
                            from ..services.stripe_service import StripeService
                            await StripeService().cancel_subscription(old_sub_id, at_period_end=False)
                        except Exception as cancel_exc:
                            # Bounded double-billing until manually resolved —
                            # loud log with the sub id for admin cancel/refund.
                            # Deliberately not re-raised: the upgrade itself
                            # succeeded, and a dedupe-released retry would
                            # re-run the whole branch for nothing.
                            logger.error(
                                "Essentials→Lite upgrade: failed to cancel old Stripe sub %s "
                                "for company %s — cancel/refund manually: %s",
                                old_sub_id, company_id_str, cancel_exc,
                            )
                    logger.info(
                        "Essentials→Lite upgrade fulfilled: company=%s new_sub=%s old_sub=%s",
                        company_id_str, stripe_sub_id, old_sub_id,
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to fulfill Essentials→Lite upgrade for %s: %s",
                        company_id_str, exc,
                    )

        elif session_mode == "subscription" and meta.get("type") == "custom_product":
            # ── Admin-composed product (/admin/products) signup payment ────
            # The product row — NOT the metadata — decides which feature flags
            # this payment grants (same authorization rule as lite_addons.py:
            # billing may only touch flags the stored definition names). The
            # slug in metadata is just the lookup key.
            company_id_str = meta.get("company_id") or ""
            product_slug = meta.get("product_slug") or ""
            stripe_sub_id = str(event_object.get("subscription") or "")
            stripe_customer_id = str(event_object.get("customer") or "")
            if company_id_str and product_slug:
                try:
                    import json as _json
                    from ...database import get_connection as _gc
                    from ..services.product_definitions import (
                        get_product_by_slug as _get_product,
                        materialize_features as _materialize,
                    )
                    company_id = UUID(company_id_str)
                    just_activated = False
                    owner = None
                    async with _gc() as conn:
                        # published_only=False — archiving a product must not
                        # strand a customer who already paid for it.
                        product = await _get_product(conn, product_slug, published_only=False)
                        if product is None:
                            raise ValueError(f"Unknown product slug '{product_slug}'")
                        existing = await conn.fetchval(
                            "SELECT enabled_features FROM companies WHERE id = $1",
                            company_id,
                        )
                        stored = existing if isinstance(existing, dict) else (
                            _json.loads(existing) if existing else {}
                        )
                        gate = product.gate_feature
                        # First-time activation only, so a Stripe retry of the
                        # same event doesn't resend the activation email.
                        just_activated = not bool(stored.get(gate)) if gate else True
                        await conn.execute(
                            "UPDATE companies SET enabled_features = $1::jsonb WHERE id = $2",
                            _json.dumps(_materialize(product)), company_id,
                        )
                        if just_activated:
                            owner = await conn.fetchrow(
                                """
                                SELECT u.email,
                                       COALESCE(c.name, u.email) AS name,
                                       comp.name AS company_name
                                FROM companies comp
                                JOIN clients c ON c.company_id = comp.id
                                JOIN users u ON u.id = c.user_id
                                WHERE comp.id = $1
                                ORDER BY c.created_at ASC
                                LIMIT 1
                                """,
                                company_id,
                            )
                    if stripe_sub_id:
                        await billing_service.upsert_subscription(
                            company_id=company_id,
                            stripe_subscription_id=stripe_sub_id,
                            stripe_customer_id=stripe_customer_id,
                            pack_id=product.pack_id,
                            credits_per_cycle=0,
                            amount_cents=int(meta.get("amount_cents") or 0),
                        )
                    if owner:
                        try:
                            from ..services.email import get_email_service
                            await get_email_service().send_lite_subscription_active_email(
                                to_email=owner["email"],
                                to_name=owner["name"],
                                company_name=owner["company_name"],
                            )
                        except Exception as email_exc:
                            logger.warning(
                                "Product %s activated but activation email failed for %s: %s",
                                product_slug, company_id_str, email_exc,
                            )
                    logger.info(
                        "Custom product %s activated: company=%s sub=%s",
                        product_slug, company_id_str, stripe_sub_id,
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to activate custom product %s for %s: %s",
                        product_slug, company_id_str, exc,
                    )

        elif session_mode == "subscription" and is_channel_event:
            # ── Channel subscription checkout ────────────────────────────
            channel_id_str = meta.get("channel_id") or ""
            user_id_str = meta.get("user_id") or ""
            stripe_sub_id = str(event_object.get("subscription") or "")

            if channel_id_str and user_id_str and stripe_sub_id:
                try:
                    from ...werk.services.channel_payment_service import handle_subscription_activated
                    import asyncio
                    import stripe as _stripe
                    _stripe.api_key = StripeService().settings.stripe_secret_key
                    sub = await asyncio.to_thread(_stripe.Subscription.retrieve, stripe_sub_id)
                    invite_code = meta.get("invite_code")
                    await handle_subscription_activated(
                        channel_id=UUID(channel_id_str),
                        user_id=UUID(user_id_str),
                        stripe_subscription_id=stripe_sub_id,
                        current_period_end=_extract_current_period_end(sub),
                        invite_code=invite_code,
                    )
                    logger.info("Channel subscription activated: %s for user %s", stripe_sub_id, user_id_str)
                except Exception as exc:
                    logger.error("Failed to activate channel subscription: %s", exc)
                    raise

        elif session_mode == "subscription" and meta.get("type") == "job_posting_subscription":
            # ── Job posting subscription checkout ───────────────────────
            posting_id_str = meta.get("posting_id") or ""
            channel_id_str = meta.get("channel_id") or ""
            user_id_str = meta.get("user_id") or ""
            stripe_sub_id = str(event_object.get("subscription") or "")

            if posting_id_str and channel_id_str and user_id_str and stripe_sub_id:
                try:
                    from ...werk.services.channel_job_posting_service import handle_job_posting_activated
                    import asyncio
                    import stripe as _stripe
                    _stripe.api_key = StripeService().settings.stripe_secret_key
                    sub = await asyncio.to_thread(_stripe.Subscription.retrieve, stripe_sub_id)
                    await handle_job_posting_activated(
                        posting_id=UUID(posting_id_str),
                        channel_id=UUID(channel_id_str),
                        user_id=UUID(user_id_str),
                        stripe_subscription_id=stripe_sub_id,
                        current_period_end=_extract_current_period_end(sub),
                    )
                    logger.info("Job posting subscription activated: %s for posting %s", stripe_sub_id, posting_id_str)
                except Exception as exc:
                    logger.error("Failed to activate job posting subscription: %s", exc)
                    raise

        elif session_mode == "subscription":
            meta = event_object.get("metadata") or {}
            company_id_str = meta.get("company_id") or ""
            pack_id = meta.get("pack_id") or ""
            billing_type = meta.get("billing_type") or ""
            tokens_per_cycle = int(meta.get("tokens_per_cycle") or "0")
            stripe_sub_id = str(event_object.get("subscription") or "")
            stripe_customer_id = str(event_object.get("customer") or "")

            # Recruiter tier: extend user's recruiter_until by one month.
            # Stored on users, not mw_subscriptions, because tier is
            # per-user not per-company.
            if pack_id == "matcha_recruiter" and billing_type == "recruiter_tier":
                recruiter_user_id_str = meta.get("user_id") or ""
                if recruiter_user_id_str:
                    try:
                        from ...database import get_connection as _get_conn
                        async with _get_conn() as _conn:
                            await _conn.execute(
                                """
                                UPDATE users
                                SET recruiter_until = GREATEST(
                                    COALESCE(recruiter_until, NOW()),
                                    NOW()
                                ) + INTERVAL '1 month'
                                WHERE id = $1
                                """,
                                UUID(recruiter_user_id_str),
                            )
                        logger.info(
                            "Recruiter tier activated for user %s (sub %s)",
                            recruiter_user_id_str, stripe_sub_id,
                        )
                    except Exception as exc:
                        logger.error("Failed to activate recruiter tier: %s", exc)
                # No further processing — recruiter tier doesn't touch
                # mw_subscriptions / token budgets.
                return {"received": True}

            if company_id_str and pack_id and stripe_sub_id:
                try:
                    company_id = UUID(company_id_str)

                    # Price comes from the session metadata (set at checkout
                    # creation). Fallback map covers sessions created before
                    # amount_cents was added to metadata — previously this
                    # hardcoded the $40 token-pack price for every pack, so
                    # $20 personal subs were recorded as $40.
                    _pack_amount_fallbacks = {
                        "matcha_work_personal": 2000,
                        "matcha_work_lite": 900,
                        token_budget_service.SUBSCRIPTION_PACK_ID: token_budget_service.SUBSCRIPTION_AMOUNT_CENTS,
                    }
                    amount_cents = int(meta.get("amount_cents") or 0) or _pack_amount_fallbacks.get(
                        pack_id, token_budget_service.SUBSCRIPTION_AMOUNT_CENTS
                    )

                    # Record subscription in mw_subscriptions
                    await billing_service.upsert_subscription(
                        company_id=company_id,
                        stripe_subscription_id=stripe_sub_id,
                        stripe_customer_id=stripe_customer_id,
                        pack_id=pack_id,
                        credits_per_cycle=0,
                        amount_cents=amount_cents,
                    )

                    # New subscription changes the user's resolved plan.
                    from ...matcha.services import entitlements_service
                    entitlements_service.invalidate_plan_cache()

                    # Activate token budget
                    if billing_type == "token_budget" and tokens_per_cycle > 0:
                        await token_budget_service.reset_subscription_tokens(
                            company_id, token_limit=tokens_per_cycle,
                        )
                        logger.info(
                            "Token subscription activated for company %s: %d tokens/month",
                            company_id_str, tokens_per_cycle,
                        )
                    else:
                        logger.info("Subscription %s recorded for company %s", stripe_sub_id, company_id_str)

                except Exception as exc:
                    logger.error("Failed to record subscription %s: %s", stripe_sub_id, exc)

    # ── Checkout expired ──────────────────────────────────────────────────────
    elif event_type == "checkout.session.expired":
        stripe_session_id = str(event_object.get("id") or "")
        if stripe_session_id:
            await billing_service.mark_stripe_session_expired(stripe_session_id)
            logger.info("Stripe session %s marked expired", stripe_session_id)

    # ── Invoice payment failed ─────────────────────────────────────────────
    elif event_type == "invoice.payment_failed":
        stripe_sub_id = str(event_object.get("subscription") or "")
        if stripe_sub_id:
            # Only handle for channel subscriptions (safe no-op if not found)
            try:
                from ...werk.services.channel_payment_service import handle_payment_failed
                await handle_payment_failed(stripe_sub_id)
            except Exception as exc:
                logger.error("Channel payment failure handler error: %s", exc)

            try:
                from ...werk.services.channel_job_posting_service import handle_job_posting_payment_failed
                await handle_job_posting_payment_failed(stripe_sub_id)
            except Exception as exc:
                logger.error("Job posting payment failure handler error: %s", exc)

    # ── Monthly invoice paid → reset token budget ────────────────────────────
    elif event_type == "invoice.paid":
        stripe_sub_id = str(event_object.get("subscription") or "")
        stripe_invoice_id = str(event_object.get("id") or "")
        billing_reason = str(event_object.get("billing_reason") or "")

        if stripe_sub_id and stripe_invoice_id and billing_reason == "subscription_cycle":
            # Check if this is a channel subscription renewal
            try:
                from ...werk.services.channel_payment_service import handle_subscription_renewed
                from ...database import get_connection as _get_conn
                async with _get_conn() as _conn:
                    is_channel_sub = await _conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM channel_members WHERE stripe_subscription_id = $1)",
                        stripe_sub_id,
                    )
                if is_channel_sub:
                    amount = int(event_object.get("amount_paid") or 0)
                    # Get period end from subscription lines
                    lines = event_object.get("lines", {}).get("data", [])
                    period_end = lines[0]["period"]["end"] if lines else None
                    if period_end and period_end > 0:
                        await handle_subscription_renewed(stripe_sub_id, period_end, amount)
                        logger.info("Channel subscription renewed: %s", stripe_sub_id)
                    else:
                        logger.warning("Channel subscription renewal %s missing period end", stripe_sub_id)
            except Exception as exc:
                logger.error("Channel subscription renewal error: %s", exc)

            # Also check for job posting subscription renewal
            from ...database import get_connection as _get_conn2
            async with _get_conn2() as _conn2:
                is_job_sub = await _conn2.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM channel_job_postings WHERE stripe_subscription_id = $1)",
                    stripe_sub_id,
                )
            if is_job_sub:
                from ...werk.services.channel_job_posting_service import handle_job_posting_renewed
                amount = int(event_object.get("amount_paid") or 0)
                lines = event_object.get("lines", {}).get("data", [])
                period_end = lines[0]["period"]["end"] if lines else None
                if period_end and period_end > 0:
                    await handle_job_posting_renewed(stripe_sub_id, period_end, amount)
                    logger.info("Job posting subscription renewed: %s", stripe_sub_id)

            # Look up the subscription to check if it's a token subscription
            sub = await billing_service.get_subscription_by_stripe_id(stripe_sub_id)
            if sub and sub["pack_id"] == token_budget_service.SUBSCRIPTION_PACK_ID:
                await token_budget_service.reset_subscription_tokens(
                    sub["company_id"],
                    token_limit=token_budget_service.SUBSCRIPTION_TOKENS,
                    stripe_invoice_id=stripe_invoice_id,
                )
                logger.info(
                    "Token subscription renewed: invoice %s, company %s",
                    stripe_invoice_id, sub["company_id"],
                )
            else:
                # Legacy dollar-credit subscription
                result = await billing_service.fulfill_subscription_invoice(
                    stripe_subscription_id=stripe_sub_id,
                    stripe_invoice_id=stripe_invoice_id,
                )
                if result and not result.get("already_fulfilled"):
                    logger.info("Legacy subscription invoice %s fulfilled", stripe_invoice_id)

    # ── Subscription canceled / deleted ──────────────────────────────────────
    elif event_type == "customer.subscription.deleted":
        stripe_sub_id = str(event_object.get("id") or "")
        if stripe_sub_id:
            # Handle channel subscription cancellation
            try:
                from ...werk.services.channel_payment_service import handle_subscription_canceled
                await handle_subscription_canceled(stripe_sub_id)
            except Exception as exc:
                logger.error("Channel subscription cancellation error: %s", exc)

            try:
                from ...werk.services.channel_job_posting_service import handle_job_posting_canceled
                await handle_job_posting_canceled(stripe_sub_id)
            except Exception as exc:
                logger.error("Job posting cancellation handler error: %s", exc)

            # Fetch before canceling to get company_id and pack_id
            sub = await billing_service.get_subscription_by_stripe_id(stripe_sub_id)
            canceled = await billing_service.cancel_subscription_record(stripe_sub_id)
            if canceled:
                logger.info("Subscription %s marked canceled", stripe_sub_id)
                if sub and sub["pack_id"] == token_budget_service.SUBSCRIPTION_PACK_ID:
                    await token_budget_service.cancel_subscription_budget(sub["company_id"])
                    logger.info("Token budget zeroed for company %s", sub["company_id"])
                elif sub and product_for_pack_id(sub["pack_id"]):
                    # ── Admin-composed product canceled ──────────────────
                    # Reset to the pending shape (every flag off) so the
                    # tenant lands back on the Subscribe CTA, mirroring the
                    # Lite un-flip. Same cancel-then-resubscribe guard.
                    _slug = product_for_pack_id(sub["pack_id"])
                    replacement = await billing_service.get_active_subscription(
                        sub["company_id"], pack_ids=(sub["pack_id"],)
                    )
                    if replacement is not None:
                        logger.info(
                            "Product %s sub %s canceled but replacement %s is active for company %s — keeping access",
                            _slug, stripe_sub_id,
                            replacement["stripe_subscription_id"], sub["company_id"],
                        )
                    else:
                        try:
                            import json as _json
                            from ...database import get_connection as _gc
                            from ..services.product_definitions import (
                                get_product_by_slug as _get_product,
                                pending_features as _pending,
                            )
                            async with _gc() as conn:
                                product = await _get_product(conn, _slug, published_only=False)
                                if product is None:
                                    raise ValueError(f"Unknown product slug '{_slug}'")
                                await conn.execute(
                                    "UPDATE companies SET enabled_features = $1::jsonb WHERE id = $2",
                                    _json.dumps(_pending(product)), sub["company_id"],
                                )
                            logger.info("Product %s deactivated for company %s", _slug, sub["company_id"])
                        except Exception as exc:
                            logger.error(
                                "Failed to deactivate product %s for %s: %s",
                                _slug, sub["company_id"], exc,
                            )
                elif sub and sub["pack_id"] in ("matcha_lite", "matcha_x", "matcha_compliance"):
                    # Each tier flips its single paid gate off on cancellation —
                    # incidents for Lite/X, the full `compliance` for the
                    # standalone Compliance product (mirror of the activation
                    # branch above; keep the flag map in sync with it).
                    _pack = sub["pack_id"]
                    _tier_label = {
                        "matcha_x": "Matcha-X",
                        "matcha_compliance": "Matcha Compliance",
                    }.get(_pack, "Matcha Lite")
                    _paid_feature = {
                        "matcha_lite": "incidents",
                        "matcha_x": "incidents",
                        "matcha_compliance": "compliance",
                    }.get(_pack, "incidents")
                    # Cancel-then-resubscribe guard: if the company already
                    # holds ANOTHER active sub of the same pack (e.g. the
                    # Essentials→Lite upgrade recorded its new sub before the
                    # old one's deleted event arrived out of order), the paid
                    # gate must stay on and the add-on cascade must not run.
                    replacement = await billing_service.get_active_subscription(
                        sub["company_id"], pack_ids=(_pack,)
                    )
                    if replacement is not None:
                        logger.info(
                            "%s sub %s canceled but replacement sub %s is active for company %s — keeping access",
                            _tier_label, stripe_sub_id,
                            replacement["stripe_subscription_id"], sub["company_id"],
                        )
                    else:
                        try:
                            import json as _json
                            from ...database import get_connection as _gc
                            async with _gc() as conn:
                                existing = await conn.fetchval(
                                    "SELECT enabled_features FROM companies WHERE id = $1",
                                    sub["company_id"],
                                )
                                features = existing if isinstance(existing, dict) else (
                                    _json.loads(existing) if existing else {}
                                )
                                features[_paid_feature] = False
                                await conn.execute(
                                    "UPDATE companies SET enabled_features = $1::jsonb WHERE id = $2",
                                    _json.dumps(features), sub["company_id"],
                                )
                            logger.info("%s deactivated for company %s", _tier_label, sub["company_id"])
                        except Exception as exc:
                            logger.error("Failed to deactivate %s for %s: %s", _tier_label, sub["company_id"], exc)
                        # Base Lite gone → cascade-cancel any add-on subs
                        # riding it. Best-effort + immediate; each add-on's
                        # own deleted event then un-flips its feature flag
                        # (event-driven, no double bookkeeping here). Stripe
                        # doesn't auto-refund the remainder — admin refund
                        # tooling covers that.
                        if _pack == "matcha_lite":
                            from ..services.lite_addons import ADDON_PACK_PREFIX
                            try:
                                addon_subs = [
                                    s for s in await billing_service.list_active_subscriptions(sub["company_id"])
                                    if s["pack_id"].startswith(ADDON_PACK_PREFIX)
                                ]
                                if addon_subs:
                                    from ..services.stripe_service import StripeService
                                    _stripe = StripeService()
                                    for addon_sub in addon_subs:
                                        try:
                                            await _stripe.cancel_subscription(
                                                addon_sub["stripe_subscription_id"], at_period_end=False,
                                            )
                                            logger.info(
                                                "Cascade-canceled add-on sub %s (%s) for company %s",
                                                addon_sub["stripe_subscription_id"],
                                                addon_sub["pack_id"], sub["company_id"],
                                            )
                                        except Exception as cascade_exc:
                                            logger.error(
                                                "Failed to cascade-cancel add-on sub %s for company %s: %s",
                                                addon_sub["stripe_subscription_id"],
                                                sub["company_id"], cascade_exc,
                                            )
                            except Exception as exc:
                                logger.error(
                                    "Add-on cascade-cancel failed for company %s: %s",
                                    sub["company_id"], exc,
                                )
                elif sub and sub["pack_id"].startswith("matcha_lite_addon_"):
                    # ── Lite add-on cancellation — un-flip that add-on's flag.
                    from ..services.lite_addons import addon_for_pack_id
                    _addon = addon_for_pack_id(sub["pack_id"])
                    if _addon is None:
                        logger.error(
                            "Canceled sub %s has unknown add-on pack_id %r — no flag un-flipped",
                            stripe_sub_id, sub["pack_id"],
                        )
                    else:
                        try:
                            import json as _json
                            from ...database import get_connection as _gc
                            async with _gc() as conn:
                                existing = await conn.fetchval(
                                    "SELECT enabled_features FROM companies WHERE id = $1",
                                    sub["company_id"],
                                )
                                features = existing if isinstance(existing, dict) else (
                                    _json.loads(existing) if existing else {}
                                )
                                features[_addon.feature] = False
                                await conn.execute(
                                    "UPDATE companies SET enabled_features = $1::jsonb WHERE id = $2",
                                    _json.dumps(features), sub["company_id"],
                                )
                            logger.info(
                                "Lite add-on %s deactivated for company %s",
                                _addon.key, sub["company_id"],
                            )
                        except Exception as exc:
                            logger.error(
                                "Failed to deactivate lite add-on %s for %s: %s",
                                _addon.key, sub["company_id"], exc,
                            )

    return {"received": True}

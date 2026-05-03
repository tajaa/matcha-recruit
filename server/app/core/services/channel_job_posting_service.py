"""Channel job posting service — Stripe integration for paid job postings."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

try:
    import stripe
except ImportError:
    stripe = None

from ...config import get_settings
from ...database import get_connection

logger = logging.getLogger(__name__)

JOB_POSTING_PRICE_CENTS = 20000  # $200/month — platform default
MIN_JOB_POSTING_PRICE_CENTS = 50  # Stripe minimum
MAX_JOB_POSTING_PRICE_CENTS = 99900  # $999.00


class JobPostingPaymentError(Exception):
    pass


def _ensure_stripe():
    if stripe is None:
        raise JobPostingPaymentError("Stripe SDK not installed")
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise JobPostingPaymentError("Stripe not configured")
    stripe.api_key = settings.stripe_secret_key


async def create_job_posting_product_and_price(
    channel_id: UUID,
    channel_name: str,
    posting_title: str,
    price_cents: Optional[int] = None,
) -> tuple[str, str]:
    """Create a Stripe product + recurring monthly price for a job posting.

    `price_cents` honors the channel-owned override (`channels.job_posting_fee_cents`).
    NULL/None falls back to the platform default. Both the per-channel column
    and the platform default are validated against Stripe's price floor.
    """
    _ensure_stripe()

    resolved_price = price_cents if price_cents else JOB_POSTING_PRICE_CENTS
    if resolved_price < MIN_JOB_POSTING_PRICE_CENTS or resolved_price > MAX_JOB_POSTING_PRICE_CENTS:
        raise JobPostingPaymentError(
            f"Posting price must be between ${MIN_JOB_POSTING_PRICE_CENTS/100:.2f} and ${MAX_JOB_POSTING_PRICE_CENTS/100:.2f}"
        )

    def _create():
        product = stripe.Product.create(
            name=f"Job Posting: {posting_title} (#{channel_name})",
            metadata={
                "type": "job_posting_subscription",
                "channel_id": str(channel_id),
            },
        )
        price = stripe.Price.create(
            product=product.id,
            unit_amount=resolved_price,
            currency="usd",
            recurring={"interval": "month"},
        )
        return product.id, price.id

    try:
        return await asyncio.to_thread(_create)
    except Exception as exc:
        raise JobPostingPaymentError(f"Failed to create Stripe product: {exc}") from exc


async def create_job_posting_checkout(
    posting_id: UUID,
    channel_id: UUID,
    user_id: UUID,
    stripe_price_id: str,
) -> str:
    """Create a Stripe checkout session for a job posting subscription. Returns checkout URL."""
    _ensure_stripe()
    settings = get_settings()

    metadata = {
        "type": "job_posting_subscription",
        "posting_id": str(posting_id),
        "channel_id": str(channel_id),
        "user_id": str(user_id),
    }

    success_url = (
        f"{settings.app_base_url}/work/channels/{channel_id}"
        f"?posting={posting_id}&activated=1"
    )
    cancel_url = (
        f"{settings.app_base_url}/work/channels/{channel_id}"
        f"?posting={posting_id}&canceled=1"
    )

    def _create():
        session = stripe.checkout.Session.create(
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            payment_method_types=["card"],
            metadata=metadata,
            subscription_data={"metadata": metadata},
            line_items=[{"price": stripe_price_id, "quantity": 1}],
        )
        return session.url

    try:
        return await asyncio.to_thread(_create)
    except Exception as exc:
        raise JobPostingPaymentError(f"Failed to create checkout session: {exc}") from exc


async def handle_job_posting_activated(
    posting_id: UUID,
    channel_id: UUID,
    user_id: UUID,
    stripe_subscription_id: str,
    current_period_end: int,
) -> None:
    """Called when a job posting subscription checkout completes successfully."""
    paid_through = datetime.fromtimestamp(current_period_end, tz=timezone.utc)

    async with get_connection() as conn:
        await conn.execute(
            """
            UPDATE channel_job_postings
            SET status = 'active',
                subscription_status = 'active',
                stripe_subscription_id = $2,
                paid_through = $3,
                updated_at = NOW()
            WHERE id = $1
            """,
            posting_id, stripe_subscription_id, paid_through,
        )

        # Record the actual fee charged (channel override or platform default)
        # so analytics aren't off when channels customize their pricing.
        amount_cents = await conn.fetchval(
            "SELECT COALESCE(job_posting_fee_cents, $2) FROM channels WHERE id = $1",
            channel_id, JOB_POSTING_PRICE_CENTS,
        ) or JOB_POSTING_PRICE_CENTS

        await conn.execute(
            """
            INSERT INTO channel_payment_events
                (channel_id, user_id, event_type, amount_cents, metadata)
            VALUES ($1, $2, 'job_posting_activated', $3, $4::jsonb)
            """,
            channel_id, user_id, amount_cents,
            __import__("json").dumps({
                "posting_id": str(posting_id),
                "stripe_subscription_id": stripe_subscription_id,
                "payout_amount_cents": amount_cents // 2,
            }),
        )


async def handle_job_posting_renewed(
    stripe_subscription_id: str,
    current_period_end: int,
    amount_cents: int,
) -> None:
    """Called when a job posting subscription invoice is paid (renewal)."""
    paid_through = datetime.fromtimestamp(current_period_end, tz=timezone.utc)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, channel_id, posted_by
            FROM channel_job_postings
            WHERE stripe_subscription_id = $1
            """,
            stripe_subscription_id,
        )
        if not row:
            logger.warning("No posting found for subscription %s", stripe_subscription_id)
            return

        await conn.execute(
            """
            UPDATE channel_job_postings
            SET paid_through = $2, subscription_status = 'active', updated_at = NOW()
            WHERE stripe_subscription_id = $1
            """,
            stripe_subscription_id, paid_through,
        )

        await conn.execute(
            """
            INSERT INTO channel_payment_events
                (channel_id, user_id, event_type, amount_cents, metadata)
            VALUES ($1, $2, 'job_posting_renewed', $3, $4::jsonb)
            """,
            row["channel_id"], row["posted_by"], amount_cents,
            __import__("json").dumps({
                "posting_id": str(row["id"]),
                "stripe_subscription_id": stripe_subscription_id,
                "payout_amount_cents": amount_cents // 2,
            }),
        )


async def handle_job_posting_payment_failed(stripe_subscription_id: str) -> None:
    """Called when a job posting subscription payment fails. Caps emails
    to one per cycle — see handle_payment_failed in channel_payment_service
    for the matching pattern on member subs."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT jp.id, jp.channel_id, jp.posted_by, jp.title, ch.company_id
            FROM channel_job_postings jp
            JOIN channels ch ON ch.id = jp.channel_id
            WHERE jp.stripe_subscription_id = $1
            """,
            stripe_subscription_id,
        )
        if not row:
            return

        await conn.execute(
            """
            UPDATE channel_job_postings
            SET subscription_status = 'past_due', updated_at = NOW()
            WHERE stripe_subscription_id = $1
            """,
            stripe_subscription_id,
        )

        # Stripe retries failed invoices 3-4× over ~3 weeks; one email per
        # cycle is enough. Boundary = last successful renewal event.
        last_success = await conn.fetchval(
            """
            SELECT created_at FROM channel_payment_events
            WHERE event_type = 'job_posting_renewed'
              AND metadata->>'stripe_subscription_id' = $1
            ORDER BY created_at DESC LIMIT 1
            """,
            stripe_subscription_id,
        )
        already_failed_this_cycle = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM channel_payment_events
                WHERE event_type = 'job_posting_payment_failed'
                  AND metadata->>'stripe_subscription_id' = $1
                  AND ($2::timestamptz IS NULL OR created_at > $2)
            )
            """,
            stripe_subscription_id, last_success,
        )
        if already_failed_this_cycle:
            return

        await conn.execute(
            """
            INSERT INTO channel_payment_events
                (channel_id, user_id, event_type, metadata)
            VALUES ($1, $2, 'job_posting_payment_failed', $3::jsonb)
            """,
            row["channel_id"], row["posted_by"],
            __import__("json").dumps({
                "posting_id": str(row["id"]),
                "stripe_subscription_id": stripe_subscription_id,
            }),
        )

        try:
            from ...matcha.services import notification_service as notif_svc
            await notif_svc.create_notification(
                user_id=row["posted_by"],
                company_id=row["company_id"],
                type="job_posting_payment_failed",
                title=f"Payment failed for job posting: {row['title']}",
                body="Your job posting subscription payment failed. Please update your payment method to keep it active.",
                link=f"/work/channels/{row['channel_id']}",
                send_email=True,
            )
        except Exception as e:
            logger.warning("Failed to send job posting payment failure notification: %s", e)


async def handle_job_posting_canceled(stripe_subscription_id: str) -> None:
    """Called when a job posting subscription is fully canceled/deleted in Stripe."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, channel_id, posted_by
            FROM channel_job_postings
            WHERE stripe_subscription_id = $1
            """,
            stripe_subscription_id,
        )
        if not row:
            return

        await conn.execute(
            """
            UPDATE channel_job_postings
            SET subscription_status = 'canceled',
                status = 'closed',
                closed_at = NOW(),
                updated_at = NOW()
            WHERE stripe_subscription_id = $1
            """,
            stripe_subscription_id,
        )

        await conn.execute(
            """
            INSERT INTO channel_payment_events
                (channel_id, user_id, event_type, metadata)
            VALUES ($1, $2, 'job_posting_canceled', $3::jsonb)
            """,
            row["channel_id"], row["posted_by"],
            __import__("json").dumps({
                "posting_id": str(row["id"]),
                "stripe_subscription_id": stripe_subscription_id,
            }),
        )


async def cancel_job_posting_subscription(
    stripe_subscription_id: str,
) -> datetime:
    """Cancel a job posting subscription at period end. Returns paid_through date."""
    _ensure_stripe()
    from .stripe_service import extract_current_period_end

    def _cancel():
        sub = stripe.Subscription.modify(
            stripe_subscription_id,
            cancel_at_period_end=True,
        )
        return datetime.fromtimestamp(extract_current_period_end(sub), tz=timezone.utc)

    try:
        paid_through = await asyncio.to_thread(_cancel)
    except Exception as exc:
        raise JobPostingPaymentError(f"Failed to cancel subscription: {exc}") from exc

    async with get_connection() as conn:
        await conn.execute(
            """
            UPDATE channel_job_postings
            SET subscription_status = 'canceling', updated_at = NOW()
            WHERE stripe_subscription_id = $1
            """,
            stripe_subscription_id,
        )

    return paid_through


async def send_invitations(
    posting_id: UUID,
    channel_id: UUID,
    company_id: UUID,
    user_ids: list[UUID],
    inviter_name: str,
    posting_title: str,
) -> None:
    """Batch-invite users to apply for a job posting. Sends notifications with email."""
    async with get_connection() as conn:
        # Insert invitations (idempotent via ON CONFLICT DO NOTHING)
        for uid in user_ids:
            await conn.execute(
                """
                INSERT INTO channel_job_invitations (posting_id, user_id)
                VALUES ($1, $2)
                ON CONFLICT (posting_id, user_id) DO NOTHING
                """,
                posting_id, uid,
            )

    # Send notification for each invited user
    try:
        from ...matcha.services import notification_service as notif_svc
        for uid in user_ids:
            try:
                await notif_svc.create_notification(
                    user_id=uid,
                    company_id=company_id,
                    type="job_posting_invite",
                    title=f"You're invited to apply: {posting_title}",
                    body=f"{inviter_name} invited you to apply for a position in a channel",
                    link=f"/work/channels/{channel_id}?posting={posting_id}",
                    send_email=True,
                )
            except Exception as e:
                logger.warning("Failed to send invite notification to %s: %s", uid, e)
    except Exception as e:
        logger.warning("Failed to import notification service: %s", e)

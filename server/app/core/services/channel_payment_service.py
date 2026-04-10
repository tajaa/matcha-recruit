"""Channel payment service — Stripe integration for paid channels."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

try:
    import stripe
except ImportError:
    stripe = None

from ...config import get_settings
from ...database import get_connection

logger = logging.getLogger(__name__)

MIN_PRICE_CENTS = 50  # Stripe minimum ~$0.50
MAX_PRICE_CENTS = 99900  # $999.00


class ChannelPaymentError(Exception):
    pass


def _ensure_stripe():
    if stripe is None:
        raise ChannelPaymentError("Stripe SDK not installed")
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise ChannelPaymentError("Stripe not configured")
    stripe.api_key = settings.stripe_secret_key


async def create_stripe_product_and_price(
    channel_id: UUID,
    channel_name: str,
    price_cents: int,
    currency: str = "usd",
) -> tuple[str, str]:
    """Create a Stripe product + recurring monthly price for a paid channel."""
    _ensure_stripe()

    if price_cents < MIN_PRICE_CENTS or price_cents > MAX_PRICE_CENTS:
        raise ChannelPaymentError(f"Price must be between ${MIN_PRICE_CENTS/100:.2f} and ${MAX_PRICE_CENTS/100:.2f}")

    def _create():
        product = stripe.Product.create(
            name=f"Channel: {channel_name}",
            metadata={"channel_id": str(channel_id), "type": "paid_channel"},
        )
        price = stripe.Price.create(
            product=product.id,
            unit_amount=price_cents,
            currency=currency,
            recurring={"interval": "month"},
        )
        return product.id, price.id

    try:
        return await asyncio.to_thread(_create)
    except Exception as exc:
        raise ChannelPaymentError(f"Failed to create Stripe product: {exc}") from exc


async def create_checkout_session(
    channel_id: UUID,
    channel_name: str,
    stripe_price_id: str,
    user_id: UUID,
    success_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
    invite_code: Optional[str] = None,
) -> str:
    """Create a Stripe checkout session for subscribing to a paid channel. Returns checkout URL."""
    _ensure_stripe()
    settings = get_settings()

    resolved_success = success_url or f"{settings.app_base_url}/app/matcha/work/channels/{channel_id}?subscribed=1"
    resolved_cancel = cancel_url or f"{settings.app_base_url}/app/matcha/work/channels/{channel_id}?canceled=1"

    metadata = {
        "channel_id": str(channel_id),
        "user_id": str(user_id),
        "type": "channel_subscription",
    }
    if invite_code:
        metadata["invite_code"] = invite_code

    def _create():
        session = stripe.checkout.Session.create(
            mode="subscription",
            success_url=resolved_success,
            cancel_url=resolved_cancel,
            payment_method_types=["card"],
            metadata=metadata,
            subscription_data={"metadata": metadata},
            line_items=[{"price": stripe_price_id, "quantity": 1}],
        )
        return session.url

    try:
        return await asyncio.to_thread(_create)
    except Exception as exc:
        raise ChannelPaymentError(f"Failed to create checkout session: {exc}") from exc


async def cancel_subscription(stripe_subscription_id: str) -> datetime:
    """Cancel a channel subscription at period end. Returns paid_through date."""
    _ensure_stripe()

    def _cancel():
        sub = stripe.Subscription.modify(
            stripe_subscription_id,
            cancel_at_period_end=True,
        )
        return datetime.fromtimestamp(sub.current_period_end, tz=timezone.utc)

    try:
        return await asyncio.to_thread(_cancel)
    except Exception as exc:
        raise ChannelPaymentError(f"Failed to cancel subscription: {exc}") from exc


async def cancel_subscription_immediately(stripe_subscription_id: str) -> None:
    """Cancel a subscription immediately (used for inactivity removal)."""
    _ensure_stripe()

    def _cancel():
        stripe.Subscription.cancel(stripe_subscription_id)

    try:
        await asyncio.to_thread(_cancel)
    except Exception as exc:
        logger.error("Failed to cancel subscription %s: %s", stripe_subscription_id, exc)


async def check_rejoin_eligibility(channel_id: UUID, user_id: UUID) -> dict:
    """Check if a user can rejoin a paid channel. Returns eligibility info."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT removal_cooldown_until, paid_through, removed_for_inactivity
            FROM channel_members
            WHERE channel_id = $1 AND user_id = $2
            """,
            channel_id, user_id,
        )

        if not row:
            return {"can_rejoin": True, "cooldown_until": None}

        now = datetime.now(timezone.utc)
        cooldown = row["removal_cooldown_until"]

        if cooldown and cooldown > now:
            return {
                "can_rejoin": False,
                "cooldown_until": cooldown.isoformat(),
                "reason": "removal_cooldown",
            }

        return {"can_rejoin": True, "cooldown_until": None}


async def handle_subscription_activated(
    channel_id: UUID,
    user_id: UUID,
    stripe_subscription_id: str,
    current_period_end: int,
    invite_code: Optional[str] = None,
) -> None:
    """Called when a channel subscription checkout completes successfully."""
    paid_through = datetime.fromtimestamp(current_period_end, tz=timezone.utc)

    async with get_connection() as conn:
        # Check if already a member (shouldn't be for new joins, but handle re-joins)
        existing = await conn.fetchval(
            "SELECT user_id FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, user_id,
        )

        if existing:
            # Re-joining after cooldown — update existing record
            await conn.execute(
                """
                UPDATE channel_members
                SET stripe_subscription_id = $3,
                    subscription_status = 'active',
                    paid_through = $4,
                    removed_for_inactivity = false,
                    removal_cooldown_until = NULL,
                    inactivity_warned_at = NULL,
                    last_contributed_at = NOW()
                WHERE channel_id = $1 AND user_id = $2
                """,
                channel_id, user_id, stripe_subscription_id, paid_through,
            )
        else:
            # New member
            await conn.execute(
                """
                INSERT INTO channel_members (channel_id, user_id, role, last_contributed_at,
                    stripe_subscription_id, subscription_status, paid_through)
                VALUES ($1, $2, 'member', NOW(), $3, 'active', $4)
                ON CONFLICT (channel_id, user_id) DO UPDATE SET
                    stripe_subscription_id = $3,
                    subscription_status = 'active',
                    paid_through = $4,
                    removed_for_inactivity = false,
                    removal_cooldown_until = NULL,
                    last_contributed_at = NOW()
                """,
                channel_id, user_id, stripe_subscription_id, paid_through,
            )

        # Log payment event
        await conn.execute(
            """
            INSERT INTO channel_payment_events (channel_id, user_id, event_type, metadata)
            VALUES ($1, $2, 'subscription_activated', $3::jsonb)
            """,
            channel_id, user_id,
            __import__("json").dumps({"stripe_subscription_id": stripe_subscription_id}),
        )

        # Increment invite use_count if this was an invite-based join (deferred from checkout)
        if invite_code:
            await conn.execute(
                """
                UPDATE channel_invites SET use_count = use_count + 1
                WHERE code = $1 AND is_active = true
                  AND (max_uses IS NULL OR use_count < max_uses)
                """,
                invite_code,
            )


async def handle_subscription_renewed(
    stripe_subscription_id: str,
    current_period_end: int,
    amount_cents: int,
) -> None:
    """Called when a channel subscription invoice is paid (renewal)."""
    paid_through = datetime.fromtimestamp(current_period_end, tz=timezone.utc)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT channel_id, user_id FROM channel_members
            WHERE stripe_subscription_id = $1
            """,
            stripe_subscription_id,
        )
        if not row:
            logger.warning("No member found for subscription %s", stripe_subscription_id)
            return

        await conn.execute(
            """
            UPDATE channel_members
            SET subscription_status = 'active', paid_through = $2
            WHERE stripe_subscription_id = $1
            """,
            stripe_subscription_id, paid_through,
        )

        await conn.execute(
            """
            INSERT INTO channel_payment_events (channel_id, user_id, event_type, amount_cents, metadata)
            VALUES ($1, $2, 'payment_success', $3, $4::jsonb)
            """,
            row["channel_id"], row["user_id"], amount_cents,
            __import__("json").dumps({"stripe_subscription_id": stripe_subscription_id}),
        )


async def handle_payment_failed(stripe_subscription_id: str) -> None:
    """Called when a channel subscription payment fails."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT cm.channel_id, cm.user_id, ch.company_id
            FROM channel_members cm
            JOIN channels ch ON ch.id = cm.channel_id
            WHERE cm.stripe_subscription_id = $1
            """,
            stripe_subscription_id,
        )
        if not row:
            return

        await conn.execute(
            """
            UPDATE channel_members SET subscription_status = 'past_due'
            WHERE stripe_subscription_id = $1
            """,
            stripe_subscription_id,
        )

        await conn.execute(
            """
            INSERT INTO channel_payment_events (channel_id, user_id, event_type, metadata)
            VALUES ($1, $2, 'payment_failed', $3::jsonb)
            """,
            row["channel_id"], row["user_id"],
            __import__("json").dumps({"stripe_subscription_id": stripe_subscription_id}),
        )

        # Send notification
        try:
            from ...matcha.services import notification_service as notif_svc
            channel_name = await conn.fetchval("SELECT name FROM channels WHERE id = $1", row["channel_id"])
            await notif_svc.create_notification(
                user_id=row["user_id"],
                company_id=row["company_id"],
                type="channel_payment_failed",
                title=f"Payment failed for #{channel_name}",
                body="Your subscription payment failed. Please update your payment method to keep access.",
                link=f"/work/channels/{row['channel_id']}",
                send_email=True,
            )
        except Exception as e:
            logger.warning("Failed to send payment failure notification: %s", e)


async def handle_subscription_canceled(stripe_subscription_id: str) -> None:
    """Called when a channel subscription is fully canceled/deleted in Stripe."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT channel_id, user_id FROM channel_members WHERE stripe_subscription_id = $1",
            stripe_subscription_id,
        )
        if not row:
            return

        await conn.execute(
            """
            UPDATE channel_members
            SET subscription_status = 'canceled'
            WHERE stripe_subscription_id = $1
            """,
            stripe_subscription_id,
        )

        await conn.execute(
            """
            INSERT INTO channel_payment_events (channel_id, user_id, event_type)
            VALUES ($1, $2, 'subscription_canceled')
            """,
            row["channel_id"], row["user_id"],
        )


async def get_payment_info(channel_id: UUID, user_id: UUID) -> dict:
    """Get payment info for a channel from the perspective of a specific user."""
    async with get_connection() as conn:
        ch = await conn.fetchrow(
            """
            SELECT is_paid, price_cents, currency, inactivity_threshold_days, inactivity_warning_days
            FROM channels WHERE id = $1
            """,
            channel_id,
        )
        if not ch or not ch["is_paid"]:
            return {"is_paid": False}

        member = await conn.fetchrow(
            """
            SELECT subscription_status, paid_through, removed_for_inactivity,
                   removal_cooldown_until, last_contributed_at, inactivity_warned_at
            FROM channel_members
            WHERE channel_id = $1 AND user_id = $2
            """,
            channel_id, user_id,
        )

        now = datetime.now(timezone.utc)
        cooldown_until = None
        can_rejoin = True

        if member and member["removal_cooldown_until"]:
            cooldown_until = member["removal_cooldown_until"].isoformat()
            can_rejoin = member["removal_cooldown_until"] <= now

        # Calculate days until removal
        days_until_removal = None
        if member and member["last_contributed_at"] and ch["inactivity_threshold_days"]:
            deadline = member["last_contributed_at"] + timedelta(days=ch["inactivity_threshold_days"])
            remaining = (deadline - now).total_seconds() / 86400
            if remaining > 0:
                days_until_removal = round(remaining, 1)

        return {
            "is_paid": True,
            "price_cents": ch["price_cents"],
            "currency": ch["currency"],
            "inactivity_threshold_days": ch["inactivity_threshold_days"],
            "inactivity_warning_days": ch["inactivity_warning_days"],
            "is_subscribed": bool(member and member["subscription_status"] == "active"),
            "subscription_status": member["subscription_status"] if member else None,
            "paid_through": member["paid_through"].isoformat() if member and member["paid_through"] else None,
            "can_rejoin": can_rejoin,
            "cooldown_until": cooldown_until,
            "days_until_removal": days_until_removal,
        }


async def get_member_activity(channel_id: UUID) -> list[dict]:
    """Get activity data for all members of a paid channel (owner/mod view)."""
    async with get_connection() as conn:
        ch = await conn.fetchrow(
            "SELECT inactivity_threshold_days, inactivity_warning_days FROM channels WHERE id = $1",
            channel_id,
        )
        threshold = ch["inactivity_threshold_days"] if ch else None
        warning = ch["inactivity_warning_days"] if ch else None

        _name = "COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email)"
        rows = await conn.fetch(
            f"""
            SELECT cm.user_id, cm.role, cm.last_contributed_at, cm.subscription_status,
                   cm.paid_through, cm.removed_for_inactivity, cm.inactivity_warned_at,
                   u.email, {_name} AS name
            FROM channel_members cm
            JOIN users u ON u.id = cm.user_id
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE cm.channel_id = $1
            ORDER BY cm.last_contributed_at DESC NULLS LAST
            """,
            channel_id,
        )

        now = datetime.now(timezone.utc)
        result = []
        for r in rows:
            days_until_removal = None
            status = "active"

            if threshold and r["last_contributed_at"] and r["role"] == "member":
                deadline = r["last_contributed_at"] + timedelta(days=threshold)
                remaining = (deadline - now).total_seconds() / 86400
                days_until_removal = round(remaining, 1)

                if remaining <= 0:
                    status = "expired"
                elif warning and remaining <= warning:
                    status = "warned"
                elif remaining <= threshold * 0.5:
                    status = "at_risk"

            if r["role"] in ("owner", "moderator"):
                status = "exempt"

            result.append({
                "user_id": str(r["user_id"]),
                "name": r["name"],
                "email": r["email"],
                "role": r["role"],
                "last_contributed_at": r["last_contributed_at"].isoformat() if r["last_contributed_at"] else None,
                "subscription_status": r["subscription_status"],
                "days_until_removal": days_until_removal,
                "activity_status": status,
            })

        return result

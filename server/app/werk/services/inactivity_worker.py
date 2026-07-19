"""
Background worker that checks for inactive paid channel members
and issues warnings or removes them based on channel thresholds.
"""

import asyncio
import logging
from datetime import datetime, timezone

from ...database import get_connection
from .channel_payment_service import cancel_subscription_immediately

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 12 * 60 * 60  # 12 hours


async def run_inactivity_checks() -> None:
    """Scan all paid channels with inactivity thresholds and warn/remove idle members."""
    logger.info("Starting inactivity check run")
    warned = 0
    removed = 0
    errors = 0

    # Phase 1: Collect all work items (short DB connection)
    work_items = []
    async with get_connection() as conn:
        channels = await conn.fetch(
            """
            SELECT id, company_id, name, inactivity_threshold_days, inactivity_warning_days
            FROM channels
            WHERE is_paid = true AND inactivity_threshold_days IS NOT NULL
            """
        )

        for ch in channels:
            members = await conn.fetch(
                """
                SELECT
                    user_id, last_contributed_at, inactivity_warned_at,
                    stripe_subscription_id, paid_through,
                    EXTRACT(EPOCH FROM (
                        (last_contributed_at + make_interval(days => $2)) - NOW()
                    )) / 86400.0 AS remaining_days
                FROM channel_members
                WHERE channel_id = $1
                  AND role = 'member'
                  AND removed_for_inactivity IS NOT TRUE
                  AND last_contributed_at IS NOT NULL
                  AND last_contributed_at < NOW() - make_interval(days => $2 - $3)
                """,
                ch["id"],
                ch["inactivity_threshold_days"],
                ch["inactivity_warning_days"] or 0,
            )

            for m in members:
                remaining = m["remaining_days"] or 0
                if remaining <= 0:
                    work_items.append(("remove", ch, m))
                elif m["inactivity_warned_at"] is None:
                    work_items.append(("warn", ch, m))

    # Phase 2: Process each item with its own connection (no long-held conn)
    for action, ch, m in work_items:
        try:
            channel_id = ch["id"]

            if action == "remove":
                # Cancel Stripe subscription first (external call, no DB conn held)
                if m["stripe_subscription_id"]:
                    try:
                        await cancel_subscription_immediately(m["stripe_subscription_id"])
                    except Exception:
                        logger.exception(
                            "Failed to cancel Stripe subscription %s for user %s",
                            m["stripe_subscription_id"], m["user_id"],
                        )

                async with get_connection() as conn:
                    await conn.execute(
                        """
                        UPDATE channel_members
                        SET removed_for_inactivity = true,
                            removal_cooldown_until = COALESCE(paid_through, NOW()) + interval '7 days'
                        WHERE channel_id = $1 AND user_id = $2
                        """,
                        channel_id, m["user_id"],
                    )
                    await conn.execute(
                        """
                        INSERT INTO channel_payment_events
                            (channel_id, user_id, event_type, metadata, created_at)
                        VALUES ($1, $2, 'removed_for_inactivity',
                                jsonb_build_object(
                                    'last_contributed_at', $3::text,
                                    'threshold_days', $4
                                ), NOW())
                        """,
                        channel_id, m["user_id"],
                        str(m["last_contributed_at"]),
                        ch["inactivity_threshold_days"],
                    )

                # Send notification outside DB connection
                try:
                    from ...matcha.services import notification_service as notif_svc
                    await notif_svc.create_notification(
                        user_id=m["user_id"],
                        company_id=ch["company_id"],
                        type="channel_removed_for_inactivity",
                        title=f"Removed from #{ch['name']}",
                        body=(
                            f"You were removed from #{ch['name']} due to "
                            f"{ch['inactivity_threshold_days']} days of inactivity."
                        ),
                        link=f"/work/channels/{channel_id}",
                        send_email=True,
                    )
                except Exception:
                    logger.exception("Failed to send removal notification for user %s", m["user_id"])

                removed += 1

            elif action == "warn":
                async with get_connection() as conn:
                    await conn.execute(
                        """
                        UPDATE channel_members
                        SET inactivity_warned_at = NOW()
                        WHERE channel_id = $1 AND user_id = $2
                        """,
                        channel_id, m["user_id"],
                    )

                remaining = m["remaining_days"] or 0
                days_left = max(1, int(remaining))
                try:
                    from ...matcha.services import notification_service as notif_svc
                    await notif_svc.create_notification(
                        user_id=m["user_id"],
                        company_id=ch["company_id"],
                        type="channel_inactivity_warning",
                        title=f"Inactivity warning for #{ch['name']}",
                        body=(
                            f"You have ~{days_left} day(s) to contribute in "
                            f"#{ch['name']} before being removed for inactivity."
                        ),
                        link=f"/work/channels/{channel_id}",
                        send_email=True,
                    )
                except Exception:
                    logger.exception("Failed to send warning notification for user %s", m["user_id"])

                warned += 1

        except Exception:
            errors += 1
            logger.exception(
                "Error processing inactivity for user %s in channel %s",
                m["user_id"], ch["id"],
            )

    logger.info(
        "Inactivity check complete: warned=%d removed=%d errors=%d",
        warned, removed, errors,
    )


async def _inactivity_loop() -> None:
    """Run inactivity checks on a fixed interval."""
    while True:
        try:
            await run_inactivity_checks()
        except Exception:
            logger.exception("Unhandled error in inactivity check loop")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


async def start_inactivity_scheduler() -> asyncio.Task:
    """Start the background inactivity checker. Call from FastAPI lifespan."""
    logger.info("Starting inactivity scheduler (every %d hours)", CHECK_INTERVAL_SECONDS // 3600)
    task = asyncio.create_task(_inactivity_loop())
    return task

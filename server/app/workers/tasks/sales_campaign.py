"""One durable recipient per task. No automatic replay after an uncertain write."""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID
import httpx
from app.database import connection_or_direct
from app.workers.celery_app import celery_app
from app.matcha.services.matcha_work import sales_service as sales
from app.matcha.services.matcha_work.gmail_service import (
    GmailService,
    GmailSendRateLimited,
)
from app.core.services.email._shared import _is_reserved_test_domain

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.tasks.sales_campaign.send_sales_campaign",
    soft_time_limit=90,
    time_limit=120,
)
def send_sales_campaign(campaign_id, token):
    asyncio.run(deliver_one(UUID(campaign_id), UUID(token)))


async def deliver_one(campaign_id, token, *, gmail_factory=GmailService):
    delay = 15
    async with connection_or_direct() as conn, conn.transaction():
        campaign = await conn.fetchrow(
            "SELECT * FROM mw_sales_campaigns WHERE id = $1 FOR UPDATE", campaign_id
        )
        if (
            not campaign
            or campaign["status"] != "sending"
            or campaign["dispatch_token"] != token
        ):
            return
        try:
            await sales.project_access(
                conn, campaign["project_id"], campaign["user_id"], edit=True
            )
        except sales.SalesError:
            await conn.execute(
                "UPDATE mw_sales_campaigns SET status = 'paused', error = 'Workspace access changed. Delivery paused.' WHERE id = $1",
                campaign_id,
            )
            return
        await sales._stale(conn, campaign_id)
        # Duplicated broker deliveries cannot bypass the pacing or an active claim.
        if campaign["next_attempt_at"] and campaign["next_attempt_at"] > datetime.now(
            timezone.utc
        ):
            delay = max(
                15,
                int(
                    (
                        campaign["next_attempt_at"] - datetime.now(timezone.utc)
                    ).total_seconds()
                )
                + 1,
            )
            item = None
        elif await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM mw_sales_prospects WHERE campaign_id = $1 AND status = 'claimed')",
            campaign_id,
        ):
            delay, item = 60, None
        else:
            item = await conn.fetchrow(
                "SELECT * FROM mw_sales_prospects WHERE campaign_id = $1 AND status = 'approved' ORDER BY created_at,id LIMIT 1 FOR UPDATE",
                campaign_id,
            )
            if not item:
                await conn.execute(
                    "UPDATE mw_sales_campaigns SET status = 'complete', error = NULL, updated_at = NOW() WHERE id = $1",
                    campaign_id,
                )
                return
            await conn.execute(
                "UPDATE mw_sales_prospects SET status = 'claimed', claimed_at = NOW() WHERE id = $1",
                item["id"],
            )
            await conn.execute(
                "UPDATE mw_sales_campaigns SET next_attempt_at = NOW() + INTERVAL '15 seconds', updated_at = NOW() WHERE id = $1",
                campaign_id,
            )
    if item is None:
        await sales.dispatch(campaign_id, token, countdown=delay)
        return

    gmail = gmail_factory(campaign["user_id"])
    # These are preflight checks: no message has left, so pending is safe.
    try:
        status = await gmail.get_status()
        if (
            not status.get("connected")
            or (status.get("email") or "").lower() != campaign["sender"]
        ):
            raise sales.SalesError(
                "The connected Gmail account changed. Reconnect the approved sender, then Resume."
            )
        if _is_reserved_test_domain(item["email"]):
            raise ValueError("Reserved test recipient; no message was sent.")
    except Exception as exc:
        async with connection_or_direct() as conn, conn.transaction():
            await conn.execute(
                "UPDATE mw_sales_prospects SET status = 'approved', claimed_at = NULL WHERE id = $1 AND status = 'claimed'",
                item["id"],
            )
            await conn.execute(
                "UPDATE mw_sales_campaigns SET status = 'paused', error = $2 WHERE id = $1",
                campaign_id,
                str(exc)
                if isinstance(exc, (sales.SalesError, ValueError))
                else "Gmail is unavailable. Reconnect and Resume.",
            )
        return

    outcome, error, message_id = (
        "unknown",
        "Delivery was not acknowledged. Check Gmail Sent; this message will not be retried.",
        None,
    )
    quota = False
    try:
        receipt = await gmail.send_email(
            to=item["email"], subject=item["subject"], body=item["body"]
        )
        if receipt.get("id"):
            outcome, error, message_id = "sent", None, receipt["id"]
    except GmailSendRateLimited as exc:
        # Raised before Gmail writes. Keep the frozen approval and wait for quota.
        outcome, quota = "approved", True
        delay = 60 if "minute" in str(exc) else 3600
        error = str(exc)
    except httpx.HTTPStatusError as exc:
        if 400 <= exc.response.status_code < 500:
            outcome, error = (
                "failed",
                f"Gmail refused delivery (HTTP {exc.response.status_code}). Review before retrying.",
            )
    except ValueError:
        outcome, error = (
            "failed",
            "Gmail rejected this message before delivery. Review its address and subject.",
        )
    except Exception:
        logger.warning(
            "Sales delivery acknowledgment missing: campaign=%s prospect=%s",
            campaign_id,
            item["id"],
        )
    # If this commit fails, the persisted claim remains and later becomes unknown.
    async with connection_or_direct() as conn, conn.transaction():
        await conn.execute(
            """UPDATE mw_sales_prospects SET status = $2, error = $3, message_id = $4,
            sent_at = CASE WHEN $2 = 'sent' THEN NOW() ELSE NULL END
            WHERE id = $1 AND status = 'claimed'""",
            item["id"],
            outcome,
            error,
            message_id,
        )
        if quota:
            await conn.execute(
                "UPDATE mw_sales_campaigns SET next_attempt_at = NOW() + make_interval(secs => $4::double precision), error = $2 WHERE id = $1 AND dispatch_token = $3",
                campaign_id,
                error,
                token,
                float(delay),
            )
        else:
            await conn.execute(
                "UPDATE mw_sales_campaigns SET error = NULL, updated_at = NOW() WHERE id = $1 AND dispatch_token = $2",
                campaign_id,
                token,
            )
    await sales.dispatch(campaign_id, token, countdown=delay)

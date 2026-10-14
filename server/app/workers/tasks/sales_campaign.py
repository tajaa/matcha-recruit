"""One durable recipient per task. No automatic replay after an uncertain write.

An uncertain outcome, or an account-wide Gmail refusal, pauses the campaign so a
provider incident costs at most one unconfirmed message. Campaigns leave part of
the person's Gmail allowance free for their own email.
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4
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

PACE_SECONDS = 15
# Below the Redis broker's default one-hour visibility timeout: a longer ETA is
# redelivered while still pending, and every copy would become another chain.
MAX_COUNTDOWN = 3000
# (counter, campaign share, window). The ceilings themselves are 50 sends/hour and
# 200 recipients/day (gmail_service); the rest stays free for the person's replies.
CAMPAIGN_SHARES = (
    ("gmail_send_3600s", 35, 3600),
    ("gmail_recipients_86400s", 150, 86400),
)
QUOTA_REASONS = {
    "rateLimitExceeded",
    "userRateLimitExceeded",
    "dailyLimitExceeded",
    "quotaExceeded",
}
UNCONFIRMED = "Delivery was not acknowledged. Check Gmail Sent, then mark it sent or not sent."
PAUSED_UNCONFIRMED = "Gmail didn't confirm a message. Check Gmail Sent, mark it sent or not sent, then Resume."
WAITING_FOR_CAPACITY = "Waiting for Gmail capacity. Campaigns leave room for your own email."


def _countdown(seconds):
    return max(1, min(int(seconds), MAX_COUNTDOWN))


def _refusal(response):
    """'quota', 'account' or 'message' for a Gmail 4xx. Nothing was sent."""
    try:
        errors = (response.json().get("error") or {}).get("errors") or []
        reasons = {e.get("reason") for e in errors if isinstance(e, dict)}
    except Exception:
        reasons = set()
    code = response.status_code
    if code == 429 or (code == 403 and reasons & QUOTA_REASONS):
        return "quota"
    if code in (401, 403):
        return "account"
    return "message"


async def _campaign_wait(user_id):
    """Seconds until a campaign may spend more of this person's Gmail allowance."""
    from app.core.services.redis_cache import get_rate_limit_state

    wait = 0
    for action, share, window in CAMPAIGN_SHARES:
        try:
            state = await get_rate_limit_state(str(user_id), action, share, window)
        except Exception:
            state = None
        # No Redis: gmail_service's own ceilings still apply at send time.
        if state and state["used"] >= share:
            wait = max(wait, state["resets_in_seconds"] or window)
    return wait


@celery_app.task(
    name="app.workers.tasks.sales_campaign.send_sales_campaign",
    soft_time_limit=90,
    time_limit=120,
)
def send_sales_campaign(campaign_id, token):
    asyncio.run(deliver_one(UUID(campaign_id), UUID(token)))


@celery_app.task(
    name="app.workers.tasks.sales_campaign.reconcile_sales_campaigns",
    soft_time_limit=90,
    time_limit=120,
)
def reconcile_sales_campaigns():
    asyncio.run(reconcile())


async def _pause(conn, campaign_id, error, token=None):
    await conn.execute(
        "UPDATE mw_sales_campaigns SET status = 'paused', error = $2, updated_at = NOW() WHERE id = $1"
        + (" AND dispatch_token = $3" if token else ""),
        campaign_id,
        error,
        *([token] if token else []),
    )


async def deliver_one(campaign_id, token, *, gmail_factory=GmailService):
    delay = PACE_SECONDS
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
            await _pause(conn, campaign_id, "Workspace access changed. Delivery paused.")
            return
        if await sales._stale(conn, campaign_id):
            await _pause(conn, campaign_id, PAUSED_UNCONFIRMED)
            return
        # Someone who opted out after approval is never contacted.
        await conn.execute(
            """UPDATE mw_sales_prospects p SET status = 'opted_out', error = NULL
            WHERE p.campaign_id = $1 AND p.status = 'approved' AND EXISTS (
                SELECT 1 FROM mw_sales_suppressions s WHERE s.user_id = $2 AND s.email = p.email)""",
            campaign_id,
            campaign["user_id"],
        )
        item = None
        # Duplicated broker deliveries cannot bypass the pacing or an active claim.
        if campaign["next_attempt_at"] and campaign["next_attempt_at"] > datetime.now(
            timezone.utc
        ):
            delay = (
                campaign["next_attempt_at"] - datetime.now(timezone.utc)
            ).total_seconds() + 1
        elif await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM mw_sales_prospects WHERE campaign_id = $1 AND status = 'claimed')",
            campaign_id,
        ):
            delay = 60
        elif wait := await _campaign_wait(campaign["user_id"]):
            delay = wait + 1
            await conn.execute(
                "UPDATE mw_sales_campaigns SET next_attempt_at = NOW() + make_interval(secs => $2::double precision), error = $3 WHERE id = $1",
                campaign_id,
                float(wait),
                WAITING_FOR_CAPACITY,
            )
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
            if _is_reserved_test_domain(item["email"]):
                # Only this recipient is undeliverable; the rest of the batch goes on.
                await conn.execute(
                    "UPDATE mw_sales_prospects SET status = 'failed', error = 'Reserved test address; nothing was sent.' WHERE id = $1",
                    item["id"],
                )
                item, delay = None, 1
            else:
                await conn.execute(
                    "UPDATE mw_sales_prospects SET status = 'claimed', claimed_at = NOW() WHERE id = $1",
                    item["id"],
                )
                await conn.execute(
                    "UPDATE mw_sales_campaigns SET next_attempt_at = NOW() + INTERVAL '15 seconds', updated_at = NOW() WHERE id = $1",
                    campaign_id,
                )
    if item is None:
        await sales.dispatch(campaign_id, token, countdown=_countdown(delay))
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
    except Exception as exc:
        async with connection_or_direct() as conn, conn.transaction():
            await conn.execute(
                "UPDATE mw_sales_prospects SET status = 'approved', claimed_at = NULL WHERE id = $1 AND status = 'claimed'",
                item["id"],
            )
            await _pause(
                conn,
                campaign_id,
                str(exc)
                if isinstance(exc, sales.SalesError)
                else "Gmail is unavailable. Reconnect and Resume.",
            )
        return

    outcome, error, message_id = "unknown", UNCONFIRMED, None
    pause, wait = PAUSED_UNCONFIRMED, None
    try:
        receipt = await gmail.send_email(
            to=item["email"],
            subject=item["subject"],
            body=sales.compose_body(item["body"], campaign["footer"]),
        )
        if receipt.get("id"):
            outcome, error, message_id, pause = "sent", None, receipt["id"], None
    except GmailSendRateLimited as exc:
        # Raised before Gmail writes. Keep the frozen approval and wait for quota.
        outcome, error, pause = "approved", str(exc), None
        wait = 60 if "minute" in str(exc) else 3600
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if 400 <= code < 500:
            # A refusal is definite: nothing went out.
            kind = _refusal(exc.response)
            if kind == "quota":
                outcome, error, pause, wait = (
                    "approved",
                    "Gmail is limiting sends from this account. Waiting before the next message.",
                    None,
                    3600,
                )
            elif kind == "account":
                outcome = "approved"
                error = pause = (
                    f"Gmail refused this account (HTTP {code}). Reconnect Gmail, then Resume."
                )
            else:
                outcome, error, pause = (
                    "failed",
                    f"Gmail refused this message (HTTP {code}). Review before retrying.",
                    None,
                )
    except ValueError:
        outcome, error, pause = (
            "failed",
            "Gmail rejected this message before delivery. Review its address and subject.",
            None,
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
            # Explicit casts: $2 is both the column value and a CASE operand.
            """UPDATE mw_sales_prospects SET status = $2::text, error = $3::text, message_id = $4::text,
            sent_at = CASE WHEN $2::text = 'sent' THEN NOW() ELSE NULL END,
            claimed_at = CASE WHEN $2::text = 'approved' THEN NULL ELSE claimed_at END
            WHERE id = $1 AND status = 'claimed'""",
            item["id"],
            outcome,
            error if outcome != "approved" else None,
            message_id,
        )
        if pause:
            await _pause(conn, campaign_id, pause, token)
        elif wait:
            await conn.execute(
                "UPDATE mw_sales_campaigns SET next_attempt_at = NOW() + make_interval(secs => $4::double precision), error = $2 WHERE id = $1 AND dispatch_token = $3",
                campaign_id,
                error,
                token,
                float(wait),
            )
        else:
            await conn.execute(
                "UPDATE mw_sales_campaigns SET error = NULL, updated_at = NOW() WHERE id = $1 AND dispatch_token = $2",
                campaign_id,
                token,
            )
    if not pause:
        await sales.dispatch(
            campaign_id, token, countdown=_countdown(wait or PACE_SECONDS)
        )


async def reconcile():
    """Worker start: restart every sending queue under a fresh token.

    A killed task, or one dropped while the API ran ahead of the worker, otherwise
    leaves a campaign showing Sending forever. The new token retires any chain
    that survived, so restarts never leave two chains running.
    """
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            "SELECT id FROM mw_sales_campaigns WHERE status = 'sending'"
        )
    for row in rows:
        token = uuid4()
        async with connection_or_direct() as conn, conn.transaction():
            current = await conn.fetchrow(
                "SELECT status FROM mw_sales_campaigns WHERE id = $1 FOR UPDATE",
                row["id"],
            )
            if not current or current["status"] != "sending":
                continue
            if await sales._stale(conn, row["id"]):
                await _pause(conn, row["id"], PAUSED_UNCONFIRMED)
                continue
            await conn.execute(
                "UPDATE mw_sales_campaigns SET dispatch_token = $2 WHERE id = $1",
                row["id"],
                token,
            )
        try:
            await sales.dispatch(row["id"], token)
        except sales.SalesError:
            logger.warning("Sales queue reconcile could not dispatch campaign=%s", row["id"])

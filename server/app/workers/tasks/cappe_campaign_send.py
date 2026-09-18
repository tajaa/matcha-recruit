"""Celery task: send a Cappe newsletter campaign.

On-demand (dispatched via .delay() from the send endpoint, NOT scheduled). The
route marks the campaign 'sending' synchronously; this task does the throttled
per-recipient send and finalizes it to 'sent' with the real recipient count.
Bulk send is kept off the web worker for deliverability + request-lifecycle
reasons.
"""
import asyncio
import logging
import os

from app.cappe.services.campaigns import deliverable_recipients, personalize_unsubscribe

from ..celery_app import celery_app
from ..utils import get_db_connection

logger = logging.getLogger(__name__)

THROTTLE_SECONDS = 0.1


def _unsubscribe_url(slug: str, token: str | None) -> str:
    base = f"https://{os.getenv('CAPPE_BASE_DOMAIN', 'hey-matcha.com')}"
    return f"{base}/api/cappe/public/sites/{slug}/unsubscribe/{token or ''}"


async def _run(campaign_id: str) -> dict:
    from app.core.services.email import EmailService

    conn = await get_db_connection()
    try:
        camp = await conn.fetchrow(
            """SELECT c.id, c.subject, c.body_html, c.from_name, c.status, c.site_id,
                      s.slug, s.name AS site_name
               FROM cappe_campaigns c JOIN cappe_sites s ON s.id = c.site_id
               WHERE c.id = $1""",
            campaign_id,
        )
        if camp is None:
            return {"skipped": True, "reason": "not_found"}
        # Only campaigns the route has staged for sending proceed (avoids a stray
        # re-dispatch re-sending a finished one).
        if camp["status"] != "sending":
            return {"skipped": True, "reason": f"status_{camp['status']}"}

        subs = await conn.fetch(
            "SELECT id, email, name, unsubscribe_token FROM cappe_subscribers "
            "WHERE site_id = $1 AND status = 'subscribed'",
            camp["site_id"],
        )
        recipients = deliverable_recipients(subs)
        # deliverable_recipients() normalizes to {email,name,unsubscribe_token};
        # keep the subscriber id reachable so a failure can be logged without
        # writing the address itself into the log stream.
        subscriber_ids = {
            (s["email"] or "").strip().lower(): s["id"] for s in subs if s["email"]
        }

        email_service = EmailService()
        subject = camp["subject"] or f"News from {camp['site_name']}"
        sent = 0
        failed = 0
        for r in recipients:
            unsub = _unsubscribe_url(camp["slug"], r["unsubscribe_token"])
            html = personalize_unsubscribe(camp["body_html"] or "", unsub)
            text = f"View this message in an HTML email client.\n\nUnsubscribe: {unsub}"
            # The sender reports failure by RETURNING False (both providers
            # down, or a blocked recipient) — it only raises on the unexpected.
            # Reading the return value is what makes failed_count real.
            why = "not delivered"
            try:
                ok = await email_service.send_email_with_fallback(
                    to_email=r["email"], to_name=r["name"], subject=subject,
                    html_content=html, text_content=text,
                )
            except Exception as exc:
                ok = False
                why = type(exc).__name__
            if ok:
                sent += 1
            else:
                # Best-effort per recipient — one bad address must not halt the
                # blast — but never silently: the failure is counted onto the
                # campaign row and logged at WARNING (subscriber id, not the
                # address, so the log line itself carries no PII).
                failed += 1
                logger.warning(
                    "[Cappe Campaign Send] campaign %s: send failed for subscriber %s (%s)",
                    campaign_id, subscriber_ids.get(r["email"]), why,
                )
            await asyncio.sleep(THROTTLE_SECONDS)

        await conn.execute(
            "UPDATE cappe_campaigns SET status = 'sent', sent_at = NOW(), "
            "recipient_count = $1, failed_count = $2, updated_at = NOW() WHERE id = $3",
            sent, failed, campaign_id,
        )
        if failed:
            logger.warning(
                "[Cappe Campaign Send] campaign %s finished with %d/%d failures",
                campaign_id, failed, len(recipients),
            )
        return {"recipients": len(recipients), "sent": sent, "failed": failed}
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=0)
def run_cappe_campaign_send(self, campaign_id: str) -> dict:
    """Deliver a Cappe newsletter campaign to its subscribers."""
    print(f"[Cappe Campaign Send] Sending campaign {campaign_id}...")
    try:
        result = asyncio.run(_run(campaign_id))
        print(f"[Cappe Campaign Send] Completed: {result}")
        return {"status": "success", **result}
    except Exception:
        logger.exception("[Cappe Campaign Send] Failed for campaign %s", campaign_id)
        raise

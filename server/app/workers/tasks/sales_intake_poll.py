"""Poll the dedicated POS Gmail inbox for itemized sales exports."""

import asyncio
import logging

from app.core.feature_flags import merge_company_features
from app.matcha.services.inventory import sales_commit, sales_mailbox, sales_mappings, sales_parse
from app.matcha.services.matcha_work.gmail_service import GmailMailboxService

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_enabled

logger = logging.getLogger(__name__)


async def _run() -> dict:
    conn = await get_db_connection()
    processed = 0
    drafts = 0
    skipped = 0
    try:
        if not await scheduler_enabled(conn, "sales_intake_poll", default=False):
            return {"processed": 0, "drafts": 0, "skipped": 0, "disabled": True}
        mailbox = GmailMailboxService()
        if not mailbox.is_configured:
            logger.warning("sales_intake_poll: POS intake Gmail is not configured")
            return {"processed": 0, "drafts": 0, "skipped": 0, "configured": False}
        source_rows = await conn.fetch(
            "SELECT s.*, lower(s.from_address) AS normalized_from_address, "
            "c.enabled_features, c.signup_source "
            "FROM inventory_sales_sources s "
            "JOIN companies c ON c.id=s.company_id "
            "WHERE s.is_active=TRUE AND c.deleted_at IS NULL"
        )
        sources = {}
        for row in source_rows:
            features = merge_company_features(row["enabled_features"], row["signup_source"])
            if features.get("sales_intake") and features.get("inventory"):
                sources[row["normalized_from_address"]] = row
        for message in await mailbox.fetch_unread():
            source = sources.get(sales_mailbox.sender_address(message.get("from", "")))
            if source is None:
                logger.warning("sales_intake_poll: unregistered sender left unread: %s", message.get("from"))
                skipped += 1
                continue
            subject_match = source["subject_match"]
            if subject_match and subject_match.lower() not in message.get("subject", "").lower():
                skipped += 1
                continue
            attachment = sales_mailbox.select_attachment(message.get("attachments", []))
            if attachment is None:
                skipped += 1
                await mailbox.mark_read(message["id"])
                continue
            try:
                raw = await mailbox.get_attachment(message["id"], attachment["attachment_id"])
                parsed = await sales_parse.parse_sales_file(raw, attachment["mime_type"], attachment["filename"])
                resolved = await sales_mappings.resolve_sold_lines(
                    conn, company_id=source["company_id"], location_id=source["location_id"],
                    lines=parsed["lines"],
                )
                result = await sales_commit.commit_sales_import(
                    conn, company_id=source["company_id"], user_id=None,
                    location_id=source["location_id"], business_date=parsed["business_date"],
                    source="email", filename=attachment["filename"],
                    gmail_message_id=message["id"],
                    lines=resolved,
                    note="POS mailbox import",
                    raw={"business_date": parsed["business_date"], "lines": resolved},
                )
                if result.get("unmapped"):
                    drafts += 1
                else:
                    processed += 1
                await mailbox.mark_read(message["id"])
            except sales_commit.DuplicateSalesPeriodError:
                logger.info("sales_intake_poll: period already committed for message %s", message["id"])
                await mailbox.mark_read(message["id"])
            except Exception:
                logger.exception("sales_intake_poll: message %s failed", message.get("id"))
                # Leave failed messages unread so an operator can retry after
                # repairing the source or parser configuration.
    finally:
        await conn.close()
    return {"processed": processed, "drafts": drafts, "skipped": skipped}


@celery_app.task(bind=True, max_retries=3)
def run_sales_intake_poll(self):
    return asyncio.run(_run())

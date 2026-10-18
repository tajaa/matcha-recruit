"""Read-only, store-scoped setup status for the existing sales intake paths."""

import os
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import get_settings
from app.matcha.services.inventory.pos.square import SquareProvider
from app.matcha.services.scheduling.autopilot.inputs import (
    load_pos_only_sales_by_day,
    load_sales_by_day,
)


async def sales_setup_status(conn, *, company_id: UUID, location_id: UUID, today: date | None = None) -> dict | None:
    location = await conn.fetchrow(
        """SELECT timezone FROM business_locations WHERE id=$1 AND company_id=$2
           AND is_active IS NOT FALSE AND is_company_wide=FALSE""",
        location_id, company_id,
    )
    if location is None:
        return None
    if today is None:
        try:
            today = datetime.now(ZoneInfo(location["timezone"])).date()
        except (TypeError, ZoneInfoNotFoundError, ValueError):
            today = datetime.now(timezone.utc).date()

    # The same two readers used by Autopilot: a connection or a draft import
    # alone is not sales evidence. POS-finalized hourly totals may be evidence
    # before inventory mappings are complete; discarded days stay excluded.
    window = {"company_id": company_id, "location_id": location_id,
              "start": today - timedelta(days=55), "end": today}
    sales = await load_sales_by_day(conn, **window)
    pos_sales = await load_pos_only_sales_by_day(conn, **window)
    dates = set(sales) | set(pos_sales)
    setup = await conn.fetchrow(
        """SELECT
           EXISTS (SELECT 1 FROM inventory_pos_connections p
                   WHERE p.company_id=$1 AND p.provider='square'
                     AND p.status='connected' AND p.secrets <> '{}'::jsonb) AS square_connected,
           EXISTS (SELECT 1 FROM inventory_pos_location_bindings b
                   JOIN inventory_pos_connections p ON p.id=b.connection_id AND p.company_id=b.company_id
                   WHERE b.company_id=$1 AND b.location_id=$2 AND p.provider='square'
                     AND p.status='connected' AND p.secrets <> '{}'::jsonb) AS square_bound,
           EXISTS (SELECT 1 FROM inventory_sales_sources s
                   WHERE s.company_id=$1 AND s.location_id=$2 AND s.is_active=TRUE) AS email_registered,
           (SELECT COUNT(*) FROM inventory_sales_imports
            WHERE company_id=$1 AND location_id=$2 AND status='draft') AS draft_imports""",
        company_id, location_id,
    )
    schedulers = await conn.fetch(
        "SELECT task_key, enabled FROM scheduler_settings WHERE task_key=ANY($1::text[])",
        ["sales_intake_poll", "pos_sales_sync"],
    )
    enabled = {row["task_key"]: bool(row["enabled"]) for row in schedulers}
    settings = get_settings()
    address = os.getenv("POS_INTAKE_GMAIL_ADDRESS", "").strip() or None
    return {
        "location_id": location_id,
        "days_with_sales": len(dates),
        "latest_sales_date": max(dates) if dates else None,
        **dict(setup),
        "square_configured": bool(SquareProvider._CLIENT_ID and SquareProvider._CLIENT_SECRET
                                  and os.getenv("SQUARE_OAUTH_REDIRECT_URI")),
        "square_sync_enabled": enabled.get("pos_sales_sync", False),
        "mailbox_configured": bool(settings.pos_intake_gmail_refresh_token
                                   and settings.pos_intake_gmail_client_id
                                   and settings.pos_intake_gmail_client_secret),
        "mailbox_address": address,
        "email_poll_enabled": enabled.get("sales_intake_poll", False),
    }

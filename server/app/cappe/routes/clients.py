"""Cappe clients — a derived directory of everyone who has interacted with a
site (ordered, booked, subscribed, or messaged), keyed by email. No table: it's
a live roll-up across the existing surfaces so it can never drift."""
from uuid import UUID

from fastapi import APIRouter, Depends

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappeClient
from ._shared import get_owned_site

router = APIRouter()

# Union every touchpoint into (email, name, kind, amount, ts), then aggregate.
_CLIENTS_SQL = """
WITH touch AS (
    SELECT lower(customer_email) AS email, customer_name AS name, 'order' AS kind,
           subtotal_cents AS amount, created_at AS ts
    FROM cappe_orders WHERE site_id = $1 AND customer_email IS NOT NULL
      AND status IN ('paid', 'fulfilled')
    UNION ALL
    SELECT lower(customer_email), customer_name, 'order_pending', 0, created_at
    FROM cappe_orders WHERE site_id = $1 AND customer_email IS NOT NULL
      AND status NOT IN ('paid', 'fulfilled')
    UNION ALL
    SELECT lower(customer_email), customer_name, 'booking', 0, created_at
    FROM cappe_bookings WHERE site_id = $1 AND customer_email IS NOT NULL
    UNION ALL
    SELECT lower(email), name, 'subscriber', 0, created_at
    FROM cappe_subscribers WHERE site_id = $1 AND status = 'subscribed'
    UNION ALL
    SELECT lower(client_email), client_name, 'thread', 0, last_message_at
    FROM cappe_threads WHERE site_id = $1
)
SELECT email,
       (array_agg(name ORDER BY ts DESC) FILTER (WHERE name IS NOT NULL))[1] AS name,
       COUNT(*) FILTER (WHERE kind = 'order') AS orders_count,
       COUNT(*) FILTER (WHERE kind = 'booking') AS bookings_count,
       bool_or(kind = 'subscriber') AS is_subscriber,
       bool_or(kind = 'thread') AS has_thread,
       COALESCE(SUM(amount), 0) AS total_spent_cents,
       MAX(ts) AS last_activity
FROM touch
GROUP BY email
ORDER BY last_activity DESC
"""


@router.get("/sites/{site_id}/clients", response_model=list[CappeClient])
async def list_clients(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(_CLIENTS_SQL, site_id)
    return [
        CappeClient(
            email=r["email"], name=r["name"],
            orders_count=r["orders_count"], bookings_count=r["bookings_count"],
            is_subscriber=r["is_subscriber"], has_thread=r["has_thread"],
            total_spent_cents=int(r["total_spent_cents"] or 0), last_activity=r["last_activity"],
        )
        for r in rows
    ]

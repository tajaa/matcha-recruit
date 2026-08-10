"""Authorization and materialization helpers for Tellus Comms."""
from typing import Literal, Optional
from uuid import UUID

from fastapi import HTTPException, status

from ..models.tellus import TellusAccount, TellusDmThread


async def resolve_inbox_brand(conn, account: TellusAccount, brand_id: Optional[UUID] = None):
    """Resolve a brand owner or inbox-enabled team member."""
    if account.account_type == "brand" and account.brand_id and (
        brand_id is None or brand_id == account.brand_id
    ):
        brand = await conn.fetchrow("SELECT * FROM tellus_brands WHERE id = $1", account.brand_id)
        if brand is not None:
            member = await conn.fetchrow(
                "SELECT * FROM tellus_brand_members WHERE brand_id = $1 AND account_id = $2",
                brand["id"], account.id,
            )
            return dict(brand), dict(member) if member else {"role": "owner", "can_manage_inbox": True}

    rows = await conn.fetch(
        """SELECT b.*, m.id AS member_id, m.role AS member_role,
                  m.can_manage_inbox
             FROM tellus_brand_members m
             JOIN tellus_brands b ON b.id = m.brand_id
            WHERE m.account_id = $1 AND m.can_manage_inbox = TRUE""",
        account.id,
    )
    if brand_id is not None:
        row = next((r for r in rows if r["id"] == brand_id), None)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inbox not found")
        brand = dict(row)
        member = {
            "id": row["member_id"],
            "role": row["member_role"],
            "can_manage_inbox": row["can_manage_inbox"],
        }
        if brand["plan_status"] != "active":
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="This business inbox is unavailable while the plan is inactive.")
        return brand, member
    if len(rows) == 1:
        row = rows[0]
        return dict(row), {"id": row["member_id"], "role": row["member_role"], "can_manage_inbox": True}
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inbox not found")
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Specify brand_id")


async def get_thread_access(conn, thread_id: UUID, account: TellusAccount):
    """Return a thread and caller role without leaking foreign thread IDs."""
    row = await conn.fetchrow(
        """SELECT t.*, b.name AS brand_name, b.slug AS brand_slug,
                  r.title AS report_title, r.report_number, r.review_state,
                  r.publish_at, s.name AS store_name, s.city AS store_city,
                  a.display_name AS assigned_member_name,
                  ca.display_name AS consumer_display_name
             FROM tellus_dm_threads t
             JOIN tellus_brands b ON b.id = t.brand_id
             LEFT JOIN tellus_reports r ON r.id = t.report_id
             LEFT JOIN tellus_stores s ON s.id = t.store_id
             LEFT JOIN tellus_brand_members am ON am.id = t.assigned_member_id
             LEFT JOIN tellus_accounts a ON a.id = am.account_id
             LEFT JOIN tellus_accounts ca ON ca.id = t.consumer_account_id
            WHERE t.id = $1""",
        thread_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    if row["consumer_account_id"] == account.id:
        return dict(row), "consumer"
    if account.account_type == "brand" and row["brand_id"] == account.brand_id:
        return dict(row), "brand"
    membership = await conn.fetchrow(
        "SELECT can_manage_inbox FROM tellus_brand_members WHERE brand_id = $1 AND account_id = $2",
        row["brand_id"], account.id,
    )
    if membership and membership["can_manage_inbox"]:
        plan = await conn.fetchval("SELECT plan_status FROM tellus_brands WHERE id = $1", row["brand_id"])
        if plan != "active":
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="This business inbox is unavailable while the plan is inactive.")
        return dict(row), "brand"
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")


def thread_to_model(row: dict, role: Literal["brand", "consumer"]) -> TellusDmThread:
    return TellusDmThread(
        id=row["id"], report_id=row.get("report_id"),
        counterparty_name=(row.get("brand_name") if role == "consumer" else (row.get("consumer_display_name") or "Reviewer")),
        report_title=row.get("report_title"), report_number=row.get("report_number"),
        review_state=row.get("review_state"), publish_at=row.get("publish_at"),
        blocked=row.get("blocked_at") is not None, unread_count=row.get("unread_count", 0) or 0,
        last_message_at=row["last_message_at"], created_at=row["created_at"],
        kind=row.get("kind", "feedback"), topic=row.get("topic"), status=row.get("status", "waiting_consumer"),
        store_id=row.get("store_id"), store_name=row.get("store_name"), store_city=row.get("store_city"),
        assigned_member_id=row.get("assigned_member_id") if role == "brand" else None,
        assigned_member_name=row.get("assigned_member_name") if role == "brand" else None,
        viewer_role=role, first_brand_response_at=row.get("first_brand_response_at"), closed_at=row.get("closed_at"),
    )


def next_status(sender_role: str) -> str:
    return "waiting_brand" if sender_role == "consumer" else "waiting_consumer"

"""Tell-Us internal admin — cross-brand review moderation queue + DM thread
oversight. The gap feedback.py's own docstring flags: brand-side moderation
can look like a brand suppressing a review it doesn't like; this gives an
admin the cross-tenant view brand.py's require_paid_brand scoping can't."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ....database import get_connection
from ...dependencies import require_tellus_admin
from ...models.tellus import TellusAccount, TellusReport
from .._shared import serialize_report, serialize_reports
from ...services.admin_audit import record_admin_action
from ...services.points_service import notify_account
from ...models.admin import TellusAdminDmThreadSummary, TellusAdminModerationUpdate
from ._shared import report_filter_sql

router = APIRouter(dependencies=[Depends(require_tellus_admin)])


@router.get("/admin/reports")
async def list_reports(
    moderation_status: Optional[str] = None,
    review_state: Optional[str] = None,
    brand_id: Optional[UUID] = None,
    q: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
):
    where, params = report_filter_sql(
        moderation_status=moderation_status, review_state=review_state,
        brand_id=str(brand_id) if brand_id else None, q=q,
    )
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"SELECT r.* FROM tellus_reports r{where} "
            f"ORDER BY r.created_at DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
            *params, limit, offset,
        )
        total = await conn.fetchval(f"SELECT COUNT(*) FROM tellus_reports r{where}", *params)
        reports = await serialize_reports(conn, rows)
        brand_ids = [r["brand_id"] for r in rows if r["brand_id"] is not None]
        brand_names: dict = {}
        if brand_ids:
            brand_rows = await conn.fetch(
                "SELECT id, name FROM tellus_brands WHERE id = ANY($1::uuid[])", brand_ids,
            )
            brand_names = {b["id"]: b["name"] for b in brand_rows}

    items = [
        {**report.model_dump(), "brand_name": brand_names.get(row["brand_id"])}
        for report, row in zip(reports, rows)
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.patch("/admin/reports/{report_id}/moderation", response_model=TellusReport)
async def moderate_report(
    report_id: UUID, body: TellusAdminModerationUpdate,
    admin: TellusAccount = Depends(require_tellus_admin),
):
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT * FROM tellus_reports WHERE id = $1", report_id)
            if row is None:
                raise HTTPException(404, "Report not found")

            updated = await conn.fetchrow(
                "UPDATE tellus_reports SET moderation_status = $2, updated_at = NOW() "
                "WHERE id = $1 RETURNING *",
                report_id, body.moderation_status,
            )

            notifiable = row["review_state"] is not None and row["reporter_account_id"] is not None
            if notifiable and body.moderation_status == "removed" and row["moderation_status"] != "removed":
                await notify_account(
                    conn, row["reporter_account_id"], "review_moderated", "Review removed",
                    "A Tell-Us admin removed your public review for a policy violation.",
                    reference_type="report", reference_id=str(report_id),
                )
            elif notifiable and body.moderation_status == "visible" and row["moderation_status"] == "removed":
                await notify_account(
                    conn, row["reporter_account_id"], "review_moderated", "Review restored",
                    "Your public review was restored by a Tell-Us admin.",
                    reference_type="report", reference_id=str(report_id),
                )

            await record_admin_action(
                conn, admin, "report.moderate", "report", report_id,
                {
                    "from": row["moderation_status"], "to": body.moderation_status,
                    "note": body.note, "brand_id": str(row["brand_id"]) if row["brand_id"] else None,
                },
            )
        return await serialize_report(conn, updated)


@router.get("/admin/dm-threads")
async def list_dm_threads(
    brand_id: Optional[UUID] = None,
    blocked: Optional[bool] = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
):
    clauses: list[str] = []
    params: list = []
    i = 1
    if brand_id:
        clauses.append(f"t.brand_id = ${i}")
        params.append(brand_id)
        i += 1
    if blocked is not None:
        clauses.append("t.blocked_at IS NOT NULL" if blocked else "t.blocked_at IS NULL")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""SELECT t.id, t.report_id, b.name AS brand_name, a.email AS consumer_email,
                       (t.blocked_at IS NOT NULL) AS blocked,
                       (SELECT COUNT(*) FROM tellus_dm_messages m WHERE m.thread_id = t.id) AS message_count,
                       t.last_message_at, t.created_at
                FROM tellus_dm_threads t
                JOIN tellus_brands b ON b.id = t.brand_id
                JOIN tellus_accounts a ON a.id = t.consumer_account_id
                {where}
                ORDER BY t.last_message_at DESC NULLS LAST LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}""",
            *params, limit, offset,
        )
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM tellus_dm_threads t{where}", *params,
        )
    return {
        "items": [TellusAdminDmThreadSummary(**dict(r)) for r in rows],
        "total": total, "limit": limit, "offset": offset,
    }


@router.get("/admin/dm-threads/{thread_id}/messages")
async def get_dm_messages(thread_id: UUID):
    async with get_connection() as conn:
        exists = await conn.fetchval("SELECT 1 FROM tellus_dm_threads WHERE id = $1", thread_id)
        if not exists:
            raise HTTPException(404, "Conversation not found")
        rows = await conn.fetch(
            "SELECT id, thread_id, sender_role, body, created_at, read_at "
            "FROM tellus_dm_messages WHERE thread_id = $1 ORDER BY created_at",
            thread_id,
        )
    return [dict(r) for r in rows]


@router.post("/admin/dm-threads/{thread_id}/block")
async def block_thread(
    thread_id: UUID, admin: TellusAccount = Depends(require_tellus_admin),
):
    async with get_connection() as conn:
        async with conn.transaction():
            result = await conn.execute(
                "UPDATE tellus_dm_threads SET blocked_at = COALESCE(blocked_at, NOW()) WHERE id = $1",
                thread_id,
            )
            if result == "UPDATE 0":
                raise HTTPException(404, "Conversation not found")
            await record_admin_action(conn, admin, "dm_thread.block", "dm_thread", thread_id, None)
    return {"blocked": True}


@router.post("/admin/dm-threads/{thread_id}/unblock")
async def unblock_thread(
    thread_id: UUID, admin: TellusAccount = Depends(require_tellus_admin),
):
    """Admin unblock can override a consumer's own block (tellus_dm_threads
    has no blocked_by column to distinguish who set it) — frontend confirm()
    must say so."""
    async with get_connection() as conn:
        async with conn.transaction():
            result = await conn.execute(
                "UPDATE tellus_dm_threads SET blocked_at = NULL WHERE id = $1", thread_id,
            )
            if result == "UPDATE 0":
                raise HTTPException(404, "Conversation not found")
            await record_admin_action(conn, admin, "dm_thread.unblock", "dm_thread", thread_id, None)
    return {"blocked": False}

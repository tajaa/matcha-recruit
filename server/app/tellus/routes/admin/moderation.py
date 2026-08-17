"""Tell-Us internal admin — cross-brand review moderation queue + DM thread
oversight. The gap feedback.py's own docstring flags: brand-side moderation
can look like a brand suppressing a review it doesn't like; this gives an
admin the cross-tenant view brand.py's require_paid_brand scoping can't."""
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ....database import get_connection
from ...dependencies import require_tellus_admin
from ...models.tellus import BoardModerationStatus, BoardReplyStatus, TellusAccount, TellusReport
from .._shared import serialize_report, serialize_reports
from ...services import board_service as bs
from ...services.admin_audit import record_admin_action
from ...services.points_service import notify_account
from ...models.admin import (
    TellusAdminBoardPostRow,
    TellusAdminBoardReplyRow,
    TellusAdminBoardReplyStatusUpdate,
    TellusAdminDmThreadSummary,
    TellusAdminModerationUpdate,
    TellusAdminAbuseReportUpdate,
)
from ._shared import report_filter_sql

router = APIRouter(dependencies=[Depends(require_tellus_admin)])


@router.get("/admin/abuse-reports")
async def list_abuse_reports(
    report_status: Optional[Literal["open", "reviewing", "actioned", "dismissed"]] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    clauses = ["1 = 1"]
    params = []
    if report_status:
        clauses.append(f"r.status = ${len(params) + 1}")
        params.append(report_status)
    where = " AND ".join(clauses)
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""SELECT r.*, reporter.display_name AS reporter_name,
                       subject.display_name AS subject_name
                  FROM tellus_abuse_reports r
                  JOIN tellus_accounts reporter ON reporter.id = r.reporter_account_id
                  JOIN tellus_accounts subject ON subject.id = r.subject_account_id
                 WHERE {where} ORDER BY r.created_at DESC
                 LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}""",
            *params, limit, offset,
        )
        total = await conn.fetchval(f"SELECT COUNT(*) FROM tellus_abuse_reports r WHERE {where}", *params)
    return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/admin/abuse-reports/{report_id}")
async def get_abuse_report(report_id: UUID):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT r.*, reporter.display_name AS reporter_name, subject.display_name AS subject_name
                 FROM tellus_abuse_reports r
                 JOIN tellus_accounts reporter ON reporter.id = r.reporter_account_id
                 JOIN tellus_accounts subject ON subject.id = r.subject_account_id
                WHERE r.id = $1""",
            report_id,
        )
    if row is None:
        raise HTTPException(404, "Abuse report not found")
    return dict(row)


@router.patch("/admin/abuse-reports/{report_id}")
async def update_abuse_report(
    report_id: UUID,
    body: TellusAdminAbuseReportUpdate,
    admin: TellusAccount = Depends(require_tellus_admin),
):
    async with get_connection() as conn:
        async with conn.transaction():
            old = await conn.fetchrow(
                "SELECT status FROM tellus_abuse_reports WHERE id = $1 FOR UPDATE", report_id,
            )
            if old is None:
                raise HTTPException(404, "Abuse report not found")
            row = await conn.fetchrow(
                """UPDATE tellus_abuse_reports
                      SET status = $2,
                          resolution_note = $3,
                          resolved_at = CASE WHEN $2 IN ('actioned', 'dismissed') THEN NOW() ELSE NULL END,
                          resolved_by = CASE WHEN $2 IN ('actioned', 'dismissed') THEN $4 ELSE NULL END
                    WHERE id = $1 RETURNING *""",
                report_id, body.status, body.resolution_note, admin.id,
            )
            action = "abuse_report.dismiss" if body.status == "dismissed" else (
                "abuse_report.action" if body.status == "actioned" else "abuse_report.review"
            )
            await record_admin_action(
                conn, admin, action, "abuse_report", report_id,
                {"from": old["status"], "to": body.status, "resolution_note": body.resolution_note},
            )
    return dict(row)


@router.get("/admin/reports")
async def list_reports(
    moderation_status: Optional[str] = None,
    review_state: Optional[Literal["published", "held", "withdrawn"]] = None,
    brand_id: Optional[UUID] = None,
    q: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
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
    kind: Optional[Literal["feedback", "general"]] = None,
    thread_status: Optional[Literal["waiting_brand", "waiting_consumer", "closed"]] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
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
    if kind:
        clauses.append(f"t.kind = ${i}"); params.append(kind); i += 1
    if thread_status:
        clauses.append(f"t.status = ${i}"); params.append(thread_status); i += 1
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""SELECT t.id, t.report_id, t.kind, t.topic, t.status,
                       b.name AS brand_name, a.email AS consumer_email,
                       s.name AS store_name, aa.display_name AS assigned_member_name,
                       (t.blocked_at IS NOT NULL) AS blocked,
                       (SELECT COUNT(*) FROM tellus_dm_messages m WHERE m.thread_id = t.id) AS message_count,
                       t.last_message_at, t.created_at
                FROM tellus_dm_threads t
                JOIN tellus_brands b ON b.id = t.brand_id
                JOIN tellus_accounts a ON a.id = t.consumer_account_id
                LEFT JOIN tellus_stores s ON s.id = t.store_id
                LEFT JOIN tellus_brand_members am ON am.id = t.assigned_member_id
                LEFT JOIN tellus_accounts aa ON aa.id = am.account_id
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


# ── Regulars board oversight ─────────────────────────────────────────────────

@router.get("/admin/board-posts", response_model=list[TellusAdminBoardPostRow])
async def admin_list_board_posts(
    brand_id: Optional[UUID] = None,
    moderation_status: Optional[BoardModerationStatus] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    clauses: list[str] = []
    params: list = []
    i = 1
    if brand_id:
        clauses.append(f"bo.brand_id = ${i}")
        params.append(brand_id)
        i += 1
    if moderation_status:
        clauses.append(f"p.moderation_status = ${i}")
        params.append(moderation_status)
        i += 1
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""SELECT p.id, p.board_id, bo.brand_id, b.name AS brand_name, p.kind, p.title,
                       p.moderation_status, a.display_name AS author_display_name, p.created_at
                FROM tellus_board_posts p
                JOIN tellus_boards bo ON bo.id = p.board_id
                JOIN tellus_brands b ON b.id = bo.brand_id
                LEFT JOIN tellus_accounts a ON a.id = p.author_account_id
                {where}
                ORDER BY p.created_at DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}""",
            *params, limit, offset,
        )
    return [TellusAdminBoardPostRow(**dict(r)) for r in rows]


@router.patch("/admin/board-posts/{post_id}/moderation", status_code=204)
async def admin_moderate_board_post(
    post_id: UUID, body: TellusAdminModerationUpdate,
    admin: TellusAccount = Depends(require_tellus_admin),
):
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT moderation_status FROM tellus_board_posts WHERE id = $1", post_id)
            if row is None:
                raise HTTPException(404, "Post not found")
            await conn.execute(
                "UPDATE tellus_board_posts SET moderation_status = $2, updated_at = NOW() WHERE id = $1",
                post_id, body.moderation_status,
            )
            await record_admin_action(
                conn, admin, "board_post.moderate", "board_post", post_id,
                {"from": row["moderation_status"], "to": body.moderation_status, "note": body.note},
            )


@router.get("/admin/board-replies", response_model=list[TellusAdminBoardReplyRow])
async def admin_list_board_replies(
    brand_id: Optional[UUID] = None,
    reply_status: Optional[BoardReplyStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Includes held/rejected — the suppression-oversight view: an admin sees
    what a brand rejected and can force-approve it."""
    clauses: list[str] = []
    params: list = []
    i = 1
    if brand_id:
        clauses.append(f"bo.brand_id = ${i}")
        params.append(brand_id)
        i += 1
    if reply_status:
        clauses.append(f"r.status = ${i}")
        params.append(reply_status)
        i += 1
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""SELECT r.id, r.post_id, p.title AS post_title, bo.brand_id, b.name AS brand_name,
                       a.display_name AS author_display_name, r.body, r.status, r.created_at
                FROM tellus_board_replies r
                JOIN tellus_board_posts p ON p.id = r.post_id
                JOIN tellus_boards bo ON bo.id = p.board_id
                JOIN tellus_brands b ON b.id = bo.brand_id
                JOIN tellus_accounts a ON a.id = r.author_account_id
                {where}
                ORDER BY r.created_at DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}""",
            *params, limit, offset,
        )
    return [
        TellusAdminBoardReplyRow(
            id=r["id"], post_id=r["post_id"], post_title=r["post_title"], brand_id=r["brand_id"],
            brand_name=r["brand_name"], author_display_name=r["author_display_name"] or "Tell-Us member",
            body=r["body"], status=r["status"], created_at=r["created_at"],
        )
        for r in rows
    ]


@router.patch("/admin/board-replies/{reply_id}/status", status_code=204)
async def admin_force_reply_status(
    reply_id: UUID, body: TellusAdminBoardReplyStatusUpdate,
    admin: TellusAccount = Depends(require_tellus_admin),
):
    """Force ANY transition — bypasses board_service.can_reply_transition by
    design. Any →approved transition goes through the same approve_reply_and_award
    core the brand route uses (so points/reason/bypass_cooldown can't drift between
    the two callers, and a reject→re-approve overturn still awards the author's
    points); every other transition is a plain status flip."""
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT status FROM tellus_board_replies WHERE id = $1", reply_id)
            if row is None:
                raise HTTPException(404, "Reply not found")

            if body.status == "approved" and row["status"] != "approved":
                result = await bs.approve_reply_and_award(
                    conn, reply_id, admin.id, board_id=None,
                    from_statuses=("held", "rejected", "removed"),
                )
                if result is None:
                    raise HTTPException(409, "Reply was already moderated")
            else:
                await conn.execute(
                    "UPDATE tellus_board_replies SET status = $2, moderated_at = NOW(), moderated_by = $3 "
                    "WHERE id = $1",
                    reply_id, body.status, admin.id,
                )

            await record_admin_action(
                conn, admin, "board_reply.moderate", "board_reply", reply_id,
                {"from": row["status"], "to": body.status},
            )

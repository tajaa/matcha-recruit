"""Escalated Queries — low-confidence Matcha Work queries for human review."""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.core.models.auth import CurrentUser
from app.matcha.models.dashboard import (
    EscalatedQueryItem,
    EscalatedQueryListResponse,
    ResolveBody,
    DismissBody,
    StatusBody,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class EscalatedQueryDetail(EscalatedQueryItem):
    thread_title: Optional[str] = None
    context_messages: list[dict] = []


@router.get("/escalated-queries", response_model=EscalatedQueryListResponse)
async def list_escalated_queries(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List escalated queries for the user's company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return EscalatedQueryListResponse(items=[], total=0)

    where = "WHERE company_id = $1"
    params: list = [company_id]
    if status_filter:
        where += f" AND status = ${len(params) + 1}"
        params.append(status_filter)

    async with get_connection() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM mw_escalated_queries {where}", *params
        ) or 0

        rows = await conn.fetch(
            f"""SELECT id, status, severity, title, user_query, ai_reply,
                       ai_mode, ai_confidence, missing_fields, resolution_note,
                       resolved_by::text, resolved_at, thread_id::text,
                       linked_record_type, linked_record_id::text, created_at, updated_at
                FROM mw_escalated_queries {where}
                ORDER BY
                  CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                  created_at DESC
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}""",
            *params, limit, offset,
        )

    items = [
        EscalatedQueryItem(
            id=str(r["id"]),
            status=r["status"],
            severity=r["severity"],
            title=r["title"],
            user_query=r["user_query"],
            ai_reply=r["ai_reply"],
            ai_mode=r["ai_mode"],
            ai_confidence=r["ai_confidence"],
            missing_fields=r["missing_fields"],
            resolution_note=r["resolution_note"],
            resolved_by=r["resolved_by"],
            resolved_at=r["resolved_at"],
            thread_id=r["thread_id"],
            linked_record_type=r["linked_record_type"],
            linked_record_id=r["linked_record_id"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]
    return EscalatedQueryListResponse(items=items, total=total)


@router.get("/escalated-queries/{query_id}", response_model=EscalatedQueryDetail)
async def get_escalated_query(
    query_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get an escalated query with surrounding thread context."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT eq.*, t.title AS thread_title
               FROM mw_escalated_queries eq
               LEFT JOIN mw_threads t ON t.id = eq.thread_id
               WHERE eq.id = $1 AND eq.company_id = $2""",
            query_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Escalated query not found")

        # Fetch surrounding messages for context
        messages = await conn.fetch(
            """SELECT id::text, role, content, created_at
               FROM mw_messages
               WHERE thread_id = $1
               ORDER BY created_at ASC
               LIMIT 20""",
            row["thread_id"],
        )

    return EscalatedQueryDetail(
        id=str(row["id"]),
        status=row["status"],
        severity=row["severity"],
        title=row["title"],
        user_query=row["user_query"],
        ai_reply=row["ai_reply"],
        ai_mode=row["ai_mode"],
        ai_confidence=row["ai_confidence"],
        missing_fields=row["missing_fields"],
        resolution_note=row["resolution_note"],
        resolved_by=str(row["resolved_by"]) if row["resolved_by"] else None,
        resolved_at=row["resolved_at"],
        thread_id=str(row["thread_id"]),
        linked_record_type=row["linked_record_type"],
        linked_record_id=str(row["linked_record_id"]) if row["linked_record_id"] else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        thread_title=row["thread_title"],
        context_messages=[dict(m) for m in messages],
    )


@router.put("/escalated-queries/{query_id}/resolve")
async def resolve_escalated_query(
    query_id: UUID,
    body: ResolveBody,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Resolve an escalated query with a resolution note."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """UPDATE mw_escalated_queries
               SET status = 'resolved',
                   resolution_note = $3,
                   resolved_by = $4,
                   resolved_at = NOW(),
                   updated_at = NOW()
               WHERE id = $1 AND company_id = $2 AND status != 'resolved'
               RETURNING thread_id""",
            query_id, company_id, body.resolution_note, current_user.id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Escalated query not found or already resolved")

    # Close the loop — post HR's resolution back into the originating thread so
    # the supervisor actually hears the outcome. Best-effort: a write-back
    # failure must never fail the resolve itself.
    thread_id = row["thread_id"]
    note = (body.resolution_note or "").strip()
    if thread_id and note:
        try:
            from app.matcha.services.matcha_work import matcha_work_document as _doc_svc
            from app.matcha.routes.matcha_work._shared import _row_to_message
            posted = await _doc_svc.add_message(
                thread_id,
                "assistant",
                f"Update from HR review: {note}",
                metadata={"escalation_resolution": {
                    "escalation_id": str(query_id),
                    "resolved_by": str(current_user.id),
                }},
            )
            try:
                from app.matcha.routes.work.thread_ws import thread_manager
                await thread_manager.broadcast_new_message(
                    str(thread_id),
                    [_row_to_message(posted).model_dump(mode="json")],
                )
            except Exception:
                logger.warning("escalation resolution WS broadcast failed for thread %s", thread_id)
        except Exception:
            logger.warning("escalation resolution write-back failed for query %s", query_id, exc_info=True)

    return {"status": "resolved"}


@router.put("/escalated-queries/{query_id}/dismiss")
async def dismiss_escalated_query(
    query_id: UUID,
    body: DismissBody,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Dismiss an escalated query."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        result = await conn.execute(
            """UPDATE mw_escalated_queries
               SET status = 'dismissed',
                   resolution_note = $3,
                   resolved_by = $4,
                   resolved_at = NOW(),
                   updated_at = NOW()
               WHERE id = $1 AND company_id = $2 AND status NOT IN ('resolved', 'dismissed')""",
            query_id, company_id, body.reason, current_user.id,
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Escalated query not found or already closed")

    return {"status": "dismissed"}


@router.put("/escalated-queries/{query_id}/status")
async def update_escalated_query_status(
    query_id: UUID,
    body: StatusBody,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Transition an escalated query to in_review."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        result = await conn.execute(
            """UPDATE mw_escalated_queries
               SET status = $3, updated_at = NOW()
               WHERE id = $1 AND company_id = $2 AND status = 'open'""",
            query_id, company_id, body.status,
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Escalated query not found or not in open status")

    return {"status": body.status}

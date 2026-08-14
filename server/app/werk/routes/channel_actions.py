"""Read-only aggregation of actionable records linked to a channel."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.services.ops.permissions import OpsCapability, resolve_ops_access
from app.werk.services.channel_access import (
    ChannelCapability,
    assert_channel_capability,
    load_channel_access,
)

router = APIRouter()


ActionKind = Literal["event_draft", "event", "event_assignment"]


class ChannelActionOut(BaseModel):
    id: UUID
    kind: ActionKind
    title: str
    summary: str
    status: str
    source_message_id: UUID | None = None
    allowed_actions: list[str]
    href: str | None = None
    created_at: str


class ChannelActionListResponse(BaseModel):
    actions: list[ChannelActionOut]
    total: int


@router.get("/{channel_id}/actions", response_model=ChannelActionListResponse)
async def list_channel_actions(
    channel_id: UUID,
    status: str = Query(default="open"),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: CurrentUser = Depends(get_current_user),
):
    async with get_connection() as conn:
        channel = await conn.fetchrow(
            """
            SELECT company_id,
                   EXISTS(
                       SELECT 1 FROM channel_members cm
                        WHERE cm.channel_id = channels.id
                          AND cm.user_id = $2
                          AND cm.removed_for_inactivity IS NOT TRUE
                   ) AS is_member
              FROM channels
             WHERE id = $1
            """,
            channel_id,
            current_user.id,
        )
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        if not channel["is_member"] and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Channel membership required")

        channel_access = await load_channel_access(
            conn,
            channel_id=channel_id,
            user_id=current_user.id,
            user_role=current_user.role,
        )
        assert_channel_capability(channel_access, ChannelCapability.AUTOMATION)
        if not channel_access.features.get("ems"):
            raise HTTPException(status_code=403, detail="Events are not enabled for this channel")

        access = await resolve_ops_access(
            conn, user=current_user, company_id=channel["company_id"]
        )
        rows: list[dict] = []

        draft_status = "pending" if status == "open" else status
        drafts = await conn.fetch(
            """
            SELECT id, source_message_id, reporter_user_id, narrative,
                   classified, status, created_at
              FROM ems_event_drafts
             WHERE channel_id = $1 AND status = $2
               AND (
                   reporter_user_id = $3
                   OR $4 = true
               )
             ORDER BY created_at DESC
             LIMIT $5
            """,
            channel_id,
            draft_status,
            current_user.id,
            access.allows(OpsCapability.EVENT_REVIEW),
            limit,
        )
        if status in ("open", "pending"):
            for row in drafts:
                rows.append(
                    {
                        "id": row["id"],
                        "kind": "event_draft",
                        "title": "Confirm event draft",
                        "summary": row["narrative"][:240],
                        "status": row["status"],
                        "source_message_id": row["source_message_id"],
                        "allowed_actions": (
                            ["confirm", "reject"]
                            if row["reporter_user_id"] == current_user.id
                            and access.allows(OpsCapability.EVENT_CONFIRM_OWN)
                            else ["confirm", "reject"]
                            if access.allows(OpsCapability.EVENT_REVIEW)
                            else []
                        ),
                        "href": f"/ops/events/drafts/{row['id']}",
                        "created_at": row["created_at"].isoformat(),
                    }
                )

        if status in ("open", "logged", "completed", "dismissed", "promoted"):
            event_status = "logged" if status == "open" else status
            events = await conn.fetch(
                """
                SELECT id, message_id, title, narrative, status, created_at
                  FROM ems_events
                 WHERE channel_id = $1 AND status = $2
                 ORDER BY created_at DESC
                 LIMIT $3
                """,
                channel_id,
                event_status,
                limit,
            )
            if access.allows(OpsCapability.EVENT_REVIEW):
                for row in events:
                    allowed = []
                    if row["status"] == "logged" and access.allows(OpsCapability.EVENT_RESOLVE):
                        allowed.extend(["complete", "no_action"])
                    if row["status"] == "logged" and access.allows(OpsCapability.EVENT_PROMOTE):
                        allowed.append("promote")
                    rows.append(
                        {
                            "id": row["id"],
                            "kind": "event",
                            "title": row["title"] or "Event",
                            "summary": row["narrative"][:240],
                            "status": row["status"],
                            "source_message_id": row["message_id"],
                            "allowed_actions": allowed,
                        "href": f"/ops/events/{row['id']}",
                            "created_at": row["created_at"].isoformat(),
                        }
                    )

        if status in ("open", "assigned", "completed", "cancelled"):
            assignment_status = "assigned" if status == "open" else status
            assignments = await conn.fetch(
                """
                SELECT a.id, a.event_id, a.message_id, a.assignee_user_id, a.assigned_by,
                       a.shared_title, a.instructions, a.due_at, a.status,
                       a.created_at, ev.status AS event_status,
                       COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), ad.name, u.email) AS assignee_name
                  FROM ems_event_assignments a
                  JOIN ems_events ev ON ev.id = a.event_id
                  JOIN users u ON u.id = a.assignee_user_id
                  LEFT JOIN clients c ON c.user_id = u.id
                  LEFT JOIN employees e ON e.user_id = u.id
                  LEFT JOIN admins ad ON ad.user_id = u.id
                 WHERE a.channel_id = $1
                   AND a.status = $2
                   AND ($3 <> 'open' OR ev.status = 'logged')
                 ORDER BY a.created_at DESC
                 LIMIT $4
                 """,
                 channel_id,
                 assignment_status,
                 status,
                 limit,
             )
            for row in assignments:
                allowed: list[str] = []
                if row["status"] == "assigned" and (
                    row["assignee_user_id"] == current_user.id
                    or access.allows(OpsCapability.EVENT_ASSIGN)
                ):
                    allowed.append("complete")
                if row["status"] == "assigned" and access.allows(OpsCapability.EVENT_ASSIGN):
                    allowed.append("cancel")
                rows.append(
                    {
                        "id": row["id"],
                        "kind": "event_assignment",
                        "title": row["shared_title"],
                        "summary": row["instructions"] or f"Assigned to {row['assignee_name']}",
                        "status": row["status"] if row["event_status"] == "logged" else row["event_status"],
                        "source_message_id": row["message_id"],
                        "allowed_actions": allowed,
                        "href": f"/ops/events/{row['event_id']}" if access.allows(OpsCapability.EVENT_REVIEW) else None,
                        "created_at": row["created_at"].isoformat(),
                    }
                )

    rows.sort(key=lambda item: item["created_at"], reverse=True)
    rows = rows[:limit]
    return {"actions": rows, "total": len(rows)}

"""Event-to-channel assignments.

An assignment is a sanitized, auditable delivery of an EMS event into a
team conversation. It deliberately does not mutate ``ems_events.channel_id``
because the originating channel is part of the event's history.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.matcha.services.ops.permissions import (
    OpsAccess,
    OpsCapability,
    assert_ops_capability,
)


class EventAssignmentError(Exception):
    """Base class for assignment domain errors."""


class EventAssignmentNotFound(EventAssignmentError):
    pass


class EventAssignmentForbidden(EventAssignmentError):
    pass


class EventAssignmentConflict(EventAssignmentError):
    pass


@dataclass(frozen=True)
class EventAssignmentCreateResult:
    assignment: dict
    message: dict


def may_complete_event_assignment(
    *,
    assignee_user_id: UUID,
    actor_user_id: UUID,
    access: OpsAccess,
) -> bool:
    """The assignee or an event manager may close the assignment."""
    return actor_user_id == assignee_user_id or access.allows(OpsCapability.EVENT_ASSIGN)


_ASSIGNMENT_SELECT = """
    SELECT a.id, a.company_id, a.event_id, a.channel_id, ch.name AS channel_name,
           a.message_id, a.assignee_user_id,
           COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), ad.name, u.email) AS assignee_name,
           u.email AS assignee_email,
           a.assigned_by, a.shared_title, a.instructions, a.due_at, a.status,
           ev.status AS event_status, a.completed_by, a.completed_at,
           a.created_at, a.updated_at
      FROM ems_event_assignments a
      JOIN ems_events ev ON ev.id = a.event_id
      JOIN channels ch ON ch.id = a.channel_id
      JOIN users u ON u.id = a.assignee_user_id
      LEFT JOIN clients c ON c.user_id = u.id
      LEFT JOIN employees e ON e.user_id = u.id
      LEFT JOIN admins ad ON ad.user_id = u.id
"""


def _clean_text(value: str | None, *, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned[:limit] or None


async def _assignment_row(conn, assignment_id: UUID) -> dict | None:
    row = await conn.fetchrow(
        f"{_ASSIGNMENT_SELECT} WHERE a.id = $1",
        assignment_id,
    )
    return dict(row) if row else None


async def create_event_assignment(
    conn,
    *,
    event_id: UUID,
    actor_user_id: UUID,
    access: OpsAccess,
    channel_id: UUID,
    assignee_user_id: UUID,
    shared_title: str,
    instructions: str | None = None,
    due_at: datetime | None = None,
    client_request_id: UUID | None = None,
) -> EventAssignmentCreateResult:
    """Create the assignment and its system message in one transaction.

    The caller must already hold a transaction. The message is intentionally
    a fallback-readable system message; the metadata pointer is authoritative
    for action cards and status refreshes.
    """

    assert_ops_capability(access, OpsCapability.EVENT_ASSIGN)
    if access.company_id is None:
        raise EventAssignmentForbidden("Event assignment requires a company scope")

    event = await conn.fetchrow(
        """
        SELECT id, company_id, status
          FROM ems_events
         WHERE id = $1
         FOR UPDATE
        """,
        event_id,
    )
    if not event or event["company_id"] != access.company_id:
        raise EventAssignmentNotFound("Event not found")
    if event["status"] != "logged":
        raise EventAssignmentConflict(
            f"Event is already {event['status']} and cannot receive a new assignment"
        )

    channel = await conn.fetchrow(
        """
        SELECT id, company_id, name, is_archived
          FROM channels
         WHERE id = $1
        """,
        channel_id,
    )
    if not channel or channel["company_id"] != access.company_id:
        raise EventAssignmentForbidden("Assignment channel must belong to the event company")
    if channel["is_archived"]:
        raise EventAssignmentConflict("Archived channels cannot receive event assignments")

    actor_member = await conn.fetchval(
        """
        SELECT 1
          FROM channel_members
         WHERE channel_id = $1 AND user_id = $2
           AND removed_for_inactivity IS NOT TRUE
        """,
        channel_id,
        actor_user_id,
    )
    if not actor_member:
        raise EventAssignmentForbidden("You must be an active member of the target channel")

    assignee = await conn.fetchrow(
        """
        SELECT u.id, u.email,
               COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), ad.name, u.email) AS name
          FROM channel_members cm
          JOIN users u ON u.id = cm.user_id
          LEFT JOIN clients c ON c.user_id = u.id
          LEFT JOIN employees e ON e.user_id = u.id
          LEFT JOIN admins ad ON ad.user_id = u.id
         WHERE cm.channel_id = $1 AND cm.user_id = $2
           AND cm.removed_for_inactivity IS NOT TRUE
        """,
        channel_id,
        assignee_user_id,
    )
    if not assignee:
        raise EventAssignmentForbidden("Assignee must be an active member of the target channel")

    existing = await conn.fetchrow(
        """
        SELECT id
          FROM ems_event_assignments
         WHERE event_id = $1 AND channel_id = $2
           AND assignee_user_id = $3 AND status = 'assigned'
        """,
        event_id,
        channel_id,
        assignee_user_id,
    )
    if existing:
        raise EventAssignmentConflict("This teammate already has an open assignment for this event")

    title = _clean_text(shared_title, limit=300)
    if not title:
        raise EventAssignmentConflict("Assignment title is required")
    note = _clean_text(instructions, limit=4000)

    assignment = await conn.fetchrow(
        """
        INSERT INTO ems_event_assignments (
            company_id, event_id, channel_id, assignee_user_id, assigned_by,
            shared_title, instructions, due_at, client_request_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id
        """,
        access.company_id,
        event_id,
        channel_id,
        assignee_user_id,
        actor_user_id,
        title,
        note,
        due_at,
        client_request_id,
    )
    if not assignment:
        raise EventAssignmentConflict("Could not create event assignment")

    assignment_id = assignment["id"]
    email_handle = str(assignee["email"] or "teammate").split("@", 1)[0]
    content = f"Event assigned to @{email_handle}: {title}"
    if note:
        content = f"{content}\n{note}"
    metadata = {
        "action": {
            "kind": "event_assignment",
            "id": str(assignment_id),
            "status": "assigned",
        }
    }
    message = await conn.fetchrow(
        """
        INSERT INTO channel_messages
            (channel_id, sender_id, content, message_type, metadata)
        VALUES ($1, NULL, $2, 'system', $3::jsonb)
        RETURNING id, channel_id, content, message_type, metadata, created_at
        """,
        channel_id,
        content,
        json.dumps(metadata),
    )
    if not message:
        raise EventAssignmentConflict("Could not create assignment channel message")

    await conn.execute(
        """
        UPDATE ems_event_assignments
           SET message_id = $2, updated_at = NOW()
         WHERE id = $1
        """,
        assignment_id,
        message["id"],
    )
    await conn.execute(
        """
        INSERT INTO ems_event_audit_log (event_id, user_id, action, details)
        VALUES ($1, $2, 'assignment_created', $3::jsonb)
        """,
        event_id,
        actor_user_id,
        json.dumps({
            "assignment_id": str(assignment_id),
            "channel_id": str(channel_id),
            "assignee_user_id": str(assignee_user_id),
            "due_at": due_at.isoformat() if due_at else None,
        }),
    )

    row = await _assignment_row(conn, assignment_id)
    if not row:
        raise EventAssignmentConflict("Assignment disappeared before commit")
    return EventAssignmentCreateResult(assignment=row, message=dict(message))


async def complete_event_assignment(
    conn,
    *,
    assignment_id: UUID,
    actor_user_id: UUID,
    access: OpsAccess,
) -> dict:
    row = await conn.fetchrow(
        f"{_ASSIGNMENT_SELECT} WHERE a.id = $1 FOR UPDATE",
        assignment_id,
    )
    if not row:
        raise EventAssignmentNotFound("Event assignment not found")
    if row["company_id"] != access.company_id:
        raise EventAssignmentNotFound("Event assignment not found")
    if not may_complete_event_assignment(
        assignee_user_id=row["assignee_user_id"],
        actor_user_id=actor_user_id,
        access=access,
    ):
        raise EventAssignmentForbidden("Only the assignee or an event manager can complete this assignment")
    if row["status"] != "assigned":
        raise EventAssignmentConflict(f"Assignment is already {row['status']}")

    updated = await conn.fetchrow(
        """
        UPDATE ems_event_assignments
           SET status = 'completed', completed_by = $2, completed_at = NOW(), updated_at = NOW()
         WHERE id = $1 AND status = 'assigned'
        RETURNING id
        """,
        assignment_id,
        actor_user_id,
    )
    if not updated:
        raise EventAssignmentConflict("Assignment was changed by another user")
    await conn.execute(
        """
        INSERT INTO ems_event_audit_log (event_id, user_id, action, details)
        VALUES ($1, $2, 'assignment_completed', $3::jsonb)
        """,
        row["event_id"],
        actor_user_id,
        json.dumps({"assignment_id": str(assignment_id)}),
    )
    result = await _assignment_row(conn, assignment_id)
    if not result:
        raise EventAssignmentNotFound("Event assignment not found")
    return result


async def cancel_event_assignment(
    conn,
    *,
    assignment_id: UUID,
    actor_user_id: UUID,
    access: OpsAccess,
) -> dict:
    assert_ops_capability(access, OpsCapability.EVENT_ASSIGN)
    row = await conn.fetchrow(
        f"{_ASSIGNMENT_SELECT} WHERE a.id = $1 FOR UPDATE",
        assignment_id,
    )
    if not row or row["company_id"] != access.company_id:
        raise EventAssignmentNotFound("Event assignment not found")
    if row["status"] != "assigned":
        raise EventAssignmentConflict(f"Assignment is already {row['status']}")
    await conn.execute(
        """
        UPDATE ems_event_assignments
           SET status = 'cancelled', updated_at = NOW()
         WHERE id = $1 AND status = 'assigned'
        """,
        assignment_id,
    )
    await conn.execute(
        """
        INSERT INTO ems_event_audit_log (event_id, user_id, action, details)
        VALUES ($1, $2, 'assignment_cancelled', $3::jsonb)
        """,
        row["event_id"],
        actor_user_id,
        json.dumps({"assignment_id": str(assignment_id)}),
    )
    result = await _assignment_row(conn, assignment_id)
    if not result:
        raise EventAssignmentNotFound("Event assignment not found")
    return result


async def list_event_assignments(conn, *, event_id: UUID, company_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        f"{_ASSIGNMENT_SELECT} WHERE a.event_id = $1 AND a.company_id = $2 ORDER BY a.created_at DESC",
        event_id,
        company_id,
    )
    return [dict(row) for row in rows]


async def get_event_assignment(conn, *, assignment_id: UUID) -> dict | None:
    return await _assignment_row(conn, assignment_id)

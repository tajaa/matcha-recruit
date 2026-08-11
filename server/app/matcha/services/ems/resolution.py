"""Atomic EMS event completion and no-action resolution."""

from __future__ import annotations

import json
from typing import Literal
from uuid import UUID

from app.matcha.services.matcha_work.work_permissions import (
    WorkAccess,
    WorkCapability,
    assert_work_capability,
)


EventResolution = Literal["completed", "no_action"]


class EventResolutionError(Exception):
    pass


class EventResolutionNotFound(EventResolutionError):
    pass


class EventResolutionConflict(EventResolutionError):
    pass


async def resolve_event(
    conn,
    *,
    company_id: UUID,
    event_id: UUID,
    actor_user_id: UUID,
    access: WorkAccess,
    resolution: EventResolution,
    note: str | None = None,
    resolution_code: str | None = None,
    duplicate_of_event_id: UUID | None = None,
) -> dict:
    if access.company_id != company_id:
        raise EventResolutionNotFound("Event not found")
    assert_work_capability(access, WorkCapability.EVENT_RESOLVE)

    row = await conn.fetchrow(
        """
        SELECT id, company_id, status
          FROM ems_events
         WHERE id = $1 AND company_id = $2
         FOR UPDATE
        """,
        event_id,
        company_id,
    )
    if not row:
        raise EventResolutionNotFound("Event not found")
    if row["status"] != "logged":
        raise EventResolutionConflict(
            f"Event is already {row['status']}, not logged"
        )

    if duplicate_of_event_id is not None:
        duplicate_exists = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM ems_events
                 WHERE id = $1 AND company_id = $3 AND id <> $2
            )
            """,
            duplicate_of_event_id,
            event_id,
            company_id,
        )
        if not duplicate_exists:
            raise EventResolutionError("Duplicate event must exist in this company")
        if duplicate_of_event_id == event_id:
            raise EventResolutionError("An event cannot duplicate itself")

    stored_status = "completed" if resolution == "completed" else "dismissed"
    stored_code = resolution_code or ("handled" if resolution == "completed" else "not_event")
    updated = await conn.fetchrow(
        """
        UPDATE ems_events
           SET status = $3,
               resolved_by = $4,
               resolved_at = NOW(),
               resolution_note = $5,
               resolution_code = $6,
               duplicate_of_event_id = $7,
               updated_at = NOW()
         WHERE id = $1 AND company_id = $2 AND status = 'logged'
        RETURNING id, company_id, status, resolved_by, resolved_at,
                  resolution_note, resolution_code, duplicate_of_event_id
        """,
        event_id,
        company_id,
        stored_status,
        actor_user_id,
        (note or "").strip()[:2000] or None,
        stored_code,
        duplicate_of_event_id,
    )
    if not updated:
        raise EventResolutionConflict("Event was changed by another reviewer")
    await conn.execute(
        """
        INSERT INTO ems_event_audit_log (event_id, user_id, action, details)
        VALUES ($1, $2, $3, $4::jsonb)
        """,
        event_id,
        actor_user_id,
        resolution,
        json.dumps(
            {
                "status": stored_status,
                "resolution_code": stored_code,
                "duplicate_of_event_id": (
                    str(duplicate_of_event_id) if duplicate_of_event_id else None
                ),
            }
        ),
    )
    return dict(updated)

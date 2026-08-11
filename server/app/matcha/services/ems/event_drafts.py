"""Persistence and authorization for confirm-before-create EMS drafts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.matcha.services.ems.event_intake import persist_event
from app.matcha.services.matcha_work.work_permissions import (
    WorkAccess,
    WorkCapability,
)


class EventDraftError(Exception):
    """Base class for domain errors that routes translate to HTTP responses."""


class EventDraftNotFound(EventDraftError):
    pass


class EventDraftForbidden(EventDraftError):
    pass


class EventDraftConflict(EventDraftError):
    pass


@dataclass(frozen=True)
class DraftDecisionResult:
    draft: dict
    event: dict | None
    changed: bool


def _decode_json(value: Any) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return {}
    return value if isinstance(value, dict) else {}


def may_decide_event_draft(
    *,
    reporter_user_id: UUID | None,
    actor_user_id: UUID,
    access: WorkAccess,
) -> bool:
    if access.company_id is None:
        return False
    if access.allows(WorkCapability.EVENT_REVIEW):
        return True
    return (
        reporter_user_id is not None
        and reporter_user_id == actor_user_id
        and access.allows(WorkCapability.EVENT_CONFIRM_OWN)
    )


async def get_event_draft(conn, *, draft_id: UUID, company_id: UUID) -> dict | None:
    row = await conn.fetchrow(
        """
        SELECT id, company_id, channel_id, source_message_id,
               confirmation_message_id, reporter_user_id, location_id,
               narrative, classified, urgency, status, event_id,
               decided_by, decided_at, expires_at, created_at, updated_at
          FROM ems_event_drafts
         WHERE id = $1 AND company_id = $2
        """,
        draft_id,
        company_id,
    )
    return dict(row) if row else None


async def create_event_draft(
    conn,
    *,
    company_id: UUID,
    channel_id: UUID,
    source_message_id: UUID,
    reporter_user_id: UUID,
    narrative: str,
    classified: dict,
    location_id: UUID | None = None,
) -> dict | None:
    """Create one draft, returning ``None`` for a replay of the source message."""

    narrative = narrative[:4000]
    row = await conn.fetchrow(
        """
        INSERT INTO ems_event_drafts (
            company_id, channel_id, source_message_id, reporter_user_id,
            location_id, narrative, classified, urgency
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
        ON CONFLICT (source_message_id) DO NOTHING
        RETURNING id, company_id, channel_id, source_message_id,
                  confirmation_message_id, reporter_user_id, location_id,
                  narrative, classified, urgency, status, event_id,
                  decided_by, decided_at, expires_at, created_at, updated_at
        """,
        company_id,
        channel_id,
        source_message_id,
        reporter_user_id,
        location_id,
        narrative,
        json.dumps(classified),
        classified.get("urgency"),
    )
    return dict(row) if row else None


async def set_confirmation_message(
    conn,
    *,
    draft_id: UUID,
    company_id: UUID,
    confirmation_message_id: UUID,
) -> dict | None:
    row = await conn.fetchrow(
        """
        UPDATE ems_event_drafts
           SET confirmation_message_id = $3, updated_at = NOW()
         WHERE id = $1 AND company_id = $2 AND status = 'pending'
        RETURNING id, company_id, channel_id, source_message_id,
                  confirmation_message_id, reporter_user_id, location_id,
                  narrative, classified, urgency, status, event_id,
                  decided_by, decided_at, expires_at, created_at, updated_at
        """,
        draft_id,
        company_id,
        confirmation_message_id,
    )
    return dict(row) if row else None


async def confirm_event_draft(
    conn,
    *,
    draft_id: UUID,
    actor_user_id: UUID,
    access: WorkAccess,
) -> DraftDecisionResult:
    """Confirm a draft and create its final event atomically.

    The caller must already be inside a transaction. The row lock makes
    confirm/reject races deterministic and preserves idempotent retries.
    """

    row = await conn.fetchrow(
        """
        SELECT id, company_id, channel_id, source_message_id,
               confirmation_message_id, reporter_user_id, location_id,
               narrative, classified, urgency, status, event_id,
               decided_by, decided_at, expires_at, created_at, updated_at
          FROM ems_event_drafts
         WHERE id = $1
         FOR UPDATE
        """,
        draft_id,
    )
    if not row:
        raise EventDraftNotFound("Event draft not found")
    draft = dict(row)
    if draft["company_id"] != access.company_id:
        raise EventDraftForbidden("Draft belongs to another company")
    if not may_decide_event_draft(
        reporter_user_id=draft["reporter_user_id"],
        actor_user_id=actor_user_id,
        access=access,
    ):
        raise EventDraftForbidden("You do not have permission to confirm this event draft")

    if draft["status"] == "confirmed":
        event = None
        if draft["event_id"]:
            event = await conn.fetchrow(
                "SELECT * FROM ems_events WHERE id = $1", draft["event_id"]
            )
        return DraftDecisionResult(draft=draft, event=dict(event) if event else None, changed=False)
    if draft["status"] != "pending":
        raise EventDraftConflict(f"Event draft is already {draft['status']}")

    expired = await conn.fetchval(
        "SELECT expires_at <= NOW() FROM ems_event_drafts WHERE id = $1",
        draft_id,
    )
    if expired:
        await conn.execute(
            """
            UPDATE ems_event_drafts
               SET status = 'expired', updated_at = NOW()
             WHERE id = $1 AND status = 'pending'
            """,
            draft_id,
        )
        raise EventDraftConflict("Event draft has expired")

    classified = _decode_json(draft["classified"])
    event, _confirmation = await persist_event(
        conn,
        company_id=draft["company_id"],
        channel_id=draft["channel_id"],
        message_id=draft["source_message_id"],
        reporter_user_id=draft["reporter_user_id"] or actor_user_id,
        content=draft["narrative"],
        classified=classified,
        location_id=draft["location_id"],
    )
    if event is None:
        raise EventDraftConflict("The source message already has an event")

    updated = await conn.fetchrow(
        """
        UPDATE ems_event_drafts
           SET status = 'confirmed', event_id = $2,
               decided_by = $3, decided_at = NOW(), updated_at = NOW()
         WHERE id = $1 AND status = 'pending'
        RETURNING id, company_id, channel_id, source_message_id,
                  confirmation_message_id, reporter_user_id, location_id,
                  narrative, classified, urgency, status, event_id,
                  decided_by, decided_at, expires_at, created_at, updated_at
        """,
        draft_id,
        event["id"],
        actor_user_id,
    )
    if not updated:
        raise EventDraftConflict("Event draft changed while confirming")
    await conn.execute(
        """
        INSERT INTO ems_event_audit_log (event_id, user_id, action, details)
        VALUES ($1, $2, 'confirmed', $3::jsonb)
        """,
        event["id"],
        actor_user_id,
        json.dumps({"draft_id": str(draft_id)}),
    )
    return DraftDecisionResult(draft=dict(updated), event=event, changed=True)


async def reject_event_draft(
    conn,
    *,
    draft_id: UUID,
    actor_user_id: UUID,
    access: WorkAccess,
    reason: str | None = None,
) -> DraftDecisionResult:
    row = await conn.fetchrow(
        """
        SELECT id, company_id, channel_id, source_message_id,
               confirmation_message_id, reporter_user_id, location_id,
               narrative, classified, urgency, status, event_id,
               decided_by, decided_at, expires_at, created_at, updated_at
          FROM ems_event_drafts
         WHERE id = $1
         FOR UPDATE
        """,
        draft_id,
    )
    if not row:
        raise EventDraftNotFound("Event draft not found")
    draft = dict(row)
    if draft["company_id"] != access.company_id:
        raise EventDraftForbidden("Draft belongs to another company")
    if not may_decide_event_draft(
        reporter_user_id=draft["reporter_user_id"],
        actor_user_id=actor_user_id,
        access=access,
    ):
        raise EventDraftForbidden("You do not have permission to reject this event draft")
    if draft["status"] == "rejected":
        return DraftDecisionResult(draft=draft, event=None, changed=False)
    if draft["status"] != "pending":
        raise EventDraftConflict(f"Event draft is already {draft['status']}")

    updated = await conn.fetchrow(
        """
        UPDATE ems_event_drafts
           SET status = 'rejected', decided_by = $2,
               decided_at = NOW(), updated_at = NOW(),
               classified = classified || jsonb_build_object('rejection_reason', $3::text)
         WHERE id = $1 AND status = 'pending'
        RETURNING id, company_id, channel_id, source_message_id,
                  confirmation_message_id, reporter_user_id, location_id,
                  narrative, classified, urgency, status, event_id,
                  decided_by, decided_at, expires_at, created_at, updated_at
        """,
        draft_id,
        actor_user_id,
        (reason or "").strip()[:2000],
    )
    if not updated:
        raise EventDraftConflict("Event draft changed while rejecting")
    return DraftDecisionResult(draft=dict(updated), event=None, changed=True)

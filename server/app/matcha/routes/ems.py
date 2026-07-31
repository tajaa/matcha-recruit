"""EMS (Event Management System) router — review + promote "@huume"-logged
channel events. Mounted under /ems, gated on the `ems` feature flag at
mount time (see routes/__init__.py); promotion additionally requires
`incidents` (checked in evaluate_promote, not at mount, since a company can
have ems without incidents).
"""

import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.ems import (
    EmsEventListResponse, EmsEventOut, EmsEventUpdate, PromoteRequest, PromoteResponse,
)
from app.matcha.services.ems import categories
from app.matcha.services.ems.event_intake import coerce_doc
from app.matcha.services.ems.promote import PromoteRaceError, evaluate_promote, promote_event
from app.matcha.services.ems.queries import EVENT_SELECT as _EVENT_SELECT, _NAME_EXPR  # noqa: F401

logger = logging.getLogger(__name__)

router = APIRouter()


def _row_to_event(row) -> EmsEventOut:
    doc = row["doc"]
    if isinstance(doc, str):
        doc = json.loads(doc) if doc else {}
    return EmsEventOut(**{**dict(row), "doc": doc or {}})


@router.get("/events", response_model=EmsEventListResponse)
async def list_events(
    status: Optional[str] = None,
    category: Optional[str] = None,
    channel_id: Optional[UUID] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    if not company_id:
        raise HTTPException(status_code=400, detail="No company associated with this account")
    if status is not None and status not in ("logged", "promoted", "dismissed"):
        raise HTTPException(status_code=400, detail="Invalid status")
    if category is not None and category not in categories.ALL_KEYS:
        raise HTTPException(status_code=400, detail="Invalid category")

    where = ["ev.company_id = $1"]
    params: list = [company_id]
    if status:
        params.append(status)
        where.append(f"ev.status = ${len(params)}")
    if category:
        params.append(category)
        where.append(f"ev.category = ${len(params)}")
    if channel_id:
        params.append(channel_id)
        where.append(f"ev.channel_id = ${len(params)}")

    async with get_connection() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM ems_events ev WHERE {' AND '.join(where)}", *params,
        )
        params_with_paging = [*params, limit, offset]
        rows = await conn.fetch(
            f"{_EVENT_SELECT} WHERE {' AND '.join(where)} "
            f"ORDER BY ev.created_at DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
            *params_with_paging,
        )
    return EmsEventListResponse(events=[_row_to_event(r) for r in rows], total=total or 0)


@router.get("/events/{event_id}", response_model=EmsEventOut)
async def get_event(
    event_id: UUID,
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"{_EVENT_SELECT} WHERE ev.id = $1 AND ev.company_id = $2", event_id, company_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    return _row_to_event(row)


@router.put("/events/{event_id}", response_model=EmsEventOut)
async def update_event(
    event_id: UUID,
    body: EmsEventUpdate,
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    sent = body.model_fields_set
    if "category" in sent and (
        body.category is None or body.category not in categories.ALL_KEYS
    ):
        # category is NOT NULL in ems_events — an explicit null is not a
        # "clear", it's invalid input (unlike the nullable true-PATCH columns).
        raise HTTPException(status_code=400, detail="Invalid category")

    dismiss_requested = "dismissed" in sent and bool(body.dismissed)

    async with get_connection() as conn:
        if dismiss_requested:
            # A promoted event must not be silently flipped to dismissed
            # (it would leave a "dismissed" event pointing at a live IR
            # incident) — mirror promote_event's own status='logged' guard.
            current_status = await conn.fetchval(
                "SELECT status FROM ems_events WHERE id = $1 AND company_id = $2",
                event_id, company_id,
            )
            if current_status is None:
                raise HTTPException(status_code=404, detail="Event not found")
            if current_status != "logged":
                raise HTTPException(
                    status_code=409, detail=f"Event is already {current_status}, not logged.",
                )

        # Column/value pairs are appended as parameterized placeholders —
        # never string-sniffed — so a `title` of literally "NOW()" can't be
        # mistaken for the SQL literal used for dismissed_at below.
        set_parts: list[str] = []
        params: list = [event_id, company_id]

        def _set(column: str, value) -> None:
            params.append(value)
            set_parts.append(f"{column} = ${len(params)}")

        classification_edited = bool({"title", "category", "doc"} & sent)
        if "title" in sent:
            _set("title", body.title)
        if "category" in sent:
            _set("category", body.category)
        if "doc" in sent:
            _set("doc", json.dumps(coerce_doc(body.doc)))
        if classification_edited:
            # An admin's manual edit must win over a clarify answer that
            # arrives later — apply_refinement only rewrites classification
            # columns WHERE status='logged', not WHERE clarify_message_id IS
            # NULL, so a still-outstanding question would otherwise let a
            # stale reply silently overwrite this edit. Disarming it here
            # leaves the question as a dangling system-message pill (a
            # reply to it just falls through apply_refinement's atomic
            # claim as a miss) rather than a race the admin can lose.
            set_parts.append("clarify_message_id = NULL")
        if dismiss_requested:
            _set("status", "dismissed")
            _set("dismissed_by", current_user.id)
            set_parts.append("dismissed_at = NOW()")

        if set_parts:
            where = "WHERE id = $1 AND company_id = $2"
            if dismiss_requested:
                where += " AND status = 'logged'"
            updated = await conn.fetchval(
                f"UPDATE ems_events SET {', '.join(set_parts)}, updated_at = NOW() "
                f"{where} RETURNING id",
                *params,
            )
            if not updated:
                if dismiss_requested:
                    # Status flipped (promote/dismiss race) between the
                    # check above and this UPDATE.
                    raise HTTPException(
                        status_code=409,
                        detail="Event was promoted or dismissed by someone else — refresh and retry.",
                    )
                raise HTTPException(status_code=404, detail="Event not found")
            await conn.execute(
                "INSERT INTO ems_event_audit_log (event_id, user_id, action, details) "
                "VALUES ($1, $2, 'updated', $3::jsonb)",
                event_id, current_user.id, json.dumps({"fields": list(sent)}),
            )
        row = await conn.fetchrow(
            f"{_EVENT_SELECT} WHERE ev.id = $1 AND ev.company_id = $2", event_id, company_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    return _row_to_event(row)


@router.post("/events/{event_id}/promote", response_model=PromoteResponse)
async def promote(
    event_id: UUID,
    body: PromoteRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"{_EVENT_SELECT} WHERE ev.id = $1 AND ev.company_id = $2", event_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Event not found")
        event = dict(row)

        from app.core.feature_flags import get_company_features
        features = await get_company_features(company_id, conn=conn)
        verdict = evaluate_promote(role=current_user.role, features=features, event_status=event["status"])
        if not verdict.ok:
            raise HTTPException(status_code=verdict.http_status, detail=verdict.reason)

        overrides = body.model_dump(exclude_unset=True)
        try:
            async with conn.transaction():
                incident_row, bg_tasks = await promote_event(
                    conn,
                    company_id=company_id,
                    event=event,
                    channel_name=event.get("channel_name"),
                    reporter_name=event.get("reporter_name"),
                    overrides=overrides,
                    actor_user_id=current_user.id,
                    actor_email=getattr(current_user, "email", None),
                )
        except PromoteRaceError as e:
            raise HTTPException(status_code=409, detail=str(e))

    for fn, args, kwargs in bg_tasks:
        background_tasks.add_task(fn, *args, **kwargs)

    return PromoteResponse(incident_id=UUID(str(incident_row["id"])))

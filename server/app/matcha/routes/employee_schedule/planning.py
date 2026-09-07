"""Planning routes — the REST backbone of the Schedule Pilot workspace.

- `GET  /locations/{id}/planning-inputs`     what a scheduler should SEE (roster
  load, availability, caps, open seats, policy, jurisdiction, week rules).
- `POST /locations/{id}/fill-vacant/preview` one server-side fill scenario:
  `plan_vacant_fill` picks people, `build_edit_proposal` runs the assignment
  guard and persists ONE reviewable `schedule_chat_proposals` row for the
  caller (`surface='editor'`), and the `ScheduleReview` comes back. No shift
  is written — a preview is a free simulation.
- `POST /fill-vacant/{proposal_id}/apply`    the same confirm-time rechecks
  Huume's confirm turn runs (`execute_edit_proposal`); only the row's creator
  may apply it. No `force` — agent/planner paths never force.
- `DELETE /fill-vacant/{proposal_id}`         discard a scenario.

Location authorization is `assert_manager_location`, the same check the Huume
session and the Week setup pane use. The mount already requires
`employee_schedule`.
"""

import json
from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.feature_flags import get_company_features
from app.database import get_connection

from ...dependencies import require_company_member
from ...models.scheduling.employee_schedule import FillVacantPreviewRequest
from ...services.scheduling import schedule_chat
from ...services.scheduling.planning_inputs import build_planning_inputs
from ...services.scheduling.schedule_assistant_session import assert_manager_location
from ...services.scheduling.week_builder import plan_vacant_fill
from ._shared import require_company_id

router = APIRouter()


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


@router.get("/locations/{location_id}/planning-inputs")
async def get_planning_inputs(
    location_id: UUID,
    week_start: date = Query(..., description="First day of the editor week"),
    current_user=Depends(require_company_member),
):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_manager_location(
            conn, company_id=company_id, user_id=current_user.id,
            actor_role=current_user.role, location_id=location_id,
        )
        return await build_planning_inputs(
            conn, company_id=company_id, location_id=location_id, week_start=week_start,
        )


@router.post("/locations/{location_id}/fill-vacant/preview")
async def preview_fill_vacant(
    location_id: UUID, body: FillVacantPreviewRequest,
    current_user=Depends(require_company_member),
):
    company_id = await require_company_id(current_user)
    week_end = body.week_start + timedelta(days=6)
    async with get_connection() as conn:
        await assert_manager_location(
            conn, company_id=company_id, user_id=current_user.id,
            actor_role=current_user.role, location_id=location_id,
        )
        plan = await plan_vacant_fill(
            conn, company_id=company_id, location_id=location_id,
            week_start=body.week_start, week_end=week_end,
            job_ids=[body.job_id] if body.job_id else None,
            role_hint=body.role_hint, shift_ids=body.shift_ids,
            only_employee_ids=[body.employee_id] if body.employee_id else None,
            exclude_employee_ids=body.exclude_employee_ids,
            allow_split_shift=body.allow_split_shift,
        )
        unfilled = [
            {**item, "starts_at": _iso(item.get("starts_at")), "ends_at": _iso(item.get("ends_at"))}
            for item in plan.get("unfilled") or []
        ]
        if plan.get("status") != "ready":
            return {
                "status": plan.get("status") or "refused", "message": plan.get("message"),
                "unfilled": unfilled, "jurisdiction": plan.get("jurisdiction"),
            }
        if not plan["assignments"]:
            return {
                "status": "empty",
                "message": "No open shift could be filled under the staffing rules.",
                "unfilled": unfilled, "jurisdiction": plan.get("jurisdiction"),
            }
        edit_requests = [
            {"kind": "assign", "target_shift_id": str(item["shift_id"]), "to_employee_name": item["employee_name"]}
            for item in plan["assignments"]
        ]
        build = await schedule_chat.build_edit_proposal(
            conn, company_id=company_id, channel_id=None, source_message_id=None,
            created_by=current_user.id,
            parsed={
                "ack": "Got it.", "action": "edit", "shift_requests": [], "edit_requests": edit_requests,
                # Apply reads these back: the proposal doc itself carries no
                # location or week, and the week bound must be re-applied at
                # confirm exactly as the Huume path does.
                "editor_location_id": str(location_id), "editor_week_start": body.week_start.isoformat(),
                "label": body.label,
            },
            today=date.today(),
            original_content=f"[editor] fill vacant shifts{(' — ' + body.label) if body.label else ''}",
            surface="editor", shift_statuses=("draft", "published"),
            editor_location_id=location_id, editor_week_start=body.week_start, editor_week_end=week_end,
        )
    if build.kind == "clarify":
        text = build.pill_text.removeprefix("\U0001F4C5 ").removesuffix("Just reply to this message.").strip()
        return {
            "status": "refused" if build.clarify_kind == "refused" else "clarify",
            "message": text, "unfilled": unfilled, "jurisdiction": plan.get("jurisdiction"),
        }
    review = {**(build.review or {}), "unfilled": unfilled}
    return {
        "status": "ready", "proposal_id": str(build.proposal_id),
        "pill_text": build.pill_text, "review": review, "label": body.label,
    }


async def _load_own_proposal(conn, *, company_id: UUID, user_id: UUID, proposal_id: UUID):
    row = await conn.fetchrow(
        """
        SELECT id, company_id, channel_id, created_by, proposal, parse, status
        FROM schedule_chat_proposals
        WHERE id = $1 AND company_id = $2
        """,
        proposal_id, company_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="That fill preview was not found")
    if row["created_by"] != user_id:
        raise HTTPException(status_code=403, detail="Only the person who previewed this fill can act on it")
    proposal = row["proposal"]
    if isinstance(proposal, str):
        proposal = json.loads(proposal)
    parse = row["parse"]
    if isinstance(parse, str):
        parse = json.loads(parse)
    if proposal.get("surface") != "editor" or proposal.get("kind") != "edit":
        raise HTTPException(status_code=400, detail="That proposal is not an editor fill preview")
    return row, proposal, parse or {}


@router.post("/fill-vacant/{proposal_id}/apply")
async def apply_fill_vacant(proposal_id: UUID, current_user=Depends(require_company_member)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        row, proposal, parse = await _load_own_proposal(
            conn, company_id=company_id, user_id=current_user.id, proposal_id=proposal_id,
        )
        if row["status"] != "proposed":
            raise HTTPException(status_code=409, detail="That fill preview was already applied or discarded")
        location_id = UUID(parse["editor_location_id"]) if parse.get("editor_location_id") else None
        week_start = date.fromisoformat(parse["editor_week_start"]) if parse.get("editor_week_start") else None
        if location_id is not None:
            await assert_manager_location(
                conn, company_id=company_id, user_id=current_user.id,
                actor_role=current_user.role, location_id=location_id,
            )
        features = await get_company_features(company_id, conn=conn)
        try:
            text = await schedule_chat.execute_edit_proposal(
                conn, proposal_row={**dict(row), "proposal": proposal},
                confirmed_by=current_user.id, features=features,
                week_start=week_start,
                week_end=(week_start + timedelta(days=6)) if week_start else None,
            )
        except schedule_chat.ProposalExecutionClaimError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except schedule_chat.ProposalScopeError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        after = await conn.fetchrow(
            "SELECT created_shift_ids FROM schedule_chat_proposals WHERE id = $1", proposal_id,
        )
    touched = [str(value) for value in ((after and after["created_shift_ids"]) or [])]
    return {"status": "applied", "message": text, "touched_shift_ids": touched}


@router.delete("/fill-vacant/{proposal_id}", status_code=204)
async def discard_fill_vacant(proposal_id: UUID, current_user=Depends(require_company_member)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await _load_own_proposal(
            conn, company_id=company_id, user_id=current_user.id, proposal_id=proposal_id,
        )
        updated = await conn.fetchval(
            """
            UPDATE schedule_chat_proposals
            SET status = 'cancelled', updated_at = NOW()
            WHERE id = $1 AND company_id = $2 AND created_by = $3 AND status = 'proposed'
            RETURNING id
            """,
            proposal_id, company_id, current_user.id,
        )
    if updated is None:
        raise HTTPException(status_code=409, detail="That fill preview was already applied or discarded")
    return None

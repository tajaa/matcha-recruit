"""Admin review surface for Schedule Intelligence's catalog-linked rule
extraction (`/admin/schedule-rules`) — see `services/schedule_rule_extraction.py`.

Every extracted threshold lands `pending`; nothing here writes to the
write-path gate directly — `schedule_compliance.rules_for_state` only reads
`review_status='approved'` rows. This module is the ONLY way a row becomes
approved (no auto-approve tier — see the extraction service docstring for why).
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.database import get_connection
from app.core.dependencies import require_admin
from app.core.us_states import US_STATE_CODES
from app.core.services.schedule_rule_extraction import (
    CODE_CURATED_STATES,
    run_sweep,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class ExtractRequest(BaseModel):
    states: Optional[list[str]] = None


class BlockGradeRequest(BaseModel):
    block_grade: bool


class RejectRequest(BaseModel):
    reason: Optional[str] = None


def _normalize_states(states: Optional[list[str]]) -> list[str]:
    if states:
        return sorted({s.strip().upper() for s in states if s.strip()})
    return sorted(US_STATE_CODES - set(CODE_CURATED_STATES))


@router.post("/schedule-rules/extract", dependencies=[Depends(require_admin)])
async def trigger_extraction(
    body: ExtractRequest, background_tasks: BackgroundTasks, current_user=Depends(require_admin),
):
    """Kick off extraction for the given states (default: every US state minus
    the in-code-curated ones). Runs in the background — see `run_sweep`."""
    states = _normalize_states(body.states)
    background_tasks.add_task(run_sweep, states, triggered_by=current_user.id)
    return {"queued": states}


@router.get("/schedule-rules/overview", dependencies=[Depends(require_admin)])
async def get_overview():
    """Per-state rollup: latest run status, and pending/approved/stale counts."""
    async with get_connection() as conn:
        run_rows = await conn.fetch(
            """
            SELECT DISTINCT ON (state) state, status, requirement_count,
                   extracted_count, completed_at, started_at
            FROM schedule_rule_extraction_runs
            ORDER BY state, started_at DESC
            """
        )
        count_rows = await conn.fetch(
            """
            SELECT state,
                   COUNT(*) FILTER (WHERE review_status = 'pending') AS pending,
                   COUNT(*) FILTER (WHERE review_status = 'approved') AS approved,
                   COUNT(*) FILTER (WHERE review_status = 'rejected') AS rejected,
                   COUNT(*) FILTER (WHERE stale_since IS NOT NULL) AS stale
            FROM schedule_rule_extractions
            WHERE is_active = true
            GROUP BY state
            """
        )
    counts_by_state = {r["state"]: dict(r) for r in count_rows}
    states_out = []
    for r in run_rows:
        counts = counts_by_state.pop(r["state"], {})
        states_out.append({
            "state": r["state"], "run_status": r["status"],
            "requirement_count": r["requirement_count"], "extracted_count": r["extracted_count"],
            "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
            "pending": counts.get("pending", 0), "approved": counts.get("approved", 0),
            "rejected": counts.get("rejected", 0), "stale": counts.get("stale", 0),
        })
    # States with extraction rows but somehow no run row (shouldn't happen, but
    # don't silently drop them from the admin's view).
    for state, counts in counts_by_state.items():
        states_out.append({
            "state": state, "run_status": None, "requirement_count": None, "extracted_count": None,
            "completed_at": None, "pending": counts.get("pending", 0), "approved": counts.get("approved", 0),
            "rejected": counts.get("rejected", 0), "stale": counts.get("stale", 0),
        })
    return {
        "states": sorted(states_out, key=lambda s: s["state"]),
        "code_curated_states": list(CODE_CURATED_STATES),
    }


@router.get("/schedule-rules/{state}", dependencies=[Depends(require_admin)])
async def get_state_rules(state: str):
    state = state.strip().upper()
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, rule_key, rule_value, no_rule, citation, source_requirement_id,
                   source_snapshot, ai_confidence, ai_rationale, review_status,
                   block_grade, proposed, stale_since, reviewed_by, reviewed_at, updated_at
            FROM schedule_rule_extractions
            WHERE state = $1 AND is_active = true
            ORDER BY rule_key
            """,
            state,
        )
    return {"state": state, "rules": [
        {
            "id": str(r["id"]), "rule_key": r["rule_key"],
            "rule_value": float(r["rule_value"]) if r["rule_value"] is not None else None,
            "no_rule": r["no_rule"], "citation": r["citation"],
            "source_requirement_id": str(r["source_requirement_id"]) if r["source_requirement_id"] else None,
            "source_snapshot": r["source_snapshot"], "ai_confidence": float(r["ai_confidence"]) if r["ai_confidence"] is not None else None,
            "ai_rationale": r["ai_rationale"], "review_status": r["review_status"],
            "block_grade": r["block_grade"], "proposed": r["proposed"],
            "stale_since": r["stale_since"].isoformat() if r["stale_since"] else None,
            "reviewed_at": r["reviewed_at"].isoformat() if r["reviewed_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]}


@router.post("/schedule-rules/{rule_id}/approve", dependencies=[Depends(require_admin)])
async def approve_rule(rule_id: UUID, current_user=Depends(require_admin)):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE schedule_rule_extractions
            SET review_status = 'approved', reviewed_by = $2, reviewed_at = NOW(), updated_at = NOW()
            WHERE id = $1 AND is_active = true
            RETURNING id
            """,
            rule_id, current_user.id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"ok": True}


@router.post("/schedule-rules/{rule_id}/reject", dependencies=[Depends(require_admin)])
async def reject_rule(rule_id: UUID, body: RejectRequest, current_user=Depends(require_admin)):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE schedule_rule_extractions
            SET review_status = 'rejected', reviewed_by = $2, reviewed_at = NOW(), updated_at = NOW()
            WHERE id = $1 AND is_active = true
            RETURNING id
            """,
            rule_id, current_user.id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"ok": True}


@router.post("/schedule-rules/{rule_id}/accept-proposed", dependencies=[Depends(require_admin)])
async def accept_proposed(rule_id: UUID, current_user=Depends(require_admin)):
    """Apply a re-run's drifted values onto an approved row and clear the
    staleness flag — the human explicitly re-confirmed the new figures."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT proposed FROM schedule_rule_extractions WHERE id = $1 AND is_active = true",
            rule_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Rule not found")
        proposed = row["proposed"]
        if not proposed:
            raise HTTPException(status_code=409, detail="No proposed change to accept")
        await conn.execute(
            """
            UPDATE schedule_rule_extractions SET
                rule_value = $2, no_rule = $3, citation = $4,
                source_requirement_id = $5, proposed = NULL, stale_since = NULL,
                reviewed_by = $6, reviewed_at = NOW(), updated_at = NOW()
            WHERE id = $1
            """,
            rule_id, proposed.get("rule_value"), proposed.get("no_rule"), proposed.get("citation"),
            UUID(proposed["source_requirement_id"]) if proposed.get("source_requirement_id") else None,
            current_user.id,
        )
    return {"ok": True}


@router.post("/schedule-rules/bulk-approve", dependencies=[Depends(require_admin)])
async def bulk_approve(body: list[UUID], current_user=Depends(require_admin)):
    async with get_connection() as conn:
        count = await conn.fetchval(
            """
            WITH updated AS (
                UPDATE schedule_rule_extractions
                SET review_status = 'approved', reviewed_by = $2, reviewed_at = NOW(), updated_at = NOW()
                WHERE id = ANY($1::uuid[]) AND is_active = true
                RETURNING id
            )
            SELECT COUNT(*) FROM updated
            """,
            body, current_user.id,
        )
    return {"approved": count}


@router.post("/schedule-rules/{rule_id}/block-grade", dependencies=[Depends(require_admin)])
async def set_block_grade(rule_id: UUID, body: BlockGradeRequest):
    """Escalate an approved minor-hour cap from advisory to a non-overridable
    BLOCK. Deliberately single-row and separate from approve/bulk-approve — a
    422 the write path can't override is a bigger decision than "this citation
    looks right", and bulk-approving 50 states' worth of rows must never
    silently also make them all block-grade."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT rule_key, review_status FROM schedule_rule_extractions WHERE id = $1 AND is_active = true",
            rule_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Rule not found")
        if not row["rule_key"].startswith("minor_"):
            raise HTTPException(status_code=422, detail="block_grade only applies to minor-hour rules")
        if row["review_status"] != "approved":
            raise HTTPException(status_code=409, detail="Rule must be approved before it can be block-grade")
        await conn.execute(
            "UPDATE schedule_rule_extractions SET block_grade = $2, updated_at = NOW() WHERE id = $1",
            rule_id, body.block_grade,
        )
    return {"ok": True}

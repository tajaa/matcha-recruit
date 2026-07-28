"""Confirm / cancel a proposed Compliance Pilot action — the write half of the
two-turn safety envelope. `actions.evaluate_confirm` / `evaluate_cancel`
(pure, DB-free) decide WHETHER a call is allowed; this module does the DB work
once they say proceed.

Shared by two callers: the agentic loop's `confirm_action`/`cancel_action`
tools (`agent.py`), and the REST endpoints `POST /actions/{id}/confirm` and
`POST /actions/{id}/cancel` (`admin_compliance_pilot.py`) — one implementation,
so a chat-confirm and a button-confirm for the same action can't diverge.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

import asyncpg

from app.database import get_connection
from app.core.services.compliance_pilot.core import (
    MAX_CONCURRENT_RESEARCH,
    STALE_RECLAIM_HOURS,
    launch_action_task,
)

logger = logging.getLogger(__name__)


class ActionConflict(Exception):
    """Another confirm won the race, or the concurrency ceiling is full — maps
    to a 409 at the route layer and to a plain refusal in the loop."""


async def confirm_and_launch(action_id: str, actor_id: Optional[UUID]) -> dict[str, Any]:
    """Flip a proposed action to running and launch its runner.

    Order matters and is deliberately narrow between the flip and the launch:
    stale reclaim -> (research only) concurrency ceiling -> CAS
    proposed->running -> launch immediately, no awaits in between. A CAS loss
    (another confirm, or the row moved) surfaces as `asyncpg.UniqueViolationError`
    against `uq_compilot_action_running`, converted here to `ActionConflict`.

    `started_at=NOW()` is set on the SAME flip that sets it 'running' — reusing
    the row's original INSERT-time `started_at` would let a proposal staged
    hours before a late confirm get reclaimed by the 2h stale-sweep seconds
    after it actually started.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, session_id, kind, status FROM compliance_pilot_actions WHERE id = $1",
            action_id,
        )
        if not row:
            raise LookupError("Action not found")

        # Reclaim stale runners (dead task / deploy swap) in THIS session first,
        # so a lost run can't lock the running-slot forever — same horizon as
        # vertical_coverage_sweep and the legacy REST create_action path.
        await conn.execute(
            "UPDATE compliance_pilot_actions "
            "SET status='failed', finished_at=NOW(), "
            "    result='{\"error\":\"reclaimed: runner lost\"}'::jsonb "
            "WHERE session_id=$1 AND status='running' "
            f"  AND started_at < NOW() - interval '{STALE_RECLAIM_HOURS} hours'",
            row["session_id"],
        )

        if row["kind"] == "research":
            running = await conn.fetchval(
                "SELECT COUNT(*) FROM compliance_pilot_actions WHERE kind='research' AND status='running'"
            ) or 0
            if running >= MAX_CONCURRENT_RESEARCH:
                raise ActionConflict("Too many research runs in flight — try again shortly")

        try:
            flipped = await conn.fetchrow(
                "UPDATE compliance_pilot_actions "
                "SET status='running', started_at=NOW(), confirmed_at=NOW(), confirmed_by=$2 "
                "WHERE id=$1 AND status='proposed' "
                "RETURNING id",
                UUID(action_id), actor_id,
            )
        except asyncpg.UniqueViolationError:
            raise ActionConflict("An action is already running for this session")
        if not flipped:
            raise ValueError("That action isn't awaiting confirmation")

    # No awaits between the flip committing and the launch — a task started
    # against a row that isn't actually 'running' yet would race its own first
    # write.
    launch_action_task(UUID(action_id), actor_id)
    return {"action_id": action_id, "status": "running"}


async def cancel_proposed(action_id: str) -> dict[str, Any]:
    """CAS proposed -> cancelled. Refuses anything not currently proposed —
    a run already in flight or finished can't be undone from here."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "UPDATE compliance_pilot_actions SET status='cancelled', finished_at=NOW() "
            "WHERE id=$1 AND status='proposed' RETURNING id",
            UUID(action_id),
        )
    if not row:
        exists = await _exists(action_id)
        if not exists:
            raise LookupError("Action not found")
        raise ValueError("That action isn't awaiting confirmation")
    return {"action_id": action_id, "status": "cancelled"}


async def _exists(action_id: str) -> bool:
    async with get_connection() as conn:
        return bool(await conn.fetchval(
            "SELECT 1 FROM compliance_pilot_actions WHERE id = $1", UUID(action_id)))

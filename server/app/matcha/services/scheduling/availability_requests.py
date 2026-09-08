"""Manager-reviewed employee availability changes.

An employee's recurring weekly availability is a single, undated set of windows
(`schedule_employee_availability`): every scheduling decision reads the rows as
they are right now, and nothing anywhere stores what they used to be. That is
why an approved change cannot simply be written at approval time — the employee
asks for it to start on a date, and writing it early would re-decide the weeks
between now and then against a pattern that is not in force yet.

So an approved change is held on its `schedule_requests` row and **promoted**
into the live table on or after `availability_effective_on`. Promotion is
read-driven, not scheduled: `promote_due_availability_changes` runs at the top
of the two functions that are the only ways availability is ever observed —
`shift_writes.fetch_availability` (every scheduling decision: assignment,
retime, swap approval, chat, coverage, the week builder) and
`schedule_profiles.fetch_availability_windows` (the portal and admin views).
Nothing can read a stale set without passing through one of them, which is what
makes correctness independent of whether any periodic worker is enabled.

The promotion write is idempotent and claimed with FOR UPDATE SKIP LOCKED, so
two concurrent scheduling operations for the same employee cannot both apply it
and cannot deadlock against each other; the loser simply reads the set the
winner just wrote.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import time
from typing import Any, Sequence
from uuid import UUID

from app.database import decode_jsonb

from .schedule_profiles import replace_availability_core


@dataclass(frozen=True)
class ProposedWindow:
    """The attribute shape ``replace_availability_core`` writes from.

    A plain dataclass rather than the Pydantic `AvailabilityWindow`: this module
    is imported from the service layer, and the stored JSONB was already
    validated by that model on the way in.
    """

    weekday: int
    start_time: time
    end_time: time


def serialize_proposed_availability(
    availability_state: str, windows: Sequence[Any],
) -> str:
    """JSON for `schedule_requests.proposed_availability`.

    The state is stored RESOLVED (never None): `AvailabilityReplace` lets a
    legacy caller omit it and means "empty list = always available", and that
    inference belongs at submit time, next to the payload that justified it —
    not at approval, days later, against a model that may have moved on.
    """
    return json.dumps({
        "availability_state": availability_state,
        "windows": [
            {
                "weekday": int(window.weekday),
                "start_time": str(window.start_time)[:5],
                "end_time": str(window.end_time)[:5],
            }
            for window in windows
        ],
    })


def parse_proposed_availability(value: Any) -> tuple[str, list[ProposedWindow]]:
    """Inverse of :func:`serialize_proposed_availability`."""
    doc = decode_jsonb(value, {}) or {}
    windows = [
        ProposedWindow(
            weekday=int(window["weekday"]),
            start_time=time.fromisoformat(window["start_time"]),
            end_time=time.fromisoformat(window["end_time"]),
        )
        for window in doc.get("windows") or []
    ]
    state = doc.get("availability_state") or ("windows" if windows else "always_available")
    return state, windows


def summarize_proposed_availability(value: Any) -> dict | None:
    """Serialized shape for the portal and the manager review queue."""
    doc = decode_jsonb(value, None)
    if not doc:
        return None
    return {
        "availability_state": doc.get("availability_state"),
        "windows": doc.get("windows") or [],
    }


async def apply_availability_request(conn, request_row, *, actor_user_id: UUID | None) -> dict:
    """Write one approved request's proposal into the live availability table.

    Caller owns the transaction, and must already hold the request row.
    """
    state, windows = parse_proposed_availability(request_row["proposed_availability"])
    result = await replace_availability_core(
        conn,
        company_id=request_row["company_id"],
        employee_id=request_row["employee_id"],
        availability_state=state,
        windows=windows,
        actor_user_id=actor_user_id,
        actor_kind="employee_request",
        extra_details={
            "request_id": str(request_row["id"]),
            "effective_on": str(request_row["availability_effective_on"]),
        },
    )
    await conn.execute(
        "UPDATE schedule_requests SET availability_applied_at = NOW(), updated_at = NOW() "
        "WHERE id = $1",
        request_row["id"],
    )
    return result


async def promote_due_availability_changes(
    conn, company_id: UUID, employee_ids: Sequence[UUID] | None = None,
) -> int:
    """Apply every approved availability change whose start date has arrived.

    Ordered by effective date then submission, so a later-dated change wins
    when two of them come due together. Returns how many were applied.

    The claim and the write must share one transaction. Without it — on a
    connection in asyncpg's autocommit mode — the FOR UPDATE lock lives only
    for the SELECT, and two readers promoting the same employee can interleave
    into a genuinely wrong result: one applies the older change AFTER the other
    applied the newer one, leaving the employee on the availability they asked
    to move off. So an already-transactional caller (every scheduling write)
    promotes inline, and a bare read opens one.
    """
    in_transaction = getattr(conn, "is_in_transaction", None)
    if in_transaction is not None and not in_transaction():
        async with conn.transaction():
            return await _promote_due(conn, company_id, employee_ids)
    return await _promote_due(conn, company_id, employee_ids)


async def _promote_due(
    conn, company_id: UUID, employee_ids: Sequence[UUID] | None,
) -> int:
    params: list[Any] = [company_id]
    scope = ""
    if employee_ids is not None:
        unique_ids = list(dict.fromkeys(employee_ids))
        if not unique_ids:
            return 0
        params.append(unique_ids)
        scope = f" AND employee_id = ANY(${len(params)}::uuid[])"
    rows = await conn.fetch(
        f"""
        SELECT id, company_id, employee_id, proposed_availability,
               availability_effective_on, reviewed_by
        FROM schedule_requests
        WHERE company_id = $1
          AND request_type = 'availability'
          AND status = 'approved'
          AND availability_applied_at IS NULL
          AND availability_effective_on <= CURRENT_DATE{scope}
        ORDER BY availability_effective_on, created_at
        FOR UPDATE SKIP LOCKED
        """,
        *params,
    )
    for row in rows:
        await apply_availability_request(conn, row, actor_user_id=row["reviewed_by"])
    return len(rows)

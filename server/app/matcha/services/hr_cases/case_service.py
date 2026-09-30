"""HR case records — create, move, read.

`apply_event` is the ONLY writer of `hr_cases.stage`: it locks the row,
asks `stages.next_stage` whether the event applies, writes the stage plus an
allow-listed set of columns, and appends an `hr_case_events` row in the same
transaction. Every function takes `conn` (pool-free-safe) and scopes by
`company_id`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from . import stages

logger = logging.getLogger(__name__)

_JSON_COLUMNS = {"triage", "review", "verification"}
_SETTABLE = _JSON_COLUMNS | {
    "decision", "decision_reason", "decided_by", "decided_at",
    "delivered_at", "delivered_by",
    "attention_reasons", "attention_acknowledged_by", "attention_acknowledged_at",
    "dismissed_reason", "draft_file_id", "signed_file_id",
    "employee_id", "action_type", "occurrence_dates", "thread_id", "gm_user_id",
}
ACTION_TYPES = ("verbal_warning", "written_warning", "final_warning", "suspension", "pip", "other")

_CASE_SELECT = """
    SELECT c.*,
           i.incident_number, i.title AS incident_title, i.occurred_at AS incident_occurred_at,
           NULLIF(TRIM(COALESCE(e.first_name, '') || ' ' || COALESCE(e.last_name, '')), '') AS employee_name,
           COALESCE(NULLIF(gc.name, ''), gu.email) AS gm_name
    FROM hr_cases c
    LEFT JOIN ir_incidents i ON i.id = c.source_incident_id
    LEFT JOIN employees e ON e.id = c.employee_id
    LEFT JOIN users gu ON gu.id = c.gm_user_id
    LEFT JOIN clients gc ON gc.user_id = c.gm_user_id
"""


class CaseError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(detail)


def _json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def serialize(row: Any) -> dict[str, Any]:
    case = dict(row)
    for col in _JSON_COLUMNS:
        case[col] = _json(case.get(col))
    stage = case["stage"]
    case["stage_label"] = stages.STAGE_LABEL.get(stage, stage)
    case["column"] = stages.COLUMN_OF.get(stage)
    case["checklist"] = stages.checklist(stage)
    case["allowed_events"] = stages.allowed_events(stage)
    return case


async def get_settings(conn, company_id: UUID) -> dict[str, Any]:
    row = await conn.fetchrow("SELECT * FROM hr_case_settings WHERE company_id = $1", company_id)
    if row:
        return dict(row)
    return {
        "company_id": company_id,
        "next_seq": 0,
        "filename_template": "{last_name}_{first_name}_{action_type}_{delivered_date}",
        "triage_min_confidence": 0.60,
    }


async def next_case_number(conn, company_id: UUID, *, now: Optional[datetime] = None) -> str:
    seq = await conn.fetchval(
        """
        INSERT INTO hr_case_settings (company_id, next_seq) VALUES ($1, 1)
        ON CONFLICT (company_id) DO UPDATE SET next_seq = hr_case_settings.next_seq + 1
        RETURNING next_seq
        """,
        company_id,
    )
    year = (now or datetime.now(timezone.utc)).year
    return f"HRC-{year}-{int(seq):04d}"


async def record_event(
    conn, *, case_id: UUID, event: str, actor_user_id: Optional[UUID] = None,
    from_stage: Optional[str] = None, to_stage: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO hr_case_events (case_id, actor_user_id, event, from_stage, to_stage, details)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        """,
        case_id, actor_user_id, event, from_stage, to_stage, json.dumps(details or {}, default=str),
    )


async def find_open_case_for_incident(conn, *, company_id: UUID, incident_id: UUID) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow(
        _CASE_SELECT + " WHERE c.company_id = $1 AND c.source_incident_id = $2 "
        "AND c.stage NOT IN ('closed', 'dismissed')",
        company_id, incident_id,
    )
    return serialize(row) if row else None


async def find_latest_case_for_incident(conn, *, company_id: UUID, incident_id: UUID) -> Optional[dict[str, Any]]:
    """The most recent case on an incident in ANY stage, closed and dismissed
    included."""
    row = await conn.fetchrow(
        _CASE_SELECT + " WHERE c.company_id = $1 AND c.source_incident_id = $2 "
        "ORDER BY c.created_at DESC LIMIT 1",
        company_id, incident_id,
    )
    return serialize(row) if row else None


async def open_case(
    conn,
    *,
    company_id: UUID,
    origin: str,
    incident_id: Optional[UUID] = None,
    triage: Optional[dict[str, Any]] = None,
    gm_user_id: Optional[UUID] = None,
    opened_by: Optional[UUID] = None,
    employee_id: Optional[UUID] = None,
) -> tuple[dict[str, Any], bool]:
    """(case, created). An incident already carrying an open case returns that
    case with created=False — the intake flag, close re-check, a GM draft and
    Huume all converge on one case per incident."""
    async with conn.transaction():
        if incident_id is not None:
            # Serialize opens for one incident, then look before numbering: a
            # duplicate open returns the existing case without burning a case
            # number. ON CONFLICT below stays as the backstop.
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))", f"hr_case_open:{incident_id}",
            )
            existing = await find_open_case_for_incident(conn, company_id=company_id, incident_id=incident_id)
            if existing is not None:
                return existing, False
        case_number = await next_case_number(conn, company_id)
        case_id = await conn.fetchval(
            """
            INSERT INTO hr_cases (company_id, case_number, origin, stage, source_incident_id,
                                  triage, gm_user_id, opened_by, employee_id)
            VALUES ($1, $2, $3, 'flagged', $4, $5::jsonb, $6, $7, $8)
            ON CONFLICT (source_incident_id)
                WHERE source_incident_id IS NOT NULL AND stage NOT IN ('closed', 'dismissed')
            DO NOTHING
            RETURNING id
            """,
            company_id, case_number, origin, incident_id,
            json.dumps(triage) if triage is not None else None,
            gm_user_id, opened_by, employee_id,
        )
        if case_id is None:
            existing = await find_open_case_for_incident(conn, company_id=company_id, incident_id=incident_id)
            if existing is None:
                raise CaseError(409, "That incident already has a case.")
            return existing, False
        await record_event(conn, case_id=case_id, event="opened", actor_user_id=opened_by,
                           to_stage="flagged", details={"origin": origin})
    return await get_case(conn, company_id=company_id, case_id=case_id), True


async def apply_event(
    conn,
    *,
    company_id: UUID,
    case_id: UUID,
    event: str,
    actor_user_id: Optional[UUID],
    sets: Optional[dict[str, Any]] = None,
    details: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    sets = dict(sets or {})
    unknown = set(sets) - _SETTABLE
    if unknown:
        raise ValueError(f"Not settable on an HR case: {sorted(unknown)}")
    async with conn.transaction():
        row = await conn.fetchrow(
            "SELECT id, stage FROM hr_cases WHERE id = $1 AND company_id = $2 FOR UPDATE",
            case_id, company_id,
        )
        if not row:
            raise CaseError(404, "That case doesn't exist.")
        try:
            to_stage = stages.next_stage(row["stage"], event)
        except stages.InvalidTransition as exc:
            raise CaseError(409, str(exc)) from None

        assignments = ["stage = $3", "updated_at = NOW()"]
        values: list[Any] = [case_id, company_id, to_stage]
        if to_stage in ("closed", "dismissed"):
            assignments.append("closed_at = NOW()")
        for col, val in sets.items():
            values.append(json.dumps(val, default=str) if col in _JSON_COLUMNS and val is not None else val)
            cast = "::jsonb" if col in _JSON_COLUMNS else ""
            assignments.append(f"{col} = ${len(values)}{cast}")
        await conn.execute(
            f"UPDATE hr_cases SET {', '.join(assignments)} WHERE id = $1 AND company_id = $2",
            *values,
        )
        await record_event(conn, case_id=case_id, event=event, actor_user_id=actor_user_id,
                           from_stage=row["stage"], to_stage=to_stage, details=details)
    return await get_case(conn, company_id=company_id, case_id=case_id)


async def get_case(conn, *, company_id: UUID, case_id: UUID, with_events: bool = False) -> dict[str, Any]:
    row = await conn.fetchrow(_CASE_SELECT + " WHERE c.id = $1 AND c.company_id = $2", case_id, company_id)
    if not row:
        raise CaseError(404, "That case doesn't exist.")
    case = serialize(row)
    if with_events:
        events = await conn.fetch(
            """
            SELECT ev.event, ev.from_stage, ev.to_stage, ev.details, ev.created_at,
                   COALESCE(NULLIF(cl.name, ''), u.email) AS actor_name
            FROM hr_case_events ev
            LEFT JOIN users u ON u.id = ev.actor_user_id
            LEFT JOIN clients cl ON cl.user_id = ev.actor_user_id
            WHERE ev.case_id = $1
            ORDER BY ev.created_at, ev.id
            """,
            case_id,
        )
        case["events"] = [{**dict(e), "details": _json(e["details"]) or {}} for e in events]
    return case


async def list_cases(
    conn, *, company_id: UUID, include_closed: bool = False, limit: int = 200,
) -> list[dict[str, Any]]:
    where = "WHERE c.company_id = $1"
    if not include_closed:
        # Open cases, plus anything closed in the last 30 days so the Done
        # column isn't empty the moment a case finishes.
        where += " AND (c.stage NOT IN ('closed', 'dismissed') OR c.closed_at > NOW() - INTERVAL '30 days')"
    rows = await conn.fetch(
        _CASE_SELECT + f" {where} ORDER BY c.updated_at DESC LIMIT $2",
        company_id, min(max(int(limit), 1), 500),
    )
    return [serialize(r) for r in rows]


async def dismiss_case(conn, *, company_id: UUID, case_id: UUID, actor_user_id: UUID, reason: str) -> dict[str, Any]:
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise CaseError(400, "Say briefly why this case is being dismissed (at least 10 characters).")
    return await apply_event(
        conn, company_id=company_id, case_id=case_id, event="dismiss",
        actor_user_id=actor_user_id, sets={"dismissed_reason": reason[:2000]},
    )

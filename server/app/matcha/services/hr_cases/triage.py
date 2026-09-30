"""Incident triage for HR cases — on intake and again on close.

Reuses the grounded, citation-gated handbook check
(`discipline.discipline_policy_check.check_incident_against_handbook` — a
library call; nothing of the retired discipline product is revived). The
model only REPORTS candidate policy matches; whether that opens a case is
the deterministic `decide_flag` rule, and a person decides everything after.

Invariants:
  - One check per (incident, phase): the `hr_case_triage_log` row is claimed
    BEFORE the model call, so a second close never re-checks or re-notifies.
    A check that couldn't run is retried once in the same run; if it still
    can't, its row is re-claimable by a later trigger, up to MAX_ATTEMPTS.
  - A check that couldn't run is stored as implicated=NULL and opens nothing.
    "Couldn't check" is never read as "clean".
  - No connection is held across the model call: the flag, the claim and the
    handbook corpus are read on a short pooled connection, released, and the
    result written on another.
  - An incident whose case HR already closed or dismissed is never reopened
    by a later check: the finding is recorded on that case, nobody notified.
  - Nothing here stores or forwards the incident narrative; the case keeps
    policy titles, relevance and confidence only.
  - Never raises (it runs after the response, as a background task).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

PHASES = ("intake", "close")
FLAG_RELEVANCE = ("violated", "bent")
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 5.0

# Strong refs to fire-and-forget close checks (the event loop only keeps weak
# ones); same pattern as compliance_pilot/core.py.
_BG_TASKS: set = set()


def decide_flag(result: dict[str, Any], *, min_confidence: float) -> bool:
    """Pure. True when any candidate match is a real violation (or a bent
    rule) at or above the company's confidence threshold."""
    for v in result.get("violations") or []:
        if not isinstance(v, dict):
            continue
        try:
            confidence = float(v.get("confidence") or 0)
        except (TypeError, ValueError):
            continue
        if v.get("relevance") in FLAG_RELEVANCE and confidence >= min_confidence:
            return True
    return False


def summarize(result: dict[str, Any], *, phase: str) -> dict[str, Any]:
    """The part of a check the case keeps: no narrative, no excerpts."""
    return {
        "phase": phase,
        "violations": [
            {
                "policy_title": v.get("policy_title"),
                "relevance": v.get("relevance"),
                "confidence": v.get("confidence"),
            }
            for v in (result.get("violations") or []) if isinstance(v, dict)
        ],
        # Deliberately no `summary`: that is model free text about the
        # incident, and nothing narrative leaves the incident.
        "citation_count": len(result.get("citations") or []),
    }


def _single_involved_employee(incident: dict[str, Any]) -> Optional[UUID]:
    ids = incident.get("involved_employee_ids") or []
    if len(ids) != 1:
        return None
    try:
        return UUID(str(ids[0]))
    except (TypeError, ValueError):
        return None


async def triage_incident(incident_id: str, company_id: str, *, phase: str = "intake") -> dict[str, Any]:
    if phase not in PHASES:
        return {"status": "error", "reason": "bad_phase"}
    try:
        return await _triage(UUID(str(incident_id)), UUID(str(company_id)), phase)
    except Exception:
        logger.exception("[hr_cases] triage failed for incident %s (%s)", incident_id, phase)
        return {"status": "error"}


async def triage_incident_task(incident_id: str, company_id: str, phase: str = "intake") -> None:
    """BackgroundTasks entry point (create_incident_core's bg_tasks)."""
    await triage_incident(incident_id, company_id, phase=phase)


def schedule_close_check(company_id: Any, incident_id: Any) -> None:
    """Fire-and-forget the close-phase check from an incident-close path.
    Never raises; outside a running loop it does nothing."""
    try:
        task = asyncio.get_running_loop().create_task(
            triage_incident(str(incident_id), str(company_id), phase="close")
        )
    except RuntimeError:
        return
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)


_CLAIM_SQL = """
    INSERT INTO hr_case_triage_log (incident_id, phase, company_id, result)
    VALUES ($1, $2, $3, '{"attempts": 1}'::jsonb)
    ON CONFLICT (incident_id, phase) DO UPDATE
        SET result = jsonb_build_object(
            'attempts', COALESCE((hr_case_triage_log.result->>'attempts')::int, 1) + 1)
        WHERE hr_case_triage_log.implicated IS NULL
          AND hr_case_triage_log.result->>'available' = 'false'
          AND COALESCE((hr_case_triage_log.result->>'attempts')::int, 1) < $4
    RETURNING (result->>'attempts')::int
"""


async def _triage(incident_id: UUID, company_id: UUID, phase: str) -> dict[str, Any]:
    from app.core.feature_flags import get_company_features
    from app.core.services.ai_usage import feature_scope
    from app.database.pool import connection_or_direct
    from app.matcha.services.discipline.discipline_policy_check import build_check_corpus, check_with_corpus

    # Short, pooled: nothing below holds a connection across the model call.
    async with connection_or_direct() as conn:
        features = await get_company_features(company_id, conn=conn)
        if not features.get("hr_cases"):
            return {"status": "module_off"}
        attempts = await conn.fetchval(_CLAIM_SQL, incident_id, phase, company_id, MAX_ATTEMPTS)
        if not attempts:
            return {"status": "already_checked"}
        row = await conn.fetchrow(
            """
            SELECT id, company_id, incident_number, title, description, incident_type, severity,
                   created_by, reported_by_email, involved_employee_ids
            FROM ir_incidents WHERE id = $1 AND company_id = $2
            """,
            incident_id, company_id,
        )
        if not row:
            return {"status": "not_found"}
        incident = dict(row)
        corpus = await build_check_corpus(conn, company_id)

    with feature_scope("matcha.hr_cases.triage"):
        result = await check_with_corpus(corpus, incident)
        if not result.get("available") and corpus is not None:
            # One retry for a transient model failure; no corpus won't improve.
            await asyncio.sleep(RETRY_DELAY_SECONDS)
            result = await check_with_corpus(corpus, incident)

    async with connection_or_direct() as conn:
        return await _record(conn, incident=incident, company_id=company_id, phase=phase,
                             result=result, attempts=int(attempts))


async def _record(conn, *, incident: dict[str, Any], company_id: UUID, phase: str,
                  result: dict[str, Any], attempts: int) -> dict[str, Any]:
    from . import case_service, notifications

    incident_id = incident["id"]
    if not result.get("available"):
        await conn.execute(
            "UPDATE hr_case_triage_log SET implicated = NULL, result = $3::jsonb "
            "WHERE incident_id = $1 AND phase = $2",
            incident_id, phase, json.dumps({"available": False, "attempts": attempts}),
        )
        return {"status": "unavailable", "attempts": attempts}

    settings = await case_service.get_settings(conn, company_id)
    implicated = decide_flag(result, min_confidence=float(settings["triage_min_confidence"]))
    summary = summarize(result, phase=phase)
    await conn.execute(
        "UPDATE hr_case_triage_log SET implicated = $3, result = $4::jsonb "
        "WHERE incident_id = $1 AND phase = $2",
        incident_id, phase, implicated, json.dumps(summary),
    )

    existing = await case_service.find_open_case_for_incident(conn, company_id=company_id, incident_id=incident_id)
    if existing is None:
        # A case HR already closed or dismissed stays that way: a later check
        # is information on it, not a new case and a second round of emails.
        existing = await case_service.find_latest_case_for_incident(
            conn, company_id=company_id, incident_id=incident_id,
        )
    if existing:
        # The case already exists (flagged on intake, or opened by a GM
        # draft): record what this check found; a clean close-time check
        # is information for HR, not an automatic dismissal.
        await case_service.record_event(
            conn, case_id=existing["id"],
            event=f"{phase}_check_{'match' if implicated else 'clean'}",
            details=summary,
        )
        return {"status": "recorded", "case_id": str(existing["id"]), "implicated": implicated}

    if not implicated:
        return {"status": "clean"}

    gm_user_id = await notifications.resolve_gm_user_id(conn, company_id=company_id, incident=incident)
    case, created = await case_service.open_case(
        conn,
        company_id=company_id,
        origin="intake_triage" if phase == "intake" else "close_check",
        incident_id=incident_id,
        triage=summary,
        gm_user_id=gm_user_id,
        employee_id=_single_involved_employee(incident),
    )
    if created:
        await notifications.notify_flagged(
            conn, case=case, incident=incident,
            policy_titles=[v["policy_title"] for v in summary["violations"]
                           if v.get("policy_title") and v.get("relevance") in FLAG_RELEVANCE],
        )
    return {"status": "flagged", "case_id": str(case["id"]), "created": created}

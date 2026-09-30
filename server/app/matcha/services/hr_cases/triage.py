"""Incident triage for HR cases — on intake and again on close.

Reuses the grounded, citation-gated handbook check
(`discipline.discipline_policy_check.check_incident_against_handbook` — a
library call; nothing of the retired discipline product is revived). The
model only REPORTS candidate policy matches; whether that opens a case is
the deterministic `decide_flag` rule, and a person decides everything after.

Invariants:
  - One check per (incident, phase) ever: the `hr_case_triage_log` row is
    claimed BEFORE the model call, so a retried background task or a second
    close never re-checks or re-notifies.
  - A check that couldn't run is stored as implicated=NULL and opens nothing.
    "Couldn't check" is never read as "clean".
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
        "citation_count": len(result.get("citations") or []),
        "summary": result.get("summary"),
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


async def _triage(incident_id: UUID, company_id: UUID, phase: str) -> dict[str, Any]:
    from app.core.feature_flags import get_company_features
    from app.core.services.ai_usage import feature_scope
    from app.database.pool import connection_or_direct
    from app.matcha.services.discipline.discipline_policy_check import check_incident_against_handbook

    from . import case_service, notifications

    # A raw connection: it is held across a ~60s grounded model call, and a
    # pooled one held that long starves request traffic (same reasoning as
    # huume/discipline_skill.check_incident_policy).
    async with connection_or_direct(force_direct=True) as conn:
        features = await get_company_features(company_id, conn=conn)
        if not features.get("hr_cases"):
            return {"status": "module_off"}

        claimed = await conn.fetchval(
            """
            INSERT INTO hr_case_triage_log (incident_id, phase, company_id)
            VALUES ($1, $2, $3) ON CONFLICT DO NOTHING RETURNING incident_id
            """,
            incident_id, phase, company_id,
        )
        if not claimed:
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

        with feature_scope("matcha.hr_cases.triage"):
            result = await check_incident_against_handbook(conn, company_id=company_id, incident=incident)

        if not result.get("available"):
            await conn.execute(
                "UPDATE hr_case_triage_log SET implicated = NULL, result = $3::jsonb "
                "WHERE incident_id = $1 AND phase = $2",
                incident_id, phase, json.dumps({"available": False}),
            )
            return {"status": "unavailable"}

        settings = await case_service.get_settings(conn, company_id)
        implicated = decide_flag(result, min_confidence=float(settings["triage_min_confidence"]))
        summary = summarize(result, phase=phase)
        await conn.execute(
            "UPDATE hr_case_triage_log SET implicated = $3, result = $4::jsonb "
            "WHERE incident_id = $1 AND phase = $2",
            incident_id, phase, implicated, json.dumps(summary),
        )

        existing = await case_service.find_open_case_for_incident(conn, company_id=company_id, incident_id=incident_id)
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

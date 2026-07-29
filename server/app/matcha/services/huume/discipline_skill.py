"""Huume incident-triggered discipline skill.

Two staged action types (`discipline_from_incident`, `discipline_decision`),
validated by `actions._validate_discipline_from_incident` /
`_validate_discipline_decision` on the confirm turn, executed here. Executors
return the standard `{status, message, record_id?, record_label?, bg_tasks?}`
shape used across the codebase (`hr_pilot_actions.py`); `bg_tasks` carries the
notification dispatch so it runs post-commit, the same contract the agent's
existing HR-ops drain already implements.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


def _resolve_occurrence_dates(staged_dates: Any, incident_row: Any) -> list[date]:
    """The conduct dates for a draft: what the admin gave, else the source
    incident's own `occurred_at`. Pure.

    Shared by `stage_enrichment` (preview) and `execute` (the filed record) on
    purpose — when each derived them separately the preview rendered "conduct
    occurring on ," while the record was stamped with the incident date, so the
    letter the admin approved was not the letter that got filed. These dates are
    also what `check_discipline_compliance` tests against protected leave, so
    they have to be real either way.
    """
    dates: list[date] = []
    for d in staged_dates or []:
        dates.append(d if isinstance(d, date) else date.fromisoformat(str(d)))
    if dates:
        return dates
    occurred_at = incident_row["occurred_at"] if incident_row else None
    return [occurred_at.date()] if occurred_at else []


async def check_incident_policy(*, company_id: UUID, incident_id: str) -> dict[str, Any]:
    """Model-facing read tool. Runs the policy check and persists it; returns
    a name-free summary (violation titles + policy ids + citation count +
    summary) — never involved_employee_ids, witnesses, or the raw narrative."""
    from app.database.pool import connection_or_direct
    from app.matcha.services.discipline.discipline_policy_check import (
        check_incident_against_handbook,
        persist_policy_check,
    )

    try:
        rid = UUID(str(incident_id))
    except (ValueError, TypeError):
        return {"status": "error", "message": "That incident id doesn't look valid."}

    # A raw, non-pooled connection (force_direct=True), not the shared pool —
    # this holds a live connection across a 60s-timeout Gemini call
    # (check_incident_against_handbook), and a request-path pooled connection
    # held that long lets concurrent Huume turns exhaust the pool.
    async with connection_or_direct(force_direct=True) as conn:
        incident = await conn.fetchrow(
            "SELECT id, title, description, incident_type, severity, incident_number "
            "FROM ir_incidents WHERE id = $1 AND company_id = $2",
            rid, company_id,
        )
        if not incident:
            return {"status": "not_found", "message": "I don't see that incident for this company."}

        # Three-state, same idiom as hr_pilot_corpus: module OFF is a distinct
        # answer from "on and found nothing". Without `handbooks` there is no
        # corpus to check against, and an empty result would otherwise read as
        # "your handbook has nothing relevant to this incident".
        from app.core.feature_flags import get_company_features
        features = await get_company_features(company_id, conn=conn)
        # `tool_declarations()` advertises this tool regardless of the
        # company's flags (same as the legal/handbook pilot skill tools) —
        # unlike the staged HR-ops actions, this READ tool had no per-call
        # re-check at all for `discipline`, only for `handbooks`. Without it,
        # a company with handbooks but not discipline could run the check and
        # get findings for a feature it doesn't have.
        if not features.get("discipline"):
            return {
                "status": "module_off",
                "message": "Discipline isn't enabled for this company.",
            }
        if not features.get("handbooks"):
            return {
                "status": "module_off",
                "message": (
                    "Handbooks aren't enabled for this company, so there's nothing to check "
                    "the incident against — this isn't a clean result, it's no corpus."
                ),
            }

        result = await check_incident_against_handbook(conn, company_id=company_id, incident=dict(incident))
        if not result.get("available"):
            return {"status": "error", "message": "The policy check is unavailable right now — try again shortly."}

        await persist_policy_check(conn, incident_id=rid, result=result)

    violations = result.get("violations") or []
    return {
        "status": "ok",
        "incident_id": str(rid),
        "violations": [
            {
                "policy_title": v["policy_title"],
                "relevance": v["relevance"],
                "confidence": v["confidence"],
            }
            for v in violations
        ],
        "citation_count": len(result.get("citations") or []),
        "summary": result.get("summary"),
    }


async def list_pending(*, company_id: UUID) -> dict[str, Any]:
    """Model-facing read tool — ids + labels for the HR approval queue."""
    from app.database import get_connection
    from app.core.feature_flags import get_company_features
    from app.matcha.services.discipline import discipline_engine

    async with get_connection() as conn:
        # Unlike check_incident_policy's `handbooks` check, this tool had no
        # per-call feature gate at all — `tool_declarations()` advertises it
        # regardless of the company's flags.
        features = await get_company_features(company_id, conn=conn)
        if not features.get("discipline"):
            return {"status": "module_off", "message": "Discipline isn't enabled for this company."}
        rows = await discipline_engine.list_pending_approval(conn, company_id)

    return {
        "status": "ok",
        "pending": [
            {
                "record_id": str(r["id"]),
                "discipline_type": r["discipline_type"],
                "infraction_type": r["infraction_type"],
                "approval_requested_at": (
                    r["approval_requested_at"].isoformat() if r.get("approval_requested_at") else None
                ),
            }
            for r in rows
        ],
    }


async def stage_enrichment(conn, *, company_id: UUID, staged: dict[str, Any]) -> dict[str, Any]:
    """Enrich a `discipline_from_incident` staged action, at STAGE time, with
    the resolved template + rendered preview + missing_fields + any existing
    policy-check citations for the source incident. Returns a NEW dict —
    nothing is written. Best-effort: enrichment failures degrade to the
    un-enriched staged dict rather than blocking staging."""
    from app.matcha.services.discipline import discipline_templates

    enriched = dict(staged)
    try:
        employee = await conn.fetchrow(
            "SELECT id, first_name, last_name, job_title, manager_id "
            "FROM employees WHERE id = $1 AND org_id = $2",
            UUID(staged["employee_id"]), company_id,
        )
        if not employee:
            return enriched

        # Display-only. The executor always uses employee_id; this exists so the
        # panel's banner and doc viewer can name the person instead of rendering
        # the literal word "employee".
        enriched["employee_name"] = " ".join(
            p for p in (employee["first_name"], employee["last_name"]) if p
        ).strip() or None

        templates = await discipline_templates.list_templates(conn, company_id)
        template = discipline_templates.resolve_template(
            templates,
            infraction_type=staged["infraction_type"],
            discipline_type=staged.get("discipline_type"),
        )

        incident = None
        citations: list[str] = []
        occurrence_dates = list(staged.get("occurrence_dates") or [])
        if staged.get("incident_id"):
            incident = await conn.fetchrow(
                "SELECT id, incident_number, occurred_at FROM ir_incidents WHERE id = $1 AND company_id = $2",
                UUID(staged["incident_id"]), company_id,
            )
            # Same fallback the executor applies (_resolve_occurrence_dates), so the
            # preview the admin approves is the letter that actually gets filed. Left
            # out, the preview read "conduct occurring on ," while the record was
            # stamped with the incident's own date.
            occurrence_dates = _resolve_occurrence_dates(occurrence_dates, incident)
            enriched["occurrence_dates"] = [str(d) for d in occurrence_dates]
            existing = await conn.fetchval(
                "SELECT analysis_data FROM ir_incident_analysis WHERE incident_id = $1 AND analysis_type = 'policy_mapping'",
                UUID(staged["incident_id"]),
            )
            if existing:
                import json
                data = json.loads(existing) if isinstance(existing, str) else dict(existing)
                citations = [m.get("policy_title") for m in (data.get("matches") or []) if m.get("policy_title")]

        if template:
            values = await discipline_templates.build_placeholder_values(
                conn, company_id=company_id, employee=dict(employee),
                record_fields={
                    "infraction_type": staged["infraction_type"],
                    "discipline_type": staged.get("discipline_type"),
                    "occurrence_dates": occurrence_dates,
                    "description": staged.get("description"),
                    "expected_improvement": staged.get("expected_improvement"),
                    "issued_date": date.today().isoformat(),
                },
                incident=dict(incident) if incident else None,
                policy_citations=citations,
            )
            rendered, missing = discipline_templates.render_template(template["body"], values)
            enriched["template_id"] = str(template["id"])
            enriched["template_name"] = template["name"]
            enriched["rendered_preview"] = rendered
            enriched["missing_fields"] = missing
        enriched["policy_citations"] = citations
    except Exception:
        logger.exception("[huume/discipline_skill] stage_enrichment failed")
    return enriched


async def execute(*, company_id: UUID, actor_user_id: Optional[UUID], action: dict[str, Any]) -> dict[str, Any]:
    atype = action.get("type")
    if atype == "discipline_from_incident":
        return await _execute_discipline_from_incident(company_id, actor_user_id, action)
    if atype == "discipline_decision":
        return await _execute_discipline_decision(company_id, actor_user_id, action)
    return {"status": "error", "message": "Unsupported action."}


async def _execute_discipline_from_incident(
    company_id: UUID, actor_user_id: Optional[UUID], action: dict[str, Any],
) -> dict[str, Any]:
    from app.database import get_connection
    from app.matcha.services.discipline.discipline_compliance import check_discipline_compliance
    from app.matcha.services.discipline.discipline_engine import issue_discipline_with_supersede

    employee_id = UUID(action["employee_id"])
    incident_id = UUID(action["incident_id"]) if action.get("incident_id") else None
    infraction_type = action["infraction_type"]

    async with get_connection() as conn:
        employee = await conn.fetchrow(
            "SELECT id, first_name, last_name FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id,
        )
        if not employee:
            return {"status": "error", "message": "I don't see that employee for this company."}

        incident_row = None
        if incident_id:
            incident_row = await conn.fetchrow(
                "SELECT occurred_at FROM ir_incidents WHERE id = $1 AND company_id = $2",
                incident_id, company_id,
            )
            if not incident_row:
                return {"status": "error", "message": "I don't see that incident for this company."}
        occurrence_dates = _resolve_occurrence_dates(action.get("occurrence_dates"), incident_row)

        # Deterministic legal gate — same order as hr_pilot_actions'
        # _execute_discipline_draft: a block is a hard refusal, no override.
        verdict = await check_discipline_compliance(
            conn, company_id=company_id, employee_id=employee_id,
            infraction_type=infraction_type, occurrence_dates=occurrence_dates,
        )
        if verdict.get("blocks"):
            details = " ".join(b.get("detail", "") for b in verdict["blocks"]).strip()
            return {
                "status": "blocked",
                "message": f"I can't stage this — {details} This needs to go to corporate HR.",
                "compliance": verdict,
            }

        row = await issue_discipline_with_supersede(
            actor_user_id=actor_user_id,
            company_id=company_id,
            employee_id=employee_id,
            infraction_type=infraction_type,
            severity=action.get("severity") or "moderate",
            discipline_type=action.get("discipline_type") or "verbal_warning",
            issued_date=date.today(),
            description=action["description"],
            expected_improvement=action.get("expected_improvement"),
            occurrence_dates=occurrence_dates,
            situation_narrative=action["description"],
            compliance_check=verdict,
            approval_status="pending",
            source_incident_id=incident_id,
            template_id=UUID(action["template_id"]) if action.get("template_id") else None,
        )

    name = " ".join(p for p in (employee["first_name"], employee["last_name"]) if p).strip() or "the employee"
    level_label = (row.get("discipline_type") or "verbal_warning").replace("_", " ")
    msg = f"Staged a {level_label} for {name} ({infraction_type}) — pending HR approval, nothing is issued yet."
    advisories = verdict.get("advisories") or []
    if advisories:
        adv_text = " ".join(a.get("detail", "") for a in advisories).strip()
        msg += f"\n\nHeads up for the approver: {adv_text}"

    async def _notify(record: dict[str, Any]) -> None:
        from app.matcha.services.discipline import discipline_notifications
        await discipline_notifications.dispatch(
            record=record, action="discipline_approval_requested", audience="hr_only",
        )

    return {
        "status": "created",
        "message": msg,
        "record_id": str(row["id"]),
        "record_label": f"Disciplinary action ({level_label}) — pending HR approval",
        "compliance": verdict,
        "bg_tasks": [(_notify, (row,), {})],
    }


async def _execute_discipline_decision(
    company_id: UUID, actor_user_id: Optional[UUID], action: dict[str, Any],
) -> dict[str, Any]:
    from app.database import get_connection
    from app.matcha.services.discipline import discipline_engine

    record_id = UUID(action["record_id"])
    decision = action["decision"]

    async with get_connection() as conn:
        if decision == "approve":
            updated = await discipline_engine.approve_record(
                conn, discipline_id=record_id, company_id=company_id, actor_user_id=actor_user_id,
            )
            notif_action, audience = "discipline_approved", "manager_only"
        else:
            updated = await discipline_engine.deny_record(
                conn, discipline_id=record_id, company_id=company_id,
                actor_user_id=actor_user_id, reason=action["reason"],
            )
            notif_action, audience = "discipline_denied", "hr_only"

    if not updated:
        return {"status": "error", "message": "That record isn't awaiting approval."}

    async def _notify(record: dict[str, Any]) -> None:
        from app.matcha.services.discipline import discipline_notifications
        await discipline_notifications.dispatch(record=record, action=notif_action, audience=audience)

    verb = "Approved" if decision == "approve" else "Denied"
    return {
        "status": "created",
        "message": f"{verb} the discipline record.",
        "record_id": str(updated["id"]),
        "record_label": f"Discipline decision — {verb.lower()}",
        "bg_tasks": [(_notify, (updated,), {})],
    }

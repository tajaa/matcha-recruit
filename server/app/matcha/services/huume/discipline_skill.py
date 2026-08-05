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

import json
import logging
from datetime import date
from typing import Any, Optional
from uuid import UUID

from app.core.services.ai_usage import feature_scope

logger = logging.getLogger(__name__)

# Discovery batch (find_candidates) tuning.
_FRESH_CHECK_CAP = 6          # max fresh Gemini checks in one call
_BATCH_BUDGET_SECONDS = 100   # bound on the whole fresh-check batch
_NOT_YET_CHECKED_NUMBERS_CAP = 20  # cap the list; `count` stays exact regardless
# Only _FRESH_CHECK_CAP (6) rows ever get a fresh Gemini check and only
# `limit` (<=10) are ever returned, but with no LIMIT a 180-day window on a
# busy tenant loads full incident description + analysis JSONB for every
# closed incident in it. Bounds the fetch without changing reported
# semantics for any realistic tenant.
_SCAN_ROW_CAP = 200
_RELEVANCE_RANK = {"violated": 2, "bent": 1, "related": 0}


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


def _rank_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure. `rows` = [{..., 'matches': [{'relevance', 'confidence', ...}, ...]}].
    Drops rows with no matches, then sorts by (max relevance rank, max
    confidence) descending — a single 'violated' match at low confidence
    still outranks several 'related' matches at high confidence, since
    `relevance` is the model's own severity judgment and `confidence` only
    disambiguates within it."""
    kept = [r for r in rows if r.get("matches")]

    def _key(row: dict[str, Any]) -> tuple[int, float]:
        matches = row["matches"]
        return (
            max(_RELEVANCE_RANK.get(m.get("relevance"), 0) for m in matches),
            max(float(m.get("confidence") or 0) for m in matches),
        )

    kept.sort(key=_key, reverse=True)
    return kept


async def find_candidates(
    *, company_id: UUID, days: int = 30, limit: int = 5, recheck: bool = False,
) -> dict[str, Any]:
    """Model-facing discovery tool: "which closed incidents implicate
    discipline?" answered in ONE call instead of one check_incident_policy
    call per incident (serial, 60s-Gemini-each, and tool calls in a turn run
    sequentially against an 8-call/240s budget — a 10-incident scan would
    force-finish partway and the partial result would read as the answer).

    Cached-first: any incident already checked (by this tool, a prior
    check_incident_policy call, or the Celery discipline_policy_sweep — they
    all persist to the same `policy_mapping` analysis row) is reported at
    zero Gemini cost. Only the remainder gets a fresh check, capped at
    `_FRESH_CHECK_CAP` and time-boxed at `_BATCH_BUDGET_SECONDS` — whatever's
    left over is reported as `not_yet_checked`, NEVER folded into "nothing
    found". Name-free by construction: no description, title, or involved-
    party id is ever copied into the returned payload — that's what
    show_record is for.
    """
    from app.database.pool import connection_or_direct
    from app.core.feature_flags import get_company_features
    from app.matcha.services.discipline.discipline_policy_check import check_incidents_against_handbook

    days = min(max(int(days or 30), 1), 180)
    limit = min(max(int(limit or 5), 1), 10)

    async with connection_or_direct(force_direct=True) as conn:
        features = await get_company_features(company_id, conn=conn)
        if not features.get("discipline"):
            return {"status": "module_off", "message": "Discipline isn't enabled for this company."}
        if not features.get("handbooks"):
            return {
                "status": "module_off",
                "message": (
                    "Handbooks aren't enabled for this company, so there's nothing to check "
                    "closed incidents against — this isn't a clean scan, it's no corpus."
                ),
            }

        rows = await conn.fetch(
            """
            SELECT i.id, i.incident_number, i.severity, i.incident_type, i.occurred_at,
                   i.title, i.description,
                   a.analysis_data,
                   EXISTS (
                       SELECT 1 FROM progressive_discipline pd WHERE pd.source_incident_id = i.id
                   ) AS already_disciplined
            FROM ir_incidents i
            LEFT JOIN ir_incident_analysis a
                   ON a.incident_id = i.id AND a.analysis_type = 'policy_mapping'
            WHERE i.company_id = $1 AND i.status = 'closed'
              AND i.updated_at > NOW() - ($2 || ' days')::interval
            ORDER BY i.updated_at DESC
            LIMIT $3
            """,
            company_id, str(days), _SCAN_ROW_CAP,
        )
        # `not_yet_checked.count` below already reads as "unchecked within the
        # scanned window", never "every closed incident" — only 30-180 days
        # of CLOSED incidents are considered in the first place, and the LIMIT
        # just bounds how much of that window one call loads (full
        # description + analysis JSONB) when only _FRESH_CHECK_CAP get a
        # fresh check and `limit` are ever returned.

        cached_rows: list[dict[str, Any]] = []
        to_check: list[dict[str, Any]] = []
        for r in rows:
            row = dict(r)
            analysis = row.get("analysis_data")
            is_cached = False
            if analysis and not recheck:
                try:
                    data = json.loads(analysis) if isinstance(analysis, str) else dict(analysis)
                except (ValueError, TypeError):
                    data = {}
                if data.get("checked_by") == "discipline_policy_check":
                    is_cached = True
                    # A stored `matches` list is shared with
                    # _auto_map_policy_violations (the IR analysis tab's
                    # writer) and persist_policy_check's own merge-over-base,
                    # so its shape isn't guaranteed forever — keep only dicts
                    # rather than trusting the JSONB blob, so one malformed
                    # cached row degrades to "no matches" instead of an
                    # AttributeError (`.get` on a str) failing the whole scan
                    # in _rank_candidates below.
                    cached_matches = data.get("matches")
                    row["matches"] = (
                        [m for m in cached_matches if isinstance(m, dict)]
                        if isinstance(cached_matches, list) else []
                    )
            if is_cached:
                cached_rows.append(row)
            else:
                to_check.append(row)

        fresh_batch = to_check[:_FRESH_CHECK_CAP]
        overflow = to_check[_FRESH_CHECK_CAP:]

        fresh_rows: list[dict[str, Any]] = []
        not_yet_checked = list(overflow)
        if fresh_batch:
            # `budget_seconds` is an INTERNAL deadline inside
            # check_incidents_against_handbook, not an external
            # asyncio.wait_for around this call — wrapping it externally
            # would cancel the batch mid-persist-loop and discard every
            # already-completed (and already-billed) Gemini check along
            # with the ones still in flight. A result missing from
            # `batch_results` because the budget expired is handled the
            # same way as one that failed: folded into not_yet_checked below.
            with feature_scope("matcha.huume.discipline_batch"):
                batch_results = await check_incidents_against_handbook(
                    conn, company_id=company_id, incidents=fresh_batch, budget_seconds=_BATCH_BUDGET_SECONDS,
                )

            for row in fresh_batch:
                result = batch_results.get(str(row["id"]))
                if result is None or not result.get("available"):
                    not_yet_checked.append(row)
                    continue
                row["matches"] = result.get("violations") or []
                fresh_rows.append(row)

    checked_rows = cached_rows + fresh_rows
    clean_count = sum(1 for r in checked_rows if not r.get("matches"))
    ranked = _rank_candidates(checked_rows)[:limit]

    return {
        "status": "ok",
        "candidates": [
            {
                "incident_id": str(row["id"]),
                "incident_number": row.get("incident_number"),
                "occurred_at": row["occurred_at"].isoformat() if row.get("occurred_at") else None,
                "severity": row.get("severity"),
                "policy_titles": [m.get("policy_title") for m in row["matches"] if m.get("policy_title")],
                "top_relevance": max(
                    row["matches"], key=lambda m: _RELEVANCE_RANK.get(m.get("relevance"), 0)
                ).get("relevance"),
                "top_confidence": max(float(m.get("confidence") or 0) for m in row["matches"]),
                "already_disciplined": bool(row.get("already_disciplined")),
            }
            for row in ranked
        ],
        "checked": len(checked_rows),
        "cached": len(cached_rows),
        "clean_count": clean_count,
        "not_yet_checked": {
            "count": len(not_yet_checked),
            # Capped independently of `count` — a busy tenant's first scan
            # can leave hundreds unchecked, and the full list adds nothing
            # the count doesn't already say plainly.
            "incident_numbers": [r.get("incident_number") for r in not_yet_checked[:_NOT_YET_CHECKED_NUMBERS_CAP]],
        },
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
            "SELECT id, first_name, last_name, job_title, manager_id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id,
        )
        if not employee:
            return {"status": "error", "message": "I don't see that employee for this company."}

        incident_row = None
        if incident_id:
            incident_row = await conn.fetchrow(
                "SELECT id, incident_number, occurred_at FROM ir_incidents WHERE id = $1 AND company_id = $2",
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

        # If a template resolved at stage time, re-render it here from a
        # fresh placeholder pass — the staged `rendered_preview` string
        # crossed a model turn and is display state, not what gets filed.
        # `situation_narrative` always keeps the raw HR/model account
        # regardless of a template (it already did before this change, since
        # both fields were previously set to the same text); `description`
        # becomes the templated letter when one applies, otherwise stays the
        # freeform text exactly as before.
        description = action["description"]
        template_id = UUID(action["template_id"]) if action.get("template_id") else None
        if template_id:
            from app.matcha.services.discipline import discipline_templates
            tpl = await conn.fetchrow(
                "SELECT id, body FROM company_discipline_templates "
                "WHERE id = $1 AND company_id = $2 AND is_active",
                template_id, company_id,
            )
            if tpl:
                citations: list[str] = []
                if incident_id:
                    existing = await conn.fetchval(
                        "SELECT analysis_data FROM ir_incident_analysis "
                        "WHERE incident_id = $1 AND analysis_type = 'policy_mapping'",
                        incident_id,
                    )
                    if existing:
                        data = json.loads(existing) if isinstance(existing, str) else dict(existing)
                        citations = [m.get("policy_title") for m in (data.get("matches") or []) if m.get("policy_title")]
                values = await discipline_templates.build_placeholder_values(
                    conn, company_id=company_id, employee=dict(employee),
                    record_fields={
                        "infraction_type": infraction_type,
                        "discipline_type": action.get("discipline_type") or "verbal_warning",
                        "occurrence_dates": occurrence_dates,
                        "description": action["description"],
                        "expected_improvement": action.get("expected_improvement"),
                        "issued_date": date.today().isoformat(),
                    },
                    incident=dict(incident_row) if incident_row else None,
                    policy_citations=citations,
                )
                rendered, missing = discipline_templates.render_template(tpl["body"], values)
                if missing:
                    logger.warning(
                        "[huume/discipline_skill] template %s missing fields at execute time: %s",
                        template_id, missing,
                    )
                description = rendered

        row = await issue_discipline_with_supersede(
            actor_user_id=actor_user_id,
            company_id=company_id,
            employee_id=employee_id,
            infraction_type=infraction_type,
            severity=action.get("severity") or "moderate",
            discipline_type=action.get("discipline_type") or "verbal_warning",
            issued_date=date.today(),
            description=description,
            expected_improvement=action.get("expected_improvement"),
            occurrence_dates=occurrence_dates,
            situation_narrative=action["description"],
            compliance_check=verdict,
            approval_status="pending",
            source_incident_id=incident_id,
            template_id=template_id,
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
        elif decision == "revise":
            updated = await discipline_engine.deny_record(
                conn, discipline_id=record_id, company_id=company_id,
                actor_user_id=actor_user_id, reason=action["reason"], disposition="revise",
            )
            notif_action, audience = "discipline_changes_requested", "drafter_only"
        else:
            updated = await discipline_engine.deny_record(
                conn, discipline_id=record_id, company_id=company_id,
                actor_user_id=actor_user_id, reason=action["reason"], disposition="reject",
            )
            notif_action, audience = "discipline_denied", "hr_only"

    if not updated:
        return {"status": "error", "message": "That record isn't awaiting approval."}

    async def _notify(record: dict[str, Any]) -> None:
        from app.matcha.services.discipline import discipline_notifications
        await discipline_notifications.dispatch(record=record, action=notif_action, audience=audience)

    verb = {"approve": "Approved", "revise": "Sent back for revision", "deny": "Denied"}[decision]
    return {
        "status": "created",
        "message": f"{verb} the discipline record.",
        "record_id": str(updated["id"]),
        "record_label": f"Discipline decision — {verb.lower()}",
        "bg_tasks": [(_notify, (updated,), {})],
    }

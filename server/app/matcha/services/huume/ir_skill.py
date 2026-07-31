"""Huume IR Copilot bridge — ask the IR Copilot a question, or run an AI
analysis, on an incident, from a matcha-work thread.

Mirrors er_skill.py's conventions: never raises past the module boundary —
degrades to {"status": "error", "message": ...}; opens its own connections;
releases the connection before any Gemini call so a slow model round doesn't
pin a pool slot for its whole duration. RateLimitExceeded is caught
explicitly in both entry points (not folded into a blanket except) so a
rate-limited turn reports cleanly instead of either dying (escaping to
agent.py's turn-level handler) or being misreported as a generic failure.

Both entry points write into the SAME tables the /app/ir/{id} page reads
(ir_incident_ai_messages, ir_incident_analysis) — a chat-originated turn or
analysis run is visible, and continuable, from the incident detail page.
"""

import asyncio
import json
import logging
from typing import Any, Optional
from uuid import UUID

from app.core.services.rate_limiter import RateLimitExceeded
from app.database import get_connection

logger = logging.getLogger(__name__)

_ANALYSIS_TYPES = ("root_cause", "recommendations")
_GEMINI_TIMEOUT = 60.0


async def _resolve_incident(
    conn, company_id: UUID, requested: Optional[str], fallback_id: Optional[str],
) -> tuple[Optional[UUID], Optional[str]]:
    """Explicit incident_id -> the thread's active incident
    (current_state.huume_ir) -> a refusal naming both options.
    Returns (incident_id, error) — mirrors er_skill._resolve_case."""
    candidate = requested or fallback_id
    if not candidate:
        return None, (
            "I don't have an incident in mind — promote an event first, or name "
            "which incident you mean."
        )
    try:
        iid = UUID(str(candidate))
    except (ValueError, TypeError):
        return None, f"'{candidate}' isn't an incident id."
    exists = await conn.fetchval(
        "SELECT id FROM ir_incidents WHERE id = $1 AND company_id = $2", iid, company_id,
    )
    if not exists:
        return None, "No incident with that id exists for this company."
    return iid, None


async def ask_copilot(
    *,
    company_id: UUID,
    actor_user_id: Optional[UUID],
    incident_id: Optional[str],
    state_incident_id: Optional[str],
    question: str,
) -> dict[str, Any]:
    from app.matcha.routes.ir_incidents._shared import log_audit
    from app.matcha.services.ir.ir_ai_orchestrator import (
        generate_guidance, load_incident_state, persist_assistant_round,
    )

    question = (question or "").strip()
    if not question:
        return {"status": "error", "message": "Ask a question about the incident."}

    async with get_connection() as conn:
        iid, err = await _resolve_incident(conn, company_id, incident_id, state_incident_id)
        if err:
            return {"status": "error", "message": err}

        incident, analyses, messages = await load_incident_state(conn, iid, company_id)
        if incident is None:
            return {"status": "error", "message": "Incident not found."}

        # The user turn is NOT written here. Writing it now and the assistant
        # turn later (on a second connection, after a Gemini call that can
        # fail) would leave an orphaned question in the incident's Copilot
        # transcript on a failure — a permanent gap on a legal record. Kept
        # in-memory for the prompt only; persist_assistant_round below writes
        # both turns atomically once guidance actually exists.
        messages = [*messages, {"role": "user", "message_type": "text", "content": question}]

    # Connection released before the (up-to-60s) Gemini call.
    try:
        payload = await generate_guidance(incident=incident, analyses=analyses, messages=messages)
    except RateLimitExceeded:
        return {"status": "error", "message": "IR Copilot hit its rate limit — try again shortly."}
    except Exception:
        logger.exception("huume: IR Copilot round failed for incident %s", iid)
        return {"status": "error", "message": "IR Copilot couldn't generate guidance right now."}

    async with get_connection() as conn:
        await persist_assistant_round(
            conn, incident_id=iid, user_id=actor_user_id, user_message=question,
            guidance_payload=payload,
        )
        # Audit in the same connection as the persisted round — a request
        # that came from chat still leaves a trail; skipping this because
        # the caller isn't the REST route would be a silent gap in it.
        await log_audit(
            conn, str(iid), str(actor_user_id) if actor_user_id else None,
            "copilot_message", "incident", str(iid),
            {"via": "huume", "user_message_len": len(question)},
        )

    return {
        "status": "ok",
        "incident_id": str(iid),
        "incident_number": incident.get("incident_number"),
        "summary": payload.get("summary"),
        "open_questions": payload.get("open_questions") or [],
        "suggested_actions": [
            c.get("title") for c in (payload.get("cards") or []) if c.get("title")
        ],
        "note": "This exchange is saved to the incident's Copilot transcript on the IR detail page.",
    }


async def run_analysis(
    *,
    company_id: UUID,
    actor_user_id: Optional[UUID],
    incident_id: Optional[str],
    state_incident_id: Optional[str],
    analysis_type: str,
    refresh: bool = False,
) -> dict[str, Any]:
    """Deliberately NOT reusing ir_incidents/ai_analysis.py's run_*_inline —
    those hard-couple to a FastAPI current_user via
    _get_incident_with_company_check. Same cache table/keys either way, so
    the IR detail panels open pre-cached regardless of which path ran it.

    Connection discipline matters here specifically: the Gemini call runs
    with NO connection held. ir_analysis.py's rate limiter opens its own
    pooled connection per call (check_limit), and the pool is only 10
    connections — holding one across the up-to-60s analyzer call while the
    rate limiter tries to acquire a second is a real deadlock under load,
    not just contention."""
    from app.matcha.routes.ir_incidents._shared import log_audit, parse_witnesses
    from app.matcha.routes.ir_incidents.ai_analysis import _auto_map_training_topics
    from app.matcha.services.ir.ir_analysis import IRAnalysisError, get_ir_analyzer

    if analysis_type not in _ANALYSIS_TYPES:
        return {"status": "error", "message": f"Unknown analysis type '{analysis_type}'."}

    async with get_connection() as conn:
        iid, err = await _resolve_incident(conn, company_id, incident_id, state_incident_id)
        if err:
            return {"status": "error", "message": err}

        if not refresh:
            cached = await conn.fetchrow(
                """
                SELECT analysis_data FROM ir_incident_analysis
                WHERE incident_id = $1 AND analysis_type = $2
                ORDER BY generated_at DESC LIMIT 1
                """,
                iid, analysis_type,
            )
            if cached:
                data = cached["analysis_data"]
                return {
                    "status": "ok", "cached": True, "incident_id": str(iid),
                    "analysis": json.loads(data) if isinstance(data, str) else data,
                }

        row = await conn.fetchrow("SELECT * FROM ir_incidents WHERE id = $1", iid)
        if not row:
            return {"status": "error", "message": "Incident not found."}
        row = dict(row)

        company_id_for_training = row.get("company_id")

        if analysis_type == "root_cause":
            category_data = (
                json.loads(row["category_data"])
                if isinstance(row.get("category_data"), str) else row.get("category_data")
            )
            witnesses = parse_witnesses(row.get("witnesses"))
            root_cause_kwargs = dict(
                title=row["title"], description=row["description"],
                incident_type=row["incident_type"], severity=row["severity"],
                location=row["location"], category_data=category_data,
                witnesses=[w.model_dump() for w in witnesses],
            )
            recommendations_kwargs = None
        else:
            company_name = industry = company_size = ir_guidance_blurb = None
            if row.get("company_id"):
                company = await conn.fetchrow(
                    "SELECT name, industry, size, ir_guidance_blurb FROM companies WHERE id = $1",
                    row["company_id"],
                )
                if company:
                    company_name, industry = company["name"], company["industry"]
                    company_size, ir_guidance_blurb = company["size"], company["ir_guidance_blurb"]
            city = state = None
            if row.get("location_id"):
                location = await conn.fetchrow(
                    "SELECT city, state FROM business_locations WHERE id = $1", row["location_id"],
                )
                if location:
                    city, state = location["city"], location["state"]
            recommendations_kwargs = dict(
                title=row["title"], description=row["description"],
                incident_type=row["incident_type"], severity=row["severity"],
                root_cause=row["root_cause"], company_name=company_name,
                industry=industry, company_size=company_size, city=city, state=state,
                ir_guidance_blurb=ir_guidance_blurb,
            )
            root_cause_kwargs = None

    # Connection released before the (up-to-60s) Gemini call — see docstring.
    try:
        analyzer = get_ir_analyzer()
        if analysis_type == "root_cause":
            result = await asyncio.wait_for(
                analyzer.analyze_root_cause(**root_cause_kwargs), timeout=_GEMINI_TIMEOUT,
            )
        else:
            result = await asyncio.wait_for(
                analyzer.generate_recommendations(**recommendations_kwargs), timeout=_GEMINI_TIMEOUT,
            )
    except RateLimitExceeded:
        return {"status": "error", "message": "IR analysis hit its rate limit — try again shortly."}
    except (IRAnalysisError, asyncio.TimeoutError):
        logger.exception("huume: %s analysis failed for incident %s", analysis_type, iid)
        return {"status": "error", "message": f"{analysis_type} analysis failed."}

    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, $2, $3)
            ON CONFLICT (incident_id, analysis_type)
            DO UPDATE SET analysis_data = EXCLUDED.analysis_data, generated_at = NOW()
            """,
            iid, analysis_type, json.dumps(result),
        )
        await log_audit(
            conn, str(iid), str(actor_user_id) if actor_user_id else None,
            "analysis_run", "analysis", None, {"type": analysis_type, "via": "huume"},
        )

    # Mirrors run_recommendations_inline's post-persist hook (ai_analysis.py)
    # so a chat-originated recommendations run maps training topics exactly
    # like the REST run does — best-effort, never fails the tool result.
    if analysis_type == "recommendations" and result.get("training_recommended") and company_id_for_training:
        try:
            await _auto_map_training_topics(str(iid), str(company_id_for_training))
        except Exception:
            logger.exception("huume: training-topic auto-map failed for incident %s", iid)

    return {
        "status": "ok", "cached": False, "incident_id": str(iid), "analysis": result,
        "note": "Cached — the AI Analysis tab on the incident opens pre-computed.",
    }

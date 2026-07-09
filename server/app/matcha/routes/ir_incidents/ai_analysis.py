"""AI analysis endpoints for IR Incidents.

Each endpoint kicks off (or returns cached) Gemini analysis of an incident:
- /analyze/categorize         — incident type taxonomy
- /analyze/severity           — severity scoring
- /analyze/root-cause         — five-whys + structured causes
- /analyze/recommendations    — corrective action recommendations (streaming)
- /analyze/similar            — precedent matches (streaming)
- /policy-mapping             — handbook/policy violation mapping
- /analyze/policy-mapping     — force-refresh policy mapping
- /consistency-guidance       — outcome consistency against prior incidents
- DELETE /analyze/{type}      — invalidate cached analysis

Heavy AI calls and helpers `_auto_map_policy_violations` /
`_get_handbook_policy_entries` continue to live in `_legacy.py` for now —
they are also used by the CRUD path. They will migrate to `_shared.py` in
step 10.
"""
import asyncio
import json
import logging
from datetime import timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.ir_incident import (
    ActionProbability,
    CategorizationAnalysis,
    ConsistencyGuidance,
    PolicyMappingAnalysis,
    PrecedentAnalysis,
    PrecedentMatch,
    RecommendationItem,
    RecommendationsAnalysis,
    RootCauseAnalysis,
    SeverityAnalysis,
)

# Helpers that still live in _legacy.py; will move to _shared.py in step 10.
# (_auto_map_policy_violations and _get_handbook_policy_entries are defined
# in this file; _legacy.py imports them lazily at call-time.)
from ._shared import (
    ANALYSIS_TYPES,
    _get_incident_with_company_check,
    _safe_json_loads,
    _sse,
    _utc_now_naive,
    log_audit,
    parse_witnesses,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/{incident_id}/analyze/categorize", response_model=CategorizationAnalysis)
async def analyze_categorization(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Auto-categorize an incident using AI."""
    from app.matcha.services.ir_analysis import get_ir_analyzer, IRAnalysisError

    async with get_connection() as conn:
        row = await _get_incident_with_company_check(
            conn, incident_id, current_user,
            columns="id, title, description, location, reported_by_name",
        )

        # Check for cached analysis
        cached = await conn.fetchrow(
            """
            SELECT analysis_data FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'categorization'
            ORDER BY generated_at DESC LIMIT 1
            """,
            str(incident_id),
        )

        if cached:
            result = _safe_json_loads(cached["analysis_data"])
            return CategorizationAnalysis(
                suggested_type=result["suggested_type"],
                confidence=result["confidence"],
                reasoning=result["reasoning"],
                generated_at=result["generated_at"],
            )

        # Run AI analysis with fallback to stale cache on failure
        try:
            analyzer = get_ir_analyzer()
            result = await analyzer.categorize_incident(
                title=row["title"],
                description=row["description"],
                location=row["location"],
                reported_by=row["reported_by_name"],
            )
        except IRAnalysisError as e:
            # Gemini failed - try to return stale cache if available
            if cached:
                result = _safe_json_loads(cached["analysis_data"])
                return CategorizationAnalysis(
                    suggested_type=result["suggested_type"],
                    confidence=result["confidence"],
                    reasoning=result["reasoning"],
                    generated_at=result["generated_at"],
                    from_cache=True,
                    cache_reason=str(e),
                )
            logger.error(f"AI analysis failed for incident {incident_id}: {e}")
            raise HTTPException(status_code=503, detail="Analysis temporarily unavailable. Please try again later.")

        # Cache the result
        await conn.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, 'categorization', $2)
            """,
            str(incident_id),
            json.dumps(result),
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "analysis_run",
            "analysis",
            None,
            {"type": "categorization"},
            request.client.host if request.client else None,
        )

        return CategorizationAnalysis(
            suggested_type=result["suggested_type"],
            confidence=result["confidence"],
            reasoning=result["reasoning"],
            generated_at=result["generated_at"],
        )


@router.post("/{incident_id}/analyze/severity", response_model=SeverityAnalysis)
async def analyze_severity(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Assess incident severity using AI."""
    from app.matcha.services.ir_analysis import get_ir_analyzer, IRAnalysisError

    async with get_connection() as conn:
        row = await _get_incident_with_company_check(conn, incident_id, current_user)

        # Check for cached analysis
        cached = await conn.fetchrow(
            """
            SELECT analysis_data FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'severity'
            ORDER BY generated_at DESC LIMIT 1
            """,
            str(incident_id),
        )

        if cached:
            result = _safe_json_loads(cached["analysis_data"])
            return SeverityAnalysis(
                suggested_severity=result["suggested_severity"],
                factors=result["factors"],
                reasoning=result["reasoning"],
                generated_at=result["generated_at"],
            )

        # Run AI analysis with fallback to stale cache on failure
        try:
            analyzer = get_ir_analyzer()
            category_data = json.loads(row["category_data"]) if isinstance(row.get("category_data"), str) else row.get("category_data")

            result = await analyzer.assess_severity(
                title=row["title"],
                description=row["description"],
                incident_type=row["incident_type"],
                location=row["location"],
                category_data=category_data,
            )
        except IRAnalysisError as e:
            # Gemini failed - try to return stale cache if available
            if cached:
                result = _safe_json_loads(cached["analysis_data"])
                return SeverityAnalysis(
                    suggested_severity=result["suggested_severity"],
                    factors=result["factors"],
                    reasoning=result["reasoning"],
                    generated_at=result["generated_at"],
                    from_cache=True,
                    cache_reason=str(e),
                )
            logger.error(f"AI analysis failed for incident {incident_id}: {e}")
            raise HTTPException(status_code=503, detail="Analysis temporarily unavailable. Please try again later.")

        # Cache the result
        await conn.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, 'severity', $2)
            """,
            str(incident_id),
            json.dumps(result),
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "analysis_run",
            "analysis",
            None,
            {"type": "severity"},
            request.client.host if request.client else None,
        )

        return SeverityAnalysis(
            suggested_severity=result["suggested_severity"],
            factors=result["factors"],
            reasoning=result["reasoning"],
            generated_at=result["generated_at"],
        )


async def run_root_cause_inline(
    incident_id: UUID,
    current_user,
    *,
    ip_address: Optional[str] = None,
    use_cache: bool = True,
) -> RootCauseAnalysis:
    """Run root cause analysis without SSE wrapping. Returns the result.

    Callable from the IR Copilot accept handler (or anywhere else that
    needs the analysis to actually happen, not just stream progress).

    Persists to ``ir_incident_analysis`` + audit-logs identically to the
    SSE endpoint. Raises ``IRAnalysisError`` if the LLM fails AND no
    cached row exists.
    """
    from app.matcha.services.ir_analysis import get_ir_analyzer, IRAnalysisError

    async with get_connection() as conn:
        row = await _get_incident_with_company_check(conn, incident_id, current_user)
        row = dict(row)

        cached = None
        if use_cache:
            cached = await conn.fetchrow(
                """
                SELECT analysis_data FROM ir_incident_analysis
                WHERE incident_id = $1 AND analysis_type = 'root_cause'
                ORDER BY generated_at DESC LIMIT 1
                """,
                str(incident_id),
            )

    if cached:
        result = _safe_json_loads(cached["analysis_data"])
        return RootCauseAnalysis(
            primary_cause=result["primary_cause"],
            contributing_factors=result["contributing_factors"],
            prevention_suggestions=result["prevention_suggestions"],
            reasoning=result["reasoning"],
            generated_at=result["generated_at"],
            from_cache=True,
        )

    category_data = json.loads(row["category_data"]) if isinstance(row.get("category_data"), str) else row.get("category_data")
    witnesses = parse_witnesses(row.get("witnesses"))

    try:
        analyzer = get_ir_analyzer()
        result = await analyzer.analyze_root_cause(
            title=row["title"],
            description=row["description"],
            incident_type=row["incident_type"],
            severity=row["severity"],
            location=row["location"],
            category_data=category_data,
            witnesses=[w.model_dump() for w in witnesses],
        )
    except IRAnalysisError:
        logger.exception("Root-cause analysis failed for incident %s", incident_id)
        raise

    async with get_connection() as conn2:
        await conn2.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, 'root_cause', $2)
            """,
            str(incident_id),
            json.dumps(result),
        )
        await log_audit(
            conn2,
            str(incident_id),
            str(current_user.id),
            "analysis_run",
            "analysis",
            None,
            {"type": "root_cause"},
            ip_address,
        )

    return RootCauseAnalysis(
        primary_cause=result["primary_cause"],
        contributing_factors=result["contributing_factors"],
        prevention_suggestions=result["prevention_suggestions"],
        reasoning=result["reasoning"],
        generated_at=result["generated_at"],
    )


async def run_followup_questions_inline(
    incident_id: UUID,
    current_user,
    *,
    ip_address: Optional[str] = None,
    use_cache: bool = True,
) -> dict:
    """Generate incident-specific follow-up investigation questions inline.

    Drives the IR Copilot investigation phase: the deterministic flow asks
    for these questions before closing so the record is more than the OSHA
    checkboxes. Persists to ``ir_incident_analysis`` under
    ``followup_questions`` and audit-logs like the other inline runners.

    Returns the analysis dict (``questions`` + ``reasoning``). Raises
    ``IRAnalysisError`` if the LLM fails AND no cached row exists.
    """
    from app.matcha.services.ir_analysis import get_ir_analyzer, IRAnalysisError

    async with get_connection() as conn:
        row = await _get_incident_with_company_check(conn, incident_id, current_user)
        row = dict(row)

        cached = None
        if use_cache:
            cached = await conn.fetchrow(
                """
                SELECT analysis_data FROM ir_incident_analysis
                WHERE incident_id = $1 AND analysis_type = 'followup_questions'
                ORDER BY generated_at DESC LIMIT 1
                """,
                str(incident_id),
            )

    if cached:
        return _safe_json_loads(cached["analysis_data"])

    category_data = json.loads(row["category_data"]) if isinstance(row.get("category_data"), str) else row.get("category_data")
    witnesses = parse_witnesses(row.get("witnesses"))

    try:
        analyzer = get_ir_analyzer()
        result = await analyzer.generate_followup_questions(
            title=row["title"],
            description=row["description"],
            incident_type=row["incident_type"],
            severity=row["severity"],
            location=row["location"],
            category_data=category_data,
            witnesses=[w.model_dump() for w in witnesses],
        )
    except IRAnalysisError:
        logger.exception("Follow-up questions failed for incident %s", incident_id)
        raise

    async with get_connection() as conn2:
        await conn2.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, 'followup_questions', $2)
            """,
            str(incident_id),
            json.dumps(result),
        )
        await log_audit(
            conn2,
            str(incident_id),
            str(current_user.id),
            "analysis_run",
            "analysis",
            None,
            {"type": "followup_questions"},
            ip_address,
        )

    return result


@router.post("/{incident_id}/analyze/root-cause")
async def analyze_root_cause(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Perform root cause analysis using AI (SSE stream).

    Streams phase events for the UI. Core work delegates to
    ``run_root_cause_inline`` so the IR Copilot accept handler can invoke
    the same logic without SSE wrapping.
    """
    from app.matcha.services.ir_analysis import IRAnalysisError

    # Pre-fetch for auth + cached probe (mirrors run_root_cause_inline's
    # cached path so the SSE can report from_cache without re-querying).
    async with get_connection() as conn:
        await _get_incident_with_company_check(conn, incident_id, current_user)
        cached = await conn.fetchrow(
            """
            SELECT analysis_data FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'root_cause'
            ORDER BY generated_at DESC LIMIT 1
            """,
            str(incident_id),
        )

    ip_address = request.client.host if request.client else None

    async def event_stream():
        yield _sse({"type": "phase", "step": "loading_incident", "message": "Loading incident data..."})
        await asyncio.sleep(0.05)

        yield _sse({"type": "phase", "step": "checking_cache", "message": "Checking analysis cache..."})
        await asyncio.sleep(0.05)

        if cached:
            rc = await run_root_cause_inline(incident_id, current_user, ip_address=ip_address)
            yield _sse({"type": "cached", "message": "Using cached analysis result", "result": rc.model_dump(mode='json')})
            yield "data: [DONE]\n\n"
            return

        yield _sse({"type": "phase", "step": "preparing_context", "message": "Preparing incident context for AI..."})
        await asyncio.sleep(0.05)

        yield _sse({"type": "phase", "step": "analyzing", "message": "AI analyzing root cause..."})

        try:
            rc = await run_root_cause_inline(incident_id, current_user, ip_address=ip_address)
        except IRAnalysisError as e:
            logger.error(f"AI analysis failed for incident {incident_id}: {e}")
            yield _sse({"type": "error", "message": "Analysis temporarily unavailable. Please try again later."})
            yield "data: [DONE]\n\n"
            return

        yield _sse({"type": "phase", "step": "validating", "message": "Validating AI response..."})
        await asyncio.sleep(0.05)

        yield _sse({"type": "phase", "step": "caching", "message": "Caching analysis result..."})

        yield _sse({"type": "complete", "result": rc.model_dump(mode='json')})
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def run_recommendations_inline(
    incident_id: UUID,
    current_user,
    *,
    ip_address: Optional[str] = None,
    use_cache: bool = True,
) -> RecommendationsAnalysis:
    """Generate corrective-action recommendations without SSE wrapping.

    Callable from the IR Copilot accept handler so the deterministic flow's
    "Suggest actions" step runs inline (and caches to ir_incident_analysis)
    instead of bouncing the user to the AI Analysis tab. Mirrors
    ``analyze_recommendations``' data-gathering + caching; raises
    ``IRAnalysisError`` if the LLM fails AND no cached row exists.
    """
    from app.matcha.services.ir_analysis import get_ir_analyzer, IRAnalysisError
    from app.matcha.models.ir_incident import RecommendationItem

    async with get_connection() as conn:
        row = await _get_incident_with_company_check(conn, incident_id, current_user)
        row = dict(row)

        company_name = industry = company_size = ir_guidance_blurb = None
        if row.get("company_id"):
            company = await conn.fetchrow(
                "SELECT name, industry, size, ir_guidance_blurb FROM companies WHERE id = $1",
                row["company_id"],
            )
            if company:
                company_name = company["name"]
                industry = company["industry"]
                company_size = company["size"]
                ir_guidance_blurb = company["ir_guidance_blurb"]

        city = state = None
        if row.get("location_id"):
            location = await conn.fetchrow(
                "SELECT city, state FROM business_locations WHERE id = $1",
                row["location_id"],
            )
            if location:
                city = location["city"]
                state = location["state"]

        cached = None
        if use_cache:
            cached = await conn.fetchrow(
                """
                SELECT analysis_data FROM ir_incident_analysis
                WHERE incident_id = $1 AND analysis_type = 'recommendations'
                ORDER BY generated_at DESC LIMIT 1
                """,
                str(incident_id),
            )

    if cached:
        result = _safe_json_loads(cached["analysis_data"])
        return RecommendationsAnalysis(
            recommendations=[RecommendationItem(**r) for r in result["recommendations"]],
            summary=result["summary"],
            generated_at=result["generated_at"],
            from_cache=True,
        )

    try:
        analyzer = get_ir_analyzer()
        result = await analyzer.generate_recommendations(
            title=row["title"],
            description=row["description"],
            incident_type=row["incident_type"],
            severity=row["severity"],
            root_cause=row["root_cause"],
            company_name=company_name,
            industry=industry,
            company_size=company_size,
            city=city,
            state=state,
            ir_guidance_blurb=ir_guidance_blurb,
        )
    except IRAnalysisError:
        logger.exception("Recommendations analysis failed for incident %s", incident_id)
        raise

    async with get_connection() as conn2:
        await conn2.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, 'recommendations', $2)
            """,
            str(incident_id),
            json.dumps(result),
        )
        await log_audit(
            conn2,
            str(incident_id),
            str(current_user.id),
            "analysis_run",
            "analysis",
            None,
            {"type": "recommendations"},
            ip_address,
        )

    return RecommendationsAnalysis(
        recommendations=[RecommendationItem(**r) for r in result["recommendations"]],
        summary=result["summary"],
        generated_at=result["generated_at"],
    )


@router.post("/{incident_id}/analyze/recommendations")
async def analyze_recommendations(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Generate corrective action recommendations using AI (SSE stream)."""
    from app.matcha.services.ir_analysis import get_ir_analyzer, IRAnalysisError
    from app.matcha.models.ir_incident import RecommendationItem

    # Pre-fetch all data before starting the stream
    async with get_connection() as conn:
        row = await _get_incident_with_company_check(conn, incident_id, current_user)
        row = dict(row)

        company_name = None
        industry = None
        company_size = None
        ir_guidance_blurb = None

        if row.get("company_id"):
            company = await conn.fetchrow(
                "SELECT name, industry, size, ir_guidance_blurb FROM companies WHERE id = $1",
                row["company_id"],
            )
            if company:
                company_name = company["name"]
                industry = company["industry"]
                company_size = company["size"]
                ir_guidance_blurb = company["ir_guidance_blurb"]

        city = None
        state = None

        if row.get("location_id"):
            location = await conn.fetchrow(
                "SELECT city, state FROM business_locations WHERE id = $1",
                row["location_id"],
            )
            if location:
                city = location["city"]
                state = location["state"]

        cached = await conn.fetchrow(
            """
            SELECT analysis_data FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'recommendations'
            ORDER BY generated_at DESC LIMIT 1
            """,
            str(incident_id),
        )

    async def event_stream():
        yield _sse({"type": "phase", "step": "loading_incident", "message": "Loading incident data..."})
        await asyncio.sleep(0.05)

        yield _sse({"type": "phase", "step": "loading_context", "message": "Loading company & location context..."})
        await asyncio.sleep(0.05)

        yield _sse({"type": "phase", "step": "checking_cache", "message": "Checking analysis cache..."})
        await asyncio.sleep(0.05)

        if cached:
            result = _safe_json_loads(cached["analysis_data"])
            rec = RecommendationsAnalysis(
                recommendations=[RecommendationItem(**r) for r in result["recommendations"]],
                summary=result["summary"],
                generated_at=result["generated_at"],
                from_cache=True,
            )
            yield _sse({"type": "cached", "message": "Using cached analysis result", "result": rec.model_dump(mode='json')})
            yield "data: [DONE]\n\n"
            return

        yield _sse({"type": "phase", "step": "building_context", "message": "Building analysis context..."})
        await asyncio.sleep(0.05)

        yield _sse({"type": "phase", "step": "analyzing", "message": "AI generating recommendations..."})

        try:
            analyzer = get_ir_analyzer()
            result = await analyzer.generate_recommendations(
                title=row["title"],
                description=row["description"],
                incident_type=row["incident_type"],
                severity=row["severity"],
                root_cause=row["root_cause"],
                company_name=company_name,
                industry=industry,
                company_size=company_size,
                city=city,
                state=state,
                ir_guidance_blurb=ir_guidance_blurb,
            )
        except IRAnalysisError as e:
            if cached:
                result_data = _safe_json_loads(cached["analysis_data"])
                rec = RecommendationsAnalysis(
                    recommendations=[RecommendationItem(**r) for r in result_data["recommendations"]],
                    summary=result_data["summary"],
                    generated_at=result_data["generated_at"],
                    from_cache=True,
                    cache_reason=str(e),
                )
                yield _sse({"type": "cached", "message": f"AI failed, using stale cache: {e}", "result": rec.model_dump(mode='json')})
                yield "data: [DONE]\n\n"
                return
            logger.error(f"AI analysis failed for incident {incident_id}: {e}")
            yield _sse({"type": "error", "message": "Analysis temporarily unavailable. Please try again later."})
            yield "data: [DONE]\n\n"
            return

        yield _sse({"type": "phase", "step": "validating", "message": "Validating AI response..."})
        await asyncio.sleep(0.05)

        yield _sse({"type": "phase", "step": "caching", "message": "Caching analysis result..."})

        async with get_connection() as conn2:
            await conn2.execute(
                """
                INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
                VALUES ($1, 'recommendations', $2)
                """,
                str(incident_id),
                json.dumps(result),
            )
            await log_audit(
                conn2,
                str(incident_id),
                str(current_user.id),
                "analysis_run",
                "analysis",
                None,
                {"type": "recommendations"},
                request.client.host if request.client else None,
            )

        rec = RecommendationsAnalysis(
            recommendations=[RecommendationItem(**r) for r in result["recommendations"]],
            summary=result["summary"],
            generated_at=result["generated_at"],
        )
        yield _sse({"type": "complete", "result": rec.model_dump(mode='json')})
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{incident_id}/analyze/similar")
async def analyze_similar_incidents(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Find precedent incidents using hybrid similarity scoring (SSE stream)."""
    from app.matcha.services.ir_precedent import find_precedents_stream

    # Pre-fetch data before starting the stream
    async with get_connection() as conn:
        row = await _get_incident_with_company_check(conn, incident_id, current_user)
        row = dict(row)

        cached = await conn.fetchrow(
            """
            SELECT analysis_data FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'similar'
            ORDER BY generated_at DESC LIMIT 1
            """,
            str(incident_id),
        )

    async def event_stream():
        yield _sse({"type": "phase", "step": "loading_incident", "message": "Loading incident data..."})
        await asyncio.sleep(0.05)

        yield _sse({"type": "phase", "step": "checking_cache", "message": "Checking analysis cache..."})
        await asyncio.sleep(0.05)

        if cached:
            result = _safe_json_loads(cached["analysis_data"])
            if "precedents" in result:
                result["from_cache"] = True
                pa = PrecedentAnalysis(**result)
                yield _sse({"type": "cached", "message": "Using cached precedent analysis", "result": pa.model_dump(mode='json')})
                yield "data: [DONE]\n\n"
                return

        # Stream precedent analysis phases
        result = None
        async with get_connection() as conn2:
            async for event in find_precedents_stream(str(incident_id), conn2, incident_row=row):
                if event.get("type") == "result":
                    result = event["data"]
                else:
                    yield _sse(event)

        if result is None:
            yield _sse({"type": "error", "message": "Analysis produced no result."})
            yield "data: [DONE]\n\n"
            return

        yield _sse({"type": "phase", "step": "caching", "message": "Caching precedent analysis..."})

        async with get_connection() as conn3:
            await conn3.execute(
                """
                INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
                VALUES ($1, 'similar', $2)
                ON CONFLICT (incident_id, analysis_type)
                DO UPDATE SET analysis_data = $2, generated_at = now()
                """,
                str(incident_id),
                json.dumps(result),
            )
            # Invalidate stale consistency guidance since precedents changed
            await conn3.execute(
                "DELETE FROM ir_incident_analysis WHERE incident_id = $1 AND analysis_type = 'consistency'",
                str(incident_id),
            )
            await log_audit(
                conn3,
                str(incident_id),
                str(current_user.id),
                "analysis_run",
                "analysis",
                None,
                {"type": "similar"},
                request.client.host if request.client else None,
            )

        pa = PrecedentAnalysis(**result)
        yield _sse({"type": "complete", "result": pa.model_dump(mode='json')})
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ===========================================
# Policy Mapping
# ===========================================


async def _get_handbook_policy_entries(conn, company_id) -> list[dict]:
    """Fetch active handbook sections as policy-compatible dicts for policy mapping."""
    handbook = await conn.fetchrow(
        """
        SELECT id, title, active_version
        FROM handbooks
        WHERE company_id = $1 AND status = 'active'
        ORDER BY published_at DESC NULLS LAST, updated_at DESC
        LIMIT 1
        """,
        company_id,
    )
    if not handbook:
        return []

    version_id = await conn.fetchval(
        "SELECT id FROM handbook_versions WHERE handbook_id = $1 AND version_number = $2",
        handbook["id"], handbook["active_version"],
    )
    if version_id is None:
        version_id = await conn.fetchval(
            "SELECT id FROM handbook_versions WHERE handbook_id = $1 ORDER BY version_number DESC LIMIT 1",
            handbook["id"],
        )
    if version_id is None:
        return []

    sections = await conn.fetch(
        """
        SELECT id, title, content
        FROM handbook_sections
        WHERE handbook_version_id = $1 AND content IS NOT NULL AND content != ''
        ORDER BY section_order ASC
        """,
        version_id,
    )
    handbook_title = handbook["title"] or "Employee Handbook"
    return [
        {
            "id": str(s["id"]),
            "title": f"{handbook_title} — {s['title']}" if s["title"] else handbook_title,
            "description": (s["content"] or "")[:300],
            "content": s["content"],
        }
        for s in sections
        if (s["content"] or "").strip()
    ]


async def _auto_map_policy_violations(incident_id: str, company_id: str):
    """Background task: auto-map incident to company policies."""
    try:
        from app.matcha.services.ir_analysis import get_ir_analyzer

        async with get_connection() as conn:
            # Fetch incident
            row = await conn.fetchrow(
                "SELECT title, description, incident_type, severity, category_data FROM ir_incidents WHERE id = $1",
                incident_id,
            )
            if not row:
                return

            # Fetch active policies + handbook sections
            policies = await conn.fetch(
                "SELECT id, title, description, content FROM policies WHERE company_id = $1 AND status = 'active'",
                company_id,
            )
            handbook_policies = await _get_handbook_policy_entries(conn, company_id)

            if not policies and not handbook_policies:
                # Cache empty result
                empty_result = {
                    "matches": [],
                    "summary": "No active policies or handbook found for this company.",
                    "no_matching_policies": True,
                    "generated_at": _utc_now_naive().isoformat(),
                }
                await conn.execute(
                    """
                    INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
                    VALUES ($1, 'policy_mapping', $2)
                    ON CONFLICT (incident_id, analysis_type)
                    DO UPDATE SET analysis_data = $2, generated_at = now()
                    """,
                    incident_id,
                    json.dumps(empty_result),
                )
                return

            policies_list = [
                {"id": str(p["id"]), "title": p["title"], "description": p.get("description"), "content": p.get("content")}
                for p in policies
            ] + handbook_policies

            analyzer = get_ir_analyzer()
            result = await analyzer.map_policy_violations(
                title=row["title"],
                description=row.get("description") or "",
                incident_type=row["incident_type"],
                severity=row["severity"],
                category_data=_safe_json_loads(row.get("category_data"), {}),
                policies=policies_list,
            )

            await conn.execute(
                """
                INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
                VALUES ($1, 'policy_mapping', $2)
                ON CONFLICT (incident_id, analysis_type)
                DO UPDATE SET analysis_data = $2, generated_at = now()
                """,
                incident_id,
                json.dumps(result),
            )
    except Exception as e:
        logger.warning(f"Auto policy mapping failed for incident {incident_id}: {e}")


@router.get("/{incident_id}/policy-mapping", response_model=PolicyMappingAnalysis)
async def get_policy_mapping(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Get policy violation mapping for an incident."""
    from app.matcha.services.ir_analysis import get_ir_analyzer

    async with get_connection() as conn:
        inc = await _get_incident_with_company_check(conn, incident_id, current_user, columns="id, title, description, incident_type, severity, category_data, company_id")

        # Check cache (<24h)
        cached = await conn.fetchrow(
            """
            SELECT analysis_data, generated_at FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'policy_mapping'
            ORDER BY generated_at DESC LIMIT 1
            """,
            str(incident_id),
        )

        if cached:
            cache_age = _utc_now_naive() - cached["generated_at"]
            if cache_age < timedelta(hours=24):
                result = _safe_json_loads(cached["analysis_data"])
                result["from_cache"] = True
                return PolicyMappingAnalysis(**result)

        # Fetch active policies + handbook sections
        company_id = inc.get("company_id")
        if not company_id:
            return PolicyMappingAnalysis(
                matches=[], summary="No company associated with this incident.",
                no_matching_policies=True, generated_at=_utc_now_naive().isoformat(),
            )

        policies = await conn.fetch(
            "SELECT id, title, description, content FROM policies WHERE company_id = $1 AND status = 'active'",
            company_id,
        )

        # Also include active handbook sections as policy sources
        handbook_policies = await _get_handbook_policy_entries(conn, company_id)

        all_policies = list(policies) + handbook_policies

        if not all_policies:
            empty = PolicyMappingAnalysis(
                matches=[], summary="No active policies or handbook found for this company.",
                no_matching_policies=True, generated_at=_utc_now_naive().isoformat(),
            )
            # Cache
            await conn.execute(
                """
                INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
                VALUES ($1, 'policy_mapping', $2)
                ON CONFLICT (incident_id, analysis_type)
                DO UPDATE SET analysis_data = $2, generated_at = now()
                """,
                str(incident_id),
                json.dumps(empty.model_dump(mode='json')),
            )
            return empty

        policies_list = [
            {"id": str(p["id"]), "title": p["title"], "description": p.get("description"), "content": p.get("content")}
            for p in policies
        ] + handbook_policies

        try:
            analyzer = get_ir_analyzer()
            result = await analyzer.map_policy_violations(
                title=inc["title"],
                description=inc.get("description") or "",
                incident_type=inc["incident_type"],
                severity=inc["severity"],
                category_data=_safe_json_loads(inc.get("category_data"), {}),
                policies=policies_list,
            )
        except Exception as e:
            logger.warning(f"Policy mapping failed: {e}")
            raise HTTPException(status_code=502, detail="Policy mapping analysis failed")

        # Cache result
        await conn.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, 'policy_mapping', $2)
            ON CONFLICT (incident_id, analysis_type)
            DO UPDATE SET analysis_data = $2, generated_at = now()
            """,
            str(incident_id),
            json.dumps(result),
        )

        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "analysis_run",
            "analysis",
            None,
            {"type": "policy_mapping"},
            request.client.host if request.client else None,
        )

        return PolicyMappingAnalysis(**result)


@router.post("/{incident_id}/analyze/policy-mapping", response_model=PolicyMappingAnalysis)
async def refresh_policy_mapping(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Force-refresh policy mapping for an incident."""
    async with get_connection() as conn:
        await _get_incident_with_company_check(conn, incident_id, current_user, columns="id")

        # Delete existing cache
        await conn.execute(
            "DELETE FROM ir_incident_analysis WHERE incident_id = $1 AND analysis_type = 'policy_mapping'",
            str(incident_id),
        )

    # Delegate to the GET handler which will compute fresh
    return await get_policy_mapping(incident_id, request, current_user)


@router.get("/{incident_id}/consistency-guidance", response_model=ConsistencyGuidance)
async def get_consistency_guidance(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Get consistency guidance based on precedent analysis for an incident."""
    from app.matcha.services.ir_consistency import compute_outcome_distribution

    async with get_connection() as conn:
        # Verify incident exists and belongs to company
        await _get_incident_with_company_check(conn, incident_id, current_user, columns="id")

        # Read cached similar analysis to get precedents
        similar_row = await conn.fetchrow(
            """
            SELECT analysis_data FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'similar'
            ORDER BY generated_at DESC LIMIT 1
            """,
            str(incident_id),
        )

        if not similar_row:
            return ConsistencyGuidance(
                sample_size=0,
                effective_sample_size=0.0,
                confidence="insufficient",
                unprecedented=True,
                generated_at=_utc_now_naive().isoformat(),
            )

        similar_data = _safe_json_loads(similar_row["analysis_data"])
        precedents = similar_data.get("precedents", [])

        if not precedents:
            return ConsistencyGuidance(
                sample_size=0,
                effective_sample_size=0.0,
                confidence="insufficient",
                unprecedented=True,
                generated_at=_utc_now_naive().isoformat(),
            )

        # Check for cached consistency result (<24h)
        cached = await conn.fetchrow(
            """
            SELECT analysis_data, generated_at FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'consistency'
            ORDER BY generated_at DESC LIMIT 1
            """,
            str(incident_id),
        )

        if cached:
            cache_age = _utc_now_naive() - cached["generated_at"]
            if cache_age < timedelta(hours=24):
                result = _safe_json_loads(cached["analysis_data"])
                result["from_cache"] = True
                return ConsistencyGuidance(**result)

        # Compute fresh guidance
        settings = get_settings()
        try:
            result = await compute_outcome_distribution(
                precedents,
                api_key=settings.gemini_api_key,
            )
        except Exception as e:
            logger.warning(f"Consistency guidance computation failed: {e}")
            return ConsistencyGuidance(
                sample_size=len(precedents),
                effective_sample_size=0.0,
                confidence="insufficient",
                unprecedented=False,
                generated_at=_utc_now_naive().isoformat(),
            )

        # Cache result
        await conn.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, 'consistency', $2)
            ON CONFLICT (incident_id, analysis_type)
            DO UPDATE SET analysis_data = $2, generated_at = now()
            """,
            str(incident_id),
            json.dumps(result),
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "analysis_run",
            "analysis",
            None,
            {"type": "consistency"},
            request.client.host if request.client else None,
        )

        return ConsistencyGuidance(**result)


@router.delete("/{incident_id}/analyze/{analysis_type}")
async def clear_analysis_cache(
    incident_id: UUID,
    analysis_type: ANALYSIS_TYPES,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Clear cached analysis to force re-analysis."""
    async with get_connection() as conn:
        # Verify incident exists and belongs to company
        await _get_incident_with_company_check(conn, incident_id, current_user, columns="id")

        # Delete cached analysis
        await conn.execute(
            """
            DELETE FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = $2
            """,
            str(incident_id),
            analysis_type,
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "analysis_cleared",
            "analysis",
            None,
            {"type": analysis_type},
            request.client.host if request.client else None,
        )

        return {"message": f"Analysis cache cleared for {analysis_type}"}



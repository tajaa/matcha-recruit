"""AI analysis: timeline, discrepancies, policy-check, similar-cases."""
import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Query, Request

from ....database import get_connection
from ...dependencies import require_admin_or_client, get_client_company_id
from ....core.models.auth import CurrentUser
from ...models.er_case import (
    TaskStatusResponse,
)

from ._shared import (
    logger,
    log_audit,
    _verify_case_company,
)

router = APIRouter()


@router.post("/{case_id}/analysis/timeline", response_model=TaskStatusResponse)
async def generate_timeline(
    case_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
    model: Optional[str] = Query(None, pattern="^(flash|pro)$"),
):
    """Generate timeline analysis. Queues async task or runs synchronously."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        # Verify case exists and has documents
        doc_count = await conn.fetchval(
            "SELECT COUNT(*) FROM er_case_documents WHERE case_id = $1 AND processing_status = 'completed'",
            case_id,
        )

        if not doc_count:
            raise HTTPException(
                status_code=400,
                detail="No processed documents found. Upload and process documents first.",
            )

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "analysis_requested",
            "timeline",
            None,
            {},
            request.client.host if request.client else None,
        )

    # Try to queue analysis task via Celery, fall back to sync
    celery_available = False
    try:
        from app.workers.tasks.er_analysis import run_timeline_analysis
        from app.workers.celery_app import celery_app
        ping_responses = celery_app.control.ping(timeout=1)
        if not ping_responses:
            raise RuntimeError("No Celery workers responded to ping")
        task = run_timeline_analysis.delay(str(case_id), model_override=model)
        celery_available = True
        logger.info(f"Queued timeline analysis for case {case_id}, task_id={task.id}")
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Timeline analysis queued",
        )
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}), running timeline analysis synchronously")

    # Fallback: run synchronously
    if not celery_available:
        try:
            from app.workers.tasks.er_analysis import _run_timeline_analysis
            logger.info(f"Starting synchronous timeline analysis for case {case_id}")
            result = await _run_timeline_analysis(str(case_id), model_override=model)
            logger.info(f"Timeline analysis completed for case {case_id}: {result}")
            return TaskStatusResponse(
                task_id=None,
                status="completed",
                message=f"Timeline analysis completed: {result.get('events_found', 0)} events found",
            )
        except Exception as sync_error:
            logger.error(f"Timeline analysis failed for case {case_id}: {sync_error}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Timeline analysis failed: {sync_error}")


@router.get("/{case_id}/analysis/timeline")
async def get_timeline(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get cached timeline analysis."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        row = await conn.fetchrow(
            """
            SELECT analysis_data, source_documents, generated_at
            FROM er_case_analysis
            WHERE case_id = $1 AND analysis_type = 'timeline'
            """,
            case_id,
        )

        if not row:
            return {
                "analysis": {
                    "events": [],
                    "gaps_identified": [],
                    "timeline_summary": "",
                },
                "source_documents": [],
                "generated_at": None,
            }

        # Handle case where JSONB might be returned as string
        analysis = row["analysis_data"]
        if isinstance(analysis, str):
            analysis = json.loads(analysis)

        source_docs = row["source_documents"]
        if isinstance(source_docs, str):
            source_docs = json.loads(source_docs)

        return {
            "analysis": analysis,
            "source_documents": source_docs,
            "generated_at": row["generated_at"],
        }


@router.post("/{case_id}/analysis/discrepancies", response_model=TaskStatusResponse)
async def generate_discrepancies(
    case_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
    model: Optional[str] = Query(None, pattern="^(flash|pro)$"),
):
    """Generate discrepancy analysis. Queues async task or runs synchronously."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        doc_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM er_case_documents
            WHERE case_id = $1
              AND processing_status = 'completed'
              AND document_type != 'policy'
            """,
            case_id,
        )

        if doc_count < 2:
            raise HTTPException(
                status_code=400,
                detail="Upload at least 2 completed non-policy documents for discrepancy analysis.",
            )

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "analysis_requested",
            "discrepancies",
            None,
            {},
            request.client.host if request.client else None,
        )

    # Try to queue analysis task via Celery, fall back to sync
    celery_available = False
    try:
        from app.workers.tasks.er_analysis import run_discrepancy_analysis
        from app.workers.celery_app import celery_app
        ping_responses = celery_app.control.ping(timeout=1)
        if not ping_responses:
            raise RuntimeError("No Celery workers responded to ping")
        task = run_discrepancy_analysis.delay(str(case_id), model_override=model)
        celery_available = True
        logger.info(f"Queued discrepancy analysis for case {case_id}, task_id={task.id}")
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Discrepancy analysis queued",
        )
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}), running discrepancy analysis synchronously")

    # Fallback: run synchronously
    if not celery_available:
        try:
            from app.workers.tasks.er_analysis import _run_discrepancy_analysis
            logger.info(f"Starting synchronous discrepancy analysis for case {case_id}")
            result = await _run_discrepancy_analysis(str(case_id), model_override=model)
            logger.info(f"Discrepancy analysis completed for case {case_id}: {result}")
            return TaskStatusResponse(
                task_id=None,
                status="completed",
                message=f"Discrepancy analysis completed: {result.get('discrepancies_found', 0)} discrepancies found",
            )
        except Exception as sync_error:
            logger.error(f"Discrepancy analysis failed for case {case_id}: {sync_error}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Discrepancy analysis failed: {sync_error}")


@router.get("/{case_id}/analysis/discrepancies")
async def get_discrepancies(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get cached discrepancy analysis."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        row = await conn.fetchrow(
            """
            SELECT analysis_data, source_documents, generated_at
            FROM er_case_analysis
            WHERE case_id = $1 AND analysis_type = 'discrepancies'
            """,
            case_id,
        )

        if not row:
            return {
                "analysis": {
                    "discrepancies": [],
                    "credibility_notes": [],
                    "summary": "",
                },
                "source_documents": [],
                "generated_at": None,
            }

        analysis = row["analysis_data"]
        if isinstance(analysis, str):
            analysis = json.loads(analysis)

        # Normalize old-format discrepancy data to match frontend types
        for d in analysis.get("discrepancies", []):
            if "statement_1" in d and "statement_a" not in d:
                s1 = d.pop("statement_1", {})
                s2 = d.pop("statement_2", {})
                d.setdefault("subject", d.pop("description", ""))
                d.setdefault("statement_a", s1.get("quote", ""))
                d.setdefault("statement_b", s2.get("quote", ""))
                d.setdefault("source_a", f"{s1.get('speaker', '')} — {s1.get('location', '')}".strip(" —"))
                d.setdefault("source_b", f"{s2.get('speaker', '')} — {s2.get('location', '')}".strip(" —"))
                d.setdefault("notes", d.pop("analysis", None))
        for cn in analysis.get("credibility_notes", []):
            if "note" not in cn and "assessment" in cn:
                cn["note"] = cn.pop("assessment", "")
            if "factors" not in cn:
                reasoning = cn.pop("reasoning", None)
                cn["factors"] = [reasoning] if reasoning else []

        source_docs = row["source_documents"]
        if isinstance(source_docs, str):
            source_docs = json.loads(source_docs)

        return {
            "analysis": analysis,
            "source_documents": source_docs,
            "generated_at": row["generated_at"],
        }


@router.post("/{case_id}/analysis/policy-check", response_model=TaskStatusResponse)
async def run_policy_check(
    case_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
    model: Optional[str] = Query(None, pattern="^(flash|pro)$"),
):
    """Run policy violation check against all company policies. Queues async task or runs synchronously."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        # Verify we have evidence documents
        evidence_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM er_case_documents
            WHERE case_id = $1 AND document_type != 'policy' AND processing_status = 'completed'
            """,
            case_id,
        )

        if not evidence_count:
            raise HTTPException(
                status_code=400,
                detail="No evidence documents found.",
            )

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "analysis_requested",
            "policy_check",
            None,
            {},
            request.client.host if request.client else None,
        )

    # Try to queue analysis task via Celery, fall back to sync
    celery_available = False
    try:
        from app.workers.tasks.er_analysis import run_policy_check as run_policy_check_task
        from app.workers.celery_app import celery_app
        ping_responses = celery_app.control.ping(timeout=1)
        if not ping_responses:
            raise RuntimeError("No Celery workers responded to ping")
        task = run_policy_check_task.delay(str(case_id), model_override=model)
        celery_available = True
        logger.info(f"Queued policy check for case {case_id}, task_id={task.id}")
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Policy check queued",
        )
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}), running policy check synchronously")

    # Fallback: run synchronously
    if not celery_available:
        try:
            from app.workers.tasks.er_analysis import _run_policy_check
            logger.info(f"Starting synchronous policy check for case {case_id}")
            result = await _run_policy_check(str(case_id), model_override=model)
            logger.info(f"Policy check completed for case {case_id}: {result}")
            return TaskStatusResponse(
                task_id=None,
                status="completed",
                message=f"Policy check completed: {result.get('violations_found', 0)} violations found",
            )
        except Exception as sync_error:
            logger.error(f"Policy check failed for case {case_id}: {sync_error}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Policy check failed: {sync_error}")


@router.get("/{case_id}/analysis/policy-check")
async def get_policy_check(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get cached policy check analysis."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        row = await conn.fetchrow(
            """
            SELECT analysis_data, source_documents, generated_at
            FROM er_case_analysis
            WHERE case_id = $1 AND analysis_type = 'policy_check'
            """,
            case_id,
        )

        if not row:
            return {
                "analysis": {
                    "violations": [],
                    "policies_potentially_applicable": [],
                    "summary": "",
                },
                "source_documents": [],
                "generated_at": None,
            }

        analysis = row["analysis_data"]
        if isinstance(analysis, str):
            analysis = json.loads(analysis)

        source_docs = row["source_documents"]
        if isinstance(source_docs, str):
            source_docs = json.loads(source_docs)

        return {
            "analysis": analysis,
            "source_documents": source_docs,
            "generated_at": row["generated_at"],
        }


@router.post("/{case_id}/analysis/similar-cases")
async def analyze_similar_cases(
    case_id: UUID,
    refresh: bool = Query(False, description="Skip cache and recompute"),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Stream SSE progress events during similar cases analysis."""
    from starlette.responses import StreamingResponse

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async def event_stream():
        def sse(data: dict) -> str:
            return f"data: {json.dumps(data, default=str)}\n\n"

        async with get_connection() as conn:
            await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")

            use_cache = not refresh

            if use_cache:
                # Invalidate cache if the case was updated after the cached analysis
                case_updated_at = await conn.fetchval(
                    "SELECT updated_at FROM er_cases WHERE id = $1", case_id
                )
                cached_generated_at = await conn.fetchval(
                    "SELECT generated_at FROM er_case_analysis WHERE case_id = $1 AND analysis_type = 'similar_cases'",
                    case_id,
                )
                if case_updated_at and cached_generated_at and case_updated_at > cached_generated_at:
                    use_cache = False

            # Check cache first
            cached = None
            if use_cache:
                cached = await conn.fetchrow(
                    """
                    SELECT analysis_data, generated_at
                    FROM er_case_analysis
                    WHERE case_id = $1 AND analysis_type = 'similar_cases'
                    """,
                    case_id,
                )
            if cached:
                analysis = cached["analysis_data"]
                if isinstance(analysis, str):
                    analysis = json.loads(analysis)
                analysis["from_cache"] = True
                analysis["cache_reason"] = f"Cached from {cached['generated_at'].isoformat() if cached['generated_at'] else 'unknown'}"
                yield sse({"type": "cached", "message": "Using cached results", "result": analysis})
                yield "data: [DONE]\n\n"
                return

            # Stream fresh analysis
            from ...services.er_precedent import find_similar_cases_stream

            async for event in find_similar_cases_stream(str(case_id), conn):
                if event["type"] == "phase":
                    yield sse(event)
                elif event["type"] == "result":
                    result_data = event["data"]
                    # Cache the result
                    try:
                        await conn.execute(
                            """
                            INSERT INTO er_case_analysis (case_id, analysis_type, analysis_data, generated_by, generated_at)
                            VALUES ($1, 'similar_cases', $2, $3, NOW())
                            ON CONFLICT (case_id, analysis_type)
                            DO UPDATE SET analysis_data = $2, generated_by = $3, generated_at = NOW()
                            """,
                            case_id,
                            json.dumps(result_data, default=str),
                            current_user.id,
                        )
                    except Exception as cache_err:
                        logger.warning(f"Failed to cache similar cases result: {cache_err}")

                    yield sse({"type": "complete", "message": "Analysis complete", "result": result_data})

            yield "data: [DONE]\n\n"

            # Audit log
            try:
                await log_audit(
                    conn, str(case_id), str(current_user.id),
                    "analysis_requested",
                    entity_type="analysis",
                    details={"analysis_type": "similar_cases"},
                )
            except Exception:
                pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{case_id}/analysis/similar-cases")
async def get_similar_cases(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get cached similar cases analysis."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        row = await conn.fetchrow(
            """
            SELECT analysis_data, generated_at
            FROM er_case_analysis
            WHERE case_id = $1 AND analysis_type = 'similar_cases'
            """,
            case_id,
        )

        if not row:
            return {
                "matches": [],
                "pattern_summary": None,
                "outcome_distribution": {},
                "generated_at": None,
                "from_cache": False,
            }

        analysis = row["analysis_data"]
        if isinstance(analysis, str):
            analysis = json.loads(analysis)

        return analysis



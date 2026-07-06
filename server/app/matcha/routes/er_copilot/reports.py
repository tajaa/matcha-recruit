"""Report generation: summary, determination letter, report fetch."""
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Request

from ....database import get_connection
from ...dependencies import require_admin_or_client, get_client_company_id
from ....core.models.auth import CurrentUser
from ...models.er_case import (
    ReportGenerateRequest,
    TaskStatusResponse,
)

from ._shared import (
    logger,
    log_audit,
    _verify_case_company,
)

router = APIRouter()


@router.post("/{case_id}/reports/summary", response_model=TaskStatusResponse)
async def generate_summary_report(
    case_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate investigation summary report. Queues async task or runs synchronously."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "report_requested",
            "summary",
            None,
            {},
            request.client.host if request.client else None,
        )

    # Try to queue task via Celery, fall back to sync
    celery_available = False
    try:
        from app.workers.tasks.er_analysis import generate_summary_report as generate_summary_task
        from app.workers.celery_app import celery_app
        ping_responses = celery_app.control.ping(timeout=1)
        if not ping_responses:
            raise RuntimeError("No Celery workers responded to ping")
        task = generate_summary_task.delay(str(case_id), str(current_user.id))
        celery_available = True
        logger.info(f"Queued summary report for case {case_id}, task_id={task.id}")
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Summary report generation queued",
        )
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}), generating summary report synchronously")

    # Fallback: run synchronously
    if not celery_available:
        try:
            from app.workers.tasks.er_analysis import _generate_summary_report
            logger.info(f"Starting synchronous summary report generation for case {case_id}")
            result = await _generate_summary_report(str(case_id), str(current_user.id))
            logger.info(f"Summary report generated for case {case_id}: {result}")
            return TaskStatusResponse(
                task_id=None,
                status="completed",
                message="Summary report generated successfully",
            )
        except Exception as sync_error:
            logger.error(f"Summary report generation failed for case {case_id}: {sync_error}", exc_info=True)
            raise HTTPException(status_code=500, detail="Summary report generation failed")


@router.post("/{case_id}/reports/determination", response_model=TaskStatusResponse)
async def generate_determination_letter(
    case_id: UUID,
    report_request: ReportGenerateRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate determination letter. Queues async task or runs synchronously."""
    if not report_request.determination:
        raise HTTPException(
            status_code=400,
            detail="Determination is required (substantiated, unsubstantiated, inconclusive)",
        )

    valid_determinations = ["substantiated", "unsubstantiated", "inconclusive"]
    if report_request.determination not in valid_determinations:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid determination. Must be one of: {valid_determinations}",
        )

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "report_requested",
            "determination",
            None,
            {"determination": report_request.determination},
            request.client.host if request.client else None,
        )

    # Try to queue task via Celery, fall back to sync
    celery_available = False
    try:
        from app.workers.tasks.er_analysis import generate_determination_letter as generate_determination_task
        from app.workers.celery_app import celery_app
        ping_responses = celery_app.control.ping(timeout=1)
        if not ping_responses:
            raise RuntimeError("No Celery workers responded to ping")
        task = generate_determination_task.delay(
            str(case_id),
            report_request.determination,
            str(current_user.id),
        )
        celery_available = True
        logger.info(f"Queued determination letter for case {case_id}, task_id={task.id}")
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Determination letter generation queued",
        )
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}), generating determination letter synchronously")

    # Fallback: run synchronously
    if not celery_available:
        try:
            from app.workers.tasks.er_analysis import _generate_determination_letter
            logger.info(f"Starting synchronous determination letter generation for case {case_id}")
            result = await _generate_determination_letter(
                str(case_id),
                report_request.determination,
                str(current_user.id),
            )
            logger.info(f"Determination letter generated for case {case_id}: {result}")
            return TaskStatusResponse(
                task_id=None,
                status="completed",
                message="Determination letter generated successfully",
            )
        except Exception as sync_error:
            logger.error(f"Determination letter generation failed for case {case_id}: {sync_error}", exc_info=True)
            raise HTTPException(status_code=500, detail="Determination letter generation failed")


@router.get("/{case_id}/reports/{report_type}")
async def get_report(
    case_id: UUID,
    report_type: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get generated report."""
    valid_types = ["summary", "determination"]
    if report_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid report type. Must be one of: {valid_types}",
        )

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        row = await conn.fetchrow(
            """
            SELECT analysis_data, source_documents, generated_at
            FROM er_case_analysis
            WHERE case_id = $1 AND analysis_type = $2
            """,
            case_id,
            report_type,
        )

        if not row:
            raise HTTPException(status_code=404, detail=f"{report_type.title()} report not found.")

        analysis_data = row["analysis_data"]
        if isinstance(analysis_data, str):
            analysis_data = json.loads(analysis_data)

        source_docs = row["source_documents"]
        if isinstance(source_docs, str):
            source_docs = json.loads(source_docs)

        return {
            "report_type": report_type,
            "content": analysis_data.get("content", ""),
            "generated_at": row["generated_at"],
            "source_documents": source_docs,
        }


# ===========================================
# Audit Log
# ===========================================


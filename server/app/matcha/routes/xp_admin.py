"""
Employee Experience (XP) Admin Routes

Routes for managing Vibe Checks, eNPS Surveys, and Performance Reviews.
Requires admin or client role.
"""
import asyncio
import json
import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ...database import get_connection
from ...config import get_settings
from ...core.services.email import get_email_service
from ..dependencies import require_admin_or_client, get_client_company_id
from ..models.xp import (
    # Vibe Checks
    VibeCheckConfigCreate,
    VibeCheckConfigUpdate,
    VibeCheckConfigResponse,
    VibeAnalytics,
    VibeCheckListResponse,
    VibeCheckResponse,
    # eNPS
    ENPSSurveyCreate,
    ENPSSurveyUpdate,
    ENPSSurveyResponse,
    ENPSSurveyListResponse,
    ENPSResults,
    # Reviews
    ReviewTemplateCreate,
    ReviewTemplateUpdate,
    ReviewTemplateResponse,
    ReviewTemplateListResponse,
    ReviewCycleCreate,
    ReviewCycleUpdate,
    ReviewCycleResponse,
    ReviewCycleListResponse,
    PerformanceReviewListResponse,
    PerformanceReviewDetail,
    ReviewProgress,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/xp", tags=["Employee Experience"])


# ================================
# Vibe Checks - Configuration
# ================================


@router.post("/vibe-checks/config", response_model=VibeCheckConfigResponse)
async def create_or_update_vibe_config(
    config: VibeCheckConfigCreate,
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """Create or update vibe check configuration for the organization."""
    if not org_id:
        raise HTTPException(400, "Organization not found")

    async with get_connection() as conn:
        # Upsert configuration
        result = await conn.fetchrow(
            """
            INSERT INTO vibe_check_configs (org_id, frequency, enabled, is_anonymous, questions)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (org_id)
            DO UPDATE SET
                frequency = EXCLUDED.frequency,
                enabled = EXCLUDED.enabled,
                is_anonymous = EXCLUDED.is_anonymous,
                questions = EXCLUDED.questions,
                updated_at = NOW()
            RETURNING *
            """,
            org_id,
            config.frequency,
            config.enabled,
            config.is_anonymous,
            json.dumps(config.questions),
        )

        return VibeCheckConfigResponse(**dict(result))


@router.get("/vibe-checks/config", response_model=VibeCheckConfigResponse)
async def get_vibe_config(
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """Get current vibe check configuration."""
    if not org_id:
        raise HTTPException(400, "Organization not found")

    async with get_connection() as conn:
        result = await conn.fetchrow(
            "SELECT * FROM vibe_check_configs WHERE org_id = $1", org_id
        )

        if not result:
            raise HTTPException(404, "Vibe check configuration not found")

        return VibeCheckConfigResponse(**dict(result))


@router.patch("/vibe-checks/config", response_model=VibeCheckConfigResponse)
async def update_vibe_config(
    config: VibeCheckConfigUpdate,
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """Partially update vibe check configuration."""
    if not org_id:
        raise HTTPException(400, "Organization not found")

    async with get_connection() as conn:
        # Build dynamic update query
        updates = []
        values = []
        param_count = 1

        if config.frequency is not None:
            updates.append(f"frequency = ${param_count}")
            values.append(config.frequency)
            param_count += 1

        if config.enabled is not None:
            updates.append(f"enabled = ${param_count}")
            values.append(config.enabled)
            param_count += 1

        if config.is_anonymous is not None:
            updates.append(f"is_anonymous = ${param_count}")
            values.append(config.is_anonymous)
            param_count += 1

        if config.questions is not None:
            updates.append(f"questions = ${param_count}")
            values.append(json.dumps(config.questions))
            param_count += 1

        if not updates:
            raise HTTPException(400, "No fields to update")

        updates.append("updated_at = NOW()")
        values.append(org_id)

        result = await conn.fetchrow(
            f"""
            UPDATE vibe_check_configs
            SET {', '.join(updates)}
            WHERE org_id = ${param_count}
            RETURNING *
            """,
            *values,
        )

        if not result:
            raise HTTPException(404, "Vibe check configuration not found")

        return VibeCheckConfigResponse(**dict(result))


# ================================
# Vibe Checks - Analytics
# ================================


@router.get("/vibe-checks/analytics", response_model=VibeAnalytics)
async def get_vibe_analytics(
    period: str = Query("week", regex="^(week|month|quarter)$"),
    manager_id: Optional[UUID] = None,
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """
    Get aggregated vibe check analytics.

    Args:
        period: Time period (week, month, quarter)
        manager_id: Optional filter for specific manager's team
    """
    if not org_id:
        raise HTTPException(400, "Organization not found")

    async with get_connection() as conn:
        # Calculate date range
        if period == "week":
            since_clause = "NOW() - INTERVAL '7 days'"
        elif period == "month":
            since_clause = "NOW() - INTERVAL '30 days'"
        else:  # quarter
            since_clause = "NOW() - INTERVAL '90 days'"

        # Build manager filter
        params = [org_id]
        manager_subquery = ""
        employee_manager_filter = ""
        if manager_id:
            manager_subquery = "AND v.employee_id IN (SELECT id FROM employees WHERE org_id = $1 AND manager_id = $2)"
            employee_manager_filter = "AND manager_id = $2"
            params.append(manager_id)

        # Aggregate stats
        stats = await conn.fetchrow(
            f"""
            SELECT
                COUNT(*) as total_responses,
                AVG(v.mood_rating)::DECIMAL(3,2) as avg_mood,
                AVG((v.sentiment_analysis->>'sentiment_score')::DECIMAL)::DECIMAL(3,2) as avg_sentiment,
                COUNT(DISTINCT v.employee_id) as unique_respondents
            FROM vibe_check_responses v
            WHERE v.org_id = $1
            AND v.created_at >= {since_clause}
            {manager_subquery}
            """,
            *params,
        )

        # Get total employee count from employees table
        total_employees = await conn.fetchval(
            f"""
            SELECT COUNT(*) FROM employees
            WHERE org_id = $1
            {employee_manager_filter}
            """,
            *params,
        )

        # Top themes (from AI analysis)
        themes = await conn.fetch(
            f"""
            SELECT
                theme,
                COUNT(*) as frequency,
                AVG((v.sentiment_analysis->>'sentiment_score')::DECIMAL) as avg_sentiment
            FROM vibe_check_responses v
            CROSS JOIN LATERAL jsonb_array_elements_text(v.sentiment_analysis->'themes') as theme
            WHERE v.org_id = $1
            AND v.created_at >= {since_clause}
            AND v.sentiment_analysis IS NOT NULL
            {manager_subquery}
            GROUP BY theme
            ORDER BY frequency DESC
            LIMIT 10
            """,
            *params,
        )

        response_rate = (
            Decimal(stats["unique_respondents"])
            / Decimal(total_employees)
            * 100
            if total_employees and total_employees > 0
            else Decimal(0)
        )

        return VibeAnalytics(
            period=period,
            total_responses=stats["total_responses"],
            avg_mood_rating=stats["avg_mood"],
            avg_sentiment_score=stats["avg_sentiment"],
            response_rate=response_rate,
            top_themes=[dict(t) for t in themes],
        )


@router.get("/vibe-checks/responses", response_model=VibeCheckListResponse)
async def get_vibe_responses(
    limit: int = Query(50, le=500),
    offset: int = 0,
    employee_id: Optional[UUID] = None,
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """Get individual vibe check responses (for admins/clients)."""
    if not org_id:
        raise HTTPException(400, "Organization not found")

    async with get_connection() as conn:
        # Build employee filter
        employee_filter = ""
        params = [org_id, limit, offset]
        if employee_id:
            employee_filter = "AND v.employee_id = $4"
            params.append(employee_id)

        # Get responses with employee names
        rows = await conn.fetch(
            f"""
            SELECT v.*,
                   CASE
                       WHEN e.id IS NOT NULL THEN e.first_name || ' ' || e.last_name
                       ELSE NULL
                   END as employee_name
            FROM vibe_check_responses v
            LEFT JOIN employees e ON v.employee_id = e.id
            WHERE v.org_id = $1
            {employee_filter}
            ORDER BY v.created_at DESC
            LIMIT $2 OFFSET $3
            """,
            *params,
        )

        # Get total count with correct parameters
        count_params = [org_id]
        count_employee_filter = ""
        if employee_id:
            count_employee_filter = "AND employee_id = $2"
            count_params.append(employee_id)

        total = await conn.fetchval(
            f"""
            SELECT COUNT(*) FROM vibe_check_responses
            WHERE org_id = $1
            {count_employee_filter}
            """,
            *count_params,
        )

        responses = [VibeCheckResponse(**dict(r)) for r in rows]

        return VibeCheckListResponse(responses=responses, total=total)


# ================================
# eNPS Surveys
# ================================


@router.post("/enps/surveys", response_model=ENPSSurveyResponse)
async def create_enps_survey(
    survey: ENPSSurveyCreate,
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """Create new eNPS survey campaign."""
    if not org_id:
        raise HTTPException(400, "Organization not found")

    async with get_connection() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO enps_surveys
            (org_id, title, description, start_date, end_date, is_anonymous, custom_question, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            org_id,
            survey.title,
            survey.description,
            survey.start_date,
            survey.end_date,
            survey.is_anonymous,
            survey.custom_question,
            current_user.id,
        )

        return ENPSSurveyResponse(**dict(result))


@router.get("/enps/surveys", response_model=ENPSSurveyListResponse)
async def list_enps_surveys(
    limit: int = Query(50, le=100),
    offset: int = 0,
    status: Optional[str] = None,
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """List eNPS surveys for organization."""
    if not org_id:
        raise HTTPException(400, "Organization not found")

    async with get_connection() as conn:
        status_filter = ""
        params = [org_id, limit, offset]
        if status:
            status_filter = "AND status = $4"
            params.append(status)

        rows = await conn.fetch(
            f"""
            SELECT * FROM enps_surveys
            WHERE org_id = $1
            {status_filter}
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            *params,
        )

        # Use separate filter for count query (only has 1-2 params)
        count_params = [org_id]
        count_status_filter = ""
        if status:
            count_status_filter = "AND status = $2"
            count_params.append(status)

        total = await conn.fetchval(
            f"""
            SELECT COUNT(*) FROM enps_surveys
            WHERE org_id = $1
            {count_status_filter}
            """,
            *count_params,
        )

        return ENPSSurveyListResponse(
            surveys=[ENPSSurveyResponse(**dict(r)) for r in rows], total=total
        )


@router.get("/enps/surveys/{survey_id}", response_model=ENPSSurveyResponse)
async def get_enps_survey(
    survey_id: UUID,
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """Get specific eNPS survey."""
    if not org_id:
        raise HTTPException(400, "Organization not found")

    async with get_connection() as conn:
        result = await conn.fetchrow(
            "SELECT * FROM enps_surveys WHERE id = $1 AND org_id = $2",
            survey_id, org_id
        )

        if not result:
            raise HTTPException(404, "Survey not found")

        return ENPSSurveyResponse(**dict(result))


@router.patch("/enps/surveys/{survey_id}", response_model=ENPSSurveyResponse)
async def update_enps_survey(
    survey_id: UUID,
    survey: ENPSSurveyUpdate,
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """Update eNPS survey."""
    if not org_id:
        raise HTTPException(400, "Organization not found")

    # Data to collect for email notifications (if activating)
    activation_data = None

    async with get_connection() as conn:
        # Get current survey state to check if we're activating it (scoped by org)
        current_survey = await conn.fetchrow(
            "SELECT status, org_id, title, description FROM enps_surveys WHERE id = $1 AND org_id = $2",
            survey_id, org_id,
        )
        if not current_survey:
            raise HTTPException(404, "Survey not found")

        is_activating = (
            survey.status == "active"
            and current_survey["status"] != "active"
        )

        # Build dynamic update
        updates = []
        values = []
        param_count = 1

        for field in [
            "title",
            "description",
            "start_date",
            "end_date",
            "status",
            "is_anonymous",
            "custom_question",
        ]:
            value = getattr(survey, field)
            if value is not None:
                updates.append(f"{field} = ${param_count}")
                values.append(value)
                param_count += 1

        if not updates:
            raise HTTPException(400, "No fields to update")

        values.append(survey_id)

        result = await conn.fetchrow(
            f"""
            UPDATE enps_surveys
            SET {', '.join(updates)}
            WHERE id = ${param_count}
            RETURNING *
            """,
            *values,
        )

        if not result:
            raise HTTPException(404, "Survey not found")

        # Collect data for email notifications while we have the connection
        if is_activating:
            org_id = current_survey["org_id"]

            # Get company name
            org = await conn.fetchrow(
                "SELECT name FROM companies WHERE id = $1", org_id
            )
            company_name = org["name"] if org else "Your Company"

            # Get all active employees with email
            employees = await conn.fetch(
                """
                SELECT e.id, e.first_name, e.last_name, e.email
                FROM employees e
                WHERE e.org_id = $1
                AND e.status = 'active'
                AND e.email IS NOT NULL
                """,
                org_id,
            )

            # Store data for sending after connection is released
            activation_data = {
                "company_name": company_name,
                "employees": [dict(e) for e in employees],
                "survey_title": result["title"],
                "survey_description": result["description"],
            }

        response = ENPSSurveyResponse(**dict(result))

    # Send email notifications AFTER releasing the DB connection
    if activation_data:
        logger.info(f"[eNPS] Survey {survey_id} activated - preparing to send emails to {len(activation_data['employees'])} employees")
        email_service = get_email_service()
        settings = get_settings()
        portal_url = f"{settings.app_base_url}/app/portal/enps"

        if not email_service.is_configured():
            logger.warning(f"[eNPS] Email service not configured - skipping email notifications")
        else:
            try:
                sem = asyncio.Semaphore(5)

                async def _send_email(emp):
                    employee_name = f"{emp['first_name']} {emp['last_name']}".strip() or "Team Member"
                    try:
                        async with sem:
                            success = await email_service.send_enps_survey_email(
                                to_email=emp["email"],
                                to_name=employee_name,
                                company_name=activation_data["company_name"],
                                survey_title=activation_data["survey_title"],
                                survey_description=activation_data["survey_description"],
                                portal_url=portal_url,
                            )
                        if not success:
                            logger.warning(f"[eNPS] Email to {emp['email']} returned false")
                        return success
                    except Exception:
                        logger.exception(f"[eNPS] Failed to send email to {emp['email']}")
                        return False

                results = await asyncio.gather(*[_send_email(emp) for emp in activation_data["employees"]])
                sent_count = sum(1 for r in results if r)
                logger.info(f"[eNPS] Survey {survey_id} - sent {sent_count}/{len(activation_data['employees'])} notification emails")
            except Exception:
                logger.exception(f"[eNPS] Unexpected error sending emails for survey {survey_id}")

    return response


@router.get("/enps/surveys/{survey_id}/results", response_model=ENPSResults)
async def get_enps_results(
    survey_id: UUID,
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """Calculate eNPS score and theme analysis for a survey."""
    if not org_id:
        raise HTTPException(400, "Organization not found")

    async with get_connection() as conn:
        # Verify survey belongs to org
        survey_check = await conn.fetchval(
            "SELECT id FROM enps_surveys WHERE id = $1 AND org_id = $2",
            survey_id, org_id
        )
        if not survey_check:
            raise HTTPException(404, "Survey not found")

        # Get all responses
        responses = await conn.fetch(
            "SELECT * FROM enps_responses WHERE survey_id = $1", survey_id
        )

        if not responses:
            return ENPSResults(
                enps_score=Decimal(0),
                promoters=0,
                detractors=0,
                passives=0,
                total_responses=0,
                response_rate=Decimal(0),
                promoter_themes=[],
                detractor_themes=[],
                passive_themes=[],
            )

        # Calculate eNPS
        total = len(responses)
        promoters = sum(1 for r in responses if r["score"] >= 9)
        detractors = sum(1 for r in responses if r["score"] <= 6)
        passives = total - promoters - detractors
        enps = Decimal((promoters - detractors) / total * 100) if total > 0 else Decimal(0)

        # Aggregate themes by category
        promoter_themes = await conn.fetch(
            """
            SELECT
                theme,
                COUNT(*) as frequency,
                AVG((sentiment_analysis->>'sentiment_score')::DECIMAL) as avg_sentiment
            FROM enps_responses
            CROSS JOIN LATERAL jsonb_array_elements_text(sentiment_analysis->'themes') as theme
            WHERE survey_id = $1 AND category = 'promoter' AND sentiment_analysis IS NOT NULL
            GROUP BY theme
            ORDER BY frequency DESC
            LIMIT 10
            """,
            survey_id,
        )

        detractor_themes = await conn.fetch(
            """
            SELECT
                theme,
                COUNT(*) as frequency,
                AVG((sentiment_analysis->>'sentiment_score')::DECIMAL) as avg_sentiment
            FROM enps_responses
            CROSS JOIN LATERAL jsonb_array_elements_text(sentiment_analysis->'themes') as theme
            WHERE survey_id = $1 AND category = 'detractor' AND sentiment_analysis IS NOT NULL
            GROUP BY theme
            ORDER BY frequency DESC
            LIMIT 10
            """,
            survey_id,
        )

        passive_themes = await conn.fetch(
            """
            SELECT
                theme,
                COUNT(*) as frequency,
                AVG((sentiment_analysis->>'sentiment_score')::DECIMAL) as avg_sentiment
            FROM enps_responses
            CROSS JOIN LATERAL jsonb_array_elements_text(sentiment_analysis->'themes') as theme
            WHERE survey_id = $1 AND category = 'passive' AND sentiment_analysis IS NOT NULL
            GROUP BY theme
            ORDER BY frequency DESC
            LIMIT 10
            """,
            survey_id,
        )

        # Get total employees for response rate
        survey = await conn.fetchrow("SELECT org_id FROM enps_surveys WHERE id = $1", survey_id)
        total_employees = await conn.fetchval(
            "SELECT COUNT(*) FROM employees WHERE org_id = $1", survey["org_id"]
        )

        response_rate = (
            Decimal(total) / Decimal(total_employees) * 100
            if total_employees and total_employees > 0
            else Decimal(0)
        )

        return ENPSResults(
            enps_score=enps,
            promoters=promoters,
            detractors=detractors,
            passives=passives,
            total_responses=total,
            response_rate=response_rate,
            promoter_themes=[dict(t) for t in promoter_themes],
            detractor_themes=[dict(t) for t in detractor_themes],
            passive_themes=[dict(t) for t in passive_themes],
        )


# ================================
# Performance Reviews - Templates
# ================================


@router.post("/reviews/templates", response_model=ReviewTemplateResponse)
async def create_review_template(
    template: ReviewTemplateCreate,
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """Create a new review template."""
    if not org_id:
        raise HTTPException(400, "Organization not found")

    async with get_connection() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO review_templates (org_id, name, description, categories)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            org_id,
            template.name,
            template.description,
            json.dumps(template.categories),
        )

        return ReviewTemplateResponse(**dict(result))


@router.get("/reviews/templates", response_model=ReviewTemplateListResponse)
async def list_review_templates(
    limit: int = Query(50, le=100),
    offset: int = 0,
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """List review templates for organization."""
    if not org_id:
        raise HTTPException(400, "Organization not found")

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM review_templates
            WHERE org_id = $1 AND is_active = true
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            org_id,
            limit,
            offset,
        )

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM review_templates WHERE org_id = $1 AND is_active = true",
            org_id,
        )

        return ReviewTemplateListResponse(
            templates=[ReviewTemplateResponse(**dict(r)) for r in rows], total=total
        )


@router.get("/reviews/templates/{template_id}", response_model=ReviewTemplateResponse)
async def get_review_template(
    template_id: UUID,
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """Get a specific review template."""
    if not org_id:
        raise HTTPException(400, "Organization not found")

    async with get_connection() as conn:
        result = await conn.fetchrow(
            "SELECT * FROM review_templates WHERE id = $1 AND org_id = $2 AND is_active = true",
            template_id, org_id
        )

        if not result:
            raise HTTPException(404, "Template not found")

        return ReviewTemplateResponse(**dict(result))


@router.patch("/reviews/templates/{template_id}", response_model=ReviewTemplateResponse)
async def update_review_template(
    template_id: UUID,
    template: ReviewTemplateUpdate,
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """Update a review template."""
    if not org_id:
        raise HTTPException(400, "Organization not found")

    async with get_connection() as conn:
        # Verify template belongs to org
        existing = await conn.fetchrow(
            "SELECT * FROM review_templates WHERE id = $1 AND org_id = $2 AND is_active = true",
            template_id, org_id
        )
        if not existing:
            raise HTTPException(404, "Template not found")

        # Build dynamic update
        updates = []
        values = []
        param_count = 1

        if template.name is not None:
            updates.append(f"name = ${param_count}")
            values.append(template.name)
            param_count += 1

        if template.description is not None:
            updates.append(f"description = ${param_count}")
            values.append(template.description)
            param_count += 1

        if template.categories is not None:
            updates.append(f"categories = ${param_count}")
            values.append(json.dumps(template.categories))
            param_count += 1

        if template.is_active is not None:
            updates.append(f"is_active = ${param_count}")
            values.append(template.is_active)
            param_count += 1

        if not updates:
            raise HTTPException(400, "No fields to update")

        values.append(template_id)
        values.append(org_id)

        result = await conn.fetchrow(
            f"""
            UPDATE review_templates
            SET {', '.join(updates)}, updated_at = NOW()
            WHERE id = ${param_count} AND org_id = ${param_count + 1}
            RETURNING *
            """,
            *values,
        )

        if not result:
            raise HTTPException(404, "Template not found")

        return ReviewTemplateResponse(**dict(result))


# ================================
# Performance Reviews - Cycles
# ================================


@router.post("/reviews/cycles", response_model=ReviewCycleResponse)
async def create_review_cycle(
    cycle: ReviewCycleCreate,
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """Create a new review cycle."""
    if not org_id:
        raise HTTPException(400, "Organization not found")

    async with get_connection() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO review_cycles (org_id, title, description, start_date, end_date, template_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            org_id,
            cycle.title,
            cycle.description,
            cycle.start_date,
            cycle.end_date,
            cycle.template_id,
        )

        return ReviewCycleResponse(**dict(result))


@router.get("/reviews/cycles", response_model=ReviewCycleListResponse)
async def list_review_cycles(
    limit: int = Query(50, le=100),
    offset: int = 0,
    status: Optional[str] = None,
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """List review cycles for organization."""
    if not org_id:
        raise HTTPException(400, "Organization not found")

    async with get_connection() as conn:
        status_filter = ""
        params = [org_id, limit, offset]
        if status:
            status_filter = "AND status = $4"
            params.append(status)

        rows = await conn.fetch(
            f"""
            SELECT * FROM review_cycles
            WHERE org_id = $1
            {status_filter}
            ORDER BY start_date DESC
            LIMIT $2 OFFSET $3
            """,
            *params,
        )

        # Use separate filter for count query (only has 1-2 params)
        count_params = [org_id]
        count_status_filter = ""
        if status:
            count_status_filter = "AND status = $2"
            count_params.append(status)

        total = await conn.fetchval(
            f"""
            SELECT COUNT(*) FROM review_cycles
            WHERE org_id = $1
            {count_status_filter}
            """,
            *count_params,
        )

        return ReviewCycleListResponse(
            cycles=[ReviewCycleResponse(**dict(r)) for r in rows], total=total
        )


@router.get("/reviews/cycles/{cycle_id}", response_model=ReviewCycleResponse)
async def get_review_cycle(
    cycle_id: UUID,
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """Get a specific review cycle."""
    if not org_id:
        raise HTTPException(400, "Organization not found")

    async with get_connection() as conn:
        result = await conn.fetchrow(
            "SELECT * FROM review_cycles WHERE id = $1 AND org_id = $2",
            cycle_id, org_id
        )

        if not result:
            raise HTTPException(404, "Review cycle not found")

        return ReviewCycleResponse(**dict(result))


@router.patch("/reviews/cycles/{cycle_id}", response_model=ReviewCycleResponse)
async def update_review_cycle(
    cycle_id: UUID,
    cycle: ReviewCycleUpdate,
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """Update a review cycle."""
    if not org_id:
        raise HTTPException(400, "Organization not found")

    async with get_connection() as conn:
        # Verify cycle belongs to this org
        existing = await conn.fetchrow(
            "SELECT * FROM review_cycles WHERE id = $1 AND org_id = $2",
            cycle_id, org_id
        )
        if not existing:
            raise HTTPException(404, "Review cycle not found")

        # Build dynamic update
        updates = []
        values = []
        param_count = 1

        for field in ["title", "description", "start_date", "end_date", "status", "template_id"]:
            value = getattr(cycle, field, None)
            if value is not None:
                updates.append(f"{field} = ${param_count}")
                values.append(value)
                param_count += 1

        if not updates:
            raise HTTPException(400, "No fields to update")

        values.append(cycle_id)
        values.append(org_id)

        result = await conn.fetchrow(
            f"""
            UPDATE review_cycles
            SET {', '.join(updates)}, updated_at = NOW()
            WHERE id = ${param_count} AND org_id = ${param_count + 1}
            RETURNING *
            """,
            *values,
        )

        if not result:
            raise HTTPException(404, "Review cycle not found")

        return ReviewCycleResponse(**dict(result))


@router.get("/reviews/cycles/{cycle_id}/progress", response_model=ReviewProgress)
async def get_cycle_progress(
    cycle_id: UUID,
    current_user=Depends(require_admin_or_client),
    org_id: UUID = Depends(get_client_company_id),
):
    """Get progress summary for a review cycle."""
    if not org_id:
        raise HTTPException(400, "Organization not found")

    async with get_connection() as conn:
        # Verify cycle exists and belongs to org
        cycle = await conn.fetchrow(
            "SELECT * FROM review_cycles WHERE id = $1 AND org_id = $2",
            cycle_id, org_id
        )
        if not cycle:
            raise HTTPException(404, "Review cycle not found")

        # Get stats
        stats = await conn.fetchrow(
            """
            SELECT
                COUNT(*) as total_reviews,
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'self_submitted') as self_submitted,
                COUNT(*) FILTER (WHERE status = 'manager_submitted') as manager_submitted,
                COUNT(*) FILTER (WHERE status = 'completed') as completed
            FROM performance_reviews
            WHERE cycle_id = $1
            """,
            cycle_id,
        )

        completion_rate = (
            Decimal(stats["completed"]) / Decimal(stats["total_reviews"]) * 100
            if stats["total_reviews"] and stats["total_reviews"] > 0
            else Decimal(0)
        )

        return ReviewProgress(
            cycle_id=cycle_id,
            total_reviews=stats["total_reviews"],
            pending=stats["pending"],
            self_submitted=stats["self_submitted"],
            manager_submitted=stats["manager_submitted"],
            completed=stats["completed"],
            completion_rate=completion_rate,
        )

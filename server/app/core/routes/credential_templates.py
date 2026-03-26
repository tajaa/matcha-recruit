"""Credential requirement template management routes."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...database import get_connection
from ...matcha.dependencies import require_admin_or_client, get_client_company_id
from ..models.auth import CurrentUser
from ..services.credential_template_service import (
    get_templates_for_scope,
    get_employee_credential_requirements,
    research_credential_requirements,
    resolve_credential_requirements,
    match_job_title_to_role_category,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Models ────────────────────────────────────────────────────────────


class TemplateCreate(BaseModel):
    state: str
    city: Optional[str] = None
    role_category_id: UUID
    credential_type_id: UUID
    is_required: bool = True
    due_days: int = 7
    priority: str = "standard"
    notes: Optional[str] = None


class TemplateUpdate(BaseModel):
    is_required: Optional[bool] = None
    due_days: Optional[int] = None
    priority: Optional[str] = None
    notes: Optional[str] = None


class ResearchRequest(BaseModel):
    state: str
    city: Optional[str] = None
    role_category_id: UUID


class PreviewRequest(BaseModel):
    state: str
    city: Optional[str] = None
    job_title: str


class WaiveRequest(BaseModel):
    reason: str


# ── Credential types ──────────────────────────────────────────────────


@router.get("/types")
async def list_credential_types(
    user: CurrentUser = Depends(require_admin_or_client),
):
    """List all credential types."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM credential_types ORDER BY category, label"
        )
        return [dict(r) for r in rows]


# ── Role categories ───────────────────────────────────────────────────


@router.get("/role-categories")
async def list_role_categories(
    user: CurrentUser = Depends(require_admin_or_client),
):
    """List all role categories."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT id, key, label, is_clinical, sort_order "
            "FROM role_categories ORDER BY sort_order"
        )
        return [dict(r) for r in rows]


# ── Templates CRUD ────────────────────────────────────────────────────


@router.get("/templates")
async def list_templates(
    state: Optional[str] = Query(None),
    role_category_id: Optional[UUID] = Query(None),
    include_pending: bool = Query(True),
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """List credential requirement templates for the company's scope."""
    async with get_connection() as conn:
        if not state:
            # Return all templates for company's states
            conditions = [
                "(crt.company_id = $1 OR crt.company_id IS NULL)",
                "crt.is_active = true",
            ]
            params = [company_id]
            if not include_pending:
                conditions.append("crt.review_status IN ('approved', 'auto_approved')")
            if role_category_id:
                conditions.append(f"crt.role_category_id = ${len(params) + 1}")
                params.append(role_category_id)

            where = " AND ".join(conditions)
            rows = await conn.fetch(
                f"""
                SELECT crt.*, ct.key AS ct_key, ct.label AS ct_label, ct.category AS ct_category,
                       rc.key AS role_key, rc.label AS role_label
                FROM credential_requirement_templates crt
                JOIN credential_types ct ON ct.id = crt.credential_type_id
                JOIN role_categories rc ON rc.id = crt.role_category_id
                WHERE {where}
                ORDER BY crt.state, rc.sort_order, ct.category, ct.label
                """,
                *params,
            )
            return [dict(r) for r in rows]

        return await get_templates_for_scope(
            conn, state, role_category_id, company_id, include_pending
        )


@router.post("/templates")
async def create_template(
    body: TemplateCreate,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Manually create a credential requirement template."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO credential_requirement_templates
                (company_id, state, city, role_category_id, credential_type_id,
                 is_required, due_days, priority, notes, source, review_status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'admin_manual', 'approved')
            RETURNING *
            """,
            company_id, body.state, body.city, body.role_category_id,
            body.credential_type_id, body.is_required, body.due_days,
            body.priority, body.notes,
        )
        return dict(row)


@router.put("/templates/{template_id}")
async def update_template(
    template_id: UUID,
    body: TemplateUpdate,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Edit a credential requirement template."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM credential_requirement_templates WHERE id = $1",
            template_id,
        )
        if not row:
            raise HTTPException(404, "Template not found")
        if row["company_id"] and row["company_id"] != company_id:
            raise HTTPException(403, "Not authorized")

        updates = []
        params = []
        idx = 1
        for field in ["is_required", "due_days", "priority", "notes"]:
            val = getattr(body, field, None)
            if val is not None:
                updates.append(f"{field} = ${idx}")
                params.append(val)
                idx += 1

        if not updates:
            return dict(row)

        updates.append(f"updated_at = NOW()")
        params.append(template_id)

        updated = await conn.fetchrow(
            f"UPDATE credential_requirement_templates SET {', '.join(updates)} "
            f"WHERE id = ${idx} RETURNING *",
            *params,
        )
        return dict(updated)


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: UUID,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Soft-delete a template (set is_active = false)."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT company_id FROM credential_requirement_templates WHERE id = $1",
            template_id,
        )
        if not row:
            raise HTTPException(404, "Template not found")
        if row["company_id"] and row["company_id"] != company_id:
            raise HTTPException(403, "Not authorized")

        await conn.execute(
            "UPDATE credential_requirement_templates SET is_active = false, updated_at = NOW() WHERE id = $1",
            template_id,
        )
        return {"ok": True}


# ── Approve / Reject ──────────────────────────────────────────────────


@router.post("/templates/{template_id}/approve")
async def approve_template(
    template_id: UUID,
    user: CurrentUser = Depends(require_admin_or_client),
):
    """Approve an AI-generated template."""
    async with get_connection() as conn:
        await conn.execute(
            """
            UPDATE credential_requirement_templates
            SET review_status = 'approved', reviewed_by = $1, reviewed_at = NOW(), updated_at = NOW()
            WHERE id = $2
            """,
            user.id, template_id,
        )
        return {"ok": True}


@router.post("/templates/{template_id}/reject")
async def reject_template(
    template_id: UUID,
    user: CurrentUser = Depends(require_admin_or_client),
):
    """Reject an AI-generated template."""
    async with get_connection() as conn:
        await conn.execute(
            """
            UPDATE credential_requirement_templates
            SET review_status = 'rejected', reviewed_by = $1, reviewed_at = NOW(), updated_at = NOW()
            WHERE id = $2
            """,
            user.id, template_id,
        )
        return {"ok": True}


@router.post("/bulk-approve")
async def bulk_approve(
    research_id: UUID = Query(...),
    user: CurrentUser = Depends(require_admin_or_client),
):
    """Approve all pending templates from a research run."""
    async with get_connection() as conn:
        result = await conn.execute(
            """
            UPDATE credential_requirement_templates
            SET review_status = 'approved', reviewed_by = $1, reviewed_at = NOW(), updated_at = NOW()
            WHERE ai_research_id = $2 AND review_status = 'pending'
            """,
            user.id, research_id,
        )
        count = int(result.split()[-1]) if result else 0
        return {"approved": count}


# ── Research ──────────────────────────────────────────────────────────


@router.post("/research")
async def trigger_research(
    body: ResearchRequest,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Trigger Gemini AI research for credential requirements."""
    async with get_connection() as conn:
        results = await research_credential_requirements(
            conn,
            state=body.state,
            city=body.city,
            role_category_id=body.role_category_id,
            company_id=None,  # System-wide templates
            triggered_by=user.id,
        )
        return {"template_count": len(results), "requirements": results}


@router.get("/research/{research_id}")
async def get_research_log(
    research_id: UUID,
    user: CurrentUser = Depends(require_admin_or_client),
):
    """Get research log details."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM credential_research_logs WHERE id = $1",
            research_id,
        )
        if not row:
            raise HTTPException(404, "Research log not found")
        return dict(row)


@router.get("/research")
async def list_research_logs(
    state: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_admin_or_client),
):
    """List research logs."""
    async with get_connection() as conn:
        if state:
            rows = await conn.fetch(
                """
                SELECT crl.*, rc.label AS role_label
                FROM credential_research_logs crl
                LEFT JOIN role_categories rc ON rc.id = crl.role_category_id
                WHERE crl.state = $1
                ORDER BY crl.started_at DESC
                LIMIT 50
                """,
                state,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT crl.*, rc.label AS role_label
                FROM credential_research_logs crl
                LEFT JOIN role_categories rc ON rc.id = crl.role_category_id
                ORDER BY crl.started_at DESC
                LIMIT 50
                """
            )
        return [dict(r) for r in rows]


# ── Preview ───────────────────────────────────────────────────────────


@router.get("/preview")
async def preview_requirements(
    state: str = Query(...),
    job_title: str = Query(...),
    city: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Preview what credential requirements would apply for a state + job title (dry-run)."""
    async with get_connection() as conn:
        requirements = await resolve_credential_requirements(
            conn, company_id, state, city, job_title
        )
        role_cat = await match_job_title_to_role_category(conn, job_title)
        return {
            "role_category": dict(role_cat) if role_cat else None,
            "state": state,
            "city": city,
            "job_title": job_title,
            "requirements": [
                {
                    "credential_type_key": r.credential_type_key,
                    "credential_type_label": r.credential_type_label,
                    "is_required": r.is_required,
                    "due_days": r.due_days,
                    "priority": r.priority,
                    "notes": r.notes,
                    "source": r.source,
                }
                for r in requirements
            ],
        }


# ── Employee credential requirements ─────────────────────────────────


@router.get("/employees/{employee_id}/requirements")
async def get_employee_requirements(
    employee_id: UUID,
    user: CurrentUser = Depends(require_admin_or_client),
):
    """Get all credential requirements for an employee."""
    async with get_connection() as conn:
        return await get_employee_credential_requirements(conn, employee_id)


@router.post("/employees/{employee_id}/requirements/{requirement_id}/waive")
async def waive_requirement(
    employee_id: UUID,
    requirement_id: UUID,
    body: WaiveRequest,
    user: CurrentUser = Depends(require_admin_or_client),
):
    """Waive a credential requirement for an employee."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM employee_credential_requirements WHERE id = $1 AND employee_id = $2",
            requirement_id, employee_id,
        )
        if not row:
            raise HTTPException(404, "Requirement not found")

        await conn.execute(
            """
            UPDATE employee_credential_requirements
            SET status = 'waived', waived_by = $1, waived_at = NOW(),
                waiver_reason = $2, updated_at = NOW()
            WHERE id = $3
            """,
            user.id, body.reason, requirement_id,
        )

        # Also complete the linked onboarding task
        await conn.execute(
            """
            UPDATE employee_onboarding_tasks
            SET status = 'completed'
            WHERE credential_requirement_id = $1 AND status = 'pending'
            """,
            requirement_id,
        )

        return {"ok": True}

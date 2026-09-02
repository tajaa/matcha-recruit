"""Credential requirement template management routes."""

import json
import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.database import get_connection
from app.matcha.dependencies import (
    require_admin_or_client,
    get_client_company_id,
    resolve_accessible_company_scope,
)
from app.core.models.auth import CurrentUser
from app.core.models.credential_templates import CredentialTypeVisibilityUpdate
from app.core.services.credential_template_service import (
    find_hidden_credential_types,
    get_templates_for_scope,
    get_employee_credential_requirements,
    research_credential_requirements,
    resolve_credential_requirements,
    match_job_title_to_role_category,
    materialize_schedule_blocking_template,
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
    schedule_blocking: bool = False
    warning_days: int = 14
    legal_basis: dict[str, Any] | None = None


class TemplateUpdate(BaseModel):
    is_required: Optional[bool] = None
    due_days: Optional[int] = None
    priority: Optional[str] = None
    notes: Optional[str] = None
    schedule_blocking: Optional[bool] = None
    warning_days: Optional[int] = None
    legal_basis: dict[str, Any] | None = None


def _validate_schedule_blocking(*, enabled: bool, legal_basis: dict[str, Any] | None) -> None:
    if enabled and not (legal_basis or {}).get("citation"):
        raise HTTPException(
            status_code=422,
            detail="A legal-basis citation is required before a credential can block scheduling",
        )


def _legal_basis(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


async def _tenant_override_for_global_template(conn, template, company_id: UUID):
    """Return a company-owned copy of a system template.

    System templates are shared reference data. Tenant edits, especially a
    schedule block, must never alter another company's eligibility rules.
    """
    override = await conn.fetchrow(
        """
        INSERT INTO credential_requirement_templates
            (company_id, state, city, role_category_id, credential_type_id,
             is_required, due_days, priority, notes, source, ai_research_id,
             ai_confidence, review_status, reviewed_by, reviewed_at, is_active,
             schedule_blocking, warning_days, legal_basis)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'tenant_override', $10,
                $11, $12, $13, $14, $15, $16, $17, $18::jsonb)
        ON CONFLICT (company_id, state, city, role_category_id, credential_type_id)
        DO NOTHING
        RETURNING *
        """,
        company_id,
        template["state"],
        template["city"],
        template["role_category_id"],
        template["credential_type_id"],
        template["is_required"],
        template["due_days"],
        template["priority"],
        template["notes"],
        template["ai_research_id"],
        template["ai_confidence"],
        template["review_status"],
        template["reviewed_by"],
        template["reviewed_at"],
        template["is_active"],
        template["schedule_blocking"],
        template["warning_days"],
        json.dumps(_legal_basis(template["legal_basis"])),
    )
    if override:
        return override

    return await conn.fetchrow(
        """
        SELECT * FROM credential_requirement_templates
        WHERE company_id = $1 AND state = $2 AND city IS NOT DISTINCT FROM $3
          AND role_category_id = $4 AND credential_type_id = $5
        """,
        company_id,
        template["state"],
        template["city"],
        template["role_category_id"],
        template["credential_type_id"],
    )


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


async def credential_settings_scope(
    company_id: UUID | None = Query(
        None, description="Platform admins must name the company they are acting on"
    ),
    user: CurrentUser = Depends(require_admin_or_client),
) -> UUID | None:
    """Resolve which tenant's credential dropdown config the caller is acting on.

    ``get_client_company_id`` falls back to the oldest company in the database
    for platform admins, so it must not be used here -- a blind admin call would
    read and write an unrelated tenant's allowlist.  Admins name the company
    explicitly; everyone else is pinned to their own.  ``None`` means "no tenant
    scope", which reads as the unfiltered catalog and is rejected for writes.
    """
    if user.role == "admin" and company_id is None:
        return None
    scope = await resolve_accessible_company_scope(user, company_id)
    return scope.get("company_id")


async def credential_settings_company_id(
    company_id: UUID | None = Depends(credential_settings_scope),
) -> UUID:
    """Write-side scope: a definite company, never the oldest-tenant fallback."""
    if company_id is None:
        raise HTTPException(
            status_code=403,
            detail="A company account is required. Platform admins must pass company_id.",
        )
    return company_id


@router.get("/types")
async def list_credential_types(
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID | None = Depends(credential_settings_scope),
):
    """List credential types available for this company's dropdowns.

    A NULL ``company_id`` matches no filter row, so an unscoped caller keeps the
    legacy behavior of seeing the whole catalog.
    """
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT ct.*
            FROM credential_types ct
            WHERE NOT EXISTS (
                SELECT 1 FROM company_credential_type_filters f
                WHERE f.company_id = $1
            ) OR EXISTS (
                SELECT 1 FROM company_credential_type_filter_items item
                WHERE item.company_id = $1 AND item.credential_type_id = ct.id
            )
            ORDER BY ct.category, ct.label
            """,
            company_id,
        )
        return [dict(r) for r in rows]


@router.get("/type-settings")
async def get_credential_type_settings(
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID | None = Depends(credential_settings_scope),
):
    """Return the full catalog and this company's current dropdown filter.

    An unscoped caller (a platform admin who named no company) still gets the
    catalog, flagged ``manageable=False`` so the UI hides the save controls
    instead of writing to whichever tenant happens to be oldest.
    """
    configured = False
    selected_rows: list = []
    async with get_connection() as conn:
        if company_id is not None:
            configured = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM company_credential_type_filters WHERE company_id = $1)",
                company_id,
            )
            selected_rows = await conn.fetch(
                """
                SELECT credential_type_id
                FROM company_credential_type_filter_items
                WHERE company_id = $1
                ORDER BY credential_type_id
                """,
                company_id,
            )
        type_rows = await conn.fetch(
            "SELECT * FROM credential_types ORDER BY category, label"
        )
    return {
        "is_configured": bool(configured),
        "manageable": company_id is not None,
        "selected_type_ids": [row["credential_type_id"] for row in selected_rows],
        "credential_types": [dict(row) for row in type_rows],
    }


@router.put("/type-settings")
async def update_credential_type_settings(
    body: CredentialTypeVisibilityUpdate,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(credential_settings_company_id),
):
    """Replace the company-specific credential dropdown allowlist."""
    selected_ids = list(dict.fromkeys(body.credential_type_ids))
    if not selected_ids:
        # An empty allowlist is still "configured", which would hide every type
        # company-wide and leave no way to add a credential rule.  Resetting is
        # the deliberate way back to the full catalog.
        raise HTTPException(
            status_code=422,
            detail="Select at least one credential type, or reset to offer every type again",
        )
    async with get_connection() as conn:
        existing_rows = await conn.fetch(
            "SELECT id FROM credential_types WHERE id = ANY($1::uuid[])",
            selected_ids,
        )
        existing_ids = {row["id"] for row in existing_rows}
        missing_ids = [
            credential_type_id
            for credential_type_id in selected_ids
            if credential_type_id not in existing_ids
        ]
        if missing_ids:
            raise HTTPException(status_code=422, detail="One or more credential types do not exist")

        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO company_credential_type_filters (company_id, updated_by)
                VALUES ($1, $2)
                ON CONFLICT (company_id) DO UPDATE
                SET updated_by = EXCLUDED.updated_by, updated_at = NOW()
                """,
                company_id,
                user.id,
            )
            await conn.execute(
                "DELETE FROM company_credential_type_filter_items WHERE company_id = $1",
                company_id,
            )
            await conn.execute(
                """
                INSERT INTO company_credential_type_filter_items (company_id, credential_type_id)
                SELECT $1, credential_type_id
                FROM UNNEST($2::uuid[]) AS credential_type_id
                """,
                company_id,
                selected_ids,
            )
    return {"ok": True, "selected_count": len(selected_ids)}


@router.delete("/type-settings")
async def reset_credential_type_settings(
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(credential_settings_company_id),
):
    """Restore the legacy default where every credential type is offered."""
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM company_credential_type_filters WHERE company_id = $1",
            company_id,
        )
    return {"ok": True}


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
    _validate_schedule_blocking(enabled=body.schedule_blocking, legal_basis=body.legal_basis)
    async with get_connection() as conn:
        hidden = await find_hidden_credential_types(
            conn, company_id=company_id, credential_type_ids=[body.credential_type_id],
        )
        if hidden:
            raise HTTPException(
                status_code=422,
                detail="That credential type is not available to this company",
            )
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO credential_requirement_templates
                    (company_id, state, city, role_category_id, credential_type_id,
                     is_required, due_days, priority, notes, schedule_blocking,
                     warning_days, legal_basis, source, review_status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, 'admin_manual', 'approved')
                RETURNING *
                """,
                company_id, body.state, body.city, body.role_category_id,
                body.credential_type_id, body.is_required, body.due_days,
                body.priority, body.notes, body.schedule_blocking, body.warning_days,
                json.dumps(body.legal_basis or {}),
            )
            if row["schedule_blocking"]:
                await materialize_schedule_blocking_template(
                    conn, company_id=company_id, template_id=row["id"],
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
        if row["company_id"] and row["company_id"] != company_id and user.role != "admin":
            raise HTTPException(403, "Not authorized")
        if row["company_id"] is None and user.role != "admin":
            row = await _tenant_override_for_global_template(conn, row, company_id)
            template_id = row["id"]

        requested_blocking = body.schedule_blocking if body.schedule_blocking is not None else row["schedule_blocking"]
        requested_basis = body.legal_basis if body.legal_basis is not None else _legal_basis(row["legal_basis"])
        _validate_schedule_blocking(enabled=requested_blocking, legal_basis=requested_basis)

        updates = []
        params = []
        idx = 1
        for field in ["is_required", "due_days", "priority", "notes", "schedule_blocking", "warning_days"]:
            val = getattr(body, field, None)
            if val is not None:
                updates.append(f"{field} = ${idx}")
                params.append(val)
                idx += 1

        if body.legal_basis is not None:
            updates.append(f"legal_basis = ${idx}::jsonb")
            params.append(json.dumps(body.legal_basis))
            idx += 1

        if not updates:
            return dict(row)

        updates.append(f"updated_at = NOW()")
        params.append(template_id)

        async with conn.transaction():
            updated = await conn.fetchrow(
                f"UPDATE credential_requirement_templates SET {', '.join(updates)} "
                f"WHERE id = ${idx} RETURNING *",
                *params,
            )
            if updated["schedule_blocking"]:
                await materialize_schedule_blocking_template(
                    conn, company_id=updated["company_id"] or company_id, template_id=updated["id"],
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
        if row["company_id"] is None and user.role != "admin":
            raise HTTPException(403, "System templates can only be removed by an admin")
        if row["company_id"] and row["company_id"] != company_id and user.role != "admin":
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
    company_id: UUID = Depends(get_client_company_id),
):
    """Approve an AI-generated template."""
    async with get_connection() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                "SELECT * FROM credential_requirement_templates WHERE id = $1",
                template_id,
            )
            if not existing:
                raise HTTPException(404, "Template not found")
            if existing["company_id"] and existing["company_id"] != company_id and user.role != "admin":
                raise HTTPException(403, "Not authorized")
            if existing["company_id"] is None and user.role != "admin":
                existing = await _tenant_override_for_global_template(conn, existing, company_id)
            template_id = existing["id"]
            row = await conn.fetchrow(
                """
                UPDATE credential_requirement_templates
                SET review_status = 'approved', reviewed_by = $1, reviewed_at = NOW(), updated_at = NOW()
                WHERE id = $2
                RETURNING *
                """,
                user.id, template_id,
            )
            if not row:
                raise HTTPException(404, "Template not found")
            if row["schedule_blocking"]:
                await materialize_schedule_blocking_template(
                    conn, company_id=row["company_id"] or company_id, template_id=template_id,
                )
        return {"ok": True}


@router.post("/templates/{template_id}/reject")
async def reject_template(
    template_id: UUID,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Reject an AI-generated template."""
    async with get_connection() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                "SELECT * FROM credential_requirement_templates WHERE id = $1",
                template_id,
            )
            if not existing:
                raise HTTPException(404, "Template not found")
            if existing["company_id"] and existing["company_id"] != company_id and user.role != "admin":
                raise HTTPException(403, "Not authorized")
            if existing["company_id"] is None and user.role != "admin":
                existing = await _tenant_override_for_global_template(conn, existing, company_id)
            await conn.execute(
                """
                UPDATE credential_requirement_templates
                SET review_status = 'rejected', reviewed_by = $1, reviewed_at = NOW(), updated_at = NOW()
                WHERE id = $2
                """,
                user.id, existing["id"],
            )
        return {"ok": True}


@router.post("/bulk-approve")
async def bulk_approve(
    research_id: UUID = Query(...),
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Approve all pending templates from a research run."""
    async with get_connection() as conn:
        async with conn.transaction():
            research = await conn.fetchrow(
                "SELECT company_id FROM credential_research_logs WHERE id = $1",
                research_id,
            )
            if not research:
                raise HTTPException(404, "Research run not found")
            if research["company_id"] is None and user.role != "admin":
                raise HTTPException(403, "System research can only be approved by an admin")
            if research["company_id"] and research["company_id"] != company_id and user.role != "admin":
                raise HTTPException(403, "Not authorized")
            rows = await conn.fetch(
                """
                UPDATE credential_requirement_templates
                SET review_status = 'approved', reviewed_by = $1, reviewed_at = NOW(), updated_at = NOW()
                WHERE ai_research_id = $2 AND review_status = 'pending'
                RETURNING *
                """,
                user.id, research_id,
            )
            for row in rows:
                if row["schedule_blocking"] and row["company_id"]:
                    await materialize_schedule_blocking_template(
                        conn, company_id=row["company_id"], template_id=row["id"],
                    )
        count = len(rows)
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
            company_id=company_id,
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
    company_id: UUID = Depends(get_client_company_id),
):
    """Get all credential requirements for an employee."""
    async with get_connection() as conn:
        return await get_employee_credential_requirements(conn, employee_id, company_id)


@router.post("/employees/{employee_id}/requirements/{requirement_id}/waive")
async def waive_requirement(
    employee_id: UUID,
    requirement_id: UUID,
    body: WaiveRequest,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Waive a credential requirement for an employee."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT ecr.id FROM employee_credential_requirements ecr
               JOIN employees e ON e.id=ecr.employee_id
               WHERE ecr.id=$1 AND ecr.employee_id=$2 AND e.org_id=$3""",
            requirement_id, employee_id, company_id,
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

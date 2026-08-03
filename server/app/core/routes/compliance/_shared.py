"""compliance package — shared models/helpers/constants + router objects (L9 split)."""
import logging
from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import get_connection
from app.matcha.dependencies import get_client_company_id

router = APIRouter()
lite_router = APIRouter()
shared_router = APIRouter()
logger = logging.getLogger(__name__)



async def resolve_company_id(
    current_user, company_id_override: str | None
) -> UUID | None:
    """Resolve company ID, allowing admins to override via query param."""
    if current_user.role == "admin" and company_id_override:
        try:
            cid = UUID(company_id_override)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid company_id")
        async with get_connection() as conn:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM companies WHERE id = $1)", cid
            )
        if not exists:
            raise HTTPException(status_code=404, detail="Company not found")
        return cid
    return await get_client_company_id(current_user)




class DismissAlertRequest(BaseModel):
    """Optional correction data when dismissing an alert (Phase 3.1)."""

    is_false_positive: bool = True  # True if the alert was incorrect/not a real change
    correction_reason: Optional[str] = (
        None  # "misread_date", "wrong_jurisdiction", "hallucination", "outdated_source"
    )
    admin_notes: Optional[str] = None




class ActionPlanUpdateRequest(BaseModel):
    action_owner_id: Optional[str] = None
    next_action: Optional[str] = None
    action_due_date: Optional[date] = None
    recommended_playbook: Optional[str] = None
    estimated_financial_impact: Optional[str] = None
    mark_actioned: Optional[bool] = None




# =====================================================
# Verification Calibration Endpoints (Phase 1.2)
# =====================================================


class VerificationFeedbackRequest(BaseModel):
    actual_is_change: bool
    admin_notes: Optional[str] = None
    correction_reason: Optional[str] = (
        None  # "misread_date", "wrong_jurisdiction", "hallucination", etc.
    )




class LegislationAssignRequest(BaseModel):
    location_id: str
    action_owner_id: Optional[str] = None
    action_due_date: Optional[date] = None




async def _fetch_company_credentials(conn, company_id: UUID, *, kind: str) -> List[dict]:
    """Join a company's certs/licenses to their catalog row. kind ∈ {'certification','license'}.

    These back the Certifications & Licenses tab and surface the gap-analysis
    wizard's finalize output (company_certifications / company_licenses).
    """
    if kind == "certification":
        rows = await conn.fetch(
            """
            SELECT cc.id, cc.certification_id AS catalog_id, cat.slug, cat.name,
                   cat.issuing_authority, cat.scope_level, cat.industry_tag,
                   cat.renewal_months, cat.description, cat.source_url,
                   cc.location_id, cc.source, cc.status, cc.added_at
            FROM company_certifications cc
            JOIN certifications_catalog cat ON cat.id = cc.certification_id
            WHERE cc.company_id = $1
            ORDER BY cat.name
            """,
            company_id,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT cl.id, cl.license_id AS catalog_id, cat.slug, cat.name,
                   cat.issuing_authority, cat.scope_level, cat.industry_tag,
                   cat.renewal_months, cat.description, cat.source_url,
                   cl.location_id, cl.source, cl.status, cl.added_at
            FROM company_licenses cl
            JOIN licenses_catalog cat ON cat.id = cl.license_id
            WHERE cl.company_id = $1
            ORDER BY cat.name
            """,
            company_id,
        )
    out: List[dict] = []
    for r in rows:
        d = dict(r)
        d["id"] = str(d["id"])
        d["catalog_id"] = str(d["catalog_id"])
        d["location_id"] = str(d["location_id"]) if d["location_id"] is not None else None
        out.append(d)
    return out




# ── Regulatory Q&A ────────────────────────────────────────


class RegulatoryQuestionRequest(BaseModel):
    question: str
    location_id: Optional[str] = None




# ── Payer Medical Policy Navigator ────────────────────────────────────────


class PayerPolicyQuestionRequest(BaseModel):
    question: str
    location_id: Optional[str] = None
    payer_name: Optional[str] = None




class PayerPolicyResearchRequest(BaseModel):
    payer_name: str
    procedure: str




# ── Admin: CMS Policy Ingestion ────────────────────────────────────────


class CMSIngestRequest(BaseModel):
    source: str = "all"  # "ncds", "lcds", "all"
    state: Optional[str] = None
    embed: bool = True




# ──────────────────────────────────────────────────────────────────────────────
# Protocol Gap Analysis
# ──────────────────────────────────────────────────────────────────────────────


class ProtocolAnalysisRequest(BaseModel):
    protocol_text: str
    location_id: Optional[str] = None
    categories: Optional[List[str]] = None

__all__ = [
    "router",
    "lite_router",
    "shared_router",
    "logger",
    "ActionPlanUpdateRequest",
    "CMSIngestRequest",
    "DismissAlertRequest",
    "LegislationAssignRequest",
    "PayerPolicyQuestionRequest",
    "PayerPolicyResearchRequest",
    "ProtocolAnalysisRequest",
    "RegulatoryQuestionRequest",
    "VerificationFeedbackRequest",
    "_fetch_company_credentials",
    "resolve_company_id",
]

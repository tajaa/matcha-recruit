"""Client-facing risk portal (`/risk-profile`, feature `risk_profile`).

The report's "Risk Intelligence Central" (WTW p.10) for Matcha tenants: the
business's own composite risk index + WC/EPL/compliance component breakdown +
top fixes — "your insurability at a glance, and how to improve your terms."
The same `risk_index` engine the broker sees, scoped to the caller's own company.
"""

from fastapi import APIRouter, Depends

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services import risk_index
from ..services import risk_narrative
from ..services import submission_readiness
from ..services import venue_severity
from ..services import exclusion_gap

router = APIRouter()


@router.get("")
async def get_risk_profile(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        return await risk_index.compute_risk_index(conn, company_id)


@router.get("/readiness")
async def get_submission_readiness(current_user=Depends(require_admin_or_client)):
    """Submission-readiness completeness score + the 'finish these → tighter terms' checklist."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        return await submission_readiness.compute_readiness(conn, company_id)


@router.get("/venue")
async def get_venue_exposure(current_user=Depends(require_admin_or_client)):
    """Per-location venue / nuclear-verdict severity exposure (casualty severity lens)."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        return await venue_severity.company_venue_exposure(conn, company_id)


@router.get("/exclusions")
async def get_exclusion_gap(current_user=Depends(require_admin_or_client)):
    """Grounded emerging-exclusion exposure (PFAS, A&M, biometric, silent-cyber/AI…)."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        return await exclusion_gap.company_exclusions(conn, company_id)


@router.post("/narrative")
async def get_risk_narrative(current_user=Depends(require_admin_or_client)):
    """AI explanation of the index + prioritized moves to improve terms."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        result = await risk_index.compute_risk_index(conn, company_id)
        company = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", company_id)
    return await risk_narrative.narrative(result, company_name=company["name"] if company else None,
                                          audience="business")

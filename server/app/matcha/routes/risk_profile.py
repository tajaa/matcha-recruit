"""Client-facing risk portal (`/risk-profile`, feature `risk_profile`).

The report's "Risk Intelligence Central" (WTW p.10) for Matcha tenants: the
business's own composite risk index + WC/EPL/compliance component breakdown +
top fixes — "your insurability at a glance, and how to improve your terms."
The same `risk_index` engine the broker sees, scoped to the caller's own company.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services import risk_index
from ..services import risk_narrative
from ..services import submission_readiness
from ..services import venue_severity
from ..services import exclusion_gap

logger = logging.getLogger(__name__)

router = APIRouter()


def _degrade_503(exc: Exception, what: str) -> HTTPException:
    """Turn an unexpected best-effort service failure into a clean 503.

    The underlying services now propagate real DB errors (rather than reporting
    a falsely-clean profile off a partial read). At the client portal we don't
    want a bare 500 — surface a retryable 503 instead of leaking a stack.
    """
    logger.exception("risk-profile %s failed", what)
    return HTTPException(status_code=503, detail=f"{what} temporarily unavailable, please retry")


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
    try:
        async with get_connection() as conn:
            return await venue_severity.company_venue_exposure(conn, company_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise _degrade_503(exc, "Venue exposure")


@router.get("/exclusions")
async def get_exclusion_gap(current_user=Depends(require_admin_or_client)):
    """Grounded emerging-exclusion exposure (PFAS, A&M, biometric, silent-cyber/AI…)."""
    company_id = await get_client_company_id(current_user)
    try:
        async with get_connection() as conn:
            return await exclusion_gap.company_exclusions(conn, company_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise _degrade_503(exc, "Exclusion exposure")


@router.post("/narrative")
async def get_risk_narrative(current_user=Depends(require_admin_or_client)):
    """AI explanation of the index + prioritized moves to improve terms."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        result = await risk_index.compute_risk_index(conn, company_id)
        company = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", company_id)
    return await risk_narrative.narrative(result, company_name=company["name"] if company else None,
                                          audience="business")

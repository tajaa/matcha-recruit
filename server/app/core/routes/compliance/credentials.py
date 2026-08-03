"""credentials routes (L9 split)."""
from typing import List, Optional

from fastapi import Depends, HTTPException, Query

from app.core.models.auth import CurrentUser
from app.core.models.compliance import CompanyCertificationResponse, CompanyLicenseResponse
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client

from ._shared import _fetch_company_credentials, resolve_company_id, router



@router.get("/certifications", response_model=List[CompanyCertificationResponse])
async def list_company_certifications(
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Per-company certifications, joined to the catalog (admins may pass ?company_id=)."""
    cid = await resolve_company_id(current_user, company_id)
    if cid is None:
        raise HTTPException(status_code=403, detail="Access denied")
    async with get_connection() as conn:
        return await _fetch_company_credentials(conn, cid, kind="certification")




@router.get("/licenses", response_model=List[CompanyLicenseResponse])
async def list_company_licenses(
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Per-company licenses, joined to the catalog (admins may pass ?company_id=)."""
    cid = await resolve_company_id(current_user, company_id)
    if cid is None:
        raise HTTPException(status_code=403, detail="Access denied")
    async with get_connection() as conn:
        return await _fetch_company_credentials(conn, cid, kind="license")

"""Anonymous reporting token management.

Backs the public `/report/{token}` form. Token CRUD is per-company, gated
to admin/client. The form itself lives in `inbound_email.py`.
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id


router = APIRouter()


def _public_report_link(request: Request, token: str) -> str:
    """Build the public reporting URL the form lives at.

    Honors the X-Forwarded-Proto / Host pair set by nginx so links work
    behind the prod proxy as well as in local dev. Falls back to the
    request's own scheme/host if those headers aren't present.
    """
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}/report/{token}"


@router.get("/anonymous-reporting/status")
async def get_anonymous_reporting_status(
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Get the company's anonymous reporting token (or null if disabled)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Company not found")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT report_email_token, report_token_used_at FROM companies WHERE id = $1",
            company_id,
        )
    if not row or not row["report_email_token"]:
        return {"token": None, "link": None, "enabled": False, "used": False}
    token = row["report_email_token"]
    return {
        "token": token,
        "link": _public_report_link(request, token),
        "enabled": True,
        "used": row["report_token_used_at"] is not None,
    }


@router.post("/anonymous-reporting/generate")
async def generate_anonymous_reporting_token(
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Generate or regenerate the anonymous reporting token."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Company not found")
    token = secrets.token_hex(6)
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE companies SET report_email_token = $1, report_token_used_at = NULL WHERE id = $2",
            token,
            company_id,
        )
    return {
        "token": token,
        "link": _public_report_link(request, token),
        "enabled": True,
        "used": False,
    }


@router.delete("/anonymous-reporting/disable")
async def disable_anonymous_reporting(
    current_user=Depends(require_admin_or_client),
):
    """Disable anonymous reporting by clearing the token."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Company not found")
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE companies SET report_email_token = NULL WHERE id = $1",
            company_id,
        )
    return {"token": None, "enabled": False}

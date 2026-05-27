"""Anonymous reporting token management.

Backs the public `/report/{token}` form. Token CRUD is per-company, gated
to admin/client. The form itself lives in `inbound_email.py`.
"""
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id

from ._shared import _location_label


router = APIRouter()


def _build_public_link(request: Request, token: str, segment: str) -> str:
    """Build a public token URL under the given path ``segment``.

    Honors the X-Forwarded-Proto / Host pair set by nginx so links work
    behind the prod proxy as well as in local dev. Falls back to the
    request's own scheme/host if those headers aren't present.
    """
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}/{segment}/{token}"


def _public_report_link(request: Request, token: str) -> str:
    """Company-wide anonymous report URL (/report/{token})."""
    return _build_public_link(request, token, "report")


class LocationLinkCreate(BaseModel):
    location_id: str = Field(..., min_length=1)


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


# ---------------------------------------------------------------------------
# Per-location magic links — the public form lives at /intake/{token} and
# (unlike the anonymous /report link) hard-codes the location + is attributed.
# Stored in ir_report_links, single-use, one current link per location.
# ---------------------------------------------------------------------------

def _serialize_location_link(request: Request, row) -> dict:
    used_at = row.get("used_at")
    created_at = row.get("created_at")
    return {
        "id": str(row["id"]),
        "location_id": str(row["location_id"]),
        "location_name": row.get("location_name"),
        "location_label": _location_label(
            row.get("location_name"), row.get("city"), row.get("state")
        ),
        "token": row["token"],
        "link": _build_public_link(request, row["token"], "intake"),
        "used": used_at is not None,
        "used_at": used_at.isoformat() if used_at else None,
        "created_at": created_at.isoformat() if created_at else None,
    }


@router.get("/anonymous-reporting/location-links")
async def list_location_links(
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """List the company's per-location magic links (one row per location)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Company not found")
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT rl.id, rl.location_id, rl.token, rl.used_at, rl.created_at,
                   bl.name AS location_name, bl.city, bl.state
            FROM ir_report_links rl
            JOIN business_locations bl ON bl.id = rl.location_id
            WHERE rl.company_id = $1
            ORDER BY bl.name NULLS LAST, bl.city
            """,
            company_id,
        )
    return [_serialize_location_link(request, r) for r in rows]


@router.post("/anonymous-reporting/location-links")
async def generate_location_link(
    body: LocationLinkCreate,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Generate (or rotate) the single-use magic link for one location.

    Idempotent on (company_id, location_id): re-POSTing rotates the token and
    clears used_at, so the same endpoint serves "Generate" and "Regenerate".
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Company not found")
    token = secrets.token_hex(6)
    async with get_connection() as conn:
        owns = await conn.fetchrow(
            """
            SELECT id, name, city, state FROM business_locations
             WHERE id = $1 AND company_id = $2 AND is_active = true
            """,
            body.location_id,
            company_id,
        )
        if not owns:
            raise HTTPException(
                status_code=400,
                detail="Location not found for your company",
            )
        row = await conn.fetchrow(
            """
            INSERT INTO ir_report_links (company_id, location_id, token, created_by)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (company_id, location_id)
            DO UPDATE SET token = EXCLUDED.token,
                          used_at = NULL,
                          created_by = EXCLUDED.created_by,
                          created_at = NOW()
            RETURNING id, location_id, token, used_at, created_at
            """,
            company_id,
            body.location_id,
            token,
            str(current_user.id),
        )
    merged = dict(row)
    merged["location_name"] = owns["name"]
    merged["city"] = owns["city"]
    merged["state"] = owns["state"]
    return _serialize_location_link(request, merged)


@router.delete("/anonymous-reporting/location-links/{link_id}")
async def revoke_location_link(
    link_id: str,
    current_user=Depends(require_admin_or_client),
):
    """Revoke (hard-delete) a per-location magic link."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        UUID(link_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Link not found")
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM ir_report_links WHERE id = $1 AND company_id = $2",
            link_id,
            company_id,
        )
    if result.endswith(" 0"):
        raise HTTPException(status_code=404, detail="Link not found")
    return {"deleted": True}

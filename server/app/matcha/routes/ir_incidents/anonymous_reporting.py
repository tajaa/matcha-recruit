"""Anonymous reporting token management.

Backs the public `/report/{token}` form. Token CRUD is per-company, gated
to admin/client. The form itself lives in `inbound_email.py`.
"""
import json
import secrets
from datetime import datetime
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.services.ir_report_poster import (
    build_report_poster_pdf, resolve_branding, DEFAULT_BRANDING,
)

from ._shared import _build_public_link, _location_label

_HEX = r"^#[0-9a-fA-F]{6}$"


async def _load_poster_branding(conn, company_id) -> Optional[dict]:
    """Raw stored poster branding for a company, or None (→ Matcha defaults).
    Best-effort: tolerates the column not existing yet (deployed before the
    posterbrand01 migration) so poster downloads never 500 on migration lag.
    JSONB comes back as a str (no pool codec) → parse it."""
    try:
        raw = await conn.fetchval(
            "SELECT report_poster_branding FROM companies WHERE id = $1", company_id
        )
    except asyncpg.exceptions.UndefinedColumnError:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return None
    return raw if isinstance(raw, dict) else None


router = APIRouter()


def _public_report_link(request: Request, token: str) -> str:
    """Company-wide anonymous report URL (/report/{token})."""
    return _build_public_link(request, token, "report")


class LocationLinkCreate(BaseModel):
    location_id: str = Field(..., min_length=1)
    # Optional limits — NULL = unlimited uses / never expires.
    max_uses: Optional[int] = Field(None, ge=1)
    expires_at: Optional[datetime] = None


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
    token = secrets.token_urlsafe(24)
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


class PosterBrandingBody(BaseModel):
    primary: str = Field(..., pattern=_HEX)
    secondary: str = Field(..., pattern=_HEX)


@router.get("/anonymous-reporting/branding")
async def get_poster_branding(current_user=Depends(require_admin_or_client)):
    """Current QR-poster palette (defaults-merged) + the Matcha default to reset to."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Company not found")
    async with get_connection() as conn:
        stored = await _load_poster_branding(conn, company_id)
    return {"branding": resolve_branding(stored), "default": DEFAULT_BRANDING}


@router.put("/anonymous-reporting/branding")
async def set_poster_branding(
    body: PosterBrandingBody,
    current_user=Depends(require_admin_or_client),
):
    """Store the client's QR-poster palette. Only primary/secondary are
    configurable — Matcha branding on the poster is fixed and always rendered."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Company not found")
    branding = resolve_branding(body.model_dump())
    async with get_connection() as conn:
        try:
            await conn.execute(
                "UPDATE companies SET report_poster_branding = $1::jsonb WHERE id = $2",
                json.dumps(branding), company_id,
            )
        except asyncpg.exceptions.UndefinedColumnError:
            raise HTTPException(
                status_code=503,
                detail="Poster branding storage is being provisioned. Try again shortly.",
            )
    return {"branding": branding, "default": DEFAULT_BRANDING}


@router.get("/anonymous-reporting/poster.pdf")
async def get_anonymous_reporting_poster(
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Branded, print-ready PDF poster for the company-wide /report link."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Company not found")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT report_email_token FROM companies WHERE id = $1",
            company_id,
        )
        branding = await _load_poster_branding(conn, company_id)
    if not row or not row["report_email_token"]:
        raise HTTPException(status_code=404, detail="Anonymous reporting is not enabled")
    link = _public_report_link(request, row["report_email_token"])
    pdf = build_report_poster_pdf(link, branding=branding)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=incident-qr-poster.pdf"},
    )


# ---------------------------------------------------------------------------
# Per-location magic links — the public form lives at /intake/{token} and
# (unlike the anonymous /report link) hard-codes the location + is attributed.
# Stored in ir_report_links: REUSABLE (not single-use) — valid until revoked,
# expired, or the optional max_uses cap is hit. One live row per location;
# regenerate/revoke retire the old token into ir_report_link_history.
# ---------------------------------------------------------------------------

def _link_status(row) -> str:
    """active | revoked | expired — derived from the row's state."""
    if not row.get("is_active", True):
        return "revoked"
    expires_at = row.get("expires_at")
    if expires_at is not None and expires_at <= datetime.now(expires_at.tzinfo):
        return "expired"
    return "active"


def _serialize_location_link(request: Request, row) -> dict:
    used_at = row.get("used_at")
    created_at = row.get("created_at")
    revoked_at = row.get("revoked_at")
    expires_at = row.get("expires_at")
    use_count = row.get("use_count") or 0
    return {
        "id": str(row["id"]),
        "location_id": str(row["location_id"]),
        "location_name": row.get("location_name"),
        "location_label": _location_label(
            row.get("location_name"), row.get("city"), row.get("state")
        ),
        "token": row["token"],
        "link": _build_public_link(request, row["token"], "intake"),
        "is_active": bool(row.get("is_active", True)),
        "status": _link_status(row),
        "use_count": use_count,
        "max_uses": row.get("max_uses"),
        "used": use_count > 0,
        "last_used_at": used_at.isoformat() if used_at else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "revoked_at": revoked_at.isoformat() if revoked_at else None,
        "created_at": created_at.isoformat() if created_at else None,
    }


# Columns selected wherever we serialize a link, to keep list/generate/revoke aligned.
_LINK_COLS = (
    "rl.id, rl.location_id, rl.token, rl.used_at, rl.created_at, "
    "rl.is_active, rl.revoked_at, rl.use_count, rl.max_uses, rl.expires_at"
)


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
            f"""
            SELECT {_LINK_COLS},
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
    """Generate (or rotate) the reusable magic link for one location.

    Idempotent on (company_id, location_id): re-POSTing rotates the token,
    resets counters, and revives a revoked link — so the same endpoint serves
    "Generate" and "Regenerate". The outgoing token (if any) is retired into
    ir_report_link_history with reason 'rotated' for the forensic trail.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Company not found")
    token = secrets.token_urlsafe(24)
    async with get_connection() as conn:
        async with conn.transaction():
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
            # Retire the current token (if this location already has one) before
            # we overwrite it on the UPSERT.
            existing = await conn.fetchrow(
                """
                SELECT id, token, use_count, created_at
                FROM ir_report_links
                WHERE company_id = $1 AND location_id = $2
                FOR UPDATE
                """,
                company_id,
                body.location_id,
            )
            if existing:
                await conn.execute(
                    """
                    INSERT INTO ir_report_link_history
                        (link_id, company_id, location_id, token, went_live_at,
                         retired_reason, use_count, retired_by)
                    VALUES ($1, $2, $3, $4, $5, 'rotated', $6, $7)
                    """,
                    existing["id"], company_id, body.location_id,
                    existing["token"], existing["created_at"],
                    existing["use_count"] or 0, str(current_user.id),
                )
            row = await conn.fetchrow(
                f"""
                INSERT INTO ir_report_links
                    (company_id, location_id, token, created_by, max_uses, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (company_id, location_id)
                DO UPDATE SET token = EXCLUDED.token,
                              used_at = NULL,
                              is_active = true,
                              revoked_at = NULL,
                              use_count = 0,
                              max_uses = EXCLUDED.max_uses,
                              expires_at = EXCLUDED.expires_at,
                              created_by = EXCLUDED.created_by,
                              created_at = NOW()
                RETURNING {_LINK_COLS.replace('rl.', '')}
                """,
                company_id,
                body.location_id,
                token,
                str(current_user.id),
                body.max_uses,
                body.expires_at,
            )
    merged = dict(row)
    merged["location_name"] = owns["name"]
    merged["city"] = owns["city"]
    merged["state"] = owns["state"]
    return _serialize_location_link(request, merged)


@router.delete("/anonymous-reporting/location-links/{link_id}")
async def revoke_location_link(
    request: Request,
    link_id: str,
    current_user=Depends(require_admin_or_client),
):
    """Soft-revoke a per-location magic link.

    The row stays (so it keeps its history and can be revived via regenerate);
    is_active flips to false and the live token is retired into history with
    reason 'revoked'. The public /intake form rejects a revoked link with 410.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        UUID(link_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Link not found")
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT id, location_id, token, use_count, created_at, is_active
                FROM ir_report_links
                WHERE id = $1 AND company_id = $2
                FOR UPDATE
                """,
                link_id,
                company_id,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Link not found")
            if row["is_active"]:
                await conn.execute(
                    """
                    INSERT INTO ir_report_link_history
                        (link_id, company_id, location_id, token, went_live_at,
                         retired_reason, use_count, retired_by)
                    VALUES ($1, $2, $3, $4, $5, 'revoked', $6, $7)
                    """,
                    row["id"], company_id, row["location_id"], row["token"],
                    row["created_at"], row["use_count"] or 0, str(current_user.id),
                )
            updated = await conn.fetchrow(
                f"""
                UPDATE ir_report_links rl
                SET is_active = false, revoked_at = NOW()
                FROM business_locations bl
                WHERE rl.id = $1 AND rl.company_id = $2 AND bl.id = rl.location_id
                RETURNING {_LINK_COLS},
                          bl.name AS location_name, bl.city, bl.state
                """,
                link_id,
                company_id,
            )
    return _serialize_location_link(request, updated)


@router.get("/anonymous-reporting/location-links/{link_id}/history")
async def location_link_history(
    link_id: str,
    current_user=Depends(require_admin_or_client),
):
    """Rotation history for one location link: the live token plus every
    retired (rotated/revoked) token, newest first."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        UUID(link_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Link not found")
    async with get_connection() as conn:
        live = await conn.fetchrow(
            """
            SELECT token, use_count, created_at, is_active, revoked_at
            FROM ir_report_links
            WHERE id = $1 AND company_id = $2
            """,
            link_id,
            company_id,
        )
        if not live:
            raise HTTPException(status_code=404, detail="Link not found")
        hist = await conn.fetch(
            """
            SELECT token, went_live_at, retired_at, retired_reason, use_count
            FROM ir_report_link_history
            WHERE link_id = $1 AND company_id = $2
            ORDER BY retired_at DESC
            """,
            link_id,
            company_id,
        )
    entries = []
    # Top entry = the current token (only meaningful while the link is live).
    if live["is_active"]:
        entries.append({
            "token": live["token"],
            "status": "active",
            "use_count": live["use_count"] or 0,
            "went_live_at": live["created_at"].isoformat() if live["created_at"] else None,
            "retired_at": None,
        })
    for h in hist:
        entries.append({
            "token": h["token"],
            "status": h["retired_reason"],
            "use_count": h["use_count"] or 0,
            "went_live_at": h["went_live_at"].isoformat() if h["went_live_at"] else None,
            "retired_at": h["retired_at"].isoformat() if h["retired_at"] else None,
        })
    return entries


@router.get("/anonymous-reporting/location-links/{link_id}/poster.pdf")
async def get_location_link_poster(
    request: Request,
    link_id: str,
    current_user=Depends(require_admin_or_client),
):
    """Branded, print-ready PDF poster for one location's /intake link."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        UUID(link_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Link not found")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT rl.token, bl.name AS location_name, bl.city, bl.state
            FROM ir_report_links rl
            JOIN business_locations bl ON bl.id = rl.location_id
            WHERE rl.id = $1 AND rl.company_id = $2
            """,
            link_id,
            company_id,
        )
        branding = await _load_poster_branding(conn, company_id)
    if not row:
        raise HTTPException(status_code=404, detail="Link not found")
    link = _build_public_link(request, row["token"], "intake")
    subtitle = _location_label(row["location_name"], row["city"], row["state"])
    pdf = build_report_poster_pdf(link, subtitle=subtitle, branding=branding)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=incident-qr-poster.pdf"},
    )

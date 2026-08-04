"""Matcha admin oversight of the Cappe creator marketplace.

Style-matches the `admin/research.py` cappe section: `require_admin`
per-route, raw SQL, no cappe imports (cappe -> matcha is 0 edges; this file
lives on the matcha side of that boundary and never imports app.cappe.*).
Every mutation is audited into cappe_admin_audit with actor_account_id=NULL
(the actor is a matcha admin, not a cappe account) — the `matcha:` action
prefix + admin email in the payload identify who did it.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.core.dependencies import require_admin
from app.core.services.email import get_email_service
from app.database import get_connection

logger = logging.getLogger("admin.cappe_creators")

router = APIRouter(prefix="/cappe", tags=["admin-cappe-creators"])

# min_offer_cents/auto_approve_days fallbacks are pinned to the migration seed
# row (zzzzcappe28_creator_marketplace) and services/collab.py's own resolver
# defaults — keep the three in sync if either changes. collab_fee_bps has no
# hardcoded default here: it must match services/collab.py:resolve_collab_fee_bps's
# fallback exactly (get_settings().cappe_platform_fee_bps), or this admin screen
# reports a different fee than checkout actually charges.
_MARKETPLACE_SETTINGS_DEFAULTS = {"min_offer_cents": 5000}


def _settings_subvalue(values: dict, key: str, subkey: str, fallback):
    """Mirrors services/collab.py:resolve_marketplace_int's defensive parsing —
    a malformed settings row (not a JSON object, or missing the subkey) falls
    back instead of 500ing the admin screen."""
    row = values.get(key)
    if not isinstance(row, dict):
        return fallback
    return row.get(subkey, fallback)


async def _audit(conn, admin_user, action: str, target: str, payload: dict) -> None:
    await conn.execute(
        "INSERT INTO cappe_admin_audit (actor_account_id, action, target, payload) "
        "VALUES (NULL, $1, $2, $3::jsonb)",
        f"matcha:{action}", target,
        json.dumps({**payload, "admin_email": admin_user.email}),
    )


async def _send_review_email(handle: str, to_email: str, approved: bool, note: Optional[str]) -> None:
    """Core admin sends this itself (inline template) rather than importing a
    cappe email helper — keeps core -> cappe at 0 edges. Only 2 short emails,
    not worth a shared template for."""
    if approved:
        subject = "Your Gummfit creator profile is live"
        html = (
            f"<p>Your creator profile (@{handle}) has been approved and is now live on "
            f"<a href=\"https://gummfit.com/creators/{handle}\">gummfit.com/creators/{handle}</a>.</p>"
            "<p>Brands can now discover you and send collab offers.</p>"
        )
    else:
        subject = "Your Gummfit creator profile needs changes"
        note_html = f"<p>{note}</p>" if note else ""
        html = (
            "<p>Your creator profile submission wasn't approved yet.</p>"
            f"{note_html}"
            "<p>You can update your profile and resubmit any time.</p>"
        )
    try:
        await get_email_service().send_email_with_fallback(
            to_email=to_email, to_name=None, subject=subject, html_content=html,
        )
    except Exception:  # noqa: BLE001 — review action must succeed even if email delivery fails
        logger.warning("cappe creator review email failed for %s", to_email, exc_info=True)


@router.get("/creators", dependencies=[Depends(require_admin)])
async def admin_list_creators(status_filter: Optional[str] = None):
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT p.id, p.handle, p.display_name, p.avatar_url, p.status, p.review_note,
                   p.niches, p.location, p.open_to_offers, p.reach_verified, p.reach_audited_at,
                   p.submitted_at, p.published_at, p.created_at,
                   a.email, a.name AS account_name,
                   COALESCE(json_agg(json_build_object(
                       'id', s.id, 'platform', s.platform, 'handle', s.handle, 'url', s.url,
                       'follower_count', s.follower_count,
                       'verified_follower_count', s.verified_follower_count,
                       'audit_status', s.audit_status, 'audited_at', s.audited_at,
                       'audit_note', s.audit_note
                   ) ORDER BY s.sort_order) FILTER (WHERE s.id IS NOT NULL), '[]') AS socials
              FROM cappe_creator_profiles p
              JOIN cappe_accounts a ON a.id = p.account_id
              LEFT JOIN cappe_creator_socials s ON s.profile_id = p.id
             WHERE ($1::text IS NULL OR p.status = $1)
             GROUP BY p.id, a.email, a.name
             ORDER BY (p.status = 'pending_review') DESC, p.submitted_at DESC NULLS LAST, p.created_at DESC
            """,
            status_filter,
        )
    out = []
    for r in rows:
        d = dict(r)
        d["socials"] = json.loads(d["socials"]) if isinstance(d["socials"], str) else d["socials"]
        # Due if genuinely stale (audited >90d ago) OR live with socials that
        # have never been through an admin audit at all (reach_audited_at is
        # only ever set by the per-social audit endpoint — a self-service
        # social edit after a prior audit doesn't touch it, so a published
        # profile can carry brand-new unaudited rows under an old or NULL
        # timestamp; both must surface here, not just the "old date" case).
        d["reaudit_due"] = bool(
            r["status"] == "published" and d["socials"]
            and (r["reach_audited_at"] is None
                 or r["reach_audited_at"] < datetime.now(timezone.utc) - timedelta(days=90))
        )
        out.append(d)
    return out


@router.post("/creators/{profile_id}/approve")
async def admin_approve_creator(profile_id: UUID, current_user=Depends(require_admin)):
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """UPDATE cappe_creator_profiles p
                      SET status='published', reviewed_at=NOW(),
                          published_at=COALESCE(published_at, NOW()), review_note=NULL, updated_at=NOW()
                    FROM cappe_accounts a
                   WHERE p.id=$1 AND p.status='pending_review' AND a.id = p.account_id
               RETURNING p.id, p.handle, a.email""",
                profile_id,
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                    detail="Profile is not pending review")
            await _audit(conn, current_user, "creators.approve", str(profile_id), {"handle": row["handle"]})
    await _send_review_email(row["handle"], row["email"], approved=True, note=None)
    return {"ok": True, "handle": row["handle"]}


class _RejectBody(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


@router.post("/creators/{profile_id}/reject")
async def admin_reject_creator(profile_id: UUID, body: _RejectBody, current_user=Depends(require_admin)):
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """UPDATE cappe_creator_profiles p
                      SET status='rejected', reviewed_at=NOW(), review_note=$2, updated_at=NOW()
                    FROM cappe_accounts a
                   WHERE p.id=$1 AND p.status='pending_review' AND a.id = p.account_id
               RETURNING p.id, p.handle, a.email""",
                profile_id, body.note,
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                    detail="Profile is not pending review")
            await _audit(conn, current_user, "creators.reject", str(profile_id),
                         {"handle": row["handle"], "note": body.note})
    await _send_review_email(row["handle"], row["email"], approved=False, note=body.note)
    return {"ok": True, "handle": row["handle"]}


class _SuspendBody(BaseModel):
    note: Optional[str] = Field(default=None, max_length=2000)


@router.post("/creators/{profile_id}/suspend")
async def admin_suspend_creator(profile_id: UUID, body: _SuspendBody, current_user=Depends(require_admin)):
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """UPDATE cappe_creator_profiles
                      SET status='suspended', review_note=$2, updated_at=NOW()
                    WHERE id=$1 AND status='published'
                RETURNING id, handle""",
                profile_id, body.note,
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile is not published")
            await _audit(conn, current_user, "creators.suspend", str(profile_id),
                         {"handle": row["handle"], "note": body.note})
    return {"ok": True, "handle": row["handle"]}


@router.post("/creators/{profile_id}/restore")
async def admin_restore_creator(profile_id: UUID, current_user=Depends(require_admin)):
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """UPDATE cappe_creator_profiles
                      SET status='published', review_note=NULL, updated_at=NOW()
                    WHERE id=$1 AND status='suspended'
                RETURNING id, handle""",
                profile_id,
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile is not suspended")
            await _audit(conn, current_user, "creators.restore", str(profile_id), {"handle": row["handle"]})
    return {"ok": True, "handle": row["handle"]}


class _SocialAuditBody(BaseModel):
    audit_status: Literal["verified", "flagged", "unverified"]
    verified_follower_count: Optional[int] = Field(default=None, ge=0)
    note: Optional[str] = Field(default=None, max_length=2000)


@router.post("/creators/socials/{social_id}/audit")
async def admin_audit_social(social_id: UUID, body: _SocialAuditBody, current_user=Depends(require_admin)):
    if body.audit_status == "verified" and body.verified_follower_count is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="verified_follower_count is required when audit_status='verified'")
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """UPDATE cappe_creator_socials
                      SET audit_status=$2, verified_follower_count=$3, audit_note=$4,
                          audited_at=NOW(), audited_by=$5, updated_at=NOW()
                    WHERE id=$1
                RETURNING profile_id""",
                social_id, body.audit_status, body.verified_follower_count, body.note, current_user.email,
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Social not found")
            profile_id = row["profile_id"]
            await conn.execute(
                """UPDATE cappe_creator_profiles p SET
                       reach_verified = EXISTS (SELECT 1 FROM cappe_creator_socials s
                                                 WHERE s.profile_id = p.id AND s.audit_status='verified')
                                   AND NOT EXISTS (SELECT 1 FROM cappe_creator_socials s
                                                 WHERE s.profile_id = p.id AND s.audit_status='flagged'),
                       reach_audited_at = NOW(), updated_at = NOW()
                 WHERE p.id = $1""",
                profile_id,
            )
            await _audit(conn, current_user, "creators.social_audit", str(social_id),
                         {"profile_id": str(profile_id), "audit_status": body.audit_status,
                          "verified_follower_count": body.verified_follower_count})
    return {"ok": True}


@router.get("/marketplace-settings", dependencies=[Depends(require_admin)])
async def admin_get_marketplace_settings():
    async with get_connection() as conn:
        rows = await conn.fetch("SELECT key, value FROM cappe_marketplace_settings")
    values = {r["key"]: json.loads(r["value"]) if isinstance(r["value"], str) else r["value"] for r in rows}
    return {
        "collab_fee_bps": _settings_subvalue(values, "collab_fee_bps", "bps", get_settings().cappe_platform_fee_bps),
        "min_offer_cents": _settings_subvalue(values, "min_offer_cents", "cents", _MARKETPLACE_SETTINGS_DEFAULTS["min_offer_cents"]),
        "auto_approve_days": _settings_subvalue(values, "auto_approve_days", "days", 14),
    }


class _MarketplaceSettingsPatch(BaseModel):
    collab_fee_bps: Optional[int] = Field(default=None, ge=0, le=5000)
    min_offer_cents: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    auto_approve_days: Optional[int] = Field(default=None, ge=1, le=90)


@router.patch("/marketplace-settings")
async def admin_patch_marketplace_settings(body: _MarketplaceSettingsPatch, current_user=Depends(require_admin)):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return {"ok": True}
    key_for = {"collab_fee_bps": ("collab_fee_bps", "bps"),
               "min_offer_cents": ("min_offer_cents", "cents"),
               "auto_approve_days": ("auto_approve_days", "days")}
    async with get_connection() as conn:
        old_rows = await conn.fetch("SELECT key, value FROM cappe_marketplace_settings")
        old_values = {r["key"]: json.loads(r["value"]) if isinstance(r["value"], str) else r["value"] for r in old_rows}
        async with conn.transaction():
            for field, value in updates.items():
                key, subkey = key_for[field]
                await conn.execute(
                    "INSERT INTO cappe_marketplace_settings (key, value) VALUES ($1, $2::jsonb) "
                    "ON CONFLICT (key) DO UPDATE SET value=$2::jsonb, updated_at=NOW()",
                    key, json.dumps({subkey: value}),
                )
            await _audit(conn, current_user, "creators.settings", "marketplace-settings",
                         {"old": old_values, "new": updates})
    return {"ok": True}


@router.get("/collab-overview", dependencies=[Depends(require_admin)])
async def admin_collab_overview():
    async with get_connection() as conn:
        status_rows = await conn.fetch(
            "SELECT status, COUNT(*) AS n, COALESCE(SUM(total_cents),0) AS total_cents "
            "FROM cappe_collab_offers GROUP BY status"
        )
        gmv_row = await conn.fetchrow(
            "SELECT COALESCE(SUM(amount_cents),0) AS gmv_cents, COALESCE(SUM(fee_cents),0) AS fees_cents "
            "FROM cappe_collab_payments WHERE status='paid'"
        )
        brand_rows = await conn.fetch(
            """SELECT ba.id AS brand_account_id, ba.name AS brand_name, ba.email AS brand_email,
                      COUNT(DISTINCT o.id) AS offers_sent,
                      COUNT(DISTINCT o.id) FILTER (WHERE o.status = 'completed') AS completed,
                      COUNT(DISTINCT o.id) FILTER (WHERE o.status = 'active') AS in_progress,
                      COUNT(DISTINCT o.id) FILTER (WHERE o.status = 'cancelled' AND o.cancelled_by = 'brand') AS brand_cancelled,
                      AVG(EXTRACT(EPOCH FROM (p.paid_at - p.due_at)) / 3600.0)
                          FILTER (WHERE p.paid_at IS NOT NULL AND p.due_at IS NOT NULL) AS avg_hours_to_pay
                 FROM cappe_collab_offers o
                 JOIN cappe_accounts ba ON ba.id = o.brand_account_id
                 LEFT JOIN cappe_collab_payments p ON p.offer_id = o.id
                GROUP BY ba.id, ba.name, ba.email
                ORDER BY completed DESC, offers_sent DESC"""
        )
    return {
        "by_status": [dict(r) for r in status_rows],
        "gmv_cents": gmv_row["gmv_cents"],
        "fees_cents": gmv_row["fees_cents"],
        "brands": [dict(r) for r in brand_rows],
    }

"""Tell-Us public brand community page — unauthenticated, one brand's
published reviews at /tellus/b/{slug}. Mirrors public_intake.py's hygiene
(rate limit, no auth) since this is the other unauthenticated surface in the
app.
"""
from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from ...core.services.redis_cache import check_rate_limit, client_ip
from ...database import get_connection
from ..dependencies import optional_consumer_account_id, require_tellus_account
from ..models.tellus import (
    TellusAccount, TellusClaimResponse, TellusMyClaim, TellusPublicBrandPage,
    TellusPublicReview, TellusReportMedia, TellusMessagingStore,
)
from ..services.admin_audit import record_admin_action
from ..services.likes_service import hydrate_likes
from ._shared import _answer_rows_to_models, _media_url
from .places import ensure_community_link

router = APIRouter()


@router.get("/b/{slug}", response_model=TellusPublicBrandPage)
async def public_brand_page(
    slug: str, request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    scope: str = Query(default="recent", pattern="^(recent|older)$"),
    authorization: Optional[str] = Header(default=None),
):
    await check_rate_limit(client_ip(request), "tellus_public_brand", 120, 3600)
    viewer_id = await optional_consumer_account_id(authorization)

    async with get_connection() as conn:
        brand = await conn.fetchrow(
            "SELECT id, name, slug, logo_url, owner_account_id, plan_status, messaging_enabled FROM tellus_brands WHERE slug = $1", slug
        )
        if brand is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")

        has_board = bool(await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM tellus_boards WHERE brand_id = $1 AND is_active)", brand["id"],
        )) and brand["plan_status"] == "active"

        claimed = brand["owner_account_id"] is not None
        followed = bool(await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM tellus_brand_follows WHERE brand_id = $1 AND consumer_account_id = $2)",
            brand["id"], viewer_id,
        )) if viewer_id is not None else False
        intake_token = None
        if not claimed:
            intake_token = await conn.fetchval(
                "SELECT token FROM tellus_links WHERE brand_id = $1 AND is_active ORDER BY created_at LIMIT 1",
                brand["id"],
            )

        # Primary store = first created (same convention as ensure_community_link's
        # store pick in routes/places.py).
        store = await conn.fetchrow(
            "SELECT address, city, state FROM tellus_stores WHERE brand_id = $1 "
            "ORDER BY created_at LIMIT 1",
            brand["id"],
        )
        stores = await conn.fetch(
            "SELECT id, name, address, city, state FROM tellus_stores WHERE brand_id = $1 ORDER BY created_at",
            brand["id"],
        )

        # Published = held + past its 48h hold + still visible. Hits
        # ix_tellus_reports_public. Strict equality to 'visible' (not just
        # <> 'removed') means a 'flagged' review also drops off the public
        # page while triage is pending, not just a fully 'removed' one.
        #
        # Rolling window: the headline rating/count only ever reflects the
        # last 12 months — old reviews stop haunting the business but stay
        # reachable via scope=older ("Show older reviews" on the public page).
        agg = await conn.fetchrow(
            """SELECT COUNT(*) AS review_count, AVG(rating) AS avg_rating
               FROM tellus_reports
               WHERE brand_id = $1 AND review_state = 'held' AND publish_at <= NOW()
                 AND publish_at >= NOW() - interval '12 months'
                 AND moderation_status = 'visible'""",
            brand["id"],
        )
        older_count = await conn.fetchval(
            """SELECT COUNT(*) FROM tellus_reports
               WHERE brand_id = $1 AND review_state = 'held' AND publish_at <= NOW()
                 AND publish_at < NOW() - interval '12 months'
                 AND moderation_status = 'visible'""",
            brand["id"],
        )

        window = ("AND r.publish_at >= NOW() - interval '12 months'" if scope == "recent"
                  else "AND r.publish_at < NOW() - interval '12 months'")
        rows = await conn.fetch(
            f"""SELECT r.*, a.display_name, s.name AS store_name
                FROM tellus_reports r
                LEFT JOIN tellus_accounts a ON a.id = r.reporter_account_id
                LEFT JOIN tellus_stores s ON s.id = r.store_id
                WHERE r.brand_id = $1 AND r.review_state = 'held' AND r.publish_at <= NOW()
                  {window} AND r.moderation_status = 'visible'
                ORDER BY r.publish_at DESC
                LIMIT $2 OFFSET $3""",
            brand["id"], limit, offset,
        )

        report_ids = [r["id"] for r in rows]
        media_by_report: dict = {}
        answers_by_report: dict = {}
        if report_ids:
            mrows = await conn.fetch(
                "SELECT id, report_id, media_type, mime_type, original_filename, storage_path "
                "FROM tellus_report_media WHERE report_id = ANY($1::uuid[]) ORDER BY created_at",
                report_ids,
            )
            for m in mrows:
                media_by_report.setdefault(m["report_id"], []).append(
                    TellusReportMedia(
                        id=m["id"], media_type=m["media_type"], mime_type=m["mime_type"],
                        original_filename=m["original_filename"], url=_media_url(m["storage_path"]),
                    )
                )

            arows = await conn.fetch(
                "SELECT id, report_id, prompt_text, answer, position FROM tellus_report_answers "
                "WHERE report_id = ANY($1::uuid[]) ORDER BY report_id, position", report_ids,
            )
            for a in arows:
                answers_by_report.setdefault(a["report_id"], []).append(a)

        likes = await hydrate_likes(conn, "report", report_ids, viewer_id)

        reviews = [
            TellusPublicReview(
                id=r["id"],
                rating=r["rating"] or 0,
                title=r["title"],
                description=r["description"],
                reviewer_name=r["display_name"] or "Tell-Us member",
                store_name=r["store_name"],
                created_at=r["created_at"],
                publish_at=r["publish_at"],
                hearted=r["hearted_at"] is not None,
                brand_reply=r["brand_public_reply"],
                brand_reply_at=r["brand_public_reply_at"],
                media=media_by_report.get(r["id"], []),
                answers=_answer_rows_to_models(answers_by_report.get(r["id"], [])),
                like_count=likes.get(r["id"], (0, False))[0],
                liked_by_me=likes.get(r["id"], (0, False))[1],
            )
            for r in rows
        ]

    older_count = older_count or 0
    # Pagination target tracks the requested scope so Load-more works for
    # either list — the headline review_count/avg_rating stay recent-only.
    total = (agg["review_count"] or 0) if scope == "recent" else older_count

    return TellusPublicBrandPage(
        brand_name=brand["name"],
        slug=brand["slug"],
        logo_url=brand["logo_url"],
        review_count=agg["review_count"] or 0,
        avg_rating=round(agg["avg_rating"], 2) if agg["avg_rating"] is not None else None,
        reviews=reviews,
        total=total,
        claimed=claimed,
        intake_token=intake_token,
        address=store["address"] if store else None,
        city=store["city"] if store else None,
        state=store["state"] if store else None,
        older_count=older_count,
        has_board=has_board,
        messaging_enabled=bool(claimed and brand["messaging_enabled"]),
        stores=[TellusMessagingStore(**dict(s)) for s in stores],
        followed=followed,
    )


@router.post("/b/{slug}/claim", response_model=TellusClaimResponse)
async def claim_brand(
    slug: str, request: Request, account: TellusAccount = Depends(require_tellus_account),
):
    """'Is this your business?' self-serve claim. Files a PENDING row in
    tellus_brand_claims — does NOT flip ownership or account_type. An admin
    must approve via routes/admin/claims.py (mirrors the old assign_owner
    logic there) before anything changes. Payment stays the verification bar
    after approval, same as before — plan_status is untouched here.
    """
    ip = client_ip(request)
    await check_rate_limit(ip, "tellus_brand_claim", 5, 3600)
    await check_rate_limit(str(account.id), "tellus_brand_claim_acct", 3, 86400)

    async with get_connection() as conn:
        async with conn.transaction():
            brand = await conn.fetchrow(
                "SELECT id, owner_account_id FROM tellus_brands WHERE slug = $1 FOR UPDATE", slug
            )
            if brand is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
            if brand["owner_account_id"] is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This business has already been claimed.",
                )
            # One brand per account — same rule admin assign_owner enforces;
            # require_tellus_account's LEFT JOIN tellus_brands assumes it holds.
            already_owns = await conn.fetchval(
                "SELECT 1 FROM tellus_brands WHERE owner_account_id = $1", account.id
            )
            if already_owns:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Your account already owns a brand — one brand per account.",
                )
            try:
                claim_id = await conn.fetchval(
                    "INSERT INTO tellus_brand_claims (brand_id, account_id, claimant_ip) "
                    "VALUES ($1, $2, $3) RETURNING id",
                    brand["id"], account.id, ip,
                )
            except asyncpg.UniqueViolationError:
                # Partial unique index — a pending claim already exists for
                # this brand or this account (concurrent double-submit).
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A claim for this business is already pending review.",
                )
            await record_admin_action(
                conn, account, "brand.claim_requested", "brand", brand["id"],
                {"claim_id": str(claim_id), "ip": ip},
            )
    return TellusClaimResponse(claim_id=claim_id, status="pending", slug=slug)


@router.get("/me/claim", response_model=Optional[TellusMyClaim])
async def my_claim(account: TellusAccount = Depends(require_tellus_account)):
    """Latest non-cancelled claim filed by the caller — drives the "claim
    pending review" state on PublicBrand.tsx. None if the caller has never
    claimed or every claim of theirs was cancelled."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT c.id, c.brand_id, b.slug AS brand_slug, b.name AS brand_name,
                      c.status, c.created_at, c.decision_note
               FROM tellus_brand_claims c
               JOIN tellus_brands b ON b.id = c.brand_id
               WHERE c.account_id = $1 AND c.status <> 'cancelled'
               ORDER BY c.created_at DESC LIMIT 1""",
            account.id,
        )
    return None if row is None else TellusMyClaim(**dict(row))


@router.post("/me/claim/cancel")
async def cancel_my_claim(account: TellusAccount = Depends(require_tellus_account)):
    """Self-serve undo. A pending claim just cancels. An approved-but-unpaid
    claim (plan_status still 'pending' — the caller never finished checkout)
    reverses ownership the same way admin unassign_owner does, since nothing
    external (billing, other users) depends on it yet. An approved+paid claim
    requires support — reversing it here would strand an active subscription.
    """
    async with get_connection() as conn:
        async with conn.transaction():
            claim = await conn.fetchrow(
                """SELECT c.id, c.brand_id, c.status, b.plan_status
                   FROM tellus_brand_claims c JOIN tellus_brands b ON b.id = c.brand_id
                   WHERE c.account_id = $1 AND c.status IN ('pending', 'approved')
                   ORDER BY c.created_at DESC LIMIT 1 FOR UPDATE OF c""",
                account.id,
            )
            if claim is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "No active claim to cancel.")

            if claim["status"] == "pending":
                await conn.execute(
                    "UPDATE tellus_brand_claims SET status = 'cancelled', decided_at = NOW() WHERE id = $1",
                    claim["id"],
                )
                await record_admin_action(
                    conn, account, "brand.claim_cancelled", "brand", claim["brand_id"],
                    {"claim_id": str(claim["id"]), "reason": "self-cancel pending"},
                )
                return {"ok": True}

            # status == 'approved'
            if claim["plan_status"] != "pending":
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "This business is already on a paid plan — contact support to release the claim.",
                )
            await conn.execute(
                "UPDATE tellus_brands SET owner_account_id = NULL, claimed_at = NULL, updated_at = NOW() "
                "WHERE id = $1",
                claim["brand_id"],
            )
            await conn.execute(
                "DELETE FROM tellus_brand_members WHERE brand_id = $1 AND role = 'owner'", claim["brand_id"],
            )
            still_owns = await conn.fetchval(
                "SELECT 1 FROM tellus_brands WHERE owner_account_id = $1", account.id
            )
            if account.account_type == "brand" and not still_owns:
                await conn.execute(
                    "UPDATE tellus_accounts SET account_type = 'consumer', updated_at = NOW() WHERE id = $1",
                    account.id,
                )
            await ensure_community_link(conn, claim["brand_id"], actor_ip=None, detail="claim self-cancel")
            await conn.execute(
                "UPDATE tellus_brand_claims SET status = 'cancelled', decided_at = NOW() WHERE id = $1",
                claim["id"],
            )
            await record_admin_action(
                conn, account, "brand.claim_cancelled", "brand", claim["brand_id"],
                {"claim_id": str(claim["id"]), "reason": "self-cancel approved-unpaid"},
            )
    return {"ok": True}

"""Tell-Us public brand community page — unauthenticated, one brand's
published reviews at /tellus/b/{slug}. Mirrors public_intake.py's hygiene
(rate limit, no auth) since this is the other unauthenticated surface in the
app.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ...core.services.redis_cache import check_rate_limit, client_ip
from ...database import get_connection
from ..dependencies import require_tellus_account
from ..models.tellus import TellusAccount, TellusClaimResponse, TellusPublicBrandPage, TellusPublicReview, TellusReportMedia
from ._shared import _answer_rows_to_models, _media_url

router = APIRouter()


@router.get("/b/{slug}", response_model=TellusPublicBrandPage)
async def public_brand_page(
    slug: str, request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
):
    await check_rate_limit(client_ip(request), "tellus_public_brand", 120, 3600)

    async with get_connection() as conn:
        brand = await conn.fetchrow(
            "SELECT id, name, slug, logo_url, owner_account_id FROM tellus_brands WHERE slug = $1", slug
        )
        if brand is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")

        claimed = brand["owner_account_id"] is not None
        intake_token = None
        if not claimed:
            intake_token = await conn.fetchval(
                "SELECT token FROM tellus_links WHERE brand_id = $1 AND is_active ORDER BY created_at LIMIT 1",
                brand["id"],
            )

        # Published = held + past its 48h hold + still visible. Hits
        # ix_tellus_reports_public. Strict equality to 'visible' (not just
        # <> 'removed') means a 'flagged' review also drops off the public
        # page while triage is pending, not just a fully 'removed' one.
        agg = await conn.fetchrow(
            """SELECT COUNT(*) AS review_count, AVG(rating) AS avg_rating
               FROM tellus_reports
               WHERE brand_id = $1 AND review_state = 'held' AND publish_at <= NOW()
                 AND moderation_status = 'visible'""",
            brand["id"],
        )

        rows = await conn.fetch(
            """SELECT r.*, a.display_name, s.name AS store_name
               FROM tellus_reports r
               LEFT JOIN tellus_accounts a ON a.id = r.reporter_account_id
               LEFT JOIN tellus_stores s ON s.id = r.store_id
               WHERE r.brand_id = $1 AND r.review_state = 'held' AND r.publish_at <= NOW()
                 AND r.moderation_status = 'visible'
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
            )
            for r in rows
        ]

    return TellusPublicBrandPage(
        brand_name=brand["name"],
        slug=brand["slug"],
        logo_url=brand["logo_url"],
        review_count=agg["review_count"] or 0,
        avg_rating=round(agg["avg_rating"], 2) if agg["avg_rating"] is not None else None,
        reviews=reviews,
        total=agg["review_count"] or 0,
        claimed=claimed,
        intake_token=intake_token,
    )


@router.post("/b/{slug}/claim", response_model=TellusClaimResponse)
async def claim_brand(
    slug: str, request: Request, account: TellusAccount = Depends(require_tellus_account),
):
    """'Is this your business?' self-serve claim. Mirrors admin
    assign_owner (routes/admin/brands.py) minus the admin gate/audit:
    ownership link only — plan_status stays 'pending' (column default), so
    every brand-dashboard surface keeps 402ing (require_paid_brand) until
    the caller completes the standard billing checkout. Payment is the
    verification bar here, not identity proof; admin unassign_owner is the
    recourse for a bad-faith claim.
    """
    await check_rate_limit(client_ip(request), "tellus_brand_claim", 5, 3600)

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
            if account.account_type == "consumer":
                await conn.execute(
                    "UPDATE tellus_accounts SET account_type = 'brand', updated_at = NOW() WHERE id = $1",
                    account.id,
                )
            await conn.execute(
                "UPDATE tellus_brands SET owner_account_id = $1, claimed_at = NOW(), updated_at = NOW() "
                "WHERE id = $2",
                account.id, brand["id"],
            )
    return TellusClaimResponse(brand_id=brand["id"], slug=slug)

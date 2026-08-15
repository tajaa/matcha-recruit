"""Regulars board — mixed-role router (dms.py pattern): each endpoint declares
its own dependency; moderator identity is resolved through
tellus_brand_members, not account_type, so a consumer moderator (added via
POST /board/team) works identically to the owning brand account.
"""
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_consumer, require_tellus_account
from ..models.tellus import (
    BoardPostKind,
    BoardReplyStatus,
    TellusAccount,
    TellusBoardJoin,
    TellusBoardJoinRequest,
    TellusBoardManageReplyRow,
    TellusBoardManageSummary,
    TellusBoardMemberEntry,
    TellusBoardMembership,
    TellusBoardPage,
    TellusBoardPost,
    TellusBoardPostCreate,
    TellusBoardPostUpdate,
    TellusBoardReply,
    TellusBoardReplyCreate,
    TellusBoardUpdate,
    TellusBrandTeamMember,
    TellusListing,
    TellusModeratedBrand,
    TellusTeamMemberAdd,
)
from ..services import board_service as bs
from ..services.access_service import find_brand_access
from ..services.marketplace_service import serialize_listing
from ..services.points_service import notify_account

router = APIRouter()


async def _manage_summary(conn, board: dict, viewer_role: str) -> TellusBoardManageSummary:
    counts = await conn.fetchrow(
        """SELECT
               (SELECT COUNT(*) FROM tellus_board_memberships WHERE board_id = $1 AND status = 'pending') AS pending,
               (SELECT COUNT(*) FROM tellus_board_replies r JOIN tellus_board_posts p ON p.id = r.post_id
                  WHERE p.board_id = $1 AND r.status = 'held') AS held,
               (SELECT COUNT(*) FROM tellus_board_memberships WHERE board_id = $1 AND status = 'approved') AS members""",
        board["id"],
    )
    return TellusBoardManageSummary(
        board_id=board["id"], title=board["title"], description=board["description"],
        is_active=board["is_active"], pending_requests=counts["pending"], held_replies=counts["held"],
        member_count=counts["members"], viewer_role=viewer_role,
    )


# ── Consumer endpoints ──────────────────────────────────────────────────────

@router.post("/b/{slug}/board/join", response_model=TellusBoardMembership, status_code=status.HTTP_201_CREATED)
async def request_join(
    slug: str, body: Optional[TellusBoardJoin] = None, account: TellusAccount = Depends(require_consumer),
):
    await check_rate_limit(str(account.id), "tellus_board_join", 10, 3600)
    note = body.note if body is not None else None

    async with get_connection() as conn:
        async with conn.transaction():
            brand = await conn.fetchrow(
                "SELECT id, name, slug, logo_url, owner_account_id, plan_status FROM tellus_brands WHERE slug = $1",
                slug,
            )
            if brand is None or brand["owner_account_id"] is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
            if brand["plan_status"] != "active":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=bs.BOARD_PAUSED_DETAIL)

            board = await bs.ensure_board(conn, brand["id"])
            if not board["is_active"]:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=bs.BOARD_PAUSED_DETAIL)

            # Pre-check under the open txn so the common case never touches
            # UniqueViolationError; the except below is a race fallback only,
            # and it must never run another query on the aborted outer txn
            # (savepoint-abort trap — see tellus/CLAUDE.md's ledger-idempotency
            # note). The INSERT itself is wrapped in its own SAVEPOINT so a
            # concurrent duplicate can raise, get caught, and the outer txn
            # (which still needs to notify the team) survives.
            #
            # Looks at the LATEST row of any status, not just pending/approved —
            # a brand's decline/removal must stick (no infinite re-request
            # spamming the moderator team on every retry); left/cancelled were
            # the account's own choice, so those fall through to a fresh INSERT.
            existing = await conn.fetchval(
                "SELECT status FROM tellus_board_memberships WHERE board_id = $1 AND account_id = $2 "
                "ORDER BY requested_at DESC LIMIT 1",
                board["id"], account.id,
            )
            if existing in ("pending", "approved"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Already a member" if existing == "approved" else "Request already pending",
                )
            if existing in ("declined", "removed"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The brand has declined this request.",
                )

            # One membership slot spans all boards. Serialize joins per account
            # so concurrent requests cannot both pass the count check.
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1::text, 0))",
                str(account.id),
            )
            active_count = await conn.fetchval(
                "SELECT count(*) FROM tellus_board_memberships "
                "WHERE account_id = $1 AND status IN ('pending', 'approved')",
                account.id,
            )
            limit = bs.board_membership_limit(account)
            if active_count >= limit:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"You're already on {limit} boards — leave one to join another.",
                )

            try:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        """INSERT INTO tellus_board_memberships (board_id, account_id, note)
                               VALUES ($1, $2, $3) RETURNING *""",
                        board["id"], account.id, note,
                    )
            except asyncpg.UniqueViolationError:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request already pending")

            await bs.notify_board_team(
                conn, brand["id"], "board_join_request", "New board join request",
                f"{account.display_name or 'A member'} requested to join your regulars board.",
                reference_type="board_membership", reference_id=str(row["id"]),
            )

    return TellusBoardMembership(
        id=row["id"], brand_id=brand["id"], brand_name=brand["name"], brand_slug=brand["slug"],
        logo_url=brand["logo_url"], status=row["status"], requested_at=row["requested_at"],
        decided_at=row["decided_at"],
    )


@router.get("/me/moderated-brands", response_model=list[TellusModeratedBrand])
async def my_moderated_brands(account: TellusAccount = Depends(require_tellus_account)):
    """Every brand this account can moderate — the bootstrap list a consumer
    moderator's client needs before it can call anything under /board/manage,
    since GET /board/manage itself 400s 'Specify brand_id' with 2+ boards."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT b.id AS brand_id, b.name, b.slug, bm.role
               FROM tellus_brand_members bm JOIN tellus_brands b ON b.id = bm.brand_id
               WHERE bm.account_id = $1
               ORDER BY bm.created_at ASC""",
            account.id,
        )
    return [TellusModeratedBrand(**dict(r)) for r in rows]


@router.get("/me/board-memberships", response_model=list[TellusBoardMembership])
async def my_memberships(account: TellusAccount = Depends(require_consumer)):
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT m.id, b.id AS brand_id, b.name AS brand_name, b.slug AS brand_slug, b.logo_url,
                      m.status, m.requested_at, m.decided_at
               FROM tellus_board_memberships m
               JOIN tellus_boards bo ON bo.id = m.board_id
               JOIN tellus_brands b ON b.id = bo.brand_id
               WHERE m.account_id = $1
               ORDER BY m.requested_at DESC""",
            account.id,
        )
    return [TellusBoardMembership(**dict(r)) for r in rows]


@router.post("/me/board-memberships/{membership_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_membership(membership_id: UUID, account: TellusAccount = Depends(require_consumer)):
    async with get_connection() as conn:
        result = await conn.execute(
            """UPDATE tellus_board_memberships
               SET status = CASE status WHEN 'pending' THEN 'cancelled' WHEN 'approved' THEN 'left' END,
                   decided_at = NOW()
               WHERE id = $1 AND account_id = $2 AND status IN ('pending', 'approved')""",
            membership_id, account.id,
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")


@router.get("/boards/{slug}", response_model=TellusBoardPage)
async def get_board(
    slug: str, kind: Optional[BoardPostKind] = None,
    limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0),
    account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        brand = await conn.fetchrow(
            "SELECT id, name, slug, logo_url, plan_status FROM tellus_brands WHERE slug = $1",
            slug,
        )
        if brand is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")

        board = await conn.fetchrow("SELECT * FROM tellus_boards WHERE brand_id = $1", brand["id"])
        access = await find_brand_access(conn, account.id, brand["id"])
        viewer_is_mod = access is not None and "board.manage" in access.capabilities
        viewer_role = access.role if viewer_is_mod else None

        if not viewer_is_mod:
            if board is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This brand has no board yet.")
            membership = await bs.get_approved_membership(conn, board["id"], account.id)
            if membership is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Request to join this board from the brand page",
                )
            viewer_role = "member"
        elif board is None:
            board = await bs.ensure_board(conn, brand["id"])

        where = "WHERE p.board_id = $1"
        params: list = [board["id"]]
        if not viewer_is_mod:
            where += " AND p.moderation_status = 'visible'"
        if kind is not None:
            params.append(kind)
            where += f" AND p.kind = ${len(params)}"

        # total's COUNT(*) must NOT see the account_id param appended below —
        # slice params back to the where-clause-only prefix for that query.
        n_where_params = len(params)
        params.append(account.id)
        viewer_idx = len(params)

        rows = await conn.fetch(
            f"""SELECT p.*,
                       (SELECT COUNT(*) FROM tellus_board_replies rr
                          WHERE rr.post_id = p.id AND rr.status = 'approved') AS approved_reply_count,
                       (SELECT COUNT(*) FROM tellus_board_replies rr
                          WHERE rr.post_id = p.id AND rr.status = 'held') AS held_reply_count,
                       (SELECT COUNT(*)::int FROM tellus_likes lk WHERE lk.post_id = p.id) AS like_count,
                       EXISTS (
                           SELECT 1 FROM tellus_likes lk
                           WHERE lk.post_id = p.id AND lk.account_id = ${viewer_idx}
                       ) AS liked_by_me
                FROM tellus_board_posts p
                {where}
                ORDER BY p.is_pinned DESC, p.created_at DESC
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}""",
            *params, limit, offset,
        )
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM tellus_board_posts p {where}", *params[:n_where_params],
        )

        listing_ids = [r["listing_id"] for r in rows if r["listing_id"] is not None]
        listings_by_id = {}
        if listing_ids:
            lrows = await conn.fetch(
                "SELECT l.*, b.name AS brand_name, "
                "  (SELECT COUNT(*)::int FROM tellus_likes lk WHERE lk.listing_id = l.id) AS like_count, "
                "  EXISTS (SELECT 1 FROM tellus_likes lk WHERE lk.listing_id = l.id AND lk.account_id = $3) AS liked_by_me "
                "FROM tellus_reward_listings l "
                "LEFT JOIN tellus_brands b ON b.id = l.brand_id "
                "WHERE l.id = ANY($1::uuid[]) AND l.brand_id = $2",
                listing_ids, brand["id"], account.id,
            )
            listings_by_id = {r["id"]: r for r in lrows}

        posts = [
            bs.serialize_post(r, viewer_is_mod=viewer_is_mod, listing_row=listings_by_id.get(r["listing_id"]))
            for r in rows
        ]

    return TellusBoardPage(
        board_id=board["id"], brand_id=brand["id"], brand_name=brand["name"],
        brand_slug=brand["slug"], logo_url=brand["logo_url"],
        title=board["title"], description=board["description"], is_active=board["is_active"],
        plan_paused=brand["plan_status"] != "active",
        viewer_role=viewer_role, can_manage_board=viewer_is_mod, posts=posts, total=total,
    )


@router.get("/boards/{slug}/posts/{post_id}/replies", response_model=list[TellusBoardReply])
async def list_replies(slug: str, post_id: UUID, account: TellusAccount = Depends(require_tellus_account)):
    async with get_connection() as conn:
        brand = await conn.fetchrow("SELECT id FROM tellus_brands WHERE slug = $1", slug)
        if brand is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
        access = await find_brand_access(conn, account.id, brand["id"])
        viewer_is_mod = access is not None and "board.manage" in access.capabilities

        post = await conn.fetchrow(
            "SELECT p.id, p.board_id FROM tellus_board_posts p JOIN tellus_boards bo ON bo.id = p.board_id "
            "WHERE p.id = $1 AND bo.brand_id = $2" + ("" if viewer_is_mod else " AND p.moderation_status = 'visible'"),
            post_id, brand["id"],
        )
        if post is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

        if not viewer_is_mod:
            membership = await bs.get_approved_membership(conn, post["board_id"], account.id)
            if membership is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a board member")

        # SQL prefilter narrows the round trip; bs.reply_visible_to is THE
        # predicate — the belt-and-braces filter below is what actually decides.
        rows = await conn.fetch(
            """SELECT r.*, a.display_name AS author_display_name,
                      (SELECT COUNT(*)::int FROM tellus_likes lk WHERE lk.reply_id = r.id) AS like_count,
                      EXISTS (
                          SELECT 1 FROM tellus_likes lk WHERE lk.reply_id = r.id AND lk.account_id = $2
                      ) AS liked_by_me
               FROM tellus_board_replies r JOIN tellus_accounts a ON a.id = r.author_account_id
               WHERE r.post_id = $1 AND (r.status = 'approved' OR r.author_account_id = $2 OR $3)
               ORDER BY r.created_at ASC LIMIT 200""",
            post_id, account.id, viewer_is_mod,
        )
    return [
        bs.serialize_reply(r, viewer_id=account.id)
        for r in rows
        if bs.reply_visible_to(r["status"], r["author_account_id"], account.id, viewer_is_mod)
    ]


@router.post(
    "/boards/{slug}/posts/{post_id}/replies", response_model=TellusBoardReply, status_code=status.HTTP_201_CREATED,
)
async def create_reply(
    slug: str, post_id: UUID, body: TellusBoardReplyCreate, account: TellusAccount = Depends(require_tellus_account),
):
    await check_rate_limit(str(account.id), "tellus_board_reply_burst", 5, 60)
    await check_rate_limit(str(account.id), "tellus_board_reply", 30, 3600)

    async with get_connection() as conn:
        async with conn.transaction():
            brand = await conn.fetchrow("SELECT id, name, plan_status FROM tellus_brands WHERE slug = $1", slug)
            if brand is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
            board = await conn.fetchrow("SELECT id, is_active FROM tellus_boards WHERE brand_id = $1", brand["id"])
            if board is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

            # Brand team members and owners reply as the brand — auto-approved,
            # no moderation. Consumer members go through the held→approve flow.
            access = await find_brand_access(conn, account.id, brand["id"])
            is_privileged = access is not None and "board.manage" in access.capabilities
            if not is_privileged:
                membership = await bs.get_approved_membership(conn, board["id"], account.id)
                if membership is None:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a board member")
                if brand["plan_status"] != "active" or not board["is_active"]:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=bs.BOARD_PAUSED_DETAIL)
            else:
                if brand["plan_status"] != "active":
                    raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="This brand account does not have an active subscription.")

            post = await conn.fetchrow(
                "SELECT id FROM tellus_board_posts WHERE id = $1 AND board_id = $2"
                + ("" if is_privileged else " AND moderation_status = 'visible'"),
                post_id, board["id"],
            )
            if post is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

            reply_status = "approved" if is_privileged else "held"
            row = await conn.fetchrow(
                """INSERT INTO tellus_board_replies (post_id, author_account_id, body, status)
                       VALUES ($1, $2, $3, $4) RETURNING *""",
                post_id, account.id, body.body, reply_status,
            )

            if not is_privileged:
                await bs.notify_board_team(
                    conn, brand["id"], "board_reply_pending", "New reply awaiting approval",
                    f"{account.display_name or 'A member'} replied to a board post.",
                    reference_type="board_post", reference_id=str(post_id),
                    slug=slug, name=brand["name"],
                )

    return TellusBoardReply(
        id=row["id"], post_id=row["post_id"], author_name=account.display_name or "Tell-Us member",
        is_mine=True, status=row["status"], body=row["body"], created_at=row["created_at"],
    )


@router.delete("/boards/{slug}/replies/{reply_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_own_reply(slug: str, reply_id: UUID, account: TellusAccount = Depends(require_consumer)):
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM tellus_board_replies WHERE id = $1 AND author_account_id = $2 AND status = 'held'",
            reply_id, account.id,
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reply not found")


# ── Brand/moderator endpoints ────────────────────────────────────────────────
# All resolve via bs.resolve_moderated_brand — brand_id disambiguates a
# consumer who moderates more than one board; mutations gate on
# bs.require_active_plan, reads don't (a lapsed plan stays read-only, not dark).

@router.get("/board/manage", response_model=TellusBoardManageSummary)
async def get_board_manage(
    brand_id: Optional[UUID] = Query(None), account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        brand, role = await bs.resolve_moderated_brand(conn, account, brand_id)
        board = await bs.ensure_board(conn, brand["id"])
        return await _manage_summary(conn, board, role)


@router.patch("/board/manage", response_model=TellusBoardManageSummary)
async def update_board_manage(
    body: TellusBoardUpdate, brand_id: Optional[UUID] = Query(None),
    account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        brand, role = await bs.resolve_moderated_brand(conn, account, brand_id)
        bs.require_active_plan(brand)
        board = await bs.ensure_board(conn, brand["id"])

        # model_fields_set (not COALESCE) so an explicit null in the request
        # body clears the column instead of being indistinguishable from an
        # omitted field — title/description are nullable text; is_active is
        # a bool NOT NULL, so a null there stays a no-op.
        sets, args = ["updated_at = NOW()"], [board["id"]]
        for field in ("title", "description", "is_active"):
            if field not in body.model_fields_set:
                continue
            value = getattr(body, field)
            if field == "is_active" and value is None:
                continue
            args.append(value)
            sets.append(f"{field} = ${len(args)}")
        row = await conn.fetchrow(
            f"UPDATE tellus_boards SET {', '.join(sets)} WHERE id = $1 RETURNING *", *args,
        )
        return await _manage_summary(conn, row, role)


@router.get("/board/manage/requests", response_model=list[TellusBoardJoinRequest])
async def list_join_requests(
    brand_id: Optional[UUID] = Query(None), account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        brand, _role = await bs.resolve_moderated_brand(conn, account, brand_id)
        board = await bs.ensure_board(conn, brand["id"])
        rows = await conn.fetch(
            """SELECT m.id, m.account_id, a.display_name AS account_display_name, m.note, m.requested_at
               FROM tellus_board_memberships m JOIN tellus_accounts a ON a.id = m.account_id
               WHERE m.board_id = $1 AND m.status = 'pending'
               ORDER BY m.requested_at ASC""",
            board["id"],
        )
        signals = await bs.loyalty_signals(conn, brand["id"], [r["account_id"] for r in rows])
    return [
        TellusBoardJoinRequest(
            id=r["id"], account_display_name=r["account_display_name"] or "Tell-Us member",
            note=r["note"], requested_at=r["requested_at"],
            review_count=signals[r["account_id"]]["review_count"],
            hearted=signals[r["account_id"]]["hearted"],
            redemption_count=signals[r["account_id"]]["redemption_count"],
        )
        for r in rows
    ]


@router.post("/board/manage/requests/{membership_id}/approve", status_code=status.HTTP_204_NO_CONTENT)
async def approve_join_request(
    membership_id: UUID, brand_id: Optional[UUID] = Query(None),
    account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        brand, _role = await bs.resolve_moderated_brand(conn, account, brand_id)
        bs.require_active_plan(brand)
        board = await bs.ensure_board(conn, brand["id"])
        async with conn.transaction():
            try:
                row = await conn.fetchrow(
                    """UPDATE tellus_board_memberships SET status = 'approved', decided_at = NOW(), decided_by = $3
                       WHERE id = $1 AND board_id = $2 AND status = 'pending'
                       RETURNING account_id""",
                    membership_id, board["id"], account.id,
                )
            except asyncpg.UniqueViolationError:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already a member")
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
            await notify_account(
                conn, row["account_id"], "membership_approved", "You're in!",
                f"You were approved to join {brand['name']}'s regulars board.",
                reference_type="board", reference_id=str(board["id"]),
            )


@router.post("/board/manage/requests/{membership_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
async def decline_join_request(
    membership_id: UUID, brand_id: Optional[UUID] = Query(None),
    account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        brand, _role = await bs.resolve_moderated_brand(conn, account, brand_id)
        bs.require_active_plan(brand)
        board = await bs.ensure_board(conn, brand["id"])
        result = await conn.execute(
            """UPDATE tellus_board_memberships SET status = 'declined', decided_at = NOW(), decided_by = $3
               WHERE id = $1 AND board_id = $2 AND status = 'pending'""",
            membership_id, board["id"], account.id,
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")


@router.get("/board/manage/members", response_model=list[TellusBoardMemberEntry])
async def list_board_members(
    brand_id: Optional[UUID] = Query(None), account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        brand, _role = await bs.resolve_moderated_brand(conn, account, brand_id)
        board = await bs.ensure_board(conn, brand["id"])
        rows = await conn.fetch(
            """SELECT m.id, a.display_name AS account_display_name,
                      COALESCE(m.decided_at, m.requested_at) AS joined_at
               FROM tellus_board_memberships m JOIN tellus_accounts a ON a.id = m.account_id
               WHERE m.board_id = $1 AND m.status = 'approved'
               ORDER BY COALESCE(m.decided_at, m.requested_at) DESC""",
            board["id"],
        )
    return [
        TellusBoardMemberEntry(
            id=r["id"], account_display_name=r["account_display_name"] or "Tell-Us member", joined_at=r["joined_at"],
        )
        for r in rows
    ]


@router.post("/board/manage/members/{membership_id}/remove", status_code=status.HTTP_204_NO_CONTENT)
async def remove_board_member(
    membership_id: UUID, brand_id: Optional[UUID] = Query(None),
    account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        brand, _role = await bs.resolve_moderated_brand(conn, account, brand_id)
        bs.require_active_plan(brand)
        board = await bs.ensure_board(conn, brand["id"])
        result = await conn.execute(
            """UPDATE tellus_board_memberships SET status = 'removed', decided_at = NOW(), decided_by = $3
               WHERE id = $1 AND board_id = $2 AND status = 'approved'""",
            membership_id, board["id"], account.id,
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")


@router.post("/board/posts", response_model=TellusBoardPost, status_code=status.HTTP_201_CREATED)
async def create_post(
    body: TellusBoardPostCreate, brand_id: Optional[UUID] = Query(None),
    account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        brand, _role = await bs.resolve_moderated_brand(conn, account, brand_id)
        bs.require_active_plan(brand)
        async with conn.transaction():
            board = await bs.ensure_board(conn, brand["id"])
            if not board["is_active"]:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=bs.BOARD_PAUSED_DETAIL)

            listing_row = None
            if body.kind == "deal":
                listing_row = await conn.fetchrow(
                    "SELECT l.*, b.name AS brand_name FROM tellus_reward_listings l "
                    "LEFT JOIN tellus_brands b ON b.id = l.brand_id "
                    "WHERE l.id = $1 AND l.brand_id = $2",
                    body.listing_id, brand["id"],
                )
                if listing_row is None or listing_row["visibility"] != "board" or not listing_row["is_active"]:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Pick a board-only reward",
                    )

            # Only a validated deal listing may attach — an update/event/question
            # post can't carry an unvalidated (possibly cross-brand) listing_id.
            listing_id = body.listing_id if body.kind == "deal" else None

            row = await conn.fetchrow(
                """INSERT INTO tellus_board_posts
                       (board_id, author_account_id, kind, title, body, listing_id,
                        event_starts_at, event_ends_at, is_pinned)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                   RETURNING *""",
                board["id"], account.id, body.kind, body.title, body.body, listing_id,
                body.event_starts_at, body.event_ends_at, body.is_pinned,
            )
            await bs.notify_board_members(
                conn, board["id"], "board_post", f"{brand['name']}: {row['title']}", body.body,
                reference_type="board_post", reference_id=str(row["id"]),
                exclude_account_id=account.id,
                slug=brand["slug"], name=brand["name"],
            )

    row_dict = {**dict(row), "approved_reply_count": 0, "held_reply_count": 0}
    return bs.serialize_post(row_dict, viewer_is_mod=True, listing_row=listing_row)


@router.patch("/board/posts/{post_id}", response_model=TellusBoardPost)
async def update_post(
    post_id: UUID, body: TellusBoardPostUpdate, brand_id: Optional[UUID] = Query(None),
    account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        brand, _role = await bs.resolve_moderated_brand(conn, account, brand_id)
        bs.require_active_plan(brand)
        board = await bs.ensure_board(conn, brand["id"])
        # model_fields_set (not COALESCE) so an explicit null clears a nullable
        # column (body/event_starts_at/event_ends_at) instead of being
        # indistinguishable from an omitted field — same pattern as
        # update_board_manage above. title/is_pinned are NOT NULL, so an
        # explicit null on either is a no-op, not a clear.
        sets, args = ["updated_at = NOW()"], [post_id, board["id"]]
        for field in ("title", "body", "is_pinned", "event_starts_at", "event_ends_at"):
            if field not in body.model_fields_set:
                continue
            value = getattr(body, field)
            if field in ("title", "is_pinned") and value is None:
                continue
            args.append(value)
            sets.append(f"{field} = ${len(args)}")
        # Ownership fetch scoped to this board — 404 not 403 (get_owned_report pattern).
        row = await conn.fetchrow(
            f"UPDATE tellus_board_posts SET {', '.join(sets)} WHERE id = $1 AND board_id = $2 RETURNING *",
            *args,
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

        counts = await conn.fetchrow(
            """SELECT
                   (SELECT COUNT(*) FROM tellus_board_replies WHERE post_id = $1 AND status = 'approved')
                       AS approved_reply_count,
                   (SELECT COUNT(*) FROM tellus_board_replies WHERE post_id = $1 AND status = 'held')
                       AS held_reply_count,
                   (SELECT COUNT(*)::int FROM tellus_likes WHERE post_id = $1) AS like_count,
                   EXISTS (SELECT 1 FROM tellus_likes WHERE post_id = $1 AND account_id = $2) AS liked_by_me""",
            post_id, account.id,
        )
        listing_row = None
        if row["listing_id"] is not None:
            listing_row = await conn.fetchrow(
                "SELECT l.*, b.name AS brand_name, "
                "  (SELECT COUNT(*)::int FROM tellus_likes lk WHERE lk.listing_id = l.id) AS like_count, "
                "  EXISTS (SELECT 1 FROM tellus_likes lk WHERE lk.listing_id = l.id AND lk.account_id = $3) AS liked_by_me "
                "FROM tellus_reward_listings l "
                "LEFT JOIN tellus_brands b ON b.id = l.brand_id WHERE l.id = $1 AND l.brand_id = $2",
                row["listing_id"], brand["id"], account.id,
            )

    row_dict = {**dict(row), **dict(counts)}
    return bs.serialize_post(row_dict, viewer_is_mod=True, listing_row=listing_row)


@router.delete("/board/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: UUID, brand_id: Optional[UUID] = Query(None), account: TellusAccount = Depends(require_tellus_account),
):
    """Soft delete — keeps reply context + admin auditability."""
    async with get_connection() as conn:
        brand, _role = await bs.resolve_moderated_brand(conn, account, brand_id)
        bs.require_active_plan(brand)
        board = await bs.ensure_board(conn, brand["id"])
        result = await conn.execute(
            "UPDATE tellus_board_posts SET moderation_status = 'removed', updated_at = NOW() "
            "WHERE id = $1 AND board_id = $2",
            post_id, board["id"],
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")


@router.get("/board/manage/replies", response_model=list[TellusBoardManageReplyRow])
async def list_manage_replies(
    reply_status: BoardReplyStatus = Query("held", alias="status"), brand_id: Optional[UUID] = Query(None),
    account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        brand, _role = await bs.resolve_moderated_brand(conn, account, brand_id)
        board = await bs.ensure_board(conn, brand["id"])
        rows = await conn.fetch(
            """SELECT r.id, r.post_id, p.title AS post_title, r.body, r.status, r.created_at,
                      a.display_name AS author_display_name
               FROM tellus_board_replies r
               JOIN tellus_board_posts p ON p.id = r.post_id
               JOIN tellus_accounts a ON a.id = r.author_account_id
               WHERE p.board_id = $1 AND r.status = $2
               ORDER BY r.created_at ASC""",
            board["id"], reply_status,
        )
    return [
        TellusBoardManageReplyRow(
            id=r["id"], post_id=r["post_id"], post_title=r["post_title"],
            author_name=r["author_display_name"] or "Tell-Us member",
            body=r["body"], status=r["status"], created_at=r["created_at"],
        )
        for r in rows
    ]


@router.post("/board/replies/{reply_id}/approve", status_code=status.HTTP_204_NO_CONTENT)
async def approve_reply(
    reply_id: UUID, brand_id: Optional[UUID] = Query(None), account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        brand, _role = await bs.resolve_moderated_brand(conn, account, brand_id)
        bs.require_active_plan(brand)
        board = await bs.ensure_board(conn, brand["id"])
        async with conn.transaction():
            cur = await conn.fetchval(
                """SELECT r.status FROM tellus_board_replies r
                   WHERE r.id = $1 AND r.post_id IN (SELECT id FROM tellus_board_posts WHERE board_id = $2)""",
                reply_id, board["id"],
            )
            if cur is None or not bs.can_reply_transition(cur, "approved"):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reply not found or already moderated")
            result = await bs.approve_reply_and_award(conn, reply_id, account.id, board_id=board["id"])
        if result is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reply not found or already moderated")


@router.post("/board/replies/{reply_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
async def reject_reply(
    reply_id: UUID, brand_id: Optional[UUID] = Query(None), account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        brand, _role = await bs.resolve_moderated_brand(conn, account, brand_id)
        bs.require_active_plan(brand)
        board = await bs.ensure_board(conn, brand["id"])
        cur = await conn.fetchval(
            """SELECT r.status FROM tellus_board_replies r
               WHERE r.id = $1 AND r.post_id IN (SELECT id FROM tellus_board_posts WHERE board_id = $2)""",
            reply_id, board["id"],
        )
        if cur is None or not bs.can_reply_transition(cur, "rejected"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reply not found or already moderated")
        result = await conn.execute(
            """UPDATE tellus_board_replies SET status = 'rejected', moderated_at = NOW(), moderated_by = $2
               WHERE id = $1 AND status = 'held'
                 AND post_id IN (SELECT id FROM tellus_board_posts WHERE board_id = $3)""",
            reply_id, account.id, board["id"],
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reply not found or already moderated")


@router.post("/board/replies/{reply_id}/remove", status_code=status.HTTP_204_NO_CONTENT)
async def remove_reply(
    reply_id: UUID, brand_id: Optional[UUID] = Query(None), account: TellusAccount = Depends(require_tellus_account),
):
    """approved→removed. No clawback — the points were earned for a reply
    that was legitimately approved at the time; removal is moderation of
    ongoing visibility, not a retroactive verdict."""
    async with get_connection() as conn:
        brand, _role = await bs.resolve_moderated_brand(conn, account, brand_id)
        bs.require_active_plan(brand)
        board = await bs.ensure_board(conn, brand["id"])
        cur = await conn.fetchval(
            """SELECT r.status FROM tellus_board_replies r
               WHERE r.id = $1 AND r.post_id IN (SELECT id FROM tellus_board_posts WHERE board_id = $2)""",
            reply_id, board["id"],
        )
        if cur is None or not bs.can_reply_transition(cur, "removed"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reply not found or already moderated")
        result = await conn.execute(
            """UPDATE tellus_board_replies SET status = 'removed', moderated_at = NOW(), moderated_by = $2
               WHERE id = $1 AND status = 'approved'
                 AND post_id IN (SELECT id FROM tellus_board_posts WHERE board_id = $3)""",
            reply_id, account.id, board["id"],
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reply not found or already moderated")


@router.get("/board/team", response_model=list[TellusBrandTeamMember])
async def list_team(
    brand_id: Optional[UUID] = Query(None), account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        brand, _role = await bs.resolve_moderated_brand(conn, account, brand_id)
        rows = await conn.fetch(
            """SELECT m.id, a.display_name AS account_display_name, a.email, m.role, m.created_at, m.can_manage_inbox
               FROM tellus_brand_members m JOIN tellus_accounts a ON a.id = m.account_id
               WHERE m.brand_id = $1 ORDER BY (m.role = 'owner') DESC, m.created_at ASC""",
            brand["id"],
        )
    return [
        TellusBrandTeamMember(
            id=r["id"], account_display_name=r["account_display_name"] or "Tell-Us member",
            email=r["email"], role=r["role"], created_at=r["created_at"], can_manage_inbox=bool(r["can_manage_inbox"]),
        )
        for r in rows
    ]


@router.get("/board/manage/listings", response_model=list[TellusListing])
async def list_board_listings(
    brand_id: Optional[UUID] = Query(None), account: TellusAccount = Depends(require_tellus_account),
):
    """Board-only rewards for the deal-post composer. Gated by
    resolve_moderated_brand (not require_paid_brand — GET /listings) so a
    consumer-typed team moderator (POST /board/team) can compose a deal post
    without hitting a 403 from an endpoint scoped to real brand accounts."""
    async with get_connection() as conn:
        brand, _role = await bs.resolve_moderated_brand(conn, account, brand_id)
        rows = await conn.fetch(
            """SELECT l.*, b.name AS brand_name FROM tellus_reward_listings l
               LEFT JOIN tellus_brands b ON b.id = l.brand_id
               WHERE l.brand_id = $1 AND l.visibility = 'board' AND l.is_active
               ORDER BY l.created_at DESC""",
            brand["id"],
        )
    return [serialize_listing(r) for r in rows]


@router.post("/board/team", response_model=TellusBrandTeamMember, status_code=status.HTTP_201_CREATED)
async def add_team_member(
    body: TellusTeamMemberAdd, brand_id: Optional[UUID] = Query(None),
    account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        brand, my_role = await bs.resolve_moderated_brand(conn, account, brand_id)
        if my_role != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Only the brand owner can manage the team.",
            )
        bs.require_active_plan(brand)

        # Target must already have a Tell-Us account — they sign up first,
        # then get added, mirroring how every other Tell-Us identity works.
        target = await conn.fetchrow(
            "SELECT id, email, display_name FROM tellus_accounts WHERE lower(email) = lower($1) AND status = 'active'",
            body.email,
        )
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No Tell-Us account with that email")

        try:
            row = await conn.fetchrow(
                """INSERT INTO tellus_brand_members
                           (brand_id, account_id, role, all_stores, added_by)
                       VALUES ($1, $2, 'staff', TRUE, $3) RETURNING *""",
                brand["id"], target["id"], account.id,
            )
            await conn.execute(
                """INSERT INTO tellus_brand_member_capabilities (member_id, capability, effect)
                   VALUES ($1, 'board.manage', 'grant')
                   ON CONFLICT (member_id, capability) DO UPDATE SET effect = 'grant'""",
                row["id"],
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already on the team")

        await notify_account(
            conn, target["id"], "board_team_added", "You're a board moderator",
            f"You were added to {brand['name']}'s regulars board team.",
            reference_type="brand", reference_id=str(brand["id"]),
        )

    return TellusBrandTeamMember(
        id=row["id"], account_display_name=target["display_name"] or "Tell-Us member",
        email=target["email"], role=row["role"], created_at=row["created_at"], can_manage_inbox=bool(row["can_manage_inbox"]),
    )


@router.delete("/board/team/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    member_id: UUID, brand_id: Optional[UUID] = Query(None), account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        brand, my_role = await bs.resolve_moderated_brand(conn, account, brand_id)
        if my_role != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Only the brand owner can manage the team.",
            )
        bs.require_active_plan(brand)
        result = await conn.execute(
            "DELETE FROM tellus_brand_members WHERE id = $1 AND brand_id = $2 AND role <> 'owner'",
            member_id, brand["id"],
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team member not found")

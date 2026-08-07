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
    TellusAccount,
    TellusBoardJoin,
    TellusBoardJoinRequest,
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
    TellusTeamMemberAdd,
)
from ..services import board_service as bs
from ..services.points_service import notify_account

router = APIRouter()


async def _manage_summary(conn, board: dict) -> TellusBoardManageSummary:
    pending = await conn.fetchval(
        "SELECT COUNT(*) FROM tellus_board_memberships WHERE board_id = $1 AND status = 'pending'",
        board["id"],
    )
    held = await conn.fetchval(
        "SELECT COUNT(*) FROM tellus_board_replies r JOIN tellus_board_posts p ON p.id = r.post_id "
        "WHERE p.board_id = $1 AND r.status = 'held'",
        board["id"],
    )
    members = await conn.fetchval(
        "SELECT COUNT(*) FROM tellus_board_memberships WHERE board_id = $1 AND status = 'approved'",
        board["id"],
    )
    return TellusBoardManageSummary(
        board_id=board["id"], title=board["title"], description=board["description"],
        is_active=board["is_active"], pending_requests=pending, held_replies=held, member_count=members,
    )


# ── Consumer endpoints ──────────────────────────────────────────────────────

@router.post("/b/{slug}/board/join", response_model=TellusBoardMembership, status_code=status.HTTP_201_CREATED)
async def request_join(slug: str, body: TellusBoardJoin, account: TellusAccount = Depends(require_consumer)):
    await check_rate_limit(str(account.id), "tellus_board_join", 10, 3600)

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

            try:
                row = await conn.fetchrow(
                    """INSERT INTO tellus_board_memberships (board_id, account_id, note)
                           VALUES ($1, $2, $3) RETURNING *""",
                    board["id"], account.id, body.note,
                )
            except asyncpg.UniqueViolationError:
                existing = await conn.fetchval(
                    "SELECT status FROM tellus_board_memberships WHERE board_id = $1 AND account_id = $2 "
                    "AND status IN ('pending', 'approved') ORDER BY requested_at DESC LIMIT 1",
                    board["id"], account.id,
                )
                detail = "Already a member" if existing == "approved" else "Request already pending"
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

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
    limit: int = Query(20, le=50), offset: int = 0,
    account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        brand = await conn.fetchrow(
            "SELECT id, name, slug, logo_url, plan_status FROM tellus_brands WHERE slug = $1", slug,
        )
        if brand is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")

        board = await conn.fetchrow("SELECT * FROM tellus_boards WHERE brand_id = $1", brand["id"])
        member_row = await conn.fetchrow(
            "SELECT role FROM tellus_brand_members WHERE brand_id = $1 AND account_id = $2",
            brand["id"], account.id,
        )
        viewer_is_mod = member_row is not None
        viewer_role = member_row["role"] if member_row is not None else None

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

        rows = await conn.fetch(
            f"""SELECT p.*,
                       (SELECT COUNT(*) FROM tellus_board_replies rr
                          WHERE rr.post_id = p.id AND rr.status = 'approved') AS approved_reply_count,
                       (SELECT COUNT(*) FROM tellus_board_replies rr
                          WHERE rr.post_id = p.id AND rr.status = 'held') AS held_reply_count
                FROM tellus_board_posts p
                {where}
                ORDER BY p.is_pinned DESC, p.created_at DESC
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}""",
            *params, limit, offset,
        )
        total = await conn.fetchval(f"SELECT COUNT(*) FROM tellus_board_posts p {where}", *params)

        listing_ids = [r["listing_id"] for r in rows if r["listing_id"] is not None]
        listings_by_id = {}
        if listing_ids:
            lrows = await conn.fetch(
                "SELECT l.*, b.name AS brand_name FROM tellus_reward_listings l "
                "LEFT JOIN tellus_brands b ON b.id = l.brand_id WHERE l.id = ANY($1::uuid[])",
                listing_ids,
            )
            listings_by_id = {r["id"]: r for r in lrows}

        posts = [
            bs.serialize_post(r, viewer_is_mod=viewer_is_mod, listing_row=listings_by_id.get(r["listing_id"]))
            for r in rows
        ]

    return TellusBoardPage(
        board_id=board["id"], brand_name=brand["name"], brand_slug=brand["slug"], logo_url=brand["logo_url"],
        title=board["title"], description=board["description"], is_active=board["is_active"],
        plan_paused=brand["plan_status"] != "active",
        viewer_role=viewer_role, posts=posts, total=total,
    )


@router.get("/boards/{slug}/posts/{post_id}/replies", response_model=list[TellusBoardReply])
async def list_replies(slug: str, post_id: UUID, account: TellusAccount = Depends(require_tellus_account)):
    async with get_connection() as conn:
        brand = await conn.fetchrow("SELECT id FROM tellus_brands WHERE slug = $1", slug)
        if brand is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
        post = await conn.fetchrow(
            "SELECT p.id, p.board_id FROM tellus_board_posts p JOIN tellus_boards bo ON bo.id = p.board_id "
            "WHERE p.id = $1 AND bo.brand_id = $2",
            post_id, brand["id"],
        )
        if post is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

        member_row = await conn.fetchrow(
            "SELECT 1 FROM tellus_brand_members WHERE brand_id = $1 AND account_id = $2",
            brand["id"], account.id,
        )
        viewer_is_mod = member_row is not None
        if not viewer_is_mod:
            membership = await bs.get_approved_membership(conn, post["board_id"], account.id)
            if membership is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a board member")

        # SQL prefilter narrows the round trip; bs.reply_visible_to is THE
        # predicate — the belt-and-braces filter below is what actually decides.
        rows = await conn.fetch(
            """SELECT r.*, a.display_name AS author_display_name
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
    slug: str, post_id: UUID, body: TellusBoardReplyCreate, account: TellusAccount = Depends(require_consumer),
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
            membership = await bs.get_approved_membership(conn, board["id"], account.id)
            if membership is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a board member")
            if brand["plan_status"] != "active" or not board["is_active"]:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=bs.BOARD_PAUSED_DETAIL)
            post = await conn.fetchrow(
                "SELECT id FROM tellus_board_posts WHERE id = $1 AND board_id = $2 AND moderation_status = 'visible'",
                post_id, board["id"],
            )
            if post is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

            row = await conn.fetchrow(
                """INSERT INTO tellus_board_replies (post_id, author_account_id, body)
                       VALUES ($1, $2, $3) RETURNING *""",
                post_id, account.id, body.body,
            )
            await bs.notify_board_team(
                conn, brand["id"], "board_reply_pending", "New reply awaiting approval",
                f"{account.display_name or 'A member'} replied to a board post.",
                reference_type="board_post", reference_id=str(post_id),
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
        brand, _role = await bs.resolve_moderated_brand(conn, account, brand_id)
        board = await bs.ensure_board(conn, brand["id"])
        return await _manage_summary(conn, board)


@router.patch("/board/manage", response_model=TellusBoardManageSummary)
async def update_board_manage(
    body: TellusBoardUpdate, brand_id: Optional[UUID] = Query(None),
    account: TellusAccount = Depends(require_tellus_account),
):
    async with get_connection() as conn:
        brand, _role = await bs.resolve_moderated_brand(conn, account, brand_id)
        bs.require_active_plan(brand)
        board = await bs.ensure_board(conn, brand["id"])
        row = await conn.fetchrow(
            """UPDATE tellus_boards SET
                   title = COALESCE($2, title), description = COALESCE($3, description),
                   is_active = COALESCE($4, is_active), updated_at = NOW()
               WHERE id = $1 RETURNING *""",
            board["id"], body.title, body.description, body.is_active,
        )
        return await _manage_summary(conn, row)


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
            """SELECT m.id, a.display_name AS account_display_name, m.decided_at AS joined_at
               FROM tellus_board_memberships m JOIN tellus_accounts a ON a.id = m.account_id
               WHERE m.board_id = $1 AND m.status = 'approved'
               ORDER BY m.decided_at DESC""",
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

            listing_row = None
            if body.kind == "deal":
                listing_row = await conn.fetchrow(
                    "SELECT l.*, b.name AS brand_name FROM tellus_reward_listings l "
                    "LEFT JOIN tellus_brands b ON b.id = l.brand_id "
                    "WHERE l.id = $1 AND l.brand_id = $2",
                    body.listing_id, brand["id"],
                )
                if listing_row is None or listing_row["visibility"] != "board":
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Pick a board-only reward",
                    )

            row = await conn.fetchrow(
                """INSERT INTO tellus_board_posts
                       (board_id, author_account_id, kind, title, body, listing_id,
                        event_starts_at, event_ends_at, is_pinned)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                   RETURNING *""",
                board["id"], account.id, body.kind, body.title, body.body, body.listing_id,
                body.event_starts_at, body.event_ends_at, body.is_pinned,
            )
            await bs.notify_board_members(
                conn, board["id"], "board_post", f"{brand['name']}: {row['title']}", body.body,
                reference_type="board_post", reference_id=str(row["id"]),
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
        # Ownership fetch scoped to this board — 404 not 403 (get_owned_report pattern).
        row = await conn.fetchrow(
            """UPDATE tellus_board_posts SET
                   title = COALESCE($3, title), body = COALESCE($4, body), is_pinned = COALESCE($5, is_pinned),
                   updated_at = NOW()
               WHERE id = $1 AND board_id = $2 RETURNING *""",
            post_id, board["id"], body.title, body.body, body.is_pinned,
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

        counts = await conn.fetchrow(
            """SELECT
                   (SELECT COUNT(*) FROM tellus_board_replies WHERE post_id = $1 AND status = 'approved')
                       AS approved_reply_count,
                   (SELECT COUNT(*) FROM tellus_board_replies WHERE post_id = $1 AND status = 'held')
                       AS held_reply_count""",
            post_id,
        )
        listing_row = None
        if row["listing_id"] is not None:
            listing_row = await conn.fetchrow(
                "SELECT l.*, b.name AS brand_name FROM tellus_reward_listings l "
                "LEFT JOIN tellus_brands b ON b.id = l.brand_id WHERE l.id = $1",
                row["listing_id"],
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


@router.get("/board/manage/replies")
async def list_manage_replies(
    reply_status: str = Query("held", alias="status"), brand_id: Optional[UUID] = Query(None),
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
        {
            "id": r["id"], "post_id": r["post_id"], "post_title": r["post_title"],
            "author_name": r["author_display_name"] or "Tell-Us member",
            "body": r["body"], "status": r["status"], "created_at": r["created_at"],
        }
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
            """SELECT m.id, a.display_name AS account_display_name, a.email, m.role, m.created_at
               FROM tellus_brand_members m JOIN tellus_accounts a ON a.id = m.account_id
               WHERE m.brand_id = $1 ORDER BY (m.role = 'owner') DESC, m.created_at ASC""",
            brand["id"],
        )
    return [
        TellusBrandTeamMember(
            id=r["id"], account_display_name=r["account_display_name"] or "Tell-Us member",
            email=r["email"], role=r["role"], created_at=r["created_at"],
        )
        for r in rows
    ]


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
                """INSERT INTO tellus_brand_members (brand_id, account_id, role, added_by)
                       VALUES ($1, $2, 'moderator', $3) RETURNING *""",
                brand["id"], target["id"], account.id,
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
        email=target["email"], role=row["role"], created_at=row["created_at"],
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

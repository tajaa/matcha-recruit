"""Tell-Us likes — pure counter on board posts, board replies, published
reviews, and reward listings. No points, no notifications.

NOT the brand heart: tellus_reports.hearted_at/hearted_by (feedback.py, gated
require_paid_brand) is a brand acknowledging a review. This is a consumer
like, a separate table (tellus_likes) with a separate count. Nothing here
reads or writes hearted_at/hearted_by.

Four nullable FK columns on tellus_likes (post_id/reply_id/report_id/
listing_id), not a polymorphic target_type/target_id pair — every target
keeps ON DELETE CASCADE. tellus_board_replies is hard-deleted by
routes/board.py:delete_own_reply and Tell-Us has no orphan-sweep cron to
compensate for a missing FK. See alembic/versions/tellus_app_15_likes.py.
"""
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status

from . import board_service as bs

_TARGET_COLUMNS = {
    "board_post": "post_id",
    "board_reply": "reply_id",
    "report": "report_id",
    "listing": "listing_id",
}


async def hydrate_likes(
    conn, target: str, ids: list[UUID], viewer_id: Optional[UUID],
) -> dict[UUID, tuple[int, bool]]:
    """{target_id: (like_count, liked_by_me)} for a whole page in one query.
    Missing key => (0, False) — callers use .get(id, (0, False)).

    viewer_id may be None (the unauthenticated public brand page): account_id
    = NULL is NULL, the FILTER matches nothing, liked_by_me comes back false.

    `target` is constrained to _TARGET_COLUMNS' keys by the LikeTargetType
    Literal on the routes/likes.py path param, so this lookup cannot KeyError
    from user input — the column name never comes from a request value.
    """
    if not ids:
        return {}
    col = _TARGET_COLUMNS[target]
    rows = await conn.fetch(
        f"""SELECT {col} AS target_id,
                   COUNT(*)::int AS like_count,
                   COUNT(*) FILTER (WHERE account_id = $2) > 0 AS liked_by_me
            FROM tellus_likes
            WHERE {col} = ANY($1::uuid[])
            GROUP BY {col}""",
        ids, viewer_id,
    )
    return {r["target_id"]: (r["like_count"], r["liked_by_me"]) for r in rows}


async def _assert_board_access(conn, account, row: dict) -> None:
    """Approved member OR brand-team moderator OR the brand's own owner.
    Mirrors routes/board.py:get_board's viewer_is_mod resolution — a
    consumer-typed team moderator and the owner (who may have no
    tellus_brand_members row) must both pass."""
    is_mod = await conn.fetchval(
        "SELECT 1 FROM tellus_brand_members WHERE brand_id = $1 AND account_id = $2",
        row["brand_id"], account.id,
    )
    is_owner = row.get("owner_account_id") == account.id
    if not is_mod and not is_owner:
        if await bs.get_approved_membership(conn, row["board_id"], account.id) is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a board member")
    if row["plan_status"] != "active" or not row["is_active"]:
        raise HTTPException(status.HTTP_409_CONFLICT, bs.BOARD_PAUSED_DETAIL)


async def _check_board_post(conn, account, post_id: UUID) -> None:
    row = await conn.fetchrow(
        """SELECT bo.id AS board_id, bo.is_active, b.id AS brand_id,
                  b.owner_account_id, b.plan_status
           FROM tellus_board_posts p
           JOIN tellus_boards bo ON bo.id = p.board_id
           JOIN tellus_brands  b ON b.id = bo.brand_id
           WHERE p.id = $1 AND p.moderation_status = 'visible'""",
        post_id,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    await _assert_board_access(conn, account, row)


async def _check_board_reply(conn, account, reply_id: UUID) -> None:
    row = await conn.fetchrow(
        """SELECT bo.id AS board_id, bo.is_active, b.id AS brand_id,
                  b.owner_account_id, b.plan_status
           FROM tellus_board_replies r
           JOIN tellus_board_posts p ON p.id = r.post_id
           JOIN tellus_boards bo ON bo.id = p.board_id
           JOIN tellus_brands  b ON b.id = bo.brand_id
           WHERE r.id = $1 AND r.status = 'approved' AND p.moderation_status = 'visible'""",
        reply_id,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reply not found")
    await _assert_board_access(conn, account, row)


async def _check_report(conn, account, report_id: UUID) -> None:
    if account.account_type != "consumer":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Brand accounts acknowledge reviews with the heart, not a like.",
        )
    ok = await conn.fetchval(
        """SELECT 1 FROM tellus_reports
           WHERE id = $1 AND review_state = 'held' AND publish_at <= NOW()
             AND moderation_status = 'visible'""",
        report_id,
    )
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")


async def _check_listing(conn, account, listing_id: UUID) -> None:
    if account.account_type != "consumer":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This action is for consumer accounts.")
    row = await conn.fetchrow(
        "SELECT id, brand_id, visibility FROM tellus_reward_listings WHERE id = $1 AND is_active",
        listing_id,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    if row["visibility"] != "board":
        return
    # visibility='board' — same three-way gate points_service.redeem_points uses.
    board = await conn.fetchrow(
        """SELECT bo.id AS board_id, bo.is_active, b.id AS brand_id,
                  b.owner_account_id, b.plan_status
           FROM tellus_boards bo JOIN tellus_brands b ON b.id = bo.brand_id
           WHERE bo.brand_id = $1""",
        row["brand_id"],
    )
    if board is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    await _assert_board_access(conn, account, board)


async def assert_can_like(conn, account, target: str, target_id: UUID) -> None:
    """404 when the target doesn't exist or isn't visible to this caller
    (existence-hiding, matching the get_owned_report pattern elsewhere in
    this app), 403 when it exists but the caller isn't eligible, 409 when
    the board is paused. Only ever called from the POST path — DELETE
    (unlike) is self-scoped by its WHERE clause and needs no authorization."""
    if target == "board_post":
        await _check_board_post(conn, account, target_id)
    elif target == "board_reply":
        await _check_board_reply(conn, account, target_id)
    elif target == "report":
        await _check_report(conn, account, target_id)
    else:
        await _check_listing(conn, account, target_id)

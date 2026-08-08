"""Tell-Us likes — pure counter on board posts, board replies, published
reviews, and reward listings. No points, no notifications.

One generic router rather than four per-domain handlers: the authorization
matrix (services/likes_service.py) IS the feature, and keeping it in one file
makes it reviewable and testable as a unit instead of four near-identical
handlers that drift. The rate limit is also per-account across all targets,
which needs a single call site.

NOT the brand heart: tellus_reports.hearted_at/hearted_by (feedback.py,
require_paid_brand) is a brand acknowledging a review — untouched here.
"""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends

from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_tellus_account
from ..models.tellus import TellusAccount, TellusLikeState
from ..services import likes_service as ls

router = APIRouter()

LikeTargetType = Literal["board_post", "board_reply", "report", "listing"]


@router.post("/likes/{target_type}/{target_id}", response_model=TellusLikeState)
async def like(
    target_type: LikeTargetType,
    target_id: UUID,
    account: TellusAccount = Depends(require_tellus_account),
):
    """Idempotent — a second tap returns the same count, never a conflict."""
    await check_rate_limit(str(account.id), "tellus_like_burst", 20, 60)
    await check_rate_limit(str(account.id), "tellus_like", 300, 3600)

    col = ls._TARGET_COLUMNS[target_type]
    async with get_connection() as conn:
        await ls.assert_can_like(conn, account, target_type, target_id)
        async with conn.transaction():
            # Bare ON CONFLICT DO NOTHING, no inference spec: the unique
            # indexes are partial (WHERE <col> IS NOT NULL), so an explicit
            # ON CONFLICT (<col>, account_id) clause would fail to match them.
            # Never catch asyncpg.UniqueViolationError here instead — a caught
            # unique violation inside an open transaction leaves it aborted
            # and the next query 500s (see tellus/CLAUDE.md ledger-idempotency
            # note).
            await conn.execute(
                f"INSERT INTO tellus_likes (account_id, {col}) VALUES ($1, $2) "
                f"ON CONFLICT DO NOTHING",
                account.id, target_id,
            )
            # Deliberately two statements, not a data-modifying CTE
            # (WITH ins AS (INSERT ... RETURNING 1) SELECT COUNT(*) ...) —
            # the SELECT and the CTE share one snapshot, so it can't see the
            # row the CTE just inserted and the count comes back stale by one.
            count = await conn.fetchval(
                f"SELECT COUNT(*)::int FROM tellus_likes WHERE {col} = $1", target_id,
            )
    return TellusLikeState(like_count=count, liked_by_me=True)


@router.delete("/likes/{target_type}/{target_id}", response_model=TellusLikeState)
async def unlike(
    target_type: LikeTargetType,
    target_id: UUID,
    account: TellusAccount = Depends(require_tellus_account),
):
    """Self-scoped by the WHERE clause (account_id = caller) — can only ever
    delete the caller's own row, so no target authorization is needed. Not
    gated on the target's visibility or the board's pause state: retraction
    must always work, or a like gets trapped on content that later became
    paused or invisible. A DELETE on a never-liked target is a no-op
    returning the current count, not a 404 — keeps double-tap symmetric."""
    await check_rate_limit(str(account.id), "tellus_like_burst", 20, 60)
    await check_rate_limit(str(account.id), "tellus_like", 300, 3600)

    col = ls._TARGET_COLUMNS[target_type]
    async with get_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                f"DELETE FROM tellus_likes WHERE account_id = $1 AND {col} = $2",
                account.id, target_id,
            )
            count = await conn.fetchval(
                f"SELECT COUNT(*)::int FROM tellus_likes WHERE {col} = $1", target_id,
            )
    return TellusLikeState(like_count=count, liked_by_me=False)

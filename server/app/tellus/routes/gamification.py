"""Tell-Us gamification — badges + city leaderboards."""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ...database import get_connection
from ..dependencies import require_consumer
from ..models.tellus import TellusAccount, TellusBadge, TellusLeaderboardEntry

router = APIRouter()


@router.get("/badges", response_model=list[TellusBadge])
async def my_badges(account: TellusAccount = Depends(require_consumer)):
    """All badge definitions with an `earned` flag for this consumer."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT d.key, d.name, d.description, d.icon, d.sort_order,
                      ub.awarded_at
               FROM tellus_badge_definitions d
               LEFT JOIN tellus_user_badges ub
                      ON ub.badge_key = d.key AND ub.account_id = $1
               ORDER BY d.sort_order, d.key""",
            account.id,
        )
    return [
        TellusBadge(
            key=r["key"], name=r["name"], description=r["description"], icon=r["icon"],
            earned=r["awarded_at"] is not None, awarded_at=r["awarded_at"],
        )
        for r in rows
    ]


@router.get("/leaderboard", response_model=list[TellusLeaderboardEntry])
async def leaderboard(
    account: TellusAccount = Depends(require_consumer),
    city: Optional[str] = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
):
    """Top consumers by lifetime points, optionally scoped to a city. Only
    opt-in accounts are listed (an opted-out caller still sees the board, just
    isn't on it)."""
    use_city = city or account.city
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT a.id, a.display_name, pb.lifetime_points, pb.level
               FROM tellus_points_balances pb
               JOIN tellus_accounts a ON a.id = pb.account_id
               WHERE a.account_type = 'consumer' AND a.leaderboard_opt_in
                 AND ($1::text IS NULL OR lower(a.city) = lower($1))
               ORDER BY pb.lifetime_points DESC, a.created_at ASC
               LIMIT $2""",
            use_city, limit,
        )
    out: list[TellusLeaderboardEntry] = []
    for i, r in enumerate(rows, start=1):
        # Never fall back to the email local-part — that leaks PII to every
        # consumer in the city. Anonymous-but-stable handle instead.
        name = r["display_name"] or f"Member-{str(r['id'])[:4]}"
        out.append(TellusLeaderboardEntry(
            rank=i, account_id=r["id"], display_name=name,
            lifetime_points=r["lifetime_points"], level=r["level"],
            is_you=r["id"] == account.id,
        ))
    return out

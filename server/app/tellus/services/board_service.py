"""Regulars board — shared logic for routes/board.py and admin oversight.

Vocabulary: replies use status ('held','approved','rejected','removed') — the
pre-moderation analogue of review_state+moderation_status. Every member-facing
predicate is strict equality status='approved' so any future state fails closed
(same principle as moderation_status='visible' on the public brand page).
"""
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status

from ..models.tellus import TellusAccount, TellusBoardPost, TellusBoardReply
from .access_service import assert_capability, find_brand_access
from .marketplace_service import serialize_listing
from .points_service import award_points, notify_account

BOARD_PAUSED_DETAIL = "This board is paused."     # plan lapsed / is_active=false → 409


async def ensure_board(conn, brand_id: UUID) -> dict:
    """Lazy-create the brand's single board row. ON CONFLICT (brand_id) DO NOTHING
    + re-select — safe under concurrent first hits. Created PAUSED (is_active=FALSE):
    this is reached from GET endpoints too, so a mere page view must not flip the
    public /b/{slug} join CTA on — the owner explicitly publishes via
    PATCH /board/manage {is_active: true}."""
    row = await conn.fetchrow(
        """INSERT INTO tellus_boards (brand_id, is_active) VALUES ($1, FALSE)
           ON CONFLICT (brand_id) DO NOTHING RETURNING *""",
        brand_id,
    )
    if row is None:
        row = await conn.fetchrow("SELECT * FROM tellus_boards WHERE brand_id = $1", brand_id)
    return dict(row)


async def get_approved_membership(conn, board_id: UUID, account_id: UUID) -> Optional[dict]:
    row = await conn.fetchrow(
        "SELECT * FROM tellus_board_memberships WHERE board_id = $1 AND account_id = $2 AND status = 'approved'",
        board_id, account_id,
    )
    return dict(row) if row is not None else None


async def resolve_moderated_brand(
    conn, account: TellusAccount, brand_id: Optional[UUID] = None,
) -> tuple[dict, str]:
    """Resolve one active membership with the explicit Board capability."""
    if brand_id is not None:
        context = await find_brand_access(conn, account.id, brand_id)
        if context is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not a moderator of that board")
        assert_capability(context, "board.manage")
    else:
        rows = await conn.fetch(
            """SELECT brand_id
               FROM tellus_brand_members
               WHERE account_id = $1 AND status = 'active'""",
            account.id,
        )
        contexts = []
        for row in rows:
            candidate = await find_brand_access(conn, account.id, row["brand_id"])
            if candidate is not None and "board.manage" in candidate.capabilities:
                contexts.append(candidate)
        if len(contexts) > 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Specify brand_id")
        if not contexts:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not a moderator of any board")
        context = contexts[0]

    brand = await conn.fetchrow("SELECT * FROM tellus_brands WHERE id = $1", context.brand_id)
    if brand is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    return dict(brand), context.role


def require_active_plan(brand_row: dict) -> None:
    """402 unless plan_status='active'. Mutations only — reads survive a lapse."""
    if brand_row["plan_status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="This brand account does not have an active subscription.",
        )


def reply_visible_to(reply_status: str, author_id: UUID, viewer_id: UUID, viewer_is_mod: bool) -> bool:
    """Pure. Strict: status=='approved' → everyone in the board.
    Otherwise author sees own (held/rejected chip) and mods see held.
    'removed' visible to mods only (not author — same as removed reviews).
    Any other/unrecognized status fails closed (False)."""
    if reply_status == "approved":
        return True
    if reply_status == "held":
        return viewer_is_mod or author_id == viewer_id
    if reply_status == "rejected":
        return viewer_is_mod or author_id == viewer_id
    if reply_status == "removed":
        return viewer_is_mod
    return False


def can_reply_transition(from_status: str, to_status: str) -> bool:
    """Pure. held→approved, held→rejected, approved→removed. Nothing else
    (no un-reject, no un-remove — admin force path bypasses via its own endpoint).
    Called by the three brand-moderator routes in routes/board.py (approve_reply,
    reject_reply, remove_reply) before their UPDATE; the admin force path
    (routes/admin/moderation.py:admin_force_reply_status) deliberately does not
    call this — it can move rejected/removed→approved to overturn a bad brand
    call, which this matrix forbids by design."""
    return (from_status, to_status) in {
        ("held", "approved"),
        ("held", "rejected"),
        ("approved", "removed"),
    }


async def loyalty_signals(conn, brand_id: UUID, account_ids: list[UUID]) -> dict[UUID, dict]:
    """One set-based query per signal. Identified reviewers only —
    reporter_account_id IS NULL rows invisible (UI copy says 'identified
    activity only'). Returns {account_id: {review_count, hearted, redemption_count}}."""
    out = {aid: {"review_count": 0, "hearted": False, "redemption_count": 0} for aid in account_ids}
    if not account_ids:
        return out

    review_rows = await conn.fetch(
        """SELECT reporter_account_id AS account_id, COUNT(*) AS review_count,
                  bool_or(hearted_at IS NOT NULL) AS hearted
           FROM tellus_reports
           WHERE brand_id = $1 AND reporter_account_id = ANY($2::uuid[])
           GROUP BY reporter_account_id""",
        brand_id, account_ids,
    )
    for r in review_rows:
        out[r["account_id"]]["review_count"] = r["review_count"]
        out[r["account_id"]]["hearted"] = r["hearted"]

    redemption_rows = await conn.fetch(
        """SELECT r.account_id, COUNT(*) AS redemption_count
           FROM tellus_redemptions r JOIN tellus_reward_listings l ON l.id = r.listing_id
           WHERE l.brand_id = $1 AND r.account_id = ANY($2::uuid[])
           GROUP BY r.account_id""",
        brand_id, account_ids,
    )
    for r in redemption_rows:
        out[r["account_id"]]["redemption_count"] = r["redemption_count"]

    return out


async def notify_board_members(
    conn, board_id: UUID, kind: str, title: str, body: Optional[str],
    reference_type: str, reference_id: str,
    exclude_account_id: Optional[UUID] = None,
    slug: Optional[str] = None,
    name: Optional[str] = None,
) -> None:
    """Fan-out to every approved board member in one statement.

    The `::text` casts on $2-$6 are load-bearing, not decoration — inside an
    INSERT...SELECT, parameter types are only reachable through the SELECT's
    target list, which Postgres can fail to infer (asyncpg's Parse then errors
    with "could not determine data type of parameter $2"). Every caller here
    passes plain strings (kind/title/reference_type/reference_id) or a
    possibly-NULL string (body), so casting the lot to text is always correct.
    """
    rows = await conn.fetch(
        """INSERT INTO tellus_notifications (account_id, kind, title, body, reference_type, reference_id)
           SELECT account_id, $2::text, $3::text, $4::text, $5::text, $6::text
           FROM tellus_board_memberships
           WHERE board_id = $1 AND status = 'approved'
             AND ($7::uuid IS NULL OR account_id <> $7)
           RETURNING account_id""",
        board_id, kind, title, body, reference_type, reference_id, exclude_account_id,
    )
    from . import push
    push.schedule_push(
        [r["account_id"] for r in rows], kind, title, body,
        reference_type=reference_type, reference_id=reference_id,
        slug=slug, name=name,
    )


async def notify_board_team(
    conn, brand_id: UUID, kind: str, title: str, body: Optional[str],
    reference_type: str, reference_id: str,
    slug: Optional[str] = None,
    name: Optional[str] = None,
) -> None:
    """Same shape over tellus_brand_members — see notify_board_members for why
    the ::text casts on $2-$6 aren't optional."""
    rows = await conn.fetch(
        """INSERT INTO tellus_notifications (account_id, kind, title, body, reference_type, reference_id)
           SELECT account_id, $2::text, $3::text, $4::text, $5::text, $6::text
           FROM tellus_brand_members WHERE brand_id = $1
           RETURNING account_id""",
        brand_id, kind, title, body, reference_type, reference_id,
    )
    from . import push
    push.schedule_push(
        [r["account_id"] for r in rows], kind, title, body,
        reference_type=reference_type, reference_id=reference_id,
        slug=slug, name=name,
    )


async def approve_reply_and_award(
    conn, reply_id: UUID, actor_id: UUID, *, board_id: Optional[UUID] = None,
    from_statuses: tuple = ("held",),
) -> Optional[dict]:
    """Flip a reply to approved and award the earning rule, atomically.
    Shared by the brand-moderator approve route and the admin force-approve
    path so the two callers can't drift on reason/bypass_cooldown.

    board_id scopes the UPDATE to a specific board (the brand-moderator path);
    None means unscoped (the admin force path, which can act cross-brand).
    from_statuses gates which current statuses may transition to approved —
    brand moderators only ever move held→approved; the admin force path also
    allows rejected/removed→approved (an admin overturning a bad brand call),
    which still can't double-credit thanks to the ledger's ON CONFLICT DO NOTHING.
    Returns {author_account_id, post_id}, or None if no matching reply
    (already approved, wrong id, or — when board_id is set — wrong board).
    """
    if board_id is not None:
        row = await conn.fetchrow(
            """UPDATE tellus_board_replies SET status = 'approved', moderated_at = NOW(), moderated_by = $2
               WHERE id = $1 AND status = ANY($4::text[])
                 AND post_id IN (SELECT id FROM tellus_board_posts WHERE board_id = $3)
               RETURNING author_account_id, post_id""",
            reply_id, actor_id, board_id, list(from_statuses),
        )
    else:
        row = await conn.fetchrow(
            """UPDATE tellus_board_replies SET status = 'approved', moderated_at = NOW(), moderated_by = $2
               WHERE id = $1 AND status = ANY($3::text[])
               RETURNING author_account_id, post_id""",
            reply_id, actor_id, list(from_statuses),
        )
    if row is None:
        return None

    # award_points opens its own conn.transaction() → SAVEPOINT here; its
    # ON CONFLICT DO NOTHING idempotency means a reject→re-approve (via the
    # admin force path) can never double-credit. NEVER catch
    # UniqueViolationError around this (savepoint-abort 500).
    await award_points(
        conn, row["author_account_id"], "earn_engagement",
        event_key="board_reply_approved", reference_type="board_reply",
        reference_id=str(reply_id), description="Board reply approved",
        bypass_cooldown=True,
    )
    await notify_account(
        conn, row["author_account_id"], "board_reply_approved", "Your reply was approved",
        "Your reply on the regulars board was approved.",
        reference_type="board_post", reference_id=str(row["post_id"]),
    )
    return dict(row)


def serialize_post(row, *, viewer_is_mod: bool, listing_row=None) -> TellusBoardPost:
    return TellusBoardPost(
        id=row["id"],
        kind=row["kind"],
        title=row["title"],
        body=row["body"],
        listing=serialize_listing(listing_row) if listing_row is not None else None,
        event_starts_at=row["event_starts_at"],
        event_ends_at=row["event_ends_at"],
        is_pinned=row["is_pinned"],
        moderation_status=row["moderation_status"],
        approved_reply_count=row["approved_reply_count"] if "approved_reply_count" in row.keys() else 0,
        held_reply_count=(
            row["held_reply_count"]
            if viewer_is_mod and "held_reply_count" in row.keys()
            else None
        ),
        created_at=row["created_at"],
        like_count=row["like_count"] if "like_count" in row.keys() else 0,
        liked_by_me=row["liked_by_me"] if "liked_by_me" in row.keys() else False,
    )


def serialize_reply(row, *, viewer_id: UUID) -> TellusBoardReply:
    # author_name = display_name or 'Tell-Us member' (TellusPublicReview
    # whitelist pattern). Email never serialized.
    return TellusBoardReply(
        id=row["id"],
        post_id=row["post_id"],
        author_name=row["author_display_name"] or "Tell-Us member",
        is_mine=row["author_account_id"] == viewer_id,
        status=row["status"],
        body=row["body"],
        created_at=row["created_at"],
        like_count=row["like_count"] if "like_count" in row.keys() else 0,
        liked_by_me=row["liked_by_me"] if "liked_by_me" in row.keys() else False,
    )

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
from .marketplace_service import serialize_listing
from .points_service import award_points, notify_account

BOARD_PAUSED_DETAIL = "This board is paused."     # plan lapsed / is_active=false → 409


async def ensure_board(conn, brand_id: UUID) -> dict:
    """Lazy-create the brand's single board row. ON CONFLICT (brand_id) DO NOTHING
    + re-select — safe under concurrent first hits."""
    row = await conn.fetchrow(
        """INSERT INTO tellus_boards (brand_id) VALUES ($1)
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
    """Which brand is this caller moderating?

    - account_type='brand'  → account.brand_id (member row must exist — backfill
      guarantees it for owners; falls back to 'owner' if somehow absent rather
      than 404ing the brand's own owner out of their own board).
    - consumer w/ member rows: exactly one → it; brand_id param → verify member;
      several + no param → 400 'Specify brand_id'.
    - no membership → 404 (existence-hiding, _get_thread_for_account pattern).

    Returns (brand row incl. plan_status, caller's role ('owner'|'moderator')).
    """
    if account.account_type == "brand":
        brand = await conn.fetchrow("SELECT * FROM tellus_brands WHERE id = $1", account.brand_id)
        if brand is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
        member = await conn.fetchrow(
            "SELECT role FROM tellus_brand_members WHERE brand_id = $1 AND account_id = $2",
            account.brand_id, account.id,
        )
        role = member["role"] if member is not None else "owner"
        return dict(brand), role

    rows = await conn.fetch(
        """SELECT bm.role AS _role, b.*
           FROM tellus_brand_members bm JOIN tellus_brands b ON b.id = bm.brand_id
           WHERE bm.account_id = $1""",
        account.id,
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not a moderator of any board")
    if brand_id is not None:
        match = next((r for r in rows if r["id"] == brand_id), None)
        if match is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not a moderator of that board")
        return dict(match), match["_role"]
    if len(rows) > 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Specify brand_id")
    row = rows[0]
    return dict(row), row["_role"]


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
    (no un-reject, no un-remove — admin force path bypasses via its own endpoint)."""
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
) -> None:
    """Fan-out to every approved board member in one statement."""
    if exclude_account_id is not None:
        await conn.execute(
            """INSERT INTO tellus_notifications (account_id, kind, title, body, reference_type, reference_id)
               SELECT account_id, $2, $3, $4, $5, $6 FROM tellus_board_memberships
               WHERE board_id = $1 AND status = 'approved' AND account_id <> $7""",
            board_id, kind, title, body, reference_type, reference_id, exclude_account_id,
        )
    else:
        await conn.execute(
            """INSERT INTO tellus_notifications (account_id, kind, title, body, reference_type, reference_id)
               SELECT account_id, $2, $3, $4, $5, $6 FROM tellus_board_memberships
               WHERE board_id = $1 AND status = 'approved'""",
            board_id, kind, title, body, reference_type, reference_id,
        )


async def notify_board_team(
    conn, brand_id: UUID, kind: str, title: str, body: Optional[str],
    reference_type: str, reference_id: str,
) -> None:
    """Same shape over tellus_brand_members."""
    await conn.execute(
        """INSERT INTO tellus_notifications (account_id, kind, title, body, reference_type, reference_id)
           SELECT account_id, $2, $3, $4, $5, $6 FROM tellus_brand_members WHERE brand_id = $1""",
        brand_id, kind, title, body, reference_type, reference_id,
    )


async def approve_reply_and_award(
    conn, reply_id: UUID, actor_id: UUID, *, board_id: Optional[UUID] = None,
) -> Optional[dict]:
    """Flip a held reply to approved and award the earning rule, atomically.
    Shared by the brand-moderator approve route and the admin force-approve
    path so the two callers can't drift on reason/bypass_cooldown.

    board_id scopes the UPDATE to a specific board (the brand-moderator path);
    None means unscoped (the admin force path, which can act cross-brand).
    Returns {author_account_id, post_id}, or None if no held reply matched
    (already moderated, wrong id, or — when board_id is set — wrong board).
    """
    if board_id is not None:
        row = await conn.fetchrow(
            """UPDATE tellus_board_replies SET status = 'approved', moderated_at = NOW(), moderated_by = $2
               WHERE id = $1 AND status = 'held'
                 AND post_id IN (SELECT id FROM tellus_board_posts WHERE board_id = $3)
               RETURNING author_account_id, post_id""",
            reply_id, actor_id, board_id,
        )
    else:
        row = await conn.fetchrow(
            """UPDATE tellus_board_replies SET status = 'approved', moderated_at = NOW(), moderated_by = $2
               WHERE id = $1 AND status = 'held'
               RETURNING author_account_id, post_id""",
            reply_id, actor_id,
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
    )

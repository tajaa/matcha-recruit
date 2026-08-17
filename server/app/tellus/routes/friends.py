"""Tell-Us consumer handles and profile privacy controls."""
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse

from ...core.services.redis_cache import (
    cache_get,
    cache_set,
    check_rate_limit,
    client_ip,
    get_redis_cache,
)
from ...database import get_connection
from ..dependencies import require_verified_consumer
from ..models.tellus import (
    TellusAccount,
    TellusFriendRequest,
    TellusFriendRequestCount,
    TellusFriendRequestCreate,
    TellusBlockCreate,
    TellusFriendListPage,
    TellusHandleAvailability,
    TellusHandleClaim,
    TellusPersonSummary,
    TellusPersonBoard,
    TellusPersonFollowedPlace,
    TellusPersonProfile,
    TellusPersonReview,
)
from ..services.friends_service import (
    FRIEND_DECLINE_COOLDOWN,
    can_request,
    block_account,
    create_friendship,
    display_name_for,
    handle_rejection_reason,
    normalize_handle,
    remove_friendship,
    assert_not_blocked,
    search_people,
    suggestions,
    visible_sections,
)
from ..services.points_service import notify_account
from ..services.likes_service import hydrate_likes

router = APIRouter()
HANDLE_COOLDOWN = FRIEND_DECLINE_COOLDOWN


async def _person_summary(
    conn, account_id: UUID, viewer_id: UUID, mutual_friend_count: int = 0,
) -> TellusPersonSummary:
    row = await conn.fetchrow(
        """SELECT a.id AS account_id, a.display_name, a.handle, a.avatar_url,
                  a.city, a.state, pb.level, pb.lifetime_points,
                  EXISTS (SELECT 1 FROM tellus_friendships f
                          WHERE f.account_id = $2 AND f.friend_account_id = a.id) AS is_friend
             FROM tellus_accounts a
             LEFT JOIN tellus_points_balances pb ON pb.account_id = a.id
            WHERE a.id = $1 AND a.account_type = 'consumer' AND a.status = 'active'""",
        account_id, viewer_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    pending_id = await conn.fetchval(
        """SELECT id FROM tellus_friend_requests
            WHERE status = 'pending'
              AND ((requester_account_id = $1 AND addressee_account_id = $2)
                OR (requester_account_id = $2 AND addressee_account_id = $1))
            ORDER BY created_at DESC LIMIT 1""",
        viewer_id, account_id,
    )
    return TellusPersonSummary(
        account_id=row["account_id"],
        display_name=display_name_for(row["display_name"], row["handle"], row["account_id"]),
        handle=row["handle"], avatar_url=row["avatar_url"], city=row["city"], state=row["state"],
        level=row["level"] if row["level"] is not None else 1,
        lifetime_points=row["lifetime_points"] if row["lifetime_points"] is not None else 0,
        is_friend=bool(row["is_friend"]), mutual_friend_count=mutual_friend_count,
        pending_request_id=pending_id,
        is_you=account_id == viewer_id,
    )


def _request_model(row: Any, person: TellusPersonSummary, viewer_id: UUID) -> TellusFriendRequest:
    return TellusFriendRequest(
        id=row["id"], requester_account_id=row["requester_account_id"],
        addressee_account_id=row["addressee_account_id"], status=row["status"],
        source=row["source"], created_at=row["created_at"], decided_at=row["decided_at"],
        person=person,
        direction="incoming" if row["addressee_account_id"] == viewer_id else "outgoing",
    )


def _cooldown_days(now: datetime, available_at: datetime) -> int:
    remaining = available_at - now
    return max(1, (remaining.days + (remaining.seconds > 0)))


@router.get("/friends/handle-available", response_model=TellusHandleAvailability)
async def handle_available(
    request: Request,
    handle: str = Query(..., min_length=1, max_length=100),
    account: TellusAccount = Depends(require_verified_consumer),
):
    """Check a handle without exposing account data or email addresses."""
    await check_rate_limit(client_ip(request), "tellus_handle_available", 60, 3600)
    normalized = normalize_handle(handle)
    reason = handle_rejection_reason(normalized)
    if reason is None:
        async with get_connection() as conn:
            taken = await conn.fetchval(
                "SELECT 1 FROM tellus_accounts WHERE handle = $1 AND id <> $2",
                normalized, account.id,
            )
        reason = "taken" if taken else None
    return TellusHandleAvailability(
        handle=normalized,
        available=reason is None,
        reason=reason,
    )


@router.post("/me/handle", response_model=TellusAccount)
async def claim_handle(
    body: TellusHandleClaim,
    request: Request,
    account: TellusAccount = Depends(require_verified_consumer),
):
    """Claim or change the caller's handle, at most once per 30 days."""
    await check_rate_limit(str(account.id), "tellus_handle_claim", 5, 86400)
    handle = normalize_handle(body.handle)
    reason = handle_rejection_reason(handle)
    if reason == "format":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_handle", "message": "Handle format is invalid."},
        )
    if reason == "reserved":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "reserved_handle", "message": "That handle is reserved."},
        )

    now = datetime.now(timezone.utc)
    if account.handle == handle:
        return account
    if account.handle_set_at is not None:
        handle_available_at = account.handle_set_at + HANDLE_COOLDOWN
        if now < handle_available_at:
            retry_after_days = _cooldown_days(now, handle_available_at)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "handle_cooldown",
                    "message": "You can change your handle again later.",
                    "retry_after_days": retry_after_days,
                },
            )

    async with get_connection() as conn:
        async with conn.transaction():
            # Serialize claims for the same normalized handle so the check and
            # update do not turn the unique-index race into a 500.
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"tellus-handle:{handle}",
            )
            taken = await conn.fetchval(
                "SELECT 1 FROM tellus_accounts WHERE handle = $1 AND id <> $2",
                handle, account.id,
            )
            if taken:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "handle_taken", "message": "That handle is already taken."},
                )
            await conn.execute(
                "UPDATE tellus_accounts SET handle = $2, handle_set_at = $3, updated_at = NOW() "
                "WHERE id = $1",
                account.id, handle, now,
            )

    return account.model_copy(update={"handle": handle, "handle_set_at": now})


@router.post("/friends/requests")
async def create_friend_request(
    body: TellusFriendRequestCreate,
    account: TellusAccount = Depends(require_verified_consumer),
):
    await check_rate_limit(str(account.id), "tellus_friend_request", 30, 3600)
    async with get_connection() as conn:
        async with conn.transaction():
            target_id = body.account_id
            if target_id is None:
                target_id = await conn.fetchval(
                    "SELECT id FROM tellus_accounts WHERE handle = $1 "
                    "AND account_type = 'consumer' AND status = 'active'",
                    normalize_handle(body.handle or ""),
                )
            if target_id is None or target_id == account.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
            target = await conn.fetchrow(
                "SELECT id FROM tellus_accounts WHERE id = $1 AND account_type = 'consumer' AND status = 'active'",
                target_id,
            )
            if target is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
            await assert_not_blocked(conn, account.id, target_id)
            pair_lo, pair_hi = sorted((account.id, target_id))
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"tellus-friend-pair:{pair_lo}:{pair_hi}",
            )
            existing = await conn.fetchrow(
                """SELECT * FROM tellus_friend_requests
                    WHERE pair_lo = $1 AND pair_hi = $2
                    ORDER BY created_at DESC LIMIT 1 FOR UPDATE""",
                pair_lo, pair_hi,
            )
            if existing and existing["status"] == "pending":
                if existing["addressee_account_id"] != account.id:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request already pending")
                await conn.execute(
                    "UPDATE tellus_friend_requests SET status = 'accepted', decided_at = NOW() WHERE id = $1",
                    existing["id"],
                )
                await create_friendship(conn, account.id, target_id, "request")
                await notify_account(
                    conn, existing["requester_account_id"], "friend_accepted",
                    "Friend request accepted", "You are now friends.",
                    reference_type="account", reference_id=str(account.id),
                    slug=account.handle, name=display_name_for(account.display_name, account.handle, account.id),
                )
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content=(await _person_summary(conn, target_id, account.id)).model_dump(mode="json"),
                )
            if existing and not can_request(
                existing["status"], existing["decided_at"], datetime.now(timezone.utc)
            ):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot send a request yet")
            row = await conn.fetchrow(
                """INSERT INTO tellus_friend_requests
                   (requester_account_id, addressee_account_id, source)
                   VALUES ($1, $2, $3) RETURNING *""",
                account.id, target_id, body.source,
            )
            actor_name = display_name_for(account.display_name, account.handle, account.id)
            await notify_account(
                conn, target_id, "friend_request", "New friend request",
                f"{actor_name} wants to be your friend.",
                reference_type="friend_request", reference_id=str(row["id"]),
                slug=account.handle, name=actor_name,
            )
            person = await _person_summary(conn, target_id, account.id)
            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content=_request_model(row, person, account.id).model_dump(mode="json"),
            )


@router.post("/friends/requests/{request_id}/accept")
async def accept_friend_request(
    request_id: UUID,
    account: TellusAccount = Depends(require_verified_consumer),
):
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """UPDATE tellus_friend_requests
                      SET status = 'accepted', decided_at = NOW()
                    WHERE id = $1 AND addressee_account_id = $2 AND status = 'pending'
                RETURNING *""",
                request_id, account.id,
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request is no longer pending")
            requester_id = row["requester_account_id"]
            await create_friendship(conn, account.id, requester_id, "request")
            actor_name = display_name_for(account.display_name, account.handle, account.id)
            await notify_account(
                conn, requester_id, "friend_accepted", "Friend request accepted",
                "You are now friends.", reference_type="account", reference_id=str(account.id),
                slug=account.handle, name=actor_name,
            )
            person = await _person_summary(conn, requester_id, account.id)
    return person.model_dump(mode="json")


@router.post("/friends/requests/{request_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
async def decline_friend_request(
    request_id: UUID,
    account: TellusAccount = Depends(require_verified_consumer),
):
    async with get_connection() as conn:
        result = await conn.execute(
            """UPDATE tellus_friend_requests SET status = 'declined', decided_at = NOW()
                WHERE id = $1 AND addressee_account_id = $2 AND status = 'pending'""",
            request_id, account.id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request is no longer pending")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/friends/requests/{request_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_friend_request(
    request_id: UUID,
    account: TellusAccount = Depends(require_verified_consumer),
):
    async with get_connection() as conn:
        result = await conn.execute(
            """UPDATE tellus_friend_requests SET status = 'cancelled', decided_at = NOW()
                WHERE id = $1 AND requester_account_id = $2 AND status = 'pending'""",
            request_id, account.id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request is no longer pending")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/friend-requests", response_model=list[TellusFriendRequest])
async def list_friend_requests(
    direction: str = Query("incoming", pattern="^(incoming|outgoing)$"),
    account: TellusAccount = Depends(require_verified_consumer),
):
    column = "addressee_account_id" if direction == "incoming" else "requester_account_id"
    other = "requester_account_id" if direction == "incoming" else "addressee_account_id"
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""SELECT * FROM tellus_friend_requests
                 WHERE {column} = $1 AND status = 'pending'
                 ORDER BY created_at DESC""",
            account.id,
        )
        result = [
            _request_model(row, await _person_summary(conn, row[other], account.id), account.id)
            for row in rows
        ]
    return result


@router.get("/me/friend-requests/count", response_model=TellusFriendRequestCount)
async def friend_request_count(account: TellusAccount = Depends(require_verified_consumer)):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT
                 COUNT(*) FILTER (WHERE addressee_account_id = $1) AS incoming,
                 COUNT(*) FILTER (WHERE requester_account_id = $1) AS outgoing
                FROM tellus_friend_requests
               WHERE status = 'pending'
                 AND (addressee_account_id = $1 OR requester_account_id = $1)""",
            account.id,
        )
    return TellusFriendRequestCount(incoming=row["incoming"], outgoing=row["outgoing"])


@router.get("/me/friends", response_model=TellusFriendListPage)
async def list_friends(
    q: str = Query("", max_length=100),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    account: TellusAccount = Depends(require_verified_consumer),
):
    pattern = f"%{q.strip()}%" if q.strip() else None
    async with get_connection() as conn:
        total = await conn.fetchval(
            """SELECT COUNT(*) FROM tellus_friendships f
                JOIN tellus_accounts a ON a.id = f.friend_account_id
               WHERE f.account_id = $1 AND a.status = 'active'
                 AND ($2::text IS NULL OR a.display_name ILIKE $2 OR a.handle ILIKE $2)""",
            account.id, pattern,
        )
        rows = await conn.fetch(
            """SELECT f.friend_account_id, f.created_at
                FROM tellus_friendships f
                JOIN tellus_accounts a ON a.id = f.friend_account_id
               WHERE f.account_id = $1 AND a.status = 'active'
                 AND ($2::text IS NULL OR a.display_name ILIKE $2 OR a.handle ILIKE $2)
               ORDER BY f.created_at DESC, f.friend_account_id
               OFFSET $3 LIMIT $4""",
            account.id, pattern, offset, limit,
        )
        entries = [await _person_summary(conn, row["friend_account_id"], account.id) for row in rows]
    next_offset = offset + len(entries) if offset + len(entries) < total else None
    return TellusFriendListPage(entries=entries, total=total, next_offset=next_offset)


@router.delete("/me/friends/{friend_account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_friend(
    friend_account_id: UUID,
    account: TellusAccount = Depends(require_verified_consumer),
):
    async with get_connection() as conn:
        await remove_friendship(conn, account.id, friend_account_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/me/blocks", status_code=status.HTTP_204_NO_CONTENT)
async def block_friend(
    body: TellusBlockCreate,
    account: TellusAccount = Depends(require_verified_consumer),
):
    if body.account_id == account.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot block yourself")
    async with get_connection() as conn:
        target = await conn.fetchval(
            "SELECT 1 FROM tellus_accounts WHERE id = $1 AND account_type = 'consumer' AND status = 'active'",
            body.account_id,
        )
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        await block_account(conn, account.id, body.account_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/blocks", response_model=list[TellusPersonSummary])
async def list_blocks(account: TellusAccount = Depends(require_verified_consumer)):
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT blocked_account_id FROM tellus_account_blocks
                WHERE blocker_account_id = $1 ORDER BY created_at DESC""",
            account.id,
        )
        return [await _person_summary(conn, row["blocked_account_id"], account.id) for row in rows]


@router.delete("/me/blocks/{blocked_account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unblock_account(
    blocked_account_id: UUID,
    account: TellusAccount = Depends(require_verified_consumer),
):
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM tellus_account_blocks WHERE blocker_account_id = $1 AND blocked_account_id = $2",
            account.id, blocked_account_id,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/friends/search", response_model=list[TellusPersonSummary])
async def search_friends(
    request: Request,
    q: str = Query(..., min_length=2, max_length=40),
    limit: int = Query(20, ge=1, le=50),
    account: TellusAccount = Depends(require_verified_consumer),
):
    await check_rate_limit(str(account.id), "tellus_friend_search", 60, 60)
    async with get_connection() as conn:
        rows = await search_people(conn, account.id, q, limit)
        return [
            await _person_summary(conn, row["account_id"], account.id, row["mutual_friend_count"])
            for row in rows
        ]


@router.get("/friends/suggestions", response_model=list[TellusPersonSummary])
async def friend_suggestions(
    request: Request,
    limit: int = Query(20, ge=1, le=50),
    account: TellusAccount = Depends(require_verified_consumer),
):
    await check_rate_limit(str(account.id), "tellus_friend_suggestions", 60, 3600)
    redis = get_redis_cache()
    cache_key = f"tellus:friend-suggestions:{account.id}"
    ids = await cache_get(redis, cache_key) if redis else None
    async with get_connection() as conn:
        if not isinstance(ids, list):
            ids = await suggestions(conn, account.id, 100)
            if redis:
                await cache_set(redis, cache_key, ids, ttl=900)
        return [await _person_summary(conn, UUID(str(account_id)), account.id) for account_id in ids[:limit]]


async def _person_profile(conn, viewer_id: UUID, subject_id: UUID) -> TellusPersonProfile:
    subject = await conn.fetchrow(
        """SELECT a.id, a.display_name, a.handle, a.avatar_url, a.city, a.state,
                  a.profile_visibility, a.leaderboard_opt_in,
                  pb.level, pb.lifetime_points, pb.current_streak,
                  (SELECT COUNT(*) FROM tellus_friendships f WHERE f.account_id = a.id) AS friend_count,
                  EXISTS (SELECT 1 FROM tellus_friendships f
                          WHERE f.account_id = $1 AND f.friend_account_id = a.id) AS is_friend,
                  (SELECT MIN(f.created_at) FROM tellus_friendships f
                    WHERE f.account_id = $1 AND f.friend_account_id = a.id) AS friends_since
             FROM tellus_accounts a
             LEFT JOIN tellus_points_balances pb ON pb.account_id = a.id
            WHERE a.id = $2 AND a.account_type = 'consumer' AND a.status = 'active'""",
        viewer_id, subject_id,
    )
    if subject is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    await assert_not_blocked(conn, viewer_id, subject_id)
    is_self = viewer_id == subject_id
    is_friend = bool(subject["is_friend"])
    sections = visible_sections(
        is_self=is_self,
        is_friend=is_friend,
        profile_visibility=subject["profile_visibility"],
        leaderboard_opt_in=subject["leaderboard_opt_in"],
    )
    mutual_count = await conn.fetchval(
        """SELECT COUNT(*) FROM tellus_friendships mutual
            WHERE mutual.account_id = $1
              AND mutual.friend_account_id IN (
                  SELECT f.friend_account_id FROM tellus_friendships f WHERE f.account_id = $2)""",
        viewer_id, subject_id,
    )
    pending_id = await conn.fetchval(
        """SELECT id FROM tellus_friend_requests
            WHERE status = 'pending'
              AND ((requester_account_id = $1 AND addressee_account_id = $2)
                OR (requester_account_id = $2 AND addressee_account_id = $1))
            ORDER BY created_at DESC LIMIT 1""",
        viewer_id, subject_id,
    )
    profile = TellusPersonProfile(
        account_id=subject["id"],
        display_name=display_name_for(subject["display_name"], subject["handle"], subject["id"]),
        handle=subject["handle"], avatar_url=subject["avatar_url"], city=subject["city"], state=subject["state"],
        level=subject["level"] or 1, lifetime_points=subject["lifetime_points"] or 0,
        current_streak=subject["current_streak"] or 0, friend_count=subject["friend_count"] or 0,
        mutual_friend_count=mutual_count or 0, friends_since=subject["friends_since"],
        is_friend=is_friend, pending_request_id=pending_id, is_you=is_self,
    )
    if "points" not in sections:
        profile.level = 1
        profile.lifetime_points = 0
        profile.current_streak = 0
    if "reviews" in sections:
        review_rows = await conn.fetch(
            """SELECT r.id, r.brand_id, b.name AS brand_name, b.slug AS brand_slug,
                      r.rating, r.title, r.description, r.created_at, r.publish_at
                 FROM tellus_reports r JOIN tellus_brands b ON b.id = r.brand_id
                WHERE r.reporter_account_id = $1 AND r.review_state = 'held'
                  AND r.publish_at <= NOW() AND r.moderation_status = 'visible'
                ORDER BY r.publish_at DESC, r.id DESC LIMIT 50""",
            subject_id,
        )
        review_ids = [row["id"] for row in review_rows]
        likes = await hydrate_likes(conn, "report", review_ids, viewer_id)
        profile.reviews = [
            TellusPersonReview(
                **dict(row), like_count=likes.get(row["id"], (0, False))[0],
                liked_by_me=likes.get(row["id"], (0, False))[1],
            ) for row in review_rows
        ]
    if "followed_places" in sections:
        rows = await conn.fetch(
            """SELECT b.slug, b.name, b.logo_url, s.city, s.state
                 FROM tellus_brand_follows f JOIN tellus_brands b ON b.id = f.brand_id
                 LEFT JOIN LATERAL (SELECT city, state FROM tellus_stores
                                    WHERE brand_id = b.id ORDER BY created_at LIMIT 1) s ON TRUE
                WHERE f.consumer_account_id = $1 ORDER BY f.created_at DESC LIMIT 100""",
            subject_id,
        )
        profile.followed_places = [TellusPersonFollowedPlace(**dict(row)) for row in rows]
    if "badges" in sections:
        rows = await conn.fetch(
            """SELECT d.key, d.name, d.description, d.icon, d.sort_order, ub.awarded_at
                 FROM tellus_badge_definitions d
                 LEFT JOIN tellus_user_badges ub ON ub.badge_key = d.key AND ub.account_id = $1
                WHERE ub.awarded_at IS NOT NULL ORDER BY d.sort_order, d.key""",
            subject_id,
        )
        profile.badges = [dict(row) for row in rows]
    if "boards" in sections:
        rows = await conn.fetch(
            """SELECT b.slug AS brand_slug, b.name AS brand_name, b.logo_url,
                      m.decided_at AS joined_at
                 FROM tellus_board_memberships m
                 JOIN tellus_boards bo ON bo.id = m.board_id
                 JOIN tellus_brands b ON b.id = bo.brand_id
                WHERE m.account_id = $1 AND m.status = 'approved'
                  AND bo.is_active AND b.plan_status = 'active'
                ORDER BY m.decided_at DESC""",
            subject_id,
        )
        profile.boards = [TellusPersonBoard(**dict(row)) for row in rows]
    return profile


@router.get("/people/{account_id}", response_model=TellusPersonProfile)
async def person_profile(
    account_id: UUID,
    account: TellusAccount = Depends(require_verified_consumer),
):
    async with get_connection() as conn:
        return await _person_profile(conn, account.id, account_id)


@router.get("/people/by-handle/{handle}", response_model=TellusPersonProfile)
async def person_profile_by_handle(
    handle: str,
    account: TellusAccount = Depends(require_verified_consumer),
):
    async with get_connection() as conn:
        account_id = await conn.fetchval(
            "SELECT id FROM tellus_accounts WHERE handle = $1 AND account_type = 'consumer' AND status = 'active'",
            normalize_handle(handle),
        )
        if account_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
        return await _person_profile(conn, account.id, account_id)

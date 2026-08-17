"""Tell-Us consumer handles and profile privacy controls."""
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse

from ...core.services.redis_cache import check_rate_limit, client_ip
from ...database import get_connection
from ..dependencies import require_verified_consumer
from ..models.tellus import (
    TellusAccount,
    TellusFriendRequest,
    TellusFriendRequestCount,
    TellusFriendRequestCreate,
    TellusHandleAvailability,
    TellusHandleClaim,
    TellusPersonSummary,
)
from ..services.friends_service import (
    FRIEND_DECLINE_COOLDOWN,
    can_request,
    display_name_for,
    handle_rejection_reason,
    normalize_handle,
)
from ..services.points_service import notify_account

router = APIRouter()
HANDLE_COOLDOWN = FRIEND_DECLINE_COOLDOWN


async def _person_summary(conn, account_id: UUID, viewer_id: UUID) -> TellusPersonSummary:
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
        is_friend=bool(row["is_friend"]), pending_request_id=pending_id,
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


async def _insert_friendship(conn, first: UUID, second: UUID, source: str) -> None:
    await conn.execute(
        """INSERT INTO tellus_friendships (account_id, friend_account_id, source)
           VALUES ($1, $2, $3), ($2, $1, $3) ON CONFLICT DO NOTHING""",
        first, second, source,
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
                await _insert_friendship(conn, account.id, target_id, "request")
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
            await _insert_friendship(conn, account.id, requester_id, "request")
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

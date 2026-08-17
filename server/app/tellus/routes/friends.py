"""Tell-Us consumer handles and profile privacy controls."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ...core.services.redis_cache import check_rate_limit, client_ip
from ...database import get_connection
from ..dependencies import require_verified_consumer
from ..models.tellus import (
    TellusAccount,
    TellusHandleAvailability,
    TellusHandleClaim,
)
from ..services.friends_service import (
    FRIEND_DECLINE_COOLDOWN,
    handle_rejection_reason,
    normalize_handle,
)

router = APIRouter()
HANDLE_COOLDOWN = FRIEND_DECLINE_COOLDOWN


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

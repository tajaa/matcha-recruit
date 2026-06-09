"""Channel broadcast REST API — LiveKit-backed live video sessions.

Mounted via core_router:
  /api/channels/{channel_id}/broadcast/*   (channels router prefix)
  /api/webhooks/livekit                    (webhook router, no auth)

Limits (per channel):
- BROADCAST_MAX_DURATION_SECONDS: hard cap per stream (10 min). Enforced via
  short token TTL + async auto-stop timer + refresh-token rejection.
- BROADCAST_WEEKLY_LIMIT: max streams started per rolling 7 days (30).
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Header, Request
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import get_current_user
from ..models.auth import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()          # mounted under /channels prefix
webhook_router = APIRouter()  # mounted under /webhooks prefix

# Per-stream + per-week limits
BROADCAST_MAX_DURATION_SECONDS = 600   # 10 minutes
BROADCAST_WEEKLY_LIMIT = 30            # 30 streams / rolling 7 days
BROADCAST_TOKEN_TTL_SECONDS = BROADCAST_MAX_DURATION_SECONDS + 30  # tiny grace

# Tracks per-broadcast auto-stop tasks so a manual /stop can cancel them.
_AUTO_STOP_TASKS: dict[str, asyncio.Task] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _assert_member(conn, channel_id: UUID, user_id: UUID) -> str:
    """Return channel_member.role or raise 403/404."""
    row = await conn.fetchrow(
        """
        SELECT cm.role FROM channel_members cm
        WHERE cm.channel_id = $1 AND cm.user_id = $2
          AND cm.removed_for_inactivity IS NOT TRUE
        """,
        channel_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=403, detail="Not a member of this channel")
    return row["role"]


async def _assert_owner(conn, channel_id: UUID, user_id: UUID) -> None:
    role = await _assert_member(conn, channel_id, user_id)
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the channel owner can perform this action")


async def _active_broadcast(conn, channel_id: UUID):
    """Return the active broadcast row or None."""
    return await conn.fetchrow(
        "SELECT * FROM channel_broadcasts WHERE channel_id = $1 AND ended_at IS NULL",
        channel_id,
    )


def _livekit_room_name(channel_id: UUID) -> str:
    return f"channel-{channel_id}"


async def _push_broadcast_event(channel_id: str, event: dict) -> None:
    """Fan out a broadcast event to every channel_member with an active WS.

    Uses send_to_user (per-user) instead of _broadcast_to_room (per-channel-room
    set) because room_members on the backend is only populated when a Mac
    client sends `join_room`. Viewers who haven't loaded the channels sidebar
    aren't in room_members and would silently miss the event. This walks
    channel_members and targets every active connection for each member.
    """
    try:
        from .channels_ws import manager
        from ...database import get_connection

        try:
            ch_uuid = UUID(channel_id) if isinstance(channel_id, str) else channel_id
        except (ValueError, TypeError):
            logger.warning("invalid channel_id in broadcast push: %r", channel_id)
            return

        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id FROM channel_members
                WHERE channel_id = $1 AND removed_for_inactivity IS NOT TRUE
                """,
                ch_uuid,
            )
        member_ids = [r["user_id"] for r in rows]
        logger.info(
            "broadcast WS fan-out: type=%s channel=%s members=%d",
            event.get("type"), channel_id, len(member_ids),
        )
        for uid in member_ids:
            try:
                await manager.send_to_user(uid, event)
            except Exception:
                logger.warning("send_to_user failed for %s", uid, exc_info=True)

        # Also fan out via room set so anyone who DID join_room (but isn't a
        # channel_member, e.g. cross-tenant guests in the future) still gets it.
        try:
            await manager._broadcast_to_room(str(channel_id), event)
        except Exception:
            pass
    except Exception:
        logger.warning("Failed to push broadcast WS event", exc_info=True)


async def _weekly_broadcast_count(conn, channel_id: UUID) -> int:
    """Count broadcasts started in the past 7 days for this channel."""
    n = await conn.fetchval(
        """
        SELECT COUNT(*) FROM channel_broadcasts
        WHERE channel_id = $1
          AND started_at > NOW() - INTERVAL '7 days'
        """,
        channel_id,
    )
    return int(n or 0)


async def _force_end_broadcast(channel_id: UUID, broadcast_id: UUID, reason: str) -> None:
    """End an active broadcast: mark ended_at, delete LiveKit room, push WS event."""
    from ..services.livekit_service import delete_room

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE channel_broadcasts SET ended_at = NOW()
            WHERE id = $1 AND ended_at IS NULL
            RETURNING livekit_room
            """,
            broadcast_id,
        )

    if not row:
        return  # already ended

    try:
        await delete_room(row["livekit_room"])
    except Exception:
        logger.warning("LiveKit delete_room failed during force-end", exc_info=True)

    await _push_broadcast_event(str(channel_id), {
        "type": "broadcast.ended",
        "channel_id": str(channel_id),
        "broadcast_id": str(broadcast_id),
        "reason": reason,
    })
    logger.info("Broadcast %s force-ended (reason=%s)", broadcast_id, reason)


def _schedule_auto_stop(channel_id: UUID, broadcast_id: UUID) -> None:
    """Spawn a task that ends the broadcast after BROADCAST_MAX_DURATION_SECONDS."""
    bid = str(broadcast_id)

    async def _runner():
        try:
            await asyncio.sleep(BROADCAST_MAX_DURATION_SECONDS)
            await _force_end_broadcast(channel_id, broadcast_id, reason="time_limit")
        except asyncio.CancelledError:
            pass
        finally:
            _AUTO_STOP_TASKS.pop(bid, None)

    task = asyncio.create_task(_runner())
    _AUTO_STOP_TASKS[bid] = task


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class StartBroadcastBody(BaseModel):
    title: Optional[str] = None


class PromoteDemoteBody(BaseModel):
    user_id: UUID


class BroadcastSummary(BaseModel):
    id: str
    channel_id: str
    started_by: str
    started_at: str
    title: Optional[str]
    active: bool
    publisher_user_ids: list[str]


# ---------------------------------------------------------------------------
# POST /channels/{channel_id}/broadcast/start
# ---------------------------------------------------------------------------

@router.post("/{channel_id}/broadcast/start")
async def start_broadcast(
    channel_id: UUID,
    body: StartBroadcastBody = Body(default_factory=StartBroadcastBody),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Owner starts a live broadcast. Returns publisher token + LiveKit URL."""
    from ..services.livekit_service import mint_token, _get_lk_config
    from ...matcha.services import entitlements_service
    try:
        livekit_url, _, _ = _get_lk_config()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Go Live is a Pro/Business entitlement (LiveKit is the most expensive
    # infra feature). Watching stays free — only starting is gated.
    await entitlements_service.require_plan(current_user.id, entitlements_service.PLAN_PRO, "go_live")

    async with get_connection() as conn:
        await _assert_owner(conn, channel_id, current_user.id)

        # Enforce max 1 active broadcast per channel.
        # Recover orphans: if existing row is past the duration cap (server may
        # have restarted before the in-process auto-stop fired), close it now.
        existing = await _active_broadcast(conn, channel_id)
        if existing:
            elapsed = (datetime.now(timezone.utc) - existing["started_at"]).total_seconds()
            if elapsed > BROADCAST_MAX_DURATION_SECONDS + 30:
                await conn.execute(
                    "UPDATE channel_broadcasts SET ended_at = NOW() WHERE id = $1",
                    existing["id"],
                )
                # Best-effort: tell members the orphan ended.
                await _push_broadcast_event(str(channel_id), {
                    "type": "broadcast.ended",
                    "channel_id": str(channel_id),
                    "broadcast_id": str(existing["id"]),
                    "reason": "orphan_recovered",
                })
                existing = None

        if existing:
            raise HTTPException(status_code=409, detail="A broadcast is already active in this channel")

        # Enforce weekly limit
        weekly = await _weekly_broadcast_count(conn, channel_id)
        if weekly >= BROADCAST_WEEKLY_LIMIT:
            raise HTTPException(
                status_code=429,
                detail=f"Weekly limit reached ({BROADCAST_WEEKLY_LIMIT} broadcasts per 7 days). Try again later.",
            )

        room_name = _livekit_room_name(channel_id)
        row = await conn.fetchrow(
            """
            INSERT INTO channel_broadcasts (channel_id, started_by, livekit_room, title)
            VALUES ($1, $2, $3, $4)
            RETURNING id, started_at
            """,
            channel_id, current_user.id, room_name, body.title,
        )

    try:
        token = mint_token(
            identity=str(current_user.id),
            name=current_user.email,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            ttl_seconds=BROADCAST_TOKEN_TTL_SECONDS,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    broadcast_id = str(row["id"])
    _schedule_auto_stop(channel_id, row["id"])

    await _push_broadcast_event(str(channel_id), {
        "type": "broadcast.started",
        "channel_id": str(channel_id),
        "broadcast_id": broadcast_id,
        "started_by": str(current_user.id),
        "started_at": row["started_at"].isoformat(),
        "title": body.title,
        "max_duration_seconds": BROADCAST_MAX_DURATION_SECONDS,
    })

    return {
        "broadcast_id": broadcast_id,
        "livekit_url": livekit_url,
        "token": token,
        "room": room_name,
        "max_duration_seconds": BROADCAST_MAX_DURATION_SECONDS,
        "weekly_remaining": BROADCAST_WEEKLY_LIMIT - weekly - 1,
    }


# ---------------------------------------------------------------------------
# POST /channels/{channel_id}/broadcast/stop
# ---------------------------------------------------------------------------

@router.post("/{channel_id}/broadcast/stop")
async def stop_broadcast(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Owner ends the active broadcast."""
    from ..services.livekit_service import delete_room

    async with get_connection() as conn:
        await _assert_owner(conn, channel_id, current_user.id)

        bc = await _active_broadcast(conn, channel_id)
        if not bc:
            raise HTTPException(status_code=404, detail="No active broadcast")

        await conn.execute(
            "UPDATE channel_broadcasts SET ended_at = NOW() WHERE id = $1",
            bc["id"],
        )

    # Cancel auto-stop timer — broadcast ended manually
    task = _AUTO_STOP_TASKS.pop(str(bc["id"]), None)
    if task and not task.done():
        task.cancel()

    # Best-effort: delete LiveKit room (ignores failure — webhook handles edge cases)
    try:
        await delete_room(bc["livekit_room"])
    except Exception:
        logger.warning("LiveKit delete_room failed for %s", bc["livekit_room"], exc_info=True)

    await _push_broadcast_event(str(channel_id), {
        "type": "broadcast.ended",
        "channel_id": str(channel_id),
        "broadcast_id": str(bc["id"]),
    })
    return {"ok": True}


# ---------------------------------------------------------------------------
# GET /channels/{channel_id}/broadcast/token  — viewer token
# ---------------------------------------------------------------------------

@router.get("/{channel_id}/broadcast/token")
async def get_viewer_token(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return a subscriber-only token for any channel member."""
    from ..services.livekit_service import mint_token, _get_lk_config
    try:
        livekit_url, _, _ = _get_lk_config()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    async with get_connection() as conn:
        await _assert_member(conn, channel_id, current_user.id)

        bc = await _active_broadcast(conn, channel_id)
        if not bc:
            raise HTTPException(status_code=404, detail="No active broadcast")

    # Token TTL must match the per-stream cap; tokens past cap auto-disconnect.
    elapsed = (datetime.now(timezone.utc) - bc["started_at"]).total_seconds()
    remaining = max(60, BROADCAST_TOKEN_TTL_SECONDS - int(elapsed))

    try:
        token = mint_token(
            identity=str(current_user.id),
            name=current_user.email,
            room=bc["livekit_room"],
            can_publish=False,
            can_subscribe=True,
            ttl_seconds=remaining,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return {
        "livekit_url": livekit_url,
        "token": token,
        "room": bc["livekit_room"],
        "max_duration_seconds": BROADCAST_MAX_DURATION_SECONDS,
        "elapsed_seconds": int(elapsed),
    }


# ---------------------------------------------------------------------------
# POST /channels/{channel_id}/broadcast/refresh-token
# ---------------------------------------------------------------------------

@router.post("/{channel_id}/broadcast/refresh-token")
async def refresh_broadcast_token(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Re-mint the caller's token. Capped at the broadcast's remaining duration —
    cannot extend a broadcast past BROADCAST_MAX_DURATION_SECONDS.
    """
    from ..services.livekit_service import mint_token, list_participant_identities, _get_lk_config
    try:
        livekit_url, _, _ = _get_lk_config()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    async with get_connection() as conn:
        await _assert_member(conn, channel_id, current_user.id)
        bc = await _active_broadcast(conn, channel_id)
        if not bc:
            raise HTTPException(status_code=404, detail="No active broadcast")

    elapsed = (datetime.now(timezone.utc) - bc["started_at"]).total_seconds()
    if elapsed >= BROADCAST_MAX_DURATION_SECONDS:
        raise HTTPException(status_code=410, detail="Broadcast time limit reached")
    remaining = max(30, BROADCAST_MAX_DURATION_SECONDS - int(elapsed))

    identity = str(current_user.id)
    try:
        publishers = await list_participant_identities(bc["livekit_room"])
        can_publish = identity in publishers and str(bc["started_by"]) == identity
    except Exception:
        can_publish = str(bc["started_by"]) == identity

    try:
        token = mint_token(
            identity=identity,
            name=current_user.email,
            room=bc["livekit_room"],
            can_publish=can_publish,
            can_subscribe=True,
            ttl_seconds=remaining,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return {
        "livekit_url": livekit_url,
        "token": token,
        "room": bc["livekit_room"],
        "max_duration_seconds": BROADCAST_MAX_DURATION_SECONDS,
        "elapsed_seconds": int(elapsed),
    }


# ---------------------------------------------------------------------------
# POST /channels/{channel_id}/broadcast/promote
# ---------------------------------------------------------------------------

@router.post("/{channel_id}/broadcast/promote")
async def promote_publisher(
    channel_id: UUID,
    body: PromoteDemoteBody,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Owner promotes an existing channel member to on-stage publisher."""
    from ..services.livekit_service import mint_token, update_participant_can_publish, _get_lk_config
    try:
        livekit_url, _, _ = _get_lk_config()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    async with get_connection() as conn:
        await _assert_owner(conn, channel_id, current_user.id)
        bc = await _active_broadcast(conn, channel_id)
        if not bc:
            raise HTTPException(status_code=404, detail="No active broadcast")

        # Guest must be a channel member
        await _assert_member(conn, channel_id, body.user_id)

        # Resolve display name for the token
        name_row = await conn.fetchrow(
            """
            SELECT COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
            FROM users u
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE u.id = $1
            """,
            body.user_id,
        )
        guest_name = name_row["name"] if name_row else str(body.user_id)

    identity = str(body.user_id)

    # Update live grants on already-connected participant (best-effort)
    try:
        await update_participant_can_publish(bc["livekit_room"], identity, can_publish=True)
    except Exception:
        logger.warning("update_participant_can_publish failed", exc_info=True)

    elapsed = (datetime.now(timezone.utc) - bc["started_at"]).total_seconds()
    remaining = max(30, BROADCAST_MAX_DURATION_SECONDS - int(elapsed))
    try:
        token = mint_token(
            identity=identity,
            name=guest_name,
            room=bc["livekit_room"],
            can_publish=True,
            can_subscribe=True,
            ttl_seconds=remaining,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Push token to the specific user (per-user envelope) + broadcast role change
    try:
        from .channels_ws import manager
        await manager.send_to_user(body.user_id, {
            "type": "broadcast.token_grant",
            "channel_id": str(channel_id),
            "token": token,
            "livekit_url": livekit_url,
            "can_publish": True,
        })
    except Exception:
        logger.warning("Failed to push token_grant to user", exc_info=True)

    await _push_broadcast_event(str(channel_id), {
        "type": "broadcast.publisher_changed",
        "channel_id": str(channel_id),
        "user_id": str(body.user_id),
        "can_publish": True,
    })

    return {"ok": True, "token": token, "livekit_url": livekit_url}


# ---------------------------------------------------------------------------
# POST /channels/{channel_id}/broadcast/demote
# ---------------------------------------------------------------------------

@router.post("/{channel_id}/broadcast/demote")
async def demote_publisher(
    channel_id: UUID,
    body: PromoteDemoteBody,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Owner removes a guest from the stage (back to viewer)."""
    from ..services.livekit_service import mint_token, update_participant_can_publish, _get_lk_config
    try:
        livekit_url, _, _ = _get_lk_config()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    async with get_connection() as conn:
        await _assert_owner(conn, channel_id, current_user.id)
        bc = await _active_broadcast(conn, channel_id)
        if not bc:
            raise HTTPException(status_code=404, detail="No active broadcast")

        name_row = await conn.fetchrow(
            """
            SELECT COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
            FROM users u
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE u.id = $1
            """,
            body.user_id,
        )
        guest_name = name_row["name"] if name_row else str(body.user_id)

    identity = str(body.user_id)

    # Force-unpublish via RoomService (token revocation alone doesn't stop active tracks)
    try:
        await update_participant_can_publish(bc["livekit_room"], identity, can_publish=False)
    except Exception:
        logger.warning("update_participant_can_publish(False) failed", exc_info=True)

    elapsed_d = (datetime.now(timezone.utc) - bc["started_at"]).total_seconds()
    remaining_d = max(30, BROADCAST_MAX_DURATION_SECONDS - int(elapsed_d))
    try:
        token = mint_token(
            identity=identity,
            name=guest_name,
            room=bc["livekit_room"],
            can_publish=False,
            can_subscribe=True,
            ttl_seconds=remaining_d,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    try:
        from .channels_ws import manager
        await manager.send_to_user(body.user_id, {
            "type": "broadcast.token_grant",
            "channel_id": str(channel_id),
            "token": token,
            "livekit_url": livekit_url,
            "can_publish": False,
        })
    except Exception:
        logger.warning("Failed to push token_grant (demote) to user", exc_info=True)

    await _push_broadcast_event(str(channel_id), {
        "type": "broadcast.publisher_changed",
        "channel_id": str(channel_id),
        "user_id": str(body.user_id),
        "can_publish": False,
    })

    return {"ok": True}


# ---------------------------------------------------------------------------
# GET /channels/{channel_id}/broadcast  — status
# ---------------------------------------------------------------------------

@router.get("/{channel_id}/broadcast")
async def get_broadcast_status(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return current broadcast state for the channel sidebar badge."""
    async with get_connection() as conn:
        await _assert_member(conn, channel_id, current_user.id)
        bc = await _active_broadcast(conn, channel_id)
        weekly = await _weekly_broadcast_count(conn, channel_id)

    base_limits = {
        "max_duration_seconds": BROADCAST_MAX_DURATION_SECONDS,
        "weekly_limit": BROADCAST_WEEKLY_LIMIT,
        "weekly_used": weekly,
        "weekly_remaining": max(0, BROADCAST_WEEKLY_LIMIT - weekly),
    }

    if not bc:
        return {"active": False, **base_limits}

    publisher_ids: list[str] = []
    try:
        from ..services.livekit_service import list_participant_identities
        publisher_ids = await list_participant_identities(bc["livekit_room"])
    except Exception:
        publisher_ids = [str(bc["started_by"])]

    elapsed = (datetime.now(timezone.utc) - bc["started_at"]).total_seconds()

    return {
        "active": True,
        "broadcast_id": str(bc["id"]),
        "started_at": bc["started_at"].isoformat(),
        "started_by": str(bc["started_by"]),
        "title": bc["title"],
        "publisher_user_ids": publisher_ids,
        "elapsed_seconds": int(elapsed),
        **base_limits,
    }


# ---------------------------------------------------------------------------
# POST /webhooks/livekit  — LiveKit server → backend lifecycle events
# ---------------------------------------------------------------------------

@webhook_router.post("/livekit")
async def livekit_webhook(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Receive LiveKit server webhooks. Verifies signature with LIVEKIT_API_SECRET."""
    body = await request.body()

    try:
        from ..services.livekit_service import receive_webhook
        event = receive_webhook(body, authorization or "")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        # WebhookReceiver raises jwt.DecodeError on bad signature; treat any
        # decode/verification failure as 400 so we don't leak details.
        logger.warning("LiveKit webhook signature verification failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event.get("event", "")
    room_info = event.get("room", {})
    room_name: str = room_info.get("name", "")

    if not room_name.startswith("channel-"):
        return {"ok": True}  # not our room

    channel_id_str = room_name.removeprefix("channel-")
    try:
        channel_id = UUID(channel_id_str)
    except ValueError:
        return {"ok": True}

    if event_type == "room_finished":
        async with get_connection() as conn:
            row = await conn.fetchrow(
                "UPDATE channel_broadcasts SET ended_at = NOW() WHERE channel_id = $1 AND ended_at IS NULL RETURNING id",
                channel_id,
            )
        if row:
            # Cancel auto-stop task if still pending
            task = _AUTO_STOP_TASKS.pop(str(row["id"]), None)
            if task and not task.done():
                task.cancel()
            await _push_broadcast_event(str(channel_id), {
                "type": "broadcast.ended",
                "channel_id": str(channel_id),
                "broadcast_id": str(row["id"]),
            })
            logger.info("Broadcast ended via LiveKit room_finished webhook: channel=%s", channel_id)

    return {"ok": True}

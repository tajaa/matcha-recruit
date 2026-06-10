"""Channel audio-call REST API — LiveKit-backed 4-person call sessions.

Mounted via core_router under the /channels prefix:
  /api/channels/{channel_id}/call/*

A call is a small-group audio room (everyone publishes mic, nothing else —
enforced server-side via the canPublishSources grant). The channel owner
starts it and picks the join policy:
  - invite_only: only users with a channel_call_invites row may join
  - members:     any channel member may join until the room is full

Capacity: CALL_MAX_PARTICIPANTS, enforced authoritatively by LiveKit
(create_room max_participants) plus a friendly count check at token mint.
Lifecycle: ends when the owner stops it, when the room sits empty for
CALL_EMPTY_TIMEOUT_SECONDS (room_finished webhook), or at the 4h orphan cap.

Calls and broadcasts are mutually exclusive per channel — one live audio
surface at a time (and one mic device on the client).
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from ...database import get_connection
from ..dependencies import get_current_user
from ..models.auth import CurrentUser
from .channel_broadcasts import _active_broadcast, _assert_member, _assert_owner

logger = logging.getLogger(__name__)

router = APIRouter()  # mounted under /channels prefix

CALL_MAX_PARTICIPANTS = 4
CALL_MAX_DURATION_SECONDS = 14_400          # 4h — orphan insurance, not a UX cap
CALL_EMPTY_TIMEOUT_SECONDS = 120            # empty room -> room_finished webhook
CALL_TOKEN_TTL_SECONDS = CALL_MAX_DURATION_SECONDS + 30

# Tracks per-call auto-stop tasks so a manual /stop can cancel them.
_AUTO_STOP_TASKS: dict[str, asyncio.Task] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _active_call(conn, channel_id: UUID):
    """Return the active call row or None."""
    return await conn.fetchrow(
        "SELECT * FROM channel_calls WHERE channel_id = $1 AND ended_at IS NULL",
        channel_id,
    )


def _call_room_name(channel_id: UUID) -> str:
    # Distinct prefix from broadcasts' "channel-{id}" so the shared LiveKit
    # webhook can route by room name.
    return f"call-{channel_id}"


async def _display_name(conn, user_id: UUID) -> str:
    row = await conn.fetchrow(
        """
        SELECT COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
        FROM users u
        LEFT JOIN clients c ON c.user_id = u.id
        LEFT JOIN employees e ON e.user_id = u.id
        LEFT JOIN admins a ON a.user_id = u.id
        WHERE u.id = $1
        """,
        user_id,
    )
    return row["name"] if row else str(user_id)


async def _push_call_event(channel_id: str, event: dict) -> None:
    """Fan out a call event to every channel_member with an active WS.

    Same per-user fan-out rationale as _push_broadcast_event: room_members is
    only populated on join_room, so members who haven't opened the channel
    would miss room-targeted events.
    """
    try:
        from .channels_ws import manager

        try:
            ch_uuid = UUID(channel_id) if isinstance(channel_id, str) else channel_id
        except (ValueError, TypeError):
            logger.warning("invalid channel_id in call push: %r", channel_id)
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
            "call WS fan-out: type=%s channel=%s members=%d",
            event.get("type"), channel_id, len(member_ids),
        )
        for uid in member_ids:
            try:
                await manager.send_to_user(uid, event)
            except Exception:
                logger.warning("send_to_user failed for %s", uid, exc_info=True)

        try:
            await manager._broadcast_to_room(str(channel_id), event)
        except Exception:
            pass
    except Exception:
        logger.warning("Failed to push call WS event", exc_info=True)


async def _notify_invitees(channel_id: UUID, call_id: UUID, invited_by: UUID, user_ids: list[UUID]) -> None:
    """Targeted call.invited pings (not a channel-wide fan-out)."""
    try:
        from .channels_ws import manager
    except Exception:
        return
    for uid in user_ids:
        try:
            await manager.send_to_user(uid, {
                "type": "call.invited",
                "channel_id": str(channel_id),
                "call_id": str(call_id),
                "invited_by": str(invited_by),
            })
        except Exception:
            logger.warning("Failed to push call.invited to %s", uid, exc_info=True)


async def _force_end_call(channel_id: UUID, call_id: UUID, reason: str) -> None:
    """End an active call: mark ended_at, delete LiveKit room, push WS event."""
    from ..services.livekit_service import delete_room

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE channel_calls SET ended_at = NOW()
            WHERE id = $1 AND ended_at IS NULL
            RETURNING livekit_room
            """,
            call_id,
        )

    if not row:
        return  # already ended

    try:
        await delete_room(row["livekit_room"])
    except Exception:
        logger.warning("LiveKit delete_room failed during call force-end", exc_info=True)

    await _push_call_event(str(channel_id), {
        "type": "call.ended",
        "channel_id": str(channel_id),
        "call_id": str(call_id),
        "reason": reason,
    })
    logger.info("Call %s force-ended (reason=%s)", call_id, reason)


def _schedule_auto_stop(channel_id: UUID, call_id: UUID) -> None:
    """Spawn a task that ends the call after CALL_MAX_DURATION_SECONDS."""
    cid = str(call_id)

    async def _runner():
        try:
            await asyncio.sleep(CALL_MAX_DURATION_SECONDS)
            await _force_end_call(channel_id, call_id, reason="time_limit")
        except asyncio.CancelledError:
            pass
        finally:
            _AUTO_STOP_TASKS.pop(cid, None)

    task = asyncio.create_task(_runner())
    _AUTO_STOP_TASKS[cid] = task


def _cancel_auto_stop(call_id) -> None:
    task = _AUTO_STOP_TASKS.pop(str(call_id), None)
    if task and not task.done():
        task.cancel()


async def _member_filtered(conn, channel_id: UUID, user_ids: list[UUID]) -> list[UUID]:
    """Return the subset of user_ids who are active members of the channel."""
    if not user_ids:
        return []
    rows = await conn.fetch(
        """
        SELECT user_id FROM channel_members
        WHERE channel_id = $1 AND user_id = ANY($2::uuid[])
          AND removed_for_inactivity IS NOT TRUE
        """,
        channel_id, user_ids,
    )
    return [r["user_id"] for r in rows]


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class StartCallBody(BaseModel):
    mode: Literal["invite_only", "members"]
    invited_user_ids: list[UUID] = Field(default_factory=list)


class InviteBody(BaseModel):
    user_ids: list[UUID]


# ---------------------------------------------------------------------------
# POST /channels/{channel_id}/call/start
# ---------------------------------------------------------------------------

@router.post("/{channel_id}/call/start")
async def start_call(
    channel_id: UUID,
    body: StartCallBody,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Owner starts a call session. Returns a publisher token + LiveKit URL."""
    from ..services.livekit_service import create_room, mint_token, _get_lk_config
    from ...matcha.services import entitlements_service
    try:
        livekit_url, _, _ = _get_lk_config()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Same Pro/Business gate as Go Live — starting is gated, joining is free.
    await entitlements_service.require_plan(current_user.id, entitlements_service.PLAN_PRO, "go_live")

    async with get_connection() as conn:
        await _assert_owner(conn, channel_id, current_user.id)

        # Recover orphans past the duration cap (server may have restarted
        # before the in-process auto-stop fired).
        existing = await _active_call(conn, channel_id)
        if existing:
            elapsed = (datetime.now(timezone.utc) - existing["started_at"]).total_seconds()
            if elapsed > CALL_MAX_DURATION_SECONDS + 30:
                await conn.execute(
                    "UPDATE channel_calls SET ended_at = NOW() WHERE id = $1",
                    existing["id"],
                )
                await _push_call_event(str(channel_id), {
                    "type": "call.ended",
                    "channel_id": str(channel_id),
                    "call_id": str(existing["id"]),
                    "reason": "orphan_recovered",
                })
                existing = None

        if existing:
            raise HTTPException(status_code=409, detail="A call is already active in this channel")

        # One live audio surface per channel: calls and broadcasts are
        # mutually exclusive (also one mic device on the client).
        if await _active_broadcast(conn, channel_id):
            raise HTTPException(status_code=409, detail="A broadcast is active in this channel — end it first")

        invitees = await _member_filtered(conn, channel_id, body.invited_user_ids)

        room_name = _call_room_name(channel_id)
        row = await conn.fetchrow(
            """
            INSERT INTO channel_calls (channel_id, started_by, mode, livekit_room)
            VALUES ($1, $2, $3, $4)
            RETURNING id, started_at
            """,
            channel_id, current_user.id, body.mode, room_name,
        )
        if invitees:
            await conn.executemany(
                """
                INSERT INTO channel_call_invites (call_id, user_id, invited_by)
                VALUES ($1, $2, $3)
                ON CONFLICT (call_id, user_id) DO NOTHING
                """,
                [(row["id"], uid, current_user.id) for uid in invitees],
            )

    # Best-effort: explicit room creation carries the authoritative caps.
    # On failure the room still auto-creates at join — we just lose the
    # SFU-side max_participants backstop (the count check below remains).
    try:
        await create_room(
            room_name,
            max_participants=CALL_MAX_PARTICIPANTS,
            empty_timeout_seconds=CALL_EMPTY_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.warning("LiveKit create_room failed for %s", room_name, exc_info=True)

    try:
        token = mint_token(
            identity=str(current_user.id),
            name=current_user.email,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            ttl_seconds=CALL_TOKEN_TTL_SECONDS,
            can_publish_sources=["microphone"],
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    call_id = row["id"]
    _schedule_auto_stop(channel_id, call_id)

    await _push_call_event(str(channel_id), {
        "type": "call.started",
        "channel_id": str(channel_id),
        "call_id": str(call_id),
        "started_by": str(current_user.id),
        "started_at": row["started_at"].isoformat(),
        "mode": body.mode,
        "max_participants": CALL_MAX_PARTICIPANTS,
    })
    await _notify_invitees(channel_id, call_id, current_user.id, invitees)

    return {
        "call_id": str(call_id),
        "livekit_url": livekit_url,
        "token": token,
        "room": room_name,
        "mode": body.mode,
        "max_participants": CALL_MAX_PARTICIPANTS,
        "max_duration_seconds": CALL_MAX_DURATION_SECONDS,
    }


# ---------------------------------------------------------------------------
# GET /channels/{channel_id}/call/token  — join
# ---------------------------------------------------------------------------

@router.get("/{channel_id}/call/token")
async def get_call_token(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Mint a join token for the active call, subject to the join policy."""
    from ..services.livekit_service import mint_token, list_participant_identities, _get_lk_config
    try:
        livekit_url, _, _ = _get_lk_config()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    async with get_connection() as conn:
        await _assert_member(conn, channel_id, current_user.id)

        call = await _active_call(conn, channel_id)
        if not call:
            raise HTTPException(status_code=404, detail="No active call")

        if call["mode"] == "invite_only" and call["started_by"] != current_user.id:
            invited = await conn.fetchval(
                "SELECT 1 FROM channel_call_invites WHERE call_id = $1 AND user_id = $2",
                call["id"], current_user.id,
            )
            if not invited:
                raise HTTPException(status_code=403, detail="You haven't been invited to this call")

        display_name = await _display_name(conn, current_user.id)

    identity = str(current_user.id)
    # Friendly capacity check; LiveKit's max_participants is the hard backstop,
    # so a failure to count (or a join race) cannot overfill the room.
    try:
        identities = await list_participant_identities(call["livekit_room"])
        if identity not in identities and len(identities) >= CALL_MAX_PARTICIPANTS:
            raise HTTPException(
                status_code=409,
                detail=f"Call is full ({CALL_MAX_PARTICIPANTS}/{CALL_MAX_PARTICIPANTS})",
            )
    except HTTPException:
        raise
    except Exception:
        logger.warning("list_participant_identities failed for %s", call["livekit_room"], exc_info=True)

    elapsed = (datetime.now(timezone.utc) - call["started_at"]).total_seconds()
    remaining = max(60, CALL_TOKEN_TTL_SECONDS - int(elapsed))

    try:
        token = mint_token(
            identity=identity,
            name=display_name,
            room=call["livekit_room"],
            can_publish=True,
            can_subscribe=True,
            ttl_seconds=remaining,
            can_publish_sources=["microphone"],
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return {
        "livekit_url": livekit_url,
        "token": token,
        "room": call["livekit_room"],
        "mode": call["mode"],
        "elapsed_seconds": int(elapsed),
        "max_participants": CALL_MAX_PARTICIPANTS,
    }


# ---------------------------------------------------------------------------
# POST /channels/{channel_id}/call/invite
# ---------------------------------------------------------------------------

@router.post("/{channel_id}/call/invite")
async def invite_to_call(
    channel_id: UUID,
    body: InviteBody,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Owner invites channel members mid-call. In 'members' mode it's a ping;
    in 'invite_only' mode it also grants join permission."""
    async with get_connection() as conn:
        await _assert_owner(conn, channel_id, current_user.id)

        call = await _active_call(conn, channel_id)
        if not call:
            raise HTTPException(status_code=404, detail="No active call")

        invitees = await _member_filtered(conn, channel_id, body.user_ids)
        if invitees:
            await conn.executemany(
                """
                INSERT INTO channel_call_invites (call_id, user_id, invited_by)
                VALUES ($1, $2, $3)
                ON CONFLICT (call_id, user_id) DO NOTHING
                """,
                [(call["id"], uid, current_user.id) for uid in invitees],
            )

    await _notify_invitees(channel_id, call["id"], current_user.id, invitees)
    return {"ok": True, "invited": [str(u) for u in invitees]}


# ---------------------------------------------------------------------------
# POST /channels/{channel_id}/call/stop
# ---------------------------------------------------------------------------

@router.post("/{channel_id}/call/stop")
async def stop_call(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Owner ends the active call."""
    from ..services.livekit_service import delete_room

    async with get_connection() as conn:
        await _assert_owner(conn, channel_id, current_user.id)

        call = await _active_call(conn, channel_id)
        if not call:
            raise HTTPException(status_code=404, detail="No active call")

        await conn.execute(
            "UPDATE channel_calls SET ended_at = NOW() WHERE id = $1",
            call["id"],
        )

    _cancel_auto_stop(call["id"])

    try:
        await delete_room(call["livekit_room"])
    except Exception:
        logger.warning("LiveKit delete_room failed for %s", call["livekit_room"], exc_info=True)

    await _push_call_event(str(channel_id), {
        "type": "call.ended",
        "channel_id": str(channel_id),
        "call_id": str(call["id"]),
    })
    return {"ok": True}


# ---------------------------------------------------------------------------
# GET /channels/{channel_id}/call  — status
# ---------------------------------------------------------------------------

@router.get("/{channel_id}/call")
async def get_call_status(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Current call state for the channel header chip / join banner."""
    async with get_connection() as conn:
        await _assert_member(conn, channel_id, current_user.id)
        call = await _active_call(conn, channel_id)
        if not call:
            return {"active": False, "max_participants": CALL_MAX_PARTICIPANTS}
        invite_rows = await conn.fetch(
            "SELECT user_id FROM channel_call_invites WHERE call_id = $1",
            call["id"],
        )

    participant_ids: list[str] = []
    try:
        from ..services.livekit_service import list_participant_identities
        participant_ids = await list_participant_identities(call["livekit_room"])
    except Exception:
        participant_ids = [str(call["started_by"])]

    elapsed = (datetime.now(timezone.utc) - call["started_at"]).total_seconds()

    return {
        "active": True,
        "call_id": str(call["id"]),
        "mode": call["mode"],
        "started_by": str(call["started_by"]),
        "started_at": call["started_at"].isoformat(),
        "elapsed_seconds": int(elapsed),
        "participant_ids": participant_ids,
        "invited_user_ids": [str(r["user_id"]) for r in invite_rows],
        "max_participants": CALL_MAX_PARTICIPANTS,
    }


# ---------------------------------------------------------------------------
# LiveKit webhook events for call- rooms (dispatched from channel_broadcasts)
# ---------------------------------------------------------------------------

async def handle_call_webhook_event(event_type: str, event: dict, room_name: str) -> dict:
    """Handle LiveKit webhooks for rooms named call-{channel_id}.

    room_finished closes the call row (the everyone-left path, after
    empty_timeout). participant_joined/left fan out live occupancy so members
    who haven't joined see the n/4 count update.
    """
    channel_id_str = room_name.removeprefix("call-")
    try:
        channel_id = UUID(channel_id_str)
    except ValueError:
        return {"ok": True}

    if event_type == "room_finished":
        async with get_connection() as conn:
            row = await conn.fetchrow(
                "UPDATE channel_calls SET ended_at = NOW() WHERE channel_id = $1 AND ended_at IS NULL RETURNING id",
                channel_id,
            )
        if row:
            _cancel_auto_stop(row["id"])
            await _push_call_event(str(channel_id), {
                "type": "call.ended",
                "channel_id": str(channel_id),
                "call_id": str(row["id"]),
            })
            logger.info("Call ended via LiveKit room_finished webhook: channel=%s", channel_id)
        return {"ok": True}

    if event_type in ("participant_joined", "participant_left"):
        async with get_connection() as conn:
            call = await _active_call(conn, channel_id)
        if not call:
            return {"ok": True}

        participant_ids: list[str] = []
        try:
            from ..services.livekit_service import list_participant_identities
            participant_ids = await list_participant_identities(room_name)
        except Exception:
            # Fall back to the event's own participant as a coarse signal.
            ident = (event.get("participant") or {}).get("identity")
            participant_ids = [ident] if ident else []

        await _push_call_event(str(channel_id), {
            "type": "call.participants_changed",
            "channel_id": str(channel_id),
            "call_id": str(call["id"]),
            "participant_ids": participant_ids,
            "count": len(participant_ids),
            "max_participants": CALL_MAX_PARTICIPANTS,
        })

    return {"ok": True}

"""Voice call signaling for WebRTC peer-to-peer audio calls in channels."""

import asyncio
import logging
from typing import Dict, List, Set
from uuid import UUID

logger = logging.getLogger(__name__)

# In-memory state for active calls, guarded by _lock
active_calls: Dict[str, Set[UUID]] = {}  # channel_id -> set of user_ids in call
_lock = asyncio.Lock()
MAX_CALL_PARTICIPANTS = 4


async def handle_voice_join(manager, user_id: UUID, user_name: str, room_key: str, channel_id: str):
    """User joins/starts a voice call. Validates membership, enforces limit."""
    # Verify user is a member of the channel room
    async with manager.lock:
        if room_key not in manager.room_members or user_id not in manager.room_members[room_key]:
            await manager.send_to_user(user_id, {
                "type": "voice_error",
                "message": "You must be a channel member to join voice calls",
            })
            return

    async with _lock:
        if channel_id in active_calls and len(active_calls[channel_id]) >= MAX_CALL_PARTICIPANTS:
            await manager.send_to_user(user_id, {
                "type": "voice_error",
                "message": f"Call is full (max {MAX_CALL_PARTICIPANTS} participants)",
                "channel_id": channel_id,
            })
            return

        if channel_id not in active_calls:
            active_calls[channel_id] = set()

        # Build participant list BEFORE adding the joiner
        participants = []
        for uid in active_calls[channel_id]:
            if uid != user_id:
                async with manager.lock:
                    u = manager.users.get(uid)
                participants.append({"user_id": str(uid), "user_name": u.name if u else "Unknown"})

        active_calls[channel_id].add(user_id)

    # Send current participant list to the joiner
    await manager.send_to_user(user_id, {
        "type": "voice_participants",
        "channel_id": channel_id,
        "participants": participants,
    })

    # Broadcast to room that this user joined the call
    await manager._broadcast_to_room(room_key, {
        "type": "voice_user_joined",
        "channel_id": channel_id,
        "user_id": str(user_id),
        "user_name": user_name,
    }, exclude_user=user_id)

    logger.info("[Voice] User %s joined call in channel %s", user_id, channel_id)


async def handle_voice_leave(manager, user_id: UUID, user_name: str, room_key: str, channel_id: str):
    """User leaves voice call. Broadcasts departure. Cleans up if empty."""
    async with _lock:
        if channel_id not in active_calls:
            return
        active_calls[channel_id].discard(user_id)
        remaining = len(active_calls[channel_id])
        if not active_calls[channel_id]:
            del active_calls[channel_id]

    await manager._broadcast_to_room(room_key, {
        "type": "voice_user_left",
        "channel_id": channel_id,
        "user_id": str(user_id),
        "user_name": user_name,
    }, exclude_user=user_id)

    logger.info("[Voice] User %s left call in channel %s (%d remaining)", user_id, channel_id, remaining)


async def handle_voice_offer(manager, user_id: UUID, data: dict):
    """Relay SDP offer to target user. Validates target is in the same call."""
    target_user_id = data.get("target_user_id")
    sdp = data.get("sdp")
    if not target_user_id or not sdp:
        return

    try:
        target_uid = UUID(target_user_id)
    except (ValueError, TypeError):
        return

    # Verify both users are in the same call
    async with _lock:
        in_same_call = any(
            user_id in participants and target_uid in participants
            for participants in active_calls.values()
        )
    if not in_same_call:
        return

    await manager.send_to_user(target_uid, {
        "type": "voice_offer",
        "from_user_id": str(user_id),
        "sdp": sdp,
    })


async def handle_voice_answer(manager, user_id: UUID, data: dict):
    """Relay SDP answer to target user."""
    target_user_id = data.get("target_user_id")
    sdp = data.get("sdp")
    if not target_user_id or not sdp:
        return

    try:
        target_uid = UUID(target_user_id)
    except (ValueError, TypeError):
        return

    async with _lock:
        in_same_call = any(
            user_id in participants and target_uid in participants
            for participants in active_calls.values()
        )
    if not in_same_call:
        return

    await manager.send_to_user(target_uid, {
        "type": "voice_answer",
        "from_user_id": str(user_id),
        "sdp": sdp,
    })


async def handle_voice_ice(manager, user_id: UUID, data: dict):
    """Relay ICE candidate to target user."""
    target_user_id = data.get("target_user_id")
    candidate = data.get("candidate")
    if not target_user_id or candidate is None:
        return

    try:
        target_uid = UUID(target_user_id)
    except (ValueError, TypeError):
        return

    # No call membership check for ICE — candidates can arrive during setup
    await manager.send_to_user(target_uid, {
        "type": "voice_ice",
        "from_user_id": str(user_id),
        "candidate": candidate,
    })


async def cleanup_user_from_calls(user_id: UUID) -> List[str]:
    """Remove user from all active calls. Returns channel_ids affected."""
    affected = []
    async with _lock:
        empty = []
        for channel_id, participants in active_calls.items():
            if user_id in participants:
                participants.discard(user_id)
                affected.append(channel_id)
                if not participants:
                    empty.append(channel_id)
        for channel_id in empty:
            del active_calls[channel_id]
    return affected

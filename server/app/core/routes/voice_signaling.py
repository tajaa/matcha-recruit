"""Voice call signaling for WebRTC peer-to-peer audio calls in channels."""

import logging
from typing import Dict, List, Set
from uuid import UUID

logger = logging.getLogger(__name__)

# In-memory state for active calls
active_calls: Dict[str, Set[UUID]] = {}  # channel_id -> set of user_ids in call
MAX_CALL_PARTICIPANTS = 4


async def handle_voice_join(manager, user_id: UUID, user_name: str, room_key: str, channel_id: str):
    """User joins/starts a voice call. Broadcasts to room, sends participant list to joiner."""
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
    participants = [
        {"user_id": str(uid), "user_name": manager.users[uid].name}
        for uid in active_calls[channel_id]
        if uid != user_id and uid in manager.users
    ]

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

    logger.info(f"[Voice] User {user_id} joined call in channel {channel_id} ({len(active_calls[channel_id])} participants)")


async def handle_voice_leave(manager, user_id: UUID, user_name: str, room_key: str, channel_id: str):
    """User leaves voice call. Broadcasts departure. Cleans up if empty."""
    if channel_id not in active_calls:
        return

    active_calls[channel_id].discard(user_id)

    # Broadcast departure to room
    await manager._broadcast_to_room(room_key, {
        "type": "voice_user_left",
        "channel_id": channel_id,
        "user_id": str(user_id),
        "user_name": user_name,
    }, exclude_user=user_id)

    # Clean up empty calls
    if not active_calls[channel_id]:
        del active_calls[channel_id]
        logger.info(f"[Voice] Call ended in channel {channel_id} (no participants)")
    else:
        logger.info(f"[Voice] User {user_id} left call in channel {channel_id} ({len(active_calls[channel_id])} remaining)")


async def handle_voice_offer(manager, user_id: UUID, data: dict):
    """Relay SDP offer to target user."""
    target_user_id = data.get("target_user_id")
    sdp = data.get("sdp")
    if not target_user_id or not sdp:
        return

    try:
        target_uid = UUID(target_user_id)
    except (ValueError, TypeError):
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

    await manager.send_to_user(target_uid, {
        "type": "voice_ice",
        "from_user_id": str(user_id),
        "candidate": candidate,
    })


def cleanup_user_from_calls(user_id: UUID) -> List[str]:
    """Remove user from all active calls (called on disconnect). Returns channel_ids affected."""
    affected = []
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

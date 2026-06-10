"""LiveKit server integration — token minting, room management, webhook verification.

All public functions check that LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET
are configured and raise RuntimeError when they are not (callers convert to 503).
"""

import logging
from datetime import timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def _get_lk_config():
    """Return (url, api_key, api_secret) or raise RuntimeError if not configured."""
    from ...config import get_settings
    s = get_settings()
    url = getattr(s, "livekit_url", None)
    key = getattr(s, "livekit_api_key", None)
    secret = getattr(s, "livekit_api_secret", None)
    if not (url and key and secret):
        raise RuntimeError("LiveKit not configured (LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET missing)")
    return url, key, secret


# ---------------------------------------------------------------------------
# Token minting (synchronous — no I/O)
# ---------------------------------------------------------------------------

def mint_token(
    *,
    identity: str,
    name: str,
    room: str,
    can_publish: bool,
    can_subscribe: bool,
    ttl_seconds: int = 3600,
    can_publish_sources: Optional[list[str]] = None,
) -> str:
    """Mint a LiveKit JWT for one participant. Returns the JWT string.

    can_publish_sources (e.g. ["microphone"]) supersedes can_publish when set —
    used by audio-only calls to reject camera/screenshare server-side.
    """
    try:
        from livekit.api import AccessToken, VideoGrants
    except ImportError as e:
        raise RuntimeError(f"livekit-api package not installed: {e}")

    _, api_key, api_secret = _get_lk_config()

    grants = VideoGrants(
        room_join=True,
        room=room,
        can_publish=can_publish,
        can_subscribe=can_subscribe,
    )
    if can_publish_sources is not None:
        grants.can_publish_sources = can_publish_sources

    token = (
        AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_name(name)
        .with_grants(grants)
        .with_ttl(timedelta(seconds=ttl_seconds))
        .to_jwt()
    )
    return token


# ---------------------------------------------------------------------------
# Room / participant management (async — HTTP calls to LiveKit server)
# ---------------------------------------------------------------------------

async def create_room(
    room_name: str,
    *,
    max_participants: int = 0,
    empty_timeout_seconds: int = 0,
) -> None:
    """Create a LiveKit room explicitly (rooms otherwise auto-create on join).

    max_participants is the authoritative capacity cap enforced by the SFU;
    empty_timeout closes the room (-> room_finished webhook) after it sits
    empty that long. 0 = LiveKit defaults.
    """
    try:
        from livekit.api import LiveKitAPI
        from livekit.protocol.room import CreateRoomRequest
    except ImportError as e:
        raise RuntimeError(f"livekit-api package not installed: {e}")

    url, key, secret = _get_lk_config()
    async with LiveKitAPI(url, key, secret) as lk:
        await lk.room.create_room(CreateRoomRequest(
            name=room_name,
            max_participants=max_participants,
            empty_timeout=empty_timeout_seconds,
        ))


async def delete_room(room_name: str) -> None:
    """Delete a LiveKit room (ends all participant connections)."""
    try:
        from livekit.api import LiveKitAPI, DeleteRoomRequest
    except ImportError as e:
        raise RuntimeError(f"livekit-api package not installed: {e}")

    url, key, secret = _get_lk_config()
    async with LiveKitAPI(url, key, secret) as lk:
        await lk.room.delete_room(DeleteRoomRequest(room=room_name))


async def update_participant_can_publish(
    room_name: str,
    identity: str,
    can_publish: bool,
) -> None:
    """Toggle a participant's publish permission on an active room.

    Revoking canPublish via token alone does NOT stop already-published tracks;
    updating the live permission through RoomService does.
    """
    try:
        from livekit.api import LiveKitAPI, UpdateParticipantRequest, ParticipantPermission
    except ImportError as e:
        raise RuntimeError(f"livekit-api package not installed: {e}")

    url, key, secret = _get_lk_config()
    async with LiveKitAPI(url, key, secret) as lk:
        await lk.room.update_participant(UpdateParticipantRequest(
            room=room_name,
            identity=identity,
            permission=ParticipantPermission(
                can_publish=can_publish,
                can_subscribe=True,
            ),
        ))


async def list_participant_identities(room_name: str) -> list[str]:
    """Return the identity strings of all active participants in a room."""
    try:
        from livekit.api import LiveKitAPI, ListParticipantsRequest
    except ImportError as e:
        raise RuntimeError(f"livekit-api package not installed: {e}")

    url, key, secret = _get_lk_config()
    async with LiveKitAPI(url, key, secret) as lk:
        resp = await lk.room.list_participants(ListParticipantsRequest(room=room_name))
        return [p.identity for p in resp.participants]


# ---------------------------------------------------------------------------
# Webhook signature verification (synchronous)
# ---------------------------------------------------------------------------

def receive_webhook(body: bytes | str, authorization: str) -> dict:
    """Verify the LiveKit webhook signature and return the parsed event dict.

    Raises ValueError on invalid signature (callers return 400).
    """
    try:
        from livekit.api import WebhookReceiver, TokenVerifier
    except ImportError as e:
        raise RuntimeError(f"livekit-api package not installed: {e}")

    _, key, secret = _get_lk_config()
    body_str = body.decode("utf-8") if isinstance(body, bytes) else body
    receiver = WebhookReceiver(TokenVerifier(key, secret))
    event = receiver.receive(body_str, authorization)
    # event is a WebhookEvent proto — convert to dict for easy consumption
    from google.protobuf.json_format import MessageToDict
    return MessageToDict(event, preserving_proto_field_name=True)

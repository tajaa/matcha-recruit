"""APNs push sender (token-based .p8 auth).

Best-effort + lazy: if `aioapns` isn't installed or the APNS_* env isn't
configured, every call is a silent no-op so the rest of the app is unaffected.
Wired as a single hook in `notification_service.create_notification`, so every
bell notification (channel message, DM, mention, call) also pushes to the
user's registered iOS devices.

Setup (one-time, per environment):
  1. Apple Developer → Keys → create an APNs Auth Key (.p8), note Key ID + Team ID.
  2. `pip install aioapns` into the server venv.
  3. Set env: APNS_KEY_ID, APNS_TEAM_ID, APNS_AUTH_KEY_PATH (path to the .p8),
     APNS_BUNDLE_ID (com.matchawork.app), APNS_USE_SANDBOX (true for dev builds).
"""
import logging
from typing import Optional
from uuid import UUID

from ...config import settings
from ...database import get_connection

logger = logging.getLogger(__name__)

_client = None
_disabled_logged = False


async def _get_client():
    """Construct (once) the aioapns client, or return None if unconfigured /
    unavailable. Failures are logged a single time, never raised."""
    global _client, _disabled_logged
    if _client is not None:
        return _client
    configured = all([
        settings.apns_key_id,
        settings.apns_team_id,
        settings.apns_auth_key_path,
        settings.apns_bundle_id,
    ])
    if not configured:
        return None
    try:
        from aioapns import APNs
        _client = APNs(
            key=settings.apns_auth_key_path,
            key_id=settings.apns_key_id,
            team_id=settings.apns_team_id,
            topic=settings.apns_bundle_id,
            use_sandbox=settings.apns_use_sandbox,
        )
        return _client
    except Exception as e:  # noqa: BLE001 — never let push setup break a request
        if not _disabled_logged:
            logger.warning("APNs disabled (aioapns import/config failed): %s", e)
            _disabled_logged = True
        return None


async def is_user_online(user_id: UUID) -> bool:
    """True if the user has a live channels-WS connection (i.e. the app is open)
    on any worker. Used to suppress push they'd otherwise also get in-app.

    Prefers the cross-worker Redis presence key (prod runs --workers 2, so the
    in-process socket table only sees this worker's clients); falls back to the
    local socket table if Redis is unavailable."""
    try:
        from ...werk.routes.channels_ws import _ONLINE_KEY_PREFIX, manager
        from .redis_cache import get_redis_cache
        redis = get_redis_cache()
        if redis is not None:
            if await redis.get(f"{_ONLINE_KEY_PREFIX}{user_id}"):
                return True
        async with manager.lock:
            return bool(manager.active_connections.get(user_id))
    except Exception:
        return False


async def send_to_user(
    user_id: UUID,
    title: str,
    body: Optional[str] = None,
    payload: Optional[dict] = None,
) -> None:
    """Push an alert to all of a user's registered iOS devices. No-op when APNs
    is unconfigured or the user has no devices. Prunes tokens APNs reports as
    permanently invalid."""
    client = await _get_client()
    if client is None:
        return

    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT token FROM device_tokens WHERE user_id = $1 AND platform = 'ios'",
            user_id,
        )
    if not rows:
        return

    from aioapns import NotificationRequest, PushType

    message = {
        "aps": {
            "alert": {"title": title, "body": body or ""},
            "sound": "default",
        },
        **(payload or {}),
    }

    dead: list[str] = []
    for r in rows:
        token = r["token"]
        try:
            req = NotificationRequest(
                device_token=token, message=message, push_type=PushType.ALERT
            )
            resp = await client.send_notification(req)
            if not resp.is_successful and resp.description in ("Unregistered", "BadDeviceToken"):
                dead.append(token)
        except Exception as e:  # noqa: BLE001
            logger.warning("APNs send failed token=%s…: %s", token[:8], e)

    if dead:
        async with get_connection() as conn:
            await conn.execute(
                "DELETE FROM device_tokens WHERE token = ANY($1::text[])", dead
            )

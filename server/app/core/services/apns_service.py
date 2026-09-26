"""Best-effort APNs routing for Werk and Matcha Schedule devices.

Each APNs topic and environment needs its own aioapns client. Legacy device
rows without a bundle/environment keep the original Werk topic and global
APNS_USE_SANDBOX setting.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional
from uuid import UUID

from app.config import get_settings
from app.database import connection_or_direct
from app.matcha.services.scheduling.schedule_rules import INACTIVE_EMPLOYMENT_STATUSES

logger = logging.getLogger(__name__)

# None for Werk means every kind except schedule_*. The Schedule app also
# receives Inbox DMs, which are shared between the two products.
APP_BUNDLES = {"werk": None, "schedule": ("schedule_*", "inbox_message")}
# (bundle, environment) -> (event loop the client was built on, client). An
# aioapns client captures the running loop when its connection pool is created,
# so it cannot outlive that loop: the API process has one loop for its lifetime,
# but every Celery task runs its own asyncio.run() and a client cached from the
# previous task would try to open connections on a closed loop.
_clients: dict[tuple[str, str], tuple[asyncio.AbstractEventLoop, object]] = {}
_disabled_logged = False
_PERMANENT_TOKEN_ERRORS = {"Unregistered", "BadDeviceToken", "DeviceTokenNotForTopic"}


def configured_bundles() -> dict[str, str]:
    settings = get_settings()
    if (settings.apns_bundle_id and settings.apns_bundle_id_schedule
            and settings.apns_bundle_id == settings.apns_bundle_id_schedule):
        # A shared APNs topic cannot separate the two apps' notifications.
        return {}
    bundles = {}
    if settings.apns_bundle_id:
        bundles[settings.apns_bundle_id] = "werk"
    if settings.apns_bundle_id_schedule:
        bundles[settings.apns_bundle_id_schedule] = "schedule"
    return bundles


def kind_allowed(bundle_id: Optional[str], kind: str) -> bool:
    """Route by the registered bundle; NULL is a legacy Werk device."""
    bundle = bundle_id or get_settings().apns_bundle_id
    app = configured_bundles().get(bundle)
    if app == "werk":
        return not kind.startswith("schedule_")
    if app == "schedule":
        return any(
            kind.startswith(rule[:-1]) if rule.endswith("*") else kind == rule
            for rule in APP_BUNDLES[app]
        )
    return False


def _environment(value: Optional[str]) -> str:
    return value or ("sandbox" if get_settings().apns_use_sandbox else "production")


async def _get_client(bundle_id: str, environment: str):
    """Cache APNs clients by topic and environment; setup failures are soft."""
    global _disabled_logged
    key = (bundle_id, environment)
    loop = asyncio.get_running_loop()
    cached = _clients.get(key)
    if cached is not None:
        cached_loop, client = cached
        if cached_loop is loop and not loop.is_closed():
            return client
        _clients.pop(key, None)
    settings = get_settings()
    if bundle_id not in configured_bundles() or not all((
        settings.apns_key_id, settings.apns_team_id, settings.apns_auth_key_path,
    )):
        return None
    try:
        from aioapns import APNs

        client = APNs(
            key=Path(settings.apns_auth_key_path).read_text(),
            key_id=settings.apns_key_id,
            team_id=settings.apns_team_id,
            topic=bundle_id,
            use_sandbox=environment == "sandbox",
        )
        _clients[key] = (loop, client)
        return client
    except Exception as exc:  # noqa: BLE001 — push must never fail a request
        if not _disabled_logged:
            logger.warning("APNs disabled (aioapns import/config failed): %s", exc)
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


async def get_offline_users(user_ids: list[UUID]) -> list[UUID]:
    """Batched is_user_online: one MGET instead of N GETs + N lock
    acquisitions. Redis unavailable ⇒ treat everyone as offline (same
    fail-open-to-push posture is_user_online falls back to for a single
    user, applied uniformly here rather than per-user local-table checks)."""
    if not user_ids:
        return []
    from ...werk.routes.channels_ws import _ONLINE_KEY_PREFIX
    from .redis_cache import get_redis_cache
    redis = get_redis_cache()
    if redis is None:
        return list(user_ids)
    try:
        vals = await redis.mget([f"{_ONLINE_KEY_PREFIX}{u}" for u in user_ids])
    except Exception:
        return list(user_ids)
    return [u for u, v in zip(user_ids, vals) if not v]


async def send_to_many(
    user_ids: list[UUID],
    title: str,
    body: Optional[str] = None,
    payload: Optional[dict] = None,
    *,
    kind: str,
    suppress_werk_users: Optional[set[UUID]] = None,
) -> None:
    """Send one batched lookup to every eligible device, pruning dead tokens."""
    if not user_ids:
        return
    settings = get_settings()
    if not all((settings.apns_key_id, settings.apns_team_id, settings.apns_auth_key_path)):
        return
    # Session-bound (Matcha Schedule) tokens only while their device session is
    # live and the employee is still employed; legacy rows have no session.
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            """SELECT dt.user_id, dt.token, dt.bundle_id, dt.environment
                 FROM device_tokens dt
                 LEFT JOIN auth_device_sessions ds ON ds.id = dt.device_session_id
                WHERE dt.user_id = ANY($1::uuid[]) AND dt.platform = 'ios'
                  AND (
                        dt.device_session_id IS NULL
                     OR (ds.revoked_at IS NULL AND NOT EXISTS (
                            SELECT 1 FROM employees e
                             WHERE e.user_id = dt.user_id
                               AND COALESCE(e.employment_status, 'active') = ANY($2::text[])
                        ))
                  )""",
            user_ids, list(INACTIVE_EMPLOYMENT_STATUSES),
        )
    if not rows:
        return

    try:
        from aioapns import NotificationRequest, PushType
    except ImportError:
        return

    message = {
        "aps": {"alert": {"title": title, "body": body or ""}, "sound": "default"},
        **(payload or {}),
    }
    dead: list[str] = []
    for row in rows:
        bundle_id = row["bundle_id"] or settings.apns_bundle_id
        if not kind_allowed(bundle_id, kind):
            continue
        if (suppress_werk_users and row["user_id"] in suppress_werk_users
                and configured_bundles().get(bundle_id) == "werk"):
            continue
        sender = await _get_client(bundle_id, _environment(row["environment"]))
        if sender is None:
            continue
        token = row["token"]
        try:
            response = await sender.send_notification(NotificationRequest(
                device_token=token, message=message, push_type=PushType.ALERT,
            ))
            if not response.is_successful and response.description in _PERMANENT_TOKEN_ERRORS:
                dead.append(token)
        except Exception as exc:  # noqa: BLE001 — one device must not block another
            logger.warning("APNs send failed token=%s…: %s", token[:8], exc)

    if dead:
        async with connection_or_direct() as conn:
            await conn.execute("DELETE FROM device_tokens WHERE token = ANY($1::text[])", dead)


async def send_to_user(
    user_id: UUID,
    title: str,
    body: Optional[str] = None,
    payload: Optional[dict] = None,
    *,
    kind: str,
    suppress_werk: bool = False,
) -> None:
    """Send to a user's eligible devices across both apps."""
    await send_to_many(
        [user_id], title, body, payload, kind=kind,
        suppress_werk_users={user_id} if suppress_werk else None,
    )

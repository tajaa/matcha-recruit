"""Tell-Us APNs push sender (token-based .p8 auth).

Mirrors `core/services/apns_service.py` but talks to the Tell-Us
`tellus_device_tokens` table and uses the Tell-Us app bundle id
(`com.beetlejuse.app`) as the APNs topic. Tell-Us accounts live in
`tellus_accounts`, not `users`, so matcha's sender cannot address them.

Best-effort + lazy: if `aioapns` isn't installed or the `APNS_*` env isn't
configured, every call is a silent no-op.

`schedule_push` never blocks the caller and never dispatches while the
caller's DB transaction is open — inside a request, it enqueues onto a
per-request `ContextVar` queue instead of firing immediately. `flush_pushes`
(a FastAPI yield-dependency wired on `tellus_router`) drains that queue only
after the whole request completed without raising, so a push can never fire
for a notification row that got rolled back by a later error in the same
handler. Outside a request (workers/scripts, no `flush_pushes` in the call
stack), `schedule_push` dispatches immediately — same as before. Dispatched
sends are tracked in `_inflight` with `add_done_callback` so the event loop's
weak task references can't silently garbage-collect an in-flight push.
"""
import asyncio
import logging
from contextvars import ContextVar
from typing import Optional
from uuid import UUID

from ...config import get_settings
from ...database import get_connection

logger = logging.getLogger(__name__)

_client = None
_disabled_logged = False

# Per-request queue of (account_ids, title, body, payload) push jobs. `None`
# outside a request (no flush_pushes dependency in the call stack) — that
# case dispatches immediately, matching pre-queue behavior for workers/scripts.
_queue: ContextVar[Optional[list]] = ContextVar("tellus_push_queue", default=None)
_inflight: set = set()

# Kinds that warrant a push. Points/level/badge/streak notifications fire in
# immediate response to the user's own in-app action (they are already looking
# at the screen), so pushing them would be noise. Push only the genuinely async
# events the product asked for: fan-board posts, campaign starts, reviews,
# messages, and board-post comments.
PUSH_KINDS = {
    "board_post",          # consumer: a brand posted to its regulars board
    "promo_campaign",      # consumer: a followed brand started a campaign
    "feedback",            # brand: a new review/feedback arrived
    "dm_message",          # either: a new message (Comms / feedback DM)
    "dm_assignment",       # brand team member: a Comms thread was assigned
    "board_reply_pending", # brand: a member replied to a board post (needs approval)
}


async def _get_client():
    """Construct (once) the aioapns client bound to the Tell-Us bundle id, or
    return None if unconfigured / unavailable. Failures are logged once, never
    raised."""
    global _client, _disabled_logged
    if _client is not None:
        return _client
    if not _is_configured():
        return None
    settings = get_settings()
    topic = settings.apns_bundle_id_tellus or settings.apns_bundle_id
    try:
        from aioapns import APNs
        _client = APNs(
            key=settings.apns_auth_key_path,
            key_id=settings.apns_key_id,
            team_id=settings.apns_team_id,
            topic=topic,
            use_sandbox=settings.apns_use_sandbox,
        )
        return _client
    except Exception as e:  # noqa: BLE001 — never let push setup break a request
        if not _disabled_logged:
            logger.warning("Tell-Us APNs disabled (aioapns import/config failed): %s", e)
            _disabled_logged = True
        return None


def _is_configured() -> bool:
    """Cheap synchronous pre-check so schedule_push never spawns a task (or a
    DB read) when APNs isn't set up — dev/test runs and unconfigured prod."""
    settings = get_settings()
    topic = settings.apns_bundle_id_tellus or settings.apns_bundle_id
    return all([
        settings.apns_key_id,
        settings.apns_team_id,
        settings.apns_auth_key_path,
        topic,
    ])


async def register_token(
    account_id: UUID,
    token: str,
    platform: str = "ios",
    bundle_id: Optional[str] = None,
) -> None:
    """Upsert a device token, scoped per (account, token) — not per token alone.
    A bare token-unique upsert lets any account that learns another device's
    APNs token silently reassign that device's push stream to itself; keying
    on the pair means registering the same token under a second account adds
    a second row instead of stealing the first (send_to_accounts dedupes by
    token so a shared device still gets one alert, not two)."""
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO tellus_device_tokens (account_id, token, platform, bundle_id, last_seen_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (account_id, token) DO UPDATE
              SET platform = EXCLUDED.platform,
                  bundle_id = EXCLUDED.bundle_id,
                  last_seen_at = NOW()
            """,
            account_id, token, platform, bundle_id,
        )


async def unregister_token(account_id: UUID, token: str) -> None:
    """Drop a device token on logout so a shared device stops receiving the
    previous account's pushes."""
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM tellus_device_tokens WHERE token = $1 AND account_id = $2",
            token, account_id,
        )


async def send_to_accounts(
    account_ids: list[UUID],
    title: str,
    body: Optional[str] = None,
    payload: Optional[dict] = None,
) -> None:
    """Push an alert to every registered iOS device of the given accounts.
    No-op when APNs is unconfigured or none have devices. Prunes tokens APNs
    reports as permanently invalid."""
    client = await _get_client()
    if client is None or not account_ids:
        return

    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT DISTINCT token FROM tellus_device_tokens
               WHERE account_id = ANY($1::uuid[]) AND platform = 'ios'
                 AND last_seen_at > NOW() - INTERVAL '60 days'""",
            list(account_ids),
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
            logger.warning("Tell-Us APNs send failed token=%s…: %s", token[:8], e)

    if dead:
        async with get_connection() as conn:
            await conn.execute(
                "DELETE FROM tellus_device_tokens WHERE token = ANY($1::text[])", dead
            )


def schedule_push(
    account_ids: list[UUID],
    kind: str,
    title: str,
    body: Optional[str] = None,
    *,
    reference_type: Optional[str] = None,
    reference_id: Optional[str] = None,
    slug: Optional[str] = None,
    name: Optional[str] = None,
) -> None:
    """Queue (or, outside a request, immediately fire) a push for a
    notification that was just inserted.

    Gated on `kind` being in PUSH_KINDS so points/level/badge noise never
    reaches the lock screen. `slug`/`name` ride in the payload so a tapped
    board-post / campaign push can deep-link to the right brand screen.

    Inside a request, this only enqueues — `flush_pushes` (the `tellus_router`
    dependency) dispatches after the handler returns successfully, and drops
    the queue if the handler raised. Never call this after yielding control
    back past the request (e.g. from a detached background task) expecting
    immediate delivery — queue it before the handler returns."""
    if kind not in PUSH_KINDS:
        return
    if not account_ids:
        return
    if not _is_configured():
        return
    payload = {
        "type": kind,
        "reference_type": reference_type,
        "reference_id": reference_id,
        "slug": slug,
        "name": name,
    }
    job = (list(account_ids), title, body, payload)
    queue = _queue.get()
    if queue is None:
        _dispatch(job)
    else:
        queue.append(job)


def _dispatch(job: tuple) -> None:
    """Spawn the send as a tracked task — `_inflight` holds a strong
    reference so the event loop's weak task refs can't GC it mid-await."""
    task = asyncio.create_task(_safe_send(*job))
    _inflight.add(task)
    task.add_done_callback(_inflight.discard)


async def _safe_send(
    account_ids: list[UUID], title: str, body: Optional[str], payload: dict
) -> None:
    try:
        await send_to_accounts(account_ids, title, body, payload)
    except Exception as e:  # noqa: BLE001
        logger.warning("Tell-Us APNs push failed: %s", e)


async def flush_pushes():
    """FastAPI yield-dependency — wrap the whole request. Pushes queued
    during the request only go out if the handler completes without raising;
    an exception (404/409/500/...) means whatever DB row the push referenced
    may have rolled back, so the queue is dropped, not dispatched."""
    token = _queue.set([])
    try:
        yield
    except Exception:
        raise
    else:
        for job in _queue.get() or []:
            _dispatch(job)
    finally:
        _queue.reset(token)

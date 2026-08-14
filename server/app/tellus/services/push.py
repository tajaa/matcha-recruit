"""Tell-Us APNs push sender (token-based .p8 auth).

Mirrors `core/services/apns_service.py` but talks to the Tell-Us
`tellus_device_tokens` table and uses the Tell-Us app bundle id
(`com.beetlejuse.app`) as the APNs topic. Tell-Us accounts live in
`tellus_accounts`, not `users`, so matcha's sender cannot address them.

Best-effort + lazy: if `aioapns` isn't installed or the `APNS_*` env isn't
configured, every call is a silent no-op. `schedule_push` is fire-and-forget
(a detached asyncio task) so a push never blocks the response and never holds
the caller's DB transaction open — `notify_account` runs inside `conn.transaction()`
blocks, and an APNs round-trip must not delay the commit or pin the connection.
"""
import asyncio
import logging
from typing import Optional
from uuid import UUID

from ...config import get_settings
from ...database import get_connection

logger = logging.getLogger(__name__)

_client = None
_disabled_logged = False

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
    """Upsert a device token for the account (idempotent on token)."""
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO tellus_device_tokens (account_id, token, platform, bundle_id, last_seen_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (token) DO UPDATE
              SET account_id = EXCLUDED.account_id,
                  platform = EXCLUDED.platform,
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
            "SELECT token FROM tellus_device_tokens WHERE account_id = ANY($1::uuid[]) AND platform = 'ios'",
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
    """Fire-and-forget push for a notification that was just inserted.

    Gated on `kind` being in PUSH_KINDS so points/level/badge noise never
    reaches the lock screen. `slug`/`name` ride in the payload so a tapped
    board-post / campaign push can deep-link to the right brand screen."""
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
    asyncio.create_task(_safe_send(account_ids, title, body, payload))


async def _safe_send(
    account_ids: list[UUID], title: str, body: Optional[str], payload: dict
) -> None:
    try:
        await send_to_accounts(account_ids, title, body, payload)
    except Exception as e:  # noqa: BLE001
        logger.warning("Tell-Us APNs push failed: %s", e)

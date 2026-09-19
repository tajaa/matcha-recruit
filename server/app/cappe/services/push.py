"""Best-effort storefront APNs notifications, dispatched after commits."""
import asyncio
import logging
from contextvars import ContextVar
from pathlib import Path

from fastapi import HTTPException

from app.config import get_settings
from app.database import get_connection

logger = logging.getLogger(__name__)
_clients = {}
_queue = ContextVar("cappe_push_queue", default=None)
_inflight = set()


def bundle_allowed(bundle):
    return bundle in {v.strip() for v in get_settings().cappe_apns_bundle_ids.split(",") if v.strip()}


async def register_token(site, shopper, body):
    if body.bundle_id != site.get("app_bundle_id") or not bundle_allowed(body.bundle_id):
        raise HTTPException(422, "App is not configured for this store")
    async with get_connection() as conn, conn.transaction():
        await conn.fetchval("SELECT id FROM cappe_shoppers WHERE id=$1 AND site_id=$2 FOR UPDATE", shopper["id"], site["id"])
        await conn.execute(
            "INSERT INTO cappe_shopper_devices(shopper_id,site_id,token,bundle_id,environment,app_version) "
            "VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT(token,bundle_id,environment) DO UPDATE SET "
            "shopper_id=EXCLUDED.shopper_id,site_id=EXCLUDED.site_id,app_version=EXCLUDED.app_version,updated_at=NOW()",
            shopper["id"], site["id"], body.token.lower(), body.bundle_id, body.environment, body.app_version,
        )


def client(bundle, environment):
    settings = get_settings()
    key = settings.cappe_apns_key_id or settings.apns_key_id
    team = settings.cappe_apns_team_id or settings.apns_team_id
    path = settings.cappe_apns_auth_key_path or settings.apns_auth_key_path
    if not all((key, team, path)) or not bundle_allowed(bundle):
        return None
    cache_key = (bundle, environment, key, team, path)
    if cache_key not in _clients:
        from aioapns import APNs
        _clients[cache_key] = APNs(key=Path(path).read_text(), key_id=key, team_id=team,
                                  topic=bundle, use_sandbox=environment == "sandbox")
    return _clients[cache_key]


async def send_to_shopper(shopper_id, site_id, title, body, data):
    try:
        async with get_connection() as conn:
            devices = await conn.fetch(
                "SELECT d.* FROM cappe_shopper_devices d JOIN cappe_shoppers s ON s.id=d.shopper_id "
                "JOIN cappe_sites t ON t.id=d.site_id WHERE d.shopper_id=$1 AND d.site_id=$2 "
                "AND s.push_order_updates AND t.app_bundle_id=d.bundle_id", shopper_id, site_id,
            )
        for device in devices:
            try:
                sender = client(device["bundle_id"], device["environment"])
                if sender is None:
                    continue
                from aioapns import NotificationRequest
                result = await sender.send_notification(NotificationRequest(
                    device_token=device["token"], message={"aps": {"alert": {"title": title, "body": body}, "sound": "default"}, **data},
                ))
                if result.description in ("BadDeviceToken", "Unregistered"):
                    async with get_connection() as conn:
                        await conn.execute("DELETE FROM cappe_shopper_devices WHERE id=$1 AND updated_at=$2",
                                           device["id"], device["updated_at"])
            except Exception:
                logger.warning("Cappe device push failed", exc_info=True)
    except Exception:
        logger.warning("Cappe shopper push failed", exc_info=True)


async def notify_order_event(order_id, event):
    try:
        async with get_connection() as conn:
            order = await conn.fetchrow(
                "SELECT o.shopper_id,o.site_id,o.access_token,s.name FROM cappe_orders o "
                "JOIN cappe_sites s ON s.id=o.site_id WHERE o.id=$1", order_id,
            )
        if order and order["shopper_id"]:
            await send_to_shopper(order["shopper_id"], order["site_id"], order["name"],
                                  f"Your order has been {event}.",
                                  {"type": "order", "order_token": order["access_token"], "event": event})
    except Exception:
        logger.warning("Cappe order push failed", exc_info=True)


def _dispatch(order_id, event):
    task = asyncio.create_task(notify_order_event(order_id, event))
    _inflight.add(task)
    task.add_done_callback(_inflight.discard)


def schedule_push(order_id, event):
    # Route/service unit tests intentionally do not bootstrap application
    # settings. Push is best-effort in production as well, so an unavailable
    # configuration must never turn an otherwise successful order transition
    # into a 500.
    try:
        settings = get_settings()
    except RuntimeError:
        return
    if not settings.cappe_apns_bundle_ids:
        return
    queue = _queue.get()
    if queue is None:
        _dispatch(order_id, event)
    else:
        queue.append((order_id, event))


async def flush_pushes():
    queue = []
    token = _queue.set(queue)
    try:
        yield
    except BaseException:
        raise
    else:
        for job in queue:
            _dispatch(*job)
    finally:
        _queue.reset(token)

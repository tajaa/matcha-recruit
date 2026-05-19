"""Channel WebSocket handler for real-time group chat messaging."""

import asyncio
import json
import logging
from typing import Dict, Optional, Set
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel

from ...database import get_connection
from ..services.auth import decode_token
from ..services.redis_cache import get_redis_cache
from .voice_signaling import (
    handle_voice_join,
    handle_voice_leave,
    handle_voice_offer,
    handle_voice_answer,
    handle_voice_ice,
    cleanup_user_from_calls,
)

logger = logging.getLogger(__name__)

# Online presence — written on every WS receive (heartbeat), read by the
# mention_email Celery worker to skip emails for users who are still active.
# TTL is intentionally generous (60s) so a single dropped ping doesn't trigger
# a false-offline email; manager.disconnect explicitly clears the key when the
# last WS for a user closes.
_ONLINE_KEY_PREFIX = "channels_ws:online:"
_ONLINE_TTL_SECONDS = 60

# Redis pub/sub channel used to fan-out broadcasts across uvicorn workers.
# Production runs --workers 2, so an in-process broadcast on worker A would
# never reach a WS client connected to worker B. Each worker subscribes to
# this channel on startup and re-dispatches incoming envelopes to its own
# local sockets via _local_broadcast_to_room / _local_send_to_user.
_FANOUT_CHANNEL = "channels:fanout"
_SERVER_PING_INTERVAL_SECONDS = 25


async def _mark_online(user_id: UUID) -> None:
    redis = get_redis_cache()
    if redis is None:
        return
    try:
        await redis.setex(f"{_ONLINE_KEY_PREFIX}{user_id}", _ONLINE_TTL_SECONDS, "1")
    except Exception:
        pass


async def _mark_offline(user_id: UUID) -> None:
    redis = get_redis_cache()
    if redis is None:
        return
    try:
        await redis.delete(f"{_ONLINE_KEY_PREFIX}{user_id}")
    except Exception:
        pass

router = APIRouter()

# ---------------------------------------------------------------------------
# User identity model (resolved at connection time)
# ---------------------------------------------------------------------------

_USER_NAME_EXPR = "COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email)"


class ChannelUser(BaseModel):
    id: UUID
    name: str
    email: str
    role: str
    avatar_url: Optional[str] = None
    company_id: Optional[UUID] = None


# ---------------------------------------------------------------------------
# Connection Manager (adapted from chat/websocket.py)
# ---------------------------------------------------------------------------

class ChannelConnectionManager:
    """Manages WebSocket connections for channel chat."""

    def __init__(self):
        self.active_connections: Dict[UUID, Set[WebSocket]] = {}
        self.room_members: Dict[str, Set[UUID]] = {}
        self.users: Dict[UUID, ChannelUser] = {}
        self.user_rooms: Dict[UUID, Set[str]] = {}
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user: ChannelUser):
        await websocket.accept()
        async with self.lock:
            if user.id not in self.active_connections:
                self.active_connections[user.id] = set()
                self.user_rooms[user.id] = set()
            self.active_connections[user.id].add(websocket)
            self.users[user.id] = user

    async def disconnect(self, websocket: WebSocket, user_id: UUID):
        async with self.lock:
            if user_id in self.active_connections:
                self.active_connections[user_id].discard(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
                    if user_id in self.user_rooms:
                        rooms_to_leave = list(self.user_rooms[user_id])
                        del self.user_rooms[user_id]
                        user = self.users.pop(user_id, None)
                        for room in rooms_to_leave:
                            if room in self.room_members:
                                self.room_members[room].discard(user_id)
                                if user:
                                    await self._broadcast_to_room(room, {
                                        "type": "user_left",
                                        "room": room,
                                        "user": user.model_dump(mode='json'),
                                    }, exclude_user=user_id)

                        # Clean up voice calls and notify participants
                        user_name = user.name if user else "Unknown"
                        affected_channels = await cleanup_user_from_calls(user_id)
                        for channel_id in affected_channels:
                            await self._broadcast_to_room(channel_id, {
                                "type": "voice_user_left",
                                "channel_id": channel_id,
                                "user_id": str(user_id),
                                "user_name": user_name,
                            }, exclude_user=user_id)

    async def join_room(self, user_id: UUID, room_key: str):
        async with self.lock:
            if room_key not in self.room_members:
                self.room_members[room_key] = set()

            was_in_room = user_id in self.room_members[room_key]
            self.room_members[room_key].add(user_id)

            if user_id in self.user_rooms:
                self.user_rooms[user_id].add(room_key)

            if not was_in_room and user_id in self.users:
                await self._broadcast_to_room(room_key, {
                    "type": "user_joined",
                    "room": room_key,
                    "user": self.users[user_id].model_dump(mode='json'),
                }, exclude_user=user_id)

    async def leave_room(self, user_id: UUID, room_key: str):
        async with self.lock:
            if room_key in self.room_members:
                self.room_members[room_key].discard(user_id)
            if user_id in self.user_rooms:
                self.user_rooms[user_id].discard(room_key)
            if user_id in self.users:
                await self._broadcast_to_room(room_key, {
                    "type": "user_left",
                    "room": room_key,
                    "user": self.users[user_id].model_dump(mode='json'),
                })

    async def broadcast_message(self, room_key: str, message: dict):
        await self._broadcast_to_room(room_key, {
            "type": "message",
            "room": room_key,
            "message": message,
        })

    async def broadcast_typing(self, room_key: str, user: ChannelUser):
        await self._broadcast_to_room(room_key, {
            "type": "typing",
            "room": room_key,
            "user": user.model_dump(mode='json'),
        }, exclude_user=user.id)

    async def get_online_users(self, room_key: str) -> list:
        async with self.lock:
            if room_key not in self.room_members:
                return []
            return [
                self.users[uid].model_dump(mode='json')
                for uid in self.room_members[room_key]
                if uid in self.users
            ]

    async def send_to_user(self, user_id: UUID, message: dict):
        """Send a message to a specific user (all their connections, on any worker)."""
        redis = get_redis_cache()
        if redis is None:
            await self._local_send_to_user(user_id, message)
            return
        envelope = {
            "kind": "user",
            "user_id": str(user_id),
            "message": message,
        }
        try:
            await redis.publish(_FANOUT_CHANNEL, json.dumps(envelope, default=str))
        except Exception:
            logger.exception("Redis publish failed in send_to_user; using local fallback")
            await self._local_send_to_user(user_id, message)

    async def _local_send_to_user(self, user_id: UUID, message: dict):
        """Direct write to this worker's local sockets for a user. Called by
        the subscriber loop when a fanout envelope targets this user, and as
        a fallback when Redis is unavailable."""
        async with self.lock:
            conns = set(self.active_connections.get(user_id, set()))
        if not conns:
            return
        data = json.dumps(message, default=str)
        dead = []
        for ws in conns:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        if dead:
            async with self.lock:
                for ws in dead:
                    self.active_connections.get(user_id, set()).discard(ws)

    async def _broadcast_to_room(self, room_key: str, message: dict, exclude_user: UUID = None):
        """Fan-out to every WS member of a room across all uvicorn workers.

        Publishes to Redis so other workers' subscribers can deliver to their
        own local sockets. If Redis is unavailable (e.g. dev without Redis),
        falls back to local-only fanout so single-process dev still works.
        """
        redis = get_redis_cache()
        if redis is None:
            await self._local_broadcast_to_room(room_key, message, exclude_user=exclude_user)
            return
        envelope = {
            "kind": "room",
            "room": room_key,
            "message": message,
            "exclude_user": str(exclude_user) if exclude_user else None,
        }
        try:
            await redis.publish(_FANOUT_CHANNEL, json.dumps(envelope, default=str))
        except Exception:
            logger.exception("Redis publish failed in _broadcast_to_room; using local fallback")
            await self._local_broadcast_to_room(room_key, message, exclude_user=exclude_user)

    async def _local_broadcast_to_room(self, room_key: str, message: dict, exclude_user: UUID = None):
        """Direct write to this worker's local sockets for a room. Called by
        the subscriber loop and as a Redis-down fallback."""
        if room_key not in self.room_members:
            return
        data = json.dumps(message, default=str)
        for user_id in self.room_members[room_key]:
            if exclude_user and user_id == exclude_user:
                continue
            if user_id in self.active_connections:
                dead = []
                for ws in self.active_connections[user_id]:
                    try:
                        await ws.send_text(data)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    self.active_connections[user_id].discard(ws)


manager = ChannelConnectionManager()


# ---------------------------------------------------------------------------
# Cross-worker pub/sub subscriber + server-side keepalive ping
# ---------------------------------------------------------------------------

_subscriber_task: Optional[asyncio.Task] = None
_server_ping_task: Optional[asyncio.Task] = None


async def _fanout_subscriber_loop() -> None:
    """Long-running per-worker task. Subscribes to the Redis fanout channel
    and dispatches incoming envelopes to this worker's local sockets.

    Self-healing: on any exception, sleeps 2s and re-subscribes. Cancellation
    exits cleanly.
    """
    while True:
        pubsub = None
        try:
            redis = get_redis_cache()
            if redis is None:
                # Dev without Redis — nothing to subscribe to; sleep then retry.
                await asyncio.sleep(5)
                continue
            pubsub = redis.pubsub()
            await pubsub.subscribe(_FANOUT_CHANNEL)
            logger.info("[Channels WS] Subscribed to %s", _FANOUT_CHANNEL)
            async for raw in pubsub.listen():
                if raw is None or raw.get("type") != "message":
                    continue
                payload = raw.get("data")
                if not payload:
                    continue
                try:
                    envelope = json.loads(payload)
                except Exception:
                    logger.warning("[Channels WS] Malformed fanout envelope; dropping")
                    continue
                kind = envelope.get("kind")
                msg = envelope.get("message")
                if msg is None:
                    continue
                if kind == "room":
                    room_key = envelope.get("room")
                    if not room_key:
                        continue
                    exclude_raw = envelope.get("exclude_user")
                    exclude_user = None
                    if exclude_raw:
                        try:
                            exclude_user = UUID(exclude_raw)
                        except (ValueError, TypeError):
                            exclude_user = None
                    await manager._local_broadcast_to_room(
                        room_key, msg, exclude_user=exclude_user,
                    )
                elif kind == "user":
                    uid_raw = envelope.get("user_id")
                    if not uid_raw:
                        continue
                    try:
                        uid = UUID(uid_raw)
                    except (ValueError, TypeError):
                        continue
                    await manager._local_send_to_user(uid, msg)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("[Channels WS] Subscriber loop error; restarting in 2s")
            await asyncio.sleep(2)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(_FANOUT_CHANNEL)
                    await pubsub.aclose()
                except Exception:
                    pass


async def _server_ping_loop() -> None:
    """Periodic keepalive push from server to every connected WS. Prevents
    Nginx / intermediaries from silently killing idle connections and gives
    the server early detection of dead sockets (a failed send drops the WS
    from active_connections)."""
    while True:
        try:
            await asyncio.sleep(_SERVER_PING_INTERVAL_SECONDS)
            # Snapshot the per-user connection map under the lock so we don't
            # iterate while disconnect() mutates it.
            async with manager.lock:
                snapshot: list[tuple[UUID, list[WebSocket]]] = [
                    (uid, list(conns)) for uid, conns in manager.active_connections.items()
                ]
            ping_payload = json.dumps({"type": "server_ping"})
            for user_id, conns in snapshot:
                dead: list[WebSocket] = []
                for ws in conns:
                    try:
                        await ws.send_text(ping_payload)
                    except Exception:
                        dead.append(ws)
                if dead:
                    async with manager.lock:
                        bucket = manager.active_connections.get(user_id)
                        if bucket is not None:
                            for ws in dead:
                                bucket.discard(ws)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("[Channels WS] Server ping loop error; continuing")


def start_fanout_subscriber() -> None:
    """Start the per-worker Redis pub/sub subscriber. Idempotent."""
    global _subscriber_task
    if _subscriber_task and not _subscriber_task.done():
        return
    _subscriber_task = asyncio.create_task(_fanout_subscriber_loop())


def start_server_ping_loop() -> None:
    """Start the per-worker server-side ping loop. Idempotent."""
    global _server_ping_task
    if _server_ping_task and not _server_ping_task.done():
        return
    _server_ping_task = asyncio.create_task(_server_ping_loop())


async def stop_fanout_subscriber() -> None:
    """Cancel the subscriber task on shutdown."""
    global _subscriber_task
    if _subscriber_task is not None:
        _subscriber_task.cancel()
        try:
            await _subscriber_task
        except (asyncio.CancelledError, Exception):
            pass
        _subscriber_task = None


async def stop_server_ping_loop() -> None:
    global _server_ping_task
    if _server_ping_task is not None:
        _server_ping_task.cancel()
        try:
            await _server_ping_task
        except (asyncio.CancelledError, Exception):
            pass
        _server_ping_task = None


async def broadcast_message_deleted(
    channel_id: str,
    message_id: str,
    deleted_by: str,
) -> None:
    """Fan out a message_deleted event to all members currently connected
    to a channel room. Called by the REST DELETE handler in channels.py.
    """
    await manager._broadcast_to_room(
        channel_id,
        {
            "type": "message_deleted",
            "room": channel_id,
            "message_id": message_id,
            "deleted_by": deleted_by,
        },
    )


async def broadcast_broadcast_started(
    channel_id: str,
    broadcast_id: str,
    started_by: str,
    started_at: str,
    title: Optional[str] = None,
) -> None:
    """Push broadcast.started to all connected members of a channel."""
    await manager._broadcast_to_room(channel_id, {
        "type": "broadcast.started",
        "channel_id": channel_id,
        "broadcast_id": broadcast_id,
        "started_by": started_by,
        "started_at": started_at,
        "title": title,
    })


async def broadcast_broadcast_ended(channel_id: str, broadcast_id: str) -> None:
    await manager._broadcast_to_room(channel_id, {
        "type": "broadcast.ended",
        "channel_id": channel_id,
        "broadcast_id": broadcast_id,
    })


async def broadcast_reaction_update(
    channel_id: str,
    message_id: str,
    reactions: list[dict],
) -> None:
    """Fan out a reaction_update event to all members currently connected
    to a channel room. Called by the REST react handler in channels.py.
    """
    await manager._broadcast_to_room(
        channel_id,
        {
            "type": "reaction_update",
            "room": channel_id,
            "message_id": message_id,
            "reactions": reactions,
        },
    )


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

async def _authenticate(token: str) -> Optional[ChannelUser]:
    """Authenticate a WebSocket connection using the main app JWT."""
    payload = decode_token(token, expected_type="access")
    if not payload:
        return None

    user_id = UUID(payload.sub)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            SELECT u.id, u.email, u.role, u.avatar_url,
                   {_USER_NAME_EXPR} AS name
            FROM users u
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE u.id = $1 AND u.is_active = true
            """,
            user_id,
        )
        if not row:
            return None

        # Resolve company_id
        company_id = None
        if row["role"] in ("client", "individual"):
            company_id = await conn.fetchval(
                "SELECT company_id FROM clients WHERE user_id = $1", user_id
            )
        elif row["role"] == "employee":
            company_id = await conn.fetchval(
                "SELECT org_id FROM employees WHERE user_id = $1", user_id
            )
        elif row["role"] == "admin":
            # Admin can access any company — resolved per room join
            company_id = None

        return ChannelUser(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            role=row["role"],
            avatar_url=row["avatar_url"],
            company_id=company_id,
        )


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("")
async def channel_websocket(
    websocket: WebSocket,
    token: str = Query(...),
):
    """WebSocket endpoint for real-time channel messaging."""
    user = await _authenticate(token)
    if not user:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await manager.connect(websocket, user)
    await _mark_online(user.id)

    try:
        while True:
            data = await websocket.receive_json()
            await _mark_online(user.id)
            msg_type = data.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "join_room":
                channel_id = data.get("channel_id")
                if channel_id:
                    try:
                        ch_uuid = UUID(channel_id)
                    except (ValueError, TypeError):
                        await websocket.send_json({"type": "error", "message": "Invalid channel ID"})
                        continue
                    async with get_connection() as conn:
                        # Verify membership (allows cross-tenant memberships; REST uses the same rule)
                        ok = await conn.fetchval(
                            "SELECT EXISTS(SELECT 1 FROM channel_members WHERE channel_id = $1 AND user_id = $2 AND removed_for_inactivity IS NOT TRUE)",
                            ch_uuid, user.id,
                        )

                        if ok:
                            room_key = str(channel_id)
                            await manager.join_room(user.id, room_key)
                            online = await manager.get_online_users(room_key)
                            await websocket.send_json({
                                "type": "online_users",
                                "room": room_key,
                                "users": online,
                            })
                            # Emit live broadcast state so late-joiners see "Live now"
                            bc = await conn.fetchrow(
                                "SELECT id, started_by, started_at, title FROM channel_broadcasts WHERE channel_id = $1 AND ended_at IS NULL",
                                ch_uuid,
                            )
                            if bc:
                                await websocket.send_json({
                                    "type": "broadcast.started",
                                    "channel_id": str(channel_id),
                                    "broadcast_id": str(bc["id"]),
                                    "started_by": str(bc["started_by"]),
                                    "started_at": bc["started_at"].isoformat(),
                                    "title": bc["title"],
                                })
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Channel not found or not a member",
                            })

            elif msg_type == "leave_room":
                channel_id = data.get("channel_id")
                if channel_id:
                    await manager.leave_room(user.id, str(channel_id))

            elif msg_type == "message":
                channel_id = data.get("channel_id")
                content = (data.get("content") or "").strip()
                attachments = data.get("attachments") or []
                reply_to_id = data.get("reply_to_id")
                # Client-generated correlation ID for optimistic UI reconciliation.
                # Clients append a pending message locally with this ID; on echo,
                # they replace the pending entry instead of duplicating it.
                client_message_id = data.get("client_message_id")
                if channel_id and (content or attachments) and len(content) <= 4000:
                    try:
                        ch_uuid = UUID(channel_id)
                    except (ValueError, TypeError):
                        continue
                    reply_uuid = None
                    if reply_to_id:
                        try:
                            reply_uuid = UUID(reply_to_id)
                        except (ValueError, TypeError):
                            pass
                    room_key = str(channel_id)
                    import json as _json
                    attachments_json = _json.dumps(attachments) if attachments else "[]"
                    async with get_connection() as conn:
                        # Verify membership (exclude removed members)
                        is_member = await conn.fetchval(
                            "SELECT EXISTS(SELECT 1 FROM channel_members WHERE channel_id = $1 AND user_id = $2 AND removed_for_inactivity IS NOT TRUE)",
                            ch_uuid, user.id,
                        )
                        if is_member:
                            row = await conn.fetchrow(
                                """
                                INSERT INTO channel_messages (channel_id, sender_id, content, attachments, reply_to_id)
                                VALUES ($1, $2, $3, $4::jsonb, $5)
                                RETURNING id, channel_id, sender_id, content, attachments, reply_to_id, created_at, edited_at
                                """,
                                ch_uuid, user.id, content or "", attachments_json, reply_uuid,
                            )
                            # Update channel + member activity timestamps
                            await conn.execute(
                                "UPDATE channels SET updated_at = NOW() WHERE id = $1",
                                ch_uuid,
                            )
                            await conn.execute(
                                "UPDATE channel_members SET last_contributed_at = NOW() WHERE channel_id = $1 AND user_id = $2",
                                ch_uuid, user.id,
                            )

                            broadcast_attachments = _json.loads(row["attachments"]) if row["attachments"] else []
                            # Build reply preview for broadcast
                            reply_preview = None
                            if reply_uuid:
                                rp = await conn.fetchrow(
                                    """
                                    SELECT m.content, m.attachments, m.deleted_at,
                                           COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS sender_name
                                    FROM channel_messages m
                                    JOIN users u ON u.id = m.sender_id
                                    LEFT JOIN clients c ON c.user_id = u.id
                                    LEFT JOIN employees e ON e.user_id = u.id
                                    LEFT JOIN admins a ON a.user_id = u.id
                                    WHERE m.id = $1
                                    """,
                                    reply_uuid,
                                )
                                if rp:
                                    rp_atts = []
                                    if not rp["deleted_at"]:
                                        raw = rp["attachments"]
                                        rp_atts = _json.loads(raw) if isinstance(raw, str) else (raw or [])
                                    reply_preview = {
                                        "id": str(reply_uuid),
                                        "sender_name": rp["sender_name"],
                                        "content": "" if rp["deleted_at"] else rp["content"],
                                        "attachments": rp_atts,
                                    }

                            # Parse + resolve @mentions BEFORE broadcasting so the
                            # payload carries the resolved IDs for client-side chip
                            # rendering. Email enqueue happens below; emails are
                            # rate-limited and only send to offline users.
                            from app.matcha.services.mentions import (
                                parse_mentions, resolve_mentions,
                            )
                            mention_handles = parse_mentions(row["content"])
                            mentioned_users = await resolve_mentions(
                                conn, ch_uuid, mention_handles, exclude_user_id=user.id,
                            ) if mention_handles else []
                            mentioned_user_ids = [str(m["id"]) for m in mentioned_users]

                            await manager.broadcast_message(room_key, {
                                "id": str(row["id"]),
                                "channel_id": str(row["channel_id"]),
                                "sender_id": str(row["sender_id"]),
                                "sender_name": user.name,
                                "sender_avatar_url": user.avatar_url,
                                "content": row["content"],
                                "attachments": broadcast_attachments,
                                "reply_to_id": str(reply_uuid) if reply_uuid else None,
                                "reply_preview": reply_preview,
                                "reactions": [],
                                "created_at": row["created_at"].isoformat(),
                                "edited_at": None,
                                "mentioned_user_ids": mentioned_user_ids,
                                "client_message_id": client_message_id,
                            })

                            # Off-load offline-email check to Celery so the WS
                            # hot path stays fast. Worker re-checks online state
                            # via Redis before sending.
                            if mentioned_user_ids:
                                try:
                                    from app.workers.tasks.mention_email import send_mention_email
                                    send_mention_email.delay(
                                        message_id=str(row["id"]),
                                        channel_id=str(row["channel_id"]),
                                        sender_id=str(user.id),
                                        sender_name=user.name,
                                        content=row["content"] or "",
                                        mentioned_user_ids=mentioned_user_ids,
                                    )
                                except Exception:
                                    logger.exception("Failed to enqueue mention_email")

                            # In-app notifications for non-sender members
                            try:
                                from ...matcha.services import notification_service as _notif_svc
                                _ch_name = await conn.fetchval(
                                    "SELECT name FROM channels WHERE id = $1", ch_uuid
                                )
                                _members = await conn.fetch(
                                    """
                                    SELECT cm.user_id, COALESCE(c.company_id, e.org_id) AS company_id
                                    FROM channel_members cm
                                    JOIN users u ON u.id = cm.user_id
                                    LEFT JOIN clients c ON c.user_id = u.id
                                    LEFT JOIN employees e ON e.user_id = u.id
                                    WHERE cm.channel_id = $1 AND cm.user_id != $2
                                      AND cm.removed_for_inactivity IS NOT TRUE
                                    """,
                                    ch_uuid, user.id,
                                )
                                _preview = (row["content"] or "")[:80]
                                import asyncio as _aio
                                for _m in _members:
                                    if _m["company_id"]:
                                        _aio.create_task(_notif_svc.create_notification(
                                            user_id=_m["user_id"],
                                            company_id=_m["company_id"],
                                            type="channel_message",
                                            title=f"#{_ch_name}",
                                            body=f"{user.name}: {_preview}",
                                            link="/work",
                                        ))
                            except Exception:
                                pass
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Not a member of this channel",
                            })

            elif msg_type == "typing":
                channel_id = data.get("channel_id")
                if channel_id:
                    await manager.broadcast_typing(str(channel_id), user)

            elif msg_type == "voice_join":
                channel_id = data.get("channel_id")
                if channel_id:
                    await handle_voice_join(manager, user.id, user.name, str(channel_id), str(channel_id))

            elif msg_type == "voice_leave":
                channel_id = data.get("channel_id")
                if channel_id:
                    await handle_voice_leave(manager, user.id, user.name, str(channel_id), str(channel_id))

            elif msg_type == "voice_offer":
                await handle_voice_offer(manager, user.id, data)

            elif msg_type == "voice_answer":
                await handle_voice_answer(manager, user.id, data)

            elif msg_type == "voice_ice":
                await handle_voice_ice(manager, user.id, data)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"[Channel WS] Error: {e}")
    finally:
        await manager.disconnect(websocket, user.id)
        # Only clear the online key if this was the user's last active WS.
        # manager.active_connections drops the user_id when the set goes empty.
        if user.id not in manager.active_connections:
            await _mark_offline(user.id)

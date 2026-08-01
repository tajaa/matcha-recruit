# Channels reliability + scale pass — implementation-ready spec

## Context

Two reported problems: (1) same account on two computers sees different messages — some never appear on the other device; (2) channels must handle hundreds of concurrent chatters with minimal delay. Audit found confirmed root causes on both sides. Espresso (Mac) already has the client-side fixes (durable outbox, merge-refetch, load-older, focus reconnect); the web client has none. Backend has a critical lock self-deadlock and an O(N)-round-trips-per-message notification fanout.

Scope: A (correctness) + B (scale/availability) + C (read-state/mute). Branch: `matcha/m-work-websocket` (already on it). **No migrations** — `channel_members.is_muted` already exists (dead schema until now). Espresso needs **zero changes**: its WS dispatch has `default: break` (ChannelsWebSocket.swift:502), so new frame types are ignored; REST additions are additive.

Files touched:
- `server/app/werk/routes/channels_ws.py` (most changes)
- `server/app/werk/routes/channels.py`
- `server/app/matcha/services/notification_service.py`
- `server/app/core/services/apns_service.py`
- NEW `server/tests/werk/test_channels_manager.py` (create `tests/werk/` dir)
- `client/src/work/api/baseSocket.ts`, `channelSocket.ts`, `channels.ts`
- NEW `client/src/work/api/channelMessages.ts` + `channelMessages.test.ts` (vitest — `npm run test:run`)
- `client/src/work/pages/ChannelView/useChannelSocket.ts`, `useChannelView.ts`, `MessageList.tsx`, `ChannelHeader.tsx`
- `client/src/work/hooks/useChannelNotifications.ts`

Execution order = section order below. Commit after each phase (P1, P2, P3, P4, P5).

---

# PHASE 1 — backend availability core (`channels_ws.py`)

## 1.1 CRITICAL deadlock: never `await _broadcast_to_room` while holding `manager.lock`

`manager.lock` is a non-reentrant `asyncio.Lock`. `disconnect` (:1112), `join_room` (:1132), `leave_room` (:1150) all await `_broadcast_to_room` INSIDE `async with self.lock`. When Redis is None or publish raises, `_broadcast_to_room` falls back to `_local_broadcast_to_room`, which re-acquires the lock at :1265 when any socket send fails → permanent deadlock, total WS outage on the worker.

**Replace the three methods exactly:**

```python
    async def disconnect(self, websocket: WebSocket, user_id: UUID):
        # Collect broadcasts under the lock, send after release — the lock is
        # non-reentrant and _local_broadcast_to_room re-acquires it for dead-
        # socket cleanup, so awaiting a broadcast while holding it deadlocks
        # the whole manager the moment Redis is down AND a socket is dead.
        to_broadcast: list[tuple[str, dict]] = []
        async with self.lock:
            self.last_seen.pop(websocket, None)
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
                                if not self.room_members[room]:
                                    # never deleted before — slow leak, one
                                    # entry per channel ever joined
                                    del self.room_members[room]
                                if user:
                                    to_broadcast.append((room, {
                                        "type": "user_left",
                                        "room": room,
                                        "user": user.model_dump(mode='json'),
                                    }))
        for room, payload in to_broadcast:
            await self._broadcast_to_room(room, payload, exclude_user=user_id)

    async def join_room(self, user_id: UUID, room_key: str):
        payload = None
        async with self.lock:
            if room_key not in self.room_members:
                self.room_members[room_key] = set()
            was_in_room = user_id in self.room_members[room_key]
            self.room_members[room_key].add(user_id)
            if user_id in self.user_rooms:
                self.user_rooms[user_id].add(room_key)
            if not was_in_room and user_id in self.users:
                payload = {
                    "type": "user_joined",
                    "room": room_key,
                    "user": self.users[user_id].model_dump(mode='json'),
                }
        if payload:
            await self._broadcast_to_room(room_key, payload, exclude_user=user_id)

    async def leave_room(self, user_id: UUID, room_key: str):
        payload = None
        async with self.lock:
            if room_key in self.room_members:
                self.room_members[room_key].discard(user_id)
                if not self.room_members[room_key]:
                    del self.room_members[room_key]
            if user_id in self.user_rooms:
                self.user_rooms[user_id].discard(room_key)
            if user_id in self.users:
                payload = {
                    "type": "user_left",
                    "room": room_key,
                    "user": self.users[user_id].model_dump(mode='json'),
                }
        if payload:
            await self._broadcast_to_room(room_key, payload)
```

(`self.last_seen` comes from 1.6 — add it in `__init__` first so this compiles.)

## 1.2 Origin-tagged local-first delivery (Redis outage must not drop messages)

Today `_broadcast_to_room`/`send_to_user` ONLY publish to Redis; the origin worker hears its own message via subscriber loopback. Subscriber down (2s restart window :1341, Redis outage) ⇒ silent total loss on that worker, sender's echo included.

**Module level, near `_FANOUT_CHANNEL` (:1042):**

```python
from uuid import uuid4  # add to existing uuid import line: from uuid import UUID, uuid4

# Identifies THIS worker's envelopes on the fanout channel. Local delivery now
# happens synchronously at publish time (local-first), so the subscriber must
# skip envelopes this worker published or every local socket gets doubles.
_WORKER_ID = uuid4().hex


def _should_process_envelope(envelope: dict, worker_id: str) -> bool:
    """Pure: process an envelope unless this worker published it. Envelopes
    from pre-deploy workers carry no 'origin' — process those (worst case a
    brief double-delivery during a rolling restart; client dedups by id)."""
    return envelope.get("origin") != worker_id
```

**Replace `send_to_user` (:1187-1202) and `_broadcast_to_room` (:1222-1243):**

```python
    async def send_to_user(self, user_id: UUID, message: dict):
        """Send to a user's connections on every worker. Local sockets are
        written directly (survives a Redis/subscriber outage); the Redis
        publish only exists to reach the OTHER worker's sockets."""
        await self._local_send_to_user(user_id, message)
        redis = get_redis_cache()
        if redis is None:
            return
        envelope = {
            "kind": "user",
            "user_id": str(user_id),
            "message": message,
            "origin": _WORKER_ID,
        }
        try:
            await redis.publish(_FANOUT_CHANNEL, json.dumps(envelope, default=str))
        except Exception:
            logger.exception("Redis publish failed in send_to_user (local delivery already done)")

    async def _broadcast_to_room(
        self, room_key: str, message: dict, exclude_user: UUID = None,
        channel: str = _FANOUT_CHANNEL,
    ):
        """Fan-out to every WS member of a room across all uvicorn workers.
        Local-first: this worker's sockets are written directly, then one
        Redis publish reaches the other worker. `channel` lets high-frequency
        event classes (typing) ride their own pub/sub channel so they can't
        head-of-line-block message delivery in the serial subscriber."""
        await self._local_broadcast_to_room(room_key, message, exclude_user=exclude_user)
        redis = get_redis_cache()
        if redis is None:
            return
        envelope = {
            "kind": "room",
            "room": room_key,
            "message": message,
            "exclude_user": str(exclude_user) if exclude_user else None,
            "origin": _WORKER_ID,
        }
        try:
            await redis.publish(channel, json.dumps(envelope, default=str))
        except Exception:
            logger.exception("Redis publish failed in _broadcast_to_room (local delivery already done)")
```

**Subscriber loop (:1281-1348) — three edits:**

1. Right after `envelope = json.loads(payload)` succeeds, add:
```python
                if not _should_process_envelope(envelope, _WORKER_ID):
                    continue
```
2. Add a new envelope kind (used by 1.4) inside the `kind` dispatch, after the `"user"` branch:
```python
                elif kind == "users":
                    # Multicast: one envelope, many recipients (bulk notify).
                    msgs = envelope.get("messages") or {}
                    for uid_raw, m in msgs.items():
                        try:
                            uid = UUID(uid_raw)
                        except (ValueError, TypeError):
                            continue
                        await manager._local_send_to_user(uid, m)
```
   Note: the top of the loop has `msg = envelope.get("message"); if msg is None: continue` — a `"users"` envelope has no `message` key. Change that guard to:
```python
                msg = envelope.get("message")
                if msg is None and kind != "users":
                    continue
```
3. Busy-loop guard: `pubsub.listen()` ending WITHOUT raising falls to `finally` and re-subscribes with no sleep. After the `async for` block (still inside `try`), add:
```python
            # listen() ended without raising (connection closed cleanly) —
            # don't spin through resubscribe at full speed.
            await asyncio.sleep(1)
```

**Refactor for 1.7:** extract the whole per-envelope body (skip check + kind dispatch) into a module-level `async def _process_envelope(envelope: dict) -> None`, and have the loop call it. The typing subscriber (1.7) reuses it verbatim.

## 1.3 Persisted-but-never-broadcast band (:1795-1949)

After the INSERT commits (:1794), ~95 unguarded lines run before `broadcast_message` (:1889). Any exception there (attachments `json.loads`, activity UPDATEs, reply-preview SELECT, `resolve_mentions` DB call) ⇒ row persisted, nobody notified, sender's socket killed by the outer handler. Mechanical fix — pre-initialize, wrap each segment, broadcast unconditionally:

Immediately after `is_new_message = bool(row["inserted"])` (:1795), restructure the band as:

```python
                            is_new_message = bool(row["inserted"])
                            # Everything between the committed INSERT and the
                            # broadcast is best-effort: a failure here must
                            # degrade the payload (no preview / no mentions),
                            # never strand a persisted row unbroadcast and
                            # kill the sender's socket.
                            broadcast_attachments: list = []
                            reply_preview = None
                            mention_handles: list = []
                            mentioned_user_ids: list[str] = []
                            try:
                                if is_new_message:
                                    await conn.execute(
                                        "UPDATE channels SET updated_at = NOW() WHERE id = $1",
                                        ch_uuid,
                                    )
                                    await conn.execute(
                                        "UPDATE channel_members SET last_contributed_at = NOW() WHERE channel_id = $1 AND user_id = $2",
                                        ch_uuid, user.id,
                                    )
                            except Exception:
                                logger.warning("[Channel WS] activity bump failed", exc_info=True)
                            try:
                                broadcast_attachments = _json.loads(row["attachments"]) if row["attachments"] else []
                            except Exception:
                                logger.warning("[Channel WS] attachments parse failed", exc_info=True)
```

Then keep the existing `_bg_sync_channel_attachments` spawn as-is; wrap the reply-preview block (`if reply_uuid: rp = await conn.fetchrow(...)` through building `reply_preview`) in its own `try/except` logging `"[Channel WS] reply preview failed"`; wrap the mentions block (`from ... import parse_mentions, resolve_mentions` through `mentioned_user_ids = [...]`) in a `try/except` logging `"[Channel WS] mention resolve failed"`. The EMS decision + spawn (pure + fire-and-forget) and the broadcast stay outside any try. Everything after the broadcast (mention email, notify block) already has its own guards — but change the notify block's bare `except Exception: pass` (:1948-1949) to `logger.warning("[Channel WS] notify fanout setup failed", exc_info=True)`.

**Also:** the endpoint's catch-all `logger.error(f"[Channel WS] Error: {e}")` (:1971) → `logger.error("[Channel WS] Error: %s", e, exc_info=True)`.

## 1.4 Batched notification fanout (the 100s-of-users blocker)

Current: `_notify_channel_members` (:1005-1027) awaits `notification_service.create_notification` per member sequentially — each = 1 pool acquire + 1 manager-lock log + 1 Redis publish + 1 Redis presence GET + (offline) another pool acquire. 200-member channel ≈ ~400 remote DB RTs + ~400 Redis RTs per message, all through the serial subscriber.

### 1.4a `notification_service.py` — add bulk sibling (below `create_notification`)

```python
async def create_notifications_bulk(
    *,
    user_ids: list[UUID],
    company_ids: list[UUID],
    type: str,
    title: str,
    body: Optional[str] = None,
    link: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Batched sibling of create_notification for N-recipient fan-outs
    (channel messages). One INSERT for the bell rows, one WS multicast
    envelope, one batched presence check + APNs pass — replaces N sequential
    create_notification calls (2N pool acquires + 2N Redis RTs) on the
    channels hot path. user_ids/company_ids are parallel arrays.
    No email path — channel messages never email."""
    if not user_ids:
        return
    import json as _json
    meta_json = _json.dumps(metadata or {})
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            INSERT INTO mw_notifications (user_id, company_id, type, title, body, link, metadata)
            SELECT t.u, t.c, $3, $4, $5, $6, $7::jsonb
            FROM unnest($1::uuid[], $2::uuid[]) AS t(u, c)
            RETURNING id, user_id, type, title, body, link, metadata, created_at
            """,
            user_ids, company_ids, type, title, body, link, meta_json,
        )

    # One multicast WS envelope for every recipient's bell (same lazy manager
    # import edge create_notification already uses — no new import kind).
    try:
        from ...werk.routes.channels_ws import manager as _ch_manager
        payloads = {
            row["user_id"]: {
                "type": "notification",
                "notification": {
                    "id": str(row["id"]),
                    "type": row["type"],
                    "title": row["title"],
                    "body": row["body"],
                    "link": row["link"],
                    "metadata": row["metadata"],
                    "is_read": False,
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                },
            }
            for row in rows
        }
        await _ch_manager.send_to_users(payloads)
    except Exception as e:
        logger.warning("Bulk notification WS push failed: %s", e)

    # APNs only for users with no live socket, resolved in ONE presence pass.
    try:
        from ...core.services import apns_service
        offline = await apns_service.get_offline_users(user_ids)
        if offline:
            await apns_service.send_to_many(
                offline, title, body,
                {"type": type, "link": link, "metadata": metadata or {}},
            )
    except Exception as e:
        logger.warning("Bulk APNs push failed: %s", e)
```

### 1.4b `channels_ws.py` — manager multicast method (next to `send_to_user`)

```python
    async def send_to_users(self, payloads: "dict[UUID, dict]") -> None:
        """Multicast: per-user payloads in ONE fanout envelope. Local sockets
        are written directly; one Redis publish covers the other worker
        (subscriber kind 'users')."""
        if not payloads:
            return
        for uid, message in payloads.items():
            await self._local_send_to_user(uid, message)
        redis = get_redis_cache()
        if redis is None:
            return
        envelope = {
            "kind": "users",
            "messages": {str(uid): m for uid, m in payloads.items()},
            "origin": _WORKER_ID,
        }
        try:
            await redis.publish(_FANOUT_CHANNEL, json.dumps(envelope, default=str))
        except Exception:
            logger.exception("Redis publish failed in send_to_users (local delivery already done)")
```

### 1.4c `apns_service.py` — batched presence + push

Read the file first; it has `is_user_online` (Redis GET on `channels_ws:online:{uid}`) and `send_to_user` (pool acquire → `SELECT token FROM device_tokens WHERE user_id = $1` → per-token APNs). Add:

```python
async def get_offline_users(user_ids: list[UUID]) -> list[UUID]:
    """Batched is_user_online: one MGET instead of N GETs. Redis unavailable
    ⇒ treat everyone as offline (same failure posture as is_user_online)."""
    redis = get_redis_cache()
    if redis is None or not user_ids:
        return list(user_ids)
    try:
        vals = await redis.mget([f"channels_ws:online:{u}" for u in user_ids])
    except Exception:
        return list(user_ids)
    return [u for u, v in zip(user_ids, vals) if not v]


async def send_to_many(user_ids: list[UUID], title, body, data) -> None:
    """Batched send_to_user: ONE device_tokens query for all recipients."""
    if not user_ids:
        return
    # (mirror send_to_user's config/no-op guards here)
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT user_id, token FROM device_tokens WHERE user_id = ANY($1)",
            user_ids,
        )
    for r in rows:
        # reuse the existing single-token send helper send_to_user delegates to
        ...
```
(Match the exact key prefix/config guards already in the file — copy them, don't re-derive.)

### 1.4d `channels_ws.py` — rewrite `_notify_channel_members` + mute filter + name cache

Replace `_notify_channel_members` body:

```python
async def _notify_channel_members(
    members: list, ch_name: Optional[str], sender_name: str, preview: str, channel_id_str: str,
) -> None:
    """Bell fan-out for a new channel message — ONE batched call (see
    notification_service.create_notifications_bulk) instead of a sequential
    per-member loop that cost ~2 pool acquires + ~2 Redis RTs per member."""
    from app.matcha.services import notification_service as notif_svc
    targets = [(m["user_id"], m["company_id"]) for m in members if m["company_id"]]
    if not targets:
        return
    try:
        await notif_svc.create_notifications_bulk(
            user_ids=[t[0] for t in targets],
            company_ids=[t[1] for t in targets],
            type="channel_message",
            title=f"#{ch_name}",
            body=f"{sender_name}: {preview}",
            link="/work",
            metadata={"channel_id": channel_id_str},
        )
    except Exception:
        logger.warning("bulk channel_message notification failed", exc_info=True)
```

In the WS message handler's notify block (:1927-1947):
- The members query gains mute status + mention exception (Slack semantics — mute silences the bell EXCEPT direct @mentions; the live in-channel message frame is unaffected by mute):
```python
                                    _members = await conn.fetch(
                                        """
                                        SELECT cm.user_id, cm.is_muted,
                                               COALESCE(c.company_id, e.org_id) AS company_id
                                        FROM channel_members cm
                                        JOIN users u ON u.id = cm.user_id
                                        LEFT JOIN clients c ON c.user_id = u.id
                                        LEFT JOIN employees e ON e.user_id = u.id
                                        WHERE cm.channel_id = $1 AND cm.user_id != $2
                                          AND cm.removed_for_inactivity IS NOT TRUE
                                        """,
                                        ch_uuid, user.id,
                                    )
                                    _notify_targets = [
                                        m for m in _members
                                        if not m["is_muted"] or str(m["user_id"]) in mentioned_user_ids
                                    ]
                                    _preview = (row["content"] or "")[:80]
                                    _spawn_bg(_notify_channel_members(
                                        list(_notify_targets), _ch_name, user.name, _preview, str(ch_uuid),
                                    ))
```
- Channel-name per-message SELECT (:1929) → module TTL cache:
```python
from cachetools import TTLCache
_channel_name_cache: TTLCache = TTLCache(maxsize=2048, ttl=60)

async def _get_channel_name(conn, ch_uuid: UUID) -> Optional[str]:
    """60s-cached channel name — was a per-message SELECT on the send path."""
    key = str(ch_uuid)
    if key in _channel_name_cache:
        return _channel_name_cache[key]
    name = await conn.fetchval("SELECT name FROM channels WHERE id = $1", ch_uuid)
    _channel_name_cache[key] = name
    return name
```
and `_ch_name = await _get_channel_name(conn, ch_uuid)` at the callsite. (`cachetools` already a dependency — provider.py uses it.)

## 1.5 WS send rate limit — in-memory token bucket

Module level (near `_TokenBucket` tests will import it, keep public-ish name `_TokenBucket`):

```python
import time  # add to stdlib imports

class _TokenBucket:
    """Per-socket send limiter: burst of 10, refill 1/s. Pure — caller
    supplies `now` (time.monotonic()) so tests need no clock patching.
    In-memory per worker: a reconnect resets the bucket, which is fine —
    the point is stopping a hot loop, not accounting."""
    __slots__ = ("burst", "refill", "tokens", "updated")

    def __init__(self, burst: int = 10, refill_per_sec: float = 1.0):
        self.burst = burst
        self.refill = refill_per_sec
        self.tokens = float(burst)
        self.updated: Optional[float] = None

    def allow(self, now: float) -> bool:
        if self.updated is not None:
            self.tokens = min(float(self.burst), self.tokens + (now - self.updated) * self.refill)
        self.updated = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False
```

In `channel_websocket`, right after `await manager.connect(...)`: `rate = _TokenBucket()`. At the TOP of the `elif msg_type == "message":` branch (before any DB work, right after reading `channel_id`/`client_message_id`):

```python
                if not rate.allow(time.monotonic()):
                    # Never kill the socket over rate — error frame + drop.
                    # Client-side onServerError removes the pending row and
                    # toasts (scoped by client_message_id).
                    await websocket.send_json({
                        "type": "error",
                        "code": "rate_limited",
                        "message": "You're sending messages too quickly — give it a moment.",
                        "channel_id": channel_id,
                        "client_message_id": client_message_id,
                    })
                    continue
```

(Order note: read `client_message_id` from `data` before this check so the error frame can carry it.)

## 1.6 Liveness deadline — server finally uses the pongs

Manager `__init__` gains:
```python
        self.last_seen: Dict[WebSocket, float] = {}
```
Manager method:
```python
    def touch(self, websocket: WebSocket) -> None:
        """Stamp last-activity for the liveness reaper. Plain dict write —
        single event loop, no await, no lock needed."""
        self.last_seen[websocket] = time.monotonic()
```
Call sites: inside `connect()` (after `self.users[user.id] = user`, still under lock: `self.last_seen[websocket] = time.monotonic()`), and in the receive loop right after `data = await websocket.receive_json()`: `manager.touch(websocket)`. (`disconnect` already pops it — 1.1.)

Constant next to `_SERVER_PING_INTERVAL_SECONDS`:
```python
# A healthy client touches at least every 25-30s (its own ping, or its pong
# reply to server_ping). 90s = 3 missed cycles ⇒ the socket is a zombie the
# 5s send timeout can't see (TCP buffer still accepting writes).
_LIVENESS_DEADLINE_SECONDS = 90
```

In `_server_ping_loop`, after building `targets`, before the gather:
```python
            now = time.monotonic()
            stale = [
                (uid, ws) for uid, ws in targets
                if now - manager.last_seen.get(ws, now) > _LIVENESS_DEADLINE_SECONDS
            ]
            for _, ws in stale:
                try:
                    await asyncio.wait_for(ws.close(), timeout=2)
                except Exception:
                    pass
            if stale:
                stale_set = {id(ws) for _, ws in stale}
                targets = [(uid, ws) for uid, ws in targets if id(ws) not in stale_set]
```
(Closing drives the peer's receive loop into `WebSocketDisconnect` → full `disconnect()` cleanup — same mechanism `_safe_send_text` relies on.)

## 1.7 Typing off the message fanout channel

```python
_TYPING_CHANNEL = "channels:typing:fanout"
```
`broadcast_typing` (:1170) passes it through:
```python
    async def broadcast_typing(self, room_key: str, user: ChannelUser):
        # Typing is the highest-frequency event class; it rides its own
        # pub/sub channel so a typing storm can't head-of-line-block message
        # delivery in the serial subscriber loop.
        await self._broadcast_to_room(room_key, {
            "type": "typing",
            "room": room_key,
            "user": user.model_dump(mode='json'),
        }, exclude_user=user.id, channel=_TYPING_CHANNEL)
```
Second subscriber: `_typing_subscriber_loop()` — copy `_fanout_subscriber_loop` but subscribe `_TYPING_CHANNEL` and call the shared `_process_envelope` (extracted in 1.2). `start_fanout_subscriber()` starts BOTH tasks (add module global `_typing_subscriber_task`, same idempotence + same `stop_fanout_subscriber` cancellation treatment). No `main.py` change — it already calls `start_fanout_subscriber()`.

## 1.8 `mark_read` WS frame + `channel_read` push (Part C server half)

New branch in the receive loop after `elif msg_type == "typing":` block:

```python
            elif msg_type == "mark_read":
                # Client sends this (debounced) while sitting in a visible
                # channel as messages arrive — otherwise last_read_at only
                # advances on GET /channels/{id} and phantom unread piles up.
                channel_id = data.get("channel_id")
                rk = _room_key(channel_id) if channel_id else None
                if rk:
                    try:
                        async with get_connection() as conn:
                            await conn.execute(
                                "UPDATE channel_members SET last_read_at = NOW() WHERE channel_id = $1 AND user_id = $2",
                                UUID(rk), user.id,
                            )
                        # Zero the badge on this user's OTHER devices too.
                        await manager.send_to_user(user.id, {
                            "type": "channel_read",
                            "channel_id": rk,
                            "user_id": str(user.id),
                        })
                    except Exception:
                        logger.warning("[Channel WS] mark_read failed", exc_info=True)
```

## Phase 1 tests — NEW `server/tests/werk/test_channels_manager.py`

```python
"""ChannelConnectionManager availability invariants + pure helpers.

    cd server && ./venv/bin/python -m pytest tests/werk/ -q
"""
import asyncio
import time
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.werk.routes import channels_ws as ws_mod
from app.werk.routes.channels_ws import (
    ChannelConnectionManager, ChannelUser, _should_process_envelope, _TokenBucket,
)


def _fake_ws(send_fails: bool = False):
    ws = AsyncMock()
    if send_fails:
        ws.send_text = AsyncMock(side_effect=RuntimeError("dead socket"))
    return ws


def _user(uid):
    return ChannelUser(id=uid, name="T", email="t@example.com", role="client")


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch):
    # Redis-down is exactly the config under test (and dev without Redis).
    # Patch the DEFINING module (repo patch rule).
    monkeypatch.setattr(ws_mod, "get_redis_cache", lambda: None)


class TestNoDeadlock:
    @pytest.mark.asyncio
    async def test_join_room_completes_with_redis_down_and_dead_socket(self):
        # Pre-fix: join_room awaited _broadcast_to_room while HOLDING
        # manager.lock; Redis-down fell back to _local_broadcast_to_room,
        # whose dead-socket cleanup re-acquires the (non-reentrant) lock —
        # permanent deadlock, total WS outage on the worker. wait_for is the
        # regression detector: pre-fix this times out.
        m = ChannelConnectionManager()
        uid_dead, uid_new = uuid4(), uuid4()
        dead = _fake_ws(send_fails=True)
        await m.connect(dead, _user(uid_dead))
        await m.join_room(uid_dead, "room1")
        live = _fake_ws()
        await m.connect(live, _user(uid_new))
        await asyncio.wait_for(m.join_room(uid_new, "room1"), timeout=5)

    @pytest.mark.asyncio
    async def test_disconnect_completes_and_prunes_empty_room(self):
        m = ChannelConnectionManager()
        uid = uuid4()
        ws = _fake_ws()
        await m.connect(ws, _user(uid))
        await m.join_room(uid, "room1")
        await asyncio.wait_for(m.disconnect(ws, uid), timeout=5)
        assert "room1" not in m.room_members  # empty-room leak fixed
        assert ws not in m.last_seen


class TestLocalFirstDelivery:
    @pytest.mark.asyncio
    async def test_broadcast_delivers_locally_when_redis_none(self):
        m = ChannelConnectionManager()
        uid = uuid4()
        ws = _fake_ws()
        await m.connect(ws, _user(uid))
        await m.join_room(uid, "room1")
        await m._broadcast_to_room("room1", {"type": "message", "x": 1})
        ws.send_text.assert_awaited()

    def test_should_process_envelope_skips_own_origin(self):
        assert _should_process_envelope({"origin": "w1"}, "w1") is False
        assert _should_process_envelope({"origin": "w2"}, "w1") is True
        # Pre-deploy envelope without origin: process (rolling restart).
        assert _should_process_envelope({}, "w1") is True


class TestTokenBucket:
    def test_burst_then_deny(self):
        b = _TokenBucket(burst=10, refill_per_sec=1.0)
        t = 100.0
        assert all(b.allow(t) for _ in range(10))
        assert b.allow(t) is False

    def test_refill_one_per_second(self):
        b = _TokenBucket(burst=10, refill_per_sec=1.0)
        t = 100.0
        for _ in range(10):
            b.allow(t)
        assert b.allow(t + 0.5) is False
        assert b.allow(t + 1.6) is True   # ~1.1 tokens refilled since t+0.5

    def test_refill_caps_at_burst(self):
        b = _TokenBucket(burst=10, refill_per_sec=1.0)
        b.allow(0.0)
        assert b.allow(10_000.0) is True
        assert b.tokens <= 10.0
```

**Verify Phase 1:** `cd server && ./venv/bin/python -m pytest tests/werk/ -q` (new file passes), then `./venv/bin/python -m pytest tests/ -q -x --ignore=tests/matcha_work/test_blog_pdf_export.py 2>&1 | tail -5` for no collateral. `python3 -m py_compile app/werk/routes/channels_ws.py app/werk/routes/channels.py app/matcha/services/notification_service.py app/core/services/apns_service.py`.

---

# PHASE 2 — backend REST contract (`channels.py`) — client work depends on this

## 2.1 `client_message_id` in REST payloads

The WS broadcast carries `client_message_id` but REST omits it, so the client can never reconcile a pending row against a refetch. Three edits:

1. `_MSG_SELECT` (:200): add `m.client_message_id,` after `m.message_type,`.
2. `ChannelMessage` model (:72): add field
```python
    # Sender's optimistic-UI correlation id — REST now returns it so a
    # reconnect refetch can reconcile a still-pending local row against the
    # persisted copy (WS echo already carried it).
    client_message_id: Optional[UUID] = None
```
3. `_row_to_message` (:128): add `client_message_id=m.get("client_message_id"),` (asyncpg Record supports `.get`, already used at :109).

## 2.2 Deterministic order + composite cursor

1. `_msg_query` default (:214): `order: str = "m.created_at DESC, m.id DESC"` — `created_at` is `NOW()` = transaction start; autocommit burst inserts collide at microsecond granularity and an untiebroken sort is nondeterministic (same defect class as server/CLAUDE.md's "every LIMIT 1 needs a deterministic ORDER BY").
2. `get_channel_messages` (:1312): add param `before_id: Optional[UUID] = Query(default=None)` and replace the cursor branch:
```python
        if before:
            try:
                before_dt = datetime.fromisoformat(before)
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail="Invalid 'before' cursor format")
            if before_id:
                # Composite keyset cursor — strict created_at-only comparison
                # skips rows sharing the boundary timestamp.
                rows = await conn.fetch(
                    _msg_query("m.channel_id = $1 AND (m.created_at, m.id) < ($2, $3)", limit_param="$4"),
                    channel_id, before_dt, before_id, limit,
                )
            else:
                # Legacy cursor (Espresso) — unchanged behavior.
                rows = await conn.fetch(
                    _msg_query("m.channel_id = $1 AND m.created_at < $2", limit_param="$3"),
                    channel_id, before_dt, limit,
                )
```

## 2.3 `channel_read` push from `get_channel` + mute route + `is_muted` in list

1. In `get_channel`'s mark-read block (:1274-1278), after the UPDATE:
```python
        if is_member:
            await conn.execute(
                "UPDATE channel_members SET last_read_at = NOW() WHERE channel_id = $1 AND user_id = $2",
                channel_id, current_user.id,
            )
            # Zero this user's badge on their other devices. Best-effort.
            try:
                from .channels_ws import manager as _ws_manager
                await _ws_manager.send_to_user(current_user.id, {
                    "type": "channel_read",
                    "channel_id": str(channel_id),
                    "user_id": str(current_user.id),
                })
            except Exception:
                pass
```
(channels.py already imports `manager` from channels_ws for the delete/edit/react broadcasts — match that import's placement/style.)

2. Mute toggle route (place near the other member-scoped POSTs; `channel_members.is_muted` exists in schema, previously dead):
```python
class MuteRequest(BaseModel):
    muted: bool


@router.post("/{channel_id}/mute")
async def set_channel_mute(
    channel_id: UUID,
    body: MuteRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Per-member mute: silences the bell/push/sound for this channel except
    direct @mentions (enforced in the WS notify fan-out). Does not affect
    live message delivery to an open view."""
    async with get_connection() as conn:
        updated = await conn.fetchval(
            "UPDATE channel_members SET is_muted = $3 WHERE channel_id = $1 AND user_id = $2 RETURNING user_id",
            channel_id, current_user.id, body.muted,
        )
    if not updated:
        raise HTTPException(status_code=404, detail="Not a member of this channel")
    return {"ok": True, "muted": body.muted}
```
ROUTE-ORDER WARNING: `@router.get("/{channel_id}")` etc. are path-param routes — FastAPI matches in registration order; a literal-suffix route like `/{channel_id}/mute` is unambiguous, no conflict. Just keep it after the models it uses.

3. `list_channels` SELECT (:372): add `COALESCE(cm.is_muted, false) AS is_muted,` and `ChannelSummary` (:248): `is_muted: bool = False`. Row-construction for ChannelSummary — find where rows map to the model (immediately after the query) and pass `is_muted=r["is_muted"]` if it's explicit field-by-field (check; if it's `ChannelSummary(**dict(r))`-style it picks up automatically).

**Verify Phase 2:** py_compile + run existing werk/channel REST tests if any (`grep -rl "get_channel_messages\|/channels" server/tests | head`), plus `pytest tests/werk/ -q`.

---

# PHASE 3 — web client correctness

## 3.1 NEW `client/src/work/api/channelMessages.ts` — pure merge/ordering module

```ts
import type { ChannelMessage } from './channels'

/**
 * (created_at, id) comparator — the server's ORDER BY, applied client-side so
 * every device converges on ONE order regardless of WS arrival order (two
 * uvicorn workers ⇒ near-simultaneous messages can arrive in different orders
 * on different sockets). Pending rows carry a local ISO timestamp and sort
 * where they were sent; a small clock skew is acceptable — the echo replaces
 * them with the server timestamp.
 */
export function compareMessages(a: ChannelMessage, b: ChannelMessage): number {
  if (a.created_at !== b.created_at) return a.created_at < b.created_at ? -1 : 1
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0
}

/**
 * Union of the in-memory list and a REST page (reconnect catch-up or older-
 * page prepend). Never clobbers: a WS message that landed while the fetch was
 * in flight survives (the old reconnect handler replaced the array, erasing
 * it on this device only — the reported cross-device divergence). Pending
 * rows reconcile by client_message_id, which REST now returns.
 */
export function mergeMessages(prev: ChannelMessage[], fetched: ChannelMessage[]): ChannelMessage[] {
  const fetchedById = new Set(fetched.map((m) => m.id))
  const fetchedByCmid = new Set(
    fetched.filter((m) => m.client_message_id).map((m) => m.client_message_id as string),
  )
  const out = fetched.slice()
  for (const m of prev) {
    if (fetchedById.has(m.id)) continue // server copy wins over local copy
    if (m.pending && m.client_message_id && fetchedByCmid.has(m.client_message_id)) continue // landed
    out.push(m) // WS arrival mid-fetch, an older page already loaded, or an unlanded pending
  }
  out.sort(compareMessages)
  return out
}

/** Insert one live WS message: reconcile the sender's optimistic pending row
 * by cmid, else dedup by id, always keeping (created_at, id) order. */
export function upsertMessage(prev: ChannelMessage[], msg: ChannelMessage): ChannelMessage[] {
  if (msg.client_message_id) {
    const idx = prev.findIndex((m) => m.client_message_id === msg.client_message_id && m.pending)
    if (idx >= 0) {
      const next = prev.slice()
      next[idx] = msg
      next.sort(compareMessages)
      return next
    }
  }
  if (prev.some((m) => m.id === msg.id)) return prev
  const next = [...prev, msg]
  next.sort(compareMessages)
  return next
}
```

NEW `client/src/work/api/channelMessages.test.ts` (vitest, colocated like `baseSocket.test.ts`):

```ts
import { describe, expect, it } from 'vitest'
import { compareMessages, mergeMessages, upsertMessage } from './channelMessages'
import type { ChannelMessage } from './channels'

function msg(over: Partial<ChannelMessage>): ChannelMessage {
  return {
    id: 'id-' + Math.random(), channel_id: 'ch1', sender_id: 'u1',
    sender_name: 'U', sender_avatar_url: null, content: 'x',
    created_at: '2026-08-01T10:00:00+00:00', edited_at: null, ...over,
  }
}

describe('mergeMessages', () => {
  it('keeps a WS arrival that landed while the refetch was in flight', () => {
    const wsArrival = msg({ id: 'ws1', created_at: '2026-08-01T10:00:05+00:00' })
    const merged = mergeMessages([wsArrival], [msg({ id: 'r1' })])
    expect(merged.map((m) => m.id)).toContain('ws1')
  })

  it('drops a pending row whose cmid appears in the fetch (it landed)', () => {
    const pending = msg({ id: 'cmid-1', client_message_id: 'cmid-1', pending: true })
    const landed = msg({ id: 'srv-1', client_message_id: 'cmid-1' })
    const merged = mergeMessages([pending], [landed])
    expect(merged).toHaveLength(1)
    expect(merged[0].id).toBe('srv-1')
  })

  it('keeps an unlanded pending row', () => {
    const pending = msg({ id: 'cmid-2', client_message_id: 'cmid-2', pending: true })
    const merged = mergeMessages([pending], [msg({ id: 'r1' })])
    expect(merged.some((m) => m.id === 'cmid-2')).toBe(true)
  })

  it('prefers the server copy when both sides carry the same id', () => {
    const stale = msg({ id: 'same', content: 'old' })
    const fresh = msg({ id: 'same', content: 'edited' })
    const merged = mergeMessages([stale], [fresh])
    expect(merged).toHaveLength(1)
    expect(merged[0].content).toBe('edited')
  })

  it('yields one deterministic (created_at, id) order regardless of input order', () => {
    const a = msg({ id: 'a', created_at: '2026-08-01T10:00:01+00:00' })
    const b = msg({ id: 'b', created_at: '2026-08-01T10:00:01+00:00' })
    const c = msg({ id: 'c', created_at: '2026-08-01T10:00:00+00:00' })
    expect(mergeMessages([b, a], [c]).map((m) => m.id)).toEqual(['c', 'a', 'b'])
    expect(mergeMessages([c], [a, b]).map((m) => m.id)).toEqual(['c', 'a', 'b'])
  })
})

describe('upsertMessage', () => {
  it('replaces the pending row on echo (same cmid) instead of duplicating', () => {
    const pending = msg({ id: 'cmid-3', client_message_id: 'cmid-3', pending: true })
    const echo = msg({ id: 'srv-3', client_message_id: 'cmid-3' })
    const next = upsertMessage([pending], echo)
    expect(next).toHaveLength(1)
    expect(next[0].id).toBe('srv-3')
    expect(next[0].pending).toBeUndefined()
  })

  it('dedups by server id on reconnect replay', () => {
    const m1 = msg({ id: 'dup' })
    expect(upsertMessage([m1], msg({ id: 'dup' }))).toHaveLength(1)
  })

  it('inserts out-of-order arrivals into (created_at, id) position', () => {
    const late = msg({ id: 'late', created_at: '2026-08-01T09:59:00+00:00' })
    const cur = msg({ id: 'cur', created_at: '2026-08-01T10:00:00+00:00' })
    expect(upsertMessage([cur], late).map((m) => m.id)).toEqual(['late', 'cur'])
  })
})

describe('compareMessages', () => {
  it('ties on created_at break by id', () => {
    const a = msg({ id: 'a' }); const b = msg({ id: 'b' })
    expect(compareMessages(a, b)).toBeLessThan(0)
  })
})
```

## 3.2 `baseSocket.ts` — send returns boolean, wake handlers, jitter

1. `send` (:192):
```ts
  /** Send a frame if the socket is open. Returns false when the frame was
   * dropped (closed / reconnecting) so callers can queue it for replay —
   * the old void signature silently ate messages sent during a backoff
   * window, the primary cross-device divergence cause. */
  protected send(data: Record<string, unknown>): boolean {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
      return true
    }
    return false
  }
```
2. Constructor + wake (new — class currently has no constructor):
```ts
  constructor() {
    // Laptop sleep / network change recovery. The OS can freeze or kill the
    // socket without a prompt onclose, and background tabs throttle the
    // backoff timer to ~1/min — so on wake, reconnect immediately and (even
    // if the socket looks open) fire connected-listeners so the channel
    // view's reconnect catch-up refetch runs. Espresso does the same via
    // didBecomeActiveNotification for exactly this reason. Listeners are
    // never removed: the sockets are process-lifetime singletons.
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') this._wake()
      })
    }
    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => this._wake())
    }
  }

  private _wake() {
    if (this._closed) return
    if (this.isOpen) {
      // Possibly a zombie socket (frozen tab) — the catch-up refetch is the
      // recovery either way; the next ping cycle flushes a true zombie out.
      this._emit(this.connectedListeners)
      return
    }
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
      this.reconnectTimeout = null
    }
    this._reconnectAttempts = 0
    this.connect()
  }
```
3. Jitter in `_scheduleReconnect` (:216):
```ts
    // +0-1s jitter: a server blip disconnects every client simultaneously;
    // deterministic backoff reconnects them all at exactly t+3s and every one
    // fires its catch-up history fetch in the same instant.
    const delay =
      Math.min(BACKOFF_MAX_MS, BACKOFF_BASE_MS * 2 ** this._reconnectAttempts) +
      Math.random() * 1000
```

Extend `baseSocket.test.ts`: a test that `send` returns false when no socket / not open, true when open (the file already fabricates sockets — follow its existing harness; it even documents the old drop behavior at ~:248, update that test's assertion to the new contract).

## 3.3 `channelSocket.ts` — persistent outbox + flush

Add below the imports:
```ts
/** Durable outbox for sends attempted while the socket was down. Mirrors
 * Espresso's channels_outbox_v1 (UserDefaults) — safe to blind-replay because
 * the server INSERT is idempotent on (sender_id, client_message_id). */
type OutboxEntry = {
  channel_id: string
  content: string
  attachments?: { url: string; filename: string; content_type: string; size: number }[]
  client_message_id: string
  reply_to_id?: string
  queued_at: number
}
const OUTBOX_KEY = 'channels_outbox_v1'
const OUTBOX_CAP = 50
```
Class additions:
```ts
  private _readOutbox(): OutboxEntry[] {
    try {
      const raw = localStorage.getItem(OUTBOX_KEY)
      return raw ? (JSON.parse(raw) as OutboxEntry[]) : []
    } catch {
      return []
    }
  }

  private _writeOutbox(entries: OutboxEntry[]) {
    try {
      localStorage.setItem(OUTBOX_KEY, JSON.stringify(entries.slice(-OUTBOX_CAP)))
    } catch { /* quota — drop rather than crash the send path */ }
  }

  private _enqueueOutbox(entry: OutboxEntry) {
    const rest = this._readOutbox().filter((e) => e.client_message_id !== entry.client_message_id)
    this._writeOutbox([...rest, entry])
  }

  removeFromOutbox(clientMessageId: string) {
    const entries = this._readOutbox()
    const rest = entries.filter((e) => e.client_message_id !== clientMessageId)
    if (rest.length !== entries.length) this._writeOutbox(rest)
  }

  private _flushOutbox() {
    const entries = this._readOutbox()
    if (!entries.length) return
    const remaining: OutboxEntry[] = []
    for (const e of entries) {
      const ok = this.send({
        type: 'message',
        channel_id: e.channel_id,
        content: e.content,
        ...(e.attachments?.length ? { attachments: e.attachments } : {}),
        client_message_id: e.client_message_id,
        ...(e.reply_to_id ? { reply_to_id: e.reply_to_id } : {}),
      })
      if (!ok) remaining.push(e)
    }
    this._writeOutbox(remaining)
  }
```
`rejoin()` becomes:
```ts
  protected rejoin() {
    for (const room of this.joinedRooms) {
      this.send({ type: 'join_room', channel_id: room })
    }
    // After membership is re-established: replay anything queued while down.
    this._flushOutbox()
  }
```
`sendMessage` becomes (returns boolean; enqueues on failure when it has a cmid to key on):
```ts
  sendMessage(
    channelId: string,
    content: string,
    attachments?: { url: string; filename: string; content_type: string; size: number }[],
    clientMessageId?: string,
    replyToId?: string,
  ): boolean {
    const sent = this.send({
      type: 'message',
      channel_id: channelId,
      content,
      ...(attachments?.length ? { attachments } : {}),
      ...(clientMessageId ? { client_message_id: clientMessageId } : {}),
      ...(replyToId ? { reply_to_id: replyToId } : {}),
    })
    if (!sent && clientMessageId) {
      this._enqueueOutbox({
        channel_id: channelId, content, attachments,
        client_message_id: clientMessageId, reply_to_id: replyToId,
        queued_at: Date.now(),
      })
    }
    return sent
  }
```
In `handleMessage`, `case 'message'`: before `_dispatchMessage`, clear a landed entry:
```ts
      case 'message': {
        const m = data.message as ChannelMessage
        if (m.client_message_id) this.removeFromOutbox(m.client_message_id)
        this._dispatchMessage(m)
        break
      }
```
In `case 'error'`: if `data.client_message_id`, also `this.removeFromOutbox(data.client_message_id as string)` (permanently rejected — don't replay forever).
New method + dispatch case for read-state:
```ts
  onChannelRead: ((data: { channel_id: string }) => void) | null = null
  markRead(channelId: string) {
    this.send({ type: 'mark_read', channel_id: channelId })
  }
```
```ts
      case 'channel_read':
        this.onChannelRead?.({ channel_id: data.channel_id as string })
        break
```

## 3.4 `useChannelSocket.ts` — merge, sort, mark-read

1. Imports: `import { mergeMessages, upsertMessage } from '../../api/channelMessages'`.
2. `handleMessage` body (:48-66) — replace the whole `setMessages` updater with:
```ts
      setMessages((prev) => upsertMessage(prev, msg))
```
   Then, after the auto-scroll block, add debounced mark-read (new ref at hook top: `const lastMarkReadRef = useRef(0)`):
```ts
      // Advance last_read_at while actually watching the channel — otherwise
      // unread only zeroes on the next GET /channels/{id} and this open tab
      // accrues phantom unread. Debounced to one frame per 5s.
      if (document.visibilityState === 'visible' && Date.now() - lastMarkReadRef.current > 5000) {
        lastMarkReadRef.current = Date.now()
        socket.markRead(channelId)
      }
```
3. Reconnect handler (:157-167) — replace the `.then` updater:
```ts
    const offConnected = socket.addConnectedListener(() => {
      getChannelMessages(channelId)
        .then((fetched) => {
          // Union, never clobber: a WS message that lands while this fetch is
          // in flight must survive (the replace-version erased it on THIS
          // device only — the cross-device divergence bug). Pending rows
          // reconcile by cmid, which REST now returns.
          setMessages((prev) => mergeMessages(prev, fetched))
        })
        .catch(() => {})
    })
```

## 3.5 `useChannelView.ts` — failed-send lifecycle + pagination

1. Type: in `channels.ts` `ChannelMessage`, add
```ts
  /** Local-only: pending send that got no echo within 8s (or was queued to
   * the outbox while offline). Renders a retry affordance. */
  failed?: boolean
```
2. `handleSend` tail (:227-229) becomes:
```ts
    const sent = socketRef.current?.sendMessage(channelId, content, attachments, cmid, replyTo?.id) ?? false
    if (!sent) {
      // Queued to the durable outbox; it replays on reconnect. Mark failed
      // now so the row visibly needs attention rather than ghosting.
      setMessages((prev) => prev.map((m) => (m.client_message_id === cmid ? { ...m, failed: true } : m)))
    }
    // 8s echo deadline (mirrors Espresso's schedulePendingTimeout): if the
    // echo hasn't replaced the pending row by then, flip it to failed.
    window.setTimeout(() => {
      setMessages((prev) => prev.map((m) => (m.client_message_id === cmid && m.pending ? { ...m, failed: true } : m)))
    }, 8000)
    setInput('')
    setReplyTo(null)
```
3. Retry handler (new, exported from the hook's return object alongside `handleDeleteMessage`):
```ts
  function handleRetryMessage(msg: ChannelMessage) {
    if (!channelId || !msg.client_message_id) return
    setMessages((prev) => prev.map((m) => (m.client_message_id === msg.client_message_id ? { ...m, failed: false } : m)))
    const cmid = msg.client_message_id
    socketRef.current?.sendMessage(channelId, msg.content, msg.attachments, cmid, msg.reply_to_id ?? undefined)
    window.setTimeout(() => {
      setMessages((prev) => prev.map((m) => (m.client_message_id === cmid && m.pending ? { ...m, failed: true } : m)))
    }, 8000)
  }
```
4. Pagination (state + loader; wire `hasMore` init from the initial load):
```ts
  const [hasMore, setHasMore] = useState(true)
  const [loadingOlder, setLoadingOlder] = useState(false)
```
   In the load effect (:132-138) after `setMessages(data.messages)`: `setHasMore(data.messages.length >= 50)`; also `setHasMore(true)` is implicitly reset because the effect re-runs per channelId — set it explicitly before the fetch alongside `setLoading(true)`.
```ts
  const loadOlder = useCallback(async () => {
    if (!channelId || loadingOlder || !hasMore) return
    const oldest = messages.find((m) => !m.pending)
    if (!oldest) return
    setLoadingOlder(true)
    try {
      const older = await getChannelMessages(channelId, oldest.created_at, oldest.id)
      if (older.length < 50) setHasMore(false)
      if (older.length) {
        // Preserve the viewport: record height before the prepend, restore after.
        const container = messagesContainerRef.current
        const prevHeight = container?.scrollHeight ?? 0
        setMessages((prev) => mergeMessages(prev, older))
        requestAnimationFrame(() => {
          if (container) container.scrollTop += container.scrollHeight - prevHeight
        })
      }
    } catch { /* transient — next scroll retries */ }
    finally { setLoadingOlder(false) }
  }, [channelId, messages, loadingOlder, hasMore])
```
   Export `loadOlder`, `hasMore`, `loadingOlder`, `handleRetryMessage` from the hook and thread them through `ChannelViewScreen.tsx` to `MessageList`.
5. `channels.ts` API (:207):
```ts
export const getChannelMessages = (id: string, before?: string, beforeId?: string) => {
  const qs = new URLSearchParams()
  if (before) qs.set('before', before)
  if (beforeId) qs.set('before_id', beforeId)
  const q = qs.toString()
  return api.get<ChannelMessage[]>(`/channels/${id}/messages${q ? `?${q}` : ''}`)
}
```

## 3.6 `MessageList.tsx` — scroll-top loader + failed row

Props gain `onLoadOlder: () => void`, `hasMore: boolean`, `loadingOlder: boolean`, `onRetry: (msg: ChannelMessage) => void`. Container div gains:
```tsx
      onScroll={(e) => {
        if (hasMore && !loadingOlder && e.currentTarget.scrollTop < 60) onLoadOlder()
      }}
```
Top-of-list indicator (before the empty-state block):
```tsx
      {loadingOlder && (
        <div className="text-center py-2 text-w-faint text-xs">Loading older messages…</div>
      )}
```
Failed-row affordance — where the pending style is applied (row has `opacity-60` when `msg.pending`), branch:
```tsx
        {msg.failed && (
          <button
            onClick={() => onRetry(msg)}
            className="text-xs text-red-500 hover:underline"
          >
            Failed to send — click to retry
          </button>
        )}
```
(Match surrounding Tailwind idiom; keep the pending opacity for non-failed pendings.)

## 3.7 `useChannelNotifications.ts` — mute gate + badge freshness + `channel_read`

1. Track mute + refresh membership on change events. Replace the one-shot `listChannels()` effect body:
```ts
    const mutedRef = { current: new Set<string>() }  // hoist as useRef at hook top
    const loadChannels = () => {
      listChannels()
        .then((channels: ChannelSummary[]) => {
          if (cancelled) return
          for (const ch of channels) {
            if (ch.is_member) {
              channelNamesRef.current.set(ch.id, ch.name)
              socket.joinRoom(ch.id)
            }
            if (ch.is_muted) mutedChannelsRef.current.add(ch.id)
            else mutedChannelsRef.current.delete(ch.id)
          }
        })
        .catch(() => {})
    }
    loadChannels()
    window.addEventListener(CHANNELS_CHANGED_EVENT, loadChannels)
    // (remove listener in the cleanup)
```
   (`mutedChannelsRef` = `useRef<Set<string>>(new Set())` at hook top; import `CHANNELS_CHANGED_EVENT` from `../api/channels`.)
2. In `handleMessage`, after the own-message/viewing checks:
```ts
      // Muted channel: no sound, no toast (mentions still notify via the
      // server-side bell/push exception; the sidebar badge still ticks).
      if (mutedChannelsRef.current.has(msg.channel_id)) return
```
3. Badge freshness — debounced sidebar refresh on any inbound message or read event (hook top: `const lastBadgeRefreshRef = useRef(0)`):
```ts
      // Sidebar unread badges only refresh on navigation today — nudge the
      // existing CHANNELS_CHANGED_EVENT refetch, debounced to 1/5s.
      if (Date.now() - lastBadgeRefreshRef.current > 5000) {
        lastBadgeRefreshRef.current = Date.now()
        window.dispatchEvent(new CustomEvent(CHANNELS_CHANGED_EVENT))
      }
```
   Place this BEFORE the own-message/muted early-returns (own messages and muted channels still move the badge). And handle cross-device read zeroing:
```ts
    socket.onChannelRead = () => {
      window.dispatchEvent(new CustomEvent(CHANNELS_CHANGED_EVENT))
    }
```
   (null it in cleanup like the view hook does for its singular handlers — but note useChannelNotifications owns this one exclusively.)

## 3.8 Mute toggle UI

`channels.ts`:
```ts
export const setChannelMute = async (id: string, muted: boolean) => {
  const res = await api.post<{ ok: boolean; muted: boolean }>(`/channels/${id}/mute`, { muted })
  window.dispatchEvent(new CustomEvent(CHANNELS_CHANGED_EVENT))
  return res
}
```
`ChannelSummary` TS type gains `is_muted?: boolean`.
`ChannelHeader.tsx`: add a bell/bell-off toggle (lucide `Bell`/`BellOff`) next to the existing header actions, calling `setChannelMute(channelId, !muted)`; local `muted` state seeded from a new optional prop or fetched channel summary — simplest: `useChannelView` exposes `muted` state seeded false and flipped by the toggle (server is source of truth; sidebar refetch picks it up).

**Verify Phase 3:** `cd client && npx tsc -p tsconfig.app.json --noEmit` (the `-p` form — bare `tsc --noEmit` checks NOTHING) and `npm run test:run -- src/work/api/`.

---

# PHASE 4 — manual + scale verification (dev-remote already running :8001/:5174)

Two browser windows, same account:
1. DevTools → Network → Offline on A; send 3 messages from B; back online on A → all 3 appear (merge catch-up), order identical to B.
2. Offline on A; send from A → row goes failed at 8s; online → outbox replays on reconnect; B receives exactly ONE copy (idempotent cmid); A's ghost reconciles.
3. Seed >50 messages (loop in console or hold enter); reload; scroll up → older pages load, scroll position stable, no duplicates at page seams.
4. Sleep-wake proxy: kill the WS in DevTools (or switch tabs 5+ min on a throttled tab), refocus → visibilitychange reconnect + catch-up fires.
5. Mute channel on A → messages from B: no sound/toast on A, badge still ticks; @mention from B → bell notification arrives.
6. Open channel on A and B; read on A → B's sidebar badge zeroes within ~5s (`channel_read` → refetch).
7. Rate limit: paste-loop 15 instant sends → first ~10 deliver, rest get the rate-limit toast, socket stays alive, composer usable.
8. Scale sanity: `python3` script opening ~50 WS clients on one channel (auth via a dev token), one sender at 10 msg/s for 30s — confirm the worker log shows ONE bulk INSERT per message (add a temporary debug log or check timing), no subscriber lag, no disconnect storm.

Full suites:
- `cd server && ./venv/bin/python -m pytest tests/werk/ tests/matcha_work/ tests/ems/ -q` — new tests pass; only the 6 pre-existing WeasyPrint failures.
- `cd client && npx tsc -p tsconfig.app.json --noEmit && npm run test:run`

# Out of scope (documented, untouched)
- Espresso Swift changes (default-branch ignores new frames; REST additive).
- `--workers 2` / pool sizes / Redis-as-transport; >2-worker scale-out is infra work.
- Per-message membership `SELECT EXISTS` (deliberate: catches mid-session kicks).
- `list_channels`' four correlated subqueries (noted for a later pass).
- Message-list virtualization + typing-indicator O(N²) client render cost (revisit if 300-chatter rooms materialize; the backend typing split in 1.7 removes the server half).

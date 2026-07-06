"""Project WebSocket — real-time collaborator presence on a matcha-work project.

Tracks two levels of presence:
- project_rooms: which users are *anywhere* in a project (drives the
  CollaboratorsPill in the project header).
- page_rooms: which users are on the same sub-tab inside a project — keyed
  by (project_id, page_key) where page_key is e.g. "sections", "pipeline",
  "chat", "sections:<section_id>". Cursor + caret events fan out only to
  users on the *same* page_key, so there's no irrelevant traffic when one
  collaborator is on Pipeline and another is on Sections.
"""

import asyncio
import json
import logging
import time
from collections import deque
from typing import Deque, Dict, Optional, Set, Tuple
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel

from ...database import get_connection
from ...core.services.auth import decode_token
from ...core.services.redis_cache import get_redis_cache

logger = logging.getLogger(__name__)

router = APIRouter()

_USER_NAME_EXPR = "COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email)"

# Cursor + caret messages allowed per (user_id, project_id) per second.
# Combined budget: client throttles cursor at 50ms (~20/s) and caret at 100ms
# (~10/s) = 30/s peak when typing while moving. Headroom of 60/s avoids
# silent drops during simultaneous mouse + edit; ring buffer keyed per
# (user, project).
_RATE_LIMIT_PER_SEC = 60
_RATE_LIMIT_WINDOW = 1.0
# Hard cap on caret section_id payload size — incoming msg fans out to
# all subscribers, so a giant blob would amplify into a DoS.
_MAX_SECTION_ID_LEN = 64

# Live co-edit section soft-locks. Redis-backed so they're correct across the
# uvicorn workers (same reason presence/fan-out use Redis). The TTL frees a lock
# automatically if the editor's client crashes without a section_edit_end.
_SECTION_LOCK_PREFIX = "mw:seclock:"
_SECTION_LOCK_TTL = 20
# Cap a live section_content frame — it fans out to every watcher each tick.
_MAX_SECTION_CONTENT_LEN = 200_000

# Redis pub/sub channel used to fan-out project broadcasts across uvicorn
# workers. Same architectural fix as channels_ws.py: with --workers 2 the
# in-process ProjectConnectionManager dicts would otherwise silo presence
# per worker, so collaborators on different workers wouldn't see each
# other in the project header pill.
_FANOUT_CHANNEL = "projects:fanout"
# Redis hash key prefix storing the cross-worker membership snapshot used
# by `get_project_presence` so a late-joiner sees members connected to
# other workers, not just the one their socket landed on.
#
# TTL is generous (1h) on purpose: the hash is only refreshed on join /
# page_change / leave_project (HSET re-bumps EXPIRE), NOT on cursor or
# caret events. A user who's connected and typing but never changes
# sub-tab would otherwise vanish from the snapshot after a short TTL,
# even though they're still actively present. Graceful disconnect
# always issues an explicit HDEL, so the long TTL only matters for
# crashed workers — those stale entries die after at most 1h.
_PRESENCE_KEY_PREFIX = "mw:presence:"
_PRESENCE_TTL_SECONDS = 3600


class ProjectUser(BaseModel):
    id: UUID
    name: str
    email: str
    role: str
    avatar_url: Optional[str] = None
    company_id: Optional[UUID] = None


class ProjectConnectionManager:
    """Connection state for project-scoped collaboration WS."""

    def __init__(self):
        self.active_connections: Dict[UUID, Set[WebSocket]] = {}
        self.users: Dict[UUID, ProjectUser] = {}
        # Per-user current location: project_id → page_key
        self.user_pages: Dict[UUID, Dict[UUID, str]] = {}
        # project_id → user_ids (anywhere in project)
        self.project_rooms: Dict[UUID, Set[UUID]] = {}
        # (project_id, page_key) → user_ids on that exact sub-tab
        self.page_rooms: Dict[Tuple[UUID, str], Set[UUID]] = {}
        # (user_id, project_id) → ring buffer of recent cursor/caret timestamps
        self.rate_history: Dict[Tuple[UUID, UUID], Deque[float]] = {}
        # Live co-edit locks held by THIS worker's users → release proactively
        # on disconnect (Redis TTL is the backstop for crashes).
        self.held_section_locks: Dict[UUID, Set[Tuple[UUID, str]]] = {}
        # Redis-down single-process fallback: (project_id, section_id) → holder.
        self._local_section_locks: Dict[Tuple[UUID, str], dict] = {}
        self.lock = asyncio.Lock()

    async def connect(
        self, websocket: WebSocket, user: ProjectUser, subprotocol: Optional[str] = None
    ):
        await websocket.accept(subprotocol=subprotocol)
        async with self.lock:
            if user.id not in self.active_connections:
                self.active_connections[user.id] = set()
                self.user_pages[user.id] = {}
            self.active_connections[user.id].add(websocket)
            self.users[user.id] = user

    async def disconnect(self, websocket: WebSocket, user_id: UUID):
        """Drop ws; if user has no more connections, remove from all rooms and notify."""
        async with self.lock:
            conns = self.active_connections.get(user_id)
            if not conns:
                return
            conns.discard(websocket)
            if conns:
                return
            # Last connection for this user — clean up everything
            del self.active_connections[user_id]
            user = self.users.pop(user_id, None)
            pages = self.user_pages.pop(user_id, {})

        # Outside the lock: fan out user_left for each project the user was in.
        for project_id, page_key in pages.items():
            await self._remove_from_rooms(user_id, project_id, page_key, user)

        # Free any sections this user was actively editing so they don't stay
        # wedged until the Redis TTL expires.
        await self.release_all_section_locks(user_id, user)

    async def _remove_from_rooms(
        self,
        user_id: UUID,
        project_id: UUID,
        page_key: Optional[str],
        user: Optional[ProjectUser],
    ):
        async with self.lock:
            if project_id in self.project_rooms:
                self.project_rooms[project_id].discard(user_id)
                if not self.project_rooms[project_id]:
                    del self.project_rooms[project_id]
            if page_key is not None:
                key = (project_id, page_key)
                if key in self.page_rooms:
                    self.page_rooms[key].discard(user_id)
                    if not self.page_rooms[key]:
                        del self.page_rooms[key]
            self.rate_history.pop((user_id, project_id), None)

        # Drop the cross-worker snapshot entry so other workers' next
        # `get_project_presence` doesn't return a ghost.
        await self._presence_hdel(project_id, user_id)

        if user:
            await self._broadcast_to_project(project_id, {
                "type": "user_left_project",
                "project_id": str(project_id),
                "user_id": str(user_id),
            }, exclude_user=user_id)

    async def join_project(self, user_id: UUID, project_id: UUID, page_key: str):
        """Add user to project_rooms + page_rooms; broadcast joined; reply with snapshot."""
        async with self.lock:
            self.project_rooms.setdefault(project_id, set()).add(user_id)
            self.page_rooms.setdefault((project_id, page_key), set()).add(user_id)
            self.user_pages.setdefault(user_id, {})[project_id] = page_key
            user = self.users.get(user_id)

        # Cross-worker snapshot bookkeeping. Write BEFORE the broadcast so a
        # peer's subsequent `get_project_presence` call sees this user.
        if user is not None:
            await self._presence_hset(project_id, user, page_key)

        # Notify others in the project that this user joined.
        if user is not None:
            await self._broadcast_to_project(project_id, {
                "type": "user_joined_project",
                "project_id": str(project_id),
                "user": user.model_dump(mode='json'),
                "page_key": page_key,
            }, exclude_user=user_id)

    async def change_page(self, user_id: UUID, project_id: UUID, new_page_key: str):
        """Move user from one sub-tab to another within the same project."""
        async with self.lock:
            old_page = self.user_pages.get(user_id, {}).get(project_id)
            if old_page == new_page_key:
                return
            if old_page is not None:
                old_key = (project_id, old_page)
                if old_key in self.page_rooms:
                    self.page_rooms[old_key].discard(user_id)
                    if not self.page_rooms[old_key]:
                        del self.page_rooms[old_key]
            self.page_rooms.setdefault((project_id, new_page_key), set()).add(user_id)
            self.user_pages.setdefault(user_id, {})[project_id] = new_page_key
            user = self.users.get(user_id)

        # Update the cross-worker snapshot with the new page_key.
        if user is not None:
            await self._presence_hset(project_id, user, new_page_key)

        await self._broadcast_to_project(project_id, {
            "type": "presence_update",
            "project_id": str(project_id),
            "user_id": str(user_id),
            "page_key": new_page_key,
        }, exclude_user=user_id)

    async def leave_project(self, user_id: UUID, project_id: UUID):
        async with self.lock:
            page_key = self.user_pages.get(user_id, {}).pop(project_id, None)
            user = self.users.get(user_id)
        await self._remove_from_rooms(user_id, project_id, page_key, user)

    def check_rate_limit(self, user_id: UUID, project_id: UUID) -> bool:
        """Returns True if message is allowed, False if rate-limited (silently drop)."""
        key = (user_id, project_id)
        now = time.monotonic()
        history = self.rate_history.get(key)
        if history is None:
            history = deque(maxlen=_RATE_LIMIT_PER_SEC + 1)
            self.rate_history[key] = history
        # Drop timestamps outside the window
        while history and (now - history[0]) > _RATE_LIMIT_WINDOW:
            history.popleft()
        if len(history) >= _RATE_LIMIT_PER_SEC:
            return False
        history.append(now)
        return True

    async def broadcast_cursor(self, project_id: UUID, page_key: str, user_id: UUID, x_pct: float, y_pct: float):
        await self._broadcast_to_page(project_id, page_key, {
            "type": "cursor",
            "project_id": str(project_id),
            "user_id": str(user_id),
            "x_pct": x_pct,
            "y_pct": y_pct,
        }, exclude_user=user_id)

    async def broadcast_caret(self, project_id: UUID, page_key: str, user_id: UUID, section_id: str, anchor: int, head: int):
        await self._broadcast_to_page(project_id, page_key, {
            "type": "caret",
            "project_id": str(project_id),
            "user_id": str(user_id),
            "section_id": section_id,
            "anchor": anchor,
            "head": head,
        }, exclude_user=user_id)

    # ── Live co-edit soft locks ──────────────────────────────────────────────

    def _track_held(self, user_id: UUID, project_id: UUID, section_id: str) -> None:
        self.held_section_locks.setdefault(user_id, set()).add((project_id, section_id))

    def _untrack_held(self, user_id: UUID, project_id: UUID, section_id: str) -> None:
        held = self.held_section_locks.get(user_id)
        if held:
            held.discard((project_id, section_id))

    async def acquire_section_lock(self, project_id: UUID, section_id: str, user: "ProjectUser") -> Optional[dict]:
        """Claim the section for editing. Returns None when granted (incl. when
        this user already holds it — reconnect/re-open), else the current
        holder dict {user_id, name} so the caller can deny."""
        holder = {"user_id": str(user.id), "name": user.name}
        redis = get_redis_cache()
        if redis is None:
            existing = self._local_section_locks.get((project_id, section_id))
            if existing and existing["user_id"] != str(user.id):
                return existing
            self._local_section_locks[(project_id, section_id)] = holder
            self._track_held(user.id, project_id, section_id)
            return None
        key = f"{_SECTION_LOCK_PREFIX}{project_id}:{section_id}"
        val = json.dumps(holder)
        ok = await redis.set(key, val, nx=True, ex=_SECTION_LOCK_TTL)
        if ok:
            self._track_held(user.id, project_id, section_id)
            return None
        cur = await redis.get(key)
        cur_holder = None
        if cur:
            try:
                cur_holder = json.loads(cur)
            except (ValueError, TypeError):
                cur_holder = None
        # Already ours (re-open / heartbeat gap) → refresh and treat as granted.
        if cur_holder and cur_holder.get("user_id") == str(user.id):
            await redis.set(key, val, ex=_SECTION_LOCK_TTL)
            self._track_held(user.id, project_id, section_id)
            return None
        return cur_holder

    async def refresh_section_lock(self, project_id: UUID, section_id: str, user: "ProjectUser") -> bool:
        """Extend the lock TTL while the holder keeps typing. Re-acquires if it
        expired and is now free. False when someone else holds it."""
        redis = get_redis_cache()
        if redis is None:
            h = self._local_section_locks.get((project_id, section_id))
            if h is None:
                self._local_section_locks[(project_id, section_id)] = {"user_id": str(user.id), "name": user.name}
                self._track_held(user.id, project_id, section_id)
                return True
            return h["user_id"] == str(user.id)
        key = f"{_SECTION_LOCK_PREFIX}{project_id}:{section_id}"
        cur = await redis.get(key)
        if not cur:
            return (await self.acquire_section_lock(project_id, section_id, user)) is None
        try:
            h = json.loads(cur)
        except (ValueError, TypeError):
            h = None
        if h and h.get("user_id") == str(user.id):
            await redis.set(key, cur, ex=_SECTION_LOCK_TTL)
            return True
        return False

    async def takeover_section_lock(self, project_id: UUID, section_id: str, user: "ProjectUser") -> Optional[dict]:
        """Force-claim the lock for `user`, evicting the current holder. Returns
        the previous holder dict (or None if it was free / already ours). Used
        for the watcher → editor take-over handoff; the caller then broadcasts
        the new holder so the evicted editor drops to watcher mode."""
        holder = {"user_id": str(user.id), "name": user.name}

        def _untrack_prev(prev: Optional[dict]) -> None:
            if prev and prev.get("user_id") and prev["user_id"] != str(user.id):
                try:
                    self._untrack_held(UUID(prev["user_id"]), project_id, section_id)
                except (ValueError, TypeError):
                    pass

        redis = get_redis_cache()
        if redis is None:
            prev = self._local_section_locks.get((project_id, section_id))
            _untrack_prev(prev)
            self._local_section_locks[(project_id, section_id)] = holder
            self._track_held(user.id, project_id, section_id)
            return prev if prev and prev.get("user_id") != str(user.id) else None
        key = f"{_SECTION_LOCK_PREFIX}{project_id}:{section_id}"
        cur = await redis.get(key)
        prev = None
        if cur:
            try:
                prev = json.loads(cur)
            except (ValueError, TypeError):
                prev = None
        await redis.set(key, json.dumps(holder), ex=_SECTION_LOCK_TTL)
        _untrack_prev(prev)
        self._track_held(user.id, project_id, section_id)
        return prev if prev and prev.get("user_id") != str(user.id) else None

    async def release_section_lock(self, project_id: UUID, section_id: str, user_id: UUID) -> bool:
        """Release the lock iff this user holds it. Returns True when it actually
        released (so the caller knows whether to broadcast `section_unlocked`).
        Critically False when the user was already evicted by a take-over — else
        their later edit_end would falsely tell watchers the section is free.
        Safe to call redundantly."""
        self._untrack_held(user_id, project_id, section_id)
        redis = get_redis_cache()
        if redis is None:
            h = self._local_section_locks.get((project_id, section_id))
            if h and h["user_id"] == str(user_id):
                self._local_section_locks.pop((project_id, section_id), None)
                return True
            return False
        key = f"{_SECTION_LOCK_PREFIX}{project_id}:{section_id}"
        cur = await redis.get(key)
        if not cur:
            return False
        try:
            h = json.loads(cur)
        except (ValueError, TypeError):
            h = None
        if h and h.get("user_id") == str(user_id):
            await redis.delete(key)
            return True
        return False

    async def broadcast_section_lock(self, project_id: UUID, page_key: str, section_id: str, user: "ProjectUser", *, locked: bool) -> None:
        await self._broadcast_to_page(project_id, page_key, {
            "type": "section_locked" if locked else "section_unlocked",
            "project_id": str(project_id),
            "section_id": section_id,
            "user_id": str(user.id),
            "user_name": user.name,
        }, exclude_user=user.id)

    async def broadcast_section_content(self, project_id: UUID, page_key: str, user_id: UUID, section_id: str, title, content: str) -> None:
        await self._broadcast_to_page(project_id, page_key, {
            "type": "section_content",
            "project_id": str(project_id),
            "section_id": section_id,
            "user_id": str(user_id),
            "title": title,
            "content": content,
        }, exclude_user=user_id)

    async def release_all_section_locks(self, user_id: UUID, user: Optional["ProjectUser"]) -> None:
        """On disconnect: free every lock this user held + tell watchers."""
        held = self.held_section_locks.pop(user_id, set())
        for (project_id, section_id) in held:
            released = await self.release_section_lock(project_id, section_id, user_id)
            if released and user is not None:
                # Section editing lives on the "sections" sub-tab.
                await self.broadcast_section_lock(project_id, "sections", section_id, user, locked=False)

    async def get_project_presence(self, project_id: UUID) -> list:
        """Snapshot of who's in this project, with their current page_key.

        Reads the cross-worker Redis hash so a late-joiner sees members
        connected to any worker, not just the one their socket landed on.
        Falls back to local in-process state when Redis is absent (dev)
        — in that case the snapshot only covers same-worker peers, which
        matches the pre-pubsub behavior.
        """
        redis = get_redis_cache()
        if redis is not None:
            try:
                raw = await redis.hgetall(f"{_PRESENCE_KEY_PREFIX}{project_id}")
                if raw:
                    members = []
                    for _uid_str, value in raw.items():
                        try:
                            members.append(json.loads(value))
                        except Exception:
                            continue
                    return members
            except Exception:
                logger.exception("Redis HGETALL failed in get_project_presence; using local fallback")
        async with self.lock:
            members = []
            for uid in self.project_rooms.get(project_id, set()):
                user = self.users.get(uid)
                page_key = self.user_pages.get(uid, {}).get(project_id)
                if user:
                    members.append({
                        **user.model_dump(mode='json'),
                        "page_key": page_key,
                    })
            return members

    async def _presence_hset(self, project_id: UUID, user: "ProjectUser", page_key: str) -> None:
        """Record this user's presence in the cross-worker Redis hash so
        snapshot reads on any worker include them."""
        redis = get_redis_cache()
        if redis is None:
            return
        value = json.dumps({
            **user.model_dump(mode='json'),
            "page_key": page_key,
        }, default=str)
        key = f"{_PRESENCE_KEY_PREFIX}{project_id}"
        try:
            await redis.hset(key, str(user.id), value)
            await redis.expire(key, _PRESENCE_TTL_SECONDS)
        except Exception:
            logger.exception("Redis HSET failed in _presence_hset")

    async def _presence_hdel(self, project_id: UUID, user_id: UUID) -> None:
        redis = get_redis_cache()
        if redis is None:
            return
        try:
            await redis.hdel(f"{_PRESENCE_KEY_PREFIX}{project_id}", str(user_id))
        except Exception:
            logger.exception("Redis HDEL failed in _presence_hdel")

    async def _broadcast_to_project(self, project_id: UUID, message: dict, exclude_user: Optional[UUID] = None):
        """Fan a project-scope event out to every connected member across all
        uvicorn workers. Publishes to Redis; per-worker subscriber dispatches
        to its local sockets. Falls back to in-process when Redis is absent."""
        redis = get_redis_cache()
        if redis is None:
            await self._local_broadcast_to_project(project_id, message, exclude_user=exclude_user)
            return
        envelope = {
            "kind": "project",
            "project_id": str(project_id),
            "message": message,
            "exclude_user": str(exclude_user) if exclude_user else None,
        }
        try:
            await redis.publish(_FANOUT_CHANNEL, json.dumps(envelope, default=str))
        except Exception:
            logger.exception("Redis publish failed in _broadcast_to_project; using local fallback")
            await self._local_broadcast_to_project(project_id, message, exclude_user=exclude_user)

    async def _local_broadcast_to_project(self, project_id: UUID, message: dict, exclude_user: Optional[UUID] = None):
        """Direct write to this worker's local sockets. Called by the
        subscriber loop and as the Redis-down fallback."""
        async with self.lock:
            members = self.project_rooms.get(project_id, set())
            targets: list[tuple[UUID, set]] = []
            for uid in members:
                if exclude_user and uid == exclude_user:
                    continue
                conns = self.active_connections.get(uid)
                if conns:
                    targets.append((uid, set(conns)))
        await self._send_to_targets(targets, message)

    async def _broadcast_to_page(self, project_id: UUID, page_key: str, message: dict, exclude_user: Optional[UUID] = None):
        """Fan a page-scope event (cursor/caret) out to every member on the
        same sub-tab across all workers."""
        redis = get_redis_cache()
        if redis is None:
            await self._local_broadcast_to_page(project_id, page_key, message, exclude_user=exclude_user)
            return
        envelope = {
            "kind": "page",
            "project_id": str(project_id),
            "page_key": page_key,
            "message": message,
            "exclude_user": str(exclude_user) if exclude_user else None,
        }
        try:
            await redis.publish(_FANOUT_CHANNEL, json.dumps(envelope, default=str))
        except Exception:
            logger.exception("Redis publish failed in _broadcast_to_page; using local fallback")
            await self._local_broadcast_to_page(project_id, page_key, message, exclude_user=exclude_user)

    async def _local_broadcast_to_page(self, project_id: UUID, page_key: str, message: dict, exclude_user: Optional[UUID] = None):
        async with self.lock:
            members = self.page_rooms.get((project_id, page_key), set())
            targets: list[tuple[UUID, set]] = []
            for uid in members:
                if exclude_user and uid == exclude_user:
                    continue
                conns = self.active_connections.get(uid)
                if conns:
                    targets.append((uid, set(conns)))
        await self._send_to_targets(targets, message)

    async def _send_to_targets(self, targets: list, message: dict):
        if not targets:
            return
        data = json.dumps(message, default=str)
        for uid, conns in targets:
            dead = []
            for ws in conns:
                try:
                    await ws.send_text(data)
                except Exception:
                    dead.append(ws)
            if dead:
                async with self.lock:
                    bucket = self.active_connections.get(uid)
                    if bucket:
                        for ws in dead:
                            bucket.discard(ws)


project_manager = ProjectConnectionManager()


# ---------------------------------------------------------------------------
# Cross-worker pub/sub subscriber
# ---------------------------------------------------------------------------

_project_subscriber_task: Optional[asyncio.Task] = None


async def _project_subscriber_loop() -> None:
    """Long-running per-worker task. Subscribes to projects:fanout and
    dispatches each envelope to this worker's local sockets via
    _local_broadcast_to_project / _local_broadcast_to_page.

    Self-healing: on any exception, sleeps 2s and re-subscribes. Cancellation
    exits cleanly.
    """
    while True:
        pubsub = None
        try:
            redis = get_redis_cache()
            if redis is None:
                await asyncio.sleep(5)
                continue
            pubsub = redis.pubsub()
            await pubsub.subscribe(_FANOUT_CHANNEL)
            logger.info("[Project WS] Subscribed to %s", _FANOUT_CHANNEL)
            async for raw in pubsub.listen():
                if raw is None or raw.get("type") != "message":
                    continue
                payload = raw.get("data")
                if not payload:
                    continue
                try:
                    envelope = json.loads(payload)
                except Exception:
                    logger.warning("[Project WS] Malformed fanout envelope; dropping")
                    continue
                kind = envelope.get("kind")
                msg = envelope.get("message")
                if msg is None:
                    continue
                exclude_raw = envelope.get("exclude_user")
                exclude_user: Optional[UUID] = None
                if exclude_raw:
                    try:
                        exclude_user = UUID(exclude_raw)
                    except (ValueError, TypeError):
                        exclude_user = None
                project_raw = envelope.get("project_id")
                if not project_raw:
                    continue
                try:
                    project_id = UUID(project_raw)
                except (ValueError, TypeError):
                    continue
                if kind == "project":
                    await project_manager._local_broadcast_to_project(
                        project_id, msg, exclude_user=exclude_user,
                    )
                elif kind == "page":
                    page_key = envelope.get("page_key")
                    if not page_key:
                        continue
                    await project_manager._local_broadcast_to_page(
                        project_id, page_key, msg, exclude_user=exclude_user,
                    )
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("[Project WS] Subscriber loop error; restarting in 2s")
            await asyncio.sleep(2)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(_FANOUT_CHANNEL)
                    await pubsub.aclose()
                except Exception:
                    pass


def start_project_fanout_subscriber() -> None:
    """Start the per-worker Redis pub/sub subscriber. Idempotent."""
    global _project_subscriber_task
    if _project_subscriber_task and not _project_subscriber_task.done():
        return
    _project_subscriber_task = asyncio.create_task(_project_subscriber_loop())


async def stop_project_fanout_subscriber() -> None:
    """Cancel the subscriber task on shutdown."""
    global _project_subscriber_task
    if _project_subscriber_task is not None:
        _project_subscriber_task.cancel()
        try:
            await _project_subscriber_task
        except (asyncio.CancelledError, Exception):
            pass
        _project_subscriber_task = None


async def broadcast_task_event(project_id: UUID, event: str, payload: dict) -> None:
    """Fan a task lifecycle event out to every connected member of a project room.

    `event` must be one of: "task.created", "task.updated", "task.deleted".
    `payload` is the task row dict (or `{"id": ...}` for delete). Caller stamps
    actor_id so clients can suppress their own optimistic-write echoes.

    Best-effort: any send failure is swallowed by `_broadcast_to_project`'s
    per-conn dead-list handling; callers should still wrap in try/except.
    """
    async with project_manager.lock:
        room = list(project_manager.project_rooms.get(project_id, set()))
    logger.info(
        "broadcast %s project=%s room_size=%d members=%s",
        event, project_id, len(room),
        [str(uid) for uid in room],
    )
    await project_manager._broadcast_to_project(project_id, {
        "type": event,
        "project_id": str(project_id),
        "task": payload,
    })


def _token_from_request(
    websocket: WebSocket, query_token: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    """Extract the JWT from the handshake. Sources, in preference order:

    1. ``Sec-WebSocket-Protocol: bearer, <token>`` — web clients; keeps the
       token out of the URL so it never lands in nginx/proxy access logs.
    2. ``?token=`` query param — legacy web clients / pre-deploy tabs.
    3. ``Authorization: Bearer`` header — native clients.

    Returns ``(token, subprotocol_to_echo)`` — when the token came in via
    subprotocol the accept() MUST echo ``"bearer"`` or browsers fail the
    handshake.
    """
    proto = websocket.headers.get("sec-websocket-protocol")
    if proto:
        parts = [p.strip() for p in proto.split(",")]
        if len(parts) >= 2 and parts[0] == "bearer" and parts[1]:
            return parts[1], "bearer"
    if query_token:
        return query_token, None
    auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:], None
    return None, None


async def _authenticate(token: str) -> Optional[ProjectUser]:
    payload = decode_token(token, expected_type="access")
    if not payload:
        logger.warning("project_ws authenticate failed — invalid/expired token")
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
        company_id = None
        if row["role"] in ("client", "individual"):
            company_id = await conn.fetchval(
                "SELECT company_id FROM clients WHERE user_id = $1", user_id
            )
        elif row["role"] == "employee":
            company_id = await conn.fetchval(
                "SELECT org_id FROM employees WHERE user_id = $1", user_id
            )
        return ProjectUser(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            role=row["role"],
            avatar_url=row["avatar_url"],
            company_id=company_id,
        )


async def _can_access_project(conn, user: ProjectUser, project_id: UUID) -> bool:
    """Mirror project_service access logic: admin, creator, same company, or active collaborator."""
    if user.role == "admin":
        return True
    return await conn.fetchval(
        """
        SELECT EXISTS(
            SELECT 1 FROM mw_projects p
            WHERE p.id = $1
              AND (
                  p.created_by = $2
                  OR ($3::uuid IS NOT NULL AND p.company_id = $3)
                  OR EXISTS(
                      SELECT 1 FROM mw_project_collaborators
                      WHERE project_id = $1 AND user_id = $2 AND status = 'active'
                  )
              )
        )
        """,
        project_id, user.id, user.company_id,
    )


@router.websocket("")
async def project_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """WebSocket for matcha-work project presence (cursor + caret + cross-tab pill)."""
    auth_token, subprotocol = _token_from_request(websocket, token)
    if not auth_token:
        await websocket.close(code=4001, reason="Missing token")
        return
    user = await _authenticate(auth_token)
    if not user:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await project_manager.connect(websocket, user, subprotocol=subprotocol)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            project_id_raw = data.get("project_id")
            if not project_id_raw and msg_type not in ("ping",):
                await websocket.send_json({"type": "error", "message": "Missing project_id"})
                continue
            try:
                project_id = UUID(project_id_raw)
            except (ValueError, TypeError):
                await websocket.send_json({"type": "error", "message": "Invalid project_id"})
                continue

            if msg_type == "join_project":
                page_key = data.get("page_key") or "sections"
                async with get_connection() as conn:
                    ok = await _can_access_project(conn, user, project_id)
                logger.info(
                    "join_project attempt user=%s project=%s access=%s page=%s",
                    user.id, project_id, ok, page_key,
                )
                if not ok:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Project not found or access denied",
                    })
                    continue
                await project_manager.join_project(user.id, project_id, page_key)
                async with project_manager.lock:
                    room_size_now = len(project_manager.project_rooms.get(project_id, set()))
                logger.info(
                    "join_project ok user=%s project=%s room_size_now=%d",
                    user.id, project_id, room_size_now,
                )
                members = await project_manager.get_project_presence(project_id)
                await websocket.send_json({
                    "type": "presence",
                    "project_id": str(project_id),
                    "members": members,
                })
                continue

            # All non-join project events require the user to have already
            # called join_project (which is the gate that runs the membership
            # check). Without this guard, a malicious client could fan-out
            # cursor/caret events into any project_id they know — receivers
            # were validated at join, but the sender path was open.
            if user.id not in project_manager.project_rooms.get(project_id, set()):
                continue

            if msg_type == "page_change":
                page_key = data.get("page_key")
                if not page_key:
                    continue
                await project_manager.change_page(user.id, project_id, page_key)

            elif msg_type == "cursor_move":
                page_key = data.get("page_key") or "sections"
                x_pct = data.get("x_pct")
                y_pct = data.get("y_pct")
                if x_pct is None or y_pct is None:
                    continue
                if not project_manager.check_rate_limit(user.id, project_id):
                    continue
                await project_manager.broadcast_cursor(
                    project_id, page_key, user.id, float(x_pct), float(y_pct)
                )

            elif msg_type == "caret_move":
                page_key = data.get("page_key") or "sections"
                section_id = data.get("section_id")
                anchor = data.get("anchor")
                head = data.get("head")
                if section_id is None or anchor is None or head is None:
                    continue
                # Validate section_id as a bounded string (UUID format
                # preferred but we accept any short identifier). Prevents
                # a 1MB-blob fan-out amplification.
                section_id_str = str(section_id)
                if len(section_id_str) > _MAX_SECTION_ID_LEN:
                    continue
                try:
                    UUID(section_id_str)
                except (ValueError, TypeError):
                    continue
                if not project_manager.check_rate_limit(user.id, project_id):
                    continue
                await project_manager.broadcast_caret(
                    project_id, page_key, user.id, section_id_str, int(anchor), int(head)
                )

            elif msg_type == "section_edit_start":
                # Claim a section for editing. Section ids are 16-hex (not
                # UUIDs), so validate by length only — not UUID format.
                page_key = data.get("page_key") or "sections"
                section_id = data.get("section_id")
                if section_id is None or not (0 < len(str(section_id)) <= _MAX_SECTION_ID_LEN):
                    continue
                section_id_str = str(section_id)
                holder = await project_manager.acquire_section_lock(project_id, section_id_str, user)
                if holder is None:
                    await project_manager.broadcast_section_lock(
                        project_id, page_key, section_id_str, user, locked=True
                    )
                else:
                    # Denied — tell the requester only who holds it.
                    await websocket.send_json({
                        "type": "section_lock_denied",
                        "project_id": str(project_id),
                        "section_id": section_id_str,
                        "holder_id": holder.get("user_id"),
                        "holder_name": holder.get("name"),
                    })

            elif msg_type == "section_content":
                page_key = data.get("page_key") or "sections"
                section_id = data.get("section_id")
                if section_id is None or not (0 < len(str(section_id)) <= _MAX_SECTION_ID_LEN):
                    continue
                content = data.get("content")
                if content is None:
                    continue
                section_id_str = str(section_id)
                # Only the lock holder may stream live content; this refreshes
                # the lock TTL while they keep typing.
                if not await project_manager.refresh_section_lock(project_id, section_id_str, user):
                    continue
                if not project_manager.check_rate_limit(user.id, project_id):
                    continue
                if isinstance(content, str) and len(content) > _MAX_SECTION_CONTENT_LEN:
                    content = content[:_MAX_SECTION_CONTENT_LEN]
                await project_manager.broadcast_section_content(
                    project_id, page_key, user.id, section_id_str, data.get("title"), content
                )

            elif msg_type == "section_edit_end":
                page_key = data.get("page_key") or "sections"
                section_id = data.get("section_id")
                if section_id is None or not (0 < len(str(section_id)) <= _MAX_SECTION_ID_LEN):
                    continue
                section_id_str = str(section_id)
                released = await project_manager.release_section_lock(project_id, section_id_str, user.id)
                # Only announce the unlock if we actually held it — a user evicted
                # by a take-over must not tell watchers the section is now free.
                if released:
                    await project_manager.broadcast_section_lock(
                        project_id, page_key, section_id_str, user, locked=False
                    )

            elif msg_type == "section_edit_takeover":
                # Wrest the lock from the current holder. Broadcasting the new
                # holder (excludes the taker) lands on the previous editor, whose
                # client flips them to watcher mode.
                page_key = data.get("page_key") or "sections"
                section_id = data.get("section_id")
                if section_id is None or not (0 < len(str(section_id)) <= _MAX_SECTION_ID_LEN):
                    continue
                section_id_str = str(section_id)
                await project_manager.takeover_section_lock(project_id, section_id_str, user)
                await project_manager.broadcast_section_lock(
                    project_id, page_key, section_id_str, user, locked=True
                )

            elif msg_type == "leave_project":
                logger.info("leave_project user=%s project=%s", user.id, project_id)
                await project_manager.leave_project(user.id, project_id)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"[Project WS] Error: {e}", exc_info=True)
    finally:
        logger.info("project_ws disconnect user=%s", user.id)
        await project_manager.disconnect(websocket, user.id)

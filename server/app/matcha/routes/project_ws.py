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
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user: ProjectUser):
        await websocket.accept()
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

        # Notify others in the project that this user joined.
        if user_id in self.users:
            await self._broadcast_to_project(project_id, {
                "type": "user_joined_project",
                "project_id": str(project_id),
                "user": self.users[user_id].model_dump(mode='json'),
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

    async def get_project_presence(self, project_id: UUID) -> list:
        """Snapshot of who's in this project, with their current page_key."""
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

    async def _broadcast_to_project(self, project_id: UUID, message: dict, exclude_user: Optional[UUID] = None):
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
    token: str = Query(...),
):
    """WebSocket for matcha-work project presence (cursor + caret + cross-tab pill)."""
    user = await _authenticate(token)
    if not user:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await project_manager.connect(websocket, user)

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

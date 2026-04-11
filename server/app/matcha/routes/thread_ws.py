"""Thread WebSocket handler for real-time collaborative thread presence and messaging."""

import asyncio
import json
import logging
from typing import Dict, Optional, Set
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel

from ...database import get_connection
from ...core.services.auth import decode_token

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# User identity model (resolved at connection time)
# ---------------------------------------------------------------------------

_USER_NAME_EXPR = "COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email)"


class ThreadUser(BaseModel):
    id: UUID
    name: str
    email: str
    role: str
    avatar_url: Optional[str] = None
    company_id: Optional[UUID] = None


# ---------------------------------------------------------------------------
# Connection Manager (mirrors ChannelConnectionManager pattern)
# ---------------------------------------------------------------------------

class ThreadConnectionManager:
    """Manages WebSocket connections for thread collaboration."""

    def __init__(self):
        self.active_connections: Dict[UUID, Set[WebSocket]] = {}
        self.room_members: Dict[str, Set[UUID]] = {}
        self.users: Dict[UUID, ThreadUser] = {}
        self.user_rooms: Dict[UUID, Set[str]] = {}
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user: ThreadUser):
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

    async def broadcast_typing(self, room_key: str, user: ThreadUser):
        await self._broadcast_to_room(room_key, {
            "type": "typing",
            "room": room_key,
            "user": user.model_dump(mode='json'),
        }, exclude_user=user.id)

    async def broadcast_new_message(self, thread_id: str, messages: list):
        """Broadcast new messages to all connected clients in a thread room.

        Called by external code (e.g., the stream endpoint) to push new
        messages to connected collaborators in real time.
        """
        await self._broadcast_to_room(thread_id, {
            "type": "new_message",
            "room": thread_id,
            "messages": messages,
        })

    async def get_online_users(self, room_key: str) -> list:
        async with self.lock:
            if room_key not in self.room_members:
                return []
            return [
                self.users[uid].model_dump(mode='json')
                for uid in self.room_members[room_key]
                if uid in self.users
            ]

    async def _broadcast_to_room(self, room_key: str, message: dict, exclude_user: UUID = None):
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


thread_manager = ThreadConnectionManager()


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

async def _authenticate(token: str) -> Optional[ThreadUser]:
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

        return ThreadUser(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            role=row["role"],
            avatar_url=row["avatar_url"],
            company_id=company_id,
        )


async def _can_access_thread(conn, user: ThreadUser, thread_id: UUID) -> bool:
    """Check if a user can access a thread.

    Access is granted if the user is:
    - An admin
    - The thread owner (created_by)
    - A collaborator in mw_thread_collaborators
    """
    if user.role == "admin":
        return True

    return await conn.fetchval(
        """
        SELECT EXISTS(
            SELECT 1 FROM mw_threads
            WHERE id = $1
              AND (
                  created_by = $2
                  OR EXISTS(SELECT 1 FROM mw_thread_collaborators WHERE thread_id = $1 AND user_id = $2)
              )
        )
        """,
        thread_id, user.id,
    )


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("")
async def thread_websocket(
    websocket: WebSocket,
    token: str = Query(...),
):
    """WebSocket endpoint for real-time thread collaboration (presence + typing + message broadcast)."""
    user = await _authenticate(token)
    if not user:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await thread_manager.connect(websocket, user)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "join_thread":
                thread_id = data.get("thread_id")
                if thread_id:
                    try:
                        t_uuid = UUID(thread_id)
                    except (ValueError, TypeError):
                        await websocket.send_json({"type": "error", "message": "Invalid thread ID"})
                        continue

                    async with get_connection() as conn:
                        ok = await _can_access_thread(conn, user, t_uuid)

                    if ok:
                        room_key = str(thread_id)
                        await thread_manager.join_room(user.id, room_key)
                        online = await thread_manager.get_online_users(room_key)
                        await websocket.send_json({
                            "type": "online_users",
                            "room": room_key,
                            "users": online,
                        })
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Thread not found or access denied",
                        })

            elif msg_type == "leave_thread":
                thread_id = data.get("thread_id")
                if thread_id:
                    await thread_manager.leave_room(user.id, str(thread_id))

            elif msg_type == "typing":
                thread_id = data.get("thread_id")
                if thread_id:
                    await thread_manager.broadcast_typing(str(thread_id), user)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"[Thread WS] Error: {e}")
    finally:
        await thread_manager.disconnect(websocket, user.id)

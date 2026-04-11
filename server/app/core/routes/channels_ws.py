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
from .voice_signaling import (
    handle_voice_join,
    handle_voice_leave,
    handle_voice_offer,
    handle_voice_answer,
    handle_voice_ice,
    cleanup_user_from_calls,
)

logger = logging.getLogger(__name__)

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
        """Send a message to a specific user (all their connections)."""
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

    try:
        while True:
            data = await websocket.receive_json()
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
                        # Verify membership + company access (exclude removed-for-inactivity members)
                        if user.role == "admin":
                            ok = await conn.fetchval(
                                "SELECT EXISTS(SELECT 1 FROM channel_members WHERE channel_id = $1 AND user_id = $2 AND removed_for_inactivity IS NOT TRUE)",
                                ch_uuid, user.id,
                            )
                        else:
                            ok = await conn.fetchval(
                                """
                                SELECT EXISTS(
                                    SELECT 1 FROM channel_members cm
                                    JOIN channels ch ON ch.id = cm.channel_id
                                    WHERE cm.channel_id = $1 AND cm.user_id = $2 AND ch.company_id = $3
                                      AND cm.removed_for_inactivity IS NOT TRUE
                                )
                                """,
                                ch_uuid, user.id, user.company_id,
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
                if channel_id and (content or attachments) and len(content) <= 4000:
                    try:
                        ch_uuid = UUID(channel_id)
                    except (ValueError, TypeError):
                        continue
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
                                INSERT INTO channel_messages (channel_id, sender_id, content, attachments)
                                VALUES ($1, $2, $3, $4::jsonb)
                                RETURNING id, channel_id, sender_id, content, attachments, created_at, edited_at
                                """,
                                ch_uuid, user.id, content or "", attachments_json,
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
                            await manager.broadcast_message(room_key, {
                                "id": str(row["id"]),
                                "channel_id": str(row["channel_id"]),
                                "sender_id": str(row["sender_id"]),
                                "sender_name": user.name,
                                "sender_avatar_url": user.avatar_url,
                                "content": row["content"],
                                "attachments": broadcast_attachments,
                                "created_at": row["created_at"].isoformat(),
                                "edited_at": None,
                            })
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

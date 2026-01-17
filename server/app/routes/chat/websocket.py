"""Chat WebSocket handler for real-time messaging."""

import asyncio
from typing import Dict, Set
from uuid import UUID
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from ...database import get_connection
from ...models.chat import ChatUserPublic, ChatMessage
from .auth import decode_chat_token

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections for chat."""

    def __init__(self):
        # user_id -> set of websockets (user can have multiple tabs)
        self.active_connections: Dict[UUID, Set[WebSocket]] = {}
        # room_slug -> set of user_ids
        self.room_members: Dict[str, Set[UUID]] = {}
        # user_id -> ChatUserPublic
        self.users: Dict[UUID, ChatUserPublic] = {}
        # user_id -> set of room slugs they're actively viewing
        self.user_rooms: Dict[UUID, Set[str]] = {}
        # Lock for thread safety
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user: ChatUserPublic):
        """Connect a user's websocket."""
        await websocket.accept()
        async with self.lock:
            if user.id not in self.active_connections:
                self.active_connections[user.id] = set()
                self.user_rooms[user.id] = set()
            self.active_connections[user.id].add(websocket)
            self.users[user.id] = user

    async def disconnect(self, websocket: WebSocket, user_id: UUID):
        """Disconnect a user's websocket."""
        async with self.lock:
            if user_id in self.active_connections:
                self.active_connections[user_id].discard(websocket)
                # If no more connections, remove user from all rooms
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
                    # Notify rooms that user left
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
                                        "user": user.model_dump(mode='json')
                                    }, exclude_user=user_id)

    async def join_room(self, user_id: UUID, room_slug: str):
        """User joins a room for real-time updates."""
        async with self.lock:
            if room_slug not in self.room_members:
                self.room_members[room_slug] = set()

            was_in_room = user_id in self.room_members[room_slug]
            self.room_members[room_slug].add(user_id)

            if user_id in self.user_rooms:
                self.user_rooms[user_id].add(room_slug)

            # Broadcast user joined if new
            if not was_in_room and user_id in self.users:
                await self._broadcast_to_room(room_slug, {
                    "type": "user_joined",
                    "room": room_slug,
                    "user": self.users[user_id].model_dump(mode='json')
                }, exclude_user=user_id)

    async def leave_room(self, user_id: UUID, room_slug: str):
        """User leaves a room for real-time updates."""
        async with self.lock:
            if room_slug in self.room_members:
                self.room_members[room_slug].discard(user_id)

            if user_id in self.user_rooms:
                self.user_rooms[user_id].discard(room_slug)

            # Broadcast user left
            if user_id in self.users:
                await self._broadcast_to_room(room_slug, {
                    "type": "user_left",
                    "room": room_slug,
                    "user": self.users[user_id].model_dump(mode='json')
                })

    async def broadcast_message(self, room_slug: str, message: ChatMessage):
        """Broadcast a new message to all users in a room."""
        await self._broadcast_to_room(room_slug, {
            "type": "message",
            "room": room_slug,
            "message": message.model_dump(mode='json')
        })

    async def broadcast_typing(self, room_slug: str, user: ChatUserPublic):
        """Broadcast typing indicator to a room."""
        await self._broadcast_to_room(room_slug, {
            "type": "typing",
            "room": room_slug,
            "user": user.model_dump(mode='json')
        }, exclude_user=user.id)

    async def get_online_users_in_room(self, room_slug: str) -> list:
        """Get list of online users in a room."""
        async with self.lock:
            if room_slug not in self.room_members:
                return []
            return [
                self.users[uid].model_dump(mode='json')
                for uid in self.room_members[room_slug]
                if uid in self.users
            ]

    async def send_to_user(self, user_id: UUID, message: dict):
        """Send a message to a specific user."""
        if user_id in self.active_connections:
            data = json.dumps(message, default=str)
            dead_connections = []
            for ws in self.active_connections[user_id]:
                try:
                    await ws.send_text(data)
                except Exception:
                    dead_connections.append(ws)
            # Clean up dead connections
            for ws in dead_connections:
                self.active_connections[user_id].discard(ws)

    async def _broadcast_to_room(self, room_slug: str, message: dict, exclude_user: UUID = None):
        """Broadcast a message to all users in a room."""
        if room_slug not in self.room_members:
            return

        data = json.dumps(message, default=str)
        for user_id in self.room_members[room_slug]:
            if exclude_user and user_id == exclude_user:
                continue
            if user_id in self.active_connections:
                dead_connections = []
                for ws in self.active_connections[user_id]:
                    try:
                        await ws.send_text(data)
                    except Exception:
                        dead_connections.append(ws)
                # Clean up dead connections
                for ws in dead_connections:
                    self.active_connections[user_id].discard(ws)


# Global connection manager instance
manager = ConnectionManager()


async def get_user_from_token(token: str) -> ChatUserPublic | None:
    """Get user from JWT token."""
    payload = decode_chat_token(token)
    if not payload or payload.type != "chat_access":
        return None

    async with get_connection() as conn:
        user = await conn.fetchrow(
            """
            SELECT id, email, first_name, last_name, avatar_url, bio, last_seen
            FROM chat_users WHERE id = $1 AND is_active = TRUE
            """,
            UUID(payload.sub)
        )
        if not user:
            return None

        # Update last_seen
        await conn.execute(
            "UPDATE chat_users SET last_seen = CURRENT_TIMESTAMP WHERE id = $1",
            UUID(payload.sub)
        )

        return ChatUserPublic(
            id=user["id"],
            email=user["email"],
            first_name=user["first_name"],
            last_name=user["last_name"],
            avatar_url=user["avatar_url"],
            bio=user["bio"],
            last_seen=user["last_seen"]
        )


@router.websocket("")
async def chat_websocket(
    websocket: WebSocket,
    token: str = Query(...)
):
    """WebSocket endpoint for real-time chat."""
    # Authenticate
    user = await get_user_from_token(token)
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
                room_slug = data.get("room")
                if room_slug:
                    # Verify room exists and user is a member
                    async with get_connection() as conn:
                        room = await conn.fetchrow(
                            """
                            SELECT r.id FROM chat_rooms r
                            JOIN chat_room_members m ON r.id = m.room_id
                            WHERE r.slug = $1 AND m.user_id = $2
                            """,
                            room_slug,
                            user.id
                        )
                        if room:
                            await manager.join_room(user.id, room_slug)
                            # Send online users in room
                            online_users = await manager.get_online_users_in_room(room_slug)
                            await websocket.send_json({
                                "type": "online_users",
                                "room": room_slug,
                                "users": online_users
                            })
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Room not found or not a member"
                            })

            elif msg_type == "leave_room":
                room_slug = data.get("room")
                if room_slug:
                    await manager.leave_room(user.id, room_slug)

            elif msg_type == "message":
                room_slug = data.get("room")
                content = data.get("content", "").strip()
                if room_slug and content and len(content) <= 2000:
                    # Verify room exists and user is a member
                    async with get_connection() as conn:
                        room = await conn.fetchrow(
                            """
                            SELECT r.id FROM chat_rooms r
                            JOIN chat_room_members m ON r.id = m.room_id
                            WHERE r.slug = $1 AND m.user_id = $2
                            """,
                            room_slug,
                            user.id
                        )
                        if room:
                            # Create message
                            row = await conn.fetchrow(
                                """
                                INSERT INTO chat_messages (room_id, user_id, content)
                                VALUES ($1, $2, $3)
                                RETURNING id, room_id, user_id, content, created_at, edited_at
                                """,
                                room["id"],
                                user.id,
                                content
                            )
                            message = ChatMessage(
                                id=row["id"],
                                room_id=row["room_id"],
                                user_id=row["user_id"],
                                content=row["content"],
                                created_at=row["created_at"],
                                edited_at=row["edited_at"],
                                user=user
                            )
                            await manager.broadcast_message(room_slug, message)
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Room not found or not a member"
                            })

            elif msg_type == "typing":
                room_slug = data.get("room")
                if room_slug:
                    await manager.broadcast_typing(room_slug, user)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[Chat WS] Error: {e}")
    finally:
        await manager.disconnect(websocket, user.id)


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance."""
    return manager

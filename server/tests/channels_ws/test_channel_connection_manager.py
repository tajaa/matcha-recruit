"""Server-side contract tests for ChannelConnectionManager.

These document the broadcast/subscription invariants the macOS Matcha
client relies on for background channel notifications. If any of these
break, the client's `joinBackgroundRooms` logic breaks too.

Specifically:
- A user must be added to `room_members[room_key]` via `join_room` before
  `_broadcast_to_room` will route messages to them.
- `leave_room` removes the user; subsequent broadcasts must NOT reach them.
- A user can be subscribed to multiple rooms simultaneously; each room's
  broadcasts route independently.
- Disconnect cleans up all room memberships for that user.
"""

import json
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

# Stub heavyweight external SDKs so importing app code is cheap.
google_module = ModuleType("google")
genai_module = ModuleType("google.genai")
types_module = ModuleType("google.genai.types")
genai_module.Client = object
genai_module.types = types_module
types_module.Tool = lambda **kw: None
types_module.GoogleSearch = lambda **kw: None
types_module.GenerateContentConfig = lambda **kw: None
sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.genai", genai_module)
sys.modules.setdefault("google.genai.types", types_module)

# `app.core.routes.__init__` transitively imports newsletter → bleach.
# Stub bleach so the import succeeds without the real dep installed.
bleach_module = ModuleType("bleach")
bleach_module.clean = lambda text, **kw: text
bleach_module.linkify = lambda text, **kw: text
sys.modules.setdefault("bleach", bleach_module)


def _make_user(name: str = "Test User"):
    from app.core.routes.channels_ws import ChannelUser
    return ChannelUser(
        id=uuid4(),
        name=name,
        email=f"{name.lower().replace(' ', '.')}@example.com",
        role="client",
    )


def _make_ws_mock():
    """Mimic a connected WebSocket: accept() succeeds, send_text records calls."""
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


def _sent_payloads(ws_mock) -> list[dict]:
    """Decode every send_text() call back into a dict for assertions."""
    return [json.loads(call.args[0]) for call in ws_mock.send_text.call_args_list]


class TestRoomBroadcastRouting:
    """Confirm that join_room is required for broadcasts to reach a user."""

    @pytest.mark.asyncio
    async def test_broadcast_to_user_in_room(self):
        from app.core.routes.channels_ws import ChannelConnectionManager
        manager = ChannelConnectionManager()
        user = _make_user()
        ws = _make_ws_mock()

        await manager.connect(ws, user)
        room_key = str(uuid4())
        await manager.join_room(user.id, room_key)

        await manager.broadcast_message(room_key, {"id": "m1", "content": "hello"})

        payloads = _sent_payloads(ws)
        # First payload is the user_joined broadcast (only when more than one
        # user is in the room before us, but we still see it routed to us via
        # `not was_in_room`); but join_room only broadcasts if there are
        # listeners — verify by filtering for the message type.
        msg_payloads = [p for p in payloads if p.get("type") == "message"]
        assert len(msg_payloads) == 1
        assert msg_payloads[0]["room"] == room_key
        assert msg_payloads[0]["message"]["content"] == "hello"

    @pytest.mark.asyncio
    async def test_broadcast_skipped_when_user_not_in_room(self):
        """The macOS bug: if client never joins the room (or leaves it),
        the server's broadcast must NOT reach them. This is the invariant
        that forced `joinBackgroundRooms` on the client side."""
        from app.core.routes.channels_ws import ChannelConnectionManager
        manager = ChannelConnectionManager()
        user = _make_user()
        ws = _make_ws_mock()

        await manager.connect(ws, user)
        # NOTE: deliberately NOT calling join_room.

        room_key = str(uuid4())
        await manager.broadcast_message(room_key, {"id": "m1", "content": "hello"})

        # Exactly zero `message`-type payloads delivered.
        msg_payloads = [p for p in _sent_payloads(ws) if p.get("type") == "message"]
        assert msg_payloads == []

    @pytest.mark.asyncio
    async def test_broadcast_after_leave_room_skipped(self):
        """Confirms that a client calling leave_room (e.g. the
        `ChannelDetailView.onDisappear` path) stops receiving broadcasts
        for that room, even though the WebSocket is still connected."""
        from app.core.routes.channels_ws import ChannelConnectionManager
        manager = ChannelConnectionManager()
        user = _make_user()
        ws = _make_ws_mock()

        await manager.connect(ws, user)
        room_key = str(uuid4())
        await manager.join_room(user.id, room_key)
        await manager.leave_room(user.id, room_key)

        # Reset mock so we only count broadcasts after leave_room.
        ws.send_text.reset_mock()
        await manager.broadcast_message(room_key, {"id": "m1", "content": "ghost"})

        msg_payloads = [p for p in _sent_payloads(ws) if p.get("type") == "message"]
        assert msg_payloads == [], "leave_room must stop further broadcast routing"

    @pytest.mark.asyncio
    async def test_user_joined_to_multiple_rooms_receives_each(self):
        """Background-notifications case: user is subscribed to all member
        channels via `joinBackgroundRooms`. Broadcasts to any of them must
        route to the single connection."""
        from app.core.routes.channels_ws import ChannelConnectionManager
        manager = ChannelConnectionManager()
        user = _make_user()
        ws = _make_ws_mock()

        await manager.connect(ws, user)
        room_a = str(uuid4())
        room_b = str(uuid4())
        room_c = str(uuid4())
        await manager.join_room(user.id, room_a)
        await manager.join_room(user.id, room_b)
        await manager.join_room(user.id, room_c)

        await manager.broadcast_message(room_a, {"id": "a", "content": "from a"})
        await manager.broadcast_message(room_b, {"id": "b", "content": "from b"})
        await manager.broadcast_message(room_c, {"id": "c", "content": "from c"})

        msg_payloads = [p for p in _sent_payloads(ws) if p.get("type") == "message"]
        rooms_seen = {p["room"] for p in msg_payloads}
        assert rooms_seen == {room_a, room_b, room_c}

    @pytest.mark.asyncio
    async def test_one_user_leaves_other_still_receives(self):
        from app.core.routes.channels_ws import ChannelConnectionManager
        manager = ChannelConnectionManager()
        alice, bob = _make_user("Alice"), _make_user("Bob")
        alice_ws, bob_ws = _make_ws_mock(), _make_ws_mock()

        await manager.connect(alice_ws, alice)
        await manager.connect(bob_ws, bob)
        room_key = str(uuid4())
        await manager.join_room(alice.id, room_key)
        await manager.join_room(bob.id, room_key)

        await manager.leave_room(alice.id, room_key)

        # Reset to ignore the user_left broadcast generated by leave_room.
        alice_ws.send_text.reset_mock()
        bob_ws.send_text.reset_mock()

        await manager.broadcast_message(room_key, {"id": "x", "content": "after-leave"})

        alice_msgs = [p for p in _sent_payloads(alice_ws) if p.get("type") == "message"]
        bob_msgs = [p for p in _sent_payloads(bob_ws) if p.get("type") == "message"]
        assert alice_msgs == []
        assert len(bob_msgs) == 1
        assert bob_msgs[0]["message"]["content"] == "after-leave"


class TestDisconnectCleansRooms:
    """Closing the WebSocket must drop the user from every room they joined,
    so the server doesn't try to send to a dead socket and so a reconnect
    starts from a clean slate (mirrors the client's `scheduleReconnect`
    logic which clears `backgroundRoomIds` and re-joins)."""

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_all_rooms(self):
        from app.core.routes.channels_ws import ChannelConnectionManager
        manager = ChannelConnectionManager()
        user = _make_user()
        ws = _make_ws_mock()

        await manager.connect(ws, user)
        room_a, room_b = str(uuid4()), str(uuid4())
        await manager.join_room(user.id, room_a)
        await manager.join_room(user.id, room_b)
        assert user.id in manager.room_members[room_a]
        assert user.id in manager.room_members[room_b]

        await manager.disconnect(ws, user.id)

        assert user.id not in manager.room_members[room_a]
        assert user.id not in manager.room_members[room_b]
        assert user.id not in manager.active_connections

    @pytest.mark.asyncio
    async def test_disconnect_one_of_multiple_connections_keeps_membership(self):
        """If the user has two WebSockets (e.g. desktop + web) and one
        closes, the other stays subscribed to all rooms."""
        from app.core.routes.channels_ws import ChannelConnectionManager
        manager = ChannelConnectionManager()
        user = _make_user()
        ws1, ws2 = _make_ws_mock(), _make_ws_mock()

        await manager.connect(ws1, user)
        await manager.connect(ws2, user)
        room_key = str(uuid4())
        await manager.join_room(user.id, room_key)

        await manager.disconnect(ws1, user.id)

        # ws2 is still active, room membership preserved.
        assert user.id in manager.active_connections
        assert ws2 in manager.active_connections[user.id]
        assert user.id in manager.room_members[room_key]


class TestSelfBroadcastIsIncluded:
    """`broadcast_message` does NOT exclude the sender — the client relies
    on this to refresh its own message list. (Compare with `broadcast_typing`,
    which does exclude the sender.)"""

    @pytest.mark.asyncio
    async def test_sender_receives_own_broadcast_message(self):
        from app.core.routes.channels_ws import ChannelConnectionManager
        manager = ChannelConnectionManager()
        user = _make_user()
        ws = _make_ws_mock()

        await manager.connect(ws, user)
        room_key = str(uuid4())
        await manager.join_room(user.id, room_key)

        await manager.broadcast_message(
            room_key, {"id": "self", "sender_id": str(user.id), "content": "hi self"}
        )

        msg_payloads = [p for p in _sent_payloads(ws) if p.get("type") == "message"]
        assert len(msg_payloads) == 1

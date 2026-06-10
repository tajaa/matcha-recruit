"""Tests for channel audio-call sessions (channel_calls routes).

Covers:
- Join policy: invite_only rejects non-invitees, admits invitees and the owner
- Capacity: 409 when full, re-join allowed while own identity still in room
- Mutual exclusion: call start 409s when a call or broadcast is active
- Webhook: room_finished closes the row; call- prefix dispatch from the shared
  LiveKit webhook; participants_changed payload shape
"""

import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

# ── Stub google.genai before importing app code ──
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


MOD = "app.core.routes.channel_calls"
LK = "app.core.services.livekit_service"


def _conn_ctx(conn):
    """get_connection() replacement returning an async CM that yields conn."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


def _user(email="owner@example.com"):
    return SimpleNamespace(id=uuid4(), email=email)


def _call_row(channel_id, *, mode="members", started_by=None, started_minutes_ago=5):
    return {
        "id": uuid4(),
        "channel_id": channel_id,
        "started_by": started_by or uuid4(),
        "mode": mode,
        "livekit_room": f"call-{channel_id}",
        "started_at": datetime.now(timezone.utc) - timedelta(minutes=started_minutes_ago),
        "ended_at": None,
    }


# ============================================================
# Constants / room naming
# ============================================================

class TestBasics:
    def test_max_participants(self):
        from app.core.routes.channel_calls import CALL_MAX_PARTICIPANTS
        assert CALL_MAX_PARTICIPANTS == 4

    def test_room_name_prefix_distinct_from_broadcasts(self):
        from app.core.routes.channel_calls import _call_room_name
        cid = uuid4()
        assert _call_room_name(cid) == f"call-{cid}"
        assert not _call_room_name(cid).startswith("channel-")


# ============================================================
# Join policy (GET /call/token)
# ============================================================

class TestJoinPolicy:
    def _conn_for(self, call, *, invited):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [call]          # _active_call
        conn.fetchval.return_value = 1 if invited else None
        return conn

    @pytest.mark.asyncio
    async def test_invite_only_rejects_non_invitee(self):
        from app.core.routes.channel_calls import get_call_token
        channel_id = uuid4()
        user = _user("member@example.com")
        call = _call_row(channel_id, mode="invite_only")
        conn = self._conn_for(call, invited=False)

        with patch(f"{MOD}.get_connection", _conn_ctx(conn)), \
             patch(f"{MOD}._assert_member", AsyncMock()), \
             patch(f"{LK}._get_lk_config", return_value=("ws://t", "k", "s")):
            with pytest.raises(HTTPException) as exc:
                await get_call_token(channel_id, current_user=user)
        assert exc.value.status_code == 403
        assert "invited" in exc.value.detail

    @pytest.mark.asyncio
    async def test_invite_only_admits_invitee(self):
        from app.core.routes.channel_calls import get_call_token
        channel_id = uuid4()
        user = _user("invitee@example.com")
        call = _call_row(channel_id, mode="invite_only")
        conn = self._conn_for(call, invited=True)
        conn.fetchrow.side_effect = [call, {"name": "Invitee"}]  # + _display_name

        with patch(f"{MOD}.get_connection", _conn_ctx(conn)), \
             patch(f"{MOD}._assert_member", AsyncMock()), \
             patch(f"{LK}._get_lk_config", return_value=("ws://t", "k", "s")), \
             patch(f"{LK}.list_participant_identities", AsyncMock(return_value=[])), \
             patch(f"{LK}.mint_token", return_value="jwt") as mt:
            resp = await get_call_token(channel_id, current_user=user)

        assert resp["token"] == "jwt"
        assert resp["mode"] == "invite_only"
        assert mt.call_args.kwargs["can_publish_sources"] == ["microphone"]

    @pytest.mark.asyncio
    async def test_invite_only_owner_bypasses_invite_check(self):
        from app.core.routes.channel_calls import get_call_token
        channel_id = uuid4()
        user = _user("owner@example.com")
        call = _call_row(channel_id, mode="invite_only", started_by=user.id)
        conn = AsyncMock()
        conn.fetchrow.side_effect = [call, {"name": "Owner"}]

        with patch(f"{MOD}.get_connection", _conn_ctx(conn)), \
             patch(f"{MOD}._assert_member", AsyncMock()), \
             patch(f"{LK}._get_lk_config", return_value=("ws://t", "k", "s")), \
             patch(f"{LK}.list_participant_identities", AsyncMock(return_value=[])), \
             patch(f"{LK}.mint_token", return_value="jwt"):
            resp = await get_call_token(channel_id, current_user=user)

        assert resp["token"] == "jwt"
        conn.fetchval.assert_not_called()  # no invite lookup for the owner


# ============================================================
# Capacity (GET /call/token)
# ============================================================

class TestCapacity:
    @pytest.mark.asyncio
    async def test_full_room_rejected(self):
        from app.core.routes.channel_calls import get_call_token
        channel_id = uuid4()
        user = _user("late@example.com")
        call = _call_row(channel_id, mode="members")
        conn = AsyncMock()
        conn.fetchrow.side_effect = [call, {"name": "Late"}]

        occupants = [str(uuid4()) for _ in range(4)]
        with patch(f"{MOD}.get_connection", _conn_ctx(conn)), \
             patch(f"{MOD}._assert_member", AsyncMock()), \
             patch(f"{LK}._get_lk_config", return_value=("ws://t", "k", "s")), \
             patch(f"{LK}.list_participant_identities", AsyncMock(return_value=occupants)):
            with pytest.raises(HTTPException) as exc:
                await get_call_token(channel_id, current_user=user)
        assert exc.value.status_code == 409
        assert "full" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_rejoin_allowed_when_own_identity_counted(self):
        from app.core.routes.channel_calls import get_call_token
        channel_id = uuid4()
        user = _user("rejoiner@example.com")
        call = _call_row(channel_id, mode="members")
        conn = AsyncMock()
        conn.fetchrow.side_effect = [call, {"name": "Rejoiner"}]

        occupants = [str(user.id)] + [str(uuid4()) for _ in range(3)]  # full, incl. self
        with patch(f"{MOD}.get_connection", _conn_ctx(conn)), \
             patch(f"{MOD}._assert_member", AsyncMock()), \
             patch(f"{LK}._get_lk_config", return_value=("ws://t", "k", "s")), \
             patch(f"{LK}.list_participant_identities", AsyncMock(return_value=occupants)), \
             patch(f"{LK}.mint_token", return_value="jwt"):
            resp = await get_call_token(channel_id, current_user=user)
        assert resp["token"] == "jwt"


# ============================================================
# Mutual exclusion + start flow (POST /call/start)
# ============================================================

class TestStartCall:
    def _patches(self, conn, active_call=None, active_broadcast=None):
        return [
            patch(f"{MOD}.get_connection", _conn_ctx(conn)),
            patch(f"{MOD}._assert_owner", AsyncMock()),
            patch(f"{MOD}._active_broadcast", AsyncMock(return_value=active_broadcast)),
            patch(f"{MOD}._push_call_event", AsyncMock()),
            patch(f"{MOD}._notify_invitees", AsyncMock()),
            patch(f"{MOD}._schedule_auto_stop"),
            patch(f"{LK}._get_lk_config", return_value=("ws://t", "k", "s")),
            patch(f"{LK}.create_room", AsyncMock()),
            patch(f"{LK}.mint_token", return_value="jwt"),
            patch("app.matcha.services.entitlements_service.require_plan", AsyncMock()),
        ]

    @pytest.mark.asyncio
    async def test_409_when_call_active(self):
        from app.core.routes.channel_calls import start_call, StartCallBody
        channel_id = uuid4()
        user = _user()
        conn = AsyncMock()
        conn.fetchrow.side_effect = [_call_row(channel_id)]  # _active_call -> fresh row

        patches = self._patches(conn)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patches[6], patches[7], patches[8], patches[9]:
            with pytest.raises(HTTPException) as exc:
                await start_call(channel_id, StartCallBody(mode="members"), current_user=user)
        assert exc.value.status_code == 409
        assert "call" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_409_when_broadcast_active(self):
        from app.core.routes.channel_calls import start_call, StartCallBody
        channel_id = uuid4()
        user = _user()
        conn = AsyncMock()
        conn.fetchrow.side_effect = [None]  # no active call

        patches = self._patches(conn, active_broadcast={"id": uuid4()})
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patches[6], patches[7], patches[8], patches[9]:
            with pytest.raises(HTTPException) as exc:
                await start_call(channel_id, StartCallBody(mode="members"), current_user=user)
        assert exc.value.status_code == 409
        assert "broadcast" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_start_members_mode_happy_path(self):
        from app.core.routes.channel_calls import start_call, StartCallBody, CALL_MAX_PARTICIPANTS
        channel_id = uuid4()
        user = _user()
        call_id = uuid4()
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            None,                                                       # _active_call
            {"id": call_id, "started_at": datetime.now(timezone.utc)},  # INSERT RETURNING
        ]
        conn.fetch.return_value = []  # _member_filtered (no invitees)

        patches = self._patches(conn)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patches[6], patches[7] as cr, patches[8] as mt, patches[9]:
            resp = await start_call(channel_id, StartCallBody(mode="members"), current_user=user)

        assert resp["call_id"] == str(call_id)
        assert resp["mode"] == "members"
        assert resp["max_participants"] == CALL_MAX_PARTICIPANTS
        assert cr.await_args.kwargs["max_participants"] == CALL_MAX_PARTICIPANTS
        assert mt.call_args.kwargs["can_publish_sources"] == ["microphone"]


# ============================================================
# Webhook handling
# ============================================================

class TestWebhook:
    @pytest.mark.asyncio
    async def test_room_finished_closes_row_and_pushes_ended(self):
        from app.core.routes.channel_calls import handle_call_webhook_event
        channel_id = uuid4()
        call_id = uuid4()
        conn = AsyncMock()
        conn.fetchrow.return_value = {"id": call_id}

        with patch(f"{MOD}.get_connection", _conn_ctx(conn)), \
             patch(f"{MOD}._push_call_event", AsyncMock()) as push:
            resp = await handle_call_webhook_event("room_finished", {}, f"call-{channel_id}")

        assert resp == {"ok": True}
        assert "ended_at = NOW()" in conn.fetchrow.call_args.args[0]
        event = push.await_args.args[1]
        assert event["type"] == "call.ended"
        assert event["call_id"] == str(call_id)

    @pytest.mark.asyncio
    async def test_participants_changed_payload(self):
        from app.core.routes.channel_calls import handle_call_webhook_event
        channel_id = uuid4()
        call = _call_row(channel_id)
        conn = AsyncMock()
        conn.fetchrow.return_value = call
        ids = [str(uuid4()), str(uuid4())]

        with patch(f"{MOD}.get_connection", _conn_ctx(conn)), \
             patch(f"{LK}.list_participant_identities", AsyncMock(return_value=ids)), \
             patch(f"{MOD}._push_call_event", AsyncMock()) as push:
            await handle_call_webhook_event("participant_joined", {}, f"call-{channel_id}")

        event = push.await_args.args[1]
        assert event["type"] == "call.participants_changed"
        assert event["participant_ids"] == ids
        assert event["count"] == 2
        assert event["max_participants"] == 4

    @pytest.mark.asyncio
    async def test_bad_room_uuid_is_ignored(self):
        from app.core.routes.channel_calls import handle_call_webhook_event
        resp = await handle_call_webhook_event("room_finished", {}, "call-not-a-uuid")
        assert resp == {"ok": True}

    @pytest.mark.asyncio
    async def test_shared_webhook_dispatches_call_prefix(self):
        """channel_broadcasts.livekit_webhook routes call- rooms to our handler
        and leaves channel- (broadcast) handling untouched."""
        from app.core.routes.channel_broadcasts import livekit_webhook
        channel_id = uuid4()

        event = {"event": "room_finished", "room": {"name": f"call-{channel_id}"}}
        request = MagicMock()
        request.body = AsyncMock(return_value=b"{}")

        with patch(f"{LK}.receive_webhook", return_value=event), \
             patch(f"{MOD}.handle_call_webhook_event", AsyncMock(return_value={"ok": True})) as h:
            resp = await livekit_webhook(request, authorization="Bearer x")

        assert resp == {"ok": True}
        h.assert_awaited_once()
        assert h.await_args.args[0] == "room_finished"
        assert h.await_args.args[2] == f"call-{channel_id}"

    @pytest.mark.asyncio
    async def test_shared_webhook_ignores_foreign_rooms(self):
        from app.core.routes.channel_broadcasts import livekit_webhook
        event = {"event": "room_finished", "room": {"name": "interview-xyz"}}
        request = MagicMock()
        request.body = AsyncMock(return_value=b"{}")

        with patch(f"{LK}.receive_webhook", return_value=event), \
             patch(f"{MOD}.handle_call_webhook_event", AsyncMock()) as h:
            resp = await livekit_webhook(request, authorization="Bearer x")

        assert resp == {"ok": True}
        h.assert_not_awaited()

"""ChannelConnectionManager availability invariants + pure helpers.

    cd server && ./venv/bin/python -m pytest tests/werk/ -q
"""
import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.werk.routes import channels_ws as ws_mod
from app.werk.routes.channels_ws import (
    ChannelConnectionManager, ChannelUser, _should_process_envelope, _TokenBucket, _process_envelope,
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

    @pytest.mark.asyncio
    async def test_disconnect_completes_with_redis_down_and_dead_sibling_socket(self):
        # Same deadlock shape, exercised via disconnect(): user A leaves a
        # room while user B's socket in that room is dead.
        m = ChannelConnectionManager()
        uid_a, uid_b = uuid4(), uuid4()
        ws_a = _fake_ws()
        ws_b_dead = _fake_ws(send_fails=True)
        await m.connect(ws_a, _user(uid_a))
        await m.connect(ws_b_dead, _user(uid_b))
        await m.join_room(uid_a, "room1")
        await m.join_room(uid_b, "room1")
        await asyncio.wait_for(m.disconnect(ws_a, uid_a), timeout=5)


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

    @pytest.mark.asyncio
    async def test_send_to_user_delivers_locally_when_redis_none(self):
        m = ChannelConnectionManager()
        uid = uuid4()
        ws = _fake_ws()
        await m.connect(ws, _user(uid))
        await m.send_to_user(uid, {"type": "notification"})
        ws.send_text.assert_awaited()

    @pytest.mark.asyncio
    async def test_send_to_users_multicasts_locally(self):
        m = ChannelConnectionManager()
        uid1, uid2 = uuid4(), uuid4()
        ws1, ws2 = _fake_ws(), _fake_ws()
        await m.connect(ws1, _user(uid1))
        await m.connect(ws2, _user(uid2))
        await m.send_to_users({uid1: {"type": "notification", "n": 1}, uid2: {"type": "notification", "n": 2}})
        ws1.send_text.assert_awaited()
        ws2.send_text.assert_awaited()

    def test_should_process_envelope_skips_own_origin(self):
        assert _should_process_envelope({"origin": "w1"}, "w1") is False
        assert _should_process_envelope({"origin": "w2"}, "w1") is True
        # Pre-deploy envelope without origin: process (rolling restart).
        assert _should_process_envelope({}, "w1") is True


class TestProcessEnvelopeUsersKind:
    @pytest.mark.asyncio
    async def test_users_envelope_delivers_to_every_local_recipient_concurrently(self, monkeypatch):
        # _process_envelope reads the module-level `manager` singleton, not a
        # parameter — swap in a fresh instance for the duration of this test
        # so it can't see state from another test.
        m = ChannelConnectionManager()
        monkeypatch.setattr(ws_mod, "manager", m)
        uid1, uid2, uid3 = uuid4(), uuid4(), uuid4()
        ws1, ws2, ws3 = _fake_ws(), _fake_ws(), _fake_ws()
        await m.connect(ws1, _user(uid1))
        await m.connect(ws2, _user(uid2))
        await m.connect(ws3, _user(uid3))

        envelope = {
            "kind": "users",
            "origin": "some-other-worker",
            "messages": {
                str(uid1): {"type": "notification", "n": 1},
                str(uid2): {"type": "notification", "n": 2},
                str(uid3): {"type": "notification", "n": 3},
            },
        }
        await asyncio.wait_for(_process_envelope(envelope), timeout=5)
        ws1.send_text.assert_awaited()
        ws2.send_text.assert_awaited()
        ws3.send_text.assert_awaited()

    @pytest.mark.asyncio
    async def test_users_envelope_one_slow_recipient_does_not_block_the_others(self, monkeypatch):
        # Regression guard for the serial-loop version of this branch: a
        # single slow/hung local delivery must not delay every other
        # recipient in the same batch (head-of-line blocking on the shared
        # per-worker fanout subscriber).
        m = ChannelConnectionManager()
        monkeypatch.setattr(ws_mod, "manager", m)
        uid_slow, uid_fast = uuid4(), uuid4()
        ws_slow, ws_fast = _fake_ws(), _fake_ws()

        async def _slow_send(*args, **kwargs):
            await asyncio.sleep(1)
        ws_slow.send_text = AsyncMock(side_effect=_slow_send)

        await m.connect(ws_slow, _user(uid_slow))
        await m.connect(ws_fast, _user(uid_fast))

        envelope = {
            "kind": "users",
            "origin": "some-other-worker",
            "messages": {
                str(uid_slow): {"type": "notification"},
                str(uid_fast): {"type": "notification"},
            },
        }
        task = asyncio.ensure_future(_process_envelope(envelope))
        await asyncio.sleep(0.05)
        # The fast recipient's delivery completed without waiting on the
        # slow one — proof the two ran concurrently, not one-after-another.
        ws_fast.send_text.assert_awaited()
        await asyncio.wait_for(task, timeout=5)


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

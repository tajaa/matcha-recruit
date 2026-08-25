"""Regression tests for `_bg_ems_draft_untargeted_reply` and its hot-path
gating helpers (`_note_ems_draft`/`_channel_recently_ems_drafted`) — the
event-draft twin of `_bg_schedule_untargeted_reply`
(tests/channels_ws/test_schedule_untargeted_reply.py).

Reported symptom: Huume posts "Add it to Events? Reply confirm or not an
event." — a plain "confirm" typed as a new message (not a threaded reply to
the pill) got no response at all, because `_ems_dispatch_decision` spawns
nothing without a threaded-reply-to-system or an @huume mention. Worse with
a mention: "@huume confirm" fell through to `classify_intent`, which has no
confirm/reject case and defaults to LOG, minting a *second* event draft
titled "confirm".

    cd server && ./venv/bin/python -m pytest tests/channels_ws/test_ems_draft_untargeted_reply.py -q
"""

import time
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.werk.routes import channels_ws


class _Conn:
    def __init__(self, row):
        self.row = row

    async def fetchrow(self, query, *args):
        return self.row


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *a):
        return False


class TestBgEmsDraftUntargetedReply:
    @pytest.mark.asyncio
    async def test_non_decision_text_never_queries_or_delegates(self, monkeypatch):
        def _boom():
            raise AssertionError("must not query the DB for non-decision text")
        monkeypatch.setattr(channels_ws, "get_connection", _boom)
        called = AsyncMock()
        monkeypatch.setattr(channels_ws, "_bg_ems_draft_reply", called)

        result = await channels_ws._bg_ems_draft_untargeted_reply(
            str(uuid4()), str(uuid4()), "ok thanks",
        )
        assert result is False
        called.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_pending_draft_returns_false(self, monkeypatch):
        monkeypatch.setattr(channels_ws, "get_connection", lambda: _Ctx(_Conn(None)))
        called = AsyncMock()
        monkeypatch.setattr(channels_ws, "_bg_ems_draft_reply", called)

        result = await channels_ws._bg_ems_draft_untargeted_reply(
            str(uuid4()), str(uuid4()), "confirm",
        )
        assert result is False
        called.assert_not_called()

    @pytest.mark.asyncio
    async def test_pending_draft_delegates_to_bg_ems_draft_reply(self, monkeypatch):
        confirmation_message_id = uuid4()
        monkeypatch.setattr(
            channels_ws, "get_connection",
            lambda: _Ctx(_Conn({"confirmation_message_id": confirmation_message_id})),
        )
        called = AsyncMock(return_value=True)
        monkeypatch.setattr(channels_ws, "_bg_ems_draft_reply", called)

        channel_id = str(uuid4())
        sender_id = str(uuid4())
        result = await channels_ws._bg_ems_draft_untargeted_reply(channel_id, sender_id, "confirm")

        assert result is True
        called.assert_awaited_once_with(
            channel_id, str(confirmation_message_id), sender_id, "confirm",
        )

    @pytest.mark.asyncio
    async def test_mention_is_stripped_before_delegating(self, monkeypatch):
        """"@huume confirm" must reach _bg_ems_draft_reply as "confirm" —
        that function refuses mention-bearing content whose decision is
        None, so a bare mention passthrough would silently no-op."""
        confirmation_message_id = uuid4()
        monkeypatch.setattr(
            channels_ws, "get_connection",
            lambda: _Ctx(_Conn({"confirmation_message_id": confirmation_message_id})),
        )
        called = AsyncMock(return_value=True)
        monkeypatch.setattr(channels_ws, "_bg_ems_draft_reply", called)

        result = await channels_ws._bg_ems_draft_untargeted_reply(
            str(uuid4()), str(uuid4()), "@huume confirm",
        )
        assert result is True
        args = called.await_args.args
        assert args[3] == "confirm"

    @pytest.mark.asyncio
    async def test_reject_decision_also_delegates(self, monkeypatch):
        confirmation_message_id = uuid4()
        monkeypatch.setattr(
            channels_ws, "get_connection",
            lambda: _Ctx(_Conn({"confirmation_message_id": confirmation_message_id})),
        )
        called = AsyncMock(return_value=True)
        monkeypatch.setattr(channels_ws, "_bg_ems_draft_reply", called)

        result = await channels_ws._bg_ems_draft_untargeted_reply(
            str(uuid4()), str(uuid4()), "not an event",
        )
        assert result is True
        called.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_query_exception_is_swallowed_returns_false(self, monkeypatch):
        class _BoomConn:
            async def fetchrow(self, *a, **k):
                raise RuntimeError("db down")
        monkeypatch.setattr(channels_ws, "get_connection", lambda: _Ctx(_BoomConn()))
        called = AsyncMock()
        monkeypatch.setattr(channels_ws, "_bg_ems_draft_reply", called)

        result = await channels_ws._bg_ems_draft_untargeted_reply(
            str(uuid4()), str(uuid4()), "confirm",
        )
        assert result is False
        called.assert_not_called()


class TestEmsDraftTtlGate:
    def setup_method(self):
        channels_ws._recent_ems_drafts.clear()

    def test_unmarked_channel_is_not_recent(self):
        assert channels_ws._channel_recently_ems_drafted(str(uuid4())) is False

    def test_marked_channel_is_recent(self):
        channel_id = str(uuid4())
        channels_ws._note_ems_draft(channel_id)
        assert channels_ws._channel_recently_ems_drafted(channel_id) is True

    def test_marker_expires_after_ttl(self, monkeypatch):
        channel_id = str(uuid4())
        channels_ws._note_ems_draft(channel_id)

        real_monotonic = time.monotonic
        future = real_monotonic() + channels_ws._EMS_DRAFT_TTL_SECONDS + 1
        monkeypatch.setattr(channels_ws.time, "monotonic", lambda: future)

        assert channels_ws._channel_recently_ems_drafted(channel_id) is False

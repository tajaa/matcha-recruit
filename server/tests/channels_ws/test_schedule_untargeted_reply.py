"""Regression test for `_bg_schedule_untargeted_reply` — the narrow fallback
that lets a plain (no @huume mention, no threaded reply) channel message
answer a live schedule clarify. A real transcript showed a bare "Willshire"
typed as a new message go completely unanswered: `_ems_dispatch_decision`
spawns nothing without a threaded-reply-to-system or an @huume mention, so
nothing ever looked at the message at all.

    cd server && ./venv/bin/python -m pytest tests/channels_ws/test_schedule_untargeted_reply.py -q
"""

import sys
from types import ModuleType
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

for _name in ("bleach", "audioop_lts", "audioop", "stripe"):
    if _name not in sys.modules:
        sys.modules[_name] = ModuleType(_name)
_bleach = sys.modules["bleach"]
_bleach.clean = lambda text, **kw: text
_bleach.linkify = lambda text, **kw: text


class _Conn:
    def __init__(self, row, location_rows=None):
        self.row = row
        self.location_rows = location_rows or []

    async def fetchrow(self, query, *args):
        return self.row

    async def fetch(self, query, *args):
        return self.location_rows


class _Ctx:
    def __init__(self, conn): self.conn = conn
    async def __aenter__(self): return self.conn
    async def __aexit__(self, *a): return False


@pytest.mark.asyncio
async def test_no_open_proposal_returns_false_without_dispatching(monkeypatch):
    from app.werk.routes import channels_ws

    monkeypatch.setattr(channels_ws, "get_connection", lambda: _Ctx(_Conn(None)))
    called = AsyncMock()
    monkeypatch.setattr(channels_ws, "_bg_schedule_reply", called)

    result = await channels_ws._bg_schedule_untargeted_reply(
        str(uuid4()), str(uuid4()), "Willshire",
    )
    assert result is False
    called.assert_not_called()


@pytest.mark.asyncio
async def test_over_length_message_short_circuits_before_any_query(monkeypatch):
    from app.werk.routes import channels_ws

    def _boom():
        raise AssertionError("must not query the DB for a long, non-clarify-shaped message")
    monkeypatch.setattr(channels_ws, "get_connection", _boom)
    called = AsyncMock()
    monkeypatch.setattr(channels_ws, "_bg_schedule_reply", called)

    result = await channels_ws._bg_schedule_untargeted_reply(
        str(uuid4()), str(uuid4()), "x" * 61,
    )
    assert result is False
    called.assert_not_called()


@pytest.mark.asyncio
async def test_typo_location_answer_delegates_to_bg_schedule_reply(monkeypatch):
    """The exact real-transcript case: a plain "Willshire" reply against a
    live LOCATION clarify must resolve — via match_location's fuzzy tier
    (checked directly here, since resolve_clarify_answer's plain containment
    check can't snap a typo against the full option string) — and be handed
    off to _bg_schedule_reply using the pill's own confirm_message_id, same
    claim path a threaded reply would use."""
    from app.matcha.services.scheduling import schedule_chat
    from app.werk.routes import channels_ws

    confirm_message_id = uuid4()
    row = {
        "company_id": uuid4(),
        "confirm_message_id": confirm_message_id,
        "proposal": {
            "clarify_question": schedule_chat.LOCATION_CLARIFY_QUESTION,
            "clarify_options": ["Sunset Smile Dental — Wilshire (Los Angeles)"],
        },
    }
    location_rows = [{"id": "1", "name": "Sunset Smile Dental — Wilshire",
                       "address": "", "city": "Los Angeles", "state": "CA", "zipcode": ""}]
    monkeypatch.setattr(channels_ws, "get_connection", lambda: _Ctx(_Conn(row, location_rows)))
    called = AsyncMock(return_value=True)
    monkeypatch.setattr(channels_ws, "_bg_schedule_reply", called)

    channel_id = str(uuid4())
    sender_id = str(uuid4())
    result = await channels_ws._bg_schedule_untargeted_reply(channel_id, sender_id, "Willshire")

    assert result is True
    called.assert_awaited_once_with(channel_id, str(confirm_message_id), sender_id, "Willshire")


@pytest.mark.asyncio
async def test_non_matching_plain_chatter_is_left_alone(monkeypatch):
    """Ordinary chatter near an open clarify must NOT be swept in — only
    text that actually resolves against the clarify's own options/time/
    location counts as an answer."""
    from app.matcha.services.scheduling import schedule_chat
    from app.werk.routes import channels_ws

    row = {
        "company_id": uuid4(),
        "confirm_message_id": uuid4(),
        "proposal": {
            "clarify_question": schedule_chat.LOCATION_CLARIFY_QUESTION,
            "clarify_options": ["Sunset Smile Dental — Wilshire (Los Angeles)"],
        },
    }
    location_rows = [{"id": "1", "name": "Sunset Smile Dental — Wilshire",
                       "address": "", "city": "Los Angeles", "state": "CA", "zipcode": ""}]
    monkeypatch.setattr(channels_ws, "get_connection", lambda: _Ctx(_Conn(row, location_rows)))
    called = AsyncMock()
    monkeypatch.setattr(channels_ws, "_bg_schedule_reply", called)

    result = await channels_ws._bg_schedule_untargeted_reply(str(uuid4()), str(uuid4()), "ok thanks")
    assert result is False
    called.assert_not_called()

"""Regression tests for `_bg_schedule_untargeted_reply` — the narrow fallback
that lets a plain (no @huume mention, no threaded reply) channel message
answer a live schedule clarify — and its hot-path gating helpers
(`_note_schedule_clarify`/`_channel_recently_clarified`).

A real transcript showed a bare "Willshire" typed as a new message go
completely unanswered: `_ems_dispatch_decision` spawns nothing without a
threaded-reply-to-system or an @huume mention, so nothing ever looked at the
message at all. A follow-up code review then found the first version of this
fallback over-claimed: `resolve_clarify_answer`'s plain containment check let
substrings like "Kim", "unstaffed", or "ed" hijack a live clarify pill, and
an employee's ordinary chatter could surface the "Only a business admin
can…" refusal into the channel unprompted. This file pins the tightened
behavior — full option echo, unique fuzzy location resolution, or an exact
clock-time match against one option's own printed start time, gated on
sender role BEFORE any match runs.

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
    def __init__(self, row, location_rows=None, role="client"):
        self.row = row
        self.location_rows = location_rows or []
        self.role = role

    async def fetchrow(self, query, *args):
        return self.row

    async def fetch(self, query, *args):
        return self.location_rows

    async def fetchval(self, query, *args):
        return self.role


class _Ctx:
    def __init__(self, conn): self.conn = conn
    async def __aenter__(self): return self.conn
    async def __aexit__(self, *a): return False


_LOCATION_QUESTION = "Which location did you mean?"  # schedule_chat.LOCATION_CLARIFY_QUESTION
_SHIFT_OPTIONS = [
    "Shift — Fri Aug 7 08:00–16:00 · Aisha Kim",
    "Shift — Fri Aug 7 12:30–18:00 · unstaffed",
]


def _shift_row(**overrides):
    row = {
        "company_id": uuid4(),
        "confirm_message_id": uuid4(),
        "proposal": {"clarify_question": "Which shift did you mean?", "clarify_options": list(_SHIFT_OPTIONS)},
    }
    row.update(overrides)
    return row


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
    (checked directly here, since the full-option-echo tier can't match a
    typo against the full option string) — and be handed off to
    _bg_schedule_reply using the pill's own confirm_message_id, same claim
    path a threaded reply would use."""
    from app.werk.routes import channels_ws

    confirm_message_id = uuid4()
    row = _shift_row(
        confirm_message_id=confirm_message_id,
        proposal={
            "clarify_question": _LOCATION_QUESTION,
            "clarify_options": ["Sunset Smile Dental — Wilshire (Los Angeles)"],
        },
    )
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
    from app.werk.routes import channels_ws

    row = _shift_row(proposal={
        "clarify_question": _LOCATION_QUESTION,
        "clarify_options": ["Sunset Smile Dental — Wilshire (Los Angeles)"],
    })
    location_rows = [{"id": "1", "name": "Sunset Smile Dental — Wilshire",
                       "address": "", "city": "Los Angeles", "state": "CA", "zipcode": ""}]
    monkeypatch.setattr(channels_ws, "get_connection", lambda: _Ctx(_Conn(row, location_rows)))
    called = AsyncMock()
    monkeypatch.setattr(channels_ws, "_bg_schedule_reply", called)

    result = await channels_ws._bg_schedule_untargeted_reply(str(uuid4()), str(uuid4()), "ok thanks")
    assert result is False
    called.assert_not_called()


class TestSubstringChatterNeverClaims:
    """Review finding: resolve_clarify_answer's containment check let a
    substring of exactly one option hijack the clarify. None of these must
    claim against _SHIFT_OPTIONS anymore — a bare name or word fragment
    stays ordinary chatter on the untargeted path (a THREADED reply still
    goes through the looser resolve_clarify_answer in _bg_schedule_reply,
    where reply-to is an explicit signal this fallback doesn't have)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("text", ["Kim", "Aisha Kim", "unstaffed", "ed", "7 08"])
    async def test_substring_never_claims(self, monkeypatch, text):
        from app.werk.routes import channels_ws

        row = _shift_row()
        monkeypatch.setattr(channels_ws, "get_connection", lambda: _Ctx(_Conn(row)))
        called = AsyncMock()
        monkeypatch.setattr(channels_ws, "_bg_schedule_reply", called)

        result = await channels_ws._bg_schedule_untargeted_reply(str(uuid4()), str(uuid4()), text)
        assert result is False, f"{text!r} incorrectly claimed the clarify pill"
        called.assert_not_called()


class TestSenderRoleGate:
    @pytest.mark.asyncio
    async def test_employee_sender_never_claims_even_on_a_full_echo(self, monkeypatch):
        from app.werk.routes import channels_ws

        row = _shift_row()
        monkeypatch.setattr(channels_ws, "get_connection", lambda: _Ctx(_Conn(row, role="employee")))
        called = AsyncMock()
        monkeypatch.setattr(channels_ws, "_bg_schedule_reply", called)

        result = await channels_ws._bg_schedule_untargeted_reply(
            str(uuid4()), str(uuid4()), _SHIFT_OPTIONS[0],
        )
        assert result is False
        called.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_sender_full_echo_claims(self, monkeypatch):
        from app.werk.routes import channels_ws

        confirm_message_id = uuid4()
        row = _shift_row(confirm_message_id=confirm_message_id)
        monkeypatch.setattr(channels_ws, "get_connection", lambda: _Ctx(_Conn(row, role="admin")))
        called = AsyncMock(return_value=True)
        monkeypatch.setattr(channels_ws, "_bg_schedule_reply", called)

        result = await channels_ws._bg_schedule_untargeted_reply(
            str(uuid4()), str(uuid4()), _SHIFT_OPTIONS[0],
        )
        assert result is True
        called.assert_awaited_once()


class TestFullOptionEcho:
    @pytest.mark.asyncio
    async def test_exact_echo_claims(self, monkeypatch):
        from app.werk.routes import channels_ws

        confirm_message_id = uuid4()
        row = _shift_row(confirm_message_id=confirm_message_id)
        monkeypatch.setattr(channels_ws, "get_connection", lambda: _Ctx(_Conn(row)))
        called = AsyncMock(return_value=True)
        monkeypatch.setattr(channels_ws, "_bg_schedule_reply", called)

        channel_id, sender_id = str(uuid4()), str(uuid4())
        result = await channels_ws._bg_schedule_untargeted_reply(channel_id, sender_id, _SHIFT_OPTIONS[1])
        assert result is True
        called.assert_awaited_once_with(channel_id, str(confirm_message_id), sender_id, _SHIFT_OPTIONS[1])

    @pytest.mark.asyncio
    async def test_echo_strips_city_suffix_for_location_options(self, monkeypatch):
        from app.werk.routes import channels_ws

        confirm_message_id = uuid4()
        row = _shift_row(
            confirm_message_id=confirm_message_id,
            proposal={
                "clarify_question": _LOCATION_QUESTION,
                "clarify_options": ["Sunset Smile Dental — Wilshire (Los Angeles)"],
            },
        )
        monkeypatch.setattr(channels_ws, "get_connection", lambda: _Ctx(_Conn(row)))
        called = AsyncMock(return_value=True)
        monkeypatch.setattr(channels_ws, "_bg_schedule_reply", called)

        result = await channels_ws._bg_schedule_untargeted_reply(
            str(uuid4()), str(uuid4()), "Sunset Smile Dental — Wilshire",
        )
        assert result is True
        called.assert_awaited_once()


class TestTimeMatchesExactlyOneOption:
    @pytest.mark.asyncio
    async def test_time_matching_one_option_claims(self, monkeypatch):
        from app.werk.routes import channels_ws

        confirm_message_id = uuid4()
        row = _shift_row(confirm_message_id=confirm_message_id)
        monkeypatch.setattr(channels_ws, "get_connection", lambda: _Ctx(_Conn(row)))
        called = AsyncMock(return_value=True)
        monkeypatch.setattr(channels_ws, "_bg_schedule_reply", called)

        result = await channels_ws._bg_schedule_untargeted_reply(str(uuid4()), str(uuid4()), "12:30")
        assert result is True
        called.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_time_matching_no_option_does_not_claim(self, monkeypatch):
        # A real review finding: "2026" parses as 20:26 via the colonless-
        # clock normalization, but neither _SHIFT_OPTIONS shift starts then
        # — must not claim on that alone.
        from app.werk.routes import channels_ws

        row = _shift_row()
        monkeypatch.setattr(channels_ws, "get_connection", lambda: _Ctx(_Conn(row)))
        called = AsyncMock()
        monkeypatch.setattr(channels_ws, "_bg_schedule_reply", called)

        result = await channels_ws._bg_schedule_untargeted_reply(str(uuid4()), str(uuid4()), "2026")
        assert result is False
        called.assert_not_called()

    @pytest.mark.asyncio
    async def test_time_matching_both_options_does_not_claim(self, monkeypatch):
        from app.werk.routes import channels_ws

        row = _shift_row(proposal={
            "clarify_question": "Which shift did you mean?",
            "clarify_options": [
                "Shift — Fri Aug 7 08:00–16:00 · Aisha Kim",
                "Shift — Sat Aug 8 08:00–16:00 · unstaffed",
            ],
        })
        monkeypatch.setattr(channels_ws, "get_connection", lambda: _Ctx(_Conn(row)))
        called = AsyncMock()
        monkeypatch.setattr(channels_ws, "_bg_schedule_reply", called)

        result = await channels_ws._bg_schedule_untargeted_reply(str(uuid4()), str(uuid4()), "8am")
        assert result is False
        called.assert_not_called()


class TestExceptionSafety:
    @pytest.mark.asyncio
    async def test_internal_exception_returns_false_not_raises(self, monkeypatch):
        from app.werk.routes import channels_ws

        def _boom():
            raise RuntimeError("pool exhausted")
        monkeypatch.setattr(channels_ws, "get_connection", _boom)
        called = AsyncMock()
        monkeypatch.setattr(channels_ws, "_bg_schedule_reply", called)

        result = await channels_ws._bg_schedule_untargeted_reply(str(uuid4()), str(uuid4()), "12:30")
        assert result is False
        called.assert_not_called()


class TestClarifyRegistry:
    """_note_schedule_clarify / _channel_recently_clarified — the in-memory
    gate that keeps _bg_schedule_untargeted_reply's DB probe off the hot
    path for the overwhelming common case (a channel with no live schedule
    clarify at all)."""

    def test_noted_channel_is_recently_clarified(self):
        from app.werk.routes import channels_ws

        channel_id = str(uuid4())
        channels_ws._note_schedule_clarify(channel_id)
        assert channels_ws._channel_recently_clarified(channel_id) is True

    def test_unnoted_channel_is_not_recently_clarified(self):
        from app.werk.routes import channels_ws

        assert channels_ws._channel_recently_clarified(str(uuid4())) is False

    def test_ttl_expiry(self, monkeypatch):
        from app.werk.routes import channels_ws

        channel_id = str(uuid4())
        channels_ws._note_schedule_clarify(channel_id)
        future = channels_ws.time.monotonic() + channels_ws._SCHEDULE_CLARIFY_TTL_SECONDS + 1
        monkeypatch.setattr(channels_ws.time, "monotonic", lambda: future)
        assert channels_ws._channel_recently_clarified(channel_id) is False

"""Tests for the EMS WS dispatch decision — the fix for two review findings:
a reply that both targets a Huume clarify pill AND @-mentions huume used to
fire _bg_ems_intake and _bg_ems_clarify independently (a duplicate event),
and _bg_ems_clarify's claim-UPDATE ran as a pooled-connection probe against
EVERY reply in every channel/tenant, not just ones that could plausibly be
answering a question.

_ems_dispatch_decision is pure (no DB/Gemini) — the send handler in
channels_ws.py just unpacks it. _bg_ems_dispatch is the thin router that
uses the decision's `reply_to_system` half to try the clarify claim first,
falling through to intake only on a claim miss.

    cd server && ./venv/bin/python -m pytest tests/ems/test_ems_dispatch.py -q
"""

from unittest.mock import AsyncMock

import pytest

# conftest.py already installs a permissive google.genai stub before any
# app.* import — see its module docstring. Import channels_ws lazily
# (inside functions/fixtures) is unnecessary here since conftest runs first
# for the whole suite; a plain module-level import matches
# tests/channels_ws/test_channel_connection_manager.py's pattern once that
# stub is in place.

from app.werk.routes import channels_ws


class TestEmsDispatchDecision:
    """Pure (spawn_task, reply_to_system) truth table."""

    def test_ordinary_reply_spawns_nothing(self):
        # reply_target_type is None when there's no reply, or "user" when
        # replying to a normal message — either way, no @huume mention
        # means nothing for EMS to do. This is the finding-7 fix: the old
        # code spawned a task (and took a pooled connection) for every
        # reply regardless.
        assert channels_ws._ems_dispatch_decision(
            reply_target_type=None, has_huume_mention=False,
        ) == (False, False)
        assert channels_ws._ems_dispatch_decision(
            reply_target_type="user", has_huume_mention=False,
        ) == (False, False)

    def test_reply_to_system_spawns_clarify_path(self):
        assert channels_ws._ems_dispatch_decision(
            reply_target_type="system", has_huume_mention=False,
        ) == (True, True)

    def test_mention_spawns_intake_path(self):
        assert channels_ws._ems_dispatch_decision(
            reply_target_type=None, has_huume_mention=True,
        ) == (True, False)

    def test_reply_to_system_with_mention_is_clarify_first(self):
        # The double-fire scenario: a reply to a Huume question that ALSO
        # @-mentions huume. reply_to_system=True means _bg_ems_dispatch
        # tries the clarify claim before ever considering intake.
        assert channels_ws._ems_dispatch_decision(
            reply_target_type="system", has_huume_mention=True,
        ) == (True, True)


class TestBgEmsDispatch:
    """_bg_ems_dispatch's fallthrough behavior, with _bg_ems_clarify and
    _bg_ems_intake mocked out — this is a pure control-flow test, not a DB
    test."""

    @pytest.mark.asyncio
    async def test_falls_through_to_intake_on_claim_miss(self, monkeypatch):
        clarify_mock = AsyncMock(return_value=False)  # stale pill, claim missed
        intake_mock = AsyncMock(return_value=None)
        monkeypatch.setattr(channels_ws, "_bg_ems_clarify", clarify_mock)
        monkeypatch.setattr(channels_ws, "_bg_ems_intake", intake_mock)

        await channels_ws._bg_ems_dispatch(
            "channel-1", "msg-1", "reply-to-system-1", "user-1", "@huume new thing",
            has_huume_mention=True,
        )

        clarify_mock.assert_awaited_once()
        intake_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stops_after_successful_claim(self, monkeypatch):
        clarify_mock = AsyncMock(return_value=True)  # claimed — this reply IS the answer
        intake_mock = AsyncMock(return_value=None)
        monkeypatch.setattr(channels_ws, "_bg_ems_clarify", clarify_mock)
        monkeypatch.setattr(channels_ws, "_bg_ems_intake", intake_mock)

        # Even with has_huume_mention=True (the double-fire scenario), a
        # successful claim must short-circuit — no second, duplicate event.
        await channels_ws._bg_ems_dispatch(
            "channel-1", "msg-1", "reply-to-system-1", "user-1", "@huume it was Jenna",
            has_huume_mention=True,
        )

        clarify_mock.assert_awaited_once()
        intake_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_reply_target_skips_clarify_entirely(self, monkeypatch):
        clarify_mock = AsyncMock(return_value=False)
        intake_mock = AsyncMock(return_value=None)
        monkeypatch.setattr(channels_ws, "_bg_ems_clarify", clarify_mock)
        monkeypatch.setattr(channels_ws, "_bg_ems_intake", intake_mock)

        await channels_ws._bg_ems_dispatch(
            "channel-1", "msg-1", None, "user-1", "@huume the ice machine is broken",
            has_huume_mention=True,
        )

        clarify_mock.assert_not_awaited()
        intake_mock.assert_awaited_once()


class TestIntakeDisposition:
    """Pure decision for _bg_ems_intake's model-side backstop — the
    classifier's not_an_event flag reroutes a message that regex-level
    classify_intent routed to LOG (see intent.py) but Gemini itself read as
    a question/request with nothing to document."""

    def test_not_an_event_reroutes_to_ask(self):
        classified = {"not_an_event": True, "category": "uncategorized"}
        assert channels_ws._intake_disposition(classified) == "reroute_ask"

    def test_normal_classification_persists(self):
        classified = {"not_an_event": False, "category": "safety"}
        assert channels_ws._intake_disposition(classified) == "persist"

    def test_missing_key_defaults_to_persist(self):
        # The Gemini-outage fallback shape carries not_an_event=False, but
        # this must degrade safely even without the key at all.
        assert channels_ws._intake_disposition({"category": "uncategorized"}) == "persist"

    def test_osha_overrides_reroute(self):
        # A message carrying an OSHA keyword that the model misread as a
        # question must still be documented — persisting a NULL not
        # rerouting to the ask path with zero DB trail.
        classified = {"not_an_event": True, "urgency": "osha"}
        assert channels_ws._intake_disposition(classified) == "persist"

    def test_not_an_event_without_osha_still_reroutes(self):
        classified = {"not_an_event": True, "urgency": None}
        assert channels_ws._intake_disposition(classified) == "reroute_ask"

"""_bg_ems_dispatch's routing to the schedule-chat handlers — a pure
control-flow test with _bg_ems_clarify/_bg_schedule_reply/_bg_schedule_request/
_bg_ems_intake mocked out, patched on `channels_ws` itself (the DEFINING
module — a patch on the service module a caller re-exports from would be a
silent no-op, per server/CLAUDE.md's patching rule). Modeled on
tests/ems/test_ems_dispatch.py.

    cd server && ./venv/bin/python -m pytest tests/ems/test_schedule_dispatch.py -q
"""

from unittest.mock import AsyncMock

import pytest

from app.werk.routes import channels_ws


class TestScheduleClaimOrdering:
    @pytest.mark.asyncio
    async def test_ems_clarify_claim_wins_before_schedule_claim_is_tried(self, monkeypatch):
        clarify_mock = AsyncMock(return_value=True)  # a live EMS question, claimed
        schedule_reply_mock = AsyncMock(return_value=False)
        monkeypatch.setattr(channels_ws, "_bg_ems_clarify", clarify_mock)
        monkeypatch.setattr(channels_ws, "_bg_schedule_reply", schedule_reply_mock)

        await channels_ws._bg_ems_dispatch(
            "channel-1", "msg-1", "reply-to-system-1", "user-1", "yes it was Jenna",
            has_huume_mention=False,
        )

        clarify_mock.assert_awaited_once()
        schedule_reply_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ems_clarify_miss_falls_through_to_schedule_claim(self, monkeypatch):
        clarify_mock = AsyncMock(return_value=False)
        schedule_reply_mock = AsyncMock(return_value=True)  # claimed by a live proposal
        intake_mock = AsyncMock(return_value=None)
        ask_mock = AsyncMock(return_value=None)
        monkeypatch.setattr(channels_ws, "_bg_ems_clarify", clarify_mock)
        monkeypatch.setattr(channels_ws, "_bg_schedule_reply", schedule_reply_mock)
        monkeypatch.setattr(channels_ws, "_bg_ems_intake", intake_mock)
        monkeypatch.setattr(channels_ws, "_bg_ems_ask", ask_mock)

        await channels_ws._bg_ems_dispatch(
            "channel-1", "msg-1", "reply-to-system-1", "user-1", "confirm",
            has_huume_mention=False,
        )

        clarify_mock.assert_awaited_once()
        schedule_reply_mock.assert_awaited_once()
        intake_mock.assert_not_awaited()
        ask_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_both_claims_miss_falls_through_to_mention_fork(self, monkeypatch):
        clarify_mock = AsyncMock(return_value=False)
        schedule_reply_mock = AsyncMock(return_value=False)
        intake_mock = AsyncMock(return_value=None)
        monkeypatch.setattr(channels_ws, "_bg_ems_clarify", clarify_mock)
        monkeypatch.setattr(channels_ws, "_bg_schedule_reply", schedule_reply_mock)
        monkeypatch.setattr(channels_ws, "_bg_ems_intake", intake_mock)

        # A reply to a stale schedule pill, but the text is itself a new
        # @huume report — must not be swallowed.
        await channels_ws._bg_ems_dispatch(
            "channel-1", "msg-1", "reply-to-system-1", "user-1",
            "@huume the walk-in freezer is out again",
            has_huume_mention=True,
        )

        clarify_mock.assert_awaited_once()
        schedule_reply_mock.assert_awaited_once()
        intake_mock.assert_awaited_once()


class TestScheduleIntentRouting:
    @pytest.mark.asyncio
    async def test_schedule_intent_routes_to_schedule_request(self, monkeypatch):
        request_mock = AsyncMock(return_value=None)
        intake_mock = AsyncMock(return_value=None)
        monkeypatch.setattr(channels_ws, "_bg_schedule_request", request_mock)
        monkeypatch.setattr(channels_ws, "_bg_ems_intake", intake_mock)

        await channels_ws._bg_ems_dispatch(
            "channel-1", "msg-1", None, "user-1",
            "@huume schedule an opener friday",
            has_huume_mention=True,
        )

        request_mock.assert_awaited_once()
        intake_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_log_intent_still_routes_to_intake(self, monkeypatch):
        request_mock = AsyncMock(return_value=None)
        intake_mock = AsyncMock(return_value=None)
        monkeypatch.setattr(channels_ws, "_bg_schedule_request", request_mock)
        monkeypatch.setattr(channels_ws, "_bg_ems_intake", intake_mock)

        await channels_ws._bg_ems_dispatch(
            "channel-1", "msg-1", None, "user-1",
            "@huume the opener called out sick",
            has_huume_mention=True,
        )

        intake_mock.assert_awaited_once()
        request_mock.assert_not_awaited()


class TestScheduleRequestParseFallback:
    @pytest.mark.asyncio
    async def test_non_actionable_parse_falls_back_to_intake(self, monkeypatch):
        from datetime import date as _date

        from app.matcha.services.scheduling import schedule_chat

        async def _fake_gate(conn, channel_id_str):
            return "company-1"

        parse_mock = AsyncMock(return_value=None)  # Gemini outage / non-actionable
        intake_mock = AsyncMock(return_value=None)
        monkeypatch.setattr(channels_ws, "_ems_company_gate", _fake_gate)
        monkeypatch.setattr(schedule_chat, "parse_schedule_request", parse_mock)
        monkeypatch.setattr(channels_ws, "_bg_ems_intake", intake_mock)

        class _FakeConn:
            async def fetchval(self, query, *args):
                return "admin"  # role lookup

        class _FakeConnCtx:
            async def __aenter__(self):
                return _FakeConn()

            async def __aexit__(self, *exc):
                return False

        monkeypatch.setattr(channels_ws, "get_connection", lambda: _FakeConnCtx())
        monkeypatch.setattr(
            channels_ws, "_schedule_company_features",
            AsyncMock(return_value={"ems": True, "employee_schedule": True}),
        )

        async def _fake_rate_limit(*args, **kwargs):
            return None

        monkeypatch.setattr(channels_ws, "check_rate_limit", _fake_rate_limit)

        user_id = "11111111-1111-1111-1111-111111111111"
        await channels_ws._bg_schedule_request(
            "channel-1", "msg-1", user_id, "@huume schedule an opener friday",
        )

        parse_mock.assert_awaited_once()
        intake_mock.assert_awaited_once_with("channel-1", "msg-1", user_id, "@huume schedule an opener friday")


class TestScheduleReplyRefusalRearms:
    @pytest.mark.asyncio
    async def test_refused_replier_rearms_the_original_pill(self, monkeypatch):
        """A reply from a non-manager (e.g. an employee replying "nice!" to
        a manager's proposal pill) must not permanently disarm the
        proposal: the claim nulls confirm_message_id before the role check
        runs, so a bare refusal without re-arming would strand the row —
        the manager's later 'confirm' would then miss the claim entirely
        and fall through to the mention fork. Regression for that bug."""
        from uuid import UUID

        from app.matcha.services.scheduling import schedule_chat

        reply_uuid = UUID("22222222-2222-2222-2222-222222222222")
        claim_id = UUID("33333333-3333-3333-3333-333333333333")
        sender_id = "11111111-1111-1111-1111-111111111111"

        executed = []

        class _FakeConn:
            async def fetchrow(self, query, *args):
                assert "UPDATE schedule_chat_proposals" in query
                assert "SET confirm_message_id = NULL" in query
                return {
                    "id": claim_id, "company_id": "company-1", "channel_id": "channel-1",
                    "source_message_id": "msg-1", "status": "proposed",
                    "proposal": "{}", "clarify_rounds": 0, "created_by": sender_id,
                }

            async def fetchval(self, query, *args):
                return "employee"  # not client/admin -> refused

            async def execute(self, query, *args):
                executed.append((query, args))

        class _FakeConnCtx:
            async def __aenter__(self):
                return _FakeConn()

            async def __aexit__(self, *exc):
                return False

        insert_mock = AsyncMock(return_value={"id": "sys-msg-1"})
        monkeypatch.setattr(channels_ws, "get_connection", lambda: _FakeConnCtx())
        monkeypatch.setattr(channels_ws, "_insert_system_message", insert_mock)
        monkeypatch.setattr(channels_ws, "_system_message_payload", lambda *a, **k: {})
        monkeypatch.setattr(channels_ws, "broadcast_system_message", AsyncMock())
        monkeypatch.setattr(
            channels_ws, "_schedule_company_features",
            AsyncMock(return_value={"ems": True, "employee_schedule": True}),
        )

        result = await channels_ws._bg_schedule_reply(
            "channel-1", str(reply_uuid), sender_id, "nice!",
        )

        assert result is True
        rearm_calls = [
            (q, a) for q, a in executed
            if "confirm_message_id = $1" in q and "WHERE id = $2" in q
        ]
        assert len(rearm_calls) == 1
        _, rearm_args = rearm_calls[0]
        assert rearm_args == (reply_uuid, claim_id)


class TestScheduleReplyLocationClarifyResume:
    """code-review fixes (2026-08-05) to the location-clarify resume block
    in _bg_schedule_reply: (1) a reply that does NOT snap onto one of the
    offered location options must still force-feed the raw reply into
    location_hint — narrowing the force-through to snapped-only answers
    silently lost to the channel's default store; (2) a re-parse coming
    back None on a NON-location clarify must bail immediately rather than
    resuming from stored_parse (which lacks the answer) and re-asking the
    identical question."""

    @staticmethod
    def _claim_conn(claimed_row, role="admin"):
        class _FakeConn:
            async def fetchrow(self, query, *args):
                assert "UPDATE schedule_chat_proposals" in query
                return claimed_row

            async def fetchval(self, query, *args):
                return role

            async def execute(self, query, *args):
                return None

        class _FakeConnCtx:
            async def __aenter__(self):
                return _FakeConn()

            async def __aexit__(self, *exc):
                return False

        return _FakeConnCtx()

    @pytest.mark.asyncio
    async def test_non_snapping_location_answer_still_forces_through(self, monkeypatch):
        from app.matcha.services.scheduling import schedule_chat

        reply_uuid = "22222222-2222-2222-2222-222222222222"
        claim_id = "33333333-3333-3333-3333-333333333333"
        sender_id = "11111111-1111-1111-1111-111111111111"
        options = [
            "Sunset Smile Dental — Wilshire (Los Angeles)",
            "Sunset Smile Dental — Downtown (Los Angeles)",
        ]
        claimed_row = {
            "id": claim_id, "company_id": "company-1", "channel_id": "channel-1",
            "source_message_id": "msg-1", "status": "clarifying",
            "proposal": {
                "kind": "create", "clarify_question": schedule_chat.LOCATION_CLARIFY_QUESTION,
                "clarify_options": options, "clarify_history": [], "original_content": "schedule an opener friday",
            },
            "parse": None, "clarify_rounds": 1, "created_by": sender_id,
        }

        conn_ctx = self._claim_conn(claimed_row)
        conn_ctxs = iter([conn_ctx, conn_ctx])
        monkeypatch.setattr(channels_ws, "get_connection", lambda: next(conn_ctxs))
        monkeypatch.setattr(
            channels_ws, "_schedule_company_features",
            AsyncMock(return_value={"ems": True, "employee_schedule": True}),
        )
        monkeypatch.setattr(channels_ws, "_insert_system_message", AsyncMock(return_value={"id": "sys-1"}))
        monkeypatch.setattr(channels_ws, "_system_message_payload", lambda *a, **k: {})
        monkeypatch.setattr(channels_ws, "broadcast_system_message", AsyncMock())

        # A reply that names a real place but doesn't snap onto either
        # offered option string — resolve_clarify_answer (real, unmocked)
        # returns it unchanged.
        reply_text = "the one over on Wilshire Blvd"

        # parse_schedule_request's re-parse must not come back with its own
        # location_hint, so the force-through is what supplies it.
        monkeypatch.setattr(
            schedule_chat, "parse_schedule_request",
            AsyncMock(return_value={"location_hint": None, "action": "create"}),
        )

        captured = {}

        async def fake_build_proposal(conn, **kwargs):
            captured["parsed"] = kwargs["parsed"]
            return schedule_chat.ProposalBuild(kind="proposal", proposal_id=claim_id, pill_text="ok")

        monkeypatch.setattr(schedule_chat, "build_proposal", fake_build_proposal)

        result = await channels_ws._bg_schedule_reply("channel-1", reply_uuid, sender_id, reply_text)

        assert result is True
        assert captured["parsed"]["location_hint"] == reply_text

    @pytest.mark.asyncio
    async def test_non_location_clarify_reparse_none_bails_without_reasking(self, monkeypatch):
        from app.matcha.services.scheduling import schedule_chat

        reply_uuid = "44444444-4444-4444-4444-444444444444"
        claim_id = "55555555-5555-5555-5555-555555555555"
        sender_id = "11111111-1111-1111-1111-111111111111"
        claimed_row = {
            "id": claim_id, "company_id": "company-1", "channel_id": "channel-1",
            "source_message_id": "msg-1", "status": "clarifying",
            "proposal": {
                "kind": "create", "clarify_question": "Which days should I schedule?",
                "clarify_options": [], "clarify_history": [], "original_content": "schedule an opener",
            },
            # A successfully-parsed original request WOULD be available,
            # but it has no `weekdays`/`date` — the very reason this
            # clarify fired — so resuming from it would just re-ask the
            # same question. Must bail instead.
            "parse": {"action": "create", "weekdays": [], "date": None},
            "clarify_rounds": 1, "created_by": sender_id,
        }

        conn_ctx = self._claim_conn(claimed_row)
        conn_ctxs = iter([conn_ctx, conn_ctx])
        monkeypatch.setattr(channels_ws, "get_connection", lambda: next(conn_ctxs))
        monkeypatch.setattr(
            channels_ws, "_schedule_company_features",
            AsyncMock(return_value={"ems": True, "employee_schedule": True}),
        )
        monkeypatch.setattr(channels_ws, "_insert_system_message", AsyncMock(return_value={"id": "sys-1"}))
        monkeypatch.setattr(channels_ws, "_system_message_payload", lambda *a, **k: {})
        monkeypatch.setattr(channels_ws, "broadcast_system_message", AsyncMock())
        monkeypatch.setattr(schedule_chat, "parse_schedule_request", AsyncMock(return_value=None))

        builder_mock = AsyncMock()
        monkeypatch.setattr(schedule_chat, "build_proposal", builder_mock)
        monkeypatch.setattr(schedule_chat, "build_edit_proposal", builder_mock)

        result = await channels_ws._bg_schedule_reply("channel-1", reply_uuid, sender_id, "Friday")

        assert result is True
        builder_mock.assert_not_called()  # no re-ask — cancelled with CLARIFY_BAIL_TEXT instead

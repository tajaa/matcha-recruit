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
from types import SimpleNamespace
from uuid import uuid4

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

    @pytest.mark.asyncio
    async def test_waste_report_routes_to_inventory(self, monkeypatch):
        inventory_mock = AsyncMock(return_value=None)
        intake_mock = AsyncMock(return_value=None)
        monkeypatch.setattr(channels_ws, "_bg_inventory_request", inventory_mock)
        monkeypatch.setattr(channels_ws, "_bg_ems_intake", intake_mock)

        await channels_ws._bg_ems_dispatch(
            "channel-1", "msg-1", None, "user-1",
            "@huume we wasted 3 bags of coffee today, it went expired",
            has_huume_mention=True,
        )

        inventory_mock.assert_awaited_once_with(
            "channel-1", "msg-1", "user-1",
            "@huume we wasted 3 bags of coffee today, it went expired",
        )
        intake_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mention_decision_claims_before_intake(self, monkeypatch):
        """"@huume confirm" against a live pill must resolve that pill, not
        classify_intent's bias-to-LOG default (which would mint a second
        draft titled "confirm" — the reported "seemed confused" bug)."""
        untargeted_mock = AsyncMock(return_value=True)
        intake_mock = AsyncMock(return_value=None)
        monkeypatch.setattr(channels_ws, "_bg_ems_draft_untargeted_reply", untargeted_mock)
        monkeypatch.setattr(channels_ws, "_bg_ems_intake", intake_mock)

        await channels_ws._bg_ems_dispatch(
            "channel-1", "msg-1", None, "user-1", "@huume confirm",
            has_huume_mention=True,
        )

        untargeted_mock.assert_awaited_once_with("channel-1", "user-1", "@huume confirm")
        intake_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mention_decision_miss_still_falls_through_to_intake(self, monkeypatch):
        """No live pill (fallback returns False) — a genuine "@huume ..."
        report must still be logged normally."""
        untargeted_mock = AsyncMock(return_value=False)
        intake_mock = AsyncMock(return_value=None)
        monkeypatch.setattr(channels_ws, "_bg_ems_draft_untargeted_reply", untargeted_mock)
        monkeypatch.setattr(channels_ws, "_bg_ems_intake", intake_mock)

        await channels_ws._bg_ems_dispatch(
            "channel-1", "msg-1", None, "user-1", "@huume the freezer is leaking",
            has_huume_mention=True,
        )

        untargeted_mock.assert_awaited_once()
        intake_mock.assert_awaited_once()


class TestInventoryWasteEventDualWrite:
    @pytest.mark.asyncio
    async def test_waste_capture_also_creates_an_ops_event(self, monkeypatch):
        class Connection:
            async def fetchrow(self, *_args):
                return {"name": "Espresso Beans (House Blend)", "current_quantity": 37}

            async def fetchval(self, *_args):
                return "employee"

        class ConnectionContext:
            async def __aenter__(self):
                return Connection()

            async def __aexit__(self, *_args):
                return False

        item = {"id": uuid4(), "name": "Espresso Beans (House Blend)"}
        movement = {
            "id": uuid4(), "item_id": item["id"], "quantity": 3,
            "quantity_estimated": False,
        }
        event_mock = AsyncMock()
        insert_mock = AsyncMock(return_value={"id": uuid4()})

        monkeypatch.setattr(channels_ws, "get_connection", lambda: ConnectionContext())
        monkeypatch.setattr(channels_ws, "check_rate_limit", AsyncMock())
        monkeypatch.setattr(channels_ws, "_inventory_company_gate", AsyncMock(return_value=uuid4()))
        monkeypatch.setattr(channels_ws, "_channel_location", AsyncMock(return_value=(uuid4(), "Downtown")))
        monkeypatch.setattr(
            channels_ws, "_schedule_company_features",
            AsyncMock(return_value={"inventory": True, "inventory_waste": True}),
        )
        monkeypatch.setattr(channels_ws, "_insert_system_message", insert_mock)
        monkeypatch.setattr(channels_ws, "_system_message_payload", lambda *_args: {})
        monkeypatch.setattr(channels_ws, "broadcast_system_message", AsyncMock())
        monkeypatch.setattr(channels_ws, "_bg_ems_intake", event_mock)

        from app.matcha.services.ems import event_intake
        from app.matcha.services.inventory import extraction, movements, pills

        monkeypatch.setattr(event_intake, "fallback_classification", lambda _content: {"urgency": None})
        monkeypatch.setattr(
            extraction, "extract_inventory",
            AsyncMock(return_value={
                "actionable": True,
                "kind": "waste",
                "lines": [{"item_name": "Espresso Beans (House Blend)", "quantity": 3}],
                "recipient_note": "expired",
                "waste_reason": "expired",
            }),
        )
        monkeypatch.setattr(movements, "list_item_names", AsyncMock(return_value=[{
            "id": item["id"], "name": item["name"], "normalized_name": "espresso beans house blend",
        }]))
        monkeypatch.setattr(movements, "find_item", AsyncMock(return_value=item))
        movement_mock = AsyncMock(return_value=[movement])
        monkeypatch.setattr(movements, "record_movements", movement_mock)
        monkeypatch.setattr(pills, "waste_pill", lambda *_args, **_kwargs: "waste logged")

        channel_id = str(uuid4())
        message_id = str(uuid4())
        user_id = str(uuid4())
        content = "@huume we wasted 3 bags of coffee today, it went expired"
        await channels_ws._bg_inventory_request(channel_id, message_id, user_id, content)

        event_mock.assert_awaited_once_with(channel_id, message_id, user_id, content)

        # Inventory movements dedupe on the source message. If an earlier
        # attempt wrote the ledger row but died before the EMS intake, the
        # retry must still hand the message to EMS's own idempotent intake.
        movement_mock.return_value = []
        await channels_ws._bg_inventory_request(channel_id, message_id, user_id, content)
        assert event_mock.await_count == 2


class TestHuumeMentionRouting:
    @pytest.mark.asyncio
    async def test_collab_code_claim_prevents_ems_dispatch(self, monkeypatch):
        code_mock = AsyncMock(return_value=True)
        ems_mock = AsyncMock()
        monkeypatch.setattr(channels_ws, "_bg_maybe_dispatch_huume_code", code_mock)
        monkeypatch.setattr(channels_ws, "_bg_ems_dispatch", ems_mock)

        await channels_ws._bg_dispatch_huume_mention(
            "channel-1", str(uuid4()), None, SimpleNamespace(id=uuid4()), "@huume fix login",
        )

        code_mock.assert_awaited_once()
        ems_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_collab_mention_falls_back_to_ems(self, monkeypatch):
        code_mock = AsyncMock(return_value=False)
        ems_mock = AsyncMock()
        monkeypatch.setattr(channels_ws, "_bg_maybe_dispatch_huume_code", code_mock)
        monkeypatch.setattr(channels_ws, "_bg_ems_dispatch", ems_mock)

        await channels_ws._bg_dispatch_huume_mention(
            "channel-1", str(uuid4()), None, SimpleNamespace(id=uuid4()), "@huume help",
        )

        ems_mock.assert_awaited_once()


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

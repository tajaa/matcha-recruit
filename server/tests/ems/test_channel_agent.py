"""The channel `@huume` tool-calling loop — proves the enforcement
properties without a real database or a real Gemini call: the model's own
choice of topic/tool never bypasses the server-side gates in
`channel_grounding.run_topic_lookup`, the loop is bounded, an inventory
order stages verbatim rather than through a model paraphrase, and total
failure degrades to the deterministic fallback line.

    cd server && ./venv/bin/python -m pytest tests/ems/test_channel_agent.py -q
"""

import asyncio

import pytest

from app.matcha.services.ems import channel_agent


def _run(coro):
    return asyncio.run(coro)


class _FnCall:
    def __init__(self, name, args):
        self.name = name
        self.args = args


class _Part:
    def __init__(self, function_call=None, text=None):
        self.function_call = function_call
        self.text = text


class _Content:
    def __init__(self, parts):
        self.parts = parts


class _Candidate:
    def __init__(self, parts):
        self.content = _Content(parts)


class _Resp:
    def __init__(self, parts=(), text=None):
        self.candidates = [_Candidate(list(parts))]
        self.text = text


class _FakeModels:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if not self._responses:
            raise AssertionError("channel_agent made more model calls than the test queued")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeAio:
    def __init__(self, responses):
        self.models = _FakeModels(responses)


class _FakeClient:
    def __init__(self, responses):
        self.aio = _FakeAio(responses)
        self.calls = self.aio.models.calls


class _FakeConnCtx:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


def _install(monkeypatch, *, responses):
    client = _FakeClient(responses)
    monkeypatch.setattr(channel_agent, "genai_env_client", lambda: client)
    monkeypatch.setattr("app.database.get_connection", lambda: _FakeConnCtx())
    return client


def _base_kwargs(**over):
    kwargs = dict(
        question="what's going on", events=[], is_admin=False, filtered=False,
        company_id="c1", channel_id="ch1", asker_user_id="u1", asker_role="employee",
        features={}, location_id=None, location_unavailable=False,
    )
    kwargs.update(over)
    return kwargs


class TestTopicEnforcementIsServerSide:
    def test_admin_only_topic_requested_by_an_employee_never_reaches_the_db(self, monkeypatch):
        # The model "hallucinating" a topic it was never offered (pto_leave
        # is admin_only and wouldn't even be in the declared enum for an
        # employee) must still be refused by run_topic_lookup's own gate —
        # the tool declaration is a hint, not the enforcement boundary.
        db_calls = []

        async def fake_lookup_impl(conn, **kwargs):
            db_calls.append(kwargs.get("topic"))
            return {"topic": kwargs.get("topic"), "active_leave": [{"first_name": "Jane", "last_name": "Doe", "leave_type": "medical"}]}

        monkeypatch.setattr(
            "app.matcha.services.huume.onboarding_skill.lookup_context_impl", fake_lookup_impl,
        )
        client = _install(monkeypatch, responses=[
            _Resp(parts=[_Part(function_call=_FnCall("lookup_context", {"topic": "pto_leave"}))]),
            _Resp(parts=[_Part(text="Can't help with that here.")], text="Can't help with that here."),
        ])

        result = _run(channel_agent.answer_channel_question(**_base_kwargs(
            question="who's out today", features={"employees": True}, asker_role="employee", is_admin=False,
        )))
        assert db_calls == []
        assert "Jane Doe" not in result["message"]
        assert "medical" not in result["message"].lower()
        assert len(client.calls) == 2

    def test_admin_requesting_an_allowed_topic_reaches_the_db(self, monkeypatch):
        db_calls = []

        async def fake_lookup_impl(conn, **kwargs):
            db_calls.append(kwargs.get("topic"))
            return {"topic": "pto_leave", "active_leave": [], "upcoming_pto": []}

        monkeypatch.setattr(
            "app.matcha.services.huume.onboarding_skill.lookup_context_impl", fake_lookup_impl,
        )
        _install(monkeypatch, responses=[
            _Resp(parts=[_Part(function_call=_FnCall("lookup_context", {"topic": "pto_leave"}))]),
            _Resp(parts=[_Part(text="Nobody's out this week.")], text="Nobody's out this week."),
        ])

        result = _run(channel_agent.answer_channel_question(**_base_kwargs(
            question="who's out this week", features={"employees": True}, asker_role="client", is_admin=True,
        )))
        assert db_calls == ["pto_leave"]
        assert "Nobody's out this week" in result["message"]

    def test_feature_off_topic_never_reaches_the_db(self, monkeypatch):
        db_calls = []

        async def fake_lookup_impl(conn, **kwargs):
            db_calls.append(kwargs.get("topic"))
            return {}

        monkeypatch.setattr(
            "app.matcha.services.huume.onboarding_skill.lookup_context_impl", fake_lookup_impl,
        )
        _install(monkeypatch, responses=[
            _Resp(parts=[_Part(function_call=_FnCall("lookup_context", {"topic": "training_status"}))]),
            _Resp(parts=[_Part(text="That's not set up here.")], text="That's not set up here."),
        ])

        result = _run(channel_agent.answer_channel_question(**_base_kwargs(
            question="any overdue training?", features={}, asker_role="client", is_admin=True,
        )))
        assert db_calls == []
        assert "not set up here" in result["message"]

    def test_dead_store_refuses_location_scoped_topic_but_serves_the_rest_in_the_same_turn(self, monkeypatch):
        db_calls = []

        async def fake_lookup_impl(conn, **kwargs):
            db_calls.append(kwargs.get("topic"))
            return {"topic": kwargs.get("topic"), "overdue": []}

        monkeypatch.setattr(
            "app.matcha.services.huume.onboarding_skill.lookup_context_impl", fake_lookup_impl,
        )
        _install(monkeypatch, responses=[
            _Resp(parts=[
                _Part(function_call=_FnCall("lookup_context", {"topic": "inventory"})),
                _Part(function_call=_FnCall("lookup_context", {"topic": "training_status"})),
            ]),
            _Resp(parts=[_Part(text="Store's paused, but no overdue training.")], text="Store's paused, but no overdue training."),
        ])

        result = _run(channel_agent.answer_channel_question(**_base_kwargs(
            question="stock and training check", features={"inventory": True, "training": True},
            asker_role="client", is_admin=True, location_unavailable=True,
        )))
        assert db_calls == ["training_status"]
        assert "Store's paused" in result["message"]


class TestLoopBounds:
    def test_stops_after_the_call_bound_and_falls_back(self, monkeypatch):
        # A model that never stops calling tools must not hang the channel
        # forever — the loop force-finishes and degrades to the same
        # deterministic line a total failure produces.
        async def fake_lookup_impl(conn, **kwargs):
            return {"topic": kwargs.get("topic")}

        monkeypatch.setattr(
            "app.matcha.services.huume.onboarding_skill.lookup_context_impl", fake_lookup_impl,
        )
        always_calling = [
            _Resp(parts=[_Part(function_call=_FnCall("lookup_context", {"topic": "inventory"}))])
            for _ in range(10)
        ]
        client = _install(monkeypatch, responses=always_calling)

        result = _run(channel_agent.answer_channel_question(**_base_kwargs(
            features={"inventory": True}, asker_role="client", is_admin=True,
        )))
        assert len(client.calls) == channel_agent._MAX_MODEL_CALLS
        assert result["message"] == channel_agent._FALLBACK_TEXT
        assert result["pending_order_id"] is None

    def test_total_model_failure_degrades_to_the_fallback_line(self, monkeypatch):
        _install(monkeypatch, responses=[RuntimeError("Gemini unavailable")])

        result = _run(channel_agent.answer_channel_question(**_base_kwargs()))
        assert result["message"] == channel_agent._FALLBACK_TEXT
        assert result["pending_order_id"] is None


class TestStageInventoryOrder:
    def test_staged_order_posts_the_pill_verbatim_and_stops_the_loop(self, monkeypatch):
        # The confirm affordance ("Reply confirm...") is load-bearing text
        # _bg_inventory_reply depends on — it must reach the channel exactly
        # as staged, never paraphrased through a second model call.
        async def fake_stage(conn, **kwargs):
            return {
                "text": "Staged fine", "order_id": "order-1",
                "pill_text": "\U0001F4E6 cups marked out of stock. Reply **confirm** to queue it.",
            }

        monkeypatch.setattr(channel_agent, "_stage_inventory_order", fake_stage)
        client = _install(monkeypatch, responses=[
            _Resp(parts=[_Part(function_call=_FnCall("stage_inventory_order", {"item_name": "cups"}))]),
            _Resp(parts=[_Part(text="should never be reached")], text="should never be reached"),
        ])

        result = _run(channel_agent.answer_channel_question(**_base_kwargs(
            question="order more cups", features={"inventory": True}, asker_role="employee", is_admin=False,
        )))
        assert result["pending_order_id"] == "order-1"
        assert result["message"].startswith("\U0001F4E6 cups marked out of stock")
        assert len(client.calls) == 1  # loop stopped immediately, no second (rephrasing) call

    def test_stage_tool_refused_when_inventory_is_off(self, monkeypatch):
        called = []

        async def fake_stage(conn, **kwargs):
            called.append(kwargs)
            return {"text": "should not run"}

        monkeypatch.setattr(channel_agent, "_stage_inventory_order", fake_stage)
        _install(monkeypatch, responses=[
            _Resp(parts=[_Part(function_call=_FnCall("stage_inventory_order", {"item_name": "cups"}))]),
            _Resp(parts=[_Part(text="Inventory isn't set up here.")], text="Inventory isn't set up here."),
        ])

        result = _run(channel_agent.answer_channel_question(**_base_kwargs(
            question="order more cups", features={}, asker_role="employee", is_admin=False,
        )))
        assert called == []
        assert result["pending_order_id"] is None
        assert "Inventory isn't set up here" in result["message"]

    def test_stage_tool_refused_when_channel_store_is_deactivated(self, monkeypatch):
        called = []

        async def fake_stage(conn, **kwargs):
            called.append(kwargs)
            return {"text": "should not run"}

        monkeypatch.setattr(channel_agent, "_stage_inventory_order", fake_stage)
        _install(monkeypatch, responses=[
            _Resp(parts=[_Part(function_call=_FnCall("stage_inventory_order", {"item_name": "cups"}))]),
            _Resp(parts=[_Part(text="This channel's store is deactivated.")], text="This channel's store is deactivated."),
        ])

        result = _run(channel_agent.answer_channel_question(**_base_kwargs(
            question="order more cups", features={"inventory": True}, asker_role="employee", is_admin=False,
            location_unavailable=True,
        )))
        assert called == []
        assert result["pending_order_id"] is None

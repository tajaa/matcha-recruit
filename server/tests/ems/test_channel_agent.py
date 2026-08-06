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

from app.matcha.services.ems import channel_agent, channel_grounding


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
        # forever — the loop stops after _MAX_MODEL_CALLS, then gets exactly
        # one extra tool-free call to try to write up whatever it already
        # learned (force-finish). If even THAT call keeps calling tools
        # (this model never stops), it still degrades to the same
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
        assert len(client.calls) == channel_agent._MAX_MODEL_CALLS + 1
        assert result["message"] == channel_agent._FALLBACK_TEXT
        assert result["pending_order_id"] is None

    def test_force_finish_call_writes_up_partial_work_on_bound_hit(self, monkeypatch):
        # The force-finish call is tools=None, so it can only return text —
        # that text becomes the answer instead of _FALLBACK_TEXT, even
        # though every lookup succeeded via tool calls the model never got
        # a turn to summarize on its own.
        async def fake_lookup_impl(conn, **kwargs):
            return {"topic": kwargs.get("topic")}

        monkeypatch.setattr(
            "app.matcha.services.huume.onboarding_skill.lookup_context_impl", fake_lookup_impl,
        )
        always_calling = [
            _Resp(parts=[_Part(function_call=_FnCall("lookup_context", {"topic": "inventory"}))])
            for _ in range(channel_agent._MAX_MODEL_CALLS)
        ]
        finishing = _Resp(parts=[_Part(text="here's what's on hand")], text="here's what's on hand")
        client = _install(monkeypatch, responses=[*always_calling, finishing])

        result = _run(channel_agent.answer_channel_question(**_base_kwargs(
            features={"inventory": True}, asker_role="client", is_admin=True,
        )))
        assert len(client.calls) == channel_agent._MAX_MODEL_CALLS + 1
        assert client.calls[-1]["config"].tools is None
        assert "here's what's on hand" in result["message"]
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

class TestCoverageTool:
    def test_declared_only_for_admin_with_schedule_reachable(self, monkeypatch):
        client = _install(monkeypatch, responses=[
            _Resp(parts=[_Part(text="nothing to check")], text="nothing to check"),
        ])
        _run(channel_agent.answer_channel_question(**_base_kwargs(
            features={"employee_schedule": True}, asker_role="client", is_admin=True,
        )))
        names = {d.name for d in client.calls[0]["config"].tools[0].function_declarations}
        assert "find_shift_coverage" in names

    def test_not_declared_for_employee(self, monkeypatch):
        client = _install(monkeypatch, responses=[
            _Resp(parts=[_Part(text="nothing to check")], text="nothing to check"),
        ])
        _run(channel_agent.answer_channel_question(**_base_kwargs(
            features={"employee_schedule": True}, asker_role="employee", is_admin=False,
        )))
        tools = client.calls[0]["config"].tools
        names = {d.name for d in tools[0].function_declarations} if tools else set()
        assert "find_shift_coverage" not in names

    def test_hallucinated_call_from_non_admin_is_refused_server_side(self, monkeypatch):
        # Even if the model calls find_shift_coverage despite never being
        # offered it, run_coverage_lookup's own is_admin re-check refuses —
        # the declaration is advisory, not the enforcement boundary.
        db_calls = []

        async def fake_find(conn, **kwargs):
            db_calls.append(kwargs)
            return {"shifts": [], "role_note": None}

        monkeypatch.setattr(
            "app.matcha.services.scheduling.coverage.find_coverage_candidates", fake_find,
        )
        client = _install(monkeypatch, responses=[
            _Resp(parts=[_Part(function_call=_FnCall("find_shift_coverage", {"date": "2026-08-05"}))]),
            _Resp(parts=[_Part(text="Can't help with that here.")], text="Can't help with that here."),
        ])

        _run(channel_agent.answer_channel_question(**_base_kwargs(
            features={"employee_schedule": True}, asker_role="employee", is_admin=False,
        )))
        assert db_calls == []
        second_call_contents = client.calls[1]["contents"]
        function_response_text = second_call_contents[-1].parts[0].function_response.response["result"]
        assert "admins" in function_response_text.lower()

    def test_admin_coverage_call_reaches_the_module_and_renders(self, monkeypatch):
        import datetime

        async def fake_find(conn, **kwargs):
            return {
                "shifts": [{
                    "starts_at": datetime.datetime(2026, 8, 5, 8, 0, tzinfo=datetime.timezone.utc),
                    "ends_at": datetime.datetime(2026, 8, 5, 16, 0, tzinfo=datetime.timezone.utc),
                    "role": "Front Desk", "required_staff": 1,
                    "assignees": ["Aisha Kim"],
                    "candidates": [{"name": "Dana Whitfield", "week_hours": 16.0,
                                     "job_title": "Front Desk", "title_mismatch": False, "flags": []}],
                }],
                "role_note": None,
            }

        monkeypatch.setattr(
            "app.matcha.services.scheduling.coverage.find_coverage_candidates", fake_find,
        )
        _install(monkeypatch, responses=[
            _Resp(parts=[_Part(function_call=_FnCall("find_shift_coverage", {"date": "2026-08-05"}))]),
            _Resp(parts=[_Part(text="Dana Whitfield can cover.")], text="Dana Whitfield can cover."),
        ])

        result = _run(channel_agent.answer_channel_question(**_base_kwargs(
            features={"employee_schedule": True}, asker_role="client", is_admin=True,
        )))
        assert "Dana Whitfield" in result["message"]

    def test_coverage_answer_carries_the_shift_link_token(self, monkeypatch):
        # channel_grounding.run_coverage_lookup's own text->model round-trip
        # can't be trusted to relay a [[shift:id:date]] token (the model
        # rewrites tool results into prose) — channel_agent staples it onto
        # the final message itself, same distrust-the-relay posture as
        # stage_inventory_order posting its pill verbatim.
        shift_id = "22222222-2222-2222-2222-222222222222"

        async def fake_run_coverage(conn, **kwargs):
            return {
                "text": "Dana Whitfield is free.", "degraded": False,
                "shift_links": [{"id": shift_id, "date": "2026-08-05"}],
            }

        monkeypatch.setattr(channel_grounding, "run_coverage_lookup", fake_run_coverage)
        _install(monkeypatch, responses=[
            _Resp(parts=[_Part(function_call=_FnCall("find_shift_coverage", {"date": "2026-08-05"}))]),
            _Resp(parts=[_Part(text="Dana Whitfield can cover.")], text="Dana Whitfield can cover."),
        ])

        result = _run(channel_agent.answer_channel_question(**_base_kwargs(
            features={"employee_schedule": True}, asker_role="client", is_admin=True,
        )))
        assert f"[[shift:{shift_id}:2026-08-05]]" in result["message"]

    def test_no_coverage_call_means_no_link_token(self, monkeypatch):
        _install(monkeypatch, responses=[
            _Resp(parts=[_Part(text="Nothing to check.")], text="Nothing to check."),
        ])
        result = _run(channel_agent.answer_channel_question(**_base_kwargs(is_admin=True, features={})))
        assert "[[shift:" not in result["message"]

    def test_system_prompt_carries_todays_date(self, monkeypatch):
        client = _install(monkeypatch, responses=[
            _Resp(parts=[_Part(text="ok")], text="ok"),
        ])
        _run(channel_agent.answer_channel_question(**_base_kwargs(is_admin=True, features={})))
        instr = client.calls[0]["config"].system_instruction
        assert "Today is" in instr

    def test_configs_never_use_thinking_budget_zero(self, monkeypatch):
        # thinking_budget: 0 is a hard 400 on 3.x models — see
        # huume/routing.py's own comment. thinking_level is the off switch.
        client = _install(monkeypatch, responses=[
            _Resp(parts=[_Part(text="ok")], text="ok"),
        ])
        _run(channel_agent.answer_channel_question(**_base_kwargs()))
        config = client.calls[0]["config"]
        assert config.max_output_tokens == 2000
        assert str(config.thinking_config.thinking_level).lower().endswith("low")
        assert config.thinking_config.thinking_budget is None


class TestStageInventoryOrderStoreDeactivated:
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


class TestRecentMessagesLiveInUserTurnNotSystemPrompt:
    """Untrusted channel content sits in the model's USER turn, never the
    system instruction — the system prompt holds the admin-only
    propose_schedule_change tool, and any channel member can author these
    messages, so they must not sit somewhere a model over-weights as
    operator instructions."""

    def test_recent_block_is_in_the_user_turn_not_the_system_prompt(self, monkeypatch):
        client = _install(monkeypatch, responses=[_Resp(parts=[_Part(text="ok")], text="ok")])
        _run(channel_agent.answer_channel_question(**_base_kwargs(
            recent_block="Casey: can you cover Friday for me?",
        )))
        call = client.calls[0]
        assert "Casey: can you cover Friday for me?" not in call["config"].system_instruction
        user_text = call["contents"][0].parts[0].text
        assert "Casey: can you cover Friday for me?" in user_text
        assert "RECENT CHANNEL MESSAGES" in user_text

    def test_no_recent_block_leaves_the_user_turn_as_just_the_question(self, monkeypatch):
        client = _install(monkeypatch, responses=[_Resp(parts=[_Part(text="ok")], text="ok")])
        _run(channel_agent.answer_channel_question(**_base_kwargs(question="what's going on")))
        assert client.calls[0]["contents"][0].parts[0].text == "what's going on"


class TestScheduleChangeToolSchema:
    """propose_schedule_change's declared params, mirrored against the
    thread-Huume tool of the same name (services/huume/tools.py) — both
    surfaces call schedule_chat.coerce_edit_request through their own
    _tool_args_to_edit_request mapper, so a field one schema omits is a
    field the model on that surface can never supply, even though the
    mapper already reads it (target_time_hint was exactly this gap here
    until fixed alongside target_staffing_hint)."""

    def test_declares_target_time_hint(self):
        props = channel_agent._SCHEDULE_CHANGE_DECLARATION.parameters.properties
        assert "target_time_hint" in props

    def test_declares_target_staffing_hint_with_the_right_enum(self):
        props = channel_agent._SCHEDULE_CHANGE_DECLARATION.parameters.properties
        assert "target_staffing_hint" in props
        assert set(props["target_staffing_hint"].enum) == {"staffed", "unstaffed"}

    def test_mapper_forwards_both_hints(self):
        args = {"kind": "assign", "target_date": "2026-08-12", "target_time_hint": "2pm",
                "target_staffing_hint": "unstaffed", "to_employee_name": "Elena Iyer"}
        mapped = channel_grounding._tool_args_to_edit_request("assign", args)
        assert mapped["target_time_hint"] == "2pm"
        assert mapped["target_staffing_hint"] == "unstaffed"

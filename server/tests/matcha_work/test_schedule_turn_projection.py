"""Saved wage data never reaches a de-entitled schedule model or SSE state."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.models.matcha_work.matcha_work import SendMessageRequest
from app.matcha.services.huume import agent, store
from app.matcha.services.matcha_work import turn_pipeline as pipeline
from app.matcha.services.scheduling.schedule_assistant_session import ScheduleAssistantScope
from app.matcha.services.scheduling import schedule_cost_projection as projection
from tests.employee_schedule.test_schedule_ui_projection import connection, full_week_review


@pytest.mark.asyncio
@pytest.mark.parametrize("role,enabled,visible", [("employee", True, False), ("client", False, False), ("client", True, True)])
async def test_turn_projects_model_input_updates_and_reread_output(monkeypatch, role, enabled, visible):
    thread_id, company_id, user_id, location_id = [uuid4() for _ in range(4)]
    state = {"huume_action": {"type": "schedule_week_draft", "status": "proposed",
                              "generation_run_id": str(uuid4()), "confirm_id": "same-confirmation",
                              "review": {"assignment_count": 28, "cost": {"after": 80}},
                              "demand_model": {"labor": {"labor_pct": 20}}}}
    tc = pipeline.TurnContext(
        thread_id=thread_id, company_id=company_id, body=SendMessageRequest(content="Review"),
        current_user=SimpleNamespace(id=user_id, role=role),
        thread={"huume_mode": True, "surface": "schedule_assistant", "current_state": state, "version": 3},
        schedule_scope=ScheduleAssistantScope(thread_id, company_id, user_id, location_id,
                                              date(2026, 10, 4), date(2026, 10, 10), role),
    )
    tc.msg_dicts = [
        {"role": "assistant", "content": "Payroll $80", "metadata": {"schedule_cost_visible": True}},
        {"role": "assistant", "content": "One seat open", "metadata": {"schedule_cost_visible": False}},
        {"role": "user", "content": "Review"},
    ]
    tc.user_msg = {"id": uuid4(), "thread_id": thread_id, "role": "user", "content": "Review",
                   "created_at": datetime.now(timezone.utc)}
    features = {"huume": True, "employee_schedule": True, "labor_cost": enabled}
    monkeypatch.setattr(pipeline, "get_company_features", AsyncMock(return_value=features))
    monkeypatch.setattr("app.core.services.redis_cache.check_rate_limit", AsyncMock())
    monkeypatch.setattr(store, "create_run", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(store, "get_thread_integrations", AsyncMock(return_value={}))
    monkeypatch.setattr(store, "complete_run", AsyncMock())
    captured = {}

    async def run_turn(**kwargs):
        captured.update(kwargs)
        yield {"type": "huume_result", "data": {"message": "Review ready", "steps": [{"result": {"cost": {"after": 80}}}],
                                                  "state_updates": state, "token_usage": None}}

    monkeypatch.setattr(agent, "run_huume_turn", run_turn)
    applied = AsyncMock(return_value={"current_state": state, "version": 4})
    monkeypatch.setattr(pipeline.doc_svc, "apply_update", applied)
    monkeypatch.setattr(pipeline.doc_svc, "get_thread", AsyncMock(return_value={"current_state": state, "version": 4}))

    async def add_message(_thread, _role, content, metadata):
        return {"id": uuid4(), "thread_id": thread_id, "role": "assistant", "content": content,
                "metadata": metadata, "created_at": datetime.now(timezone.utc)}

    saved = AsyncMock(side_effect=add_message)
    monkeypatch.setattr(pipeline.doc_svc, "add_message", saved)
    monkeypatch.setattr(pipeline, "_record_turn_usage", AsyncMock(return_value=None))
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def preview_connection():
        yield connection({"schedule_review": full_week_review()})

    monkeypatch.setattr(projection, "get_connection", preview_connection)
    from app.matcha.routes.work.thread_ws import thread_manager
    monkeypatch.setattr(thread_manager, "broadcast_new_message", AsyncMock())
    frames = [frame async for frame in pipeline._run_huume_dispatch(tc)]
    assert tc.terminated and any('"type": "complete"' in frame for frame in frames)
    assert ("cost" in captured["current_state"]["huume_action"]["review"]) is visible
    assert ("Payroll $80" in [message["content"] for message in captured["history"]]) is visible
    assert ("cost" in applied.call_args.args[1]["huume_action"]["review"]) is visible
    assert ("cost" in tc.current_state["huume_action"]["review"]) is visible
    assert len(tc.current_state["huume_action"]["review"]["assignments"]) == 28
    assert "assignments" not in captured["current_state"]["huume_action"]["review"]
    assert "assignments" not in applied.call_args.args[1]["huume_action"]["review"]
    assert tc.current_state["huume_action"]["confirm_id"] == "same-confirmation"
    assert saved.call_args.kwargs["metadata"]["schedule_cost_visible"] is visible
    assert ("cost" in saved.call_args.kwargs["metadata"]["huume_steps"][0]["result"]) is visible


@pytest.mark.asyncio
@pytest.mark.parametrize("role,enabled,visible", [("employee", True, False), ("client", False, False), ("client", True, True)])
async def test_transport_filters_legacy_history_and_compacted_summaries(monkeypatch, role, enabled, visible):
    from app.matcha.routes.matcha_work import messaging
    from app.matcha.services.matcha_work import matcha_work_ai

    thread_id, company_id, user_id, location_id = [uuid4() for _ in range(4)]
    thread = {"surface": "schedule_assistant", "status": "active", "company_id": company_id, "title": "Schedule",
              "current_state": {"huume_action": {"review": {"cost": {"after": 80}}}}}
    user = SimpleNamespace(id=user_id, role=role)
    scope = ScheduleAssistantScope(thread_id, company_id, user_id, location_id,
                                   date(2026, 10, 4), date(2026, 10, 10), role)
    monkeypatch.setattr(messaging, "get_client_company_id", AsyncMock(return_value=company_id))
    monkeypatch.setattr(messaging.doc_svc, "get_thread", AsyncMock(return_value=thread))
    monkeypatch.setattr(messaging, "get_company_features", AsyncMock(return_value={"employee_schedule": True, "labor_cost": enabled}))
    monkeypatch.setattr(messaging, "resolve_schedule_assistant_scope", AsyncMock(return_value=scope))
    monkeypatch.setattr(messaging, "_run_quota_gate", AsyncMock())
    prepared = AsyncMock()
    monkeypatch.setattr(messaging, "_prepare_attachments", prepared)
    monkeypatch.setattr(messaging.doc_svc, "get_thread_messages", AsyncMock(return_value=[
        {"role": "assistant", "content": "Payroll $80", "metadata": '{"schedule_cost_visible":true}'},
        {"role": "assistant", "content": "One seat open", "metadata": '{"schedule_cost_visible":false}'},
        {"role": "user", "content": "Review", "metadata": None},
    ]))
    monkeypatch.setattr(messaging.doc_svc, "get_company_profile_for_ai", AsyncMock(return_value={}))
    monkeypatch.setattr(messaging.doc_svc, "get_context_summary", AsyncMock(return_value=("Payroll $80", 2)))
    monkeypatch.setattr(messaging, "_inject_slide_context", lambda *args: None)
    monkeypatch.setattr(matcha_work_ai, "fetch_image_parts_for_messages", AsyncMock())
    monkeypatch.setattr(messaging, "get_ai_provider", lambda: object())
    monkeypatch.setattr(messaging, "_build_company_context", lambda profile: "")
    monkeypatch.setattr(messaging, "_fetch_project_meta", AsyncMock(return_value=None))
    monkeypatch.setattr(messaging, "_inject_recruiting_project_context", AsyncMock(return_value=""))
    response = await messaging.send_message_stream(thread_id, SendMessageRequest(content="Review"), user)
    assert response.media_type == "text/event-stream"
    tc = prepared.call_args.args[0]
    assert ("cost" in tc.thread["current_state"]["huume_action"]["review"]) is visible
    assert ("Payroll $80" in [message["content"] for message in tc.msg_dicts]) is visible
    assert (tc.context_summary is not None) is visible
    safe_message = next(message for message in tc.msg_dicts if message["content"] == "One seat open")
    assert safe_message["metadata"]["schedule_cost_visible"] is False

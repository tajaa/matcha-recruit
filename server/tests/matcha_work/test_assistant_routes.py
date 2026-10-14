from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.feature_flags import DEFAULT_COMPANY_FEATURES, FEATURE_REQUIRES, RETIRED_COMPANY_FEATURES
from app.matcha.models.matcha_work.assistant import AbilityEnableRequest, GoogleConnectRequest
from app.matcha.routes.matcha_work import assistant as routes
from app.matcha.services.billing import entitlements_service
from app.matcha.services.matcha_work.agent_runtime import consent, conversation, grants
from app.matcha.services.matcha_work.gmail_service import GMAIL_SCOPES, SCOPE_GMAIL_MODIFY

from tests.agent_runtime.helpers import FakeConn, connection


def _user():
    return SimpleNamespace(id=uuid4(), role="client", email="ana@example.com")


@pytest.fixture
def wired(monkeypatch):
    company = uuid4()
    monkeypatch.setattr(routes, "get_client_company_id", AsyncMock(return_value=company))
    conn = FakeConn()
    monkeypatch.setattr(routes, "get_connection", connection(conn))

    class Gmail:
        is_configured = True
        granted_scopes = frozenset(GMAIL_SCOPES)

        def __init__(self, user_id):
            pass

        async def load_token(self):
            return None

    monkeypatch.setattr(routes, "GmailService", Gmail)
    monkeypatch.delenv("ASSISTANT_COMMIT_MODE", raising=False)
    monkeypatch.delenv("AGENT_BROWSER_QUEUE", raising=False)
    monkeypatch.delenv("DUFFEL_ACCESS_TOKEN", raising=False)
    return SimpleNamespace(company=company, conn=conn, gmail=Gmail)


def test_there_is_no_company_flag_and_plans_still_apply():
    # Personal accounts get the assistant; no business switch exists.
    assert "espresso_assistant" not in DEFAULT_COMPANY_FEATURES
    assert "espresso_assistant" not in FEATURE_REQUIRES
    assert "espresso_assistant" in RETIRED_COMPANY_FEATURES
    assert entitlements_service.features_for_plan("pro")["assistant"] is True
    assert entitlements_service.features_for_plan("business")["assistant"] is True
    assert entitlements_service.features_for_plan("lite")["assistant"] is False
    assert entitlements_service.ASSISTANT_DAILY_RUNS == {"pro": 30, "business": 60}


def test_the_router_is_gated_and_mounted():
    from app.matcha.routes.matcha_work import router
    from tests._helpers.routes import iter_api_routes

    paths = {(m, r.path) for r in iter_api_routes(router) for m in r.methods if "/assistant" in r.path}
    assert paths == {
        ("POST", "/assistant/channel"), ("GET", "/assistant/runs/{run_id}"),
        ("GET", "/assistant/abilities"), ("PUT", "/assistant/abilities/{key}"),
        ("DELETE", "/assistant/abilities/{key}"),
        ("GET", "/assistant/conversations"), ("POST", "/assistant/conversations"),
        ("PATCH", "/assistant/conversations/{channel_id}"),
    }
    assert routes.router.prefix == "/assistant" and len(routes.router.dependencies) == 1


@pytest.mark.asyncio
async def test_only_a_personal_workspace_gets_the_routes(monkeypatch):
    from app.matcha.services.matcha_work.agent_runtime import enqueue

    user = _user()
    monkeypatch.setattr(routes, "get_client_company_id", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(enqueue, "workspace_enabled", AsyncMock(return_value=True))
    assert await routes.require_personal_workspace(current_user=user) is user
    monkeypatch.setattr(enqueue, "workspace_enabled", AsyncMock(return_value=False))
    with pytest.raises(HTTPException) as exc:
        await routes.require_personal_workspace(current_user=user)
    assert exc.value.status_code == 403 and exc.value.detail["code"] == "feature_disabled"
    monkeypatch.setattr(routes, "get_client_company_id", AsyncMock(return_value=None))
    with pytest.raises(HTTPException):
        await routes.require_personal_workspace(current_user=user)


@pytest.mark.asyncio
async def test_opening_the_conversation_is_idempotent_and_scoped_to_the_caller(wired, monkeypatch):
    channel = uuid4()
    ensure = AsyncMock(return_value=channel)
    monkeypatch.setattr(conversation, "ensure_assistant_channel", ensure)
    user = _user()
    assert await routes.ensure_assistant_channel(current_user=user) == {"channel_id": str(channel)}
    assert ensure.await_args.kwargs == {"user_id": user.id, "company_id": wired.company}
    routes.get_client_company_id.return_value = None
    with pytest.raises(HTTPException) as exc:
        await routes.ensure_assistant_channel(current_user=user)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_a_run_is_readable_only_by_the_person_who_asked(wired):
    user, run_id = _user(), uuid4()
    now = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
    wired.conn.on("FROM mw_project_agent_steps", [
        {"seq": 1, "kind": "search", "label": "Searched", "status": "ok", "created_at": now}])
    wired.conn.on("FROM mw_project_agent_runs", {
        "id": run_id, "status": "done", "surface": "assistant", "abilities": ["web"],
        "result": '{"schema": "agent_result.v2", "headline": "H", "blocks": []}', "error": None,
        "model_calls": 2, "search_calls": 1, "created_at": now, "started_at": now, "completed_at": None})
    out = await routes.get_assistant_run(run_id, current_user=user)
    assert out["id"] == str(run_id) and out["result"]["headline"] == "H" and out["completed_at"] is None
    assert out["steps"] == [{"seq": 1, "kind": "search", "label": "Searched", "status": "ok",
                             "created_at": now.isoformat()}]
    lookup = wired.conn.ran("FROM mw_project_agent_runs")[0]
    assert "requested_by = $2" in lookup[1] and lookup[2] == (run_id, user.id)

    wired.conn.on("FROM mw_project_agent_runs", None)
    with pytest.raises(HTTPException) as exc:
        await routes.get_assistant_run(run_id, current_user=_user())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_abilities_say_what_stands_in_the_way(wired, monkeypatch):
    monkeypatch.setattr(grants, "list_rows", AsyncMock(return_value={
        "email": {"enabled": True, "consent_version": consent.current_version("email"), "settings": {}},
        "calendar": {"enabled": True, "consent_version": "calendar-openai-0", "settings": {}},
    }))
    out = await routes.list_abilities(current_user=_user())
    by_key = {a["key"]: a for a in out["abilities"]}
    assert list(by_key) == ["web", "shopping", "flights", "email", "calendar", "sales", "reservations"]
    # Read-only, no consent needed; offered only where a Duffel token is set.
    assert by_key["flights"]["always_on"] and not by_key["flights"]["acts"]
    assert not by_key["flights"]["private_only"]
    assert by_key["flights"]["reason"] == "Not set up on this server yet."
    assert by_key["web"]["always_on"] and by_key["web"]["enabled"] and not by_key["web"]["acts"]
    assert by_key["web"]["disclosure"] is None
    email = by_key["email"]
    assert email["enabled"] and email["available"] and email["acts"] and email["private_only"]
    assert email["missing_scopes"] == [SCOPE_GMAIL_MODIFY] and email["needs_connection"]
    assert email["disclosure"]["version"] == "email-openai-1" and not email["consent_outdated"]
    calendar = by_key["calendar"]
    assert not calendar["enabled"] and calendar["needs_consent"] and calendar["consent_outdated"]
    assert by_key["reservations"]["reason"] == "Not set up on this server yet."
    assert out["google"] == {"connected": True, "scopes": sorted(GMAIL_SCOPES)}
    assert out["commit_mode"] == "dry_run"
    assert by_key["calendar"]["commit_mode"] == "live"
    assert by_key["email"]["commit_mode"] == "dry_run"


@pytest.mark.asyncio
async def test_buying_is_listed_only_for_accounts_allowed_to_buy(wired, monkeypatch):
    monkeypatch.setattr(grants, "list_rows", AsyncMock(return_value={}))
    monkeypatch.setenv("AGENT_PURCHASE_ALLOWED_EMAILS", "ana@example.com")
    out = await routes.list_abilities(current_user=_user())
    buying = {a["key"]: a for a in out["abilities"]}["purchase"]
    assert buying["acts"] and buying["private_only"] and buying["needs_consent"] and not buying["enabled"]
    assert buying["disclosure"]["version"] == "purchase-1"


@pytest.mark.asyncio
async def test_an_ability_not_offered_to_the_account_cannot_be_switched_on(wired, monkeypatch):
    enabled = AsyncMock()
    monkeypatch.setattr(grants, "enable", enabled)
    monkeypatch.delenv("AGENT_PURCHASE_ALLOWED_EMAILS", raising=False)
    with pytest.raises(HTTPException) as exc:
        await routes.enable_ability("purchase", AbilityEnableRequest(consent_version="purchase-1"),
                                    current_user=_user())
    assert exc.value.status_code == 404 and enabled.await_count == 0


@pytest.mark.asyncio
async def test_switching_an_ability_on_and_off(wired, monkeypatch):
    enabled = AsyncMock(return_value={"key": "email", "enabled": True, "settings": {}})
    disabled = AsyncMock(return_value={"key": "email", "enabled": False})
    monkeypatch.setattr(grants, "enable", enabled)
    monkeypatch.setattr(grants, "disable", disabled)
    user = _user()
    body = AbilityEnableRequest(consent_version="email-openai-1")
    assert (await routes.enable_ability("email", body, current_user=user))["enabled"] is True
    assert enabled.await_args.args == (user.id, wired.company, "email")
    assert enabled.await_args.kwargs == {"consent_version": "email-openai-1", "settings": {}}
    assert (await routes.disable_ability("email", current_user=user))["enabled"] is False
    assert disabled.await_args.args == (user.id, "email")
    for call in (routes.enable_ability("web", body, current_user=user),
                 routes.disable_ability("shopping", current_user=user)):
        with pytest.raises(HTTPException) as exc:
            await call
        assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        await routes.enable_ability("made_up", body, current_user=user)
    assert exc.value.status_code == 404


def test_request_models():
    assert GoogleConnectRequest().abilities == []
    assert GoogleConnectRequest(abilities=["calendar"]).abilities == ["calendar"]
    with pytest.raises(ValueError):
        GoogleConnectRequest(abilities=["x"] * 9)
    assert AbilityEnableRequest().settings == {} and AbilityEnableRequest().consent_version is None
    assert routes._iso(None) is None


@pytest.mark.asyncio
async def test_connect_asks_google_for_the_named_abilities_incrementally(monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    from app.matcha.routes.matcha_work import workspace
    from app.matcha.services.matcha_work import gmail_service

    monkeypatch.setattr(gmail_service, "get_oauth_credentials",
                        lambda: {"client_id": "cid", "client_secret": "s"})
    monkeypatch.setattr(workspace, "_issue_gmail_oauth_state", AsyncMock(return_value="state-1"))
    monkeypatch.setattr(workspace, "get_settings", lambda: SimpleNamespace(app_base_url="https://app.example"))
    out = await workspace.agent_email_connect(_user(), GoogleConnectRequest(abilities=["calendar"]))
    query = parse_qs(urlsplit(out["auth_url"]).query)
    assert query["scope"][0].split() == [*GMAIL_SCOPES, "https://www.googleapis.com/auth/calendar.events"]
    assert query["include_granted_scopes"] == ["true"] and query["state"] == ["state-1"]
    assert set(query["prompt"][0].split()) == {"consent", "select_account"}
    assert "login_hint" not in query
    plain = await workspace.agent_email_connect(_user())
    assert parse_qs(urlsplit(plain["auth_url"]).query)["scope"][0].split() == GMAIL_SCOPES


# No Anthropic key in tests (conftest), so the picker is the two Gemini rows.
_GEMINI_PICKER = {
    "chat_models": [{"id": "gemini-3.5-flash-lite", "locked": False}, {"id": "gemini-3.7-flash", "locked": False}],
    "default_chat_model": "gemini-3.7-flash",
}


@pytest.mark.asyncio
async def test_entitlements_say_what_the_workspace_has_switched_on(monkeypatch):
    from app.matcha.services.matcha_work.agent_runtime import enqueue, quota

    monkeypatch.setattr(entitlements_service, "resolve_plan_for_user", AsyncMock(return_value="pro"))
    monkeypatch.setattr(quota, "assistant_usage", AsyncMock(return_value={"limit": 30, "used": 2, "remaining": 28}))
    enabled = AsyncMock(return_value=True)
    monkeypatch.setattr(enqueue, "workspace_enabled", enabled)
    company = uuid4()
    out = await entitlements_service.resolve_entitlements(uuid4(), company)
    # The assistant's own menu rides along only when the workspace has it.
    assert out["workspace"] == {
        "espresso_assistant": True, "claude_models": False, **_GEMINI_PICKER,
        "assistant_models": [{"id": "gpt-5.6-luna", "label": "OpenAI Luna"}],
        "default_assistant_model": "gpt-5.6-luna",
    }
    assert out["features"]["assistant"] is True
    assert out["quotas"]["assistant_runs"] == {"limit": 30, "used": 2, "remaining": 28}
    enabled.assert_awaited_once_with(company)

    # No workspace, or a lookup that fails: off, and the read still answers.
    assert (await entitlements_service.resolve_entitlements(uuid4(), None))["workspace"] == {
        "espresso_assistant": False, "claude_models": False, **_GEMINI_PICKER}
    enabled.side_effect = RuntimeError("db down")
    assert (await entitlements_service.resolve_entitlements(uuid4(), company))["workspace"] == {
        "espresso_assistant": False, "claude_models": False, **_GEMINI_PICKER}

    # A menu that cannot be read leaves it out; the app falls back to no menu.
    from app.matcha.services.matcha_work.agent_runtime import models

    enabled.side_effect = None
    monkeypatch.setattr(models, "picker", AsyncMock(side_effect=RuntimeError("settings down")))
    workspace_out = (await entitlements_service.resolve_entitlements(uuid4(), company))["workspace"]
    assert workspace_out["espresso_assistant"] is True and "assistant_models" not in workspace_out


@pytest.mark.asyncio
async def test_conversations_are_paginated_and_owned_by_the_caller(wired):
    now = datetime.now(timezone.utc)
    wired.conn.on("SELECT id, name, updated_at FROM channels", [
        {"id": uuid4(), "name": f"Chat {i}", "updated_at": now} for i in range(51)])
    user = _user()
    out = await routes.list_conversations(offset=50, current_user=user)
    assert len(out["conversations"]) == 50 and out["has_more"]
    query = wired.conn.ran("SELECT id, name")[0]
    assert query[2] == (wired.company, user.id, 50)
    assert "assistant_user_id = $2" in query[1] and "channel_scope = 'assistant'" in query[1]
    assert "ORDER BY updated_at DESC, id DESC LIMIT 51" in query[1]
    wired.conn.on("SELECT id, name, updated_at FROM channels", [])
    assert await routes.list_conversations(offset=0, current_user=user) == {
        "conversations": [], "has_more": False}


@pytest.mark.asyncio
async def test_create_and_rename_preserve_company_and_owner_scope(wired, monkeypatch):
    from app.matcha.models.matcha_work.assistant import AssistantConversationRequest, AssistantConversationRename
    user, channel, key = _user(), uuid4(), uuid4()
    create = AsyncMock(return_value=channel)
    monkeypatch.setattr(conversation, "create_conversation", create)
    body = AssistantConversationRequest(title="  Café ☕  ", request_id=key)
    assert await routes.create_conversation(body, current_user=user) == {"channel_id": str(channel)}
    assert create.await_args.kwargs == dict(user_id=user.id, company_id=wired.company,
                                          title="Café ☕", request_id=key)
    now = datetime.now(timezone.utc)
    wired.conn.on("UPDATE channels SET name", {"id": channel, "name": "Mail", "updated_at": now})
    out = await routes.rename_conversation(channel, AssistantConversationRename(title="Mail"), current_user=user)
    assert out == {"id": str(channel), "title": "Mail", "updated_at": now.isoformat()}
    query = wired.conn.ran("UPDATE channels SET name")[0]
    assert query[2] == ("Mail", channel, wired.company, user.id)
    assert "company_id = $3 AND assistant_user_id = $4" in query[1]
    wired.conn.on("UPDATE channels SET name", None)
    with pytest.raises(HTTPException) as exc:
        await routes.rename_conversation(channel, AssistantConversationRename(title="Mail"), current_user=_user())
    assert exc.value.status_code == 404
    for request in (AssistantConversationRequest(title=" ", request_id=key),
                    AssistantConversationRename(title=" ")):
        with pytest.raises(HTTPException) as exc:
            if isinstance(request, AssistantConversationRequest):
                await routes.create_conversation(request, current_user=user)
            else:
                await routes.rename_conversation(channel, request, current_user=user)
        assert exc.value.status_code == 422


def test_conversation_and_mailbox_request_bounds():
    from app.matcha.models.matcha_work.assistant import (
        AssistantConversationRequest, AssistantConversationRename, EmailFetchRequest,
    )
    assert EmailFetchRequest().mailbox == "unread"
    for kwargs in ({"mailbox": "trash"}, {"page_token": ""}, {"page_token": "x" * 2049}):
        with pytest.raises(ValueError):
            EmailFetchRequest(**kwargs)
    with pytest.raises(ValueError):
        AssistantConversationRequest(title="x" * 101, request_id=uuid4())
    with pytest.raises(ValueError):
        AssistantConversationRename(title="")

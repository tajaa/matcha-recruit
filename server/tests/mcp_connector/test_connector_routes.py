"""REST side of the connector (consent, grants, research launch) and the MCP
tool wrapper's caller resolution."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException
from mcp.server.auth.provider import AccessToken
from mcp.server.mcpserver.exceptions import ToolError

from app.core.services import mcp_oauth
from app.matcha.routes.matcha_work import connectors
from app.matcha.routes.mcp_connector import research, server
from tests._helpers.routes import route_client

USER = SimpleNamespace(id=uuid.UUID("cccccccc-3333-4333-8333-333333333333"), role="client", email="u@example.com")
TASK = uuid.UUID("aaaaaaaa-1111-4111-8111-111111111111")
PROJECT = uuid.UUID("bbbbbbbb-2222-4222-8222-222222222222")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MCP_PUBLIC_ORIGIN", "https://matcha.test")
    with route_client(
        connectors.router, overrides={connectors.require_company_member: USER}
    ) as c:
        yield c


# ── grants ───────────────────────────────────────────────────────────────────


def test_list_connectors_reports_connected_kinds(client, monkeypatch):
    async def grants(user_id):
        assert user_id == USER.id
        return [{"client_id": "c1", "client_name": "Claude", "kind": "claude",
                 "connected_at": "2026-09-01T00:00:00+00:00", "last_used_at": None}]

    monkeypatch.setattr(mcp_oauth, "list_user_grants", grants)
    body = client.get("/connectors").json()
    assert body["mcp_url"] == "https://matcha.test/api/mcp"
    assert body["connected"] == {"claude": True, "chatgpt": False, "claude_code": False, "codex": False}
    assert body["claude_code_command"] == "claude mcp add --transport http matcha https://matcha.test/api/mcp"
    assert body["codex_commands"] == [
        "codex mcp add matcha --url https://matcha.test/api/mcp",
        "codex mcp login matcha",
    ]


def test_disconnect(client, monkeypatch):
    calls = []

    async def revoke(user_id, client_id):
        calls.append((user_id, client_id))
        return 2 if client_id == "c1" else 0

    monkeypatch.setattr(mcp_oauth, "revoke_client_grants", revoke)
    assert client.delete("/connectors/c1").json() == {"disconnected": True}
    assert client.delete("/connectors/nope").status_code == 404
    assert calls[0] == (USER.id, "c1")  # always the caller's own grants


# ── consent ──────────────────────────────────────────────────────────────────


def test_consent_describe_and_expired(client, monkeypatch):
    async def describe(handle):
        return None if handle == "old" else {
            "client_name": "ChatGPT", "client_kind": "chatgpt", "redirect_host": "chatgpt.com",
            "scopes": ["kanban:read"], "resource": "https://matcha.test/api/mcp",
        }

    monkeypatch.setattr(mcp_oauth, "describe_consent", describe)
    ok = client.get("/connectors/consent", params={"request": "h"}).json()
    assert ok == {"client_name": "ChatGPT", "client_kind": "chatgpt",
                  "redirect_host": "chatgpt.com", "scopes": ["kanban:read"]}
    assert client.get("/connectors/consent", params={"request": "old"}).status_code == 400


def test_consent_decision_binds_the_logged_in_user(client, monkeypatch):
    seen = {}

    async def approve(handle, user_id):
        seen["user"] = user_id
        return "https://claude.ai/api/mcp/auth_callback?code=x&state=s"

    monkeypatch.setattr(mcp_oauth, "approve_authorization", approve)
    monkeypatch.setattr(mcp_oauth, "deny_authorization", lambda h: None)
    resp = client.post("/connectors/consent", json={"request": "h", "approve": True})
    assert resp.json()["redirect_url"].startswith("https://claude.ai/")
    assert seen["user"] == USER.id
    assert client.post("/connectors/consent", json={"request": "h", "approve": False}).status_code == 400


# ── research launch ──────────────────────────────────────────────────────────


@pytest.fixture
def card(monkeypatch):
    state = {"card": {"id": TASK, "project_id": PROJECT, "title": "Which MacBook?"}, "error": None}

    async def authorized(user, task_id):
        if state["error"]:
            raise state["error"]
        return state["card"], {}, "owner"

    monkeypatch.setattr(research, "_authorized_card", authorized)
    return state


@pytest.mark.parametrize("kind, host", [("claude", "claude.ai"), ("chatgpt", "chatgpt.com")])
def test_launch_deep_links(client, card, kind, host):
    body = client.post(f"/projects/{PROJECT}/tasks/{TASK}/research-launch", json={"client": kind}).json()
    parsed = urlparse(body["url"])
    assert parsed.hostname == host
    assert parse_qs(parsed.query)["q"][0] == body["prompt"]
    assert str(TASK) in body["prompt"]


@pytest.mark.parametrize("kind, binary", [("claude_code", "claude"), ("codex", "codex")])
def test_launch_cli_returns_a_shell_command(client, card, kind, binary):
    body = client.post(f"/projects/{PROJECT}/tasks/{TASK}/research-launch", json={"client": kind}).json()
    assert body["url"] is None and body["command"].startswith(f"{binary} '")
    assert str(TASK) in body["command"]


def test_launch_refusals(client, card):
    card["card"] = {**card["card"], "project_id": uuid.uuid4()}
    assert client.post(f"/projects/{PROJECT}/tasks/{TASK}/research-launch", json={"client": "claude"}).status_code == 404
    card["error"] = research.ConnectorError("not a research card")
    assert client.post(f"/projects/{PROJECT}/tasks/{TASK}/research-launch", json={"client": "claude"}).status_code == 400
    assert client.post(f"/projects/{PROJECT}/tasks/{TASK}/research-launch", json={"client": "gemini"}).status_code == 422


# ── MCP tool caller resolution ───────────────────────────────────────────────


def _token(scopes=("kanban:read", "kanban:write")):
    return AccessToken(token="t", client_id="c1", scopes=list(scopes), subject=str(USER.id),
                       resource="https://matcha.test/api/mcp")


@pytest.fixture
def caller_env(monkeypatch):
    import app.core.dependencies as core_deps
    import app.core.services.redis_cache as redis_cache
    import app.matcha.dependencies as matcha_deps

    state = SimpleNamespace(token=_token(), rate_error=None, feature_error=None, revocation=None)
    monkeypatch.setattr(server, "get_access_token", lambda: state.token)

    async def rate(key, action, limit, window):
        if state.rate_error:
            raise state.rate_error

    async def load(user_id, **kw):
        state.revocation = kw.get("check_session_revocation")
        return USER

    def feature(name):
        async def check(user):
            if state.feature_error:
                raise state.feature_error
            return user
        return check

    async def client_name(client_id):
        return "Claude"

    monkeypatch.setattr(redis_cache, "check_rate_limit", rate)
    monkeypatch.setattr(core_deps, "load_current_user", load)
    monkeypatch.setattr(matcha_deps, "require_feature", feature)
    monkeypatch.setattr(server, "_client_name", client_name)
    return state


@pytest.mark.asyncio
async def test_caller_resolves_user_without_the_browser_session_watermark(caller_env):
    user, name = await server._caller(write=True)
    assert user is USER and name == "Claude"
    assert caller_env.revocation is False


@pytest.mark.asyncio
@pytest.mark.parametrize("setup, message", [
    (lambda s: setattr(s, "token", None), "Not signed in"),
    (lambda s: setattr(s, "token", _token(scopes=("kanban:read",))), "read-only"),
    (lambda s: setattr(s, "rate_error", HTTPException(status_code=429)), "Too many"),
    (lambda s: setattr(s, "feature_error", HTTPException(status_code=403, detail="off")), "off"),
])
async def test_caller_refusals_become_tool_errors(caller_env, setup, message):
    setup(caller_env)
    with pytest.raises(ToolError, match=message):
        await server._caller(write=True)


@pytest.mark.asyncio
async def test_run_passes_client_name_to_writes_and_maps_refusals(caller_env):
    seen = {}

    async def op(user, **kw):
        seen.update(kw)
        raise research.ConnectorError("nope")

    with pytest.raises(ToolError, match="nope"):
        await server._run("x", op, write=True, task_id="t")
    assert seen == {"task_id": "t", "client_name": "Claude"}


@pytest.mark.asyncio
async def test_tool_functions_delegate(caller_env, monkeypatch):
    calls = []

    def recorder(name):
        async def fn(user, **kw):
            calls.append((name, kw))
            return {"ok": name}
        return fn

    for name in ("list_research_cards", "get_research_card", "claim_research_card", "attach_research_report"):
        monkeypatch.setattr(research, name, recorder(name))
    await server.list_research_cards_tool(limit=3)
    await server.get_research_card_tool(task_id="t")
    await server.claim_research_card_tool(task_id="t")
    await server.attach_research_report_tool(task_id="t", report_markdown="r", card_note="n")
    assert [c[0] for c in calls] == [
        "list_research_cards", "get_research_card", "claim_research_card", "attach_research_report",
    ]
    assert calls[3][1] == {"task_id": "t", "report_markdown": "r", "card_note": "n", "client_name": "Claude"}

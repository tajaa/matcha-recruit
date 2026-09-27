"""First-party grants use existing tables; these tests never connect to a DB."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.services import mcp_local_tokens as tokens, mcp_oauth
from app.matcha.routes.matcha_work import connectors
from app.matcha.routes.mcp_connector import research
from tests._helpers.routes import route_client


@pytest.mark.asyncio
async def test_issue_is_transactional_hashed_short_lived_and_has_no_refresh(monkeypatch):
    calls = []
    state = {"transaction": False}

    class Connection:
        @asynccontextmanager
        async def transaction(self):
            state["transaction"] = True
            try:
                yield
            finally:
                state["transaction"] = False

        async def execute(self, sql, *args):
            assert state["transaction"]
            calls.append((sql, args))

    @asynccontextmanager
    async def connection():
        yield Connection()

    monkeypatch.setattr(tokens, "get_connection", connection)
    monkeypatch.setenv("MCP_PUBLIC_ORIGIN", "https://matcha.test")
    user = uuid4()
    before = datetime.now(timezone.utc)
    out = await tokens.issue_token(user)
    assert len(calls) == 2
    assert "ON CONFLICT (client_id) DO NOTHING" in calls[0][0]
    sql, args = calls[1]
    assert "'access'" in sql and "refresh" not in sql
    assert args[0] == mcp_oauth._hash(out["access_token"])
    assert out["access_token"].startswith("mat_at_")
    assert all(out["access_token"] not in str(call) for call in calls)
    assert args[1:4] == (out["grant_id"], tokens.CLIENT_ID, user)
    assert args[4] == "kanban:read kanban:write"
    assert out["resource"] == args[5] == "https://matcha.test/api/mcp"
    assert 1799 <= (out["expires_at"] - before).total_seconds() <= 1801
    assert "refresh_token" not in out


@pytest.mark.asyncio
async def test_revoke_is_user_run_and_client_scoped(monkeypatch):
    execute = AsyncMock()

    @asynccontextmanager
    async def connection():
        yield SimpleNamespace(execute=execute)

    monkeypatch.setattr(tokens, "get_connection", connection)
    user, grant = uuid4(), uuid4()
    await tokens.revoke_token(user, grant)
    sql, *args = execute.call_args.args
    assert "user_id = $1" in sql and "family_id = $2" in sql and "client_id = $3" in sql
    assert "revoked_at IS NULL" in sql
    assert args == [user, grant, tokens.CLIENT_ID]


@pytest.fixture
def local_api(monkeypatch):
    user = SimpleNamespace(id=uuid4(), role="client")
    project, task = uuid4(), uuid4()
    state = SimpleNamespace(card={"id": task, "project_id": project, "category": "research",
                                  "status": "pending", "board_column": "todo",
                                  "autopr_run_requested_at": None}, role="owner")

    async def authorized(caller, task_id):
        assert caller == user and task_id == task
        return state.card, {}, state.role

    result = {"access_token": "mat_at_test", "expires_at": datetime.now(timezone.utc),
              "resource": "https://matcha.test/api/mcp", "client_id": tokens.CLIENT_ID,
              "grant_id": uuid4()}
    issue = AsyncMock(return_value=result)
    revoke = AsyncMock()
    monkeypatch.setattr(research, "_authorized_card", authorized)
    monkeypatch.setattr(tokens, "issue_token", issue)
    monkeypatch.setattr(tokens, "revoke_token", revoke)
    with route_client(connectors.router, overrides={connectors.require_company_member: user}) as client:
        yield client, state, user, issue, revoke, {"project_id": str(project), "task_id": str(task)}


def test_local_route_mints_only_after_card_authorization(local_api):
    client, _, user, issue, _, body = local_api
    r = client.post("/connectors/local-token", json=body)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert r.json()["token_type"] == "Bearer"
    issue.assert_awaited_once_with(user.id)


@pytest.mark.parametrize("change,status", [
    ({"project_id": uuid4()}, 404),
    ({"board_column": "review"}, 409),
    ({"status": "cancelled"}, 409),
    ({"autopr_run_requested_at": datetime.now(timezone.utc)}, 409),
    ({"autopr_claimed_at": datetime.now(timezone.utc)}, 409),
])
def test_local_route_refuses_ineligible_card(local_api, change, status):
    client, state, _, issue, _, body = local_api
    state.card.update(change)
    assert client.post("/connectors/local-token", json=body).status_code == status
    issue.assert_not_called()


def test_local_route_refuses_viewer(local_api):
    client, state, _, issue, _, body = local_api
    state.role = "viewer"
    assert client.post("/connectors/local-token", json=body).status_code == 403
    issue.assert_not_called()


def test_local_route_preserves_access_errors(local_api, monkeypatch):
    client, _, _, issue, _, body = local_api
    monkeypatch.setattr(research, "_authorized_card", AsyncMock(side_effect=research.ConnectorError("hidden", 404)))
    assert client.post("/connectors/local-token", json=body).status_code == 404
    issue.assert_not_called()


def test_local_revoke_is_idempotent_and_caller_scoped(local_api):
    client, _, user, _, revoke, _ = local_api
    grant = uuid4()
    assert client.delete(f"/connectors/local-tokens/{grant}").status_code == 204
    revoke.assert_awaited_once_with(user.id, grant)


@pytest.mark.asyncio
async def test_grant_issued_at_is_caller_and_client_scoped(monkeypatch):
    issued = datetime.now(timezone.utc)
    fetchval = AsyncMock(return_value=issued)

    @asynccontextmanager
    async def connection():
        yield SimpleNamespace(fetchval=fetchval)

    monkeypatch.setattr(tokens, "get_connection", connection)
    user, grant = uuid4(), uuid4()
    assert await tokens.grant_issued_at(user, grant) == issued
    sql, *args = fetchval.call_args.args
    assert "user_id = $1 AND family_id = $2 AND client_id = $3" in sql
    assert "revoked_at" not in sql  # release still works after cleanup revoked it
    assert args == [user, grant, tokens.CLIENT_ID]


def test_local_release_hands_the_run_window_to_the_service(local_api, monkeypatch):
    client, _, user, _, _, body = local_api
    issued = datetime.now(timezone.utc)
    lookup = AsyncMock(return_value=issued)
    release = AsyncMock(return_value={"released": True, "column": "todo"})
    monkeypatch.setattr(tokens, "grant_issued_at", lookup)
    monkeypatch.setattr(research, "release_unfinished_claim", release)
    grant = uuid4()
    r = client.post(f"/connectors/local-tokens/{grant}/release", json=body)
    assert r.status_code == 200 and r.json() == {"released": True, "column": "todo", "reason": None}
    lookup.assert_awaited_once_with(user.id, grant)
    kwargs = release.await_args.kwargs
    assert kwargs["since"] == issued
    assert str(kwargs["project_id"]) == body["project_id"] and str(kwargs["task_id"]) == body["task_id"]


def test_local_release_refuses_an_unknown_run(local_api, monkeypatch):
    client, _, _, _, _, body = local_api
    release = AsyncMock()
    monkeypatch.setattr(tokens, "grant_issued_at", AsyncMock(return_value=None))
    monkeypatch.setattr(research, "release_unfinished_claim", release)
    assert client.post(f"/connectors/local-tokens/{uuid4()}/release", json=body).status_code == 404
    release.assert_not_called()


def test_local_release_maps_connector_errors(local_api, monkeypatch):
    client, _, _, _, _, body = local_api
    monkeypatch.setattr(tokens, "grant_issued_at", AsyncMock(return_value=datetime.now(timezone.utc)))
    monkeypatch.setattr(research, "release_unfinished_claim",
                        AsyncMock(side_effect=research.ConnectorError("no", 403)))
    assert client.post(f"/connectors/local-tokens/{uuid4()}/release", json=body).status_code == 403

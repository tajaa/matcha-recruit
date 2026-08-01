"""Tests for inbox.search_users scoping (app.werk.routes.inbox).

search_users' docstring promises: same-company users matchable by substring,
cross-company users only by exact email, admins keep the old global substring
search. The SQL previously had no company filter at all — any authenticated
user could substring-search every user in the system. These tests assert the
query actually enforces what the docstring claims, by inspecting the SQL text
and bound params captured on the mocked connection.
"""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ── Stub google.genai before importing app code ──
google_module = ModuleType("google")
genai_module = ModuleType("google.genai")
types_module = ModuleType("google.genai.types")
genai_module.Client = object
genai_module.types = types_module
types_module.Tool = lambda **kw: None
types_module.GoogleSearch = lambda **kw: None
types_module.GenerateContentConfig = lambda **kw: None
sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.genai", genai_module)
sys.modules.setdefault("google.genai.types", types_module)

MOD = "app.werk.routes.inbox"


def _conn_ctx(conn):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


def _user(role="client"):
    return SimpleNamespace(id=uuid4(), role=role)


@pytest.mark.asyncio
async def test_non_admin_search_scopes_to_company_and_exact_cross_tenant_email():
    from app.werk.routes.inbox import search_users

    user = _user(role="client")
    caller_company_id = uuid4()
    conn = AsyncMock()
    conn.fetchval.return_value = caller_company_id
    conn.fetch.return_value = []

    with patch(f"{MOD}.get_connection", _conn_ctx(conn)):
        result = await search_users(q="jane", current_user=user)

    assert result == []
    sql, *params = conn.fetch.await_args.args
    # Company-scoped substring branch present and gated on the caller's company
    assert "COALESCE(c.company_id, e.org_id) = $4" in sql
    # Exact-email cross-tenant branch present
    assert "lower(u.email) = lower($3)" in sql
    assert params == [user.id, "%jane%", "jane", caller_company_id]


@pytest.mark.asyncio
async def test_admin_search_keeps_global_substring_no_company_filter():
    from app.werk.routes.inbox import search_users

    user = _user(role="admin")
    conn = AsyncMock()
    conn.fetch.return_value = []

    with patch(f"{MOD}.get_connection", _conn_ctx(conn)):
        result = await search_users(q="jane", current_user=user)

    assert result == []
    sql, *params = conn.fetch.await_args.args
    # Company join for display purposes is fine; no WHERE-clause company gate
    assert "COALESCE(c.company_id, e.org_id) = $4" not in sql
    assert "lower(u.email) = lower($3)" not in sql
    assert params == [user.id, "%jane%"]
    # Admin path never resolves a caller company — no extra fetchval round-trip
    conn.fetchval.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_admin_with_no_company_still_matches_exact_email_only():
    """An individual/personal user (no company) can still find someone by
    exact email — the company-scoped substring branch is a no-op via the
    $4::uuid IS NOT NULL guard, not a crash or a wide-open match."""
    from app.werk.routes.inbox import search_users

    user = _user(role="individual")
    conn = AsyncMock()
    conn.fetchval.return_value = None  # no company
    conn.fetch.return_value = []

    with patch(f"{MOD}.get_connection", _conn_ctx(conn)):
        await search_users(q="jane@example.com", current_user=user)

    sql, *params = conn.fetch.await_args.args
    assert "$4::uuid IS NOT NULL" in sql
    assert params[-1] is None

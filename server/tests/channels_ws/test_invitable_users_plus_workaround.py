"""Regression test for the channels invitable-users + workaround.

The desktop client previously sent `q=user+tag@gmail.com` without
percent-encoding the `+`. Starlette decodes a raw `+` in a query string as
a space, so the server saw `q="user tag@gmail.com"` and the email-equality
clause failed. Personal users couldn't invite each other by email even
though both accounts existed and were active.

The fix has two layers:
1. The Mac client now encodes `+` as `%2B` (channels + matcha-work paths).
2. The server tolerates the old behavior: when the query contains a space
   AND looks like an email, it also tries the `+`-substituted form. This
   keeps older builds working while the new build rolls out.

This test pins layer 2.
"""

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

# Stub heavy optional deps before importing app code
for _name in ("google", "google.genai", "google.genai.types", "bleach",
              "audioop_lts", "audioop", "stripe"):
    if _name not in sys.modules:
        sys.modules[_name] = ModuleType(_name)
_genai = sys.modules["google.genai"]
_genai.Client = object
_genai.types = sys.modules["google.genai.types"]
_gt = sys.modules["google.genai.types"]
_gt.Tool = lambda **kw: None
_gt.GoogleSearch = lambda **kw: None
_gt.GenerateContentConfig = lambda **kw: None
_bleach = sys.modules["bleach"]
_bleach.clean = lambda text, **kw: text
_bleach.linkify = lambda text, **kw: text


class _CapturingConn:
    """Captures the final fetch() query + params so the test can assert
    which parameter values reached the SQL layer."""

    def __init__(self, *, profile_row: dict | None = None, fetch_rows: list | None = None):
        self.profile_row = profile_row or {"company_id": None, "is_personal": True}
        self.fetch_rows = fetch_rows or []
        self.fetch_query: str = ""
        self.fetch_params: tuple = ()

    async def fetchrow(self, query, *args):
        # Profile lookup for client/individual
        if "FROM clients c JOIN companies" in query:
            return self.profile_row
        return None

    async def fetchval(self, query, *args):
        return None

    async def fetch(self, query, *args):
        self.fetch_query = query
        self.fetch_params = args
        return self.fetch_rows


class _Ctx:
    def __init__(self, conn): self.conn = conn
    async def __aenter__(self): return self.conn
    async def __aexit__(self, *a): return False


def _make_user(role: str = "individual"):
    """Minimal CurrentUser-like object the route needs."""
    u = MagicMock()
    u.id = uuid4()
    u.role = role
    return u


@pytest.mark.asyncio
async def test_plus_substitution_when_query_has_space(monkeypatch):
    """Old client sends `q=user+tag@gmail.com`; Starlette decodes to
    `user tag@gmail.com`. Server must try the `+`-substituted form so
    the cross-tenant exact-email lookup can still match."""
    from app.core.routes import channels as channels_route

    conn = _CapturingConn()
    monkeypatch.setattr(channels_route, "get_connection", lambda: _Ctx(conn))

    user = _make_user("individual")
    await channels_route.search_invitable_users(
        q="tessu2022 mon@gmail.com",  # what server sees after Starlette's `+`→space decode
        channel_id=None,
        current_user=user,
    )

    # The fetch params should include BOTH email forms — original (with space)
    # AND substituted (with +). Old clients sending decoded-to-space queries
    # match the substituted form via Source 6 (exact LOWER(email)).
    param_strs = [str(p) for p in conn.fetch_params]
    assert any("tessu2022+mon@gmail.com" == p for p in param_strs), (
        f"expected `+`-substituted exact email in params, got {param_strs}"
    )


@pytest.mark.asyncio
async def test_correctly_encoded_query_still_matches(monkeypatch):
    """New client sends `q=user%2Btag@gmail.com` → Starlette decodes to the
    correct `user+tag@gmail.com`. No space, so the substitution path
    short-circuits — only the original exact-email clause fires."""
    from app.core.routes import channels as channels_route

    conn = _CapturingConn()
    monkeypatch.setattr(channels_route, "get_connection", lambda: _Ctx(conn))

    user = _make_user("individual")
    await channels_route.search_invitable_users(
        q="tessu2022+mon@gmail.com",
        channel_id=None,
        current_user=user,
    )

    param_strs = [str(p) for p in conn.fetch_params]
    # Original email present
    assert "tessu2022+mon@gmail.com" in param_strs
    # No need for a `+`-substituted form because there was no space to swap
    # (would have been the same string anyway).


@pytest.mark.asyncio
async def test_non_email_query_does_not_substitute(monkeypatch):
    """A bare name like `john smith` has a space but isn't an email. The
    `+`-substitution branch is gated by an email-shape check; it must not
    fire for plain names."""
    from app.core.routes import channels as channels_route

    conn = _CapturingConn()
    monkeypatch.setattr(channels_route, "get_connection", lambda: _Ctx(conn))

    user = _make_user("individual")
    await channels_route.search_invitable_users(
        q="john smith",
        channel_id=None,
        current_user=user,
    )

    # Should NOT contain "john+smith" exact-email param
    param_strs = [str(p) for p in conn.fetch_params]
    assert "john+smith" not in param_strs, (
        f"non-email query should not produce `+`-substituted exact-email param, got {param_strs}"
    )


@pytest.mark.asyncio
async def test_query_used_in_ilike_pattern_too(monkeypatch):
    """The `+`-substituted form must also be available to the ILIKE pattern
    (the AND-ed name filter), not only the exact-email OR-source. Otherwise
    the AND filter rejects the row before Source 6 can include it."""
    from app.core.routes import channels as channels_route

    conn = _CapturingConn()
    monkeypatch.setattr(channels_route, "get_connection", lambda: _Ctx(conn))

    user = _make_user("individual")
    await channels_route.search_invitable_users(
        q="tessu2022 mon@gmail.com",
        channel_id=None,
        current_user=user,
    )

    param_strs = [str(p) for p in conn.fetch_params]
    # ILIKE pattern wraps the query in % wildcards — both forms must appear.
    assert any("%tessu2022+mon@gmail.com%" == p for p in param_strs), (
        f"expected `+`-substituted ILIKE pattern in params, got {param_strs}"
    )

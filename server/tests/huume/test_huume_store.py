"""Regression test for the 500 on `GET .../huume/record`: asyncpg hands
`companies.enabled_features` back as a plain str (no jsonb codec is
registered anywhere in this app), and `get_thread_features_and_integrations`
used to wrap it in `dict(...)` directly — which iterates the JSON string's
characters and raises `ValueError: dictionary update sequence element #0 has
length 1; 2 is required`. Nothing exercised this function before the panel
route started calling it, which is exactly why the bug shipped silently.

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_store.py -q
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.matcha.services.huume.store import get_thread_features_and_integrations

MOD = "app.matcha.services.huume.store"


def _conn_ctx(conn):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


@pytest.mark.asyncio
async def test_str_enabled_features_does_not_raise(monkeypatch):
    conn = MagicMock()
    # This is what asyncpg actually returns for a jsonb column — a str, not
    # a dict. The old code's `dict(row["enabled_features"] or {})` blew up
    # on exactly this shape.
    conn.fetchrow = AsyncMock(return_value={"enabled_features": '{"huume": true}', "signup_source": "bespoke"})
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(f"{MOD}.get_connection", _conn_ctx(conn))

    features, integrations = await get_thread_features_and_integrations("company-1")

    assert features["huume"] is True
    assert integrations == {}


@pytest.mark.asyncio
async def test_no_company_row_defaults_cleanly(monkeypatch):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(f"{MOD}.get_connection", _conn_ctx(conn))

    features, integrations = await get_thread_features_and_integrations("company-1")

    assert features["huume"] is False
    assert integrations == {}


@pytest.mark.asyncio
async def test_dict_enabled_features_still_works(monkeypatch):
    # Belt-and-suspenders: if a caller ever passes a connection where a
    # codec DOES decode jsonb to a dict, the helper must not assume str.
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"enabled_features": {"huume": True}, "signup_source": None})
    conn.fetch = AsyncMock(return_value=[{"provider": "google_workspace"}])
    monkeypatch.setattr(f"{MOD}.get_connection", _conn_ctx(conn))

    features, integrations = await get_thread_features_and_integrations("company-1")

    assert features["huume"] is True
    assert integrations == {"google_workspace": True}

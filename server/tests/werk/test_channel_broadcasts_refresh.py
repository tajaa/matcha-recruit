"""Tests for refresh_broadcast_token's publish-rights check
(app.werk.routes.channel_broadcasts).

Previously `can_publish` required `identity == started_by` unconditionally,
so a guest promoted to publisher on-stage silently lost publish rights the
next time their token refreshed. It should instead check their LIVE grant.
"""

import sys
from datetime import datetime, timedelta, timezone
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

MOD = "app.werk.routes.channel_broadcasts"
LK = "app.core.services.livekit_service"


def _conn_ctx(conn):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


def _user(email="guest@example.com"):
    return SimpleNamespace(id=uuid4(), email=email)


def _broadcast_row(started_by, *, started_minutes_ago=2):
    return {
        "livekit_room": "channel-abc",
        "started_by": started_by,
        "started_at": datetime.now(timezone.utc) - timedelta(minutes=started_minutes_ago),
    }


@pytest.mark.asyncio
async def test_promoted_guest_keeps_publish_on_refresh():
    from app.werk.routes.channel_broadcasts import refresh_broadcast_token

    starter_id = uuid4()
    guest = _user()
    bc = _broadcast_row(starter_id)
    conn = AsyncMock()
    conn.fetchrow.return_value = bc

    with patch(f"{MOD}.get_connection", _conn_ctx(conn)), \
         patch(f"{MOD}._assert_member", AsyncMock()), \
         patch(f"{LK}._get_lk_config", return_value=("ws://t", "k", "s")), \
         patch(f"{LK}.list_publisher_identities", AsyncMock(return_value=[str(guest.id)])), \
         patch(f"{LK}.mint_token", return_value="jwt") as mt:
        resp = await refresh_broadcast_token(uuid4(), current_user=guest)

    assert resp["token"] == "jwt"
    assert mt.call_args.kwargs["can_publish"] is True


@pytest.mark.asyncio
async def test_non_promoted_member_gets_viewer_token():
    from app.werk.routes.channel_broadcasts import refresh_broadcast_token

    starter_id = uuid4()
    viewer = _user("viewer@example.com")
    bc = _broadcast_row(starter_id)
    conn = AsyncMock()
    conn.fetchrow.return_value = bc

    with patch(f"{MOD}.get_connection", _conn_ctx(conn)), \
         patch(f"{MOD}._assert_member", AsyncMock()), \
         patch(f"{LK}._get_lk_config", return_value=("ws://t", "k", "s")), \
         patch(f"{LK}.list_publisher_identities", AsyncMock(return_value=[str(starter_id)])), \
         patch(f"{LK}.mint_token", return_value="jwt") as mt:
        resp = await refresh_broadcast_token(uuid4(), current_user=viewer)

    assert resp["token"] == "jwt"
    assert mt.call_args.kwargs["can_publish"] is False


@pytest.mark.asyncio
async def test_starter_always_keeps_publish_even_if_livekit_lookup_fails():
    from app.werk.routes.channel_broadcasts import refresh_broadcast_token

    starter = _user("starter@example.com")
    bc = _broadcast_row(starter.id)
    conn = AsyncMock()
    conn.fetchrow.return_value = bc

    with patch(f"{MOD}.get_connection", _conn_ctx(conn)), \
         patch(f"{MOD}._assert_member", AsyncMock()), \
         patch(f"{LK}._get_lk_config", return_value=("ws://t", "k", "s")), \
         patch(f"{LK}.list_publisher_identities", AsyncMock(side_effect=Exception("livekit down"))), \
         patch(f"{LK}.mint_token", return_value="jwt") as mt:
        resp = await refresh_broadcast_token(uuid4(), current_user=starter)

    assert resp["token"] == "jwt"
    assert mt.call_args.kwargs["can_publish"] is True


@pytest.mark.asyncio
async def test_promoted_guest_falls_back_to_viewer_when_livekit_lookup_fails():
    """Conservative fallback: if we can't verify a non-starter's live grant,
    don't hand out publish rights we can't confirm."""
    from app.werk.routes.channel_broadcasts import refresh_broadcast_token

    starter_id = uuid4()
    guest = _user()
    bc = _broadcast_row(starter_id)
    conn = AsyncMock()
    conn.fetchrow.return_value = bc

    with patch(f"{MOD}.get_connection", _conn_ctx(conn)), \
         patch(f"{MOD}._assert_member", AsyncMock()), \
         patch(f"{LK}._get_lk_config", return_value=("ws://t", "k", "s")), \
         patch(f"{LK}.list_publisher_identities", AsyncMock(side_effect=Exception("livekit down"))), \
         patch(f"{LK}.mint_token", return_value="jwt") as mt:
        resp = await refresh_broadcast_token(uuid4(), current_user=guest)

    assert resp["token"] == "jwt"
    assert mt.call_args.kwargs["can_publish"] is False

"""Admin matcha-lite-pricing routes — missing-row fallback + upsert.

Covers the "Pricing config not found" bug: the add-on product codes
(addon_voice_intake / addon_hris_sync / addon_handbook_watch) are seeded by
migration mlpricing04, which may not have run in every environment yet. The
admin GET/PUT routes should treat a missing-but-valid product_code as "not
configured yet", not a 404 — GET falls back to launch defaults, PUT upserts.
"""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

# ── Stub heavyweight optional deps before importing app code — importing
# app.core.routes.matcha_lite_pricing_admin pulls in app.core.routes.__init__,
# which imports every other router (incl. Gemini-backed ones). ──
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
_gt.Content = lambda **kw: None
_gt.Part = type("Part", (), {"from_text": staticmethod(lambda **kw: None)})
_bleach = sys.modules["bleach"]
_bleach.clean = lambda text, **kw: text
_bleach.linkify = lambda text, **kw: text

from app.core.routes.matcha_lite_pricing_admin import (  # noqa: E402
    MatchaLitePricingUpdate,
    get_matcha_lite_pricing_admin,
    update_matcha_lite_pricing,
)

MOD = "app.core.routes.matcha_lite_pricing_admin"


def _conn_ctx(conn):
    txn = MagicMock()
    txn.__aenter__ = AsyncMock(return_value=None)
    txn.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=txn)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


def _user():
    return SimpleNamespace(id="admin-1", email="admin@example.com")


def _update_body(**overrides):
    defaults = dict(
        price_per_block_cents=100,
        block_size=1,
        sale_price_per_block_cents=None,
        sale_active=False,
        min_headcount=1,
        max_headcount=300,
    )
    defaults.update(overrides)
    return MatchaLitePricingUpdate(**defaults)


@pytest.mark.asyncio
async def test_get_falls_back_to_defaults_when_addon_row_missing(monkeypatch):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=None)  # no seed row for this env yet
    monkeypatch.setattr(f"{MOD}.get_connection", _conn_ctx(conn))

    result = await get_matcha_lite_pricing_admin(
        product_code="addon_voice_intake", current_user=_user()
    )

    assert result.price_per_block_cents == 100  # _FALLBACK_DEFAULTS placeholder
    assert result.block_size == 1
    assert result.updated_at is None
    assert result.updated_by is None


@pytest.mark.asyncio
async def test_get_unknown_product_code_still_400s(monkeypatch):
    conn = MagicMock()
    monkeypatch.setattr(f"{MOD}.get_connection", _conn_ctx(conn))

    with pytest.raises(HTTPException) as exc:
        await get_matcha_lite_pricing_admin(product_code="not_a_real_code", current_user=_user())
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_put_upserts_when_row_missing_instead_of_404(monkeypatch):
    conn = MagicMock()
    inserted_row = {
        "price_per_block_cents": 150,
        "block_size": 1,
        "sale_price_per_block_cents": None,
        "sale_active": False,
        "min_headcount": 1,
        "max_headcount": 300,
        "updated_at": None,
        "updated_by": "admin@example.com",
    }
    # First fetchrow (SELECT ... FOR UPDATE) finds nothing; second (the
    # INSERT ... ON CONFLICT ... RETURNING) returns the newly created row.
    conn.fetchrow = AsyncMock(side_effect=[None, inserted_row])
    conn.execute = AsyncMock()
    monkeypatch.setattr(f"{MOD}.get_connection", _conn_ctx(conn))

    result = await update_matcha_lite_pricing(
        _update_body(price_per_block_cents=150),
        product_code="addon_voice_intake",
        current_user=_user(),
    )

    assert result.price_per_block_cents == 150
    insert_sql = conn.fetchrow.call_args_list[1].args[0]
    assert "ON CONFLICT (product_code) DO UPDATE" in insert_sql

    # History row recorded with old_values = NULL (nothing existed before).
    history_args = conn.execute.call_args.args
    assert history_args[2] == "null"


@pytest.mark.asyncio
async def test_put_updates_existing_row(monkeypatch):
    conn = MagicMock()
    old_row = {
        "price_per_block_cents": 100,
        "block_size": 1,
        "sale_price_per_block_cents": None,
        "sale_active": False,
        "min_headcount": 1,
        "max_headcount": 300,
    }
    new_row = {**old_row, "price_per_block_cents": 200, "updated_at": None, "updated_by": "admin@example.com"}
    conn.fetchrow = AsyncMock(side_effect=[old_row, new_row])
    conn.execute = AsyncMock()
    monkeypatch.setattr(f"{MOD}.get_connection", _conn_ctx(conn))

    result = await update_matcha_lite_pricing(
        _update_body(price_per_block_cents=200),
        product_code="addon_voice_intake",
        current_user=_user(),
    )

    assert result.price_per_block_cents == 200
    history_args = conn.execute.call_args.args
    assert history_args[2] != "null"


@pytest.mark.asyncio
async def test_put_rejects_min_greater_than_max(monkeypatch):
    conn = MagicMock()
    monkeypatch.setattr(f"{MOD}.get_connection", _conn_ctx(conn))

    with pytest.raises(HTTPException) as exc:
        await update_matcha_lite_pricing(
            _update_body(min_headcount=50, max_headcount=10),
            product_code="matcha_lite",
            current_user=_user(),
        )
    assert exc.value.status_code == 400

"""Werk plan entitlements — resolver matrix, feature maps, gates, model clamp.

Pure unit tests (no DB): the resolver's row→plan mapping is exercised via
`_plan_from_row`, the plan gate via a patched `resolve_plan_for_user`, and the
model clamp via patched plan resolution + platform mode.
"""

import sys
from types import ModuleType
from unittest.mock import AsyncMock, patch

import pytest

# ── Stub heavyweight optional deps before importing app code ──
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

from app.matcha.services import entitlements_service as ent  # noqa: E402
from app.matcha.services.entitlements_service import (  # noqa: E402
    PLAN_BUSINESS,
    PLAN_FREE,
    PLAN_LITE,
    PLAN_PRO,
    PLAN_QUOTAS,
    _plan_from_row,
    features_for_plan,
    plan_at_least,
)


def _row(
    role="individual",
    beta=None,
    is_personal=True,
    enabled=None,
    pack=None,
):
    return {
        "role": role,
        "beta_features": beta or {},
        "company_id": "c-1",
        "is_personal": is_personal,
        "enabled_features": enabled or {},
        "sub_pack_id": pack,
    }


# ============================================================
# Resolver matrix — _plan_from_row
# ============================================================

class TestPlanFromRow:
    def test_missing_user_row_is_free(self):
        assert _plan_from_row(None) == PLAN_FREE

    def test_admin_is_pro(self):
        assert _plan_from_row(_row(role="admin")) == PLAN_PRO

    def test_business_client_with_matcha_work(self):
        row = _row(role="client", is_personal=False, enabled={"matcha_work": True})
        assert _plan_from_row(row) == PLAN_BUSINESS

    def test_client_without_matcha_work_flag_is_free(self):
        row = _row(role="client", is_personal=False, enabled={})
        assert _plan_from_row(row) == PLAN_FREE

    def test_client_on_personal_company_not_business(self):
        # Personal Werk workspaces share signup machinery with companies;
        # is_personal=true must never resolve to the business plan.
        row = _row(role="client", is_personal=True, enabled={"matcha_work": True})
        assert _plan_from_row(row) == PLAN_FREE

    def test_individual_with_matcha_work_flag_not_business(self):
        row = _row(role="individual", is_personal=True, enabled={"matcha_work": True})
        assert _plan_from_row(row) == PLAN_FREE

    def test_pro_pack_grandfathers_to_pro(self):
        assert _plan_from_row(_row(pack=ent.PRO_PACK_ID)) == PLAN_PRO

    def test_lite_pack_is_lite(self):
        assert _plan_from_row(_row(pack=ent.LITE_PACK_ID)) == PLAN_LITE

    def test_beta_full_maps_to_pro(self):
        row = _row(beta={"matcha_work_beta_full": True})
        assert _plan_from_row(row) == PLAN_PRO

    def test_beta_lite_maps_to_lite(self):
        row = _row(beta={"matcha_work_beta_lite": True})
        assert _plan_from_row(row) == PLAN_LITE

    def test_beta_full_outranks_lite_pack(self):
        row = _row(beta={"matcha_work_beta_full": True}, pack=ent.LITE_PACK_ID)
        assert _plan_from_row(row) == PLAN_PRO

    def test_pro_pack_outranks_beta_lite(self):
        row = _row(beta={"matcha_work_beta_lite": True}, pack=ent.PRO_PACK_ID)
        assert _plan_from_row(row) == PLAN_PRO

    def test_jsonb_as_string_is_parsed(self):
        row = _row()
        row["beta_features"] = '{"matcha_work_beta_full": true}'
        assert _plan_from_row(row) == PLAN_PRO

    def test_malformed_jsonb_string_is_ignored(self):
        row = _row()
        row["beta_features"] = "not-json"
        assert _plan_from_row(row) == PLAN_FREE

    def test_default_individual_is_free(self):
        assert _plan_from_row(_row()) == PLAN_FREE


# ============================================================
# Plan ordering + quotas
# ============================================================

class TestPlanOrderingAndQuotas:
    def test_ordering(self):
        assert plan_at_least(PLAN_PRO, PLAN_LITE)
        assert plan_at_least(PLAN_BUSINESS, PLAN_PRO)
        assert plan_at_least(PLAN_LITE, PLAN_LITE)
        assert not plan_at_least(PLAN_FREE, PLAN_LITE)
        assert not plan_at_least(PLAN_LITE, PLAN_PRO)

    def test_quota_ladder_monotonic(self):
        free, lite, pro = (PLAN_QUOTAS[p][0] for p in (PLAN_FREE, PLAN_LITE, PLAN_PRO))
        assert free < lite < pro
        assert PLAN_QUOTAS[PLAN_BUSINESS][0] == PLAN_QUOTAS[PLAN_PRO][0]

    def test_every_plan_has_quota(self):
        for plan in (PLAN_FREE, PLAN_LITE, PLAN_PRO, PLAN_BUSINESS):
            limit, hours = PLAN_QUOTAS[plan]
            assert limit > 0 and hours > 0


# ============================================================
# Feature map
# ============================================================

class TestFeatureMap:
    def test_free(self):
        f = features_for_plan(PLAN_FREE)
        assert f["threads_ai"] and f["journals_basic"]
        assert not f["projects_solo"] and not f["projects_collab"]
        assert not f["journals_full"] and not f["email_ai"]
        assert not f["go_live"] and not f["paid_channels"]

    def test_lite(self):
        f = features_for_plan(PLAN_LITE)
        assert f["projects_solo"] and f["journals_full"] and f["email_ai"]
        assert not f["projects_collab"] and not f["go_live"]
        assert not f["ai_model_pro"] and not f["paid_channels"]

    def test_pro(self):
        f = features_for_plan(PLAN_PRO)
        assert f["ai_model_pro"] and f["projects_collab"] and f["go_live"]
        assert f["paid_channels"]
        assert not f["business_modes"]

    def test_business(self):
        f = features_for_plan(PLAN_BUSINESS)
        assert f["ai_model_pro"] and f["projects_collab"] and f["go_live"]
        assert f["business_modes"]
        # Paid channels are an individual-account product rule.
        assert not f["paid_channels"]


# ============================================================
# require_plan gate — structured 403
# ============================================================

class TestRequirePlan:
    @pytest.mark.asyncio
    async def test_blocked_raises_structured_403(self):
        from fastapi import HTTPException

        with patch.object(ent, "resolve_plan_for_user", AsyncMock(return_value=PLAN_FREE)):
            with pytest.raises(HTTPException) as exc:
                await ent.require_plan("u-1", PLAN_LITE, "projects_solo")
        assert exc.value.status_code == 403
        detail = exc.value.detail
        assert detail["code"] == "plan_required"
        assert detail["required_plan"] == PLAN_LITE
        assert detail["current_plan"] == PLAN_FREE
        assert detail["feature"] == "projects_solo"

    @pytest.mark.asyncio
    async def test_business_passes_pro_gate(self):
        with patch.object(ent, "resolve_plan_for_user", AsyncMock(return_value=PLAN_BUSINESS)):
            assert await ent.require_plan("u-1", PLAN_PRO, "go_live") == PLAN_BUSINESS

    @pytest.mark.asyncio
    async def test_exact_plan_passes(self):
        with patch.object(ent, "resolve_plan_for_user", AsyncMock(return_value=PLAN_LITE)):
            assert await ent.require_plan("u-1", PLAN_LITE, "email_ai") == PLAN_LITE


# ============================================================
# Model clamp — _get_model
# ============================================================

class _Settings:
    analysis_model = "gemini-3.1-flash-lite"


class TestModelClamp:
    def _patches(self, plan, mode="normal"):
        return (
            patch.object(ent, "resolve_plan_for_user", AsyncMock(return_value=plan)),
            patch(
                "app.matcha.services.matcha_work_ai.get_matcha_work_model_mode",
                AsyncMock(return_value=mode),
            ),
        )

    @pytest.mark.asyncio
    async def test_free_cannot_force_pro_override(self):
        from app.matcha.services.matcha_work_ai import _get_model, PRO_MODEL

        p1, p2 = self._patches(PLAN_FREE)
        with p1, p2:
            model = await _get_model(_Settings(), model_override=PRO_MODEL, user_id="u-1")
        assert model == _Settings.analysis_model

    @pytest.mark.asyncio
    async def test_pro_plan_override_honored(self):
        from app.matcha.services.matcha_work_ai import _get_model, PRO_MODEL

        p1, p2 = self._patches(PLAN_PRO)
        with p1, p2:
            model = await _get_model(_Settings(), model_override=PRO_MODEL, user_id="u-1")
        assert model == PRO_MODEL

    @pytest.mark.asyncio
    async def test_lite_override_to_flash_is_fine(self):
        from app.matcha.services.matcha_work_ai import _get_model

        p1, p2 = self._patches(PLAN_LITE)
        with p1, p2:
            model = await _get_model(
                _Settings(), model_override="gemini-3-flash-preview", user_id="u-1"
            )
        assert model == "gemini-3-flash-preview"

    @pytest.mark.asyncio
    async def test_business_defaults_to_pro_model(self):
        from app.matcha.services.matcha_work_ai import _get_model, PRO_MODEL

        p1, p2 = self._patches(PLAN_BUSINESS)
        with p1, p2:
            model = await _get_model(_Settings(), user_id="u-1")
        assert model == PRO_MODEL

    @pytest.mark.asyncio
    async def test_heavy_mode_forces_pro_for_all(self):
        from app.matcha.services.matcha_work_ai import _get_model, PRO_MODEL

        p1, p2 = self._patches(PLAN_FREE, mode="heavy")
        with p1, p2:
            model = await _get_model(_Settings(), user_id="u-1")
        assert model == PRO_MODEL

    @pytest.mark.asyncio
    async def test_free_default_is_analysis_model(self):
        from app.matcha.services.matcha_work_ai import _get_model

        p1, p2 = self._patches(PLAN_FREE)
        with p1, p2:
            model = await _get_model(_Settings(), user_id="u-1")
        assert model == _Settings.analysis_model


# ============================================================
# Personal plan SKU table (stripe_service)
# ============================================================

class TestPersonalPlanTable:
    def test_plan_table_shape(self):
        from app.core.services.stripe_service import StripeService

        plans = StripeService.PERSONAL_PLANS
        assert plans["lite"]["pack_id"] == ent.LITE_PACK_ID
        assert plans["lite"]["amount_cents"] == ent.LITE_AMOUNT_CENTS
        assert plans["pro"]["pack_id"] == ent.PRO_PACK_ID
        assert plans["pro"]["amount_cents"] == ent.PRO_AMOUNT_CENTS

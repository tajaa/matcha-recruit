"""Matcha-work thread harness model tiering: alias normalization, the
two-model fleet, and the flash-lite gate that keeps skill threads off it.

    cd server && ./venv/bin/python -m pytest tests/matcha_work/test_model_selection.py -q
"""
from unittest.mock import AsyncMock

import pytest
from google.genai import types

from app.matcha.services.matcha_work.matcha_work_ai import (
    FLASH, FLASH_LITE, PRO_MODEL, SUPPORTED_MODELS, _MODEL_ALIASES,
    _get_model, classify_thinking_level, resolve_turn_model,
)
from app.matcha.services.matcha_work.matcha_work_ai import _models


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    # _get_model's "no override" path hits platform_settings.get_matcha_work_model_mode
    # (a real DB call) before falling through to the plan-entitlement check
    # (also a real DB call absent user/company_id, which these tests never
    # pass) — stub the mode lookup so _get_model is exercised DB-free.
    monkeypatch.setattr(_models, "get_matcha_work_model_mode", AsyncMock(return_value="normal"))


class TestModelFleet:
    def test_two_models_supported(self):
        assert SUPPORTED_MODELS == {FLASH_LITE, FLASH}

    def test_pro_preview_retired(self):
        # Product decision 2026-07-31: matcha-work's paid tier now runs the
        # same flash model as everyone else.
        assert PRO_MODEL == FLASH

    def test_old_picker_ids_alias_to_new_fleet(self):
        assert _MODEL_ALIASES["gemini-3-flash-preview"] == FLASH
        assert _MODEL_ALIASES["gemini-3.1-flash-lite"] == FLASH_LITE
        assert _MODEL_ALIASES["gemini-3.1-pro-preview"] == FLASH


class TestGetModel:
    @pytest.mark.asyncio
    async def test_stale_client_override_normalizes_to_new_fleet(self):
        settings = type("S", (), {"analysis_model": "unused"})()
        for old_id, expected in _MODEL_ALIASES.items():
            resolved = await _get_model(settings, model_override=old_id)
            assert resolved == expected

    @pytest.mark.asyncio
    async def test_unrecognized_override_falls_through_to_plan_selection(self):
        settings = type("S", (), {"analysis_model": "unused"})()
        resolved = await _get_model(settings, model_override="not-a-real-model")
        assert resolved == FLASH  # base fallback, no entitlement resolvers to hit

    @pytest.mark.asyncio
    async def test_no_override_no_entitlement_is_flash(self):
        settings = type("S", (), {"analysis_model": "unused"})()
        resolved = await _get_model(settings)
        assert resolved == FLASH


class TestResolveTurnModel:
    def test_trivial_skill_less_turn_downgrades_to_flash_lite(self):
        assert resolve_turn_model("none", "chat", FLASH) == FLASH_LITE

    def test_trivial_turn_inside_a_skill_thread_stays_on_plan_model(self):
        # The trap: classify_thinking_level's trivial-phrase set fires before
        # its skill check, so "ok" inside an offer_letter thread still comes
        # back thinking_level="none" — but "ok" there can mean "send it".
        assert resolve_turn_model("none", "offer_letter", FLASH) == FLASH
        assert resolve_turn_model("none", "hr_pilot", FLASH) == FLASH

    def test_non_trivial_thinking_never_downgrades(self):
        assert resolve_turn_model("low", "chat", FLASH) == FLASH
        assert resolve_turn_model("high", "chat", FLASH) == FLASH

    def test_plan_model_passed_through_unchanged_when_not_downgraded(self):
        # Whatever _get_model resolved (including a future distinct pro
        # model) survives untouched outside the flash-lite gate.
        assert resolve_turn_model("high", "offer_letter", "some-future-model") == "some-future-model"


class TestSkillThreadsNeverClassifyAsChat:
    """Companion pin to the resolve_turn_model trap test: every skill in
    classify_thinking_level's high-thinking set is confirmed to still report
    thinking_level="none" on a trivial-shaped message, so resolve_turn_model's
    skill check is the only thing keeping it off flash-lite."""

    @pytest.mark.parametrize("skill", [
        "offer_letter", "review", "workbook", "handbook", "policy",
        "presentation", "project", "onboarding",
    ])
    def test_trivial_message_in_skill_thread_still_classifies_none(self, skill):
        level = classify_thinking_level(
            "ok", skill, compliance_mode=False, payer_mode=False, node_mode=False,
        )
        assert level == "none"
        # ...which is exactly why resolve_turn_model must check skill too.
        assert resolve_turn_model(level, skill, FLASH) == FLASH


class TestThinkingConfigOnFlashLite:
    def test_minimal_level_not_budget_zero(self):
        # Mirrors the Huume/Merlin pin: 3.x drops thinking_budget, and
        # budget=0 is a hard 400 on flash-lite. thinking_level="minimal" is
        # the thinking-off equivalent that actually works on it.
        cfg = types.ThinkingConfig(thinking_level="minimal")
        assert cfg.thinking_level == "MINIMAL"
        assert cfg.thinking_budget is None


class TestThinkingConfigNeverUsesBudget:
    def test_call_gemini_source_has_no_thinking_budget(self):
        # thinking_budget is a 2.5-era field; 0 is a hard 400 on BOTH fleet
        # models (probed live 2026-08-01). The retired gemini-3-flash-preview
        # tolerated it, which is how a budget=0 branch survived until the
        # fleet bump — this pins the whole method against reintroducing one,
        # not just the flash-lite-only branch that regressed once already.
        import inspect
        from app.matcha.services.matcha_work.matcha_work_ai import provider
        # Substring on the constructor call, not the bare word — the method's
        # own comments legitimately mention "thinking_budget" as the field
        # never to use.
        assert "thinking_budget=" not in inspect.getsource(provider.GeminiProvider._call_gemini)

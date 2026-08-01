"""Model-catalog single-source-of-truth pins.

    cd server && ./venv/bin/python -m pytest tests/test_model_catalog.py -q

Every service constant must alias the catalog (a re-literaled id drifts on
the next fleet bump), and every catalog model must be priced identically in
BOTH billing ledgers (an absent row falls to DEFAULT_PRICING / cost_usd=NULL).
"""
from decimal import Decimal

from app.core.services.model_catalog import GEMINI_FLASH, GEMINI_FLASH_LITE


class TestSingleSourceOfTruth:
    def test_huume_routing_aliases_catalog(self):
        from app.matcha.services.huume import routing
        assert routing.FLASH == GEMINI_FLASH
        assert routing.FLASH_LITE == GEMINI_FLASH_LITE

    def test_matcha_work_models_alias_catalog(self):
        from app.matcha.services.matcha_work.matcha_work_ai import _models
        assert _models.FLASH == GEMINI_FLASH
        assert _models.FLASH_LITE == GEMINI_FLASH_LITE
        assert _models.PRO_MODEL == GEMINI_FLASH  # pro-preview retired 2026-07-31

    def test_ems_intake_aliases_catalog(self):
        from app.matcha.services.ems import event_intake
        assert event_intake.FLASH_LITE_MODEL == GEMINI_FLASH_LITE

    def test_compaction_aliases_catalog(self):
        from app.matcha.services.matcha_work.matcha_work_ai import compaction
        assert compaction.COMPACTION_MODEL == GEMINI_FLASH


class TestPricingParity:
    def test_both_ledgers_price_every_catalog_model_identically(self):
        from app.core.services.ai_usage import PRICING
        from app.matcha.services.billing.model_pricing import DEFAULT_PRICING, MODEL_PRICING
        for model in (GEMINI_FLASH, GEMINI_FLASH_LITE):
            assert model in MODEL_PRICING, f"{model} missing from MODEL_PRICING"
            assert MODEL_PRICING[model] != DEFAULT_PRICING
            inp, outp = PRICING[("gemini", model)]
            assert MODEL_PRICING[model]["input_per_1m"] == Decimal(str(inp))
            assert MODEL_PRICING[model]["output_per_1m"] == Decimal(str(outp))

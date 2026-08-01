"""The two-model Gemini fleet — single source of truth for model ids.

Every service that hardcoded "gemini-3.5-flash-lite" / "gemini-3.6-flash"
now assigns from here, so the next fleet bump is: (1) edit these two
constants, (2) add pricing rows for the new ids in BOTH
`matcha/services/billing/model_pricing.MODEL_PRICING` and
`core/services/ai_usage.PRICING` (those tables stay literal-keyed on
purpose — they must also price retired ids still present on historical
usage rows). tests/test_model_catalog.py enforces the pricing half.

Cappe's Merlin (`cappe/services/merlin/catalog.py`) deliberately does NOT
import this — separate product, its literals carry their own pricing-history
comments.
"""

# Quality tier — agent loops, skill/document turns, compaction, classification
# where the output is the product.
GEMINI_FLASH = "gemini-3.6-flash"

# Cheap tier — confirm turns, trivial chat acks, one-shot titles/summaries/
# extractions. NOTE: the 3.x generation dropped `thinking_budget`; passing
# thinking_budget=0 is a hard 400 INVALID_ARGUMENT on this model — use
# ThinkingConfig(thinking_level="minimal") to turn thinking off.
GEMINI_FLASH_LITE = "gemini-3.5-flash-lite"

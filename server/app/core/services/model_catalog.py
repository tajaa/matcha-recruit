"""The two-model Gemini FLEET — single source of truth for the fleet's ids.

Fleet = the pair of models the interactive product surfaces run on (Huume
agent loop, matcha-work threads, EMS channel intake/ask, the one-shot
title/summary/draft/scan/resume services, compliance pilot, compaction,
handbook relevance). A fleet bump is: (1) edit these two constants,
(2) add pricing rows for the new ids in BOTH
`matcha/services/billing/model_pricing.MODEL_PRICING` and
`core/services/ai_usage.PRICING` (literal-keyed on purpose — they must also
price retired ids still on historical usage rows).
tests/test_model_catalog.py enforces both halves (value aliasing + a
no-re-literaled-fleet-ids sweep + pricing parity).

Deliberately NOT migrated here (each is its own product decision, not a
drift accident):
- `gemini-3.1-flash-lite` legacy call sites (recruiting, thread_uploads,
  impact_summary, grounding_verifier, gemini_compliance light model) — a
  silent bump to 3.5-flash-lite would ~3x their cost.
- `gemini-3.1-pro-preview` in the ER deep-analysis paths (er_analysis,
  er_case_context `model_override == "pro"`).
- The image models (image_gen, pdf.py) and the Live/analysis models in
  config.py (env-overridable settings, different lifecycle).
- Cappe's Merlin catalog (separate product, own pricing-history comments).
"""

# Quality tier — agent loops, skill/document turns, compaction, classification
# where the output is the product.
GEMINI_FLASH = "gemini-3.6-flash"

# Cheap tier — confirm turns, trivial chat acks, one-shot titles/summaries/
# extractions. CANONICAL NOTE (other modules point here rather than
# re-stating this): the 3.x generation dropped `thinking_budget`;
# thinking_budget=0 is a hard 400 INVALID_ARGUMENT on BOTH fleet models
# (probed live 2026-08-01 — the retired gemini-3-flash-preview tolerated it,
# which is how a budget=0 code path survived until this fleet bump).
# Thinking-off is ThinkingConfig(thinking_level="minimal"), never a budget.
GEMINI_FLASH_LITE = "gemini-3.5-flash-lite"

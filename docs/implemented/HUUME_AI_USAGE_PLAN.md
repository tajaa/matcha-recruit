# Huume spend tracking in /admin/ai-usage (technical plan)

> **Status (verified 2026-07-26): IMPLEMENTED — shipped in `71ee40b`.** All 4 changes
> confirmed at their named lines: `feature_scope` wraps (`legal_skill.py:220`,
> `handbook_skill.py:171`), `_accumulate_usage` (`agent.py:124,753`), `gemini-3.6-flash`
> pricing (`model_pricing.py:27-30`), `HUUME_FEATURE_PREFIX` rollup (`AiUsage.tsx:471-503`);
> `tests/huume/test_usage_accounting.py` matches. One deliberate deviation: Edit B's
> `generate_packet` scope wrap was skipped because `build_defense_packet` makes no Gemini
> calls — rationale preserved as a code comment at `legal_skill.py:296`. Kept for history.

## Context

Ask: make sure `/admin/ai-usage` tracks Huume spend — calls, thinking, context/cached tokens.

Base already works: `get_genai_client()` (`server/app/core/services/genai_client.py:37,42`) wraps
every client via `ai_usage.wrap_client`, recording **every** Gemini call to `ai_usage_log`
(input/output/thinking/cached tokens + cost + latency), and Huume's loop already labels its calls
`feature_scope("matcha.huume.loop")` at `server/app/matcha/services/huume/agent.py:606`. The admin
by-feature rollup (with its Thinking column) already shows that row.

Four gaps to close:

| # | Gap | Where |
|---|---|---|
| 1 | Pilot tools invoked FROM huume log under `matcha.legal_defense` / `matcha.handbook_pilot` — indistinguishable from the standalone pilot UIs; huume-attributed spend understates | `huume/legal_skill.py`, `huume/handbook_skill.py` |
| 2 | `agent.py` accumulate discards `thoughts_token_count`/`cached_content_token_count` → `huume_runs.token_usage` + billing event understate; `prompt+completion != total` in blob | `agent.py:223,614-618` |
| 3 | Billing prices huume's model at DEFAULT (0.50/3.00) — `MODEL_PRICING` has no `gemini-3.6-flash` while admin ledger `ai_usage.PRICING:53` has (1.50, 7.50) → every huume turn ~3x undercounted in `mw_token_usage_events`; thinking never billed | `billing/model_pricing.py`, `messaging.py:_record_turn_usage` |
| 4 | No huume rollup block on the admin page (spend scattered across 3 labels) | `client/src/pages/admin/AiUsage.tsx` |

Two ledgers stay separate by design: `ai_usage_log` (admin, per-call, no company_id) vs
`mw_token_usage_events` (per-company billing, per-turn).

---

## Change 1 — label embedded pilot calls as huume sub-features

`feature_scope(label)` (`app/core/services/ai_usage.py:81`) is a ContextVar contextmanager —
async-safe, survives `asyncio.to_thread`, covers the entire awaited call tree. Precedent for
per-sub-surface agent labels: `cappe.merlin_agent.loop.{tier}` + `cappe.merlin_agent.image`
(`merlin_agent.py:750,677`). Adds exactly 2 permanent labels.

### `server/app/matcha/services/huume/legal_skill.py`

Add import (module has plain top imports at l.17-23):
```python
from app.core.services.ai_usage import feature_scope
```

**Edit A — `ask_matter` (l.215).** Current:
```python
    result: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    async for ev in ld.run_chat_turn(matter, history, corpus, question):
        if ev.get("type") == "result":
            result = ev.get("data")
        elif ev.get("type") == "error":
            error_message = ev.get("message")
```
New:
```python
    result: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    # Attribute the pilot's Gemini call to huume in the admin AI ledger —
    # without this it lands under the stack-derived `matcha.legal_defense`,
    # indistinguishable from the standalone /app/legal-pilot UI.
    with feature_scope("matcha.huume.legal_pilot"):
        async for ev in ld.run_chat_turn(matter, history, corpus, question):
            if ev.get("type") == "result":
                result = ev.get("data")
            elif ev.get("type") == "error":
                error_message = ev.get("message")
```

**Edit B — `generate_packet` (l.290).** Current:
```python
        packet = await ld.build_defense_packet(
            conn, matter, corpus, memo, company_name=company["name"] if company else None,
        )
```
New:
```python
        with feature_scope("matcha.huume.legal_pilot"):
            packet = await ld.build_defense_packet(
                conn, matter, corpus, memo, company_name=company["name"] if company else None,
            )
```

### `server/app/matcha/services/huume/handbook_skill.py`

Same import. **Edit C — `draft_content` (l.166).** Current:
```python
    result: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    async for ev in hp.run_chat_turn(session, history, corpus, request_text):
        if ev.get("type") == "result":
            result = ev.get("data")
        elif ev.get("type") == "error":
            error_message = ev.get("message")
```
New: identical wrap with `feature_scope("matcha.huume.handbook_pilot")` (same comment pattern).
`promote()` makes no Gemini calls — untouched.

---

## Change 2 — capture thinking/cached in `agent.py`

### `server/app/matcha/services/huume/agent.py`

**Edit A — l.223.** Current:
```python
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
```
New:
```python
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                   "thinking_tokens": 0, "cached_tokens": 0}
```

**Edit B — replace the inline accumulate (l.614-618) with a module-level pure helper** (testable,
same style as `_cap_payload`):

New helper near `_cap_payload`:
```python
def _accumulate_usage(total: dict[str, int], usage: Any) -> None:
    """Fold one response's usage_metadata into the turn total. thoughts/cached
    were silently dropped before 2026-07 — total_token_count includes thoughts,
    so without them prompt+completion never equalled total in the stored blob."""
    for key, attr in (
        ("prompt_tokens", "prompt_token_count"),
        ("completion_tokens", "candidates_token_count"),
        ("total_tokens", "total_token_count"),
        ("thinking_tokens", "thoughts_token_count"),
        ("cached_tokens", "cached_content_token_count"),
    ):
        total[key] = total.get(key, 0) + (getattr(usage, attr, 0) or 0)
```

Call site — current:
```python
            usage = getattr(response, "usage_metadata", None)
            if usage:
                total_usage["prompt_tokens"] += getattr(usage, "prompt_token_count", 0) or 0
                total_usage["completion_tokens"] += getattr(usage, "candidates_token_count", 0) or 0
                total_usage["total_tokens"] += getattr(usage, "total_token_count", 0) or 0
```
New:
```python
            usage = getattr(response, "usage_metadata", None)
            if usage:
                _accumulate_usage(total_usage, usage)
```

Downstream needs nothing: `huume_result.token_usage` → `store.complete_run` JSONB (no migration),
`_record_turn_usage` → `log_token_usage_event` (`_tokens.py:17` reads only the keys it stores —
extra keys ignored; `mw_token_usage_events` schema untouched).

---

## Change 3 — price `gemini-3.6-flash` + bill thinking

### `server/app/matcha/services/billing/model_pricing.py`

**Edit A — `MODEL_PRICING` gains an entry** (after `gemini-3.1-pro-preview`; values mirror
`ai_usage.PRICING:53`):
```python
    # Gemini 3.6 Flash — the Huume agent-loop model (huume/agent.py _MODEL).
    # Must match ai_usage.PRICING's row — the admin ledger priced this
    # correctly while billing fell to DEFAULT_PRICING (~3x low) on every
    # Huume turn.
    "gemini-3.6-flash": {
        "input_per_1m": Decimal("1.50"),
        "output_per_1m": Decimal("7.50"),
    },
```

**Edit B — `calculate_call_cost` signature** (current at l.64-79):
```python
def calculate_call_cost(
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    thinking_tokens: int | None = None,
) -> Decimal:
```
Body — current:
```python
    output_cost = Decimal(completion_tokens or 0) * pricing["output_per_1m"] / Decimal("1000000")
```
New (thinking bills at the output rate — same convention as `ai_usage.compute_cost`):
```python
    # Thinking tokens bill at the output rate (matches ai_usage.compute_cost).
    output_cost = (
        Decimal((completion_tokens or 0) + (thinking_tokens or 0))
        * pricing["output_per_1m"] / Decimal("1000000")
    )
```

### `server/app/matcha/routes/matcha_work/messaging.py`

**Edit C — `_record_turn_usage` (l.103-107).** Current:
```python
    cost = calculate_call_cost(
        model=str(final_usage.get("model") or "unknown"),
        prompt_tokens=final_usage.get("prompt_tokens"),
        completion_tokens=final_usage.get("completion_tokens"),
    )
```
New:
```python
    cost = calculate_call_cost(
        model=str(final_usage.get("model") or "unknown"),
        prompt_tokens=final_usage.get("prompt_tokens"),
        completion_tokens=final_usage.get("completion_tokens"),
        # Only the huume loop records this key today; skill-engine turns
        # carry no thinking_tokens and price exactly as before.
        thinking_tokens=final_usage.get("thinking_tokens"),
    )
```

---

## Change 4 — "Huume agent" block on `/admin/ai-usage`

### `client/src/pages/admin/AiUsage.tsx` (mirrors the image-generation block; no new endpoint)

**Edit A — const** next to `IMAGE_MODEL_PREFIX` (l.36):
```ts
const HUUME_FEATURE_PREFIX = 'matcha.huume.'
```

**Edit B — generalize the sum helper.** `sumImageMetrics(rows: AiUsageModelRollup[])` (l.42-60)
only reads `AiUsageMetrics` fields, and `AiUsageFeatureRollup`/`AiUsageModelRollup` are both
`AiUsageMetrics & {...}` (`client/src/types/aiUsage.ts:19-20`). Rename + retype + add the two
token fields the huume card needs:
```ts
function sumRollupMetrics(rows: AiUsageMetrics[]) {
  ...existing body unchanged, plus:
    thinking_tokens: rows.reduce((s, r) => s + r.thinking_tokens, 0),
    cached_tokens: rows.reduce((s, r) => s + r.cached_tokens, 0),
}
```
Import `AiUsageMetrics` from `'../../types/aiUsage'` (file already imports the other types).
Update the one existing caller (l.293) — behavior identical.

**Edit C — derivation** next to `imageModelRows` (l.292-293):
```ts
  // Derived, not fetched — same pattern as the image block above: by_feature
  // already carries every huume label's rollup (matcha.huume.loop plus the
  // embedded matcha.huume.legal_pilot / .handbook_pilot sub-features).
  const huumeRows = summary?.by_feature.filter((r) => r.feature.startsWith(HUUME_FEATURE_PREFIX)) ?? []
  const huumeTotals = huumeRows.length ? sumRollupMetrics(huumeRows) : null
```

**Edit D — card block** directly under the image block (after l.451's closing `)}`), same
structure; `Bot` icon added to the existing `lucide-react` import:
```tsx
      {huumeTotals && (
        <div className="mb-4">
          <p className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            <Bot size={11} /> Huume agent
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
            <StatCard label="Huume calls" value={String(huumeTotals.calls)} />
            <StatCard label="Huume spend" value={fmtCost(huumeTotals.cost_usd)} />
            <StatCard label="Tokens in" value={fmtTokens(huumeTotals.input_tokens)} sub="context" />
            <StatCard label="Thinking" value={fmtTokens(huumeTotals.thinking_tokens)} />
            <StatCard label="Cached" value={fmtTokens(huumeTotals.cached_tokens)} />
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {huumeRows.map((r) => (
              <button
                key={r.feature}
                type="button"
                onClick={() => selectFeature(r.feature)}
                className={`text-[10px] px-1.5 py-0.5 rounded border ${
                  selection?.kind === 'feature' && selection.value === r.feature
                    ? 'border-emerald-500 text-emerald-300'
                    : 'border-zinc-700 text-zinc-400 hover:text-zinc-200'
                }`}
              >
                {r.feature.slice(HUUME_FEATURE_PREFIX.length)} · {r.calls} · {fmtCost(r.cost_usd)}
              </button>
            ))}
          </div>
          {huumeTotals.unknown_cost_calls > 0 && (
            <p className="mt-1.5 text-[11px] text-amber-300/90">
              {huumeTotals.unknown_cost_calls} huume call(s) have unknown cost — spend above is undercounted.
            </p>
          )}
        </div>
      )}
```
(`StatCard` props: `{label, value, sub?, onClick?, active?}` — l.101. `selectFeature` already
exists and cross-filters the call log.)

---

## Tests

### `server/tests/huume/test_usage_accounting.py` (new file; pure, no DB/Gemini — same idiom as `test_huume_agent_helpers.py`)

```python
"""Huume spend-accounting tests (no DB/Gemini).

    cd server && ./venv/bin/python -m pytest tests/huume/test_usage_accounting.py -q

Covers: _accumulate_usage folding all five usage_metadata counters (thinking/
cached were silently dropped pre-2026-07), the gemini-3.6-flash pricing row
(billing fell to DEFAULT_PRICING ~3x low while the admin ledger priced it
right), thinking-at-output-rate billing, and the huume feature-label constants
the admin page's HUUME_FEATURE_PREFIX filter depends on.
"""
import inspect
from decimal import Decimal
from types import SimpleNamespace

from app.matcha.services.billing.model_pricing import (
    DEFAULT_PRICING, MODEL_PRICING, calculate_call_cost,
)
from app.matcha.services.huume.agent import _MODEL, _accumulate_usage


class TestAccumulateUsage:
    def test_folds_all_five_counters(self):
        total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                 "thinking_tokens": 0, "cached_tokens": 0}
        _accumulate_usage(total, SimpleNamespace(
            prompt_token_count=100, candidates_token_count=20,
            total_token_count=150, thoughts_token_count=30, cached_content_token_count=40))
        _accumulate_usage(total, SimpleNamespace(
            prompt_token_count=1, candidates_token_count=2,
            total_token_count=6, thoughts_token_count=3, cached_content_token_count=4))
        assert total == {"prompt_tokens": 101, "completion_tokens": 22,
                         "total_tokens": 156, "thinking_tokens": 33, "cached_tokens": 44}

    def test_missing_and_none_attrs_count_zero(self):
        total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                 "thinking_tokens": 0, "cached_tokens": 0}
        _accumulate_usage(total, SimpleNamespace())                       # attrs absent
        _accumulate_usage(total, SimpleNamespace(prompt_token_count=None,
                                                 thoughts_token_count=None))
        assert all(v == 0 for v in total.values())


class TestHuumeModelPricing:
    def test_huume_model_is_priced_not_default(self):
        # The loop's model must never fall back to DEFAULT_PRICING again.
        assert _MODEL in MODEL_PRICING
        assert MODEL_PRICING[_MODEL] != DEFAULT_PRICING

    def test_rate_matches_admin_ledger(self):
        # ai_usage.PRICING has ("gemini","gemini-3.6-flash"): (1.50, 7.50) —
        # the two ledgers must not disagree on the same model again.
        from app.core.services.ai_usage import PRICING
        inp, outp = PRICING[("gemini", "gemini-3.6-flash")]
        assert MODEL_PRICING["gemini-3.6-flash"]["input_per_1m"] == Decimal(str(inp))
        assert MODEL_PRICING["gemini-3.6-flash"]["output_per_1m"] == Decimal(str(outp))

    def test_million_token_cost(self):
        cost = calculate_call_cost("gemini-3.6-flash", 1_000_000, 1_000_000)
        assert cost == Decimal("9.000000")   # 1.50 in + 7.50 out


class TestThinkingBilling:
    def test_thinking_bills_at_output_rate(self):
        with_thinking = calculate_call_cost("gemini-3.6-flash", 0, 100, thinking_tokens=100)
        as_output = calculate_call_cost("gemini-3.6-flash", 0, 200)
        assert with_thinking == as_output

    def test_omitted_and_none_are_identical(self):
        assert calculate_call_cost("gemini-3.6-flash", 500, 500) == \
               calculate_call_cost("gemini-3.6-flash", 500, 500, thinking_tokens=None)


class TestFeatureLabels:
    def test_pilot_skills_carry_huume_labels(self):
        # The admin page filters by_feature on 'matcha.huume.' — a renamed or
        # dropped feature_scope label silently vanishes from the Huume block.
        from app.matcha.services.huume import handbook_skill, legal_skill
        assert 'feature_scope("matcha.huume.legal_pilot")' in inspect.getsource(legal_skill)
        assert 'feature_scope("matcha.huume.handbook_pilot")' in inspect.getsource(handbook_skill)

    def test_loop_label_shares_the_prefix(self):
        from app.matcha.services.huume import agent
        assert 'feature_scope("matcha.huume.loop")' in inspect.getsource(agent)
```

Note: check `ai_usage.PRICING` is importable/public before writing
`test_rate_matches_admin_ledger` — it is a module-level dict at `ai_usage.py:53`; if it's
underscore-private, read via `getattr(ai_usage, "PRICING", None) or ai_usage._PRICING`.

## Verification

```bash
cd server && ./venv/bin/python -m pytest tests/huume -q                      # new file + existing suite green
cd server && ./venv/bin/python -m pytest tests/matcha_work -q                # messaging untouched-behavior check (6 known blog_pdf failures)
cd client && npx tsc -p tsconfig.app.json --noEmit                           # -p form; bare tsc checks nothing
```
Manual (dev stack): `/admin/ai-usage` → Huume block hidden with no rows (same empty-state rule as
the image block); run a huume turn → `matcha.huume.loop` chip + thinking/cached populate; ask
Legal Pilot from a huume thread → `matcha.huume.legal_pilot` chip appears; chip click filters the
call log.

## Explicitly deferred

- Cancelled huume SSE stream records nothing in `mw_token_usage_events` (no cancel-finalizer
  analogue; admin ledger unaffected — the proxy records per call).
- Per-company attribution in `ai_usage_log` (documented v1 gap in `ai_usage.py` docstring).
- `huume_runs` stays write-only (timeline served from message metadata).

# Merlin: Highlight-Driven Precision Design (Cappe)

## Context

Merlin today edits at **block/field granularity**: the finest thing an op can address is a whole
text field (or a list index within one). Text fields are plain strings; fonts are theme-wide
(heading + body); per-section styling lives in the premium `_design` bag.

The goal is design-editor-grade precision: highlight any element — down to a single word or
letter — and Merlin always knows exactly what to edit, and can deliver real design at that
granularity (custom font treatment per span, AI-generated lettering, precise image
generation/placement).

Decisions:

- **Both capabilities, styling first**: structured span styling (real CSS: any web font, size,
  weight, color, gradients, spacing, shadows/outlines) is the foundation; AI-generated lettering
  (image-gen a word/letter as artwork, placed inline, original text preserved as alt) is the
  escalation path.
- **Highlight everything**: one unified selection contract — text ranges AND element clicks
  (images, buttons, single cards/list items).
- **Gating**: selection UX for all plans; span-design ops + lettering premium-gated exactly like
  `_design` already is.

On the infra question ("tailwind via our cloudfront cdn", dozens of edits/page × hundreds of
sites): **no build/compile step is needed**. Published sites are SSR'd Python string assembly
with one inline stylesheet, cached in Redis per (site, page) with `Cache-Control: public,
max-age=60` (`routes/render.py`). Span styling is just more string assembly on the same path;
there is nothing to compile or deploy per site. The real marginal costs are agent-loop
screenshots/model calls (already tier-bounded) and image generation (already quota'd).
CloudFront in front of tenant domains is an optional later bolt-on that the existing cache
headers already support.

## Current architecture (verified)

- **Op registry** `server/app/cappe/services/merlin/ops.py`: 14 whitelisted ops, each a
  `MerlinOp{name, validate, prompt_shape, prompt_rules}`; skip-and-report validation;
  `MAX_OPS_PER_TURN=20`. Client-side appliers in
  `client/src/cappe/pages/site/PageEditor/merlinOps.ts` (`applyMerlinOps`, pure fold; client
  state is source of truth).
- **Design vocabulary** `services/design_registry.py`: `DesignKey` registry (merlin_spec +
  declarative RenderRule), semantic `DESIGN_COLOR_TOKENS` (`--t-*` vars, cycle-proof), `_design`
  premium-gated via `design_gate.py:gate_content`.
- **Blocks** `services/merlin/catalog.py:BLOCK_FIELDS`: text is plain strings
  (`text|textarea`), lists of dicts for cards. Canvas blocks already do per-element style
  `{font,size,weight,spacing,lineHeight,color,align,…}` on a 24-col grid — the in-repo precedent
  for element-level styling.
- **Agent loop** `services/merlin/agent.py`: 5 tools (apply_ops / render_screenshot /
  inspect_block / generate_image / finish), per-tier bounds (regular 6 calls/3 shots/120s; max
  10/5/240s), working copy + op_log returned to client; screenshots via
  `services/browser_pool.py` (`focus_block` index → `data-cz-block` anchor scroll).
- **Selection today**: the editor's server-rendered iframe runtime ALREADY posts `cz-select
  {block, field}` and `cz-edit {block, field, value}` via postMessage (`useCanvasBridge.ts`) —
  click-to-select at block+field granularity exists; Merlin only ever receives `selected_block`
  (block id) (`models/merlin.py:CappeMerlinChatRequest`, `useMerlin.ts`).
- **Renderer** `services/render/page.py:render_site_html` + `blocks.py` + `design.py` +
  `sanitize.py`: pure string assembly, one inline `<style>`, one Google Fonts `<link>`
  (`_gfonts_link(heading, body)`).
- **Serving** `routes/render.py`: per-request SSR + Redis cache `cappe:render:{site_id}:{slug}`,
  owner-CRUD invalidation.
- **Editor preview**: debounced `POST /sites/{id}/preview` per edit → iframe srcDoc
  (`usePagePreview.ts`).
- **Image gen** `core/services/image_gen.py` (+ `image_quota`, `cappe_assets`,
  `image_prompting.py`).

## Plan

Blocks/pages are JSONB `content` folded client-side — **no DB migration in any phase**; the new
bags (`_spans`, request `selection`) are additive keys the existing save path persists
untouched, exactly like `_design`.

### Phase 1 — Unified selection contract (all plans, no gating)

Merlin always knows what "this" is: block → field → character range → element.

New request field (keep `selected_block` for back-compat), `models/merlin.py`:

```json
"selection": {
  "block": "k-abc123",
  "field": "items.2.title",   // dot path, same convention as set_field.path; null = whole block
  "kind": "text"|"image"|"button"|"element",
  "start": 4, "end": 9,        // char offsets into the plain-string field; null = whole field
  "text": "Fresh"              // selected substring — the authoritative anchor (max 300)
}
```

- **Server**: `CappeMerlinSelection` model (lenient/Optional — malformed degrades to
  `selected_block` behavior). `routes/merlin.py:_prepare_turn` + `services/merlin/turn.py` +
  `agent.py:_build_system_prompt` render a `SELECTED:` prompt section (`characters 4–9
  ("Fresh") of hero field "heading" — resolve "this"/"it" here`). Server cross-checks
  `selection.text` against the snapshot's field substring; on drift, re-anchor by text search or
  degrade to field-level with a "may be stale" note.
- **Runtime (iframe)**: extend the editor runtime JS (`render/blocks.py` `_CANVAS_JS` area) — on
  `selectionchange`/`mouseup` inside a `data-cz-field` element, compute char offsets against
  `textContent` and post `cz-selection {block, field, start, end, text, kind}`; image/button/
  element clicks post kind + no range. Audit all 22 block renderers so every text-bearing/image/
  button element carries `data-cz-field` (+ `data-cz-kind`) in editor mode.
- **Editor**: `useCanvasBridge.ts` handles `cz-selection` → `useMerlin.ts` sends `selection` in
  the request → `MerlinPanel.tsx` shows a selection chip ("Editing: 'Fresh' in Hero heading" with
  clear button).
- **Risk**: offset drift between rendered `textContent` and the source string (escaping, icon
  prefixes). Mitigation: only emit ranges from elements whose textContent is exactly
  `_esc(value)`; `text` is the authoritative anchor, offsets are a hint.

### Phase 2 — Per-span custom font design (premium-gated; the flagship)

**Data**: sibling `_spans` bag on the block — text stays a plain string, every existing consumer
unaffected:

```json
"_spans": { "heading": [ { "s": 4, "e": 9, "t": "Fresh", "style": { ... } } ] }
```

Anchor = offset + text `t`; on mismatch re-search for `t`; if gone, span drops silently
(never-raises).

**Span style spec** — new registry `services/span_registry.py` mirroring `design_registry.py`
(enums / clamped ints / color tokens, never free CSS):

| key | spec |
|---|---|
| `font` | enum over the curated font catalog (Phase 3) |
| `scale` | (50, 300) % of parent size |
| `weight` | {"300"…"900"} · `style` {"normal","italic"} |
| `spacing` | (-5, 30) in 0.01em · `transform` {none,uppercase,lowercase,capitalize} |
| `color` | tokens ∪ hex (reuse `_is_valid_color`) |
| `gradient` | same shape as `bg.gradient` (reuse `_design_gradient`) → background-clip:text |
| `highlight` | color (mutually exclusive with gradient — validator enforces) |
| `shadow` | {none,soft,hard,glow,neon,long} preset classes · `outline` {none,thin,thick} + `outlineColor` |
| `underline` | {none,solid,wavy,thick,accent-bar} · `rotate` (-15, 15) deg inline-block tilt |

**New ops** (registry entries in `ops.py` + appliers in `merlinOps.ts`):

- `style_text_range {block, field, start, end, text, style}` — validates field is text-kind
  (incl. dot paths into list items), `text` matches/re-anchors, style keys skip-and-report-
  stripped against the span registry; premium-refused with a reason like `set_design`. Caps: ≤8
  spans/field, non-overlapping (overlaps refused, model re-emits), ≤40 spans/page.
- `clear_text_range {block, field, start?, end?}` — omitted range clears the field's spans.

**Renderer**: new `render/spans.py:_esc_spans(value, spans)` — sort spans, split string, `_esc`
each segment, wrap ranges in `<span class="cz-sp …" style="…">` built ONLY from the registry's
declarative emission (`_hexonly`/`_clampi`/token lookup); any anomaly falls back to plain
`_esc(value)`. Swap into text-bearing renderers in `blocks.py`; shadow/underline preset classes
go in `_BASE_CSS`.

**Editing interplay**: inline edits post whole-field plain text (`cz-edit`) — new client
`spanHelpers.ts:reanchorSpans(oldText, newText, spans)` shifts offsets / drops orphans; wired
into `useCanvasBridge.ts` and `FieldInputs.tsx`.

**Gating**: `design_gate.py:gate_content` strips `_spans` alongside `_design` for non-premium;
validators refuse span ops on free plans.

**Prompt**: new shared section (op shapes, span spec table, token-over-hex, "1–2 styled spans
per section; typographic restraint" taste rules).

### Phase 3 — Design-tooling upgrades for the agent harness

- **Close-up screenshots**: `browser_pool.screenshot_html` gains `focus_field` — after the
  `focus_block` scroll, clip to `[data-cz-block] [data-cz-field]`'s padded bounding box (element
  screenshot) so letter-level work is actually judgeable. Extend the `render_screenshot` tool
  declaration + `do_screenshot` with a `field` arg; agent renders emit `data-cz-field` via a
  flag (published pages unchanged). No budget increase — a clip shot is cheaper than full-page.
- **Font catalog**: new `services/font_catalog.py` — ~50 curated Google fonts as `FontEntry{name,
  category, weights, vibe}` ("Playfair Display — serif, high-contrast, editorial/luxury"). Feeds
  the span registry's `font` enum + a vibe-grouped prompt section in
  `build_shared_prompt_sections` (shared single-shot + agent). Theme fonts stay free-text; span
  fonts are catalog-only.
- **Selection-aware loop**: first screenshot defaults its focus to the selection; prompt rule
  "after styling a range, take a focused screenshot of that field before finishing."
- `inspect_block` includes `_spans` so the agent can read existing span state.

### Phase 4 — AI-generated lettering (premium, agent-path only)

- **Op/tool** `generate_lettering {block, field, start, end, text, prompt, height?}` — validated
  like `generate_image`, executed client-side async (single-shot) AND as an agent tool so the
  loop screenshot-judges glyph fidelity and retries (reuses `do_generate_image`'s
  quota-degradation + `reference_images` machinery).
- **Generation discipline**: server-side prompt wrapper — transparent background, exactly the
  glyphs `"{text}"`, no extra marks, tight crop; aspect picked from text length; 1K default
  (inline art, cheaper than the 2K background default).
- **Storage**: span gains `art: {url, alt: original text}` (own-storage URL enforced via
  `attachments._is_own_storage`); renders as `<img class="cz-lt" alt="{text}"
  style="height:{h}em">` — baseline-locked em height, original text preserved as alt (SEO/a11y).
  `clear_text_range` restores plain text.
- Quota: rides the existing `image_quota` daily caps + cost-estimate labels.

### Phase 5 — Font delivery + infra (no Tailwind, no build step)

**Verdict on "Tailwind via CloudFront": not needed and actively worse.** There is no build step
today — sites are SSR string assembly with inline CSS, Redis-cached per (site, page),
invalidated on owner CRUD. Span styling adds bytes of inline CSS, not compile work; a Tailwind
pipeline would add per-site build artifacts, deploy latency, and a new failure mode for zero
win. Concretely:

- **Font collection**: `render/page.py` walks theme fonts + `_spans[].style.font` + canvas
  `style.font` → one merged deduped `_gfonts_link` (extend `design.py:_gfonts_link` to a list);
  `&text=` subsetting for span-only fonts (a one-word treatment downloads a handful of glyphs);
  validator cap ~6 extra families/page so a page can't accrete 20 font downloads.
- **CloudFront** in front of tenant domains honoring the existing `Cache-Control: public,
  max-age=60` is an optional later bolt-on — zero renderer change; only if origin QPS actually
  grows.
- **Cost guardrails already exist**: editor previews are debounced ms-scale string assembly;
  agent shots/calls are tier-bounded; image gen is quota'd. New caps added here: spans/field,
  spans/page, fonts/page.

### Sequencing & reuse

1 (selection) → 2 (spans) → 3 (tooling; can overlap 2) → 4 (lettering) → 5 (font delivery lands
with 2; CDN documented only).

Reused wholesale: `_design` gating pipeline, `DESIGN_COLOR_TOKENS`/`_is_valid_color`/
`_design_gradient`/`_font_stack`/`_gfonts_link`, skip-and-report validator machinery,
`focus_block` screenshot scroll, `generate_image` client-async execution + quota degradation,
canvas `style` keys as the span-spec precedent, `build_shared_prompt_sections` for
single-shot/agent prompt parity.

### Critical files

- `server/app/cappe/services/merlin/ops.py`, `catalog.py`, `turn.py`, `agent.py`
- `server/app/cappe/services/design_registry.py` (template) → new `span_registry.py`,
  `font_catalog.py`
- `server/app/cappe/services/render/blocks.py`, `page.py`, `design.py` → new `render/spans.py`
- `server/app/cappe/services/browser_pool.py`, `design_gate.py`, `models/merlin.py`,
  `routes/merlin.py`
- `client/src/cappe/pages/site/PageEditor/`: `merlinOps.ts`, `useCanvasBridge.ts`,
  `useMerlin.ts`, `MerlinPanel.tsx`, `FieldInputs.tsx` → new `spanHelpers.ts`,
  `selectionHelpers.ts`

### Verification

- **Unit**: mirror `tests/cappe/` patterns — new `test_render_spans.py` (escaping correctness
  incl. `<`/`&` inside/around ranges, gradient emission, anomaly fallback to plain `_esc`),
  span-op validator tests (overlap refusal, unknown keys stripped, free-plan refusal,
  re-anchor), registry-derivation test like `test_design_registry.py`, gate test that `_spans` is
  stripped on free save; client `spanHelpers`/applier tests beside `merlinOps.test.ts`. Run:
  `cd server && python3 -m pytest tests/cappe/ -q` and `cd client && npx tsc -p
  tsconfig.app.json --noEmit`.
- **End-to-end (manual, dev)**: in the editor, highlight one word in a hero heading → chip
  appears → ask Merlin "make this word look hand-lettered gold" → span op applies, preview shows
  it, Save persists, published tenant page renders identically with the extra font loaded;
  free-plan account gets the upsell refusal; agent tier takes a close-up shot of the field
  mid-turn (visible in the step trace).
- **Perf sanity**: render a page with 40 spans + 6 fonts and confirm preview latency is
  unchanged (string assembly); confirm Redis render-cache hit path unchanged.

# Cappe — Deep Design Control ("change anything on a template")

## Context

Cappe (consumer brand **Gummfit**, live on gummfit.com) is the website builder in this repo.
The owner wants **very specific control of design** — tooling to get in and change anything on a
template. Today the design surface is real but shallow:

- **Rendering is 100% server-side** — pure-Python string building in
  `server/app/cappe/services/render.py` (`render_site_html`, ~line 2083). Every design property is
  already a **CSS custom property** fed by tokens; a static `_BASE_CSS` (starts ~line 331) consumes
  them. There is **no React renderer** — the editor holds block JSON, PUTs the whole page, and shows
  a server-rendered HTML string in a sandboxed iframe (`POST /api/cappe/sites/{id}/preview`, 400ms
  debounce, `client/.../PageEditor/usePagePreview.ts`).
- **The gap**: `_BASE_CSS` hardcodes almost every spacing/type/layout magic number (`font-size:17px`,
  `line-height:1.6`, `.cz-wrap{max-width:72rem;padding:0 1.5rem}`, section `clamp(3rem,7vw,5rem)`,
  grids `repeat(auto-fit,minmax(220px,1fr))`, `.cz-card{padding:1.6rem}`). None of it is user-editable.
  The per-section `_design` layer (`_apply_design`, line 133) handles motion/bg/layout/colors but has
  no columns, arbitrary padding, per-section type size, borders, or anchors.
- **Security invariant (must preserve)**: no raw user string reaches a CSS/attr/class sink — every
  value is an enum lookup, a clamped number (`_clampi`), a hex-only color (`_hexonly`), or a
  scheme-checked URL. Font name is the one hardened free-text sink (`_font_stack`).

**Decisions locked with the user:**
1. **Structured tokens only** — widen the token vocabulary + expose richer controls. No custom-CSS
   escape hatch, no full-canvas rebuild. Keep the "no raw CSS" invariant.
2. **Productize for Pro/Business** — new controls sit above the existing premium wall.
3. **All four editor UX upgrades** — undo/redo, drag-reorder in form mode, copy/paste section styles,
   saved style presets/library.

**Load-bearing finding (verified twice):** the premium wall is **client-only**. The server enforces
plan for site count (`sites.py:47 _PLAN_SITE_LIMIT`) and video upload (`uploads.py:42
_VIDEO_PLANS`), but `render.py` applies `_design`/`theme.premium` for **any** site — `render_site_html`
never receives an account/plan. A hand-crafted PUT already unlocks all "premium" design today.
Monetizing new controls therefore requires a server-side gate (Phase E), which also closes the
existing bypass. This is a monetization gate, not a security fix — the renderer stays injection-safe
regardless.

The mechanism that makes all of this safe and non-breaking: convert each hardcoded `_BASE_CSS`
literal to `var(--token, <same literal>)`, and only emit `--token` when the editor sets it. **Unset ⇒
byte-identical render.**

---

## Phase A — Global style system (server: `render.py`)

Follow the existing "designer extra-vars" precedent at `render.py:2130-2146` (`type.headingWeight`
→ `--font-h-wght`, etc.): parse `theme_config.style` into an `_extra` list of `--token:value` strings,
join into an extra `:root{}` block, concatenate after `theme_vars` in the `<style>` (line ~2170).

**New enum maps (module constants near `_PAD_SCALE`, line 103)** — default value equals today's literal:
- `_CONTAINER` compact/default(72rem)/wide/xwide · `_GUTTER` tight/default(1.5rem)/roomy
- `_LINEHEIGHT` tight/normal(1.6)/relaxed · `_SEC_PAD` compact/cozy/default(`clamp(3rem,7vw,5rem)`)/roomy
- `_CARD_BORDER` none/hairline(1px)/bold · `_GRID_GAP` tight/default(1.25rem)/roomy

**New `theme_config.style` keys → tokens** (each conditional; absent ⇒ omitted): `baseFont`
(`_clampi 14-20`→`--base-fs`), `lineHeight`→`--base-lh`, `container`→`--container`, `gutter`→`--gutter`,
`sectionPad`→`--sec-pad`, `gap`→`--grid-gap`, `cardPad`(`8-48`)→`--card-pad`, `cardBorder`→`--card-bd`,
`headerPad`(`8-28`)→`--hdr-pad`, `brandSize`(`14-32`)→`--brand-fs`, `footerPad`(`16-80`)→`--ftr-pad`,
`buttonPadX/Y`→`--btn-px/--btn-py`.

**`_BASE_CSS` literal→var conversions** (exact lines): body font/line-height (335); `.cz-wrap`
container+gutter (340, leave `.cz-narrow` fixed); section padding on the **standard family only**
(`.cz-features/gallery/pricing/quotes/band/menu/store/stats/faq/bento/split/creds/reviews/map/form-sec`)
— **do NOT touch** `.cz-hero/text/posts/hours/logos` (deliberate different rhythm); card padding +
border-width on `.cz-card/plan/quote/review/cred/bento-cell`; grid gaps per-grid; header/brand/footer/
button. Each becomes `var(--token, <exact current literal>)`.

**Gate**: `_clean_css` only strips `< > }` — safety comes entirely from values being enum-dict
constants or `_clampi` ints emitted with a unit. Never interpolate a `style.*` string directly.

## Phase B — Global style panel (client: `ThemeMenu.tsx` + `useThemeEditor.ts`)

- Add `setStyleKey(key, value)` mutator to `useThemeEditor.ts` (model on `setTypeKey`, line 35 —
  delete-on-empty). Export + expose.
- Add a **"Layout & spacing"** subsection inside the existing premium "Designer" block in
  `ThemeMenu.tsx` (after line 137, still under `designerUnlocked` gate). Reuse `DSelect`/`DNum` from
  `DesignPrimitives`. Controls: base font, line height, container, gutter, section spacing, grid gap,
  card padding, card border, header/brand/footer padding — each bound to a `style.*` key, first option
  "Default" → `''` (clears the key). No new API calls; writes flow through the existing `theme_config`
  PUT and the live preview already sends `theme_config`.

## Phase C — Richer per-section inspector (server `_apply_design`+`_BASE_CSS`, client `DesignInspector.tsx`)

**Server — extend `_apply_design` (render.py ~215-244)**, all skip-when-absent:
- `layout.columns` (`_clampi 1-6`) → `--cz-cols:repeat({n},minmax(0,1fr))` + class `cz-has-cols`.
- `layout.padTopPx`/`padBottomPx` (`0-400`) → reuse `--cz-pad-t/-b`; **px wins over the enum `padTop`**
  (compute px first, fall back to `_PAD_SCALE` only when px absent — don't double-emit).
- `layout.gap` (`0-80`) → `--cz-gap`.
- `type.headingSize` (`16-96`) → `--cz-h-size` + `cz-has-hsize`; `type.bodySize` (`12-28`) → `--cz-p-size`.
- `border.top`/`border.bottom` (bool) + `border.width` (`1-8`) + `border.color` (`_hexonly`) → classes
  `cz-bd-t/-b` + `--cz-bd-w/--cz-bd-col`.
- `anchor.id` → **new `_anchor_id` helper**, strict `^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$` else `""`,
  appended to the existing `attrs` merge (NOT a second `_SECTION_RE`). This is a new `id=` attr sink —
  the strict slug is what keeps it safe.

**Server — `_BASE_CSS` block-class updates** (cz-design layer ~733-748):
- Each grid consumes columns by wrapping the **whole value** in one var with its current literal as
  fallback: `.cz-cards{grid-template-columns:var(--cz-cols,repeat(auto-fit,minmax(220px,1fr)))}`, same
  for `.cz-grid-img/plans/quote-grid/stats-grid/creds-grid/reviews-grid/menu-grid`. **Exclude
  `.cz-bento-grid`** (768px span layout, 679-682) and `.cz-logos__row` (flex) — hide "Columns" for
  those block types in the inspector.
- Per-grid `gap:var(--cz-gap, <default>)`; heading/body size scoped under `.cz-design.cz-has-*`;
  `.cz-bd-t/.cz-bd-b` border rules.

**Client — extend `DesignInspector.tsx`** (already premium-gated, line 30): add Columns / Padding-px /
Item-gap / Type-size / Border / Anchor controls after the Layout section (80), via the existing
`patch(group,key,value)` → `onChange({...block,_design})`. No new API surface.

## Phase D — Editor UX (client, `PageEditor/`)

1. **Undo/redo** — new `useEditorHistory.ts`. Snapshot = `{blocks,title,meta,theme}`; `past/future`
   stacks + `isRestoring` ref; record via a **500ms-coalesced** effect (skip while restoring, cap ~50);
   Cmd+Z / Cmd+Shift+Z listener in `index.tsx` (guard against canvas contenteditable). Toolbar buttons
   in `EditorToolbar.tsx`. **`themeEditor.loadTheme` must also set dirty** (add `markDirty()`) or
   restored theme won't save.
2. **Drag-reorder in form mode** — assign each block a stable ephemeral `_k` (`crypto.randomUUID()`,
   stripped before PUT) and key cards on it (index keys break DnD). Native HTML5 DnD on the
   `BlockCard` grip (line 26) → new `reorderBlock(from,to)` in `index.tsx`; keep arrow `moveBlock`.
   No new library (client convention).
3. **Copy/paste section style + duplicate** — wire the existing `duplicateBlock` (index.tsx:90) into a
   `BlockCard` header button. Add a `styleClipboard` in `index.tsx` state mirrored to
   `localStorage['cappe:styleClipboard']`; Copy-style = `structuredClone(block._design)`, Paste-style =
   `onChange({...block,_design:clone})` **dropping `anchor.id`** (ids stay unique).
4. **Saved style presets/library** — **new DB table** `cappe_style_presets` (account-scoped;
   `kind ∈ {theme,section}`, `data JSONB`), migration `zzzzcappe21_style_presets.py`
   (`down_revision="zzzzcappe20"`, raw-SQL `op.execute` per convention, `gen_random_uuid()` PK,
   CASCADE on account, account index). New router `routes/presets.py` (mirror `pages.py`) —
   `GET/POST/DELETE /style-presets`, `Depends(require_cappe_account)`, `account_id`-scoped; Pydantic
   `CappeStylePresetCreate` in `models/cappe.py`; mount in the cappe routes `__init__`. **Re-validate
   `data` through the Phase E gate on POST** so a preset can't smuggle premium tokens. Client: typed
   helpers in `cappeClient.ts`; "Save/apply" UI in `ThemeMenu.tsx` (theme) + `DesignInspector.tsx`
   (section).

## Phase E — Server-side premium enforcement (REQUIRED to monetize)

New `services/design_gate.py`: `gate_theme(theme_config, plan)` strips premium `style.*`/`type.*`/
`colors.brandGradient`/`premium` keys for `plan ∈ {free,hosting}`, passes through for `{pro,business}`;
`gate_content(content, plan)` drops `_design` from every block for non-premium plans. Apply at the
**write choke points** (renderer stays account-context-free): `update_site` (sites.py:240) on
`theme_config`, `update_page` (pages.py:92) on `content`, and **`preview_site_page` (sites.py:175-184)**
so the editor preview reflects the wall. Defense-in-depth: injection-safety is unchanged; this only
gates monetization. Pre-existing sites unaffected (gate strips on write only, premium plans untouched).

---

## Critical files
- `server/app/cappe/services/render.py` — Phases A + C (tokens, `_BASE_CSS`, `_apply_design`)
- `client/src/pages/cappe/site/PageEditor/ThemeMenu.tsx` + `useThemeEditor.ts` — Phase B + preset UI
- `client/src/pages/cappe/site/PageEditor/DesignInspector.tsx` — Phase C controls
- `client/src/pages/cappe/site/PageEditor/index.tsx` + `EditorToolbar.tsx` + `FormModeView.tsx` +
  `BlockCard.tsx` + new `useEditorHistory.ts` — Phase D
- `server/app/cappe/routes/sites.py` + `pages.py` + `models/cappe.py` + new `services/design_gate.py`
  + new `routes/presets.py` — Phases D(4) + E
- `server/alembic/versions/zzzzcappe21_style_presets.py` (new) — Phase D(4). **Do NOT auto-run
  Alembic; user applies to dev then prod per repo rules.**

## Cross-cutting pitfalls
- `_clean_css` is not a general sanitizer (strips only `< > }`) — safety depends on values being enum
  constants or clamped ints. `_SECTION_RE` matches only the first `<section>`; merge `anchor.id` into the
  existing `attrs`, not a new regex. `--cz-cols` fallback must be each grid's exact current `repeat(...)`
  or unset sections shift. Whole-blob PUTs (site theme, page content) can clobber across canvas/form
  tabs + autosave — add an `updated_at` optimistic-concurrency 409 or a "changed elsewhere" warning.
  Keep the preview sequence-guard (`usePagePreview` 31-32) and history coalescing so the debounced
  re-render path isn't amplified.

## Verification (end-to-end)
1. **Byte-identical guard**: render a seeded template (`seed_cappe_templates.py`) with
   `render_site_html` before and after the `_BASE_CSS`→var conversion; diff HTML (ignore `_uid()`
   counter deltas). Must be identical when no `style.*`/new `_design` keys are set.
2. **Server unit**: feed a `theme_config.style` / `_design` blob with out-of-range + junk values through
   `_tokens`/`_apply_design`; assert only clamped/enum/hex output, no raw strings in the emitted CSS.
3. **Gate test**: `gate_theme`/`gate_content` with `plan='free'` strips premium keys; `plan='pro'`
   passes through; preset POST re-validation rejects smuggled premium.
4. **Live UI** (`./scripts/dev-remote.sh`, frontend :5174 — track any throwaway server by PID, never
   port-pattern pkill): open a site's PageEditor as a Pro account → global style panel changes
   container/section-padding/base-font and the preview reflects them; per-section columns/border/anchor
   apply; undo/redo, drag-reorder, copy-paste style, save+apply a preset. As a free account, confirm the
   panel is locked and a crafted premium blob is stripped on save.
5. `cd client && npx tsc --noEmit` clean; `cd server && ./venv/bin/python -m pytest tests/ -q` for any
   added cappe tests. Cloud/`claude/*` branch scope = commit + PR only, no build/deploy.

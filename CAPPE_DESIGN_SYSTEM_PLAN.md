# Cappe — Premium Design System: completion roadmap

Status: Stage 1 shipped (`898edbf`, branch `cappe/web-design`). Stages 2–7 below are planned, not started.

## Context

Stage 1 (theme highlight-sync + de-stacked editor layout) is done. This doc covers what's left to make Cappe a credible **premium bespoke** design system rather than a template picker, plus backend speed/accuracy.

An audit found the editing UX fixed but the **design vocabulary thin**: no shadows/elevation at all, no button styles for template CTAs (only canvas buttons have them), no link styles, no per-heading type scale, no hide-on-mobile, no per-element control inside template blocks, no custom-CSS escape hatch. Backend: preview does a full re-render per keystroke, images are raw 5MB S3 passthrough, published pages cold-miss into a 300s Redis TTL, and JSONB content is unvalidated.

Scope decisions taken: **per-element styling inside template blocks** (not just tokens); **optimize new uploads**; **all four backend items**.

## Verified current state (load-bearing facts)

- **Pillow 12.2.0 is already installed** (transitive) → the image pipeline needs **no new dependency**.
- **`design_gate.py` strips `theme_config.style` wholesale** for free plans (`_PREMIUM_THEME_KEYS = ("style","type","premium")`) and strips every block `_design`. ⇒ **every new style token is auto-gated**. Only a new *top-level* key (`customCss`) needs a gate entry.
- `render.py:_style_vars` (137-168) is table-driven (`_enum` / `_px` helpers) — a new token is ~1 line + 1 dict.
- `render.py:_apply_design` (190-372) already post-processes each block's HTML and **merges classes into its first `<section>`** — the hook for per-element scoping.
- Renderers use **stable semantic classes** (`.cz-hero__title`, `.cz-plan`, `.cz-stat__num`, `.cz-card`, …); `_btn` (981) and `_head` (993) are single choke points. ⇒ per-element targeting needs **zero renderer edits**.
- `_canvas` (1853) already emits a **scoped `<style>` per block** with `@media` mobile overrides — the pattern to reuse for element CSS.
- `POST /sites/{id}/preview` (`routes/sites.py:162`): full `render_site_html` + 2 DB reads + gate, on every call, `no-store`.
- Public render (`routes/render.py:41,219-260`): Redis `cappe:render:{site}:{slug}`, TTL 300s, invalidated on CRUD. No warm-on-publish, no ETag.
- `routes/presets.py`: GET/POST/DELETE only, no PUT. Table `cappe_style_presets`, account-scoped.
- `models/cappe.py`: `content` / `theme_config` are `dict[str, Any]` passthrough — zero validation.

**Migrations needed: none.** Everything rides existing JSONB (`theme_config`, `_design`) or existing tables.

---

## Stage 2 — Form-mode declutter + form↔preview sync

- `BlockCard.tsx:26` — default **collapsed** (`useState(false)`); auto-open only the just-added block (`defaultOpen` prop from `FormModeView`'s add path).
- Header chrome: grip + label + **kebab (⋮)** (Copy/Paste style, Duplicate, Up/Down) + delete + chevron. Drag-reorder already exists, so Up/Down leave the always-visible row.
- `FormModeView.tsx:38` — list column `lg:w-[38%]`, preview 62%.
- **Block sync** (the bridge already highlights by index): hover/expand a card → `cz-highlight {block}` + scroll the block into view; click a block in the preview → expand + scroll its card.
  - Needs the runtime in form mode always, not only when the drawer is open: `usePagePreview` → `editable = editMode==='canvas' || themeOpen || editMode==='form'` (i.e. always true inside the editor).
  - **Suppress canvas affordances in form mode**: post a `mode` at `cz-ready` (`'form' | 'canvas'`); in form mode the runtime keeps click→select but disables dblclick-to-edit, drag-reorder, and element drag/resize. Stage 1's `themeMode` flag already gates these — generalize the two booleans into one `interaction` mode.

## Stage 3 — No-flash theme preview

Theme-only edits must stop replacing the whole `srcDoc`.

- **Server**: `POST /sites/{id}/preview` gains `vars_only: bool`. When true, return `{css}` — just `theme_vars` + `extra_vars` (`render.py:2231-2253`, including `_style_vars`) + `customCss` (Stage 6) — as JSON, skipping block render entirely. Same `gate_theme`, 1 DB read.
- **Client**: `usePagePreview` fast path — if only `theme` changed (blocks / meta / title unchanged by reference), call `vars_only` and `postToTheme({type:'cz-theme-vars', css})` instead of touching `srcDoc`.
- **Iframe** (`_CANVAS_JS`): handle `cz-theme-vars` → replace `<style id="cz-live-theme">`, appended after the base `<style>` so same-`:root` vars win by cascade. Preserves scroll + selection.
- **Full-reload fallback** (must not silently miss): fonts (`fonts.heading` / `body`) or `preset` changed → `_gfonts_link` must reload; blocks / meta / title changed; initial load; mode switch.

## Stage 4 — The missing design primitives (theme tokens + section overrides)

New `theme_config.style` / `.type` keys. Each is one `_enum`/`_px` line in `_style_vars`, one dict, one control in `ThemeDrawer`, and **one entry in `THEME_REGION_SEL` + the `ThemeRegion` union** — Stage 1's highlight-sync must stay complete, since a token with no region is a token whose effect the user can't see.

| Key | CSS var | Values |
|---|---|---|
| `style.shadow` | `--shadow` | none / soft / medium / dramatic → box-shadow on `.cz-card,.cz-plan,.cz-quote,.cz-bento-cell` |
| `style.buttonStyle` | `--btn-*` | solid / outline / soft / pill → `.cz-btn` variants (template CTAs get style control for the first time) |
| `style.linkStyle` | `--link-*` | plain / underline / brand |
| `type.headingScale` | `--h1` … `--h3` | compact / default / display → an h1–h3 `clamp()` triple (one control, three sizes — keeps the type *relationship* coherent) |

Per-section `_design` additions (in `_apply_design`):

- `layout.hideMobile` → `@media(max-width:767px){display:none}` — responsive visibility, currently absent entirely.
- `layout.padX` (0-200px) → `--cz-pad-x` — only top/bottom padding exists today.
- `bg.focal` (9-position enum) → `background-position` — background images crop badly without it.
- `shadow` (same enum as the theme token) → section-level elevation.

## Stage 5 — Per-element styling inside template blocks ⭐ (the bespoke unlock)

**Approach: closed selector registry + scope class. No renderer changes.**

- `_apply_design` adds `cz-b{index}` to the section when `_design.el` is non-empty (it already merges classes), plus `data-cz-type` when editable so the runtime can resolve clicks.
- **`_EL_TARGETS` registry** in `render.py` — block type → element key → CSS selector, grounded in the real emitted classes:
  - `hero`: eyebrow `.cz-hero__eyebrow` · heading `.cz-hero__title` · sub `.cz-hero__lead` · cta `.cz-cta-row .cz-btn--solid` · cta2 `.cz-cta-row .cz-btn--ghost`
  - `features`: heading `.cz-head h2` · card `.cz-card` · cardIcon `.cz-feat__icon` · cardTitle `.cz-card h3` · cardBody `.cz-card p`
  - `pricing`: plan `.cz-plan` · planHot `.cz-plan--hot` · planName `.cz-plan h3` · planPrice `.cz-plan__price` · planBadge `.cz-plan__badge` · planCta `.cz-plan .cz-btn`
  - `testimonial`: quote `.cz-quote` · quoteText `.cz-quote blockquote` · quoteAuthor `.cz-quote figcaption b`
  - `cta`: heading `.cz-band h2` · sub `.cz-band p` · button `.cz-band .cz-btn`
  - `split`: heading `.cz-split__body h2` · body `.cz-split__body p` · bullets `.cz-split__bullets li` · art `.cz-split__art img` · cta `.cz-split .cz-btn`
  - `stats`: stat `.cz-stat` · statNum `.cz-stat__num` · statLabel `.cz-stat__label`
  - `text`: heading `.cz-text h2` · body `.cz-text p`
  - bento / gallery / logos / faq / credentials / menu get added incrementally — the registry is pure data, additive.
- **Indexed targeting**: key `plan[1]` → `.cz-plans > .cz-plan:nth-child(2)` (0-based key, clamped int). This is what lets you style *the second pricing card* without touching the others. The registry marks which keys are indexable.
- **Element props** (closed, clamped set): `bg` / `color` (hex), `border{width,color}`, `radius` (0-200), `shadow` (enum), `padX` / `padY`, `font`, `fontSize`, `fontWeight` (400-900), `align`, `opacity` (0-100), `hover` (none/lift/glow).
- **Emit**: one scoped `<style>` per block (reusing `_canvas`'s pattern) — e.g. `.cz-b3 .cz-plan:nth-child(2){background:#111;…}`.
- **Injection invariant** (state it in the code): the selector *never* comes from user input — it is the closed registry plus a clamped integer, and every value passes the existing `_hexonly` / `_clampi` / enum gates. Same defensive posture as `_apply_design` today.
- **Frontend**: mirror the registry in `elementTargets.ts`; inject it into the runtime as JSON so a canvas click can resolve target → key (`el.closest(sel)` against the block's type). Extend `cz-select` with an `el` field; the floating canvas inspector gains **Block | Element** tabs. Element selection reuses the existing `.cz-el-sel` outline.
- **Gating**: rides the existing `_design` strip in `gate_content` — free plans lose it automatically, no gate edit needed.

## Stage 6 — Custom CSS + saved-looks revamp

- **Custom CSS** (`theme_config.customCss`, premium): inject `<style id="cz-custom">` **after** theme vars + `_style_vars` so it wins. Sanitize the `</style` breakout (`.replace("</", "<\\/")`), cap 20KB server-side. Add `"customCss"` to `_PREMIUM_THEME_KEYS` in `design_gate.py` — the one gate edit this whole plan needs. Monospace textarea in an "Advanced" drawer tab. Stage 3's `vars_only` payload must include it.
- **Saved looks**: add `PUT /style-presets/{id}` (rename + "overwrite with current look"), gate-validated exactly like POST. Frontend: inline rename, an overwrite button, and a **swatch thumbnail** rendered from `data.colors` / `fonts` (reuse the preset-grid swatch markup already in `ThemeMenu.tsx`).

## Stage 7 — Backend speed + accuracy

- **Image pipeline** (`routes/uploads.py`; Pillow already present): on upload, cap max dimension ~2400px, strip EXIF, and emit a **WebP** sibling; store both and serve via `<picture>`. New uploads only; existing URLs untouched. Keeps the current SVG block.
- **Warm render on publish**: `publish_site` pre-renders each page into Redis, killing the first-visitor cold miss. Reuse `invalidate_render_cache`'s key scheme.
- **ETag on public render**: hash the rendered HTML → `ETag` + `304` on `If-None-Match`. Repeat visits become free.
- **Trim Google Fonts**: `_gfonts_link` (423) requests 5 weights × up to 3 families as a render-blocking `<link>`. Request only the weights actually in use (`--font-h-wght` / heading weight / body 400+600). Faster first paint on every published site.
- **Content validation warnings**: a light `validate_content()` returning *warnings* (unknown block type, unknown field, malformed list) surfaced in the editor — **not** hard rejects, so existing sites can't break. Today a malformed block renders empty and silent.

---

## Shipping order

2 → 3 → 4 → 5 → 6 → 7. Each stage is independently shippable and testable. Stage 5 is the big one and depends on nothing but Stage 4's shadow enum (shared). Stage 3 goes before 4 and 5 because it makes them *feel* right — no iframe flash while dragging a slider.

Work lands on `cappe/web-design`. No deploy/CI.

## Verification (per stage)

- `cd client && npx tsc --noEmit --incremental false` (never incremental — it false-cleans).
- `cd server && python3 -m py_compile app/cappe/services/render.py`, and syntax-check the injected `_CANVAS_JS` by extracting it and running it through `new Function(...)` — this caught a real error during Stage 1.
- Manual, against the existing dev-remote on `:5174` (do **not** `pkill -f vite`; the pattern also matches the real dev server):
  - **S2** — cards start collapsed; hovering a card glows + scrolls its block; clicking a block expands its card. Form mode shows no drag/dblclick affordances.
  - **S3** — dragging a spacing slider causes no iframe flash and preserves scroll. Changing a font or preset still triggers a full reload (fonts must load).
  - **S4** — each new token hover-highlights the right region (highlight-sync stays complete); a free plan sees them stripped.
  - **S5** — click the 2nd pricing card in canvas → Element tab → set bg/shadow → only that card changes; the published page renders identically; a free plan gets nothing.
  - **S6** — `</style><script>alert(1)</script>` in custom CSS renders inert; >20KB is rejected; save → rename → overwrite → apply a look.
  - **S7** — upload a 5MB JPEG → stored at ≤2400px with a WebP sibling; publish → the first visitor hits a warm cache; a second request returns 304.

# Cappe refactor — technical implementation plan

**Status: proposed, not yet implemented.** This document lays out a commit-by-commit plan for refactoring `server/app/cappe/`. No code in `server/app/cappe/` has been changed as part of this PR — this is the plan only, for review before implementation begins.

## Context

`server/app/cappe/` (~17.7k lines, 60 files) is healthy but three files grew into monoliths and one layering inversion exists. Six refactoring items, all intended to be behavior-preserving — no schema/DB changes, no API changes, every commit should leave the test suite green:

1. Layering fix (services importing from `routes/_shared.py`)
2. `models/cappe.py` split (1,422 lines / 127 Pydantic classes)
3. `services/merlin/` package (8 flat `merlin_*` files, ~3,400 lines)
4. `routes/public.py` split (1,420 lines, 9 banner-delineated sections)
5. `services/render.py` split (2,604 lines; ~1,100 are inline CSS/JS → real `.css`/`.js` asset files)
6. Fat-endpoint extractions (`public_create_order` ~260 lines, `_resolve_booking_slot` ~110, `merlin_agent` SSE route ~210)

**Dedupe finding reversed during planning**: an earlier review pass flagged `_canvas_elements` (merlin_ops vs merlin_apply) and `_num` (merlin_ops vs render) as duplicates. Verified NOT duplicates — different semantics (ops `_num` rejects bools/strings, render `_num` coerces strings; ops `_canvas_elements` filters to dicts, apply's doesn't). **Do not merge them.** No dedupe commit.

## Verified constraints (import graph fully explored)

- **models shim must be `models/cappe.py` itself** — `models/__init__.py` is empty, nothing imports package-level. Importers: 22 route files + `dependencies.py` (relative `..models.cappe`), 3 test files (absolute). No service/worker imports models.
- **render private names reached by tests** — must stay importable from `app.cappe.services.render` after the split: `_emit_design_group`, `_DIVIDER_PATHS`, `_anchor_id`, `_BASE_CSS`, `_EASING`, `_LOOP_FX`, plus `_render_block` / `_tokens` via module-attribute access (`from app.cappe.services import render as R`). In-app importers use only `render_site_html` (routes/render.py, sites.py, merlin.py, templates.py). render.py's only intra-cappe import is `design_registry` — it's a leaf.
- **merlin cycle**: `merlin_router.py:~174` has a *function-local* `from .merlin import resolve_model_tier` (cycle breaker — MUST stay lazy after the move). `merlin.py` re-exports `MERLIN_OPS, OP_NAMES, validate_ops` from `merlin_ops` with `# noqa: F401` — `test_merlin_validation.py` depends on `merlin.validate_ops`; keep the re-export.
- **Test-only private crossings to preserve**: `merlin._build_prompt`, `merlin._THEME_INTENT_RE`, `merlin_ops._v_set_theme` + `ValidationCtx`, `routes/public._validate_intake` (test_cappe_offerings), `routes/_shared._site_owner` (used by public.py).
- **routes/public.py external surface**: only `routes/__init__.py` (`from .public import router as public_router` — keeps working against a package) + the `_validate_intake` test import. `_published_site` / `_resolve_booking_slot` are internal-only.
- **Module-attribute import styles that break naive moves**: `routes/merlin.py` does `from ..services import cappe_assets, merlin_store`; `test_canvas_render.py` does `R._render_block`. Countermeasures below (alias import; `__init__` re-binds).
- **Outside-cappe importers (paths that must not move)**: `main.py` (cappe_router; `routes.render` router + `is_registered_custom_domain`; `browser_pool.shutdown`), `workers/tasks/cappe_{campaign_send,booking_reminders,domain_renewals}.py` (services.campaigns/email/reminders/stripe_connect/porkbun), `tests/test_scoped_auth.py` (services.auth), `scripts/cappe_make_test_tenant.py` (`routes._shared.slugify`).
- **Tests**: all `tests/cappe/` files use normal absolute imports (no importlib fragility). `test_merlin_turn.py` is inside `tests/cappe/`; `test_scoped_auth.py` at `tests/` root.
- Post-edit hook py_compiles every `.py`. TS untouched. No alembic surface.

## Global decisions

- **Merlin move: update importers, NO shims.** All importers are in-repo and enumerated (~15 test files, `routes/merlin.py`, `routes/uploads.py`). Use `git mv` so history follows.
- **Models split: permanent shim, importers NOT updated.** `models/cappe.py` becomes a star-re-export shim and stays; zero churn in 26 importing files (avoids rebase pain against commits 5–7 which edit routes).
- **Ordering**: item 1 → before merlin move (else merlin_store's import is rewritten twice). Merlin move → before agent-SSE extraction (new module lands directly in `services/merlin/`). Endpoint extractions → before public.py split (split moves lean stubs, not fat bodies about to be gutted).

## Commit sequence

Test command: **CAPPE** = `cd server && python3 -m pytest tests/cappe/ -q` — run at the end of every commit; targeted subsets listed per commit run first for fast signal.

### Commit 1 — Layering fix: pure helpers → `services/common.py`

- **Create** `server/app/cappe/services/common.py`: move verbatim from `routes/_shared.py` the pure helpers `_SLUG_RE`, `RESERVED_SUBDOMAINS`, `slugify`, `safe_subdomain_base`, `loads`, `loads_list`. DB-touching helpers (`unique_slug`, `unique_site_slug`, `get_owned_site`, `fetch_option_groups`, `_site_owner`, `site_row_to_dict`, `page_row_to_dict`) stay in `routes/_shared.py`.
- **Edit** `routes/_shared.py`: delete moved bodies, add `from ..services.common import RESERVED_SUBDOMAINS, loads, loads_list, safe_subdomain_base, slugify  # noqa: F401` — all ~20 route importers, `test_cappe_auth_tokens.py`, `test_cappe_hosting.py`, `scripts/cappe_make_test_tenant.py` untouched.
- **Edit** `services/merlin_store.py:20` → `from .common import loads_list`; `services/readiness.py:8` → `from .common import loads`.
- **Test**: `pytest tests/cappe/test_cappe_auth_tokens.py tests/cappe/test_cappe_hosting.py tests/cappe/test_merlin_conversations.py -q`, then CAPPE.

### Commit 2 — `models/cappe.py` → `models/` package (permanent shim)

- **Create** domain modules split along the file's existing banner comments; rule: a class lives with the domain whose routes consume it; `CappePublic*` response models live in `models/public.py` importing from shop/bookings as needed:
  - `models/auth.py` (signup/login/tokens/account)
  - `models/sites.py` (sites, pages, templates, readiness, `normalize_custom_domain`)
  - `models/shop.py` (products/options, orders, checkout, receipt, inventory, discounts)
  - `models/bookings.py` (booking types, availability, rate rules, rider, locations, staff, bookings/quotes)
  - `models/engage.py` (newsletter/campaigns, forms, reviews, messages/threads, clients, blog)
  - `models/merlin.py` (merlin chat/agent/conversation shapes)
  - `models/public.py` (`CappePublicSite`, `CappePublicLocation`, `CappePublicStaff`, `CappePublicBooking`, `CappePublicThread`, …)
- Each submodule gets an explicit `__all__`; **rewrite** `models/cappe.py` as `from .auth import *  # noqa: F401,F403` (one line per submodule). `models/__init__.py` stays empty.
- **Guard**: capture `sorted(n for n in dir(app.cappe.models.cappe) if not n.startswith('_'))` before/after — after must be a superset.
- **Test**: CAPPE (shim covers `test_cappe_hosting.py`, `test_cappe_offerings.py`, `test_merlin_validation.py`).

### Commit 3 — `services/merlin/` package move

- **`git mv`** into `services/merlin/`, dropping the prefix: `merlin.py→turn.py`, `merlin_agent.py→agent.py`, `merlin_ops.py→ops.py`, `merlin_apply.py→apply.py`, `merlin_catalog.py→catalog.py`, `merlin_store.py→store.py`, `merlin_router.py→routing.py`, `merlin_attachments.py→attachments.py`.
- **Create** `services/merlin/__init__.py`: docstring only, **no eager re-exports** (would re-tighten the turn↔routing cycle); importers use submodule paths.
- **Intra-package import fixes** (sibling `.merlin_x`→`.x`; out-of-package `.y`→`..y`):
  - `turn.py`: `..design_gate`, `.attachments`, `.catalog`; **keep** `from .ops import MERLIN_OPS, OP_NAMES, validate_ops  # noqa: F401`.
  - `agent.py`: `..browser_pool`, `..design_gate`, `..image_quota`; `.turn`, `.apply`, `.attachments`, `.catalog`, `.ops`.
  - `ops.py`: `.catalog` (module-level AND the second function-local import inside `build_merlin_schema`), `..section_presets`, `..style_recipes`, `..theme_presets`.
  - `apply.py`: `.catalog`, `..theme_presets`. `store.py`: `..common`. `catalog.py`: `..design_registry` (keep its noqa re-exports).
  - `routing.py`: `..design_gate`, `.catalog`; the lazy import becomes `from .turn import resolve_model_tier` — **must stay function-local**.
- **External importer updates**:
  - `routes/merlin.py`: submodule paths (`..services.merlin.turn` etc.); the module-attribute style becomes `from ..services import cappe_assets` + `from ..services.merlin import store as merlin_store` (call sites `merlin_store.xxx` unchanged).
  - `routes/uploads.py`: `..services.merlin.catalog`.
  - Tests: mechanical rewrite `app.cappe.services.merlin_X` → `app.cappe.services.merlin.X` and `services.merlin import/from` → `services.merlin.turn`. Find ALL via `grep -rn "services\.merlin" server/app server/tests server/scripts` — **including string literals** (monkeypatch `setattr("app.cappe.services.merlin_agent…")` targets), not just import statements.
- **Test**: `pytest tests/cappe/test_merlin_*.py -q`, then CAPPE; grep check above returns no stale paths.

### Commit 4 — Extract merlin agent SSE orchestration (item 6c)

- **Create** `services/merlin/agent_stream.py`: move the ~210-line SSE generator body from `routes/merlin.py:merlin_agent` (lines ~414–623) into `async def stream_agent_turn(...) -> AsyncIterator[str]`; parameters = the closure's free variables (enumerate at implementation time). Route keeps auth/ownership (`get_owned_site`), request validation, rate limits, tier resolution, and returns `StreamingResponse(stream_agent_turn(...), media_type="text/event-stream")` with identical headers. `HTTPException`s raised before first yield stay in the route; mid-stream error frames move with the generator (already emitted as SSE data frames — behavior-identical).
- Tests that reach `routes/merlin.py` privates (`_resolve_conversation`, `_parse_page_id`, `_recent_history_tail`, `_MAX_SNAPSHOT_BYTES` — test_merlin_validation, test_merlin_conversations) are untouched: those helpers stay in the route file.
- **Test**: `pytest tests/cappe/test_merlin_agent.py tests/cappe/test_merlin_turn.py tests/cappe/test_merlin_conversations.py -q`, then CAPPE.

### Commit 5 — Fat public-endpoint extractions (items 6a + 6b)

- **6b first — booking slot resolution**: move `_resolve_booking_slot` (public.py:264–372) to `services/slots.py` as public `resolve_booking_slot(...)`; move `_anchor_local` (line 253) with it iff grep confirms it has no other caller. Note slots.py is currently DB-free/pure — keep the pure functions (`generate_slots`, `merge_any_staff_slots`) untouched so `test_cappe_slots.py` / `test_cappe_staff_slots.py` stay DB-free; the new async function is additive.
- **6a — order creation**: extend `services/commerce.py` (currently owns `order_subtotal`/quote math) with `async def create_public_order(conn, site, body: CappeCheckoutRequest, background) -> dict`: moves cart validation + option pricing, inventory decrement + `_inv_log`, booking-line creation (calls `resolve_booking_slot`), Stripe Checkout session creation, and email fan-out scheduling verbatim from `public_create_order` (public.py:401–658). Route keeps: rate limits, `_reject_reserved`, `_published_site` lookup, response envelope. `HTTPException` raising moves into the service unchanged (repo precedent: `get_owned_site` raises from a shared helper — don't invent a domain-error type here). `from ..models.cappe import CappeCheckoutRequest` in the service is valid via the commit-2 shim.
- **Test**: `pytest tests/cappe/test_cappe_commerce.py tests/cappe/test_cappe_slots.py tests/cappe/test_cappe_pricing.py tests/cappe/test_cappe_offerings.py tests/cappe/test_cappe_email_payloads.py -q`, then CAPPE.

### Commit 6 — `routes/public.py` → `routes/public/` package

Now ~1,000 lines after commit 5. Follow the `ir_incidents/` package precedent.

- **Create** `routes/public/`:
  - `_common.py`: file-header docstring + shared helpers `_published_site`, `_reject_reserved`, `_recipient_send_ok`, `_read_rate_limit`, `_site_today`, `_site_rate_rules`, `_location_ctx`, `_site_rider`, `_active_discounts`, `_validate_intake`, `_active_staff_for_type`, `_booking_by_token`, `_booking_can_modify` + their imports (incl. `_site_owner` from `.._shared`).
  - One module per existing banner, each with its own `router = APIRouter()`: `site.py` (render data), `shop.py` (products/orders/receipts), `newsletter.py`, `forms.py`, `reviews.py`, `bookings.py` (locations/staff/types/rider/availability/slots/create/quote), `booking_selfserve.py` (token-gated view/cancel/reschedule), `messages.py`, `blog.py`. Split strictly at the banner lines (181 / 208 / 739 / 781 / 832 / 864 / 1163 / 1323 / 1390 of the pre-commit-5 file — recompute after commit 5).
  - `__init__.py`: `router = APIRouter()` + `include_router` per submodule, **plus** `from ._common import _validate_intake  # noqa: F401` (test_cappe_offerings imports it from `app.cappe.routes.public`).
- Use `git mv routes/public.py routes/public/bookings.py` (largest surviving chunk) so history follows; carve the rest out.
- `routes/__init__.py` needs zero edits (`from .public import router` resolves against the package).
- **Test**: `pytest tests/cappe/test_cappe_offerings.py tests/cappe/test_cappe_slots.py tests/cappe/test_cappe_commerce.py tests/cappe/test_cappe_hours.py -q`, then CAPPE.

### Commit 7 — `services/render.py` → `services/render/` package (Python split only)

- **Create** `services/render/`:
  - `sanitize.py`: `_uid`/`_uid_counter`, `_esc`, `_safe_href`, `_safe_image`, `_js_obj`, `_clean_css`, `_hexonly`, `_clampi`, `_anchor_id` + `_ANCHOR_RE`, `_safe_url_css`, `_cv_safe_id`, `_num`.
  - `design.py`: design constants (`_RADIUS`, `_LIGHT`, `_DARK`, `_PAD_SCALE`, `_MAXW`, `_MINH`, `_MOTION_FX`, `_HOVER_FX`, `_LOOP_FX`, `_HEADING_FX`, `_EASING`, `_OVERLAYS`, `_IMG_FILTER_FX`, `_BG_PATTERNS`, `_DIVIDER_PATHS`, `_CONTAINER`, `_GUTTER`, `_LINEHEIGHT`, `_SEC_PAD`, `_CARD_BORDER`, `_GRID_GAP`, `_RESP_BREAKPOINTS`, `_SERIF`, `_HEX_RE`, `_SECTION_RE`) + `_design_color`, `_style_vars`, `_design_motion`, `_block_has_motion`, `_emit_design_group`, `_responsive_layout_style`, `_apply_design`, `_design_gradient`, `_font_stack`, `_tokens`, `_gfonts_link`, and `_BASE_CSS` (for now). Keeps `from ..design_registry import DESIGN_COLOR_TOKENS, DESIGN_KEYS_BY_GROUP`.
  - `blocks.py`: `_btn`, `_fattr`, `_head`, all block renderers (`_hero`…`_credentials`, `_reviews`, `_store`, `_booking`, `_newsletter`, `_contact`, `_map`, `_hours`, `_canvas`), `_widget_runtime`, the JS constants (`_STAGGER_SEL`, `_MOTION_JS`, `_CANVAS_JS`, `_STORE_JS`, `_BOOKING_JS`, `_NEWSLETTER_JS`, `_CONTACT_JS`, `_REVIEWS_JS`, `_OPENNOW_JS`), `_DAY_NAMES`, `_resolve_loc`, `_CV_COLS_MAX`/`_CV_SPAN_MAX`, `_render_block`.
  - `page.py`: `_head_seo`, `_local_business_ld`, `_footer`, `_promo_link`, `_promos`, `_PROMO_JS`, `render_site_html`.
  - `__init__.py`: `from .page import render_site_html  # noqa: F401` **plus explicit re-binds of every test-crossed private name**:
    ```python
    from .design import _BASE_CSS, _EASING, _LOOP_FX, _DIVIDER_PATHS, _emit_design_group, _tokens  # noqa: F401
    from .sanitize import _anchor_id  # noqa: F401
    from .blocks import _render_block  # noqa: F401
    ```
- `git mv services/render.py services/render/blocks.py` (largest fragment) for history; carve the rest.
- Zero importer edits: in-app files import only `render_site_html`; the 13 render test files are covered by the `__init__` re-binds (incl. `R._render_block`/`R._tokens` attribute access).
- **Test**: `pytest tests/cappe/test_design_registry.py tests/cappe/test_render_decorative.py tests/cappe/test_render_motion.py tests/cappe/test_render_responsive.py tests/cappe/test_render_typography.py tests/cappe/test_canvas_render.py tests/cappe/test_cappe_design_tooling.py tests/cappe/test_cappe_render_blocks.py tests/cappe/test_cappe_render_canvas.py tests/cappe/test_cappe_render_meta.py tests/cappe/test_style_recipes.py tests/cappe/test_section_presets.py -q`, then CAPPE.

### Commit 8 — Render CSS/JS → real asset files

- **Create** `services/render/assets/` and move blob **bodies** (Python keeps the `<style>`/`<script>` wrapper tags and constant names):
  - `base.css` ← `_BASE_CSS` (pure static, ~575 lines)
  - `canvas.css` + `canvas.js` ← `_CANVAS_JS` (mixed `<style>…</style><script>…` — split the two bodies)
  - `store.js`, `booking.js`, `newsletter.js`, `contact.js`, `reviews.js` ← their `r"""` constants (they contain `__ID__` placeholders replaced per-render — the placeholder text just lives in the file)
  - `opennow.js` ← `_OPENNOW_JS`; `promo.js` ← `_PROMO_JS`; `runtime.js` ← the `_widget_runtime()` bootstrap (verified pure static)
  - `motion.js` ← `_MOTION_JS`, **with a `__STAGGER_SEL__` placeholder** substituted at import time from the Python `_STAGGER_SEL` constant (the only blob that interpolates a Python value)
- **Loading rule** (import-time, once): `_ASSETS = pathlib.Path(__file__).parent / "assets"`; `_BASE_CSS = (_ASSETS / "base.css").read_text(encoding="utf-8")`. All constants keep their exact names as module-level strs — mandatory for `_BASE_CSS` (`test_render_motion.py` imports it as a str); commit-7 `__init__` re-binds keep working.
- **Byte-identity guard**: before the change, print `hashlib.sha256(const.encode())` for each blob via throwaway `python3 -c`; after, assert the file-loaded constants hash identically (watch leading/trailing newlines from `"""` blocks; extraction removes the raw-string escaping footgun rather than adding one).
- Assets ship automatically (Docker copies the whole app dir); no packaging config needed.
- **Test**: commit-7 render subset, then CAPPE, then the branch-closing full run: `cd server && python3 -m pytest tests/ -q` (covers `tests/test_scoped_auth.py`).

## Verification

Per-commit: targeted pytest subset + full `tests/cappe/` (must be green at every commit boundary). Branch-closing:

1. `cd server && python3 -m pytest tests/ -q` — full suite (known pre-existing collection failures listed in `server/CLAUDE.md` are the only tolerated reds; compare against a pre-branch baseline run).
2. Import-surface checks:
   - `python3 -c "from app.cappe.models.cappe import CappeSiteUpdate, CappeProductCreate, CappeMerlinChatRequest, normalize_custom_domain"` (shim superset guard from commit 2).
   - `python3 -c "from app.cappe.services import render as R; R._render_block; R._tokens; R._BASE_CSS"`.
   - `grep -rn "merlin_ops\|merlin_catalog\|merlin_apply\|merlin_store\b\|merlin_router\|merlin_attachments\|merlin_agent" server/app server/tests server/scripts` → only the `store as merlin_store` alias in routes/merlin.py remains.
3. Render byte-identity: sha256 comparison of all extracted CSS/JS constants (commit 8 guard) + eyeball one `render_site_html` output diff before/after the branch via a small fixture script (the render tests already assert on emitted HTML fragments).
4. App boots: `cd server && python3 -c "from app.main import app"` (exercises router aggregation incl. the new `routes/public/` package).

## Risk notes

- `routing.py`'s lazy `from .turn import resolve_model_tier` must stay function-local (documented turn↔routing cycle breaker).
- Grep for monkeypatch **string targets** (`"app.cappe.services.merlin_…"`) in commit 3, not just import statements.
- Do NOT merge `_num` / `_canvas_elements` "duplicates" — verified different semantics.
- `services/slots.py` pure functions stay pure (DB-free tests); the moved resolver is additive.
- Every commit is pure-Python/asset moves — no DB, no alembic, no deploy surface.

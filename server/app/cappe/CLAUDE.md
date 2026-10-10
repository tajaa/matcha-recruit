# Cappe backend

Website builder + domain reselling for the consumer brand **Gummfit** (gummfit.com). Own product — not a matcha tenant. See root `CLAUDE.md`'s "Repo layout — products map" and "Custom products" sections for where this fits among the other products; this file only covers what's specific to working inside `server/app/cappe/`.

For domain-reselling ops (Porkbun, Stripe platform account, go-live checklist), see `DOMAINS.md` in this directory — don't duplicate that content here.

## Identity & boundary

- Own identity model: `cappe_accounts` table, JWT `scope=cappe`. **Not** `users`/`companies` — no tenant model shared with Matcha.
- Mounted at `/api/cappe` (+ an unprefixed tenant renderer on `*.gummfit.com`).
- **Import rule**: `cappe/` imports only from `app/core/*` (shared db pool, email, storage, auth, redis). Verified 2026-07-27: `cappe → matcha` is 0 edges. Don't add one — grep the root CLAUDE.md's cross-product import rule before reaching for a matcha service.

## Layout

- `routes/` — HTTP layer
- `services/` — business logic (Porkbun client, Stripe Connect, site rendering, etc.)
- `models/` — Pydantic shapes
- `dependencies.py` — `scope=cappe` JWT auth dep

## Frontend pairing

Paired frontend lives at `client/src/cappe/` (own `CLAUDE.md` there).

## AI models (Admin → Settings → AI models)

Gummfit is one app on the Matcha platform admin's *AI models* page (registry
`app/core/services/agent_surfaces.py`, `GUMMFIT_*`). Merlin's single-step turn
(`merlin/turn.py`), the Merlin Auto classifier (`merlin/routing.py`), directory
inference (`services/directory.py`) and booking suggestions
(`services/booking_suggestions.py`) call `core.anthropic_messages.generate_content_routed`
with their surface: Gemini while the row is built-in, the same request on Claude
when it names a model. Each keeps its own timeout (the classifier's 6s, booking's
12s); a Merlin tier then sets Claude's effort (lite low, regular medium, max high).
A Claude call counts in the `anthropic` rate-limit bucket under the same label, so
each site skips its Gemini `record_call` when `ran_on_claude(response)`.

Still Gemini-only: Merlin's multi-step agent and setup agent (Gemini tool loops
with `thought_signature`; a follow-up moves them onto a core Claude session) and
image generation (`core/services/image_gen.py` — Claude can't produce images).
Model ids come from `core/services/model_catalog.py`; the Merlin tiers, classifier
and directory used to hard-code the 3.7 Flash Lite id, which that catalog records
as unavailable, and `tests/test_model_catalog.py` no longer exempts Cappe.

## Cross-cutting rules

DB safety rules, test-data email domain rules, and deploy rules are in root `CLAUDE.md` — they apply here unchanged, not restated.

## Ops invariants (2026-09 audit)

- **Every scheduled Cappe task needs three things or it silently never runs:** its module in
  `workers/celery_app.py` `include` (Celery builds the consumer's strategy map *before*
  `worker_ready` fires, so a module imported lazily at dispatch time is "unregistered" and the
  message is dropped), a `_SCHEDULED_TASKS` entry, and a `scheduler_settings` row seeded by a
  migration (`zzzzcappe30`/`zzzzcappe31` are the shape — the admin UI can toggle rows but never
  inserts them). `tests/workers/test_celery_scheduler_dispatch.py` pins the first two.
- **Custom domains are served through CloudFront distribution tenants, not the EC2 directly.**
  `cappe_sites.custom_domain` is written only by `cappe_edge_sync` once the tenant's managed
  certificate is `live`; registration/verification only sets `cappe_domains.edge_status`.
  Feature is gated by `CAPPE_CUSTOM_DOMAINS_ENABLED` until the AWS side in
  `docs/ops/CAPPE_CUSTOM_DOMAINS.md` exists. Flow + runbook: `DOMAINS.md`.
- **Consumer PII lives in Cappe's own tables** — `scripts/sql/anonymize_dev.sql` block 8 scrubs
  them and `refresh-dev-from-prod.sh` gates on them; a new email/token column on a `cappe_*`
  table must be added to both.
- **Money-path webhooks gate on `payment_status == "paid"`** (`routes/payments.py`,
  `routes/domains.py`); `async_payment_succeeded/failed` and `session.expired` are handled and the
  abandoned-order reaper (`cappe_order_reaper`) is the backstop for restocking.

## Payments invariants (2026-10 review) — runbook: `docs/ops/CAPPE_PAYMENTS.md`

- **Every refund is a row in `cappe_order_refunds`, and `refunded` is reached only by
  `refunds.apply_refund`** settling the refund that brings the refunded total to the order total.
  The dashboard writes the row `pending` (with the owner's restock choice) BEFORE calling Stripe;
  `charge.refunded` (`refunds.sync_stripe_refunds`) applies a covered pending row with that choice
  and records anything beyond as a Stripe-dashboard refund. The status PATCH refuses `refunded`.
  Never add a path that writes the status without the money moving.
- **Order status changes go through `order_lifecycle.ALLOWED_TRANSITIONS`.** No cycle may pass
  through a restock; `cancelled` / `refunded` / `declined` are terminal.
- **Close the Stripe page before releasing or settling anything by hand** — storefront orders
  (`_close_open_checkout`), collab installments (`_close_collab_sessions`), domain purchases
  (`reap_abandoned_purchase`). A released row with a payable page is a customer charged for nothing.
- **A collab session settles an installment only if it is the one WE created for it**
  (`_collab_reject_reason`: stored session id + amount + currency). Session metadata is written by
  whoever created the session, and the connected account is the creator's own. Anything else that
  settles is refunded (`_refund_unapplied_collab_charge`).
- **No Stripe call inside a DB transaction.** `sync_subscription` raises
  `DuplicateLiveSubscription`; `sync_subscription_tx` resolves it after the connection is released.
- **A refused CARD is `CappeStripeCardError`; anything else is ours.** Only the first may count
  against a customer (dunning, lapse). `charge_off_session` must be given a payment method id.
- **Discount rounding is integer half-up on both sides** (`discounts.apply_discount_cents` and
  `render/assets/store.js`) — `test_cappe_checkout_failure.py` pins the two expressions together.
- **A failed attempt to take a card is an error, never a fallback to the unpaid flow**
  (`commerce.create_public_order` → `release_unpaid_order` + 502).

## Shipping and currency (2026-10, `services/shipping.py`)

- **A physical order's payment page takes an address only in the country it was priced for**
  (`cappe_orders.ship_country` → Stripe `allowed_countries=[ship_country]`). Shipping and tax are
  per destination; widening the list lets a buyer pay home rates and ship abroad.
- **The home country's rates are the site's own columns** (`shipping_*`, `tax_rate_bps`); zones
  (`cappe_shipping_zones`, plan feature `shipping_zones`) add other countries. No zones = home only.
  Subscriptions ship home only (their shipping is fixed into the Stripe price).
- **One store, one currency** (`cappe_sites.currency`, two-decimal allowlist `SITE_CURRENCIES`,
  mirrored in the migration and `client/src/cappe/utils/countries.ts`). Products take it on create
  and follow it on change; a change is refused while subscriptions are billing.

- **A promo code applies to lines with no automatic discount, split pro rata before tax**
  (`promos.allocate`, each line's `promo_discount_cents`). `cappe_orders.subtotal_cents` is AFTER
  the code (fees and refunds use it); a discounted line goes to Stripe as one item at its
  discounted total — never a negative line. Uses are counted under the code's row lock and given
  back in `inventory.release_order_bookings`, and taken again by `retake_order_stock` when a
  released order is paid after all. Lock order: product rows, then the CODE row, then its
  redemption (`_move_promo_use`) — a code delete cascades code→redemption, so never the
  reverse. An order with nothing to pay is created `paid`, or becomes `paid` when accepted if it
  waited for approval — no payment will ever settle it. Subscriptions
  refuse codes.

- **Web shoppers keep the refresh token in the `__Host-cz_shopper` cookie only** (host-only,
  HttpOnly, Secure, SameSite=Strict; `routes/public/shopper_web.py`). It is never in a response body
  or page storage; cookie endpoints also require `X-Cappe-Web: 1`. Web sign-out deletes that one
  session — the app's `/auth/logout` revokes every session and device, so never point the web at it.
  Every session mutation takes the shopper row lock first (refresh, both logouts), and rotation
  only UPDATEs its row — a refresh must never re-create a session a sign-out deleted. A refresh
  token the session already rotated past raises `StaleRefresh`: 401 WITHOUT clearing the cookie
  (it's a racing tab; the browser now holds the newer one). `account.js` runs one refresh at a
  time (per page, and across tabs via Web Locks).
- **A store that closes to shoppers still lets the people it bills in** (unpublished, owner
  inactive, plan without shopper accounts): `shopper_auth.sign_in_site` / `session_site` let a
  subscriber sign in and refresh, and only the `require_shopper_session` endpoints (list, cancel)
  serve them. Purchases keep `published_shopper_site`. Codes go only to `subscribes_here` emails;
  `/auth/start` stays 204 either way.

## Site templates (`services/site_templates/`)

- **The catalog is code, not the `cappe_templates` table.** One `SiteTemplate` per entry, one module
  per Discover category (`food_drink.py`, `beauty_grooming.py`, …), aggregated in `__init__.py`.
  `routes/templates.py` and `POST /sites/from-template` read the registry; `cappe_templates` and
  `cappe_sites.template_id` are inert (dropping them is its own approved migration). A site records
  the registry key in `cappe_sites.template_slug` (`zzzzcappe37`). The hand-run
  `scripts/seed_cappe_templates.py` is gone — nothing needs seeding.
- **Every template is available on every plan; nothing is priced per template.** Templates are the
  free plan's path to a finished site — Merlin's agent loop is the paid one. Author a template
  COMPLETE (premium keys, `_design` bags included) and make sure it looks finished without them:
  `clone_structure` runs the same `gate_theme`/`gate_content` the editor's save path runs, so a free
  clone is exactly what the editor keeps and a paid clone gets the polish. The old clone copied
  everything and shipped effects that vanished on the first save.
- **`tests/cappe/test_site_templates.py` is the drift gate** — every block through the real
  `add_block` validation with nothing filtered, every page rendered gated AND ungated, every
  Discover category covered, ≥40% light mode, internal links resolve, no third-party hosts, no
  invented facts (years, "Est."), `{{business_name}}` on every home page. Run it after touching a
  block field, a design key, the directory taxonomy, or a template.
- **Imagery never comes from outside our origin.** Slots are manifest keys (`imagery.py`); until
  `scripts/cappe_template_imagery.py` has generated a photo (same Gemini image model + S3/CloudFront
  as owners' images; URLs land in the committed `imagery_urls.json`) the slot shows the
  deterministic placeholder tile from `GET /templates/placeholder/{key}.svg`. That route REDIRECTS
  to the photo once it exists, so a site cloned early (which stored the placeholder path) upgrades
  on its own — keep its cache short and never `immutable`. Off-origin renders (Merlin's about:blank
  screenshots) must pass their HTML through `imagery.inline_placeholders`.
- **The preview route sets `tenant_security_headers()` itself.** It is only ever shown in an
  iframe; without a handler-set CSP `main.py:add_security_headers` stamps `frame-ancestors 'none'`
  on it and the gallery draws blank. `test_preview_survives_the_real_security_middleware` pins it.
- **Previews are memoised per (slug, page, premium)** and browsable (`?page=` links rewritten), so
  the gallery's N cards cost N dict lookups; the rate limit only has to stop a scraper.


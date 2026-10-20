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

## Admin plan changes and signup grants (2026-10, `routes/matcha_admin.py`)

- **Matcha's `/admin/cappe` reaches Cappe through `/api/cappe/matcha-admin/*`**, gated at the mount
  by core's `require_admin` (cappe → core is the allowed direction). It lives here, not in
  `core/routes/admin/`, so plan changes go through `billing.grant_comp` / `end_comp` rather than a
  copy in core. `/admin/*` on this router is the in-Cappe platform admin, a different auth realm.
- **Every plan an admin gives is a comp, never a charge.** Free = `end_comp`; any other plan =
  `grant_comp` with an optional `comped_until` (timezone required). Both refuse (409) an account
  with a live Stripe subscription: change those in Stripe. Both take the account row lock, so comp
  writers on one account run in turn; a webhook-recorded subscription racing them is a 409.
- **A signup grant (`cappe_signup_grants`, `zzzzcappe48`) is a link, `/cappe/signup?grant=<token>`.**
  Signup records it on the account (`signup_grant_id`); confirming the email redeems it
  (`services/signup_grants.redeem`: account row locked, then the grant row; capacity, revocation
  and the plan still being on sale judged then, link expiry judged at signup time) into a comp
  ending `days` later, or records why not in `signup_grant_refused` (an account that already holds
  a plan is never overwritten). **Every path that confirms an account redeems, in the same
  transaction as the confirmation:** `/auth/verify`, `/auth/reset-password` (it confirms too, and
  clears the verification token) and auto-verified signup. A new confirming path must do the same.
  A failed redemption rolls back its savepoint alone and never fails the confirmation.
  `unusable_reason` is the one rule for the lookup, signup and redemption. `cappe_comp_expiry`
  must stay ON or a "30 days free" grant never ends (`zzzzcappe48` turned it on).
- **Subscribing to the comped plan during its comp bills from the comp's end**
  (`billing.comp_trial_end(sub, plan_code)` → Stripe `trial_end`, no $1 intro), so keeping it early
  never costs the free days. Any OTHER plan bills at checkout: deferring every plan turned a comp
  on a cheap plan into free time on the top one. Also at checkout: no end date, or an end outside
  Stripe's 49 h–729 d window. The billing page reads `CappeSubscription.comp_bills_from` rather
  than re-deriving this. `change_plan` keeps such a trial for an interval switch on the same plan
  (`trial_is_from_comp`: no intro redemption on the subscription) and ends it for a tier switch.
- **`models/billing.CappePlanCheckoutRequest` is not `models/shop.CappeCheckoutRequest`.** The
  `models.cappe` shim star-imports every module, so one name in two modules resolves to the last
  one imported; that sent the cart model to `/billing/checkout` and 422'd every plan purchase.
  `test_no_two_model_modules_export_the_same_name` guards it.

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
- **A destination may offer delivery options** (`cappe_shipping_rates`, `zzzzcappe52`, zone_id NULL =
  home; same `shipping_zones` plan gate): `ship`, `pickup`, `local_delivery`, priced by
  `shipping.rate_price` — amount + per extra item + the products' `shipping_surcharge_cents`, free
  over an amount, offered only inside its value/weight bands. No rows = the flat rate, presented as
  the one option `"flat"`; the first option is the default. **One rule for both:** the flat rate is
  priced by the same `rate_price` (`compute_shipping_cents` is gone), so a quote and its order
  cannot disagree. `ships_free` products never count; goods of 0 never pay delivery.
- **The quote falls back to the default; the order refuses** (`choose_option(strict=True)`: 409 for
  an option it no longer gets, 422 when none fits) — never a silent reprice. The order stores what
  was chosen as it was (`shipping_rate_id` without FK, method, label, estimate, pickup
  instructions); the order page, receipt and Pay now read those, not the live rate.
- **Stripe asks for an address only for `ship`.** Pickup stores none; local delivery is offered
  only once the bag sends a postal code (`postal_matches` is False without one, area or not), so its
  typed address is the one priced, and Stripe gets the fee as a line item instead of a shipping
  option. An app that sends no option and no address is therefore never defaulted onto one.
- **Rates are saved with zones** (`PUT /sites/{id}/shipping-zones`, `rates` per zone + `home_rates`).
  Zones are replaced as a set, so their ids change: options left out (`None`) are re-inserted, a
  zone's by its name. Estimates are the store's `handling_days_*` plus each option's transit days.
- **Tax is on top or inside the price, never both** (`cart.tax_in`, `zzzzcappe53`). The site's
  `prices_include_tax` makes `tax_cents` the part of the price that is tax (`amount*bps//(10000+bps)`)
  and the total subtotal + shipping; `tax_on_shipping` taxes shipping at the same rate
  (`shipping_tax_cents`). A zone that charges tax uses its own `tax_rate_bps`, else the store's; one
  that doesn't charges none, inclusive prices or not (the price stays as listed). Both flags ungated.
- **An order and a subscription keep how they were priced** (`tax_included`, `shipping_tax_cents`;
  renewals copy the subscription's). Everything that reads an order honours it: no Stripe tax line
  when included (the lines are the total), the receipt, order page, owner view and bag say
  "Includes VAT" under the total, and finances use `_GOODS_NET` / `_SHIPPING_NET` so goods + tax +
  shipping = total. **The platform fee is on `cart.goods_net_cents`** — never the inclusive subtotal.

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

## Variants and what a plan sells (2026-10, `services/variants.py`, `zzzzcappe50`)

- **A variant is one option from each VARIANT GROUP — a required, single-pick group** (Size ×
  Colour) — with its own stock, SKU, price and picture (`cappe_product_variants`, `option_ids`
  sorted by uuid text). Optional groups and add-ons stay plain options. A selection with no variant
  row behaves exactly as before variants existed.
- **The stock rule every path follows** (checkout, `restock_order`, `retake_order_stock`, the bag's
  availability): a matched variant owns the stock of the options it is made of — their own option
  stock never moves for that sale; options outside it (an add-on) move theirs; the product's own
  stock, when tracked, is the total. Use `variants.uncovered_option_ids`, never the raw selection.
- **An order line records what it took**: `variant_id` (bought), `decremented_variant_id` (stock
  taken, NULL = untracked), `sku` (sold under). A line with `stock_decremented` set is recorded; an
  unrecorded one (a renewal line before `retake_order_stock`) has only `variant_id`, and its options
  exclude the variant's (`inventory._line_option_ids` joins `variant_option_ids`).
- **Lock order: products → variants → options**, each in id order (`inventory.lock_stock_rows`).
- **A variant row's combination never changes.** `replace_variants` pairs by id only when the id
  still names the same combination, else by combination; anything unclaimed is deleted, and
  `prune_variants` drops every variant that no longer fits the groups an option save leaves (a
  deleted option, a group made optional or pick-many, a variant group added since). The editor
  sends `{group, option}` NAMES so options created in the same save can carry variants; `variants`
  omitted = leave them, `[]` = none.
- **Checkout asks the plan about every line** (`entitlements.sells`), not only the editor's create /
  kind-change gate: a store whose plan stopped selling a kind (downgrade, lineup change) can't sell
  it. The public listing and `/quote` drop those products. Since `zzzzcappe50` Free sells digital,
  service and booking only; Creator sells all four. `GET /billing/entitlements` is what the
  dashboard reads instead of hard-coding plan names.
- **The Storefront app's required keys are a contract** — `tests/cappe/test_cappe_variants.py`
  reads them out of `platforms/ios/Storefront/Sources/Models.swift`; add fields, never rename or null them.

## Product pages and the store's own SEO (2026-10, `services/product_pages.py`, `zzzzcappe51`)

- **A product lives at `/shop/<slug>` on its store** (`routes/render.py:product_page`,
  `services/render/product_page.py`): server-rendered name, price, pictures, description, its own
  title/canonical/Open Graph (`render_site_html(seo=…)` → `_head_seo` override) and Product
  JSON-LD (`product_pages.product_ld`, Offer or AggregateOffer for differently priced variants).
  store.js then fills the same panel in place (`data-product`). Active products the plan sells
  only. `/shop` is the linked catalog crawlers read.
- **The slug is made from the name once and survives renames** (`assign_slug`); only an owner's
  explicit `slug` changes it, and a taken one is a 409, never a quiet `-2`. Every insert path must
  call `assign_slug` (owner create, Merlin `create_product`); a NULL slug simply has no page.
- **Pictures are `cappe_product_images` in order; `cappe_products.image_url` mirrors the first**
  for everything that reads one column (both apps, receipts, directory). `images` sent →
  `replace_images` decides the cover; only `image_url` sent (the apps, Merlin) → `set_cover`.
- **JSON-LD escapes every `<`, `>`, `&`** (`\u003c`…), not just `</`: owner text with `<!--` +
  `<script` would otherwise stop our real `</script>` from closing the element.
- **Product pages, the catalog and the sitemap are cached per site** (`cappe:render:{site}:…`);
  every product write calls `invalidate_site_render_cache`. Sales don't, so a page's stock and
  availability can lag by the 300 s TTL.
- **A store answers its own `/robots.txt` and `/sitemap.xml`** (`render.tenant_seo`). Matcha's SEO
  routes (`core/routes/content/sitemap.py`) are mounted first and used to give every store
  Matcha's files; they now ask `register_host_seo` hooks first, and `main.py` registers Cappe's.
  A store that isn't published answers `Disallow: /`.

## Policies, the seller on receipts, mail as the store (2026-10, `zzzzcappe54`)

- **A store's policies are `cappe_site_policies`** (refund, shipping, terms, privacy; plain text,
  `services/policies.py`), served at `/policies/<kind>`, linked from the footer (`_site_dict(site,
  kinds)` → `site["policies"]`, also `window.__CAPPE__.policies` for the bag), the sitemap, the bag
  and Stripe's page. No row = no page. Every write drops the store's render cache.
- **Checkout points at the terms; it does not ask Stripe to collect consent.** Stripe's
  `consent_collection.terms_of_service` refuses to open a page unless the CONNECTED account has its
  own terms URL in its own Stripe settings — it would break a seller's checkout. The bag says "By
  placing your order you agree to…" and Stripe's page shows `policies.checkout_note` as
  `custom_text.submit`. `collect_phone` turns on `phone_number_collection`.
- **Selling physical goods requires the refund and shipping policies to publish**
  (`readiness`'s `policies` item, `policies.REQUIRED_FOR_PHYSICAL`). Payments, shipping, tax,
  identity and product pictures are nudges, shown only when they apply.
- **Receipts name the seller** (`legal_name`, `business_address`, `tax_id` → "VAT ID: …"), **frozen
  onto the order when the receipt is numbered** (`cappe_orders.seller_*`, `assign_receipt_number`):
  receipts render on demand, so without it an old receipt showed a changed VAT number. **And the
  buyer's billing address** (`cappe_orders.billing_address`, from Stripe's `customer_details` in
  `_mark_order_paid`; scrubbed by `anonymize_dev.sql`).
- **Mail to a store's buyers is sent as the store and replies reach it**: `email.store_from_name`
  ("Lumen via Gummfit", address-list characters stripped — it goes into a From header) and
  `email.store_reply_to` (the store's `meta_config.contact_email`, else the owner's login), through
  core's `send_email_with_fallback(reply_to=)` (Gmail `Reply-To` header, MailerSend `reply_to`;
  `client.clean_reply_to` drops anything but one plain address). Orders, the paid receipt and
  subscriptions do this; owner alerts stay "Gummfit". Booking mail to customers doesn't yet.
- **Merlin's `create_product` takes `inventory`/`sku`/`weight_g`**; a physical product with no
  `inventory` key (nobody said the stock) is created a draft — `null` means made to order.

## Social growth (2026-10, `services/social/`, migrations `cappesocial01`–`03`)

Owners connect the Instagram business account and Facebook Page they already run, drop photos
into a composer (one carousel post, or one post per photo spread across days), schedule or post
now, and answer comments/DMs from an inbox where Claude Haiku 5.5 drafts replies. Owner routes
`routes/social.py` (`/sites/{id}/social/*`); Meta's OAuth callback + webhook are public in
`routes/public/social_meta.py`; page `client/src/cappe/pages/site/Social/`.

- **One Meta app, two networks.** Facebook Login yields a Page token per Page; the Page's
  Instagram account is addressed with the same token. `providers/meta.py` is the only module that
  speaks Graph; everything else uses `providers/base.py` shapes. A new network is a new provider
  module plus one line in `providers/__init__.py:_PROVIDERS`.
- **Tokens are Fernet-encrypted at rest** (`core.services.secret_crypto`) and decrypted only by
  `connections.credentials()` for a call about to be made. `PUBLIC_COLUMNS` never includes
  `access_token_enc`. A Graph token error (190/102) marks the connection `expired` ("reconnect").
- **Connect is bound to the browser that started it.** The OAuth `state` is HMAC-signed (JWT
  secret), expires in 15 min, and carries a nonce the start response sets as an HttpOnly,
  `SameSite=Lax` cookie scoped to the callback path. Without the cookie match, an owner could send
  someone the Facebook link and land that person's Pages on their own site. The cookie is set on
  the host the dashboard calls and the redirect URI is built from `CAPPE_BASE_DOMAIN`, so Connect
  works only from a dashboard served on that host (the same assumption `dashboard_url` makes).
- **Publishing is per target.** A post is the composition; a target is that post on one
  connection. `cappe_social_publisher` sweeps every minute (self-re-enqueue + `last_run_at` claim,
  the `schedule_break_reminders` shape) and claims due targets `FOR UPDATE SKIP LOCKED`; "Post now"
  dispatches `run_cappe_social_publish_post` for one post. Retryable failures back off
  2/10/30 min, three attempts; the post's status rolls up from its targets
  (`posts.rollup_status`).
- **Replies: deterministic first, model second, owner's mode last** (`autoreply.py`). The
  hard-stop list (refunds, disputes, legal, injury/allergy) and the owner's escalate words run
  before any model call and can only ever escalate. The draft is grounded ONLY on the store's
  active catalog, contact details and the owner's notes, and must set `needs_human` rather than
  guess. `auto` sends by itself only for plain-question intents at confidence ≥ 0.75 under the
  hourly cap; everything else is a draft to approve. Before an automatic send, `reply_guard`
  (deterministic, after the model) holds any reply with a link off the store's own site, contact
  details that aren't the store's, or a hard-stop subject — a commenter can't plant one through
  the prompt. A partial post's "Post now" re-tries only its unpublished targets. The reply row is
  written before the network call. The inbound worker re-checks the plan (`social_autoreply`) before running the model — a
  downgrade keeps the stored mode, the plan decides.
- **Models.** Admin → Settings → AI models row `gummfit.social`; default Claude Haiku 5.5 with an
  Anthropic key, nothing without one (no Gemini fallback for words sent under the owner's name).
  Every call counts in the `anthropic` bucket via `social/ai.py`; a full bucket means "not now".
- **No pooled connection is held across a model or network call** in the routes (draft, reply).
- **Video (`cappesocial02`, plan feature `social_video` on business / pro / creator).** The
  browser posts the original straight to S3 with a presigned POST pinned to the declared size
  (`assets.presign_upload`; nginx caps proxied bodies at 20 MB) into the public bucket under an
  unguessable key — that bucket's CORS must list the dashboard origin (`https://gummfit.com`,
  `https://www.gummfit.com`), or the browser's POST is blocked. `assets/{id}/complete` HEADs it and checks the container's first bytes, then queues
  `render_cappe_social_video` (`workers/tasks/cappe_social_media.py`), which reads the original
  through a presigned GET and cuts a 1080x1920 vertical render (plus 1920x1080 for a clearly
  landscape clip) — fitted on a blurred copy of itself, never cropped, trimmed to 90 s, H.264 High
  / AAC 48 kHz stereo, `+faststart`, a silent track added when there's none. Renders and three
  poster frames go to the public bucket (Meta fetches by URL).
  - **It runs on the shared default worker** (one slot, 768 MB) — Diego chose that over a media
    host for now. So `render.py` bounds everything: `veryfast`, two threads, short lookahead, a
    timeout per ffmpeg with the whole process group killed, one output on disk at a time; the
    task is idempotent (stored frames/renders are skipped) and retried once. A long render delays
    the minute publisher while it runs. If renders start to hurt, move the task to its own queue
    on separate compute (the recaps worker pattern, `docs/ops/ESPRESSO_RECAPS.md`).
  - **ffmpeg input is untrusted:** every `-i` carries `-protocol_whitelist https,tls,tcp` and
    `-format_whitelist` (MP4/MOV + Matroska/WebM demuxers only), so a playlist posing as a video
    can't make the worker read `file:` paths or fetch other URLs. Keep both on any new ffmpeg call.
  - **A post names a video by `asset_id`**; `variants.media_for` swaps in the cut each network
    takes at publish time (Instagram → Reel from the vertical cut; Facebook → Reel, or a Page
    video from the landscape cut). A video always goes out alone (`validate_for_targets`). A
    scheduled post whose video isn't ready is `rendering` and never claimed; the render flips it
    to `scheduled` and publishes any that are already due.
  - **Meta processes video for minutes, so publishing is resumable.** A provider returns
    `Pending(phase, state, retry_after_s)`; the target goes back to `pending` with its `state`
    (container / video id) and the claim's attempt handed back (`record_pending`), and the next
    sweep checks once — no call waits. Instagram: `REELS` container → poll `status_code` (≤10
    checks) → `media_publish`. Facebook Reel: `video_reels` start → `rupload` with `file_url`
    (header auth `OAuth <token>`, not Bearer) → finish `PUBLISHED` → poll `status`.
  - **`cappe_social_media_sweep`** (every 5 min, seeded on) re-queues renders stuck 30 min (fails
    them after two attempts), deletes uploads never completed after a day, puts back targets a
    killed worker left `publishing` for 20 min (`claimed_at`), and removes files 30 days on
    (`expires_at`) once no live post needs them. Frames are kept for the queue.
- **Chat composer** (`routes/social_chat.py`, `services/social/chat/`, the Create tab's default;
  the form stays one click away). The owner drops photos/videos and says what to post, where and
  when; one Claude call (`gummfit.social`, `ai.model_for("chat")`) per turn writes a reply and,
  per post, the Instagram caption + hashtags, the Facebook text and alt text. **The model only
  writes words and picks from lists; code decides the rest** (`chat/plan.py:resolve`): the time is
  read from the owner's words first by `chat/when.py` (deterministic, the store's timezone —
  "2pm tomorrow", weekdays, dates, "in 2 hours", "tonight"), the model's reading only when they
  name none; accounts are the site's connected ones for the networks named (TikTok/YouTube get
  files to download, below — a photos-only plan still gets a warning); the link is a real
  `/shop/<slug>` page or the store; photos may share a carousel (≤10), a video goes alone, and
  nothing dropped is left out of the plan.
  - The conversation reuses Merlin's tables (`kind='social'`, no page; no migration) and the plan
    is a staged action (`social_plan`: proposed → executed / dismissed / replaced). A new turn
    replaces the open plan and bumps `revision`; confirm must name it and runs under
    `lock_conversation_actions`, so a double click can't post twice.
  - Confirm makes ordinary posts + targets (`chat/confirm.py`), with each network's copy and
    UTM-tagged link on its target (`post_targets.content`); `outbound` prefers it over the post's
    caption. Photos handed to the model must be our own `cappe/social/` uploads (Claude fetches
    them by URL); a video is shown by its poster frame.
  - The Create tab lists the owner's chats (`GET …/chat/conversations` with the last message and
    whether a plan is waiting; `PATCH`/`DELETE …/chat/conversations/{id}` rename and delete,
    scoped to `kind='social'` and the site).
- **Exports (`cappesocial03`, `routes/social_exports.py`, `services/social/exports.py`; the Exports
  tab).** TikTok and YouTube can't be posted to through their APIs until their app audits pass, so
  a video is cut into files the owner downloads and uploads by hand, with the words to paste. The
  chat makes them when the owner asks in their own words (`chat/intent.py`, deterministic, before
  the model: "prepare this for all platforms", "cut it for TikTok", "export", "word-for-word
  captions"), when they post "everywhere" or name TikTok/YouTube (posts go to Instagram/Facebook,
  files for the other two), and for any video when no account is connected. `plan.exports`
  carries `{platforms, captions, items, reason, files_only, note}`; the card's **Files only**
  mode (`mode: "export"`) posts nothing; a plan with posts makes both. The model writes TikTok
  (caption + hashtags) and YouTube (title, description, tags) words only when files are coming
  (`plan.export_hint`); code fills them from the Instagram words when it doesn't and enforces the
  limits. Links: YouTube's description gets the UTM link; Instagram/TikTok captions don't make
  links clickable, so theirs is shown apart "for your bio" (`plan.texts_for`).
  - **Cuts** (`presets.py`): one 1080x1920 file serves Instagram, TikTok and Shorts — a single
    caption box (`VERTICAL_BOX`, bottom edge at y=1400, 140 px sides) clears all three apps'
    buttons and text — plus 1920x1080 for YouTube when the clip is clearly landscape. Up to 180 s
    (Shorts' limit); `-fs` 240 MB. A cut identical to the video's posting render (no captions,
    clip ≤ 90 s) is reused (`shared`) rather than encoded again. A download is a 10-minute
    presigned GET with `Content-Disposition: attachment; filename="<site>-<clip>-tiktok.mp4"`.
  - **Captions**: the words come from **Gemini 3.5 Transcribe** (`transcribe.py`, the
    `gemini-3.5-transcribe` model with `word_timestamp=True`; Claude doesn't take audio), fed 16 kHz
    mono FLAC inline, counted in the `gemini` bucket; a full bucket or no key means "try again in
    5 min" (6 runs, then the files go out without captions). The timed words are kept on the video
    (`cappe_social_assets.transcript`) so it is transcribed once. `subtitles.py` groups them (≤18
    characters / 4 words a line, breaking on pauses and sentence ends) into an ASS file — white
    DejaVu Sans Bold with a black outline, the spoken word lit in Gummfit lime — burned in by
    ffmpeg's `ass` filter after the frame is fitted, and a phrase-level `.srt` for YouTube. The
    image's ffmpeg must have libass; `server/Dockerfile` fails the build if it doesn't, and
    `render.has_filter("ass")` makes a build without it ship plain files with a note. Homebrew's
    ffmpeg has no libass, so the caption e2e test is skipped on a Mac. DejaVu covers Latin, Greek
    and Cyrillic only.
  - **One step per task run** (`prepare_cappe_social_export`: probe → transcribe → each cut → the
    `.srt`), each recorded as it lands (`next_step` reads what's left), then the task queues the
    next, so the minute publisher gets the worker between steps. `step` records what's running: a
    soft time-limit or a second failure gives up that step only (that file shows its error; the
    export ends `partial`). The media sweep re-queues exports idle 30 min and fails them after 12
    runs; files expire after 30 days. A video an export uses can't be deleted and outlives its
    own expiry until the export goes. A video made into files by a confirmed chat plan counts as
    used, like a posted one.
- **Plan features:** `social` (posting, scheduling, captions) on every plan; `social_video`
  (dropped videos, and their export files) and `social_autoreply` (the AI inbox) on business / pro
  / creator. All 402 at the route.
- **Schedules are the store's wall clock.** A `scheduled_at` with no zone is read in
  `cappe_sites.timezone` (`routes/social.py:check_schedule`), so "2pm" is the store's 2pm; the
  chat's plan card edits times the same way. The form composer still sends an aware time from the
  browser.
- **Consumer data:** `scripts/sql/anonymize_dev.sql` turns every token into `dev_<id>` (connection
  `revoked`) and strips inbox author ids/raw payloads; `refresh-dev-from-prod.sh` gates on both.

**Meta setup (once, before "Connect" works):** create a Meta app (Business type) with Facebook
Login for Business, Instagram Graph API and Messenger; add the redirect URI
`https://<CAPPE_BASE_DOMAIN>/api/cappe/public/social/meta/callback`; subscribe the app's webhooks
for `page` (feed, messages) and `instagram` (comments, messages) to
`https://<CAPPE_BASE_DOMAIN>/api/cappe/public/social/meta/webhook` with the verify token; then
set `CAPPE_META_APP_ID`, `CAPPE_META_APP_SECRET`, `CAPPE_META_VERIFY_TOKEN` (optional
`CAPPE_META_GRAPH_VERSION`, default v21.0) in `~/matcha/.env.backend`. Outside development mode
the permissions in `meta.SCOPES` need Meta App Review and business verification. Unset ⇒ Connect
and Publish 503 with a setup message; the composer and queue still work.

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


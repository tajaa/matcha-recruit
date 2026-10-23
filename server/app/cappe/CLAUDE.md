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

## Magazines (2026-10, photo-journalism stories; `cappemag01`→)

Writers tell stories through pictures, laid out like a print magazine, from their own photos,
open-licensed and public-domain archive images, and labeled AI illustrations. The plan is a stack
of seven PRs (library → stories → archive imports → AI → writers/follows/issues → paid → showcase).
What is built so far:

- **Every stored image is re-encoded first (`services/media.py`)**, so no EXIF (a phone photo's GPS
  position, camera serial, time) reaches the CDN: the editor's `/upload`, the library upload and
  the creator upload all go through `process_image`. It decodes, turns the picture upright
  (`exif_transpose`), converts an embedded colour profile to sRGB and writes a new file from the
  pixels alone, capped at `MAX_SIDE` (3200). An animated GIF is stored as it came (GIF has no
  EXIF); an animated WebP is written again without it. Runs in `asyncio.to_thread`.
- **The library knows where each picture came from and what is printed beside it** (`cappe_assets`,
  `cappemag01`): `source`, `license`, `credit_line`, `alt`, `caption`, size, `variants` (WebP at
  480/960/1440/2048, never wider than the original, plus a 1200 px JPEG for email and link
  previews), `rights_attested_at`, `moderation`. **A generated image is always AI**:
  `cappe_assets.record` sets `ai_generated`, `license='ai'` and the credit "AI illustration" for
  every `kind='generated'` row (the editor button and Merlin both record through it), and the
  table has `CHECK (kind <> 'generated' OR ai_generated)`.
- **Credits: the owner writes them only on their own non-AI uploads** (`cappe_assets.editable_fields`;
  `PATCH /sites/{id}/assets/{asset_id}` answers 422 otherwise). An archive picture's credit comes
  from its license; an AI picture's is fixed. Alt text and captions are always the owner's.
- **The library upload (`POST /sites/{id}/assets/upload`) needs `rights_attested`** ("I took this
  or may publish it"), takes up to 15 MB, stores the sizes under `cappe/library`, and its row is the
  point of the request (not best-effort, unlike the editor upload's catalog row).
- **A story is a `cappe_posts` row with `format='blocks'`** (`cappemag02`): its words and pictures are
  `content = {"blocks": [...]}` (vocabulary and limits in `services/magazine/story_schema.py`; one
  cover, first; one paywall; pictures by library `asset_id` only, never a URL). Its `body` is DERIVED
  from the blocks on every save so the iOS app (which reads/writes only the old fields) always has
  text to show; an app edit that changes a story's `body` is 409 `edit_on_web`. A plain post
  (`format='markdown'`) is untouched and renders as one text block. `cappe_post_assets` records
  which pictures a story uses, so the library refuses to delete one (409).
- **Stories render server-side on the tenant host** (`routes/render.py` → `services/magazine/pages.py`
  through `render_site_html(body_override=…)`, their own `mz-` CSS in `render/assets/magazine.css`,
  not the page-block registry): `/magazine` (`?page=`), `/stories/<slug>`, `/topics/<key>`,
  `/feed.xml`, plus sitemap entries and a header link. A magazine-only site (`front_at_root`) serves
  its front at `/` and `/magazine` 308s there. Cache keys `cappe:render:{site}:__mag__:*`, dropped
  by every post/magazine write (`routes/blog.py` now invalidates on every write).
- **The pages exist only while the magazine is live** (`magazines.live_magazine`: turned on AND the
  owner's plan has the `magazine` feature — business, pro, creator, writer; `_legacy_fallback` too).
  The plan is checked at render, never at save, so losing it takes pages down without touching
  anything the owner wrote. A hidden story (`hidden_at`) is a 404 everywhere a reader can reach.
- **A paid story's words are never in the server-rendered page, the cache, the feed or the public
  JSON** (`story_render.split_at_paywall`; `routes/public/blog.py` nulls `body`/`content`). Writing
  `access='paid'` is refused until reader subscriptions ship (PR 6).
- **Rich text is a document, with its Markdown beside it** (`services/magazine/rt.py`, 2026-10-21): a
  text block's and a sidebar's `rt`, an interview answer's `a_rt`, are ProseMirror JSON (what the
  dashboard's Tiptap editor types). `normalize_rt` keeps only paragraphs, headings 2–3, quotes, lists
  (ordered with `start`), line breaks and the marks link (http/https/mailto only)/bold/italic/strike/
  underline, merges runs, turns anything else (and lists/quotes nested past six levels) into paragraphs
  of its words without recursion, so nothing typed is dropped, and caps characters (counted whole: a half-character is dropped, never kept or cut into) and nodes (30,000).
  `story_schema._rich`: a sent document wins and its `md` is derived (`rt_to_md`: nested lists indented four spaces as `render_md` reads them; for emails, feeds, word
  counts and the iOS `body`); Markdown alone (an old story, Assist, iOS) becomes a document (`md_to_rt`, which never
  fails: past the budget it gives plain paragraphs, so every old story opens).
  The page renders `render_rt` (else `render_md` for a block stored before documents). A single story
  for the owner (`blog._out`, through `stories.with_documents`) and the layout starters always carry
  documents; the list doesn't (converting Markdown costs about 1 ms a block). `tests/cappe/fixtures/
  magazine_rt_cases.json` pins `rt` → HTML and Markdown here and the client's `canvas/rt.ts` (whose editor
  reads that HTML back into the same document). `MAX_CONTENT_BYTES` is 600 KB (words are kept twice).
- **Text and photos carry their design in the block** (`story_schema`): text has `variant`
  (body/lede/small/statement), `align`, `columns` 1–3 (read for old stories but offered nowhere: a book
  page is already a column, `.mz-book .mz-text--cols` is one column); a photo has `border`, `shape`
  (rect/rounded/circle/arch), `filter` (none/bw/sepia) and `crop` ({x,y,w,h} percent, at least 5%, a whole
  picture is `null`). `story_render.photo_html` draws a crop by scaling the picture inside a frame of the
  crop's aspect, and a crop, circle or arch adds "(cropped)" to a CC BY/BY-SA credit. A circle ignores the
  crop. A text block also has its own type: `font` ("body" = the magazine's), `size` (0.6–3 × the story's),
  `color` ("" = the page's ink) and `leading` (0 = the page's, else 0.9–3).
- **Every picture is a design, and so is a designed page** (`services/magazine/design_schema.py` →
  `design_render.py` + `render/assets/design.css`, 2026-10-22). The cover, a photo and each photo-group
  picture take an optional `design`; the `page` block (`aspect` 3:4/4:5/2:3/1:1) is one. A design is
  `{layers, background}`: text (an `rt` document, face, size, weight, colour, alignment, leading,
  tracking, case, padding, autosize), image (a library `asset_id` only, fit, focal, zoom, filter), shape
  (rect/ellipse/line) and group (≤4 deep) layers, each placed in percent of its artboard with rotation,
  flips, opacity, 16 blends, hide/lock, a link, fills (solid/linear/radial, ≤8 stops), strokes, per-corner
  radius, ≤4 shadows and blur. `normalize_design` clamps everything, drops unknown keys, regenerates bad or
  duplicate ids (`l{n}`) and holds a design to 200 layers / 80 KB; text is ≤2,000 characters a layer, and
  colours are `#rrggbb[aa]` or `accent`. Positions are numbers (`--x/--y/--w/--h`) that design.css turns
  into a place through the artboard's units (`--bw/--bh`), so a design is the same on a spread, a phone
  and a snapshot; the cover's design is anchored to the picture's own box inside the cropped cover.
  Pictures laid on a design are checked like any block picture (the site's own library, 422 otherwise)
  and **each one's credit is printed** (`layer_credits`, from the asset row). Layer words count as story
  text (`design_words`), go under the picture in an issue email, and are edited on the page as rich fields
  `design.<id>` / `items.<n>.design.<id>` (`rich_registry`). The client draws designs too
  (`magazine/design/designRender.ts`); `tests/cappe/fixtures/magazine_design_cases.json` holds both to the
  same bytes (each case's `html` is `design_html`'s output: when the renderer changes on purpose, rewrite the
  cases from it, then make the TS match).
- **Legacy photo `overlays` become text layers on read** (`design_schema.overlays_to_layers`, called by
  `normalize_story` and `with_designs`), so stored overlays keep rendering and are never written again.
- **Fonts are an allowlist of 95 Google faces** (`services/magazine/fonts.py`, mirrored by the client's
  generated `design/fonts.ts`), each with the weights and italics it ships. A page's font link asks only
  for what its designs and text blocks use (`story_fonts` → `fonts_links`: one `<link>` per face, always
  with regular 400; issue pages too). "heading"/"body" are the magazine's own pair (`var(--mz-h)`/`--mz-b`).
- **A story page is a book turned left and right** (`pages.book_html`, `render/assets/book.js`, the book
  section of `magazine.css`): the article flows through CSS columns of the page's height inside a
  horizontally scrolling `.mz-book` (one page on a phone, a two-page spread from 960 px). **A matte cover and
  glossy pages**: the first spread (the cover sheet) gets a grain and softer photos (`.mz-pages::before`,
  which scrolls away with it); later spreads are bright coated paper with a sheen (`.mz-gloss`, fixed over
  the spread, off while `data-mz-at="0"`), a gutter shadow and stacked page edges (`.mz-spread`). A spread
  is the book's width: the script turns by `clientWidth` (arrows, ←/→/Page keys; a swipe past `FLICK` of a
  spread turns, short of it springs back). **Browsers never count the space after the last column**, so the
  script measures the story's column pieces (`getClientRects`, never by changing layout) and places
  `.mz-end` to end the pages on a whole spread; without it the last page could not be reached. The cover is
  a flex column of one page's height (the photo fills what the words leave, so every cover is cropped and
  credited so). In the book, text runs in one column (nested columns break across pages in Safari) and pull
  quotes are capped, smaller past `story_render.LONG_QUOTE` characters. Each figure carries `--mz-ar` so a
  picture fits the page height. The front, topic pages, the feed and issue emails are not paged.
- **Our script-less frames turn the pages from outside** (`client/src/cappe/magazine/reader/BookFrame.tsx`
  over `book.ts`: the editor preview, "View as a reader", a reader's dashboard). **Safari never calls a
  listener the parent adds inside a `sandbox="allow-same-origin"` frame without `allow-scripts`**, so
  nothing listens in the frame: the arrows, page count and keys are the parent's, `book.ts` polls the
  pages' scroll (`POLL_MS`) to settle swipes, and a link in the page is rewritten to `about:blank#mz-link=…`
  so following it fires the frame's `load`, which the parent reads (`followedLink`) and puts the page back.
- **The story editor is one design workspace with one undoable document** (`editor/StoryEditor.tsx`,
  `editor/history.ts`: headline fields + blocks; edits within 1 s fold into one step, structural edits are
  their own), ⌘Z/⇧⌘Z/⌘S and the shared `useUnsavedGuard`. See the client's CLAUDE.md for its layout.
- **Markdown (stories stored before documents, emails, feeds) is constrained** (`richtext.render_md`: `<` escaped before Markdown, then our
  own `html.parser` allowlist of p/em/strong/a/h2/h3/lists/blockquote — not bleach, which several
  test modules stub; h1→h2; links http(s)/mailto with `rel="nofollow ugc noopener"`). Credits come
  from the library row, never the block.
- **Archive pictures come from four sources** (`services/magazine/sources/`, `cappemag03`): Openverse
  (CC photos from Flickr, Wikimedia and others), the Smithsonian Open Access API, The Met and NASA.
  Diego approved these for magazines on 2026-10-20; the "Claude + Brave only" rule is Espresso's.
  Only CC0, public domain, CC BY and CC BY-SA, never mature (`base.ALLOWED_LICENSES`; NC and ND are
  out because magazines can be paid and a cover crop is an adaptation). Each source filters, and
  `allowed()` filters again on the way out of the registry, whatever the archive's own filter says:
  The Met's `isPublicDomain` search filter let copyrighted works through when this was written, so
  each object's own flag decides. Shapes that bit, checked live 2026-10-21: The Met retired
  `/v1/search` (410) for `/v1.1/search`; anonymous Openverse stops at 240 results (401 past it, so
  `openverse.ANON_PAGES`); Smithsonian marks CC0 per image (`media.usage.access`) and resizes at the
  source (`&max=`); a NASA item's `href` is a manifest, and `~large` is often missing (`best_file`).
  Keys are optional: `OPENVERSE_CLIENT_ID`/`OPENVERSE_CLIENT_SECRET` (else anonymous and throttled),
  `SMITHSONIAN_API_KEY` (else `DEMO_KEY`). Searches are cached an hour for everyone (archive data is
  public); resolves a day.
- **An import re-checks the license before it downloads** (`services/magazine/imports.py`, worker
  `workers/tasks/cappe_media_import.py`, on demand, no scheduled task). The route queues
  `cappe_asset_imports` rows; the worker claims one at a time (`FOR UPDATE SKIP LOCKED`), resolves it
  again with `fresh=True` (anything no longer allowed is `refused` and never fetched), downloads
  through `safe_fetch.fetch_public` (25 MB; the Met's web-large copy stands in for an oversized
  original), runs it through `media.process_image` like an upload, and writes the `kind='stock'`
  asset (with its credit) and marks the import ready in one transaction. No transaction is open and
  no lock held during a network call. A failed download is retried up to 3 attempts; the owner's
  polling (`GET …/library/imports`) re-dispatches anything stuck. A picture deleted from the library
  can be imported again (`imports.requeueable`).
- **The daily allowance is the plan's `stock_imports_per_day`** (300 paid, 25 free; a plan may set
  0), counted per account in the database; a full day is a 429 that says how many are left.
  Pictures already in the library don't count. "Stock a topic" (`POST …/library/stock-topic`) runs
  `topics.TOPIC_QUERIES` (fixed searches per topic) and queues what isn't in the library yet.
- **Archive thumbnails are served from our origin** (`GET /public/stock-thumbs/<token>`,
  `routes/public/stock.py`): the dashboard's CSP allows images only from itself and CloudFront, so a
  search result carries a signed path (`sources/thumbs.py`: HMAC from `JWT_SECRET_KEY`, 6 h) and the
  route fetches only addresses our searches signed, re-encodes them as a small WebP and caches them a
  day by picture. It is not an open proxy; the archive's file URL never reaches the browser.
- **An AI illustration is always labeled and never a real person** (`services/magazine/ai_images.py`,
  `POST /sites/{id}/library/illustrate`, `routes/magazine_ai.py`). The prompt is checked before anything
  is generated: first a deterministic check for the unmistakable cases (an @handle; an office only a
  person holds followed by a name, "President Lincoln", "Pope Francis"; titles that also name things,
  "General Motors", "Dr Pepper", are left to the model), then Claude Haiku. The check FAILS CLOSED: no
  key, an error, a timeout or an unreadable verdict is a 503, never a pass. A refusal (422
  `real_person`) or an unavailable check spends no image quota; the shared `image_quota` is charged
  only after a pass (the paid allowance for any plan with `magazine`, since Writer isn't a premium
  design plan), plus 40 prompt checks a day. The picture is drawn in a visible illustration style
  ("clearly an illustration and not a photograph", invented people only), stored as
  `kind='generated'`, `ai_generated`, `license='ai'`, credit "AI illustration"
  (`cappe_assets.insert_generated`). The generator's own file stays the original (with whatever
  provenance data it carries); only the responsive sizes are added (`media.store_processed(main_url=)`).
- **Assist is fixed writing actions on Claude, proposals only** (`services/magazine/assist.py`,
  `POST /sites/{id}/posts/{post_id}/assist`): `draft`, `headlines`, `captions`, `tighten`,
  `search_terms`. One `generate_text` call each, no agent loop, no Gemini, nothing saved. The model is
  Admin → Settings → AI models, surface `gummfit.magazine` (`claude_default`: Haiku unless the admin
  picks another). It reads the editor's unsaved story when sent (else the saved one; a plain post is
  one text block), releases the connection, then downloads each picture's 960 px WebP size and calls
  the model. The prompt forbids invented facts, quotes and numbers (a draft writes "[check: …]"
  instead), naming a person in a picture unless its title or credit does, and writing credits. Every
  proposed draft goes through `normalize_story`, and a picture id the model wasn't given is dropped
  (`_scrub`). 5 a day without the `magazine` feature, 60 with; a request the writer has to fix (422)
  spends none.
- **Writers are an account type** (`account_type='writer'`, `cappemag04`): sign up at
  `/cappe/magazines/signup`, then `POST /magazine/sites` makes their one magazine-only site
  (`source_type='magazine'`, `front_at_root`, a draft About page) at EXACTLY the handle chosen
  (`services/magazine/writers.py`: 3–30 lowercase letters/digits/single hyphens, not a
  `RESERVED_SUBDOMAINS` label; taken is 409, never a "-2"), under the same account lock and site limit
  as any site. Business accounts get a magazine by turning it on for their site instead (403 here).
- **The Writer plan is offered only to writers** (`catalog.plan_offered`: `features.audience='writer'`
  keeps it off everyone else's lists and checkout; a writer sees Writer, Free and Business). $9/month,
  `can_sell=false`, one site, `magazine`. Its Stripe Price needs `server/scripts/seed_cappe_plans.py`
  after the migration; until then a writer checkout is 503. `GET /public/pricing?for=writer` is the
  magazines landing page's lineup.
- **A magazine site publishes with a published story on a plan with `magazine`**
  (`readiness._magazine_readiness`; the publish route answers a missing plan with 402
  `plan_required` naming the Writer plan first). It is never sent for business-listing inference.
- **Following is double opt-in** (`POST /public/sites/{slug}/follow`, `routes/public/magazine.py`): a
  `pending_confirmation` row with `source='follow'`, confirmed by the existing confirmation worker and
  page (worded as the reader's own ask). It never touches a `subscribed` or `bounced` row, the answer is
  always the same 202, and an address gets at most three confirmation emails a day per magazine.
- **An emailed "issue" is a campaign** (`cappe_campaigns.kind='issue'`, `routes/magazine_emails.py`, the
  owner's "Emails" page; not an issue in print, below): a published
  story emailed to followers from our template (`services/magazine/issue_email.py`: tables and inline
  styles, the 1200 px JPEG for pictures, credits from the library row, "AI illustration" for AI). A paid
  story only ever sends its opening. A story goes out once. Newsletters and issues share one send budget
  (`services/campaigns.py`: `SENDS_PER_DAY` and `send_cap_problem`'s 5,000 recipients a day). The send
  worker gives each reader their own links: a page on the magazine's address
  (`GET /unsubscribe/{token}` in `routes/render.py` changes nothing; its button POSTs) and the RFC 8058
  one-click address in `List-Unsubscribe` + `List-Unsubscribe-Post`, sent in the magazine's name with
  the writer as Reply-To. Those headers go out on the Gmail path only
  (`EmailService.send_email_with_fallback(extra_headers=)`); MailerSend drops them, so the body always
  carries the link too. Unsubscribing works whatever the site's status.
- **Readers pay with a `cappe_shopper_subscriptions` row of `kind='magazine'`** (`cappemag05`,
  `services/magazine/billing.py`). They get everything a store's recurring order has: the Checkout
  handshake (`recurring._attach_checkout_session`), cancel/resume, the card portal, the account page,
  deletion of the reader or the site. **A magazine invoice never becomes an order**: `recurring.handle_event`
  writes `cappe_magazine_payments` (unique on the invoice) instead, so there is no stock, receipt or order
  alert, and the emails are the magazine's (the writer hears about a new paid reader, not each renewal).
  `charge.refunded` without an order updates the ledger's `refunded_cents`.
- **Gummfit's share is `magazine_fee_bps`** (`cappe_marketplace_settings`, admin-editable 0–5000, 3000 when
  missing, unreadable or out of range — never the plan's store fee), sent as `application_fee_percent`.
  Connect Standard with direct charges, so Stripe's processing fee comes out of the writer's balance.
- **The paid part of a story is never in the page, the cache, the feed, an issue email or the public
  JSON.** The page holds the teaser (blocks before the `paywall` block, else `preview_blocks`) and an empty
  `.mz-paid` box; `render/assets/paywall.js` signs the reader in (emailed code, the same cookie session and
  Web Lock as `account.js`), then fetches `GET /public/sites/{slug}/stories/{story}/paid`
  (`no-store, private`; 403 `{code:'subscribe'}` without access) or starts checkout. Paid access
  (`services/magazine/access.py`) is a magazine subscription that is `active`, `trialing` or `past_due`,
  or a comp (`cappe_magazine_comps`) neither revoked nor expired. `magazine_paid` alone opens reader
  sign-in (`shopper_auth.published_shopper_site`).
- **Paid needs the plan, Stripe and a price** (`PUT /sites/{id}/magazine`); a story becomes `paid` only
  while the magazine takes subscribers (an already paid story stays paid). **Turning paid off, or losing it**
  (plan without `magazine_paid`, account not active — `services/magazine/lapse.py`, run by the hourly
  `cappe_comp_expiry` task) stamps `lapsed_at`; the sweep then sets each reader's subscription to end with the
  month they paid for and emails them, retrying what Stripe refused on the next run. A lapsed magazine stays
  up for `magazines.GRACE_DAYS` (31) without the plan, so paid readers keep what they paid for — only while it
  has readers (a subscription still billing or a live comp); with none, losing the plan takes it down at once.
- **Reader accounts** (`account_type='reader'`, `cappemag06`) subscribe to magazines and sell nothing:
  `plan_offered` offers them no plan and `_enforce_site_limit` refuses them a site (403 `reader_account`).
  Their dashboard is `routes/reader.py` over `services/magazine/shelf.py`. **No new identity table**: on
  each magazine a reader is still that site's `cappe_shoppers` row, matched by the account's **confirmed**
  email (`shelf.confirmed_email` re-checks `email_verified_at`; `idx_cappe_shoppers_email` serves the
  cross-site lookup). So a subscription started on the magazine's site shows on the dashboard and one
  started on the dashboard works there; any account type can use these routes. Subscribing makes the
  shopper row if needed and runs the same `billing.checkout` with `return_origins=[app_origin()]` (a
  return off gummfit.com becomes the magazine's dashboard page). Reading returns the story page as JSON
  `{html}` for a script-less frame, whole when the reader has paid access (rendered as a free story: the
  paywall marker prints nothing), cut at the paywall otherwise; `no-store, private`. The shelf keeps a
  magazine that is down so its reader can still cancel; resume needs one still taking subscribers. The
  paywall on the magazine's own page links to the dashboard (`pages.reader_path`, `data-mz-alt`).
- **Readers follow magazines from their account** (`cappemag08`: `cappe_magazine_follows`, PK
  account+site, both cascade; `services/magazine/follows.py`, routes in `routes/reader.py`). A follow is
  a one-tap Follow on the reader dashboard and sends NO email: email followers stay `cappe_subscribers`
  (double opt-in, above), a separate list. It feeds the dashboard's Following list (a magazine that is
  down stays, `live` false, so it can be unfollowed) and Feed (`GET /reader/feed`: live followed
  magazines' stories, newest first, one query; capped at `FOLLOW_LIMIT` follows, checked and inserted
  under the account's advisory lock so concurrent follows can't pass it; the feed goes back
  `FEED_MAX_PAGE` pages and its last says `has_more: false`, since the route refuses the next). Which are live is
  `magazines.live_magazines` — `live_magazine`'s rule for many sites, each owner plan resolved once;
  keep the two in step. The owner sees a count only (`GET /sites/{id}/magazine/follows`): an account
  follow carries no consent to share who. A magazine's own page can't see the dashboard's sign-in, so
  its follow box links to `/cappe/reader/m/<slug>?follow=1` (`data-mz-alt`), which follows on arrival.
- **An issue in print is one numbered book** (`cappemag07`: `cappe_magazine_issues`,
  `cappe_magazine_issue_stories`, `cappe_magazine_issue_assets`; `services/magazine/issues.py`,
  owner API `routes/issues.py` at `/sites/{id}/magazine/issues…`). It holds stories in order, each with a
  section and contents line, and **a story is in at most one issue** (`post_id` UNIQUE). Its `cover` and
  `contents` are designs checked and reshaped by `issue_schema.normalize_cover`/`normalize_contents` (as
  `normalize_story` treats a story): a 4:5 artboard, positions in percent and type sizes in `cqw`, ≤8 cover
  lines, a picture only as a library `asset_id` (recorded in `cappe_magazine_issue_assets`, so the library
  refuses to delete it), and a cover line may link only to a story in the issue. The client mirror of the
  lists is `client/src/cappe/magazine/issues/coverVocab.ts` (a server test reads it).
  **Releasing publishes the issue's draft stories in the same transaction**; a released issue stays
  editable, every save goes live, and a draft added to it is published by the save (the editor's button
  says so). Withdrawing takes it back to a draft and leaves its stories up. Release needs a live magazine
  and at least one story. Readers reach a released issue without `hidden_at`, and in it only live stories.
- **Its pages** (`services/magazine/issue_render.py` for the cover and contents, `issue_pages.py` for
  the pages; `render/assets/issue.css`): `/issues/{n}` is the whole issue as one book: the cover alone on
  the right of the first spread (a closed magazine; the spread is clipped to its right half until the first
  turn), the contents, then every story from a new page with its own opener and, when paid, its own
  paywall. The cover's face is drawn over its page from outside the flowing columns (`.mz-issue__face`, a
  child of `.mz-pages`, not of the measured `[data-mz-flow]`), so it bleeds to the paper's edges and is
  never split across pages. `book.js` (and `reader/book.ts` for our frames) calls the first spread
  "Cover", doesn't count the mat page (`data-mz-skip`), fills the contents' page numbers
  (`[data-mz-pageno]`) from where each story starts, and turns to a story from its contents entry, a cover
  line or a `#mz-s-<slug>` link in. **One paywall script serves every paid story on a page** (each wall
  `[data-mz-paywall]` fills the `[data-mz-paid]` box after it from the per-story `/paid`; the single-story
  page keeps `id="mz-paywall"`), so the paid part of every story stays out of the issue's HTML and cache.
  **The script asks `GET …/magazine/me` before it fetches any paid part**: a reader without access spends
  none of the `/paid` allowance (300 an hour), and back from checkout (`?subscribed=1`) it polls only
  `/magazine/me` (6 tries, 2 s apart) for the webhook, then fetches each part once.
  `/issues` is the archive of covers; the front page leads with the newest released issue (its stories
  stay in the list below; the lead reads only the first `issue_pages.CURRENT_LIST` titles and slugs,
  `issues.issue_headlines`), a story in one links "From No. 3 — read it in the issue", and the sitemap
  lists them. Cached as `__mag__:issue:{n}` and `__mag__:issues:{page}`; every owner write invalidates.
  The owner's issue preview shows drafts as they will be once released but never an archived story.
  A story put in another issue between `check_stories` and the save (the `uq_…_issue_stories_post`
  clash, on the stories' INSERT or the issue's UPDATE) is a 422 that says so: `save_issue` runs both writes
  in one try that turns it into an IssueError (`_unique_problem`).
- **The owner edits on the page itself** (2026-10-21): an *edit render* of a story or an issue
  (`POST /sites/{id}/stories/preview` or `…/magazine/issues/preview` with `edit: true`) is the reader's page
  with markers, and each story's rich fields' documents in a `<script type="application/json"
  data-mz-rt>` (`pages.rich_registry`, `"<block>|<field>"` → document, `<` escaped) so the editor opens
  them exactly. The editor itself is the dashboard's (`client/src/cappe/magazine/frame/`, bundled by
  `client/vite-mz-frame.ts` and written into the page by `EditFrame`); the server serves none. The
  dashboard shows it in a `sandbox="allow-scripts"` frame **without** allow-same-origin (the dashboard's
  tokens live in sessionStorage) and listens only to its own frame (`client/src/cappe/magazine/canvas/`).
  The same renderers take `edit` (`story_render`, `pages.story_article_html`/`render_story`/`book_html`,
  `issue_render`, `issue_pages`); **only `routes/blog.py` and `routes/issues.py` pass it** (pinned by
  `test_cappe_magazine_canvas.py`): published pages, the cache, "View as a reader" and the reader dashboard
  never get it. Markers: `data-mz-edit` on the reader, `data-mz-s` per story (`preview` in the story
  preview), `data-mz-b` = the block's index in `content.blocks` (counted before anything is skipped; edit
  mode prints a placeholder for an empty block or a missing picture, `data-mz-pick`), `data-mz-f` +
  `data-mz-k="plain|rich"` per field (`@title`/`@kicker`/`@excerpt`/`@byline`, then per block exactly what
  `client/src/cappe/magazine/canvas/fields.ts` lists — a test pins each block type to that list; issue fields
  are `issue:lines.N.text|sub`, `issue:issue_line.text`, `issue:contents.heading`, `issue:line:<post>`,
  `issue:section:<first post>`), `data-mz-drag` for words on a photo, `data-mz-focal` on cover pictures,
  `data-mzc-el` cover elements. An edit render shows **a paid story whole** with a "Subscribers only from
  here" mark and no paywall script; it is `no-store` and owner-only, so the paid part still never reaches a
  reader's page, the cache, the feed or the JSON. The issue's edit preview also takes `stories_content`
  (each story's unsaved words, through `normalize_story` + `check_assets` like a save; a story not in the
  issue is ignored; its cover picture is what saving them would leave, the cover block's or none, never the
  saved one) and has its own rate bucket (`cappe_issue_edit_preview`, `EDIT_PREVIEWS_PER_HOUR`).
  Rich fields come back as documents and are kept as above. In the frame, Home/End/Page keys are
  swallowed while typing (on a Mac they scroll the whole page out from under the book), Backspace never
  navigates back, and the book is re-measured and turned to the caret when typing runs onto a new spread
  (`book.js` counts spreads only on resize and load).

### Gummfit Studio: stories made of pages (2026-10-22, `services/magazine/studio/`, `cappemag09`)

A story with `format='pages'` is a document of exact pages designed in the Studio
(`client/src/cappe/studio/`): `content = {"doc": {...}}`, normalized by `studio/schema.normalize_doc`
(lengths in pt to 2 places, every id/enum/colour/font/asset checked, limits in `studio/limits.py`, mirrored
by `client/src/cappe/studio/model/limits.ts` and pinned by a test). Text lives in threads of text frames;
each thread stores its **composition** (`comp.lines`, `[frame, para, start, end, x, baseline, width, align]`,
UTF-16 offsets), made by the Studio's composer (HarfBuzz on our own faces). **The server never measures
text**: it checks the composition's shape (`valid_comp`, else dropped) and slices the words out of the
normalized paragraphs itself; a thread with no valid composition prints its words flowed in one frame.
- **One renderer in two languages, byte-equal**: `studio/render.py` and `client/src/cappe/studio/render/
  layoutRender.ts`, held equal by `tests/cappe/fixtures/studio_render_cases.json` (rewrite it with
  `STUDIO_FIXTURES=write`); `studio/layout.css` and the client's copy are byte-equal (tested). Every size is
  `calc(N * var(--u))`, `--u` one point on screen (the reader sets it from container units, the Studio from
  its zoom). A line is an absolutely placed `white-space:pre` box anchored by its **bottom** (a zero-height
  strut at the baseline), the space it breaks at follows as its own `.lyt-sp`, justified lines use
  `text-align-last:justify`: no browser re-breaks a line. Paragraphs are `<p>` holding their lines, so
  copy and screen readers read in order.
- **Faces are ours** (`studio/fonts.py`, committed `fonts_manifest.json`: google/fonts at a pinned commit,
  static Latin subsets, metrics normalized by `server/scripts/build_magazine_fonts.py`). Served by sha at
  `/api/cappe/public/fonts/{sha}.ttf` (`routes/public/fonts.py`: manifest shas only, bytes checked against
  the sha, immutable; read from `CAPPE_FONTS_DIR` or storage key `cappe/fonts/<sha>.ttf`). Every face has
  its own family name (`f-<sha16>`), so an installed font never stands in. **Ops:** run the build script
  once per environment (`--out DIR --upload --dry-run`, then for real) or the Studio and readers fall back
  to system fonts.
- **Saving** (`routes/studio.py`): `PUT …/studio/stories/{id}` with `base_rev` (a stale one is 409
  `{code:"stale_rev", rev}`); an unpublished story saves to itself; a **published** one saves to its
  working copy (`cappe_posts.draft`; readers keep the live pages, nothing is invalidated) until
  `publish: true` makes it live (kept as a revision, cache dropped). Revisions (`cappe_post_revisions`,
  kinds save/publish/restore/convert, `KEEP_REVISIONS`), discard, restore. The story API (`routes/blog.py`)
  changes only what isn't on the pages (title, dek, byline, topic, access, status): content, cover or format
  of a paged story is 422 `EDIT_IN_STUDIO`, a changed `body` 409, and a story can't become pages there.
  A draft still at its placeholder slug (`untitled-story-N`, either editor) takes its headline's slug the
  first time it is published; never after.
- **Readers**: `/stories/{slug}` is the pages strip (`studio/reader.css`, `pages.js`: arrows, keys, folio;
  under 700 px one page at a time); `/stories/{slug}/text` is the **Text view** (`studio/text_view.text_blocks`:
  the threads and pictures in reading order as ordinary blocks, through the classic book), which is also
  what `story_blocks` returns for a paged story, so the feed, issue emails, `story_text` (iOS body, word
  count, search) and Assist all get words. Other stories' `/text` is a 308 to the story.
- **Paywall by page**: `doc.paywall_page` (2 or later; page 1 is always free). Pages from it are empty
  placeholders in the HTML and cache (`data-lyt-lock`, with a link to `#mz-paywall`); `/paid` returns
  `pages: [{n, html}]` and `paywall.js` fills them. The Text view cuts paragraphs where they cross into a
  locked page; the public JSON never carries a paged story's `content`.
- **Migration `cappemag09`**: format `pages`, `cappe_posts.rev` + `draft`, `cappe_post_revisions`; its
  downgrade refuses while paged stories exist. **CSP**: the dashboard needs `'wasm-unsafe-eval'` and
  `worker-src 'self'` (HarfBuzz): `client/nginx.conf` ×3 in the image, and `deploy/nginx/matcha.conf` on
  the host (hand-applied per its README).
- **Picture Editor** (`routes/pictures.py`, `studio/recipe.py`, `studio/edits.py`, `studio/models.py`,
  migration `cappemag10`): looks, sliders, crop/straighten/turn/flip and a click-to-keep **cut-out**, all
  in the browser (WebGL; the cut-out is SlimSAM on onnxruntime-web in a worker). Edits are never made in
  place: Done uploads the baked picture to `POST /sites/{id}/assets/{asset_id}/edit` with its recipe, and
  it becomes a new library picture (`kind='edit'`, `parent_asset_id` = the picture edited, `recipe` +
  `recipe_version`, `adapted`) carrying the source's provenance and licence; BY/BY-SA credits gain
  "(adapted)", AI pictures stay "AI illustration". Editing an edit again opens its parent with its recipe.
  The recipe is normalized the same way on both sides (`normalize_recipe` / `studio/picture/recipe.ts`,
  pinned by `tests/cappe/fixtures/picture_recipe_cases.json`, rewrite with `PICTURE_FIXTURES=write`).
  **An upload only keeps the source's credit if it is that picture edited** (else 422): its size is what
  the recipe's crop makes (`size_matches`), and its *detail* (each cell less the kept cells around it,
  inside the bounds of what a cut-out keeps) correlates with the source's (`looks_like`, ≥ 0.5). Plain
  light-and-dark correlation can't tell one sunset landscape from another, and comparing a whole thin
  cut-out at thumbnail size refused real edits (a cut edge's transparent black skews the cells beside it),
  so don't go back to either; the thresholds were set from 44 real edits from Chromium and WebKit against
  1,008 unrelated pictures (`MIN_LIKENESS` comment). Pixels for the editor come from the same-origin,
  owner-only, no-store `GET …/assets/{id}/pixels` (no CloudFront CORS). The cut-out model's two ONNX files
  are pinned by sha in `studio/models_manifest.json` (Xenova/slimsam-77-uniform, Apache-2.0) and served
  signed-in only at `/studio/models/manifest.json` and `/studio/models/{sha}.onnx`, read from
  `CAPPE_MODELS_DIR` or storage `cappe/models/<sha>.onnx`. **Ops:** run
  `server/scripts/fetch_magazine_models.py --upload --dry-run`, then for real, once per environment (or set
  `CAPPE_MODELS_DIR` in dev); until then the cut-out says the model isn't on this server yet. Migration
  `cappemag10`'s downgrade refuses while edits exist.
- **Graphics bank** (`studio/graphics.py`, `graphics_own.py`, `routes/public/graphics.py`; client `model/graphics.ts`,
  `ui/add/`): a page item of kind `graphic` names a file by sha (`src`), like faces: 3,560 cleaned SVGs (Lucide icons
  ISC, Microsoft Fluent Emoji flat MIT, our own shapes/badges/dividers/patterns CC0) in the committed
  `graphics_manifest.json` + `graphics_licenses.txt`. Both renderers draw it as a `div` background (colourful) or a
  CSS mask over its `color` (one-colour, `mono`), `fit` contain / stretch / tile (`tile` pt). Stretch draws
  `/public/graphics/stretch/<sha>.svg`, the file with `preserveAspectRatio="none"` on its root (`graphics.stretched`):
  CSS sizing alone never distorts an SVG with a viewBox, it centres it at its own shape. The schema refuses a
  `src` the manifest lacks, so **never take an entry out of the manifest**; the server forces `color` to null for a
  colourful one, so the Object panel's Colour recolours only the one-colour graphics of a selection. The side panel browses (`/public/graphics/browse`) and searches (`/public/graphics/search`) rather
  than download the ~1 MB manifest. Files are served by sha with a no-script CSP from `CAPPE_GRAPHICS_DIR` or storage
  `cappe/graphics/<sha>.svg`. **Ops:** run `server/scripts/build_studio_graphics.py --out DIR --upload --dry-run`,
  then for real, once per environment (it rebuilds the manifest from pinned sources: commit any change); until then
  graphics show as empty boxes.
- **Page templates** (client only: `ui/add/templates.ts`, `applyTemplate.ts`, `TemplatesTab.tsx`): 13 pages drawn on
  Letter and fitted to the story's size when used (type scaled, edge items out to the bleed, linked frames one
  thread). A blank page takes the template; any other gets a new page after it, so nothing is covered. One undo
  step. The target is the page in view at the click (by id; its faces load first, one template at a time), and the
  finished document is checked against the save limits (`limits.docProblem`, the server's counts) before it is
  committed: a full story is told why and left unchanged, never made unsavable. `templates.test.tsx` holds every face and graphic to the bank and composes each frame at its face's real
  ascent and descent: a display face can be far taller than its size, so size frames from that test, not by eye.
- **Studio bank** (Gummfit-curated, cappemag11: `studio/bank.py`, `routes/studio_bank_admin.py` at
  `/matcha-admin/studio-bank` behind matcha `require_admin`; admin UI hey-matcha.com/admin/cappe → Studio bank;
  client `ui/add/bank.ts`, `BankPhotos.tsx`): photos and graphics every site's Studio shows first (Photos →
  Gummfit, Elements → From Gummfit). A **photo** is stored once under `cappe/bank/`; placing it
  (`POST /sites/{id}/library/bank/{item}`) upserts the site's `cappe_assets` row (kind `stock`, source and licence
  `gummfit`, `source_id` the bank id) on the bank's own files, so there is no import queue. A **graphic** is
  `clean_svg`'d and stored by sha at `cappe/graphics/<sha>.svg`, served by the same public route; the two save paths
  in `blog.py` pass `bank.doc_graphics` to `normalize_doc`, which is how a page may name a sha the manifest lacks.
  So **a graphic is hidden, never deleted** (pages name it); deleting a photo is safe (library rows never delete
  files). `/public/graphics/picks` is cached 5 minutes.
- **Ask the Studio** (`studio/ask.py`, `POST …/studio/stories/{id}/ask`; client `ui/ask/`, `ui/panels/AskPanel.tsx`):
  one Claude Messages call per question (surface `gummfit.studio`, Haiku by default), no tools, nothing saved,
  nothing on the page changed. **The Studio sends the guide (`ui/guideContent.ts`) and the commands
  (`ui/commands.ts`) with each question**, so they stay the one description of what the Studio does; don't copy
  them to the server. It also sends the page in view in words (`ui/ask/describe.ts`, in the document's units),
  the last 6 turns and at most one reference picture (checked with Pillow, never stored); the server adds the
  manifest's families by kind. An answer's buttons survive only if they name a guide section or command that was
  sent, and the panel never offers Cut, Delete, Delete this page or Close as a button. 20 questions a day, 150
  with `magazine` (`cappe_studio_ask`).

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
    mono FLAC inline, counted in the `gemini` bucket; a full bucket, a 429/5xx or a dead
    connection means "try again in 5 min" (6 runs, then the files go out without captions); no key
    on the server skips captions at once (`transcribe.configured`). The timed words are kept on the
    video (`cappe_social_assets.transcript`) so it is transcribed once — except a passing failure
    (`reason` in `exports.TRANSIENT_NO_WORDS`), which only the export that hit it gives up on
    (`exports.CAPTIONS_UNAVAILABLE` in its `warnings`); a later export listens again.
    `subtitles.py` groups them (≤18
    characters / 4 words a line, breaking on pauses and sentence ends) into an ASS file — white
    DejaVu Sans Bold with a black outline, the spoken word lit in Gummfit lime — burned in by
    ffmpeg's `ass` filter after the frame is fitted, and a phrase-level `.srt` for YouTube. The
    image's ffmpeg must have libass; `server/Dockerfile` fails the build if it doesn't, and
    `render.has_filter("ass")` makes a build without it ship plain files with a note. Homebrew's
    ffmpeg has no libass, so the caption e2e test is skipped on a Mac. DejaVu covers Latin, Greek
    and Cyrillic only.
  - **Invariants from the 2026-10-21 review** (keep them):
    - A post never waits in `rendering` on an event alone: `posts.settle_renders` re-derives every
      held post from its videos' current state (ready → `scheduled`, failed/gone → `failed`); the
      media sweep runs it, and `set_schedule`/`update_post` run it for the one post.
    - `recover_stale_claims` resumes only targets with a `state` handle; one with none may already
      be live, so it fails with `posts.INTERRUPTED` instead of posting twice. A Facebook Reel saves
      its `video_id` (`facebook_uploading`) before uploading.
    - Chat confirm reads what the chat already posted from `cappe_social_posts.ai_meta.chat`
      (`confirm.posted_from_chat`), under the plan lock, and 409s a repeat; it re-checks every
      video is still usable. Spread posts add days on the store's wall clock.
    - A follow-up turn keeps the open plan's `exports` unless the message says something new about
      files or posting (`plan.carried_exports`). Owner-edited TikTok/YouTube words carry
      `by_owner` and are pasted as written.
    - `exports.record_output`/`record_srt` write only to an open export and say so; a file cut for
      an export deleted meanwhile is removed. Giving up a step never overwrites a file that landed.
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


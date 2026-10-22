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
- **Text and photos carry their design in the block** (`story_schema`): text has `variant`
  (body/lede/small/statement), `align`, `columns` 1–3; a photo has `border`, `shape`
  (rect/rounded/circle/arch), `filter` (none/bw/sepia), `crop` ({x,y,w,h} percent, at least 5%, a whole
  picture is `null`) and up to 8 `overlays` (words centred on an x/y point, size, tone, box, align).
  `story_render.photo_html` draws a crop by scaling the picture inside a frame of the crop's aspect, and a
  crop, circle or arch adds "(cropped)" to a CC BY/BY-SA credit. Overlay words are escaped, count as story
  text, and go under the picture in an issue email (email can't lay them over it). A circle ignores the crop.
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
- **The story editor keeps one undoable document** (`editor/history.ts`: headline fields + blocks; edits
  within 1 s fold into one step, structural edits are their own), ⌘Z/⇧⌘Z/⌘S, insert-anywhere, duplicate,
  drag to reorder, a Markdown toolbar (`editor/MarkdownField.tsx`, `editor/markdown.ts`) and the shared
  `useUnsavedGuard`.
- **Rich text is constrained Markdown** (`richtext.render_md`: `<` escaped before Markdown, then our
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
  up for `magazines.GRACE_DAYS` (31) without the plan, so paid readers keep what they paid for.
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
  `/issues` is the archive of covers; the front page leads with the newest released issue (its stories
  stay in the list below), a story in one links "From No. 3 — read it in the issue", and the sitemap lists
  them. Cached as `__mag__:issue:{n}` and `__mag__:issues:{page}`; every owner write invalidates.
- **The owner edits on the page itself** (2026-10-21): an *edit render* of a story or an issue
  (`POST /sites/{id}/stories/preview` or `…/magazine/issues/preview` with `edit: true`) is the reader's page
  with markers and `render/assets/editor.js` + `editor.css` inlined (`pages._EDITOR`, after `book.js`). The
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
  Rich fields come back as HTML and the dashboard stores them as the constrained Markdown `render_md`
  reads (`canvas/htmlToMd.ts`); `tests/cappe/fixtures/magazine_md_cases.json` pins HTML → Markdown on the
  client and Markdown → HTML here. In the frame, Home/End/Page keys are swallowed while typing (on a Mac
  they scroll the whole page out from under the book) and Backspace never navigates back.

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


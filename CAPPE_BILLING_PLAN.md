# Cappe monetization — subscriptions, take rate, and the private-email add-on

Working plan for turning Cappe from a product that can only take **one-off**
Stripe charges into one that sells **recurring plans**, takes a **per-plan cut**
of merchant sales, and can sell **per-mailbox add-ons** (private email).

Status: **foundation + backend shipped**; frontend and mailbox provisioning
remain. See [Rollout](#rollout) for exactly what is and isn't done.

---

## Why

The question that started this was "how do we give Cappe pro users a private
email service?" — but the answer surfaced a bigger gap: **Cappe had no way to
charge anyone a recurring fee at all.**

What existed before this work:

- `cappe_accounts.plan` (`free|hosting|pro|business`) — read by `design_gate.py`
  and `rider.py`, but **nothing in the codebase ever wrote it**. Every account
  was `free` unless hand-edited in SQL.
- Two working one-off Stripe paths: Connect **direct charges** for storefront
  sales (flat 2% `application_fee_amount`), and **platform** Checkout for domain
  purchases with a saved-card off-session renewal cron.
- `create_platform_checkout_session` already carried the docstring *"domains and
  plan billing"* — the plan-billing caller was never written.

What was missing: no `stripe.Subscription`/`Price`/`Product` usage anywhere in
Cappe, no account-level Stripe Customer, no plan catalog, no entitlement
resolution, no admin write surface, and **no webhook event dedupe on either
Cappe webhook**.

---

## Product decisions

| Decision | Choice |
|---|---|
| Plan lineup | **Creator** + **Business**, plus a `free` tier |
| Free tier | Can build and publish a site; **cannot take payments** |
| Intervals | Monthly + yearly, plus **$1 for 30 days → auto-converts to monthly** |
| Take rate | **Per-plan** `platform_fee_bps`, admin-adjustable at runtime |
| Creator limits | **Hard gate** — may only sell `service` / `booking` |
| Private email | **Separate paid add-on**, priced per mailbox, on any paid plan |
| Admin UI | **Inside the Cappe app**, behind a platform-admin flag |
| Premium design | **Every paid plan** gets it, Creator included |
| Existing sellers | **Comped**, never cut off (see [Rollout](#rollout)) |

---

## Two bugs found and fixed on the way

### 1. A latent cross-product webhook outage

Matcha core and Cappe **share one Stripe platform account and one secret key**.
Core's webhook already handles `invoice.paid`, `invoice.payment_failed` and
`customer.subscription.deleted` (`core/routes/billing/stripe_webhook.py`) —
precisely the events a Cappe subscription product needs.

`stripe_webhook_events.event_id` was a **global primary key**. So the moment a
Cappe endpoint subscribed to those event types, both endpoints would receive the
identical `evt_...`, and whichever called `_claim_event` first would win — the
loser reads the conflict as "already processed" and skips every side effect.
Nothing raises, nothing logs. A Matcha subscription simply never activates, or a
Cappe one doesn't, depending on delivery order.

**Fix** (`stripeevt02`): the ledger is keyed `(consumer, event_id)`. Existing
rows default to `'core'`, so core's behaviour is byte-identical. Consumers:
`core`, `cappe_platform`, `cappe_connect`.

### 2. A double-computed platform fee

`platform_fee_cents` ran **twice** on every storefront sale:

- `services/commerce.py` — for persistence to `cappe_orders.platform_fee_cents`
- `services/stripe_connect.py`, inside `create_checkout_session` — for the real
  `application_fee_amount`

Both read the same global setting, so they agreed *by luck*. With a per-plan
rate they could diverge, and the persisted number would be a lie about money.

**Fix**: the fee is computed once by the caller and passed in as
`application_fee_cents`; the internal recomputation is gone. The fee base is
unchanged — `subtotal_cents`, tax excluded.

---

## Schema (`zzzzcappe26`)

- **`cappe_billing_products`** — ONE catalog for plans and add-ons (`kind`), so a
  single price table can hang off both. Carries the entitlements:
  `can_sell`, `platform_fee_bps`, `allowed_fulfillment`, `site_limit`,
  `mailbox_quota_included`, `premium_design`, `features`.
- **`cappe_billing_prices`** — **APPEND-ONLY**. Stripe `Price` objects are
  immutable in `unit_amount`, so an admin price edit mints a *new* Stripe Price
  and a new row and flips `is_current`. Old rows survive, which is what makes
  grandfathering real: an existing subscriber's row still resolves to the amount
  they were actually sold at. `lookup_key` is Stripe's own idempotency handle.
- **`cappe_subscriptions`** — one live per account (partial unique index).
  `source='comp'` models a granted plan with no Stripe subscription behind it, so
  comped accounts stay queryable and revocable rather than indistinguishable from
  paying ones. **`stripe_event_at` is a watermark**: Stripe delivers
  `customer.subscription.updated` *out of order*, and without guarding each
  UPDATE on it a stale `trialing` event can land after an `active` one and
  silently downgrade a paying account.
- **`cappe_subscription_items`** — carries the plan item *and* the add-on items.
  A pure projection, rebuilt from `items.data` on every subscription event, so
  quantities cannot drift from what the customer is billed for.
- **`cappe_intro_redemptions`** — one $1 per account, ever.
- **`cappe_admin_audit`** — these are runtime-editable money knobs.
- **`cappe_accounts`** gains account-level `stripe_customer_id` (there was none —
  only a per-domain one on `cappe_domains`, so a domain buyer who subscribed
  would have got a second `cus_`), `is_platform_admin`, `plan_override_until`,
  and **swaps the `plan` CHECK for an FK** to the catalog — an admin-editable
  lineup must not need a migration per tier, and the FK makes a plan value with
  no entitlement row unwritable.

**No Stripe API calls in the migration.** `migrate-prod.sh` rehearses the whole
upgrade against live rows and rolls it back; a rehearsal that created real Stripe
objects could not undo them, and the second run would duplicate them. Stripe
objects are minted by `server/scripts/seed_cappe_plans.py`.

---

## Entitlements

`server/app/cappe/services/entitlements.py` is Cappe's analogue of matcha's
`require_feature` (it had none — gating was ad-hoc and inline).

- **`cappe_accounts.plan` stays the denormalized effective tier**, written only
  by the subscription webhook and the admin override. Entitlement lookup on the
  hot path is therefore a dict read against a cached catalog — no extra query,
  and every existing reader of `account.plan` keeps working untouched.
- **Only the catalog is cached** (60s TTL, `connection_or_direct` so pool-free
  Celery workers can read it). Per-account state is deliberately not cached:
  nothing to save, and an upgrade that takes a minute to apply generates tickets.
- **Failure is OPEN to today's behaviour.** An unreadable catalog resolves every
  account to a permissive fallback (selling allowed at the global 200 bps, all
  fulfillment types). A billing-config outage must not stop a merchant taking
  money. The fallback cannot itself raise — it does not call `get_settings()`
  unguarded.

Replaced by catalog lookups: the inline `_PLAN_SITE_LIMIT = {"free": 1}` dict in
`routes/sites.py`, and the bare `plan != "pro"` rider check in `routes/rider.py`
(`pro` is a retired code, so that compare would have left riders permanently
unreachable for every account on the current lineup).

`design_gate.is_premium_plan` stays **pure and sync** — it runs at write choke
points with no async DB context — but gains an optional `premium=` kwarg so
callers holding resolved entitlements can use the admin-editable catalog value.

---

## Where the gates live

| Gate | Placement | Why there |
|---|---|---|
| Free tier can't sell | `commerce.py`, **before** the order INSERT | The Stripe branch degrades to a manual pending order on any failure, so "never connect Stripe" would otherwise *be* the workaround for selling free. Scoped to `subtotal > 0` so $0 bookings, RSVPs and lead-gen forms — the free tier's whole value — keep working. |
| Creator fulfillment | `routes/shop.py` create + update | Update only re-checks when `fulfillment` is in `model_fields_set`, so an unrelated edit to a pre-existing product doesn't start 403-ing. |
| Site limit | `routes/sites.py` | Now `ent.site_limit` (NULL = unlimited). |
| Rider | `routes/rider.py` | Now `features.rider`. |
| Take rate | `commerce.py` | Computed once, passed to Stripe. |

---

## Stripe object model

- **Price immutability** — an admin price change creates a new `stripe.Price` on
  the same Product and repoints `is_current`. Existing subscribers keep their own
  `stripe_price_id` and are **grandfathered by default**. Migrating them is an
  explicit, separate admin action, never a side effect of editing a form field.
- **$1 for 30 days → monthly** — `mode="subscription"` with
  `subscription_data.trial_period_days` plus the $1 as
  `subscription_data.add_invoice_items`. Checkout **rejects non-recurring prices
  in `line_items`** in subscription mode, which rules out the obvious approach; a
  first-invoice coupon was rejected because the coupon amount is itself immutable
  and would need re-minting on every price edit. The card is captured up front
  and the first full invoice lands on day 31 — no cron, no conversion job.
  Eligibility is server-decided and one-shot: refused if the account has **any**
  prior subscription row.
- **Per-mailbox add-on** — an additional `SubscriptionItem` with `quantity` on
  the **same** subscription, not a second subscription: one invoice, one dunning
  state, one payment method. Increases invoice immediately (`always_invoice`) so
  provisioning is paid before it happens; decreases create prorations that credit
  the next invoice.
- **`trialing` and `past_due` are fully entitled.** `trialing` because the $1
  intro *is* a Stripe trial — gating it would mean the customer pays and gets
  nothing. `past_due` because Stripe retries a failed card for days, and dropping
  a merchant's storefront on the first retry failure would break a live business
  over a card that renews Thursday. Access ends at `unpaid`/`canceled`.

---

## Rollout

Enforcement ships **after** billing exists, or accounts selling today get cut off.

1. **Idempotency** (`stripeevt02`) — consumer-scoped dedupe ledger, shared
   service, dedupe added to Cappe's webhooks. Zero product change. ✅ done
2. **Schema** (`zzzzcappe26`) — tables, catalog seed, customer backfill,
   CHECK→FK. **Behaviour-neutral**: the seed reproduces today's rules exactly
   (`free.can_sell = true`, flat 200 bps). ✅ done
3. **Entitlements** — service + every call site, no behavioural delta. ✅ done
4. **Stripe + billing surfaces** — subscription methods, webhook dispatch,
   tenant billing routes, admin routes, seed script. ✅ done
5. **Admin UI + the flip** — Cappe admin screens, then
   `PATCH /admin/plans/free {"can_sell": false}` after customer comms. A single
   runtime toggle, instantly reversible — the whole payoff of putting this in a
   catalog rather than env constants. ⬜ frontend remaining
6. **Private email provisioning** — mailbox host (Migadu / Zoho / Improvmx vs
   self-hosted), DNS/MX, DKIM. Billing and entitlement side is done; the
   provisioning itself is a separate piece of work. ⬜ remaining

**Existing accounts** stay `free` and nothing has ever written `plan`, so nobody
is charged and nobody loses access. The only accounts whose behaviour changes at
the step-5 flip are free accounts that connected Stripe and are actively selling.
Query that set before flipping:

```sql
SELECT count(*) FROM cappe_accounts WHERE plan = 'free' AND stripe_charges_enabled;
```

and comp them onto a paid plan (`source='comp'`, `comped_until`) rather than
breaking live storefronts.

---

## Verification

- **Pure units** (`server/tests/cappe/test_cappe_entitlements.py`) — take-rate
  arithmetic, selling gate, fulfillment gate, fallback behaviour, cache
  invalidation. These encode money rules, so they are the highest-value tests
  here: a wrong `platform_fee_bps` silently over- or under-charges every merchant
  on that plan.
- **Webhook dedupe** — replay the same event id twice, assert one side effect;
  assert a handler raise releases the claim so Stripe's retry re-processes; assert
  two consumers can claim the same event independently.
- **Stripe CLI** against local dev (`./scripts/dev-remote.sh`, backend `:8001`):
  ```
  stripe listen --forward-to localhost:8001/api/cappe/domains/webhook
  stripe trigger checkout.session.completed
  stripe trigger customer.subscription.deleted
  ```
  Prod is in Stripe **test mode** (see root `CLAUDE.md`), so test cards are the norm.
- **End to end**: sign up → $1 intro checkout → confirm the subscription row and
  the plan flip → create a physical product on Creator (expect 403) → sell on a
  non-selling plan (expect refusal, **including** the no-Stripe manual-order path)
  → verify `cappe_orders.platform_fee_cents` matches the plan rate **and** the
  Stripe `application_fee_amount`.
- **Migrations**: author, commit, then
  `MIGRATE_REHEARSAL=1 DATABASE_URL=… alembic upgrade heads` against dev. Never
  run against prod without explicit approval.

### Deploy note

`server/scripts/seed_cappe_plans.py` must run once per environment **after** the
migration to mint the Stripe Products/Prices. Nothing is purchasable until it
does — `stripe_price_id` is NULL on every seeded price row, and checkout refuses
rather than guessing.

# Plan — Matcha Work Personal ($20/mo) + Channel Credit + Stripe Connect

## Context

**Scope: Matcha Work Personal ($20/mo consumer tier) + creator payouts + admin comp flow + unified billing config.**

**Top-level rule, non-negotiable:** No pricing number is hardcoded in a `.py` file after this plan ships. All numeric pricing lives in `platform_settings.billing` and is read at request time. Env vars only hold Stripe API credentials and webhook secrets — never prices, pack definitions, or fee percentages. Changing a price = admin edits a form = next checkout uses the new value. No code path, no deploy, no Stripe dashboard round-trip.

Company billing split:
- Company **base tier = manual invoicing** (not Stripe, out of scope here — do not touch the invoicing flow itself)
- Company **AI credit top-ups = existing Stripe flow** (`create_token_subscription_checkout` / token packs at `stripe_service.py`). Functionally unchanged, but the hardcoded `CREDIT_PACKS` dict and $40 Pro tier numbers migrate from module-level constants to `platform_settings.billing` lookups. Same Stripe API shape, same webhook handling, different read path for the numbers.
- Company users do NOT get channel credit (that's a Personal-only feature).

Matcha Work Personal is the $20/mo consumer tier. Individuals sign up, get AI tokens for their personal workspace + a $10/mo credit spendable against paid channels. **Creators must be individual (personal) accounts. Company users are not allowed to be paid channel creators — a company admin who wants to run a personal paid channel must create a separate individual account.** This simplifies the Stripe Connect flow (always user-level, never company-level) and keeps the creator-payout liability off company tenants. Promos are granted via 100% off Stripe coupons applied at checkout so the card is captured and auto-converts when the coupon expires.

We need four tightly-coupled additions:

1. **Stripe Connect (Express)** — creators onboard their own Stripe, receive payouts automatically
2. **$20/mo Matcha Work Personal tier** — for individuals, separate from the $40 Pro/Company tier
3. **$10/mo channel credit pool** — Personal subscribers get $10 spendable against paid channel subscriptions each month
4. **100% off Stripe coupon flow** — admin generates a signup URL with a coupon attached; user checks out at $0, card captured, auto-converts to $20/mo when coupon expires

Existing scaffolding to reuse:
- `stripe_webhook.py:160-196` dispatcher — add Personal-tier event handlers alongside existing company top-up ones. Personal subs keyed by `pack_id='matcha_work_personal'`; existing company top-up dispatch stays unaffected.
- `mw_subscriptions` + `upsert_subscription()` — reuse table; new rows with `pack_id='matcha_work_personal'`
- `mw_token_budgets` + `token_budget_service.reset_subscription_tokens` — reuse pattern for Personal sub's monthly token grant refresh, scoped to the user's auto-provisioned `is_personal=true` company
- `channel_payment_service.py` — rewrite `create_stripe_product_and_price` / `create_checkout_session` to accept `stripe_account=creator_account_id` (destination charges)
- `users.is_personal` flag + auto-provisioned personal workspace at `auth.py:2762` / `register_beta` at `auth.py:2667`
- Admin `POST /admin/individual-invites` endpoint (commit `d4251e4`) — extend to attach coupon + comp duration
- `platform_settings` table + cache pattern at `platform_settings.py` — add billing keys here
- `stripe_service.create_token_subscription_checkout` + company top-up packs — **leave untouched** (existing company AI credit flow, still works)

**Explicitly out of this plan** (do not touch):
- Company base tier billing (manual invoicing flow outside the app)
- Any channel-credit-like feature for company users (company users don't get the $10/mo credit; that's a Personal consumer perk)

**Touched by this plan** (config externalization, not behavior change):
- `stripe_service.CREDIT_PACKS` hardcoded dict → migrates to `platform_settings.billing.credit_packs`
- `stripe_service.FEE_CENTS` = 250 → migrates to `platform_settings.billing.credit_pack_processing_fee_cents`
- `stripe_service.FREE_SIGNUP_CREDITS` = 5.0 → migrates to `platform_settings.billing.free_signup_credit_dollars`
- `stripe_service.create_token_subscription_checkout` hardcoded $40 / 5M tokens / "Matcha Work Pro" → reads from `platform_settings.billing.pro_tier.{unit_amount_cents, tokens_per_cycle, product_name, product_description}`
- `token_budget_service.FREE_TOKEN_GRANT` = 1_000_000 → migrates to `platform_settings.billing.free_signup_token_grant`
- Checkout session shape (inline `price_data`) is unchanged — still works the same way against Stripe, just reading numbers from DB instead of Python constants

## Product decisions

### Where each knob lives

**Rule:** if a value changes because of **product/marketing strategy**, put it in `platform_settings` so admins edit it without deploy. If it's **infra** (env differs per environment), env var. If it's **structural logic** (not a number), hard-coded.

The `platform_settings` table + cached getter pattern at `server/app/core/services/platform_settings.py` already exists — used for `visible_features`, `risk_assessment_weights`, `matcha_work_model_mode`. Extend with billing keys. Admin UI at `client/src/pages/admin/Settings.tsx` is the editor.

**Env vars** — ONLY API credentials and infra. No prices, no IDs of specific SKUs:
- `STRIPE_SECRET_KEY` — sk_test / sk_live
- `STRIPE_WEBHOOK_SECRET` — rotates on test→live
- `STRIPE_PUBLISHABLE_KEY` — frontend-consumed

| Knob | Venue | Default | Notes |
|---|---|---|---|
| **Pro tier** — unit amount, tokens/cycle, name, description, enabled | `platform_settings.billing.pro_tier.*` | 4000c / 5M / "Matcha Work Pro" | Currently hardcoded in `stripe_service.create_token_subscription_checkout`; migrate |
| **Personal tier** — unit amount, tokens/cycle, channel credit, name, description, enabled | `platform_settings.billing.personal_tier.*` | 2000c / 1M / 1000c credit / "Matcha Work Personal" | All numeric, all admin-editable |
| **Credit packs** (one-time dollar packs) | `platform_settings.billing.credit_packs` (array) | `[twenty, fifty]` with base_cents, credits, label, description | Add/edit/remove whole packs from admin UI |
| Credit pack processing fee | `platform_settings.billing.credit_pack_processing_fee_cents` | 250 ($2.50) | Was `FEE_CENTS` constant |
| Free signup credit (business) | `platform_settings.billing.free_signup_credit_dollars` | 5.0 | Was `FREE_SIGNUP_CREDITS` constant |
| Free signup token grant | `platform_settings.billing.free_signup_token_grant` | 1_000_000 | Was `FREE_TOKEN_GRANT` in `token_budget_service.py` |
| Platform fee % on direct channel subs | `platform_settings.billing.channel_platform_fee_percent` | 15 | Tunable for promos, competitive pressure |
| Platform fee % on channel job postings ($200/mo) | `platform_settings.billing.job_posting_platform_fee_percent` | 50 | Per PAID_CHANNELS_PLAN (50/50 split) |
| Available comp coupon durations | `platform_settings.billing.comp_durations_months` | `[3, 6, 12]` + `forever` | Admin invite dropdown options |
| Min channel price cents | **Hard-coded** (`channel_payment_service.MIN_PRICE_CENTS = 50`) | 50 | Already hard-coded, leave |
| Max channel price cents | **Hard-coded** (`channel_payment_service.MAX_PRICE_CENTS = 99900`) | 99900 | Already hard-coded, leave |
| Credit rollover policy | **Hard-coded** (no rollover) | — | Structural logic, not a value |
| Partial credit application | **Hard-coded** (no, v1) | — | Structural logic |
| Multiple Personal subs per user | **Hard-coded** (no, DB unique constraint) | — | Structural |
| Refund policy | **Hard-coded** (Stripe default: cancel at period end) | — | Structural |
| Credit applies to $200 job postings? | **Hard-coded** (no — member subs only) | — | Structural |
| Company base tier (invoicing) | **Not touched — manual invoicing, out of scope** | — | — |

### Why not put everything in admin?

- Stripe price IDs: test-mode IDs don't work in live mode. If these are admin-managed, a misclick takes prod down. Env var keeps infra and business concerns separated.
- Min/max channel price: rarely changes, no commercial reason to tune. Hard-code stays.
- Structural logic (rollover etc.) isn't a value — it's code paths. Putting it in admin means maintaining both branches forever.

### Admin Settings.tsx — new "Billing (Matcha Work Personal)" section

Add a `PersonalBillingSettings` card at `client/src/pages/admin/Settings.tsx` showing:
- Channel credit cents/month ($10, editable — applies to next period renewal)
- Platform fee % on direct channel subs (15%, editable — applies to next subscription created)
- Platform fee % on channel job postings (50%)
- Personal tier monthly AI token grant (1M, editable)
- Comp duration options (multi-select: 3 mo / 6 mo / 12 mo — "forever" always allowed in admin invite)
- Read-only display of current Stripe mode (test vs live) and a link to the Stripe dashboard for audit

Copy labelled "Matcha Work Personal only" at top. Company billing is managed via invoicing outside the app — not configurable here.

Each save hits `PATCH /admin/platform-settings/billing` with the JSON blob, cache invalidates, new subscriptions pick up the change immediately. Existing subscriptions keep their original terms until next renewal.

### Service helper

Add to `server/app/core/services/platform_settings.py`:
```python
DEFAULT_BILLING_SETTINGS = {
    # Company Pro tier (existing, currently hardcoded in stripe_service)
    "pro_tier": {
        "enabled": True,
        "unit_amount_cents": 4000,
        "currency": "usd",
        "tokens_per_cycle": 5_000_000,
        "product_name": "Matcha Work Pro",
        "product_description": "5M AI tokens per month",
    },

    # Matcha Work Personal tier (new)
    "personal_tier": {
        "enabled": True,
        "unit_amount_cents": 2000,
        "currency": "usd",
        "tokens_per_cycle": 1_000_000,
        "product_name": "Matcha Work Personal",
        "product_description": "AI workspace + $10/mo channel credit",
        "channel_credit_cents": 1000,   # monthly credit issued to each Personal sub
    },

    # One-time credit packs (replaces hardcoded CREDIT_PACKS dict)
    "credit_packs": [
        {"pack_id": "twenty", "base_cents": 2000, "credits": 20.0,
         "label": "$20 AI Credits", "description": "$20 of AI usage"},
        {"pack_id": "fifty",  "base_cents": 5000, "credits": 50.0,
         "label": "$50 AI Credits", "description": "$50 of AI usage"},
    ],
    "credit_pack_processing_fee_cents": 250,   # was FEE_CENTS constant

    # Free grants on signup
    "free_signup_credit_dollars": 5.0,         # was FREE_SIGNUP_CREDITS constant
    "free_signup_token_grant": 1_000_000,      # was FREE_TOKEN_GRANT constant

    # Platform fees on paid channels (Stripe Connect destination charges)
    "channel_platform_fee_percent": 15,
    "job_posting_platform_fee_percent": 50,

    # Comp invite flow
    "comp_durations_months": [3, 6, 12],
}

async def get_billing_settings() -> dict: ...
def invalidate_billing_settings_cache() -> None: ...
```
Same 30-second cache TTL pattern as existing `visible_features` / `matcha_work_model_mode` getters. Merge with `DEFAULT_BILLING_SETTINGS` so partial admin overrides still return a complete config object.

## Architecture

### Money flow

```
┌──────────────────────────┐
│  User card               │
│  ($20/mo Personal)       │
└────────────┬─────────────┘
             │
             ▼
┌──────────────────────────┐
│  Platform Stripe balance │ ← revenue
└────────────┬─────────────┘
             │
             │  Personal user subs to paid channel A ($8/mo)
             │  credit[10] - 8 = 2 remaining
             │
             ▼
┌──────────────────────────┐
│  Creator A Connect acct  │ ← $8/mo destination charge
│  (funded by platform)    │   NOT the user
└──────────────────────────┘

Non-Personal user subs to paid channel B ($12/mo):
User card → platform checkout → destination charge to Creator B
  → amount: $12, application_fee_amount: $1.80 (15%)
  → platform keeps $1.80, creator gets $10.20
```

### Data model

**Stripe Connect on users** (new alembic migration):
```sql
ALTER TABLE users ADD COLUMN stripe_connect_account_id TEXT;
ALTER TABLE users ADD COLUMN stripe_connect_charges_enabled BOOLEAN DEFAULT false;
ALTER TABLE users ADD COLUMN stripe_connect_payouts_enabled BOOLEAN DEFAULT false;
ALTER TABLE users ADD COLUMN stripe_connect_onboarded_at TIMESTAMPTZ;
CREATE INDEX idx_users_stripe_connect_account_id ON users(stripe_connect_account_id) WHERE stripe_connect_account_id IS NOT NULL;
```

**Channel credit ledger** (new table — keyed by Stripe subscription cycle, NOT calendar month):
```sql
CREATE TABLE mw_channel_credits (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  stripe_subscription_id TEXT NOT NULL,         -- the Personal sub funding this credit period
  period_start TIMESTAMPTZ NOT NULL,            -- from invoice.period_start
  period_end TIMESTAMPTZ NOT NULL,              -- from invoice.period_end
  credit_cents INT NOT NULL,                    -- snapshot from platform_settings at issue time
  used_cents INT NOT NULL DEFAULT 0,
  source_charge_id TEXT,                        -- the Personal sub charge that funds this period;
                                                -- passed as Transfer.source_transaction on redemption
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(stripe_subscription_id, period_start)
);
CREATE INDEX idx_mw_channel_credits_user_period ON mw_channel_credits(user_id, period_start DESC);
```
One row per Stripe subscription cycle. Created in the `invoice.paid` webhook handler using `invoice.period_start`, `invoice.period_end`, and `invoice.charge` — no calendar math, no cron. Unused cents forfeit at `period_end`. The `UNIQUE` constraint handles webhook at-least-once delivery.

**Stripe customer ID on users** (for credit redemption Transfer linking + future self-serve billing portal):
```sql
ALTER TABLE users ADD COLUMN stripe_customer_id TEXT;
CREATE UNIQUE INDEX idx_users_stripe_customer_id ON users(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;
```
Populated on first `checkout.session.completed` webhook. Reused thereafter so repeat subscribes/cancels all hit the same Stripe customer.

**channel_members extension** (so we know whether a membership is credit-funded vs direct-paid):
```sql
ALTER TABLE channel_members ADD COLUMN funding_source TEXT DEFAULT 'direct';
-- 'direct' = user card (Branch B), 'credit' = redeemed via Personal credit (Branch A)
```
The renewal webhook only touches rows where `funding_source = 'credit'`.

**Stripe coupon cache** (durable, not module-level — so coupons don't multiply across deploys):
```sql
CREATE TABLE stripe_coupons (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stripe_coupon_id TEXT NOT NULL UNIQUE,
  percent_off INT NOT NULL,
  duration TEXT NOT NULL,                -- 'once' | 'repeating' | 'forever'
  duration_in_months INT,                -- null for once/forever
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(percent_off, duration, duration_in_months)
);
```
The comp-invite flow looks up by `(percent_off, duration, duration_in_months)`; creates the Stripe coupon only the first time each shape is requested.

**mw_subscriptions extension**: re-use existing table. Personal sub stored with `pack_id = 'matcha_work_personal'`. Existing columns sufficient.

**Comp tracking**: coupon ID stored on the Stripe subscription `discount.coupon.id`. No new column — read from Stripe when needed for admin views. Optionally cache in `mw_subscriptions.metadata JSONB` for easier admin listing.

### Stripe Connect onboarding flow

**Scope rule (permanent, not a v1 limit):** `stripe_connect_account_id` lives on `users`, not `companies`. **Only individual (personal) accounts can create paid channels.** Company users — even admins — are blocked from creating paid channels. Rationale: company tenants are billed by invoice and don't get a creator-payout liability mixed into their relationship with us; if a company admin wants to run a creator side channel they create a separate individual account. This is enforced server-side in `POST /channels` by rejecting any `paid_config` body when `current_user.role != 'individual'` (admin can override for testing).

1. **Creator opens Settings** → sees "Payouts" card. If `stripe_connect_account_id IS NULL`: "Connect Stripe" button.
2. **Click Connect** → `POST /api/stripe/connect/onboard` creates Express account via `stripe.Account.create(type='express', ...)` + `stripe.AccountLink.create(type='account_onboarding', return_url, refresh_url)`. Returns link URL.
3. **User redirected to Stripe-hosted KYC** → completes form, returns to `/work/settings/payouts?return=1`.
4. **Webhook `account.updated`** → read `charges_enabled` + `payouts_enabled` from event, update user row.
5. **Frontend polls `GET /api/stripe/connect/status`** on return → shows "✓ Connected" when `charges_enabled=true`.
6. **Paid channel creation gate**: `POST /channels` with `paid_config` checks creator's `charges_enabled`. If false: 403 with actionable message + link to Settings > Payouts.

### $20 Personal subscription flow

1. **User hits `/billing` or signup** → sees Personal tier at whatever `platform_settings.billing.personal_tier.unit_amount_cents` currently says.
2. **Click Subscribe** → `POST /api/matcha-work/billing/checkout?tier=personal` → creates `stripe.checkout.Session` with `mode='subscription'` and inline `line_items=[{price_data: {unit_amount: personal_tier.unit_amount_cents, recurring: {interval: 'month'}, product_data: {name: personal_tier.product_name, description: personal_tier.product_description}}}]`. Optional `discounts=[{coupon: coupon_id}]` for comped signups. No pre-created Stripe price IDs — Stripe creates the price records as a side effect of the first session, we don't reference them.
3. **Checkout completes** → `checkout.session.completed` webhook:
   - persists `users.stripe_customer_id` from the session (first time only)
   - calls `upsert_subscription()` (existing)
   - creates first `mw_channel_credits` row using `invoice.period_start` / `invoice.period_end` / `invoice.charge` from the attached invoice
   - grants matcha-work token budget per `platform_settings.billing.personal_token_grant`, scoped to the user's `is_personal=true` company (resolved via `users → clients → companies.is_personal=true`)
4. **Monthly renewal** → `invoice.paid` with `billing_reason='subscription_cycle'`:
   - resets token budget
   - inserts new `mw_channel_credits` row with `ON CONFLICT (stripe_subscription_id, period_start) DO NOTHING` for idempotency (Stripe delivers webhooks at-least-once)
   - triggers credit-funded channel renewal (see Branch A below — enumerates `channel_members WHERE funding_source='credit' AND user_id=...` and re-covers each)
5. **Cancel** (`customer.subscription.deleted` or `updated` with `cancel_at_period_end=true`):
   - flips Personal sub status
   - credits stop refreshing but current-period credits remain until `period_end` (`used_cents` frozen)
   - **schedule credit-funded channel memberships to expire at `period_end`**: stop future transfers, flip `subscription_status='canceled'` at expiry
   - send ONE notification on cancel event: "Your Personal subscription ends {period_end}. These channels will also expire then: [list]. Subscribe directly to keep access."

### Channel subscribe flow (2 branches)

**Branch A: Personal user with available credit (webhook-driven, no cron)**

First-time subscribe:
1. User clicks Subscribe on paid channel → `POST /api/channels/{id}/subscribe`
2. Backend checks: active Personal sub + current `mw_channel_credits` row for that sub + `credit_cents - used_cents >= channel.price_cents`
3. If yes, inside a single DB transaction:
   - Insert `channel_members` row: `subscription_status='active'`, `funding_source='credit'`, `paid_through=mw_channel_credits.period_end`
   - `UPDATE mw_channel_credits SET used_cents = used_cents + channel.price_cents WHERE id = $1`
   - Call:
     ```python
     stripe.Transfer.create(
       amount=channel.price_cents,
       currency='usd',
       destination=creator_stripe_connect_account_id,
       source_transaction=mw_channel_credits.source_charge_id,   # links transfer to the Personal sub charge that funds it
       metadata={
         'channel_id': str(channel_id),
         'user_id': str(user_id),
         'redemption_type': 'credit',
       },
     )
     ```
   - Wrap all three in a transaction — if Transfer fails, roll back the insert + update. No orphaned credit spend.
4. Channel access granted immediately.

Renewal (on Personal sub `invoice.paid` webhook, after new credit row is created):
1. Query `SELECT cm.channel_id, cm.user_id FROM channel_members cm WHERE cm.user_id = $user AND cm.funding_source = 'credit' AND cm.subscription_status IN ('active','past_due')`
2. For each membership, check `channel.price_cents <= (new_credit.credit_cents - new_credit.used_cents)`:
   - If yes: `Transfer.create` again with the new `source_charge_id`, increment `used_cents`, extend `paid_through = new_credit.period_end`
   - If no (e.g. admin lowered credit amount): flip `subscription_status='expired'`, remove access, send notification "Channel X is no longer covered by your credit ($Y needed, $Z available). Subscribe directly to keep access."
3. No cron. Stripe's webhook is the single source of truth for timing.

**Branch B: Non-Personal user (or Personal with insufficient credit)**
1. `POST /api/channels/{id}/subscribe` → create `checkout.Session` with destination charge:
   ```python
   stripe.checkout.Session.create(
     mode='subscription',
     line_items=[{'price': channel_stripe_price_id, 'quantity': 1}],
     subscription_data={
       'application_fee_percent': fee_pct,
       'transfer_data': {'destination': creator_stripe_connect_account_id},
     },
     success_url=...,
     cancel_url=...,
   )
   ```
   where `fee_pct = platform_settings.billing.channel_platform_fee_percent` (default 15). Note: in `mode='subscription'`, `payment_intent_data` is ignored — only `subscription_data` applies.
2. User card charged monthly, (100 - fee_pct)% → creator, fee_pct% → platform.
3. On webhook, `channel_members.funding_source='direct'`.

### Admin comp invite flow

1. **Admin Individuals page** → "Generate Signup URL" button (already built `d4251e4`) gets expanded modal:
   - Email (required)
   - Comp type: dropdown populated from `platform_settings.billing.comp_durations_months` + `none` + `forever`
2. Frontend `POST /api/admin/individual-invites` now accepts `{email, comp_duration: 'none'|'3_months'|'6_months'|'12_months'|'forever'}`
3. Backend creates (or reuses) a `beta_invitation`. For non-`none` comp:
   - Looks up the Stripe coupon in the `stripe_coupons` table by `(percent_off=100, duration, duration_in_months)` triple. If not found, calls `stripe.Coupon.create(...)` and inserts the new row. Never create more than one coupon per shape.
   - Stores `coupon_id` on `beta_invitations` (new column)
4. **Signup page** (`/register/beta?token=...`) reads the invitation, if it has a `coupon_id`, pre-attaches on the checkout session so the user sees "$20/mo — 3 months free" on Stripe-hosted checkout.
5. **Checkout completes at $0** → `checkout.session.completed` webhook runs normal `upsert_subscription()`, grants credit + token budget. User has real subscription in their Stripe customer portal. Auto-charges at coupon expiry.

## Critical files to modify

**Backend (server/app/)**:
- `alembic/versions/{new}_add_stripe_connect_and_channel_credits.py` — migration for user columns + `mw_channel_credits` + `beta_invitations.coupon_id`
- `core/services/platform_settings.py` — **extend** with `get_billing_settings()` + `invalidate_billing_settings_cache()` (reuse existing cache pattern)
- `core/routes/admin.py` — new `PATCH /admin/platform-settings/billing` endpoint (validates keys, writes to `platform_settings`, invalidates cache)
- `core/services/stripe_service.py` — add `create_personal_subscription_checkout(user_id, coupon_id?)`, add coupon helpers. **Do NOT modify** `create_token_subscription_checkout` (company top-up flow)
- `core/services/channel_payment_service.py` — rewrite `create_stripe_product_and_price` to accept `stripe_account=creator_id`, add `create_channel_checkout_for_non_personal(...)` with destination charge, add `redeem_credit_and_transfer(user_id, channel_id)` for credit branch
- `core/services/connect_service.py` — NEW — Express account creation, account link generation, status fetch
- `core/routes/stripe_connect.py` — NEW — `POST /stripe/connect/onboard`, `GET /stripe/connect/status`
- `core/routes/stripe_webhook.py` — handle `account.updated` (update user Connect flags), `customer.subscription.created/updated/deleted` for Personal tier (update `mw_subscriptions` + `mw_channel_credits`), handle `invoice.paid` for Personal tier refresh. Existing company top-up dispatch unchanged.
- `core/routes/channels.py:create_channel` — gate `paid_config` on `charges_enabled=true`
- `matcha/routes/billing.py` — add Personal tier endpoint (separate from existing company packs endpoint)
- `matcha/services/channel_credit_service.py` — NEW — `grant_monthly_credit`, `check_available`, `consume`, `list_current_period_credit(user_id)`
- `core/routes/admin.py:create_individual_invite` — accept `comp_duration`, create/reuse coupon, store on invite
- `core/routes/auth.py:register_beta` — read invitation's coupon_id, forward to checkout session creation

**Frontend (client/src/)**:
- `pages/admin/Settings.tsx` — **extend** with "Billing (Matcha Work Personal)" card (edit `platform_settings.billing` JSON)
- `pages/work/Settings.tsx` (or new Payouts page) — Stripe Connect card: "Connect Stripe" button, status, disconnect
- `pages/billing/Billing.tsx` — add Personal tier card, show credit status
- `pages/admin/Individuals.tsx` — "Generate Signup URL" modal gets comp duration radio (options pulled from `billing.comp_durations_months` setting)
- `components/channels/CreateChannelModal.tsx` — if creator not onboarded to Connect, show "Connect Stripe first" instead of the paid toggle
- `components/channels/PaidChannelJoinWizard.tsx` — show credit status ("Using $10 channel credit — free this month") when applicable
- `api/stripe.ts` — NEW — `connectOnboard`, `connectStatus` fetchers
- `api/billing.ts` — extend existing — `getChannelCredit`, `subscribePersonal`

**Config — split across three surfaces**:

1. **Env vars** (`config.py` + `.env.backend`) — ONLY API credentials:
   - `STRIPE_SECRET_KEY` — test/live rotation
   - `STRIPE_WEBHOOK_SECRET` — test/live rotation
   - `STRIPE_PUBLISHABLE_KEY` — frontend-consumed
   - **No price IDs, no pack definitions, no fee percentages.** Every checkout session uses inline `price_data` that reads from `platform_settings.billing` at request time.

2. **`platform_settings.billing` JSONB row** (admin-editable, see Billing Settings table above for the full key set — pro_tier, personal_tier, credit_packs, fees, free grants, comp durations)

3. **Hard-coded constants** (`channel_payment_service.py`):
   - `MIN_PRICE_CENTS`, `MAX_PRICE_CENTS` — already there, leave alone
   - Credit ledger policy (rollover, partial application) — in service code, not config

## Phased rollout

Ship in four independent phases — each deployable and testable alone:

**Phase 1 — Stripe Connect Express onboarding (no UI gate yet)**
- Migration: add `users.stripe_connect_*` columns
- Service + routes for onboard/status
- Webhook handler for `account.updated`
- Settings UI card
- Creators can connect but nothing yet uses the account_id
- **Ship gate:** creator completes full KYC in test mode, `charges_enabled=true` lands in DB

**Phase 2 — Rewrite channel payments to use Connect**
- Update `channel_payment_service.create_stripe_product_and_price` → pass `stripe_account=creator_id`
- Update checkout session creation → destination charge with app fee (read fee % from `platform_settings.billing.channel_platform_fee_percent`)
- Gate `create_channel(paid_config)` on `charges_enabled`
- **Ship gate:** non-Personal user can subscribe, creator receives transfer in Stripe dashboard

**Phase 3 — $20 Personal tier + coupon flow + credit ledger + admin billing settings**
- Create Stripe product `matcha_work_personal` in test dashboard, record price ID in config
- Migration: `mw_channel_credits` + `beta_invitations.coupon_id`
- `platform_settings.py` billing getter + admin UI Settings card
- Services: `channel_credit_service`, extend `stripe_service`
- Admin invite with comp duration modal
- Webhook: `invoice.paid` for Personal → refresh credit row
- Channel subscribe endpoint branches on credit availability
- **Ship gate:** admin generates 3-month-free invite, user completes $0 checkout, card captured, credit granted, user subscribes to paid channel at no further charge, creator receives credit transfer

**Phase 4 — Live switch**
- No Stripe product/price records to pre-create — everything uses inline `price_data` at checkout time. Live flip only requires swapping API keys (below)
- Swap secrets to `sk_live_...`, update webhook secrets for live
- Clear test-mode dead data from DB:
  - Channels: `UPDATE channels SET stripe_product_id = NULL, stripe_price_id = NULL WHERE is_paid = true` (forces re-creation against live account)
  - Channel subscriptions: `DELETE FROM channel_members WHERE stripe_subscription_id IS NOT NULL`
  - Personal tier test subs: `DELETE FROM mw_subscriptions WHERE pack_id = 'matcha_work_personal'` (forces test users to re-subscribe against live price; skip if zero test users)
  - Channel credits: `DELETE FROM mw_channel_credits` (tied to test subscriptions, rebuild on next real renewal)
  - Stripe coupons cache: `DELETE FROM stripe_coupons` (coupon IDs are test-mode-scoped, must regenerate)
- Smoke test against live card (low-value Personal tier + small paid channel subscription)

## Reuse checklist (verify before each phase)

- [ ] `create_token_subscription_checkout` pattern at `stripe_service.py:~150` — copy structure for Personal tier, **do not modify original**
- [ ] `upsert_subscription` at `billing_service.py:506` — already handles INSERT/UPDATE with pack_id, reuse as-is
- [ ] `stripe_webhook.py` event dispatcher — add handlers to existing switch, don't create new route
- [ ] `auth.py:register_beta` flow already creates personal workspace — extend, don't replace
- [ ] `admin.py:create_individual_invite` (commit `d4251e4`) — extend with comp_duration, don't create parallel endpoint
- [ ] `channel_payment_service._ensure_stripe` — keep, add `_with_connect_account` variant that passes `stripe_account` header
- [ ] `platform_settings.py` cache pattern — follow same 30s TTL + getter/invalidator structure as `visible_features` / `matcha_work_model_mode`

## Verification

Run against Stripe **test mode**. Stripe provides test Connect accounts and test cards.

**Phase 1:**
1. Log in as individual user, open Settings → Payouts
2. Click "Connect Stripe" → Stripe-hosted onboarding form opens
3. Fill with test values (Stripe provides a `test mode` shortcut)
4. Return to app → Settings shows "✓ Connected"
5. Verify `users.stripe_connect_account_id` populated, `charges_enabled=true`
6. Test webhook via Stripe CLI `stripe trigger account.updated`

**Phase 2:**
1. Connected creator creates paid channel ($5/mo)
2. Stripe dashboard shows product + price on CREATOR's connected account, not platform
3. Log in as different user (no Personal sub), click Subscribe
4. Stripe checkout loads, pay with `4242 4242 4242 4242`
5. Webhook fires → `channel_members` row inserted
6. Stripe dashboard shows: platform charged $5, split $4.25 → creator, $0.75 app fee → platform
7. Creator dashboard shows balance

**Phase 3:**
1. Admin opens Settings page → "Billing (Matcha Work Personal)" card → adjusts channel credit to $15, saves → cache invalidates
2. Admin "Generate Signup URL" with `3 months free` → URL copied
3. Open URL in incognito, fill register form → Stripe checkout opens showing "$20/mo — first 3 months free, then $20/mo"
4. Pay with test card → checkout completes at $0
5. Back in app, Settings shows "Matcha Work Personal" subscription + "Channel credit: $15 of $15 remaining this month"
6. Subscribe to a $8/mo paid channel → no charge, credit drops to $7
7. Try subscribing to a $10/mo channel → works, credit drops to $-3? NO — rejected because $10 > $7. ("Insufficient credit, upgrade or pay direct")
8. Subscribe to a $5/mo channel → works, credit drops to $2
9. Stripe dashboard: creator received $8 + $5 via transfers from platform
10. Admin Individuals page shows "Comped until [date 3 months out]"
11. Simulate time passing: manually trigger `invoice.paid` → new credit row at $15 (current setting), budget refreshed

**Regression:**
- Company user with existing Stripe token top-up flow can still buy credits (no change to their flow, still uses `create_token_subscription_checkout`)
- Non-Personal users can still subscribe to paid channels directly (pay creator, no credit)
- Creating free channels doesn't hit Connect gate

## Out of scope for v1 (name explicitly)

- Multiple Personal pricing tiers (e.g. $40 tier with $25 credit)
- Credit rollover across months
- Partial credit application (must cover channel fully)
- Creator Stripe balance dashboard inside Matcha (they use Stripe's own dashboard)
- Refund flow beyond Stripe's default (cancel-at-period-end)
- Custom Connect accounts (white-label) — Express only
- Credit on job postings ($200/mo) — member channel subs only
- Localized currencies — USD only
- Tax handling — Stripe Tax not enabled in this phase
- Channel credit for company users (company users get AI top-ups via existing Stripe flow, no channel credit)

## Open questions (tagged for before-build review)

- **Q1 (before live):** Credit ledger edge case — user cancels mid-month. Default **yes, credit remains until `current_period_end`, `used_cents` frozen at cancel time; credit-funded channel memberships expire at the same `period_end` with one grace-period notification**.
- **Q2 (before build):** Phase ordering — ship Phase 1 (Connect onboarding) alone, or bundle with Phase 2 (rewrite channel payments to use Connect)? Default **bundled** — Phase 1 alone does nothing user-visible.
- **Q3 (resolved):** Creators are individual accounts only — company users cannot create paid channels, period. Not a v1 limit; a permanent product rule.
- **Q4 (before build):** Admin credit-amount reduction mid-subscription. If admin drops channel credit from $10 to $5, existing credit-funded memberships at $8 get auto-expired on next renewal. Default **yes, expire + notify at next `invoice.paid`**. Alternative: grandfather existing memberships at original credit amount, only apply to new subscriptions. Pick one.
- **Q5 (before build):** Waitlist → comp invite conversion. `newsletter_subscribers` with `source='matcha_work_beta_waitlist'` (already shipped) is the waitlist. Admin reviews the list, cherry-picks high-value signups, and generates individual-invites with N months free. Is the curation fully manual for v1, or do we auto-comp N% of waitlist signups on an interval?
- **Q6 (nice-to-have):** Should the admin Settings UI surface a live preview of "if you change this, X existing subs will be affected at next renewal"? Default **no for v1**, but a "Settings changed on [date]" audit log would help.

## Implementation notes (minor — inline checks during build)

- **N1.** Admin `platform_settings.billing` cache is in-memory per backend replica with 30s TTL. In multi-replica deploys, admin edits take up to 30s to propagate across instances. Add UI copy under the Save button: "Changes propagate within 30 seconds."
- **N2.** Personal tier token grant scoping: `mw_token_budgets` is keyed by `company_id`. For Personal users, resolve via `users → clients → companies WHERE is_personal = true` — NOT via a nonexistent `users.company_id` column. Spelling this out so implementers don't waste time hunting.
- **N3.** Webhook idempotency is handled by DB constraints:
  - `mw_channel_credits` UNIQUE `(stripe_subscription_id, period_start)` absorbs duplicate `invoice.paid` deliveries via `ON CONFLICT DO NOTHING`
  - `channel_members` UNIQUE `(channel_id, user_id)` handles duplicate subscribe clicks
  - Credit redemption transaction wraps DB updates + Transfer.create in a try/except; on Stripe API failure, roll back the DB changes
- **N4.** `users.stripe_customer_id` should be populated on first `checkout.session.completed`. If the user already has a customer ID (e.g. from a prior Personal sub), reuse it on subsequent subscribe flows via `checkout.Session.create(customer=existing_id)` so their saved cards and customer history follow them.

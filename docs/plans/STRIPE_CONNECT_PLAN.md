# Stripe Connect revenue share for channel mods (deferred)

## Context

The prior work in this feature line (`feat(channels)`, commit `0f80f2f`) added the creator approval gate, recruiter tier, and mod message deletion. The mod role now exists as a real moderation tool, but moderators have no economic incentive. The originating ask: creators should be able to hand mods a percentage cut of their paid channel's subscription revenue (and eventually tips / gifting) as compensation for moderation work.

There is **zero Stripe Connect infrastructure** in the repo today. Verified:

- No `stripe_connect*` columns on users.
- No `AccountLink` / `stripe.Account.create` calls.
- No onboarding routes, no webhook handler for `account.updated`.
- `client/src/components/channels/CreateChannelModal.tsx:574,719` has aspirational copy ("You'll receive payouts automatically") that is **not** backed by code.
- `server/app/matcha/services/matcha_work_ai.py:220` notes "Stripe Connect creator payouts are planned but not yet live."

Starting from scratch.

## MVP decisions (pre-approved)

1. **Express** Connect accounts (Stripe-hosted KYC, platform brand).
2. **Pure pass-through** splits — no platform fee on top of mod cuts. Creator gets the remainder.
3. **Silently skip** mods whose `payouts_enabled` flag is false — their share goes to the creator for that cycle. No escrow. UI tells them to finish onboarding or forfeit earnings.
4. **Tips / gifting pool deferred** — ship subscription revenue share only. Tip fanout is a follow-up on `payment_intent.succeeded` with `source_type='tip'`.
5. **Platform Connect dashboard toggle** must be turned on manually in Stripe before this ships. Not something this plan can automate.

## Prerequisites (manual, outside code)

- Enable Connect in the Stripe dashboard (Settings → Connect → Get started).
- Pick Express as the account type.
- Set the platform's branding + return URLs.
- Confirm the production webhook endpoint subscribes to `account.updated` in addition to the existing `checkout.session.completed` / `invoice.paid` / `invoice.payment_failed` events.

## Design

### Schema

One migration. All additive.

```sql
ALTER TABLE users
  ADD COLUMN stripe_connect_account_id text,
  ADD COLUMN stripe_connect_charges_enabled boolean NOT NULL DEFAULT false,
  ADD COLUMN stripe_connect_payouts_enabled boolean NOT NULL DEFAULT false;

CREATE UNIQUE INDEX idx_users_stripe_connect_account_id
  ON users(stripe_connect_account_id)
  WHERE stripe_connect_account_id IS NOT NULL;

ALTER TABLE channel_members
  ADD COLUMN mod_revenue_share_bps integer NOT NULL DEFAULT 0,
  ADD CONSTRAINT channel_members_mod_revenue_share_bps_range
    CHECK (mod_revenue_share_bps BETWEEN 0 AND 10000);

-- Audit every Stripe Transfer we create on behalf of a mod.
CREATE TABLE channel_mod_payouts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id uuid NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    mod_user_id uuid NOT NULL REFERENCES users(id),
    source_type text NOT NULL
      CHECK (source_type IN ('channel_subscription','tip','job_posting')),
    source_invoice_id text,
    source_payment_intent_id text,
    amount_cents integer NOT NULL,
    share_bps integer NOT NULL,
    stripe_transfer_id text,
    destination_account_id text NOT NULL,
    status text NOT NULL DEFAULT 'pending'
      CHECK (status IN ('pending','succeeded','failed','skipped')),
    failure_reason text,
    created_at timestamptz NOT NULL DEFAULT NOW()
);

-- Idempotency: one transfer per (invoice, mod).
CREATE UNIQUE INDEX idx_channel_mod_payouts_invoice_mod
  ON channel_mod_payouts(source_invoice_id, mod_user_id)
  WHERE source_invoice_id IS NOT NULL;

CREATE INDEX idx_channel_mod_payouts_mod_created
  ON channel_mod_payouts(mod_user_id, created_at DESC);
```

### Backend

**a. Stripe helpers** — new methods in `server/app/core/services/stripe_service.py`:

```python
async def create_connect_account(self, user_id: UUID, email: str) -> str:
    """stripe.Account.create(type='express', country='US', email=email,
    capabilities={'transfers': {'requested': True}}, metadata={'user_id': ...})
    Returns the new acct_... id."""

async def create_account_link(self, account_id: str, refresh_url: str, return_url: str) -> str:
    """stripe.AccountLink.create(account=..., type='account_onboarding').
    Returns the URL to redirect the mod to."""

async def create_transfer(
    self, destination_account_id: str, amount_cents: int,
    source_type: str, source_id: str, transfer_group: str,
) -> str:
    """stripe.Transfer.create(amount, currency='usd', destination=...,
    transfer_group=..., metadata={source_type, source_id}).
    Returns tr_... id. Caller handles idempotency via the audit table's
    unique index."""
```

**b. Onboarding routes** — new file `server/app/core/routes/connect.py`, mounted at `/users`:

- `POST /users/me/connect/onboard` → create Stripe account if missing, return AccountLink URL.
- `GET /users/me/connect/status` → return `{account_id, charges_enabled, payouts_enabled}`.
- `POST /users/me/connect/dashboard-link` → `stripe.Account.create_login_link(account_id)` for ready accounts so mods can view their Stripe Express dashboard.

**c. Webhook handler** — extend `server/app/core/routes/stripe_webhook.py`:

- New branch on `event_type == 'account.updated'`. Read the Connect account's `charges_enabled` and `payouts_enabled`, lookup the user by `stripe_connect_account_id`, update the two boolean columns.

**d. Revenue share assignment** — new routes:

- `PATCH /channels/{id}/members/{user_id}/revenue-share` body `{bps: int}`. Owner-only. Server validates `0 <= bps <= 10000` and SUM(new bps + all other mod bps) <= 10000; rejects if it would exceed 100%.
- Extend existing `GET /channels/{id}` so the members list includes `mod_revenue_share_bps` so the settings UI can render the current splits.

**e. Payout fanout** — hook into existing `invoice.paid` webhook in `stripe_webhook.py` (search for `handle_subscription_renewed`):

```python
if is_channel_sub:
    await handle_subscription_renewed(stripe_sub_id, period_end, amount)
    # NEW:
    await fanout_channel_subscription_payouts(
        stripe_sub_id=stripe_sub_id,
        stripe_invoice_id=stripe_invoice_id,
        amount_cents=amount,
    )
```

`fanout_channel_subscription_payouts` lives in a new `server/app/core/services/channel_payout_service.py`:

1. Look up the channel by `stripe_subscription_id` on `channel_members` (the subscribing member row).
2. Find the channel owner and every mod with `mod_revenue_share_bps > 0`.
3. For each mod: `share = amount_cents * bps // 10000`.
4. If the mod has `stripe_connect_payouts_enabled = true` AND a Stripe account id: create Transfer via the helper, insert `channel_mod_payouts` row with status=`succeeded` and `stripe_transfer_id`.
5. Otherwise insert row with status=`skipped` and `failure_reason='connect_not_ready'`. Share is forfeited to creator.
6. Idempotent: the unique index on `(source_invoice_id, mod_user_id)` means retried webhooks are a no-op.
7. Creator's cut is implicit — remaining funds stay on the platform and route to their own Connect account via the platform's existing payout schedule (out of scope for this feature; creator payout onboarding is the same onboarding route).

### Frontend

**a. API client** — new `client/src/api/stripeConnect.ts`:

```ts
export interface ConnectStatus {
  account_id: string | null
  charges_enabled: boolean
  payouts_enabled: boolean
}

export const getConnectStatus = () => api.get<ConnectStatus>('/users/me/connect/status')
export const startConnectOnboarding = (returnUrl: string, refreshUrl: string) =>
  api.post<{ url: string }>('/users/me/connect/onboard', { return_url: returnUrl, refresh_url: refreshUrl })
export const getConnectDashboardLink = () =>
  api.post<{ url: string }>('/users/me/connect/dashboard-link')
```

Add to `client/src/api/channels.ts`:

```ts
export const setMemberRevenueShare = (channelId: string, userId: string, bps: number) =>
  api.patch(`/channels/${channelId}/members/${userId}/revenue-share`, { bps })
```

Also bump `ChannelMember` type to include `mod_revenue_share_bps?: number`.

**b. UserSettings — Creator payouts section.** New component `client/src/components/profile/CreatorPayoutsSection.tsx`, embedded in `UserSettings.tsx` below `ProfileResumeSection`:

- Fetches `getConnectStatus()` on mount.
- If `account_id` is null → "Set up payouts" button → calls `startConnectOnboarding` with current URL as return/refresh, `window.location.href = url`.
- If onboarding started but `charges_enabled/payouts_enabled` not both true → "Finish payout setup" button (re-runs onboarding, Stripe handles resume).
- If ready → green state, "Open Stripe dashboard" button (calls `getConnectDashboardLink`).
- Payout history list (last 20 from a new endpoint `GET /users/me/payouts` — small extra route).

**c. ChannelSettingsPanel — revenue share column.** Edit `client/src/components/channels/ChannelSettingsPanel.tsx`:

- For each member with role=`moderator` show a percentage input bound to `mod_revenue_share_bps / 100`.
- Owner-only.
- "Save" button calls `setMemberRevenueShare`. Optimistic update.
- Show the sum of all mod shares + creator's implicit remainder as a pie or progress bar.
- Warn (red) when sum > 100%.
- Link to the mod's `stripe_connect_payouts_enabled` status — if false, show an amber "mod has not set up payouts — their share will be forfeited" warning next to the input.

### Deferred follow-ups (not this plan's critical path)

- **Tips / gifting fanout.** Same pattern on `payment_intent.succeeded` with `source_type='tip'`. Needs a `tips` table that records `channel_id + tipper_id + amount + payment_intent_id`. Touches `channel_payment_service.create_tip_checkout`.
- **Job posting fee fanout.** Recruiter pays the channel fee today; mods who helped curate could get a cut. Lower priority than tips.
- **Escrow for unready mods.** If we want to hold funds until the mod onboards Connect, need an `escrowed_payouts` table and a catch-up cron. Product decision — MVP forfeits to creator.
- **Platform fee.** Currently pure pass-through. If we ever want to take a cut, add a `platform_fee_bps` in the fanout calc.
- **1099 reporting.** Stripe Connect Express generates tax forms automatically, but US tax compliance is the platform's legal responsibility. Review before shipping to production with real mods.

## Files to create / modify (when this gets picked up)

**New:**
- `server/alembic/versions/zzx4y5z6a7b8_stripe_connect_revenue_share.py`
- `server/app/core/routes/connect.py`
- `server/app/core/services/channel_payout_service.py`
- `client/src/api/stripeConnect.ts`
- `client/src/components/profile/CreatorPayoutsSection.tsx`

**Modified:**
- `server/app/core/services/stripe_service.py` — 3 new Connect helpers
- `server/app/core/routes/stripe_webhook.py` — `account.updated` branch, `invoice.paid` fanout call
- `server/app/core/routes/channels.py` — member response includes `mod_revenue_share_bps`, new PATCH route
- `server/app/core/routes/__init__.py` — register connect router
- `client/src/api/channels.ts` — `setMemberRevenueShare`, `ChannelMember.mod_revenue_share_bps`
- `client/src/pages/app/UserSettings.tsx` — embed `CreatorPayoutsSection`
- `client/src/components/channels/ChannelSettingsPanel.tsx` — revenue share column

## Rollout / verification

1. **Stripe dashboard**: Enable Connect, pick Express, set branding, subscribe webhook to `account.updated`.
2. **Migration**: `cd server && alembic upgrade head`.
3. **Onboarding smoke**: as a test mod, hit `POST /users/me/connect/onboard`, complete Stripe's Express onboarding with test data, return → verify `users.stripe_connect_account_id` set, both capability flags true after `account.updated` webhook fires.
4. **Revenue share assign**: as channel owner, PATCH a mod's bps to 2500 (25%). Verify rejection when sum > 10000.
5. **Payout fanout**: trigger a channel subscription renewal (Stripe CLI `trigger invoice.paid` with a test invoice targeting a channel sub). Verify `channel_mod_payouts` rows: one succeeded per ready mod, one skipped per unready mod. Verify Stripe dashboard shows the Transfer.
6. **Idempotency**: replay the webhook — expect zero duplicate transfers thanks to the unique index.
7. **Client**: mod visits Settings → Creator payouts → walks onboarding → returns → sees ready state. Owner visits channel settings → sets a split → sees optimistic update.

## Risk notes

- **Real money movement on prod.** Test with Stripe test-mode keys end to end before flipping production keys.
- **Partial-refund semantics.** If a member refunds a channel sub mid-cycle, Stripe creates a refund — we're not handling reversal of already-paid mod transfers. First-pass: ignore and let the platform eat the cost; add `channel_mod_payouts.reversed_at` in a follow-up.
- **Account deletion.** If a mod closes their Stripe account, `account.updated` flips `payouts_enabled=false`. Subsequent payouts become skipped automatically. Fine for MVP.
- **Non-US mods.** Express defaults to US. Cross-border needs `country` negotiation and international KYC. MVP is US-only.

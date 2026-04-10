# Paid Chat Channels with Auto-Removal for Inactivity

## Overview

Channel creators can make paid channels with a monthly subscription. Members must actively contribute (send messages, upload files) to stay in. Inactive members are auto-removed. Removed members cannot rejoin for 1 week after their billing period ends.

---

## Business Rules

1. **Paid channels** — Creator sets a monthly price when creating a channel
2. **Contribution = activity** — Only sending messages and uploading files count as activity (not reading)
3. **Inactivity threshold** — Creator sets the number of days of no contribution before auto-removal (e.g. 7, 14, 30 days)
4. **Warning period** — Members get warned N days before removal (creator-configurable)
5. **Cooldown on removal** — Removed members cannot rejoin until 1 week after their current billing month ends
6. **Owner/moderator exemption** — Owners and moderators are exempt from inactivity removal
7. **No prorated refunds** — Removed members keep access until billing period ends, then get removed + cooldown starts

---

## Data Model Changes

### Alter `channels` table

| Column                      | Type      | Default | Description                                      |
|-----------------------------|-----------|---------|--------------------------------------------------|
| `is_paid`                   | boolean   | false   | Whether channel requires payment                 |
| `price_cents`               | integer   | null    | Monthly price in cents (e.g. 500 = $5.00)        |
| `currency`                  | text      | 'usd'   | ISO currency code                                |
| `inactivity_threshold_days` | integer   | null    | Days of no contribution before removal           |
| `inactivity_warning_days`   | integer   | 3       | Days before removal to send warning              |
| `stripe_product_id`         | text      | null    | Stripe product ID for this channel               |
| `stripe_price_id`           | text      | null    | Stripe price ID for the monthly subscription     |

### Alter `channel_members` table

| Column              | Type        | Default | Description                                       |
|---------------------|-------------|---------|---------------------------------------------------|
| `last_contributed_at` | timestamptz | null  | Last message sent or file uploaded                |
| `subscription_id`   | text        | null    | Stripe subscription ID                            |
| `subscription_status` | text      | null    | 'active', 'past_due', 'canceled'                  |
| `paid_through`       | timestamptz | null   | End of current paid billing period                |
| `removed_for_inactivity` | boolean | false  | Whether member was removed for inactivity         |
| `removal_cooldown_until` | timestamptz | null | Date after which member can rejoin               |

### New table: `channel_payment_events`

| Column       | Type        | Description                                    |
|--------------|-------------|------------------------------------------------|
| `id`         | uuid PK     |                                                |
| `channel_id` | uuid FK     | Channel                                        |
| `user_id`    | uuid FK     | Member                                         |
| `event_type` | text        | 'payment_success', 'payment_failed', 'refund', 'removal' |
| `amount_cents` | integer   | Amount involved                                |
| `stripe_event_id` | text   | Stripe event reference                         |
| `metadata`   | jsonb       | Extra details                                  |
| `created_at` | timestamptz |                                                |

---

## Client-Side Changes (`client/src/`)

### 1. API Layer (`api/channels.ts`)

**New types:**
- `PaidChannelConfig` — `{ is_paid, price_cents, currency, inactivity_threshold_days, inactivity_warning_days }`
- `MemberActivity` — extends `ChannelMember` with `last_contributed_at`, `subscription_status`, `days_until_removal`
- `ChannelPaymentInfo` — `{ is_paid, price_cents, currency, is_subscribed, paid_through, can_rejoin, cooldown_until }`

**New/updated functions:**
- `createChannel()` — add optional `paid_config` parameter
- `getChannelPaymentInfo(channelId)` — GET `/channels/{id}/payment-info`
- `createChannelCheckout(channelId)` — POST `/channels/{id}/checkout` → returns Stripe checkout URL
- `cancelChannelSubscription(channelId)` — POST `/channels/{id}/cancel-subscription`
- `updateChannelPaidSettings(channelId, config)` — PATCH `/channels/{id}/paid-settings`
- `getMemberActivity(channelId)` — GET `/channels/{id}/member-activity`

### 2. Create Channel Modal (`components/channels/CreateChannelModal.tsx`)

Add collapsible "Paid Channel" section below visibility:
- Toggle: "Make this a paid channel"
- When enabled, show:
  - **Price** — number input with currency display (e.g. `$5.00/mo`)
  - **Inactivity removal** — dropdown: 7 / 14 / 21 / 30 days
  - **Warning period** — dropdown: 1 / 2 / 3 / 5 / 7 days before removal
  - Info text: "Members who don't send messages or upload files for X days will be automatically removed. Removed members can rejoin 1 week after their billing period ends."

### 3. Paid Channel Join Gate (`components/channels/PaidChannelGate.tsx`)

Shown instead of the free "Join Channel" button when `is_paid = true`:
- Channel name and description
- Price badge: "$5.00/month"
- Inactivity policy summary: "Stay active by contributing at least once every 14 days"
- Cooldown notice (if applicable): "You can rejoin after Apr 20, 2026"
- "Subscribe & Join" button → calls `createChannelCheckout()` → redirects to Stripe
- Back link

### 4. Channel Settings Panel (`components/channels/ChannelSettingsPanel.tsx`)

Slide-out or modal for channel owner, accessible from ChannelView header:
- **General** — name, description (existing)
- **Paid Settings** (if `is_paid`):
  - Current price display
  - Inactivity threshold (editable dropdown)
  - Warning period (editable dropdown)
  - Member activity summary: X active / Y at risk / Z warned
- **Revenue** (if `is_paid`):
  - Current subscriber count
  - Monthly recurring display
- **Danger zone**:
  - Convert free → paid (or paid → free)

### 5. Inactivity Warning Banner (`components/channels/InactivityWarningBanner.tsx`)

Persistent banner at top of ChannelView for members approaching removal:
- Yellow/amber background
- Text: "You'll be removed from this channel in X days due to inactivity. Send a message to stay active."
- Dismissible (but reappears on next visit if still at risk)

### 6. Channel View Updates (`pages/work/ChannelView.tsx`)

- Import and render `PaidChannelGate` when `!isMember && channel.is_paid`
- Import and render `InactivityWarningBanner` when member has `days_until_removal` set
- Add settings gear icon in header (owner only) → opens `ChannelSettingsPanel`
- Members sidebar: show `last_contributed_at` relative time and warning indicator for at-risk members
- Show small "$" or price badge next to channel name in header

### 7. Sidebar Updates (`components/work/WorkSidebar.tsx`)

- Show a small `$` or dollar icon next to paid channel names in the sidebar list
- Color-code: green = active subscription, amber = at risk, red = cooldown

---

## Server-Side Changes (`server/app/core/`)

### 1. Alembic Migration

- Add columns to `channels` and `channel_members`
- Create `channel_payment_events` table

### 2. Routes (`routes/channels.py`)

New endpoints:
- `GET /channels/{id}/payment-info` — payment status for current user
- `POST /channels/{id}/checkout` — create Stripe checkout session, return URL
- `POST /channels/{id}/cancel-subscription` — cancel Stripe subscription
- `PATCH /channels/{id}/paid-settings` — update inactivity settings (owner only)
- `GET /channels/{id}/member-activity` — list members with activity data (owner/mod only)
- `POST /channels/stripe-webhook` — handle Stripe webhook events

Update existing:
- `POST /channels` — accept `paid_config` in body
- `POST /channels/{id}/join` — check cooldown, require payment for paid channels
- WebSocket message handler — update `last_contributed_at` on message/upload

### 3. Services (`services/channel_payment_service.py`)

- `create_stripe_product_and_price(channel)` — creates Stripe product + monthly price
- `create_checkout_session(channel, user)` — Stripe checkout session
- `handle_stripe_webhook(payload, sig)` — process payment events
- `cancel_subscription(channel, user)` — cancel + set `paid_through`
- `check_rejoin_eligibility(channel, user)` — verify cooldown has passed

### 4. Celery Worker (`workers/inactivity_worker.py`)

Periodic task (runs daily):
1. Query all paid channels with `inactivity_threshold_days` set
2. For each channel, find members where `last_contributed_at < now() - threshold`
3. Skip owners and moderators
4. For members in warning window: send warning notification, set flag
5. For members past threshold: remove from channel, cancel subscription, set `removal_cooldown_until = paid_through + 7 days`
6. Log all actions to `channel_payment_events`

---

## Implementation Order

### Phase 1 — Foundation (client-only scaffolding)
1. `api/channels.ts` — types and API stubs
2. `CreateChannelModal.tsx` — paid toggle + settings UI
3. `PaidChannelGate.tsx` — payment gate component
4. `InactivityWarningBanner.tsx` — warning banner
5. `ChannelSettingsPanel.tsx` — owner settings panel
6. `ChannelView.tsx` — wire up new components
7. `WorkSidebar.tsx` — paid channel badges

### Phase 2 — Backend
1. Alembic migration for schema changes
2. Stripe integration service
3. Channel routes (payment, settings, activity)
4. WebSocket handler updates (`last_contributed_at`)
5. Stripe webhook endpoint

### Phase 3 — Background Jobs
1. Inactivity checker Celery task
2. Warning notification system
3. Auto-removal + cooldown logic

### Phase 4 — Polish
1. Email notifications for warnings and removals
2. Creator revenue dashboard
3. Member-facing subscription management (cancel, view history)

---

## Known Issues & Open Questions

### Critical — Must Resolve Before Implementation

1. **No Stripe Connect for creator payouts** — Current Stripe integration (`stripe_service.py`) is company-scoped. Payments would go to *our* Stripe account, not the channel creator. Need Stripe Connect (Standard or Express) so creators receive funds. This changes checkout flow, webhook handling, and requires creator onboarding (connect their Stripe account).

2. **`last_contributed_at` not tracked anywhere today** — WebSocket handler (`channels_ws.py`) only updates `channels.updated_at`, not per-member activity. File upload endpoint (`channels.py:877-918`) also doesn't track activity. Both need hooks added. Writing to DB on every message is expensive at scale — consider Redis-based activity tracking flushed to DB by the Celery worker.

3. **New members have NULL `last_contributed_at`** — Inactivity worker would flag them immediately on join. Need to initialize `last_contributed_at = joined_at` when a member joins, or have the worker skip members with NULL.

4. **No failed payment handling** — `subscription_status: 'past_due'` is in the schema but no logic exists for what happens. Does the member lose access? Get a grace period? The inactivity worker only handles inactivity, not payment failures. Need a separate payment failure flow.

5. **Free → paid conversion undefined** — What happens to existing free members when a channel converts to paid? Options: grandfather them, give them a grace period to subscribe, or kick everyone. Plan must specify.

6. **Removal + continued access is contradictory** — "Removed members keep access until billing period ends" means they're not actually removed yet. Need two distinct states: `subscription_canceled` (still has access through `paid_through`) and `removed` (actually loses access). The single `removed_for_inactivity` boolean doesn't capture this.

### Design Issues

7. **Cooldown is punitive for paying users** — A user who paid $50/month, got removed for inactivity on day 3, loses $50 AND can't rejoin for a week. Consider: prorated refunds for remaining period, or cooldown only after repeated removals.

8. **No price validation** — Stripe has minimum charge amounts (~$0.50 USD). Need min/max price enforcement. Also no currency validation beyond the default.

9. **Creator can subscribe to own channel** — No guard against this. Should owners be auto-members without a subscription?

10. **Channel deletion doesn't cancel subscriptions** — If a channel is deleted/archived, all active Stripe subscriptions must be canceled. Not mentioned in the plan.

11. **Webhook routing** — Plan says `POST /channels/stripe-webhook` but existing webhook is at `POST /webhooks/stripe` (global, shared). Should extend existing webhook with metadata routing, not create a second endpoint.

### Codebase Gaps the Plan Must Address

12. **`CreateChannelRequest` model** (`channels.py:88-92`) only has `name, description, visibility` — needs `paid_config` added.

13. **`join_channel()` endpoint** (`channels.py:506-534`) has no payment or cooldown validation — needs guards for paid channels.

14. **Notification types** — `notification_service.py` doesn't have `channel_inactivity_warning` or `channel_removed_for_inactivity`. Must be added.

15. **Celery task registration** — New inactivity task must be added to `celery_app.py` include list and follow existing task patterns in `workers/tasks/`.

16. **Daily worker timing** — If threshold is 7 days and warning is 3 days, a once-daily worker could give less than 3 full days of warning. Consider running twice daily or using precise timestamps.

### Existing Infrastructure to Reuse

- **Stripe SDK**: `stripe_service.py` — `create_checkout_session()`, `create_subscription_checkout_session()`
- **Webhook handler**: `stripe_webhook.py` — extend with channel payment event types
- **Celery**: Fully configured with Redis broker, 18+ existing tasks
- **Notifications**: `notification_service.py` — `create_notification()` with email support
- **Channel roles**: `channel_members.role` already has `owner/moderator/member`

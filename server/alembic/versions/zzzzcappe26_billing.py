"""cappe: billing catalog, subscriptions, and add-ons

Cappe had no way to charge a recurring fee. `cappe_accounts.plan` existed but
nothing ever wrote it, and the only Stripe money paths were one-off (Connect
direct charges for storefront sales, platform Checkout for domains).

Shape notes, each of which is load-bearing:

- `cappe_billing_products` is ONE catalog for plans and add-ons (`kind`), so a
  single append-only price table can hang off both. Prices, the intro offer and
  the per-plan take rate are ROWS because the whole point is that they are
  tunable from the admin UI without a deploy.
- `cappe_billing_prices` is APPEND-ONLY. Stripe `Price` objects are immutable in
  `unit_amount`, so an admin price change mints a new Stripe Price and a new row
  and flips `is_current`. Old rows survive, which is what makes grandfathering
  real: an existing subscriber's row still resolves to the amount they were
  actually sold at.
- `cappe_subscriptions.stripe_event_at` is a watermark. Stripe delivers
  `customer.subscription.updated` OUT OF ORDER; without guarding each UPDATE on
  it, a stale `trialing` event can land after an `active` one and silently
  downgrade a paying account.
- `cappe_subscription_items` carries both the plan item and the add-on items
  (private email, priced per mailbox). It is a pure projection rebuilt from
  `items.data` on every subscription event, so quantities cannot drift.
- `cappe_accounts.plan` stays the denormalized effective tier and gains an FK to
  the catalog INSTEAD of a widened CHECK — an admin-editable plan lineup must
  not need a migration per tier, and the FK makes a plan value with no
  entitlement row unwritable.

**The seed reproduces today's behaviour exactly** — `free.can_sell = TRUE` at
2% — so applying this migration changes nothing observable. Turning selling off
for the free tier is a later, instantly-reversible runtime toggle, done after
customer comms. Legacy 'hosting'/'pro' are seeded as `status='legacy'`:
honoured at read time, not purchasable.

No Stripe API calls here: `migrate-prod.sh` rehearses the whole upgrade against
live rows and rolls it back, and a rehearsal that created real Stripe objects
could not undo them. Stripe Products/Prices are minted by a separate seed
script.

Revision ID: zzzzcappe26
Revises: stripeevt02
Create Date: 2026-07-30
"""
from alembic import op

revision = "zzzzcappe26"
down_revision = "stripeevt02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Catalog: plans and add-ons ────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_billing_products (
            code VARCHAR(40) PRIMARY KEY,
            kind VARCHAR(20) NOT NULL CHECK (kind IN ('plan', 'addon')),
            name VARCHAR(120) NOT NULL,
            description TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'legacy', 'archived')),
            sort_order INTEGER NOT NULL DEFAULT 0,
            stripe_product_id VARCHAR(64) UNIQUE,

            -- Entitlements (meaningful on kind='plan').
            can_sell BOOLEAN NOT NULL DEFAULT false,
            platform_fee_bps INTEGER NOT NULL DEFAULT 200
                CHECK (platform_fee_bps BETWEEN 0 AND 5000),
            allowed_fulfillment TEXT[] NOT NULL DEFAULT '{}'::TEXT[]
                CHECK (allowed_fulfillment
                       <@ ARRAY['physical', 'digital', 'service', 'booking']::TEXT[]),
            site_limit INTEGER,                       -- NULL = unlimited
            mailbox_quota_included INTEGER NOT NULL DEFAULT 0,
            features JSONB NOT NULL DEFAULT '{}'::jsonb,

            -- Add-on shape (meaningful on kind='addon').
            unit_label VARCHAR(50) NOT NULL DEFAULT 'unit',
            max_quantity INTEGER NOT NULL DEFAULT 100 CHECK (max_quantity > 0),

            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    # ── Prices: append-only mirror of Stripe Price objects ────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_billing_prices (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            product_code VARCHAR(40) NOT NULL
                REFERENCES cappe_billing_products(code) ON DELETE RESTRICT,
            role VARCHAR(20) NOT NULL DEFAULT 'standard'
                CHECK (role IN ('standard', 'intro')),
            interval VARCHAR(10) NOT NULL CHECK (interval IN ('month', 'year', 'once')),
            unit_amount_cents INTEGER NOT NULL CHECK (unit_amount_cents >= 0),
            currency VARCHAR(3) NOT NULL DEFAULT 'USD',
            intro_days INTEGER,
            stripe_price_id VARCHAR(64) UNIQUE,
            -- Stripe's own idempotency handle: a re-run of the seed script errors
            -- instead of silently minting a duplicate Price.
            lookup_key VARCHAR(120) UNIQUE,
            is_current BOOLEAN NOT NULL DEFAULT true,
            active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            archived_at TIMESTAMPTZ,
            CONSTRAINT cappe_prices_intro_days CHECK ((role = 'intro') = (intro_days IS NOT NULL)),
            CONSTRAINT cappe_prices_intro_once CHECK (role <> 'intro' OR interval = 'once')
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_cappe_price_current
            ON cappe_billing_prices (product_code, role, interval, currency)
            WHERE is_current
        """
    )

    # ── Subscriptions ─────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_subscriptions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL REFERENCES cappe_accounts(id) ON DELETE CASCADE,
            stripe_subscription_id VARCHAR(64) UNIQUE,
            stripe_customer_id VARCHAR(64),
            plan_code VARCHAR(40) NOT NULL REFERENCES cappe_billing_products(code),
            price_id UUID REFERENCES cappe_billing_prices(id),
            interval VARCHAR(10) NOT NULL DEFAULT 'month',
            -- Stripe's status verbatim, plus 'comp' for a granted plan with no
            -- Stripe subscription behind it (kept queryable and revocable rather
            -- than indistinguishable from a paying subscriber).
            status VARCHAR(30) NOT NULL,
            source VARCHAR(10) NOT NULL DEFAULT 'stripe'
                CHECK (source IN ('stripe', 'comp')),
            comped_until TIMESTAMPTZ,
            comp_reason TEXT,
            current_period_end TIMESTAMPTZ,
            trial_end TIMESTAMPTZ,
            cancel_at_period_end BOOLEAN NOT NULL DEFAULT false,
            canceled_at TIMESTAMPTZ,
            latest_invoice_id VARCHAR(64),
            -- Out-of-order delivery guard; see the module docstring.
            stripe_event_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    # At most one live subscription per account. Terminal rows are excluded so
    # subscription history survives — that history is also what makes the
    # one-shot intro offer enforceable.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_cappe_sub_live
            ON cappe_subscriptions (account_id)
            WHERE status IN ('trialing', 'active', 'past_due', 'incomplete', 'unpaid', 'paused')
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_sub_customer "
        "ON cappe_subscriptions (stripe_customer_id)"
    )

    # ── Subscription items (plan item + add-on items) ─────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_subscription_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            subscription_id UUID NOT NULL
                REFERENCES cappe_subscriptions(id) ON DELETE CASCADE,
            stripe_item_id VARCHAR(64) NOT NULL UNIQUE,
            product_code VARCHAR(40) NOT NULL REFERENCES cappe_billing_products(code),
            price_id UUID REFERENCES cappe_billing_prices(id),
            stripe_price_id VARCHAR(64),
            quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_sub_items_sub "
        "ON cappe_subscription_items (subscription_id)"
    )

    # ── Intro offer: one $1 per account, ever ─────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_intro_redemptions (
            account_id UUID PRIMARY KEY REFERENCES cappe_accounts(id) ON DELETE CASCADE,
            redeemed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            stripe_subscription_id VARCHAR(64),
            -- Best-effort serial-signup defence, populated from the first paid
            -- charge. Nullable: the column exists from day one so enabling the
            -- check later needs no migration.
            card_fingerprint VARCHAR(64)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_cappe_intro_fingerprint
            ON cappe_intro_redemptions (card_fingerprint)
            WHERE card_fingerprint IS NOT NULL
        """
    )

    # ── Admin audit (these are runtime-editable money knobs) ──────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_admin_audit (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            actor_account_id UUID REFERENCES cappe_accounts(id) ON DELETE SET NULL,
            action VARCHAR(60) NOT NULL,
            target VARCHAR(120),
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_admin_audit_created "
        "ON cappe_admin_audit (created_at DESC)"
    )

    # ── cappe_accounts: billing identity + platform admin ─────────────────
    # Widen `plan` to match `cappe_billing_products.code`. The FK below is legal
    # across VARCHAR(20)→VARCHAR(40), so nothing complains at migration time —
    # but the catalog could then hold a code the denormalized column cannot
    # store, and any attempt to GRANT that plan (_materialize_plan, grant_comp,
    # the subscription webhook) would raise "value too long". A subscription to
    # such a plan would fail inside the webhook and Stripe would retry forever
    # while the customer is billed.
    op.execute("ALTER TABLE cappe_accounts ALTER COLUMN plan TYPE VARCHAR(40)")
    op.execute("ALTER TABLE cappe_accounts ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(64)")
    op.execute(
        "ALTER TABLE cappe_accounts ADD COLUMN IF NOT EXISTS "
        "is_platform_admin BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute("ALTER TABLE cappe_accounts ADD COLUMN IF NOT EXISTS plan_override_until TIMESTAMPTZ")

    # Adopt the Stripe Customer a domain purchase already created, so a
    # domain-buyer who later subscribes does not end up with a second `cus_`.
    # Ranked twice: one customer per account, and one account per customer, so
    # the partial unique index below cannot fail on legacy data.
    op.execute(
        """
        WITH per_account AS (
            SELECT account_id,
                   stripe_customer_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY account_id ORDER BY created_at DESC, id
                   ) AS rn
              FROM cappe_domains
             WHERE stripe_customer_id IS NOT NULL
        ),
        picked AS (
            SELECT account_id,
                   stripe_customer_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY stripe_customer_id ORDER BY account_id
                   ) AS rn_customer
              FROM per_account
             WHERE rn = 1
        )
        UPDATE cappe_accounts a
           SET stripe_customer_id = p.stripe_customer_id
          FROM picked p
         WHERE a.id = p.account_id
           AND p.rn_customer = 1
           AND a.stripe_customer_id IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_cappe_accounts_stripe_customer
            ON cappe_accounts (stripe_customer_id)
            WHERE stripe_customer_id IS NOT NULL
        """
    )

    # ── Seed the catalog (behaviour-neutral) ──────────────────────────────
    # Prices are placeholders for the admin UI. `free.can_sell = TRUE` and a flat
    # 200 bps reproduce today's behaviour exactly; the flip is a runtime toggle.
    op.execute(
        """
        INSERT INTO cappe_billing_products (
            code, kind, name, description, status, sort_order,
            can_sell, platform_fee_bps, allowed_fulfillment, site_limit,
            mailbox_quota_included, features,
            unit_label, max_quantity
        ) VALUES
        (
            'free', 'plan', 'Free', 'Build and publish a site.', 'active', 0,
            true, 200, ARRAY['physical', 'digital', 'service', 'booking']::TEXT[], 1,
            0, , '{}'::jsonb, 'unit', 100
        ),
        (
            'creator', 'plan', 'Creator',
            'For solo professionals selling their time.', 'active', 1,
            true, 300, ARRAY['service', 'booking']::TEXT[], NULL,
            0, , '{"rider": true}'::jsonb, 'unit', 100
        ),
        (
            'business', 'plan', 'Business',
            'Sell services, physical and digital products.', 'active', 2,
            true, 150, ARRAY['physical', 'digital', 'service', 'booking']::TEXT[], NULL,
            0, , '{}'::jsonb, 'unit', 100
        ),
        (
            'pro', 'plan', 'Pro (legacy)',
            'Retired tier. Honoured for existing accounts, not purchasable.', 'legacy', 90,
            true, 200, ARRAY['physical', 'digital', 'service', 'booking']::TEXT[], NULL,
            0, , '{"rider": true}'::jsonb, 'unit', 100
        ),
        (
            'hosting', 'plan', 'Hosting (legacy)',
            'Retired tier. Honoured for existing accounts, not purchasable.', 'legacy', 91,
            true, 200, ARRAY['physical', 'digital', 'service', 'booking']::TEXT[], NULL,
            0, , '{}'::jsonb, 'unit', 100
        ),
        (
            'mailbox', 'addon', 'Private email',
            'A mailbox on your own domain, billed per mailbox.', 'active', 10,
            false, 0, '{}'::TEXT[], NULL,
            0, , '{}'::jsonb, 'mailbox', 50
        )
        ON CONFLICT (code) DO NOTHING
        """
    )

    # Placeholder price rows. stripe_price_id stays NULL until the seed script
    # mints the Stripe objects; nothing can be purchased before then.
    op.execute(
        """
        INSERT INTO cappe_billing_prices (
            product_code, role, interval, unit_amount_cents, intro_days, lookup_key
        ) VALUES
            ('creator',  'standard', 'month', 1900,  NULL, 'cappe_creator_month_v1'),
            ('creator',  'standard', 'year',  19000, NULL, 'cappe_creator_year_v1'),
            ('creator',  'intro',    'once',  100,   30,   'cappe_creator_intro_v1'),
            ('business', 'standard', 'month', 4900,  NULL, 'cappe_business_month_v1'),
            ('business', 'standard', 'year',  49000, NULL, 'cappe_business_year_v1'),
            ('business', 'intro',    'once',  100,   30,   'cappe_business_intro_v1'),
            ('mailbox',  'standard', 'month', 300,   NULL, 'cappe_mailbox_month_v1'),
            ('mailbox',  'standard', 'year',  3000,  NULL, 'cappe_mailbox_year_v1')
        ON CONFLICT (lookup_key) DO NOTHING
        """
    )

    # ── plan: CHECK → FK against the catalog ──────────────────────────────
    # A hardcoded CHECK would mean a migration for every new tier, which defeats
    # an admin-editable lineup. The FK also makes it impossible to write a plan
    # value that has no entitlement row behind it.
    op.execute(
        """
        DO $$
        DECLARE
            target_name TEXT;
        BEGIN
            SELECT c.conname INTO target_name
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            WHERE t.relname = 'cappe_accounts'
              AND c.contype = 'c'
              AND pg_get_constraintdef(c.oid) ILIKE '%plan%'
              AND pg_get_constraintdef(c.oid) ILIKE '%hosting%'
            ORDER BY c.conname
            LIMIT 1;

            IF target_name IS NOT NULL THEN
                EXECUTE format('ALTER TABLE cappe_accounts DROP CONSTRAINT %I', target_name);
            END IF;
        END $$
        """
    )
    op.execute(
        """
        ALTER TABLE cappe_accounts
            ADD CONSTRAINT fk_cappe_accounts_plan
            FOREIGN KEY (plan) REFERENCES cappe_billing_products(code)
        """
    )

    # ── Comp expiry sweep (seeded disabled, like every other scheduled task) ──
    # comped_until is only meaningful if something acts on it; without this the
    # comped tier stays materialized on cappe_accounts.plan forever.
    op.execute(
        """
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'cappe_comp_expiry',
            'Cappe Comp Expiry',
            'Returns Cappe accounts whose comped plan has passed comped_until back to '
            'the free plan. Skips accounts that have since started paying. Default off.',
            false,
            1
        )
        ON CONFLICT (task_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'cappe_comp_expiry'")
    op.execute("ALTER TABLE cappe_accounts DROP CONSTRAINT IF EXISTS fk_cappe_accounts_plan")
    # Any account on a tier the old CHECK did not know about must be folded back
    # before the narrower constraint can be restored.
    op.execute(
        "UPDATE cappe_accounts SET plan = 'free' "
        "WHERE plan NOT IN ('free', 'hosting', 'pro', 'business')"
    )
    op.execute(
        """
        ALTER TABLE cappe_accounts ADD CONSTRAINT cappe_accounts_plan_check
            CHECK (plan IN ('free', 'hosting', 'pro', 'business'))
        """
    )
    op.execute("ALTER TABLE cappe_accounts ALTER COLUMN plan TYPE VARCHAR(20)")

    op.execute("DROP INDEX IF EXISTS uq_cappe_accounts_stripe_customer")
    op.execute("ALTER TABLE cappe_accounts DROP COLUMN IF EXISTS plan_override_until")
    op.execute("ALTER TABLE cappe_accounts DROP COLUMN IF EXISTS is_platform_admin")
    op.execute("ALTER TABLE cappe_accounts DROP COLUMN IF EXISTS stripe_customer_id")

    op.execute("DROP TABLE IF EXISTS cappe_admin_audit")
    op.execute("DROP TABLE IF EXISTS cappe_intro_redemptions")
    op.execute("DROP TABLE IF EXISTS cappe_subscription_items")
    op.execute("DROP TABLE IF EXISTS cappe_subscriptions")
    op.execute("DROP TABLE IF EXISTS cappe_billing_prices")
    op.execute("DROP TABLE IF EXISTS cappe_billing_products")

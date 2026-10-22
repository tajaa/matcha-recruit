"""Cappe magazines, PR 5 — writers, follows and email issues.

A new kind of account, the writer, signs up at gummfit.com/magazines and gets
one magazine-only site at `<handle>.gummfit.com`. Readers follow a magazine by
email (double opt-in), and a writer sends a story to them as an issue.

  * `cappe_accounts.account_type` gains `writer`;
  * `cappe_sites.source_type` gains `magazine` (a writer's site: its front
    page is the magazine, and it has no shop);
  * the `writer` plan: $9 a month, no selling, one site, magazines on
    (`features.audience = 'writer'` keeps it off other accounts' plan lists
    and theirs off a writer's, except Free and Business). Its Stripe Product
    and Price are minted by `server/scripts/seed_cappe_plans.py`, run after
    this; until then a writer checkout answers 503;
  * `cappe_campaigns.kind` — `campaign` (a newsletter) or `issue` (a story
    sent to followers: `story_id`, `include_body` for the whole free story
    rather than its opening, and `body_text`, the plain-text part).

The downgrade refuses while any writer account, writer site or writer
subscription exists (the zzzzcappe28 precedent: narrowing a CHECK under rows
that use the value fails, so it says so first).

Revision ID: cappemag04
Revises: cappemag03
Create Date: 2026-10-21
"""
from alembic import op

revision = "cappemag04"
down_revision = "cappemag03"
branch_labels = None
depends_on = None

_SITE_SOURCE_DROP = """
    DO $$
    DECLARE c TEXT;
    BEGIN
        FOR c IN SELECT conname FROM pg_constraint
                  WHERE conrelid = 'cappe_sites'::regclass AND contype = 'c'
                    AND pg_get_constraintdef(oid) LIKE '%source_type%'
        LOOP
            EXECUTE format('ALTER TABLE cappe_sites DROP CONSTRAINT %I', c);
        END LOOP;
    END $$
"""

_UPGRADE = [
    "ALTER TABLE cappe_accounts DROP CONSTRAINT IF EXISTS cappe_accounts_account_type_check",
    "ALTER TABLE cappe_accounts ADD CONSTRAINT cappe_accounts_account_type_check "
    "CHECK (account_type IN ('business', 'personal', 'creator', 'writer'))",
    _SITE_SOURCE_DROP,
    "ALTER TABLE cappe_sites ADD CONSTRAINT ck_cappe_sites_source_type "
    "CHECK (source_type IN ('template', 'byo', 'blank', 'magazine'))",
    """
    INSERT INTO cappe_billing_products (
        code, kind, name, description, status, sort_order, can_sell, platform_fee_bps,
        allowed_fulfillment, site_limit, mailbox_quota_included, features, unit_label, max_quantity
    ) VALUES (
        'writer', 'plan', 'Writer', 'Publish your own photo magazine, at your own address.', 'active', 1,
        false, 200, '{}'::TEXT[], 1, 0,
        jsonb_build_object('magazine', true, 'audience', 'writer', 'stock_imports_per_day', 300),
        'unit', 100
    ) ON CONFLICT (code) DO NOTHING
    """,
    """
    INSERT INTO cappe_billing_prices (product_code, role, interval, unit_amount_cents, intro_days, lookup_key)
    VALUES ('writer', 'standard', 'month', 900, NULL, 'cappe_writer_month_v1')
    ON CONFLICT (lookup_key) DO NOTHING
    """,
    "ALTER TABLE cappe_campaigns ADD COLUMN IF NOT EXISTS kind VARCHAR(10) NOT NULL DEFAULT 'campaign'",
    "ALTER TABLE cappe_campaigns ADD COLUMN IF NOT EXISTS story_id UUID REFERENCES cappe_posts(id) ON DELETE SET NULL",
    "ALTER TABLE cappe_campaigns ADD COLUMN IF NOT EXISTS include_body BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE cappe_campaigns ADD COLUMN IF NOT EXISTS body_text TEXT",
    """
    DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cappe_campaigns_kind') THEN
            ALTER TABLE cappe_campaigns ADD CONSTRAINT ck_cappe_campaigns_kind
                CHECK (kind IN ('campaign', 'issue'));
        END IF;
    END $$
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_campaigns_issues ON cappe_campaigns (site_id, created_at DESC) "
    "WHERE kind = 'issue'",
]

_DOWNGRADE = [
    """
    DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM cappe_accounts WHERE account_type = 'writer' OR plan = 'writer')
           OR EXISTS (SELECT 1 FROM cappe_sites WHERE source_type = 'magazine')
           OR EXISTS (SELECT 1 FROM cappe_subscriptions WHERE plan_code = 'writer') THEN
            RAISE EXCEPTION 'cappemag04 downgrade: writer accounts, magazine sites or writer subscriptions exist';
        END IF;
    END $$
    """,
    "DROP INDEX IF EXISTS idx_cappe_campaigns_issues",
    "ALTER TABLE cappe_campaigns DROP CONSTRAINT IF EXISTS ck_cappe_campaigns_kind",
    "ALTER TABLE cappe_campaigns DROP COLUMN IF EXISTS body_text",
    "ALTER TABLE cappe_campaigns DROP COLUMN IF EXISTS include_body",
    "ALTER TABLE cappe_campaigns DROP COLUMN IF EXISTS story_id",
    "ALTER TABLE cappe_campaigns DROP COLUMN IF EXISTS kind",
    "DELETE FROM cappe_billing_prices WHERE product_code = 'writer'",
    "DELETE FROM cappe_billing_products WHERE code = 'writer'",
    "ALTER TABLE cappe_sites DROP CONSTRAINT IF EXISTS ck_cappe_sites_source_type",
    "ALTER TABLE cappe_sites ADD CONSTRAINT ck_cappe_sites_source_type "
    "CHECK (source_type IN ('template', 'byo', 'blank'))",
    "ALTER TABLE cappe_accounts DROP CONSTRAINT IF EXISTS cappe_accounts_account_type_check",
    "ALTER TABLE cappe_accounts ADD CONSTRAINT cappe_accounts_account_type_check "
    "CHECK (account_type IN ('business', 'personal', 'creator'))",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)

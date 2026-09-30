"""Espresso assistant: buying from the private conversation.

Revision ID: assistbuy01
Revises: agentrt03
Create Date: 2026-09-30

Four changes, all additive:

  * `mw_shipping_addresses`: where a purchase ships. Per person, at most five
    (enforced in the route), one marked default.
  * `mw_payment_cards.billing_address`: NULL means "same as shipping", which is
    the default; a card with a different billing address stores it here.
  * `mw_agent_purchase_requests` now also records purchases made by the
    assistant, which have a conversation instead of a project and a card.
    `project_id`/`task_id` become nullable, `channel_id` is added, and a CHECK
    requires one or the other. The address a purchase shipped to (and billed
    to) is snapshotted on the row, so editing or deleting an address later
    never rewrites history.
  * status `charging`: a charge whose outcome is not written yet.
"""
from alembic import op

revision = "assistbuy01"
down_revision = "agentrt03"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_shipping_addresses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            line1 TEXT NOT NULL,
            line2 TEXT NOT NULL DEFAULT '',
            city TEXT NOT NULL,
            region TEXT NOT NULL DEFAULT '',
            postal_code TEXT NOT NULL,
            country TEXT NOT NULL DEFAULT 'US',
            phone TEXT NOT NULL DEFAULT '',
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT mw_shipping_addresses_country CHECK (country ~ '^[A-Z]{2}$')
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_shipping_addresses_user
            ON mw_shipping_addresses (user_id, created_at)
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mw_shipping_addresses_one_default
            ON mw_shipping_addresses (user_id) WHERE is_default
    """)
    op.execute("ALTER TABLE mw_payment_cards ADD COLUMN IF NOT EXISTS billing_address JSONB")
    op.execute("""
        ALTER TABLE mw_agent_purchase_requests
            ALTER COLUMN project_id DROP NOT NULL,
            ALTER COLUMN task_id DROP NOT NULL,
            ADD COLUMN IF NOT EXISTS channel_id UUID REFERENCES channels(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS shipping_address JSONB,
            ADD COLUMN IF NOT EXISTS billing_address JSONB
    """)
    # A card purchase has its task; an assistant purchase had its conversation
    # when it was made. `channel_id` may later go NULL (conversation deleted),
    # so the check is on creation shape: task, or a snapshot address.
    op.execute("""
        ALTER TABLE mw_agent_purchase_requests
            DROP CONSTRAINT IF EXISTS mw_agent_purchase_requests_origin
    """)
    op.execute("""
        ALTER TABLE mw_agent_purchase_requests ADD CONSTRAINT mw_agent_purchase_requests_origin
            CHECK (task_id IS NOT NULL OR shipping_address IS NOT NULL)
    """)
    # `charging`: the Stripe call was made (or is about to be) and its outcome
    # is not written yet. A row left there is an outcome nobody knows; the
    # next attempt on the same approval settles it (same idempotency key).
    op.execute("ALTER TABLE mw_agent_purchase_requests DROP CONSTRAINT IF EXISTS mw_agent_purchase_requests_status_check")
    op.execute("""
        ALTER TABLE mw_agent_purchase_requests ADD CONSTRAINT mw_agent_purchase_requests_status_check
            CHECK (status IN ('handoff', 'cancelled', 'charging', 'test_charged', 'test_failed'))
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_agent_purchase_requests_user
            ON mw_agent_purchase_requests (user_id, created_at DESC)
    """)


def downgrade():
    # Assistant purchases have no task and cannot survive NOT NULL again.
    op.execute("DELETE FROM mw_agent_purchase_requests WHERE task_id IS NULL")
    op.execute("UPDATE mw_agent_purchase_requests SET status = 'test_failed' WHERE status = 'charging'")
    op.execute("ALTER TABLE mw_agent_purchase_requests DROP CONSTRAINT IF EXISTS mw_agent_purchase_requests_status_check")
    op.execute("""
        ALTER TABLE mw_agent_purchase_requests ADD CONSTRAINT mw_agent_purchase_requests_status_check
            CHECK (status IN ('handoff', 'cancelled', 'test_charged', 'test_failed'))
    """)
    op.execute("DROP INDEX IF EXISTS idx_mw_agent_purchase_requests_user")
    op.execute("""
        ALTER TABLE mw_agent_purchase_requests
            DROP CONSTRAINT IF EXISTS mw_agent_purchase_requests_origin
    """)
    op.execute("""
        ALTER TABLE mw_agent_purchase_requests
            DROP COLUMN IF EXISTS billing_address,
            DROP COLUMN IF EXISTS shipping_address,
            DROP COLUMN IF EXISTS channel_id,
            ALTER COLUMN task_id SET NOT NULL,
            ALTER COLUMN project_id SET NOT NULL
    """)
    op.execute("ALTER TABLE mw_payment_cards DROP COLUMN IF EXISTS billing_address")
    op.execute("DROP TABLE IF EXISTS mw_shipping_addresses")

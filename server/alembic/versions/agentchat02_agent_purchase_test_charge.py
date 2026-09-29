"""Matcha Work: agent-card purchases record a Stripe test-mode charge.

Revision ID: agentchat02
Revises: agentchat01
Create Date: 2026-09-29

An approved purchase with a verified total is charged in Stripe **test mode**
(see `agent_card/test_charge.py`): no real money, the saved card's number is
never sent. The row keeps the PaymentIntent id and the outcome.
"""
from alembic import op


revision = "agentchat02"
down_revision = "agentchat01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE mw_agent_purchase_requests
            ADD COLUMN IF NOT EXISTS stripe_payment_intent_id TEXT,
            ADD COLUMN IF NOT EXISTS charge_error TEXT
    """)
    op.execute("ALTER TABLE mw_agent_purchase_requests DROP CONSTRAINT IF EXISTS mw_agent_purchase_requests_status_check")
    op.execute("""
        ALTER TABLE mw_agent_purchase_requests ADD CONSTRAINT mw_agent_purchase_requests_status_check
            CHECK (status IN ('handoff', 'cancelled', 'test_charged', 'test_failed'))
    """)


def downgrade():
    op.execute("UPDATE mw_agent_purchase_requests SET status = 'handoff' WHERE status IN ('test_charged', 'test_failed')")
    op.execute("ALTER TABLE mw_agent_purchase_requests DROP CONSTRAINT IF EXISTS mw_agent_purchase_requests_status_check")
    op.execute("""
        ALTER TABLE mw_agent_purchase_requests ADD CONSTRAINT mw_agent_purchase_requests_status_check
            CHECK (status IN ('handoff', 'cancelled'))
    """)
    op.execute("""
        ALTER TABLE mw_agent_purchase_requests
            DROP COLUMN IF EXISTS charge_error,
            DROP COLUMN IF EXISTS stripe_payment_intent_id
    """)

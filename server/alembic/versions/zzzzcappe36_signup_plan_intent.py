"""Cappe signup plan intent — remember the plan picked on the pricing page.

A visitor who clicks "Start with Business" signs up, then confirms their email
from a link that usually opens in another tab or on another device. The choice
therefore cannot ride in the browser; it is parked on the account row at signup
and handed back (and cleared) when the email is confirmed, so the person lands
in checkout for the plan they picked.

Not an entitlement: nothing reads these columns to grant anything. The plan an
account is on is still set only from Stripe state.

Additive + idempotent.

Revision ID: zzzzcappe36
Revises: zzzzcappe35
"""
from alembic import op

revision = "zzzzcappe36"
down_revision = "zzzzcappe35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cappe_accounts
            ADD COLUMN IF NOT EXISTS intended_plan_code VARCHAR(40),
            ADD COLUMN IF NOT EXISTS intended_interval  VARCHAR(10)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE cappe_accounts
            DROP COLUMN IF EXISTS intended_plan_code,
            DROP COLUMN IF EXISTS intended_interval
        """
    )

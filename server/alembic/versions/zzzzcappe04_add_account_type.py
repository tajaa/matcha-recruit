"""Cappe account types: business vs personal ("business of one").

A `business` account is a storefront for an organization (coffee shop,
studio, restaurant); a `personal` account is a solo professional who gets
hired/booked (barista for events, photographer, chef, consultant, trainer).
Same offering engine underneath — the type steers signup, template
recommendations, and dashboard emphasis, not capabilities.

Additive with a default, so existing rows are unchanged.

Revision ID: zzzzcappe04
Revises: zzzzcappe03
Create Date: 2026-06-12
"""
from alembic import op


revision = "zzzzcappe04"
down_revision = "zzzzcappe03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cappe_accounts
            ADD COLUMN IF NOT EXISTS account_type VARCHAR(20) NOT NULL DEFAULT 'business'
                CHECK (account_type IN ('business', 'personal'))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE cappe_accounts DROP COLUMN IF EXISTS account_type")

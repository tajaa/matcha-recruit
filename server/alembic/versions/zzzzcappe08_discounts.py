"""Cappe discounts — creator-set promotional discounts.

A discount is a percentage off, scoped to everything (`all`), a single booking
type (`booking_type`), or a single product (`product`). It's gated by an
`active` flag and an optional [starts_on, ends_on] date window — so a creator
who's quiet this week can drop a site-wide discount, or mark down one service.

Applied at quote/order time (authoritative, server-side); the best single
matching discount wins (no stacking).

Revision ID: zzzzcappe08
Revises: zzzzcappe07
"""
from alembic import op

revision = "zzzzcappe08"
down_revision = "zzzzcappe07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_discounts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            label VARCHAR(120) NOT NULL DEFAULT 'Discount',
            percent_off INTEGER NOT NULL CHECK (percent_off >= 1 AND percent_off <= 90),
            scope VARCHAR(16) NOT NULL DEFAULT 'all'
                CHECK (scope IN ('all', 'booking_type', 'product')),
            target_id UUID,
            active BOOLEAN NOT NULL DEFAULT true,
            starts_on DATE,
            ends_on DATE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_discounts_site_active "
        "ON cappe_discounts(site_id, active)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cappe_discounts")

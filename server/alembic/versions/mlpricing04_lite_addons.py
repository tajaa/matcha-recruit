"""Seed matcha_lite_pricing rows for the Lite add-ons.

Each Lite-family add-on (see server/app/core/services/lite_addons.py) is its
own Stripe subscription priced from this table — block_size=1 makes
price_per_block_cents a straight per-employee-per-month rate.

Seeded prices are PLACEHOLDERS ($1 / $2 / $1 PEPM) — set real values at
/admin/matcha-lite-pricing before launch.

Idempotent (INSERT ... ON CONFLICT DO NOTHING).

Revision ID: mlpricing04
Revises: mlpricing03
Create Date: 2026-07-01
"""
from alembic import op


revision = "mlpricing04"
down_revision = "mlpricing03"
branch_labels = None
depends_on = None

ADDON_CODES = ("addon_voice_intake", "addon_hris_sync", "addon_handbook_watch")


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO matcha_lite_pricing
            (product_code, price_per_block_cents, block_size, min_headcount, max_headcount)
        VALUES
            ('addon_voice_intake',   100, 1, 1, 300),
            ('addon_hris_sync',      200, 1, 1, 300),
            ('addon_handbook_watch', 100, 1, 1, 300)
        ON CONFLICT (product_code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM matcha_lite_pricing WHERE product_code IN "
        "('addon_voice_intake', 'addon_hris_sync', 'addon_handbook_watch')"
    )

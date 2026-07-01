"""Seed matcha_lite_pricing row for matcha_compliance.

Matcha Compliance moves off the old hardcoded matcha_compliance_price_cents()
stub (headcount formula + ad-hoc per-jurisdiction surcharge) onto the same
DB-backed, admin-configurable pricing table Lite/Essentials already use.
Seeded flat at $8/head — block_size=1 makes price_per_block_cents equal the
per-employee rate directly, no jurisdiction component.

Idempotent (INSERT ... ON CONFLICT DO NOTHING).

Revision ID: mlpricing03
Revises: mlpricing02
Create Date: 2026-07-01
"""
from alembic import op


revision = "mlpricing03"
down_revision = "mlpricing02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO matcha_lite_pricing
            (product_code, price_per_block_cents, block_size, min_headcount, max_headcount)
        VALUES ('matcha_compliance', 800, 1, 1, 300)
        ON CONFLICT (product_code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM matcha_lite_pricing WHERE product_code = 'matcha_compliance'")

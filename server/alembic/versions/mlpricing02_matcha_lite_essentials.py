"""Seed matcha_lite_pricing row for matcha_lite_essentials.

Matcha Lite Essentials is a signup-time choice on the same /lite/signup page
(not a separate product) for companies that want incident reporting without
an employee roster (no CSV/HRIS import, no OSHA logs). Priced as its own row
in the existing matcha_lite_pricing table (schema unchanged — product_code
was already the primary key), seeded at $40/block of 10 ($4/head), cheaper
than standard Lite's $50/block.

Idempotent (INSERT ... ON CONFLICT DO NOTHING).

Revision ID: mlpricing02
Revises: mlpricing01
Create Date: 2026-07-01
"""
from alembic import op


revision = "mlpricing02"
down_revision = "mlpricing01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO matcha_lite_pricing
            (product_code, price_per_block_cents, block_size, min_headcount, max_headcount)
        VALUES ('matcha_lite_essentials', 4000, 10, 1, 300)
        ON CONFLICT (product_code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM matcha_lite_pricing WHERE product_code = 'matcha_lite_essentials'")

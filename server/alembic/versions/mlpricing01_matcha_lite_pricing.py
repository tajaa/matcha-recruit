"""Add matcha_lite_pricing — admin-configurable Matcha Lite pricing.

Matcha Lite pricing was a hardcoded Python constant (math.ceil(headcount/10) *
10_000 cents in stripe_service.matcha_lite_price_cents) — changing the price or
running a sale required a code deploy. This table makes it a single admin-editable
row: a base price per headcount block, block size, and an optional sale-price
override + on/off toggle. matcha_lite_pricing_history records every change
(old/new values + who), since this directly sets what customers are charged.

Seeded at $50/block of 10 employees ($5/head effective) — the new launch price.

Idempotent (CREATE TABLE IF NOT EXISTS / INSERT ... ON CONFLICT DO NOTHING) so
re-running against a partially upgraded DB is safe.

Revision ID: mlpricing01
Revises: lossratio01
Create Date: 2026-06-30
"""
from alembic import op


revision = "mlpricing01"
down_revision = "lossratio01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS matcha_lite_pricing (
            product_code                 text PRIMARY KEY,
            price_per_block_cents        integer NOT NULL,
            block_size                   integer NOT NULL,
            sale_price_per_block_cents   integer,
            sale_active                  boolean NOT NULL DEFAULT false,
            min_headcount                integer NOT NULL DEFAULT 1,
            max_headcount                integer NOT NULL,
            updated_at                   timestamptz NOT NULL DEFAULT now(),
            updated_by                   text
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS matcha_lite_pricing_history (
            id           bigserial PRIMARY KEY,
            changed_at   timestamptz NOT NULL DEFAULT now(),
            changed_by   text,
            old_values   jsonb,
            new_values   jsonb
        )
        """
    )
    op.execute(
        """
        INSERT INTO matcha_lite_pricing
            (product_code, price_per_block_cents, block_size, min_headcount, max_headcount)
        VALUES ('matcha_lite', 5000, 10, 1, 300)
        ON CONFLICT (product_code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS matcha_lite_pricing_history")
    op.execute("DROP TABLE IF EXISTS matcha_lite_pricing")

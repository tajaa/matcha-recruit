"""Tell-Us — paid brand signup, priced per store location.

Brand accounts move from free to a Stripe subscription billed per
`location_count`. Pricing itself is NOT a new table — it reuses
`matcha_lite_pricing` (product_code='tellus_brand', block_size=1 ⇒ flat
per-location), which comes with a ready-made admin editor and audit history.
See server/app/core/services/matcha_lite_pricing.py.

Existing brands predate the paywall and must not be locked out — they are
grandfathered to plan_status='active' with location_count backfilled from
their actual store count (not left at the column default of 1, which would
immediately trip the new store-count cap on their next store creation).

Revision ID: tellus_app_04
Revises: tellus_app_03
Create Date: 2026-08-03
"""
from alembic import op


revision = "tellus_app_04"
down_revision = "tellus_app_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tellus_brands ADD COLUMN IF NOT EXISTS location_count INT NOT NULL DEFAULT 1"
    )
    op.execute(
        "ALTER TABLE tellus_brands ADD COLUMN IF NOT EXISTS plan_status TEXT NOT NULL DEFAULT 'pending'"
    )
    op.execute(
        """DO $$ BEGIN
            ALTER TABLE tellus_brands ADD CONSTRAINT ck_tellus_brands_plan_status
                CHECK (plan_status IN ('pending', 'active', 'past_due', 'canceled'));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""
    )
    op.execute("ALTER TABLE tellus_brands ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT")
    op.execute("ALTER TABLE tellus_brands ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT")
    op.execute("ALTER TABLE tellus_brands ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ")

    # Grandfather pre-existing brands: active, location_count backfilled to
    # their real store count (never below 1) so the new store cap doesn't
    # immediately block them.
    op.execute(
        """UPDATE tellus_brands b SET
               plan_status = 'active',
               location_count = GREATEST(1, (
                   SELECT count(*) FROM tellus_stores s WHERE s.brand_id = b.id
               ))"""
    )

    # Seed the tellus_brand pricing row. Placeholder $29/store/mo — change via
    # Admin > Matcha Lite Pricing > "Tell-Us (per store)", not by editing this.
    op.execute(
        """INSERT INTO matcha_lite_pricing
               (product_code, price_per_block_cents, block_size, min_headcount, max_headcount)
           VALUES ('tellus_brand', 2900, 1, 1, 500)
           ON CONFLICT (product_code) DO NOTHING"""
    )


def downgrade() -> None:
    op.execute("DELETE FROM matcha_lite_pricing WHERE product_code = 'tellus_brand'")
    op.execute("ALTER TABLE tellus_brands DROP COLUMN IF EXISTS activated_at")
    op.execute("ALTER TABLE tellus_brands DROP COLUMN IF EXISTS stripe_subscription_id")
    op.execute("ALTER TABLE tellus_brands DROP COLUMN IF EXISTS stripe_customer_id")
    op.execute("ALTER TABLE tellus_brands DROP COLUMN IF EXISTS plan_status")
    op.execute("ALTER TABLE tellus_brands DROP COLUMN IF EXISTS location_count")

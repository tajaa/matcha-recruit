"""tellus_app_22 — admin-granted consumer paid tiers.

Consumer gifts are separate from Stripe brand billing. The first paid-tier
entitlement is the Regulars board membership cap.
"""
from alembic import op


revision = "tellus_app_22"
down_revision = "tellus_app_21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tellus_accounts ADD COLUMN IF NOT EXISTS consumer_tier "
        "TEXT NOT NULL DEFAULT 'free'"
    )
    op.execute(
        "ALTER TABLE tellus_accounts ADD COLUMN IF NOT EXISTS consumer_tier_expires_at TIMESTAMPTZ"
    )
    op.execute(
        """DO $$ BEGIN
            ALTER TABLE tellus_accounts ADD CONSTRAINT ck_tellus_accounts_consumer_tier
                CHECK (consumer_tier IN ('free', 'paid'));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tellus_accounts DROP CONSTRAINT IF EXISTS ck_tellus_accounts_consumer_tier")
    op.execute("ALTER TABLE tellus_accounts DROP COLUMN IF EXISTS consumer_tier_expires_at")
    op.execute("ALTER TABLE tellus_accounts DROP COLUMN IF EXISTS consumer_tier")

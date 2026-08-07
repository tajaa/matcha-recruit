"""tellus_app_11 — per-listing redemption expiry.

Revision ID: tellus_app_11
Revises: tellus_app_10
"""
from alembic import op

revision = "tellus_app_11"
down_revision = "tellus_app_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Days a redeemed code stays valid; stamped onto tellus_redemptions.expires_at
    # at redeem time (points_service.redeem_points). 30 matches the pre-existing
    # code-level default so old listings behave identically.
    op.execute(
        "ALTER TABLE tellus_reward_listings "
        "ADD COLUMN IF NOT EXISTS expiry_days INTEGER NOT NULL DEFAULT 30"
    )
    op.execute(
        "ALTER TABLE tellus_reward_listings "
        "DROP CONSTRAINT IF EXISTS ck_tellus_listings_expiry_days"
    )
    op.execute(
        "ALTER TABLE tellus_reward_listings "
        "ADD CONSTRAINT ck_tellus_listings_expiry_days CHECK (expiry_days BETWEEN 1 AND 365)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tellus_reward_listings DROP CONSTRAINT IF EXISTS ck_tellus_listings_expiry_days")
    op.execute("ALTER TABLE tellus_reward_listings DROP COLUMN IF EXISTS expiry_days")

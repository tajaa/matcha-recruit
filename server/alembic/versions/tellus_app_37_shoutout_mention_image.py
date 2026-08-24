"""Persist Tell-Us shoutout mention post image (SerpApi profile API only)."""
from alembic import op


revision = "tellus_app_37"
down_revision = "tellus_app_36"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tellus_shoutout_mentions ADD COLUMN IF NOT EXISTS image_url TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE tellus_shoutout_mentions DROP COLUMN IF EXISTS image_url")

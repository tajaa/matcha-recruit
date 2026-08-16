"""tellus_app_27 - attach promo campaigns to Regulars board posts."""
from alembic import op


revision = "tellus_app_27"
down_revision = "tellus_app_26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """ALTER TABLE tellus_board_posts
           ADD COLUMN IF NOT EXISTS campaign_id UUID
           REFERENCES tellus_promo_campaigns(id) ON DELETE SET NULL"""
    )
    op.execute("ALTER TABLE tellus_board_posts DROP CONSTRAINT IF EXISTS tellus_board_posts_kind_check")
    op.execute(
        """ALTER TABLE tellus_board_posts ADD CONSTRAINT tellus_board_posts_kind_check
           CHECK (kind IN ('update', 'deal', 'event', 'question', 'promo'))"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_board_posts_campaign
           ON tellus_board_posts (campaign_id) WHERE campaign_id IS NOT NULL"""
    )


def downgrade() -> None:
    op.execute("DELETE FROM tellus_board_posts WHERE kind = 'promo'")
    op.execute("DROP INDEX IF EXISTS ix_tellus_board_posts_campaign")
    op.execute("ALTER TABLE tellus_board_posts DROP COLUMN IF EXISTS campaign_id")
    op.execute("ALTER TABLE tellus_board_posts DROP CONSTRAINT IF EXISTS tellus_board_posts_kind_check")
    op.execute(
        """ALTER TABLE tellus_board_posts ADD CONSTRAINT tellus_board_posts_kind_check
           CHECK (kind IN ('update', 'deal', 'event', 'question'))"""
    )

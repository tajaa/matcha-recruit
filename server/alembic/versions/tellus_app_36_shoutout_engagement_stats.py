"""Persist Tell-Us shoutout mention engagement stats."""
from alembic import op


revision = "tellus_app_36"
down_revision = "tellus_app_35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE tellus_shoutout_mentions
        ADD COLUMN IF NOT EXISTS like_count INT,
        ADD COLUMN IF NOT EXISTS comment_count INT,
        ADD COLUMN IF NOT EXISTS author_followers INT,
        ADD COLUMN IF NOT EXISTS author_verified BOOLEAN,
        ADD COLUMN IF NOT EXISTS posted_age TEXT,
        ADD COLUMN IF NOT EXISTS stats_source TEXT,
        ADD COLUMN IF NOT EXISTS stats_fetched_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS stats_status TEXT""")
    op.execute("""ALTER TABLE tellus_shoutout_mentions
        ADD CONSTRAINT ck_tellus_shoutout_mentions_stats_source
        CHECK (stats_source IS NULL OR stats_source IN ('search','profile_api')) NOT VALID""")
    op.execute("""ALTER TABLE tellus_shoutout_mentions
        ADD CONSTRAINT ck_tellus_shoutout_mentions_stats_status
        CHECK (stats_status IS NULL OR stats_status IN ('ok','not_found','unsupported','error')) NOT VALID""")


def downgrade() -> None:
    op.execute("""ALTER TABLE tellus_shoutout_mentions
        DROP CONSTRAINT IF EXISTS ck_tellus_shoutout_mentions_stats_source,
        DROP CONSTRAINT IF EXISTS ck_tellus_shoutout_mentions_stats_status,
        DROP COLUMN IF EXISTS like_count,
        DROP COLUMN IF EXISTS comment_count,
        DROP COLUMN IF EXISTS author_followers,
        DROP COLUMN IF EXISTS author_verified,
        DROP COLUMN IF EXISTS posted_age,
        DROP COLUMN IF EXISTS stats_source,
        DROP COLUMN IF EXISTS stats_fetched_at,
        DROP COLUMN IF EXISTS stats_status""")

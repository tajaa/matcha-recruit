"""Tell-Us loyalty social submissions: allow resubmitting a withdrawn post.

``ux_tellus_loyalty_social_url`` was unconditional on (brand_id,
canonical_url), so a consumer who withdrew a submission by mistake got a
permanent 409 duplicate_social_url on any future attempt to submit the same
post. Make the index partial so only non-withdrawn rows collide.
"""
from alembic import op


revision = "tellus_app_30"
down_revision = "tellus_app_29"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_tellus_loyalty_social_url")
    op.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_loyalty_social_url
           ON tellus_loyalty_social_submissions (brand_id, canonical_url)
           WHERE status <> 'withdrawn'"""
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_tellus_loyalty_social_url")
    op.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_loyalty_social_url
           ON tellus_loyalty_social_submissions (brand_id, canonical_url)"""
    )

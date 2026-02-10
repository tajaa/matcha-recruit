"""add hr news articles

Revision ID: r8s9t0u1v2w3
Revises: q7r8s9t0u1v2
Create Date: 2026-02-10
"""
from alembic import op
import sqlalchemy as sa

revision = "r8s9t0u1v2w3"
down_revision = ("q7r8s9t0u1v2", "f2bb0fb0d85f")
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hr_news_articles",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("item_hash", sa.VARCHAR(64), nullable=False, unique=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("link", sa.Text),
        sa.Column("author", sa.VARCHAR(255)),
        sa.Column("pub_date", sa.TIMESTAMP),
        sa.Column("source_name", sa.VARCHAR(100)),
        sa.Column("source_feed_url", sa.Text),
        sa.Column("image_url", sa.Text),
        sa.Column("full_content", sa.Text),
        sa.Column("content_fetched_at", sa.TIMESTAMP),
        sa.Column("content_error", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_hr_news_articles_pub_date", "hr_news_articles", [sa.text("pub_date DESC")])
    op.create_index("idx_hr_news_articles_source_name", "hr_news_articles", ["source_name"])
    op.create_index("idx_hr_news_articles_created_at", "hr_news_articles", [sa.text("created_at DESC")])


def downgrade():
    op.drop_index("idx_hr_news_articles_created_at")
    op.drop_index("idx_hr_news_articles_source_name")
    op.drop_index("idx_hr_news_articles_pub_date")
    op.drop_table("hr_news_articles")

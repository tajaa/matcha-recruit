"""extend policies table with category, source_type, and upload metadata

Revision ID: zq5r6s7t8u9v
Revises: zb2c3d4e5f6g
Create Date: 2026-03-18
"""
from alembic import op
import sqlalchemy as sa

revision = "zq5r6s7t8u9v"
down_revision = "zb2c3d4e5f6g"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("policies", sa.Column("category", sa.VARCHAR(50), nullable=True))
    op.add_column("policies", sa.Column("source_type", sa.VARCHAR(20), nullable=False, server_default="manual"))
    op.add_column("policies", sa.Column("effective_date", sa.Date(), nullable=True))
    op.add_column("policies", sa.Column("review_date", sa.Date(), nullable=True))
    op.add_column("policies", sa.Column("original_filename", sa.VARCHAR(500), nullable=True))
    op.add_column("policies", sa.Column("mime_type", sa.VARCHAR(100), nullable=True))
    op.add_column("policies", sa.Column("page_count", sa.Integer(), nullable=True))
    op.create_index("idx_policies_category", "policies", ["category"])


def downgrade() -> None:
    op.drop_index("idx_policies_category", table_name="policies")
    op.drop_column("policies", "page_count")
    op.drop_column("policies", "mime_type")
    op.drop_column("policies", "original_filename")
    op.drop_column("policies", "review_date")
    op.drop_column("policies", "effective_date")
    op.drop_column("policies", "source_type")
    op.drop_column("policies", "category")

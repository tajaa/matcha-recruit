"""add er case category and outcome columns

Revision ID: q1r2s3t4u5v6
Revises: z7a8b9c0d1e
Create Date: 2026-02-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "q1r2s3t4u5v6"
down_revision = "z7a8b9c0d1e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("er_cases", sa.Column("category", sa.String(50), nullable=True))
    op.add_column("er_cases", sa.Column("outcome", sa.String(50), nullable=True))
    op.create_index("idx_er_cases_category", "er_cases", ["category"])
    op.create_index("idx_er_cases_outcome", "er_cases", ["outcome"])

    # Backfill category from intake_context objective where mapping is reliable
    op.execute("""
        UPDATE er_cases
        SET category = 'policy_violation'
        WHERE category IS NULL
          AND intake_context->>'answers' IS NOT NULL
          AND (intake_context->'answers'->>'objective') = 'policy'
    """)


def downgrade() -> None:
    op.drop_index("idx_er_cases_outcome", table_name="er_cases")
    op.drop_index("idx_er_cases_category", table_name="er_cases")
    op.drop_column("er_cases", "outcome")
    op.drop_column("er_cases", "category")

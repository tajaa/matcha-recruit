"""Add index on metadata->>'research_source' for jurisdiction_requirements

Revision ID: zs7t8u9v0w1x
Revises: zr6s7t8u9v0w
Create Date: 2026-03-19
"""

from alembic import op

revision = "zs7t8u9v0w1x"
down_revision = "zr6s7t8u9v0w"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_jr_research_source "
        "ON jurisdiction_requirements ((metadata->>'research_source'))"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_jr_research_source")

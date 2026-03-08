"""add involved_employees JSONB to er_cases

Revision ID: m8n9o0p1q2r3
Revises: l7m8n9o0p1q2
Create Date: 2026-03-08
"""

from alembic import op


revision = "m8n9o0p1q2r3"
down_revision = "l7m8n9o0p1q2"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE er_cases
        ADD COLUMN IF NOT EXISTS involved_employees JSONB DEFAULT '[]'
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_er_cases_involved_employees
        ON er_cases USING GIN (involved_employees jsonb_path_ops)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_er_cases_involved_employees")
    op.execute("ALTER TABLE er_cases DROP COLUMN IF EXISTS involved_employees")

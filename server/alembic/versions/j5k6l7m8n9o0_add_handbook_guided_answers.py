"""add guided_answers JSONB column to handbooks

Revision ID: j5k6l7m8n9o0
Revises: i4j5k6l7m8n9
Create Date: 2026-03-07
"""

from alembic import op


revision = "j5k6l7m8n9o0"
down_revision = "i4j5k6l7m8n9"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE handbooks ADD COLUMN IF NOT EXISTS guided_answers JSONB DEFAULT '{}'")


def downgrade():
    op.execute("ALTER TABLE handbooks DROP COLUMN IF EXISTS guided_answers")

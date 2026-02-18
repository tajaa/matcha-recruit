"""add candidate_id FK to interviews for multi-signal ranking

Revision ID: z6a7b8c9d0e
Revises: y5z6a7b8c9d
Create Date: 2026-02-17
"""

from alembic import op


revision = "z6a7b8c9d0e"
down_revision = "y5z6a7b8c9d"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'interviews' AND column_name = 'candidate_id'
            ) THEN
                ALTER TABLE interviews ADD COLUMN candidate_id UUID REFERENCES candidates(id) ON DELETE SET NULL;
            END IF;
        END$$;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_interviews_candidate_id ON interviews(candidate_id)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_interviews_candidate_id")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'interviews' AND column_name = 'candidate_id'
            ) THEN
                ALTER TABLE interviews DROP COLUMN candidate_id;
            END IF;
        END$$;
        """
    )

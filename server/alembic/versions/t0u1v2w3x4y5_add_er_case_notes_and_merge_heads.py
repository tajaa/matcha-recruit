"""add er_case_notes and merge heads

Revision ID: t0u1v2w3x4y5
Revises: i5j6k7l8m9n0, s9t0u1v2w3x4
Create Date: 2026-02-16
"""

from alembic import op


revision = "t0u1v2w3x4y5"
down_revision = ("i5j6k7l8m9n0", "s9t0u1v2w3x4")
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS er_case_notes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id UUID NOT NULL REFERENCES er_cases(id) ON DELETE CASCADE,
            note_type VARCHAR(50) NOT NULL DEFAULT 'general'
                CHECK (note_type IN ('general', 'question', 'answer', 'guidance', 'system')),
            content TEXT NOT NULL,
            metadata JSONB,
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_er_case_notes_case_id ON er_case_notes(case_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_er_case_notes_created_at ON er_case_notes(created_at DESC)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_er_case_notes_created_at")
    op.execute("DROP INDEX IF EXISTS idx_er_case_notes_case_id")
    op.execute("DROP TABLE IF EXISTS er_case_notes")

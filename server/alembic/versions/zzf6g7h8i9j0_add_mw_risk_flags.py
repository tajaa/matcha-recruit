"""Add mw_risk_flags table for pre-computed dashboard risk analysis.

Revision ID: zzf6g7h8i9j0
Revises: zze5f6g7h8i9
Create Date: 2026-04-05
"""
from alembic import op

revision = "zzf6g7h8i9j0"
down_revision = "zze5f6g7h8i9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_risk_flags (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            priority INT NOT NULL DEFAULT 0,
            category TEXT NOT NULL,
            location_subject TEXT NOT NULL,
            description TEXT NOT NULL,
            recommendation TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'medium',
            source_type TEXT NOT NULL DEFAULT 'pattern',
            source_id TEXT,
            link TEXT,
            group_label TEXT DEFAULT 'Locations',
            is_ai_generated BOOLEAN DEFAULT FALSE,
            analyzed_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_risk_flags_company
        ON mw_risk_flags(company_id, priority)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_mw_risk_flags_company")
    op.execute("DROP TABLE IF EXISTS mw_risk_flags")

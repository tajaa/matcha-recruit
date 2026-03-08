"""add risk_assessment_history table and company scheduling columns

Revision ID: k6l7m8n9o0p1
Revises: j5k6l7m8n9o0
Create Date: 2026-03-07
"""

from alembic import op


revision = "k6l7m8n9o0p1"
down_revision = "j5k6l7m8n9o0"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS risk_assessment_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            overall_score INT NOT NULL,
            overall_band TEXT NOT NULL,
            dimensions JSONB NOT NULL,
            weights JSONB NOT NULL,
            computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            source VARCHAR(20) NOT NULL DEFAULT 'scheduled'
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_risk_history_company_date
        ON risk_assessment_history(company_id, computed_at DESC)
    """)
    op.execute("""
        ALTER TABLE companies ADD COLUMN IF NOT EXISTS next_risk_assessment TIMESTAMPTZ
    """)
    op.execute("""
        ALTER TABLE companies ADD COLUMN IF NOT EXISTS risk_assessment_interval_days INTEGER DEFAULT 7
    """)
    op.execute("""
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES ('risk_assessment', 'Risk Assessment', 'Automated weekly risk assessment scoring for all companies.', false, 3)
        ON CONFLICT (task_key) DO NOTHING
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS risk_assessment_history")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS next_risk_assessment")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS risk_assessment_interval_days")
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'risk_assessment'")

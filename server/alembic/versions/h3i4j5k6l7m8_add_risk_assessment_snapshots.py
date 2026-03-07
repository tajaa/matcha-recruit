"""add risk_assessment_snapshots table

Revision ID: h3i4j5k6l7m8
Revises: g2h3i4j5k6l7
Create Date: 2026-03-07
"""

from alembic import op


revision = "h3i4j5k6l7m8"
down_revision = "g2h3i4j5k6l7"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS risk_assessment_snapshots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            overall_score INT NOT NULL,
            overall_band TEXT NOT NULL,
            dimensions JSONB NOT NULL,
            report TEXT,
            recommendations JSONB,
            weights JSONB NOT NULL,
            computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            computed_by UUID REFERENCES users(id),
            UNIQUE (company_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_risk_assessment_snapshots_company
        ON risk_assessment_snapshots(company_id)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS risk_assessment_snapshots")

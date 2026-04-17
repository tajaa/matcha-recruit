"""add flight_risk_snapshots table

Revision ID: zzz6a7b8c9d0
Revises: zzy5z6a7b8c9
Create Date: 2026-04-16

Backs §3.3 of QSR_RETENTION_PLAN.md — composite flight-risk score
(0-100, six factors) per active employee. Snapshot rows let us trend
the score over time, backtest weights against actual separations,
and surface "trending up" deltas in the per-employee drawer.

Service: server/app/matcha/services/flight_risk_service.py
"""

from alembic import op


revision = "zzz6a7b8c9d0"
down_revision = "zzy5z6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS flight_risk_snapshots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            employee_id UUID NOT NULL,
            score INTEGER NOT NULL,
            tier VARCHAR(20) NOT NULL,
            factors JSONB NOT NULL DEFAULT '[]'::jsonb,
            top_factor VARCHAR(50),
            computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_flight_risk_score CHECK (score BETWEEN 0 AND 100),
            CONSTRAINT chk_flight_risk_tier
                CHECK (tier IN ('low', 'elevated', 'high', 'critical'))
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_flight_risk_org_computed
        ON flight_risk_snapshots (org_id, computed_at DESC)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_flight_risk_employee_computed
        ON flight_risk_snapshots (employee_id, computed_at DESC)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_flight_risk_employee_computed")
    op.execute("DROP INDEX IF EXISTS idx_flight_risk_org_computed")
    op.execute("DROP TABLE IF EXISTS flight_risk_snapshots")

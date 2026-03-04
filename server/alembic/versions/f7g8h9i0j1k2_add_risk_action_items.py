"""add risk action items

Revision ID: f7g8h9i0j1k2
Revises: z7a8b9c0d1e
Create Date: 2026-03-04
"""

from alembic import op


revision = "f7g8h9i0j1k2"
down_revision = "z7a8b9c0d1e"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS risk_action_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            source_type VARCHAR(50) NOT NULL,
            source_ref VARCHAR(255),
            title TEXT NOT NULL,
            description TEXT,
            assigned_to UUID REFERENCES users(id),
            due_date DATE,
            status VARCHAR(20) NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'completed', 'dismissed')),
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            closed_at TIMESTAMP
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_risk_action_items_company "
        "ON risk_action_items(company_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_risk_action_items_status "
        "ON risk_action_items(status)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS risk_action_items")

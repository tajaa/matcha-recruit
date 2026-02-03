"""Add verification_outcomes table for confidence calibration

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'h8i9j0k1l2m3'
down_revision: Union[str, None] = 'g7h8i9j0k1l2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create verification_outcomes table for tracking prediction calibration
    # Using raw SQL with IF NOT EXISTS for idempotency
    op.execute("""
        CREATE TABLE IF NOT EXISTS verification_outcomes (
            id SERIAL PRIMARY KEY,
            jurisdiction_id UUID REFERENCES jurisdictions(id) ON DELETE SET NULL,
            alert_id UUID REFERENCES compliance_alerts(id) ON DELETE SET NULL,
            requirement_key TEXT NOT NULL,
            category VARCHAR(50),
            predicted_confidence DECIMAL(3, 2) NOT NULL,
            predicted_is_change BOOLEAN NOT NULL,
            verification_sources JSONB,
            actual_is_change BOOLEAN,
            reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            reviewed_at TIMESTAMP,
            admin_notes TEXT,
            correction_reason VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW() NOT NULL
        )
    """)

    # Create indexes for analysis queries (IF NOT EXISTS)
    op.execute("CREATE INDEX IF NOT EXISTS idx_verification_outcomes_jurisdiction_id ON verification_outcomes(jurisdiction_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_verification_outcomes_category ON verification_outcomes(category)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_verification_outcomes_predicted_confidence ON verification_outcomes(predicted_confidence)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_verification_outcomes_actual_is_change ON verification_outcomes(actual_is_change)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_verification_outcomes_created_at ON verification_outcomes(created_at)")


def downgrade() -> None:
    # Drop indexes (IF EXISTS)
    op.execute("DROP INDEX IF EXISTS idx_verification_outcomes_created_at")
    op.execute("DROP INDEX IF EXISTS idx_verification_outcomes_actual_is_change")
    op.execute("DROP INDEX IF EXISTS idx_verification_outcomes_predicted_confidence")
    op.execute("DROP INDEX IF EXISTS idx_verification_outcomes_category")
    op.execute("DROP INDEX IF EXISTS idx_verification_outcomes_jurisdiction_id")

    # Drop table
    op.execute("DROP TABLE IF EXISTS verification_outcomes")

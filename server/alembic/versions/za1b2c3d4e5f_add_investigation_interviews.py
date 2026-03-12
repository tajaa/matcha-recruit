"""add investigation interviews for IR incidents

Revision ID: za1b2c3d4e5f
Revises: z9a0b1c2d3e4
Create Date: 2026-03-11
"""

from alembic import op


revision = "za1b2c3d4e5f"
down_revision = "z9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add er_case_id column to ir_incidents
    op.execute(
        "ALTER TABLE ir_incidents ADD COLUMN IF NOT EXISTS er_case_id UUID REFERENCES er_cases(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ir_incidents_er_case_id ON ir_incidents(er_case_id) WHERE er_case_id IS NOT NULL"
    )

    # 2. Add investigation-related columns to interviews
    op.execute(
        "ALTER TABLE interviews ADD COLUMN IF NOT EXISTS incident_id UUID REFERENCES ir_incidents(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE interviews ADD COLUMN IF NOT EXISTS er_case_id UUID REFERENCES er_cases(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE interviews ADD COLUMN IF NOT EXISTS interviewee_role VARCHAR(50)"
    )
    op.execute(
        "ALTER TABLE interviews ADD COLUMN IF NOT EXISTS investigation_analysis JSONB"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_interviews_incident_id ON interviews(incident_id) WHERE incident_id IS NOT NULL"
    )

    # 3. Create junction table for investigation interviews
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ir_investigation_interviews (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id UUID NOT NULL REFERENCES ir_incidents(id) ON DELETE CASCADE,
            interview_id UUID NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
            er_case_id UUID REFERENCES er_cases(id) ON DELETE SET NULL,
            interviewee_role VARCHAR(50),
            interviewee_name VARCHAR(255),
            interviewee_email VARCHAR(255),
            questions_generated JSONB,
            status VARCHAR(50) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW(),
            completed_at TIMESTAMP
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_irii_incident_id ON ir_investigation_interviews(incident_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_irii_interview_id ON ir_investigation_interviews(interview_id)"
    )


def downgrade():
    # Drop junction table indexes and table
    op.execute("DROP INDEX IF EXISTS idx_irii_interview_id")
    op.execute("DROP INDEX IF EXISTS idx_irii_incident_id")
    op.execute("DROP TABLE IF EXISTS ir_investigation_interviews")

    # Drop interviews columns
    op.execute("DROP INDEX IF EXISTS idx_interviews_incident_id")
    op.execute("ALTER TABLE interviews DROP COLUMN IF EXISTS investigation_analysis")
    op.execute("ALTER TABLE interviews DROP COLUMN IF EXISTS interviewee_role")
    op.execute("ALTER TABLE interviews DROP COLUMN IF EXISTS er_case_id")
    op.execute("ALTER TABLE interviews DROP COLUMN IF EXISTS incident_id")

    # Drop ir_incidents column
    op.execute("DROP INDEX IF EXISTS idx_ir_incidents_er_case_id")
    op.execute("ALTER TABLE ir_incidents DROP COLUMN IF EXISTS er_case_id")

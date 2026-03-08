"""add OSHA 300/301 log fields and annual summaries table

Revision ID: v4w5x6y7z8a9
Revises: c6d7e8f9a0b1
Create Date: 2026-03-08
"""

from alembic import op


revision = "v4w5x6y7z8a9"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE ir_incidents ADD COLUMN IF NOT EXISTS osha_recordable BOOLEAN;
        ALTER TABLE ir_incidents ADD COLUMN IF NOT EXISTS osha_case_number VARCHAR(20);
        ALTER TABLE ir_incidents ADD COLUMN IF NOT EXISTS osha_classification VARCHAR(30);
        ALTER TABLE ir_incidents ADD COLUMN IF NOT EXISTS days_away_from_work INTEGER DEFAULT 0;
        ALTER TABLE ir_incidents ADD COLUMN IF NOT EXISTS days_restricted_duty INTEGER DEFAULT 0;
        ALTER TABLE ir_incidents ADD COLUMN IF NOT EXISTS date_of_death DATE;
        ALTER TABLE ir_incidents ADD COLUMN IF NOT EXISTS osha_form_301_data JSONB;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS osha_annual_summaries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            year INTEGER NOT NULL,
            establishment_name VARCHAR(255),
            total_cases INTEGER DEFAULT 0,
            total_deaths INTEGER DEFAULT 0,
            total_days_away_cases INTEGER DEFAULT 0,
            total_restricted_cases INTEGER DEFAULT 0,
            total_other_recordable INTEGER DEFAULT 0,
            total_days_away INTEGER DEFAULT 0,
            total_days_restricted INTEGER DEFAULT 0,
            total_injuries INTEGER DEFAULT 0,
            total_skin_disorders INTEGER DEFAULT 0,
            total_respiratory INTEGER DEFAULT 0,
            total_poisonings INTEGER DEFAULT 0,
            total_hearing_loss INTEGER DEFAULT 0,
            total_other_illnesses INTEGER DEFAULT 0,
            average_employees INTEGER,
            total_hours_worked INTEGER,
            certified_by VARCHAR(255),
            certified_title VARCHAR(255),
            certified_date DATE,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(company_id, year)
        );
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS osha_annual_summaries")
    op.execute(
        """
        ALTER TABLE ir_incidents
            DROP COLUMN IF EXISTS osha_form_301_data,
            DROP COLUMN IF EXISTS date_of_death,
            DROP COLUMN IF EXISTS days_restricted_duty,
            DROP COLUMN IF EXISTS days_away_from_work,
            DROP COLUMN IF EXISTS osha_classification,
            DROP COLUMN IF EXISTS osha_case_number,
            DROP COLUMN IF EXISTS osha_recordable;
        """
    )

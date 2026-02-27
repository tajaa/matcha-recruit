"""add company profile columns for AI context

Revision ID: o1p2q3r4s5t6
Revises: n8p9q0r1s2t3
Create Date: 2026-02-27
"""

from alembic import op


revision = "o1p2q3r4s5t6"
down_revision = "n8p9q0r1s2t3"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'headquarters_state') THEN
                ALTER TABLE companies ADD COLUMN headquarters_state VARCHAR(50);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'headquarters_city') THEN
                ALTER TABLE companies ADD COLUMN headquarters_city VARCHAR(100);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'work_arrangement') THEN
                ALTER TABLE companies ADD COLUMN work_arrangement VARCHAR(30);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'default_employment_type') THEN
                ALTER TABLE companies ADD COLUMN default_employment_type VARCHAR(30);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'benefits_summary') THEN
                ALTER TABLE companies ADD COLUMN benefits_summary TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'pto_policy_summary') THEN
                ALTER TABLE companies ADD COLUMN pto_policy_summary TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'compensation_notes') THEN
                ALTER TABLE companies ADD COLUMN compensation_notes TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'company_values') THEN
                ALTER TABLE companies ADD COLUMN company_values TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'ai_guidance_notes') THEN
                ALTER TABLE companies ADD COLUMN ai_guidance_notes TEXT;
            END IF;
        END $$;
        """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE companies
            DROP COLUMN IF EXISTS headquarters_state,
            DROP COLUMN IF EXISTS headquarters_city,
            DROP COLUMN IF EXISTS work_arrangement,
            DROP COLUMN IF EXISTS default_employment_type,
            DROP COLUMN IF EXISTS benefits_summary,
            DROP COLUMN IF EXISTS pto_policy_summary,
            DROP COLUMN IF EXISTS compensation_notes,
            DROP COLUMN IF EXISTS company_values,
            DROP COLUMN IF EXISTS ai_guidance_notes;
        """
    )

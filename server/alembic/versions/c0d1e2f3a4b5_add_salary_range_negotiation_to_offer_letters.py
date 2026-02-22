"""add salary range negotiation to offer letters

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a
Create Date: 2026-02-22
"""

from alembic import op


revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'salary_range_min') THEN
                ALTER TABLE offer_letters ADD COLUMN salary_range_min DECIMAL(10,2);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'salary_range_max') THEN
                ALTER TABLE offer_letters ADD COLUMN salary_range_max DECIMAL(10,2);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'candidate_range_min') THEN
                ALTER TABLE offer_letters ADD COLUMN candidate_range_min DECIMAL(10,2);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'candidate_range_max') THEN
                ALTER TABLE offer_letters ADD COLUMN candidate_range_max DECIMAL(10,2);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'matched_salary') THEN
                ALTER TABLE offer_letters ADD COLUMN matched_salary DECIMAL(10,2);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'range_match_status') THEN
                ALTER TABLE offer_letters ADD COLUMN range_match_status VARCHAR(50);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'candidate_token') THEN
                ALTER TABLE offer_letters ADD COLUMN candidate_token VARCHAR(64) UNIQUE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'candidate_email') THEN
                ALTER TABLE offer_letters ADD COLUMN candidate_email VARCHAR(255);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'candidate_token_expires_at') THEN
                ALTER TABLE offer_letters ADD COLUMN candidate_token_expires_at TIMESTAMP;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'negotiation_round') THEN
                ALTER TABLE offer_letters ADD COLUMN negotiation_round INTEGER DEFAULT 1;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'max_negotiation_rounds') THEN
                ALTER TABLE offer_letters ADD COLUMN max_negotiation_rounds INTEGER DEFAULT 3;
            END IF;
        END $$;
    """)


def downgrade():
    op.execute("""
        ALTER TABLE offer_letters
            DROP COLUMN IF EXISTS salary_range_min,
            DROP COLUMN IF EXISTS salary_range_max,
            DROP COLUMN IF EXISTS candidate_range_min,
            DROP COLUMN IF EXISTS candidate_range_max,
            DROP COLUMN IF EXISTS matched_salary,
            DROP COLUMN IF EXISTS range_match_status,
            DROP COLUMN IF EXISTS candidate_token,
            DROP COLUMN IF EXISTS candidate_email,
            DROP COLUMN IF EXISTS candidate_token_expires_at,
            DROP COLUMN IF EXISTS negotiation_round,
            DROP COLUMN IF EXISTS max_negotiation_rounds;
    """)

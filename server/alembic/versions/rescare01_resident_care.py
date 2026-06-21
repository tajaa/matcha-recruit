"""Resident-care risk asset: safety programs + MVR reviews

Revision ID: rescare01
Revises: wcclass01
Create Date: 2026-06-20

Healthcare / senior-living "resident-care risk management program" (WTW p.175)
+ MVR reviews at hire & annually (p.176). Gated by the `resident_care` feature.
- safety_programs — fall-prevention/infection-control/abuse-prevention/… register.
- mvr_reviews     — motor-vehicle-record reviews (hire + annual cadence).
"""

from alembic import op


revision = "rescare01"
down_revision = "wcclass01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS safety_programs (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id         UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            program_type       VARCHAR(30) NOT NULL
                                 CHECK (program_type IN ('fall_prevention','infection_control',
                                        'abuse_prevention','emergency_prep','medication_safety','other')),
            name               VARCHAR(255) NOT NULL,
            status             VARCHAR(12) NOT NULL DEFAULT 'active'
                                 CHECK (status IN ('active','inactive')),
            last_reviewed_date DATE,
            owner              VARCHAR(255),
            notes              TEXT,
            created_by         UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at         TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_safety_programs_company ON safety_programs(company_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mvr_reviews (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id    UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            driver_name   VARCHAR(255) NOT NULL,
            employee_id   UUID,
            review_type   VARCHAR(10) NOT NULL DEFAULT 'annual'
                            CHECK (review_type IN ('hire','annual')),
            review_date   DATE,
            status        VARCHAR(10) NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('clear','flagged','pending')),
            next_due_date DATE,
            notes         TEXT,
            created_by    UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_mvr_reviews_company ON mvr_reviews(company_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS mvr_reviews")
    op.execute("DROP TABLE IF EXISTS safety_programs")

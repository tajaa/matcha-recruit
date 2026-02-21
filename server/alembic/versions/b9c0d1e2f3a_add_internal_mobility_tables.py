"""add internal mobility tables

Revision ID: b9c0d1e2f3a
Revises: a7b8c9d0e1f, a8b9c0d1e2f, d4e5f6g7h8i9
Create Date: 2026-02-21
"""

from alembic import op


revision = "b9c0d1e2f3a"
down_revision = ("a7b8c9d0e1f", "a8b9c0d1e2f", "d4e5f6g7h8i9")
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_career_profiles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            target_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
            target_departments JSONB NOT NULL DEFAULT '[]'::jsonb,
            skills JSONB NOT NULL DEFAULT '[]'::jsonb,
            interests JSONB NOT NULL DEFAULT '[]'::jsonb,
            mobility_opt_in BOOLEAN NOT NULL DEFAULT true,
            visibility VARCHAR(20) NOT NULL DEFAULT 'private'
                CHECK (visibility IN ('private', 'hr_only', 'manager_visible')),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(employee_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employee_career_profiles_org_id
            ON employee_career_profiles(org_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employee_career_profiles_employee_id
            ON employee_career_profiles(employee_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employee_career_profiles_org_opt_in
            ON employee_career_profiles(org_id, mobility_opt_in)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS internal_opportunities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            type VARCHAR(20) NOT NULL
                CHECK (type IN ('role', 'project')),
            position_id UUID REFERENCES positions(id) ON DELETE SET NULL,
            title VARCHAR(255) NOT NULL,
            department VARCHAR(100),
            description TEXT,
            required_skills JSONB NOT NULL DEFAULT '[]'::jsonb,
            preferred_skills JSONB NOT NULL DEFAULT '[]'::jsonb,
            duration_weeks INTEGER
                CHECK (duration_weeks IS NULL OR duration_weeks > 0),
            status VARCHAR(20) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'active', 'closed')),
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_internal_opportunities_org_status
            ON internal_opportunities(org_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_internal_opportunities_type
            ON internal_opportunities(type)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS internal_opportunity_matches (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            opportunity_id UUID NOT NULL REFERENCES internal_opportunities(id) ON DELETE CASCADE,
            match_score FLOAT,
            reasons JSONB,
            status VARCHAR(20) NOT NULL DEFAULT 'suggested'
                CHECK (status IN ('suggested', 'saved', 'dismissed', 'applied')),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(employee_id, opportunity_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_internal_opportunity_matches_employee_status
            ON internal_opportunity_matches(employee_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_internal_opportunity_matches_opportunity_id
            ON internal_opportunity_matches(opportunity_id)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS internal_opportunity_applications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            opportunity_id UUID NOT NULL REFERENCES internal_opportunities(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'new'
                CHECK (status IN ('new', 'in_review', 'shortlisted', 'aligned', 'closed')),
            employee_notes TEXT,
            submitted_at TIMESTAMP NOT NULL DEFAULT NOW(),
            reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            reviewed_at TIMESTAMP,
            manager_notified_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(employee_id, opportunity_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_internal_opportunity_applications_opportunity_status
            ON internal_opportunity_applications(opportunity_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_internal_opportunity_applications_employee_id
            ON internal_opportunity_applications(employee_id)
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_internal_opportunity_applications_employee_id")
    op.execute("DROP INDEX IF EXISTS idx_internal_opportunity_applications_opportunity_status")
    op.execute("DROP TABLE IF EXISTS internal_opportunity_applications")

    op.execute("DROP INDEX IF EXISTS idx_internal_opportunity_matches_opportunity_id")
    op.execute("DROP INDEX IF EXISTS idx_internal_opportunity_matches_employee_status")
    op.execute("DROP TABLE IF EXISTS internal_opportunity_matches")

    op.execute("DROP INDEX IF EXISTS idx_internal_opportunities_type")
    op.execute("DROP INDEX IF EXISTS idx_internal_opportunities_org_status")
    op.execute("DROP TABLE IF EXISTS internal_opportunities")

    op.execute("DROP INDEX IF EXISTS idx_employee_career_profiles_org_opt_in")
    op.execute("DROP INDEX IF EXISTS idx_employee_career_profiles_employee_id")
    op.execute("DROP INDEX IF EXISTS idx_employee_career_profiles_org_id")
    op.execute("DROP TABLE IF EXISTS employee_career_profiles")

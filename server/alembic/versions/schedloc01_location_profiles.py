"""Per-location scheduling profile: hours, default week template, leader job.

The whole-week builder only knows two demand sources (existing draft shifts, or
a saved week template). A store that has neither cannot be built at all, which
is what this table fixes: Huume interviews the manager once, saves the answers
here, and points `default_week_template_id` at the location's own pattern.

`week_start_weekday` is stored now and consumed by the editor/week-math work
that follows; 0 (Sunday) preserves today's hard-coded behavior everywhere.

Revision ID: schedloc01
Revises: empsched21
"""

from alembic import op


revision = "schedloc01"
down_revision = "empsched21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_location_profiles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID NOT NULL UNIQUE REFERENCES business_locations(id) ON DELETE CASCADE,
            operating_hours JSONB NOT NULL DEFAULT '{}'::jsonb,
            default_week_template_id UUID REFERENCES schedule_week_templates(id) ON DELETE SET NULL,
            leader_job_id UUID REFERENCES schedule_jobs(id) ON DELETE SET NULL,
            notes TEXT,
            week_start_weekday SMALLINT NOT NULL DEFAULT 0,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_schedule_location_profiles_week_start_weekday
                CHECK (week_start_weekday BETWEEN 0 AND 6)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_schedule_location_profiles_company
        ON schedule_location_profiles(company_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS schedule_location_profiles")

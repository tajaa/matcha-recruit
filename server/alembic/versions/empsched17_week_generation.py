"""Persist Huume whole-week schedule generation proposals.

Revision ID: empsched17
Revises: empsched16
"""

from alembic import op


revision = "empsched17"
down_revision = "empsched16"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_generation_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
            week_start DATE NOT NULL,
            thread_id UUID REFERENCES mw_threads(id) ON DELETE SET NULL,
            source_mode VARCHAR(20) NOT NULL,
            week_template_id UUID REFERENCES schedule_week_templates(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'proposed',
            input_hash VARCHAR(64) NOT NULL,
            planner_version VARCHAR(32) NOT NULL,
            constraints JSONB NOT NULL DEFAULT '{}'::jsonb,
            proposal JSONB NOT NULL DEFAULT '{}'::jsonb,
            metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            applied_by UUID REFERENCES users(id) ON DELETE SET NULL,
            applied_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT schedule_generation_runs_source_check
                CHECK (source_mode IN ('existing', 'template')),
            CONSTRAINT schedule_generation_runs_status_check
                CHECK (status IN ('proposed', 'applied', 'stale', 'cancelled', 'failed'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_schedule_generation_runs_scope
        ON schedule_generation_runs(company_id, location_id, week_start, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_schedule_generation_runs_thread
        ON schedule_generation_runs(thread_id, created_at DESC)
        WHERE thread_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS schedule_generation_runs")

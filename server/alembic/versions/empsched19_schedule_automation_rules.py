"""Add tenant-scoped schedule automation rules.

Revision ID: empsched19
Revises: empsched18
"""

from alembic import op


revision = "empsched19"
down_revision = "empsched18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_automation_rules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
            week_template_id UUID REFERENCES schedule_week_templates(id) ON DELETE SET NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            cadence VARCHAR(16) NOT NULL DEFAULT 'weekly',
            run_weekday SMALLINT,
            run_date DATE,
            run_time TIME NOT NULL,
            target_weeks_ahead SMALLINT,
            target_week_start DATE,
            next_run_at TIMESTAMPTZ,
            schedule_version INTEGER NOT NULL DEFAULT 1,
            last_attempt_at TIMESTAMPTZ,
            last_completed_at TIMESTAMPTZ,
            last_status VARCHAR(24),
            last_message TEXT,
            last_generation_run_id UUID REFERENCES schedule_generation_runs(id) ON DELETE SET NULL,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT schedule_automation_rules_location_unique UNIQUE(company_id, location_id),
            CONSTRAINT schedule_automation_rules_cadence_check CHECK (cadence IN ('weekly', 'once')),
            CONSTRAINT schedule_automation_rules_weekday_check CHECK (run_weekday BETWEEN 0 AND 6),
            CONSTRAINT schedule_automation_rules_weeks_ahead_check CHECK (target_weeks_ahead BETWEEN 1 AND 8),
            CONSTRAINT schedule_automation_rules_shape_check CHECK (
                (cadence='weekly' AND run_weekday IS NOT NULL AND run_date IS NULL
                    AND target_weeks_ahead IS NOT NULL AND target_week_start IS NULL)
                OR
                (cadence='once' AND run_weekday IS NULL AND run_date IS NOT NULL
                    AND target_weeks_ahead IS NULL AND target_week_start IS NOT NULL)
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_schedule_automation_rules_next_run
        ON schedule_automation_rules(next_run_at)
        WHERE enabled=true AND next_run_at IS NOT NULL
        """
    )
    # empsched18 registered a tenant-wide sweep. Rules now enqueue their exact
    # ETA directly, so retaining that global dispatcher would restore the
    # blanket cadence this migration replaces.
    op.execute("DELETE FROM scheduler_settings WHERE task_key='schedule_auto_generation'")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS schedule_automation_rules")
    op.execute(
        """
        INSERT INTO scheduler_settings(task_key, display_name, description, enabled, max_per_cycle)
        VALUES(
            'schedule_auto_generation',
            'Automatic weekly schedule suggestions',
            'Prepares next-week schedule proposals for manager review; never publishes them.',
            true,
            100
        )
        ON CONFLICT (task_key) DO NOTHING
        """
    )

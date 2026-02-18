"""add onboarding reminder infrastructure

Revision ID: z7a8b9c0d1e
Revises: y5z6a7b8c9d
Create Date: 2026-02-18
"""

from alembic import op


revision = "z7a8b9c0d1e"
down_revision = "y5z6a7b8c9d"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE employee_onboarding_tasks
            ADD COLUMN IF NOT EXISTS assignee_reminded_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS manager_reminded_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS hr_reminded_at TIMESTAMP
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employee_onboarding_tasks_pending_due_date
            ON employee_onboarding_tasks(due_date)
            WHERE status = 'pending' AND due_date IS NOT NULL
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS onboarding_notification_settings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL UNIQUE REFERENCES companies(id) ON DELETE CASCADE,
            timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
            quiet_hours_start SMALLINT,
            quiet_hours_end SMALLINT,
            business_days SMALLINT[] NOT NULL DEFAULT ARRAY[0, 1, 2, 3, 4],
            reminder_days_before_due INTEGER NOT NULL DEFAULT 1,
            escalate_to_manager_after_days INTEGER NOT NULL DEFAULT 3,
            escalate_to_hr_after_days INTEGER NOT NULL DEFAULT 5,
            hr_escalation_emails TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            email_enabled BOOLEAN NOT NULL DEFAULT true,
            in_app_enabled BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT check_onboarding_quiet_hours_start
                CHECK (quiet_hours_start IS NULL OR (quiet_hours_start >= 0 AND quiet_hours_start <= 23)),
            CONSTRAINT check_onboarding_quiet_hours_end
                CHECK (quiet_hours_end IS NULL OR (quiet_hours_end >= 0 AND quiet_hours_end <= 23)),
            CONSTRAINT check_onboarding_reminder_days
                CHECK (reminder_days_before_due >= 0),
            CONSTRAINT check_onboarding_escalation_days
                CHECK (
                    escalate_to_manager_after_days >= 1
                    AND escalate_to_hr_after_days >= escalate_to_manager_after_days
                )
        )
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_onboarding_notification_settings_org_id
            ON onboarding_notification_settings(org_id)
        """
    )

    op.execute(
        """
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'onboarding_reminders',
            'Onboarding Reminders',
            'Sends onboarding reminders and escalation emails for pending tasks.',
            false,
            200
        )
        ON CONFLICT (task_key) DO NOTHING
        """
    )


def downgrade():
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'onboarding_reminders'")
    op.execute("DROP INDEX IF EXISTS idx_onboarding_notification_settings_org_id")
    op.execute("DROP TABLE IF EXISTS onboarding_notification_settings")
    op.execute("DROP INDEX IF EXISTS idx_employee_onboarding_tasks_pending_due_date")
    op.execute(
        """
        ALTER TABLE employee_onboarding_tasks
            DROP COLUMN IF EXISTS hr_reminded_at,
            DROP COLUMN IF EXISTS manager_reminded_at,
            DROP COLUMN IF EXISTS assignee_reminded_at
        """
    )

"""Enable scheduled, review-only weekly schedule suggestions.

Revision ID: empsched18
Revises: empsched17
"""

from alembic import op


revision = "empsched18"
down_revision = "empsched17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE schedule_generation_runs
        ADD COLUMN IF NOT EXISTS origin VARCHAR(20) NOT NULL DEFAULT 'manual'
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'schedule_generation_runs_origin_check'
            ) THEN
                ALTER TABLE schedule_generation_runs
                ADD CONSTRAINT schedule_generation_runs_origin_check
                CHECK (origin IN ('manual', 'automatic'));
            END IF;
        END $$
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_schedule_automatic_generation_scope
        ON schedule_generation_runs(company_id, location_id, week_start)
        WHERE origin='automatic' AND status IN ('proposed', 'applied')
        """
    )
    op.execute(
        """
        INSERT INTO scheduler_settings(
            task_key, display_name, description, enabled, max_per_cycle
        ) VALUES (
            'schedule_auto_generation',
            'Automatic weekly schedule suggestions',
            'Prepares next-week schedule proposals for manager review; never publishes them.',
            true,
            100
        )
        ON CONFLICT (task_key) DO UPDATE SET
            display_name=EXCLUDED.display_name,
            description=EXCLUDED.description,
            enabled=true
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM scheduler_settings WHERE task_key='schedule_auto_generation'")
    op.execute("DROP INDEX IF EXISTS uniq_schedule_automatic_generation_scope")
    op.execute(
        "ALTER TABLE schedule_generation_runs "
        "DROP CONSTRAINT IF EXISTS schedule_generation_runs_origin_check"
    )
    op.execute("ALTER TABLE schedule_generation_runs DROP COLUMN IF EXISTS origin")

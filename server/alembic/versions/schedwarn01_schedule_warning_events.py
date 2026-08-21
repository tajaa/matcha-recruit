"""Persist scheduling competency warnings in EMS.

The schedule page can show a warning immediately, while EMS needs a durable
record that can be assigned or resolved. Generated records are deliberately
source-tagged and are not channel reports.
"""

from alembic import op


revision = "schedwarn01"
down_revision = ("matchaops02", "brokerrenew01")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ems_events ADD COLUMN IF NOT EXISTS source_kind VARCHAR(80)"
    )
    op.execute(
        "ALTER TABLE ems_events ADD COLUMN IF NOT EXISTS source_ref VARCHAR(255)"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_ems_events_active_source
        ON ems_events(company_id, source_kind, source_ref)
        WHERE status = 'logged' AND source_kind IS NOT NULL AND source_ref IS NOT NULL
        """
    )
    op.execute(
        """
        INSERT INTO scheduler_settings
            (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'schedule_warning_events',
            'Schedule warning events',
            'Reconcile expired training and credential warnings into EMS.',
            false,
            500
        )
        ON CONFLICT (task_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'schedule_warning_events'")
    op.execute("DROP INDEX IF EXISTS uniq_ems_events_active_source")
    op.execute("ALTER TABLE ems_events DROP COLUMN IF EXISTS source_ref")
    op.execute("ALTER TABLE ems_events DROP COLUMN IF EXISTS source_kind")

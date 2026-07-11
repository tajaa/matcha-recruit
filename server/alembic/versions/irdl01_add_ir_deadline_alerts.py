"""add ir_deadline_alert_log + seed ir_deadline_alerts scheduler row

Backs the IR deadline/SLA reminder worker (app/workers/tasks/ir_deadline_alerts.py).
IR was the only major domain without a deadline worker — compliance, legal,
grievance, leave, and discipline all have one. This adds:

  - ir_deadline_alert_log: an idempotency ledger so each (incident, alert_kind)
    fires at most once per day. CAPA due-date nudges dedupe on
    ir_corrective_actions.reminder_sent_at instead (migration ircapa01); this
    table covers the incident-scoped sweeps (stale critical, unclassified
    recordable, OSHA emergency countdown) that have no natural stamp column.
  - scheduler_settings row 'ir_deadline_alerts', seeded DISABLED (repo
    convention — the user enables it from /admin when ready).

Revision ID: irdl01
Revises: ircapa01
Create Date: 2026-07-11
"""

from alembic import op


revision = "irdl01"
down_revision = "ircapa01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ir_deadline_alert_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id UUID NOT NULL REFERENCES ir_incidents(id) ON DELETE CASCADE,
            company_id UUID NOT NULL,
            alert_kind VARCHAR(40) NOT NULL,
            sent_on DATE NOT NULL DEFAULT CURRENT_DATE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (incident_id, alert_kind, sent_on)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ir_deadline_alert_log_company "
        "ON ir_deadline_alert_log(company_id, sent_on);"
    )
    op.execute(
        """
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'ir_deadline_alerts',
            'IR Deadline & SLA Alerts',
            'Nudges owners on overdue corrective actions, stale critical/high incidents, '
            'unclassified OSHA recordables before the 300A/ITA deadlines, and the OSHA 8/24hr '
            'emergency reporting window. Best-effort; default off.',
            false,
            200
        )
        ON CONFLICT (task_key) DO NOTHING;
        """
    )


def downgrade():
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'ir_deadline_alerts'")
    op.execute("DROP TABLE IF EXISTS ir_deadline_alert_log")

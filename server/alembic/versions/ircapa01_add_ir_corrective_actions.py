"""add ir_corrective_actions — structured CAPA (corrective/preventive actions)

Promotes the single free-text ir_incidents.corrective_actions column from a
notes blob to an accountable child table: one row per action, each with its own
owner, due date, status lifecycle, and effectiveness verification.

The free-text column stays (the IR Copilot + AI recommendation cards still write
it); this table is additive — the accountable layer on top of the notes layer.

status lifecycle: open -> in_progress -> completed -> verified (or cancelled).
effectiveness (effective | ineffective | pending) captures the CAPA
effectiveness check EHS buyers expect after a corrective action is completed.

reminder_sent_at is stamped by the ir_deadline_alerts worker (migration irdl01)
so a due-date nudge fires at most once per day per action.

Revision ID: ircapa01
Revises: do01
Create Date: 2026-07-11
"""

from alembic import op


revision = "ircapa01"
# Chains off do01, the head this branch merged into. It was authored against
# oshacase0001 (a head at the time the branch was cut); leaving it there left
# the merged tree with two heads (do01 + ita01), which breaks
# `alembic upgrade head` in migrate-dev.sh / migrate-prod.sh.
down_revision = "do01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ir_corrective_actions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id UUID NOT NULL REFERENCES ir_incidents(id) ON DELETE CASCADE,
            company_id UUID NOT NULL,
            description TEXT NOT NULL,
            action_type VARCHAR(20) NOT NULL DEFAULT 'corrective'
                CHECK (action_type IN ('corrective', 'preventive')),
            priority VARCHAR(20) NOT NULL DEFAULT 'short_term'
                CHECK (priority IN ('immediate', 'short_term', 'long_term')),
            assigned_to UUID,
            assignee_name TEXT,
            due_date DATE,
            status VARCHAR(20) NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'in_progress', 'completed', 'verified', 'cancelled')),
            completed_at TIMESTAMPTZ,
            verified_by UUID,
            verified_at TIMESTAMPTZ,
            effectiveness VARCHAR(20)
                CHECK (effectiveness IN ('effective', 'ineffective', 'pending')),
            reminder_sent_at DATE,
            created_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ir_corrective_actions_incident "
        "ON ir_corrective_actions(incident_id);"
    )
    # Company-wide open/overdue sweeps (dashboard tile + deadline worker) filter
    # on (company_id, status, due_date).
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ir_corrective_actions_company_status_due "
        "ON ir_corrective_actions(company_id, status, due_date);"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS ir_corrective_actions")

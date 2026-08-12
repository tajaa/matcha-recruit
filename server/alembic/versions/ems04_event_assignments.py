"""Add channel assignments for EMS events.

Assignments are separate from the event's originating channel so one event
can be shared with more than one team conversation without changing history.
"""

from alembic import op


revision = "ems04"
down_revision = "ems03"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ems_event_assignments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            event_id UUID NOT NULL REFERENCES ems_events(id) ON DELETE CASCADE,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            assignee_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            assigned_by UUID NOT NULL REFERENCES users(id),
            shared_title VARCHAR(300) NOT NULL,
            instructions TEXT,
            due_at TIMESTAMPTZ,
            status VARCHAR(20) NOT NULL DEFAULT 'assigned'
                CHECK (status IN ('assigned', 'completed', 'cancelled')),
            completed_by UUID REFERENCES users(id),
            completed_at TIMESTAMPTZ,
            client_request_id UUID UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_ems_event_assignment_active
        ON ems_event_assignments(event_id, channel_id, assignee_user_id)
        WHERE status = 'assigned'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ems_event_assignments_channel_status
        ON ems_event_assignments(channel_id, status, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ems_event_assignments_event
        ON ems_event_assignments(event_id, created_at DESC)
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS ems_event_assignments")

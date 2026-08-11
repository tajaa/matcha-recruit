"""Event confirmation, resolution metadata, and channel action pointers.

Non-urgent EMS classifications are stored in ``ems_event_drafts`` until a
reporter or reviewer confirms them. Existing ``dismissed`` event rows remain
valid; the UI presents that state as "No action".

Revision ID: ems03
Revises: mwperm01, inventory01
"""

from alembic import op


revision = "ems03"
down_revision = ("mwperm01", "inventory01")
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE channel_messages ADD COLUMN IF NOT EXISTS "
        "metadata JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute(
        "ALTER TABLE ems_events ADD COLUMN IF NOT EXISTS resolved_by UUID REFERENCES users(id)"
    )
    op.execute(
        "ALTER TABLE ems_events ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE ems_events ADD COLUMN IF NOT EXISTS resolution_note TEXT"
    )
    op.execute(
        "ALTER TABLE ems_events ADD COLUMN IF NOT EXISTS resolution_code VARCHAR(20)"
    )
    op.execute(
        "ALTER TABLE ems_events ADD COLUMN IF NOT EXISTS "
        "duplicate_of_event_id UUID REFERENCES ems_events(id) ON DELETE SET NULL"
    )
    op.execute("ALTER TABLE ems_events DROP CONSTRAINT IF EXISTS ems_events_status_check")
    op.execute(
        "ALTER TABLE ems_events ADD CONSTRAINT ems_events_status_check "
        "CHECK (status IN ('logged', 'completed', 'promoted', 'dismissed'))"
    )
    op.execute(
        "ALTER TABLE ems_events ADD CONSTRAINT ems_events_resolution_code_check "
        "CHECK (resolution_code IS NULL OR resolution_code IN "
        "('handled', 'not_event', 'duplicate', 'informational'))"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ems_event_drafts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            source_message_id UUID NOT NULL REFERENCES channel_messages(id) ON DELETE CASCADE,
            confirmation_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            reporter_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            narrative TEXT NOT NULL,
            classified JSONB NOT NULL DEFAULT '{}'::jsonb,
            urgency VARCHAR(10) CHECK (urgency IN ('osha', 'severe')),
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'confirmed', 'rejected', 'expired')),
            event_id UUID REFERENCES ems_events(id) ON DELETE SET NULL,
            decided_by UUID REFERENCES users(id) ON DELETE SET NULL,
            decided_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '7 days',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (source_message_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ems_event_drafts_company_status "
        "ON ems_event_drafts(company_id, status, created_at DESC)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS ems_event_drafts")
    op.execute("ALTER TABLE ems_events DROP CONSTRAINT IF EXISTS ems_events_resolution_code_check")
    op.execute("ALTER TABLE ems_events DROP CONSTRAINT IF EXISTS ems_events_status_check")
    op.execute(
        "ALTER TABLE ems_events ADD CONSTRAINT ems_events_status_check "
        "CHECK (status IN ('logged', 'promoted', 'dismissed'))"
    )
    op.execute("ALTER TABLE ems_events DROP COLUMN IF EXISTS duplicate_of_event_id")
    op.execute("ALTER TABLE ems_events DROP COLUMN IF EXISTS resolution_code")
    op.execute("ALTER TABLE ems_events DROP COLUMN IF EXISTS resolution_note")
    op.execute("ALTER TABLE ems_events DROP COLUMN IF EXISTS resolved_at")
    op.execute("ALTER TABLE ems_events DROP COLUMN IF EXISTS resolved_by")
    op.execute("ALTER TABLE channel_messages DROP COLUMN IF EXISTS metadata")

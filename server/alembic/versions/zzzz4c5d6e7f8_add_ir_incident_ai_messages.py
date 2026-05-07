"""IR Copilot conversation log.

Adds ir_incident_ai_messages — single chat-shaped log per incident, mixing
free-text utterances ('text'), structured action cards ('card'), and system
action receipts ('event'). Powers the IR Copilot panel.

Revision ID: zzzz4c5d6e7f8
Revises: zzzz3b4c5d6e7
Create Date: 2026-05-06
"""
from alembic import op


revision = "zzzz4c5d6e7f8"
down_revision = "zzzz3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ir_incident_ai_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id UUID NOT NULL REFERENCES ir_incidents(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL CHECK (role IN ('user','assistant','system')),
            message_type VARCHAR(20) NOT NULL DEFAULT 'text'
                CHECK (message_type IN ('text','card','event')),
            content TEXT NOT NULL,
            metadata JSONB,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ir_ai_messages_incident_id "
        "ON ir_incident_ai_messages(incident_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ir_ai_messages_created_at "
        "ON ir_incident_ai_messages(created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_ir_ai_messages_created_at")
    op.execute("DROP INDEX IF EXISTS idx_ir_ai_messages_incident_id")
    op.execute("DROP TABLE IF EXISTS ir_incident_ai_messages")

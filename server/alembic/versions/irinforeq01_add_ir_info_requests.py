"""Add ir_info_requests (IR Copilot "Request More Info" email workflow).

Backs a single-use, token-gated public form: an admin composes questions
(seeded from the Copilot's own open_questions + any custom ones), emails an
outside party a link scoped to one incident, and the recipient's answers are
stored here for the admin to review — never auto-written to the incident.

Revision ID: irinforeq01
Revises: tellus_app_03
Create Date: 2026-07-03
"""
from alembic import op


revision = "irinforeq01"
down_revision = "tellus_app_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ir_info_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id UUID NOT NULL REFERENCES ir_incidents(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            token VARCHAR(32) UNIQUE NOT NULL,
            recipient_name VARCHAR(255) NOT NULL,
            recipient_email VARCHAR(255) NOT NULL,
            questions JSONB NOT NULL,
            custom_message TEXT,
            responses JSONB,
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'submitted', 'expired', 'revoked')),
            requested_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            submitted_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ir_info_requests_incident ON ir_info_requests(incident_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ir_info_requests_token ON ir_info_requests(token)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ir_info_requests")
